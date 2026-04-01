import base64
import hmac
import json
import logging
import mimetypes
import os
import re
import secrets
import smtplib
import sqlite3
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from hashlib import pbkdf2_hmac, sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.parse import quote_plus
from urllib.request import urlopen


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_DIR = ROOT_DIR / "backend" / "data"
LOG_DIR = ROOT_DIR / "backend" / "logs"
DB_PATH = DATA_DIR / "fps.db"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_PAGE_SIZE = 8
MAX_PAGE_SIZE = 50

JWT_SECRET = os.environ.get("FPS_JWT_SECRET", "fps-dev-secret-change-this")
JWT_EXP_HOURS = 12

VALID_TYPES = {"Journal", "Conference", "Article", "Books", "Chapter"}
VALID_STATUS = {"Draft", "Submitted", "Accepted", "Published"}
VALID_SCOPE = {"National Conference", "International Conference"}
VALID_INDEXING = {"Scopus", "Non-Scopus", "SCI", "Non-SCI"}
EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
ALLOWED_EMAIL_DOMAIN = "@bitsathy.ac.in"
OTP_EXP_MINUTES = 10
MAX_OTP_ATTEMPTS = 5
GOOGLE_CLIENT_ID = os.environ.get("FPS_GOOGLE_CLIENT_ID", "").strip()


class ValidationError(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.FileHandler(LOG_DIR / "server.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def ensure_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS faculties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS publications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                faculty_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                authors TEXT NOT NULL,
                venue TEXT NOT NULL,
                pub_type TEXT NOT NULL,
                conference_scope TEXT NOT NULL DEFAULT '',
                indexing_params TEXT NOT NULL DEFAULT '',
                published_date TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                publication_status TEXT NOT NULL DEFAULT 'Submitted',
                citation_count INTEGER NOT NULL DEFAULT 0,
                publisher_name TEXT NOT NULL DEFAULT '',
                doi TEXT,
                file_name TEXT,
                file_type TEXT,
                file_data BLOB,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (faculty_id) REFERENCES faculties(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                otp_hash TEXT NOT NULL,
                otp_salt TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                used_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        columns = {row[1] for row in conn.execute("PRAGMA table_info(publications)").fetchall()}
        migrations = [
            ("content", "ALTER TABLE publications ADD COLUMN content TEXT NOT NULL DEFAULT ''"),
            (
                "conference_scope",
                "ALTER TABLE publications ADD COLUMN conference_scope TEXT NOT NULL DEFAULT ''",
            ),
            (
                "indexing_params",
                "ALTER TABLE publications ADD COLUMN indexing_params TEXT NOT NULL DEFAULT ''",
            ),
            (
                "publication_status",
                "ALTER TABLE publications ADD COLUMN publication_status TEXT NOT NULL DEFAULT 'Submitted'",
            ),
            ("citation_count", "ALTER TABLE publications ADD COLUMN citation_count INTEGER NOT NULL DEFAULT 0"),
            ("publisher_name", "ALTER TABLE publications ADD COLUMN publisher_name TEXT NOT NULL DEFAULT ''"),
            ("file_name", "ALTER TABLE publications ADD COLUMN file_name TEXT"),
            ("file_type", "ALTER TABLE publications ADD COLUMN file_type TEXT"),
            ("file_data", "ALTER TABLE publications ADD COLUMN file_data BLOB"),
            ("updated_at", "ALTER TABLE publications ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"),
        ]

        for column_name, query in migrations:
            if column_name not in columns:
                conn.execute(query)

        conn.execute("UPDATE publications SET updated_at = created_at WHERE COALESCE(updated_at, '') = ''")
        conn.execute(
            """
            UPDATE publications
            SET conference_scope = CASE
                WHEN conference_scope = 'National' THEN 'National Conference'
                WHEN conference_scope = 'International' THEN 'International Conference'
                ELSE conference_scope
            END
            """
        )
        conn.execute(
            """
            DELETE FROM password_reset_otps
            WHERE used_at IS NOT NULL OR expires_at < ?
            """,
            (utc_now().isoformat(),),
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_publications_faculty_date ON publications(faculty_id, published_date DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_publications_faculty_type ON publications(faculty_id, pub_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_publications_faculty_scope ON publications(faculty_id, conference_scope)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_faculties_email ON faculties(email)")
        conn.commit()


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return digest.hex(), salt.hex()


def verify_password(password: str, expected_hash: str, salt_hex: str) -> bool:
    candidate_hash, _ = hash_password(password, salt_hex)
    return secrets.compare_digest(candidate_hash, expected_hash)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign_jwt(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    message = f"{encoded_header}.{encoded_payload}"
    signature = hmac.new(JWT_SECRET.encode("utf-8"), message.encode("utf-8"), sha256).digest()
    return f"{message}.{_b64url_encode(signature)}"


def issue_token(faculty: sqlite3.Row) -> str:
    now = utc_now()
    payload = {
        "sub": str(faculty["id"]),
        "name": faculty["name"],
        "email": faculty["email"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_EXP_HOURS)).timestamp()),
    }
    return sign_jwt(payload)


def decode_jwt(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        message = f"{parts[0]}.{parts[1]}"
        expected_sig = hmac.new(JWT_SECRET.encode("utf-8"), message.encode("utf-8"), sha256).digest()
        candidate_sig = _b64url_decode(parts[2])
        if not hmac.compare_digest(expected_sig, candidate_sig):
            return None
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(utc_now().timestamp()):
            return None
        return payload
    except Exception:
        return None

def sanitize_filename(filename: str) -> str:
    if not filename:
        return "attachment"
    safe = Path(filename).name.replace('"', "").strip()
    return safe or "attachment"


def validate_email(value: str) -> bool:
    return bool(value and EMAIL_REGEX.match(value))


def is_allowed_institution_email(email: str) -> bool:
    return validate_email(email) and email.lower().endswith(ALLOWED_EMAIL_DOMAIN)


def validate_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def send_otp_email(email: str, otp: str) -> bool:
    smtp_host = os.environ.get("FPS_SMTP_HOST", "").strip()
    smtp_port = int(os.environ.get("FPS_SMTP_PORT", "587"))
    smtp_user = os.environ.get("FPS_SMTP_USER", "").strip()
    smtp_password = os.environ.get("FPS_SMTP_PASSWORD", "").strip()
    sender = os.environ.get("FPS_SMTP_FROM", smtp_user).strip()

    if not smtp_host or not smtp_user or not smtp_password or not sender:
        logging.warning("SMTP not configured for OTP delivery.")
        return False

    message = EmailMessage()
    message["Subject"] = "FPS Password Reset OTP"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        f"Your OTP for Faculty Publication System password reset is {otp}. "
        f"It is valid for {OTP_EXP_MINUTES} minutes."
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)
    return True


def verify_google_id_token(id_token: str) -> dict | None:
    if not id_token:
        return None
    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={quote_plus(id_token)}"
        with urlopen(url, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    audience = str(data.get("aud") or "")
    email = str(data.get("email") or "").strip().lower()
    email_verified = str(data.get("email_verified") or "").lower() == "true"
    name = str(data.get("name") or "").strip()

    if GOOGLE_CLIENT_ID and audience != GOOGLE_CLIENT_ID:
        return None
    if not email_verified or not is_allowed_institution_email(email):
        return None
    return {"email": email, "name": name or email.split("@")[0]}


def normalize_indexing(values: list) -> list[str]:
    normalized: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        if value not in VALID_INDEXING:
            raise ValidationError("Unsupported indexing parameter.")
        if value not in normalized:
            normalized.append(value)
    return normalized


def parse_int_query(value: str, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def parse_publication_payload(payload: dict) -> dict:
    title = str(payload.get("title") or "").strip()
    authors = str(payload.get("authors") or "").strip()
    venue = str(payload.get("venue") or "").strip()
    pub_type = str(payload.get("type") or "").strip()
    conference_scope = str(payload.get("conferenceScope") or "").strip()
    submission_date = str(payload.get("submissionDate") or payload.get("publishedDate") or "").strip()
    content = str(payload.get("content") or "").strip()
    publisher_name = str(payload.get("publisherName") or "").strip()
    doi = str(payload.get("doi") or "").strip()

    if not title or not authors or not venue or not content:
        raise ValidationError("Title, authors, venue and content are required.")
    if pub_type not in VALID_TYPES:
        raise ValidationError("Invalid publication type.")
    if not validate_date(submission_date):
        raise ValidationError("Invalid submission date. Use YYYY-MM-DD.")

    impact_raw = payload.get("impactFactor", payload.get("citationCount", 0))
    try:
        impact_factor = float(impact_raw)
    except (TypeError, ValueError):
        raise ValidationError("Impact factor must be numeric.")
    if impact_factor < 0:
        raise ValidationError("Impact factor cannot be negative.")

    indexing_values = payload.get("indexing") or []
    if not isinstance(indexing_values, list):
        raise ValidationError("Invalid indexing payload.")
    indexing = normalize_indexing(indexing_values)

    if pub_type == "Conference":
        if conference_scope not in VALID_SCOPE:
            raise ValidationError("Conference scope must be National Conference or International Conference.")
    else:
        conference_scope = "N/A"

    attachment = payload.get("attachment")
    remove_attachment = bool(payload.get("removeAttachment"))
    file_name = None
    file_type = None
    file_data = None
    attachment_provided = False

    if attachment is not None:
        attachment_provided = True
        if not isinstance(attachment, dict):
            raise ValidationError("Invalid attachment payload.")
        file_name = sanitize_filename(str(attachment.get("name") or "attachment"))
        file_type = str(attachment.get("type") or "application/octet-stream").strip() or "application/octet-stream"
        b64 = str(attachment.get("data") or "").strip()
        if not b64:
            raise ValidationError("Attachment data is missing.")
        try:
            file_data = base64.b64decode(b64, validate=True)
        except Exception as exc:
            raise ValidationError("Invalid file encoding.") from exc
        if len(file_data) > MAX_UPLOAD_BYTES:
            raise ValidationError("File size exceeds 10 MB limit.")

    return {
        "title": title,
        "authors": authors,
        "venue": venue,
        "pub_type": pub_type,
        "conference_scope": conference_scope,
        "indexing": indexing,
        "submission_date": submission_date,
        "content": content,
        "impact_factor": impact_factor,
        "publisher_name": publisher_name,
        "doi": doi,
        "file_name": file_name,
        "file_type": file_type,
        "file_data": file_data,
        "attachment_provided": attachment_provided,
        "remove_attachment": remove_attachment,
    }


class FacultyPublicationHandler(BaseHTTPRequestHandler):
    server_version = "FPS/2.0"

    def log_message(self, format: str, *args) -> None:
        logging.info("%s - %s", self.address_string(), format % args)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _apply_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self' https://accounts.google.com; "
            "img-src 'self' data:; connect-src 'self'; frame-src https://accounts.google.com;",
        )

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._apply_security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_binary(self, status: int, body: bytes, content_type: str, extra_headers: dict | None = None) -> None:
        self.send_response(status)
        self._apply_security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            return {}
        if content_length > MAX_UPLOAD_BYTES + (512 * 1024):
            raise ValidationError("Request payload too large.")

        raw = self.rfile.read(content_length)
        if not raw:
            return {}

        try:
            parsed = json.loads(raw.decode("utf-8"))
            if isinstance(parsed, dict):
                return parsed
            raise ValidationError("JSON object payload expected.")
        except json.JSONDecodeError as exc:
            raise ValidationError("Invalid JSON payload.") from exc

    def _parse_pub_id(self, path: str, with_suffix: str | None = None) -> int | None:
        parts = path.strip("/").split("/")
        if with_suffix:
            if len(parts) != 4 or parts[0] != "api" or parts[1] != "publications" or parts[3] != with_suffix:
                return None
            pub_id = parts[2]
        else:
            if len(parts) != 3 or parts[0] != "api" or parts[1] != "publications":
                return None
            pub_id = parts[2]

        if not pub_id.isdigit():
            return None
        return int(pub_id)

    def _get_token(self) -> str | None:
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header.removeprefix("Bearer ").strip()
        return None

    def _auth_faculty(self) -> sqlite3.Row | None:
        token = self._get_token()
        if not token:
            return None
        payload = decode_jwt(token)
        if not payload:
            return None

        sub = payload.get("sub")
        email = payload.get("email")
        if not str(sub).isdigit() or not email:
            return None

        with self._connect() as conn:
            return conn.execute(
                "SELECT id, name, email FROM faculties WHERE id = ? AND email = ?",
                (int(sub), str(email).lower()),
            ).fetchone()

    def _format_publication(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "authors": row["authors"],
            "venue": row["venue"],
            "type": row["pub_type"],
            "conferenceScope": row["conference_scope"] or "",
            "indexing": [value for value in (row["indexing_params"] or "").split(",") if value],
            "submissionDate": row["published_date"],
            "publishedDate": row["published_date"],
            "content": row["content"] or "",
            "impactFactor": float(row["citation_count"] or 0),
            "citationCount": float(row["citation_count"] or 0),
            "publisherName": row["publisher_name"] or "",
            "doi": row["doi"] or "",
            "hasAttachment": bool(row["file_name"]),
            "fileName": row["file_name"] or "",
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def _handle_static(self, path: str) -> None:
        route_path = "login.html" if path in {"/", ""} else path.lstrip("/")
        file_path = (FRONTEND_DIR / route_path).resolve()

        if FRONTEND_DIR not in file_path.parents and file_path != FRONTEND_DIR:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Forbidden"})
            return

        if not file_path.exists() or not file_path.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "File not found"})
            return

        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/"):
            content_type += "; charset=utf-8"
        self._send_binary(HTTPStatus.OK, content, content_type)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._apply_security_headers()
        self.send_header("Allow", "GET,POST,PUT,DELETE,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        try:
            if parsed.path == "/api/health":
                self._send_json(HTTPStatus.OK, {"status": "ok"})
                return

            if parsed.path == "/api/auth/config":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "allowedDomain": ALLOWED_EMAIL_DOMAIN.lstrip("@"),
                        "googleEnabled": bool(GOOGLE_CLIENT_ID),
                        "googleClientId": GOOGLE_CLIENT_ID,
                    },
                )
                return

            if parsed.path == "/api/auth/me":
                faculty = self._auth_faculty()
                if not faculty:
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                    return
                self._send_json(
                    HTTPStatus.OK,
                    {"faculty": {"id": faculty["id"], "name": faculty["name"], "email": faculty["email"]}},
                )
                return

            if parsed.path == "/api/publications/stats":
                faculty = self._auth_faculty()
                if not faculty:
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                    return

                with self._connect() as conn:
                    rows = conn.execute(
                        """
                        SELECT pub_type, publication_status, conference_scope, indexing_params
                        FROM publications
                        WHERE faculty_id = ?
                        """,
                        (faculty["id"],),
                    ).fetchall()

                stats = {
                    "total": 0,
                    "journals": 0,
                    "conferences": 0,
                    "nationalConferences": 0,
                    "internationalConferences": 0,
                    "scopusIndexed": 0,
                    "nonScopusIndexed": 0,
                    "sciIndexed": 0,
                    "nonSciIndexed": 0,
                }
                for row in rows:
                    stats["total"] += 1
                    if row["pub_type"] in {"Journal", "Article"}:
                        stats["journals"] += 1
                    if row["pub_type"] == "Conference":
                        stats["conferences"] += 1
                        if row["conference_scope"] == "National Conference":
                            stats["nationalConferences"] += 1
                        if row["conference_scope"] == "International Conference":
                            stats["internationalConferences"] += 1

                    indexing_set = {value for value in (row["indexing_params"] or "").split(",") if value}
                    if "Scopus" in indexing_set:
                        stats["scopusIndexed"] += 1
                    if "Non-Scopus" in indexing_set:
                        stats["nonScopusIndexed"] += 1
                    if "SCI" in indexing_set:
                        stats["sciIndexed"] += 1
                    if "Non-SCI" in indexing_set:
                        stats["nonSciIndexed"] += 1

                self._send_json(HTTPStatus.OK, {"stats": stats})
                return

            if parsed.path == "/api/publications":
                faculty = self._auth_faculty()
                if not faculty:
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                    return

                query_params = parse_qs(parsed.query)
                q = query_params.get("q", [""])[0].strip().lower()
                pub_type = query_params.get("type", [""])[0].strip()
                year_filter = query_params.get("year", [""])[0].strip()
                scope_filter = query_params.get("scope", [""])[0].strip()
                indexing_filter = query_params.get("indexing", [""])[0].strip()
                page = parse_int_query(query_params.get("page", ["1"])[0], 1, 1, 100000)
                page_size = parse_int_query(query_params.get("page_size", [str(DEFAULT_PAGE_SIZE)])[0], DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)

                sql = """
                    SELECT id, title, authors, venue, pub_type, conference_scope, indexing_params, published_date,
                           content, publication_status, citation_count, publisher_name, doi, file_name, created_at, updated_at
                    FROM publications
                    WHERE faculty_id = ?
                """
                count_sql = "SELECT COUNT(*) AS total FROM publications WHERE faculty_id = ?"
                args: list = [faculty["id"]]
                count_args: list = [faculty["id"]]

                if pub_type:
                    sql += " AND pub_type = ?"
                    args.append(pub_type)
                    count_sql += " AND pub_type = ?"
                    count_args.append(pub_type)
                if year_filter and year_filter.isdigit():
                    sql += " AND strftime('%Y', published_date) = ?"
                    args.append(year_filter)
                    count_sql += " AND strftime('%Y', published_date) = ?"
                    count_args.append(year_filter)
                if scope_filter in VALID_SCOPE:
                    sql += " AND conference_scope = ?"
                    args.append(scope_filter)
                    count_sql += " AND conference_scope = ?"
                    count_args.append(scope_filter)
                if indexing_filter in VALID_INDEXING:
                    sql += " AND instr(',' || indexing_params || ',', ',' || ? || ',') > 0"
                    args.append(indexing_filter)
                    count_sql += " AND instr(',' || indexing_params || ',', ',' || ? || ',') > 0"
                    count_args.append(indexing_filter)
                if q:
                    like = f"%{q}%"
                    sql += " AND (LOWER(title) LIKE ? OR LOWER(authors) LIKE ? OR LOWER(venue) LIKE ? OR LOWER(content) LIKE ?)"
                    args.extend([like, like, like, like])
                    count_sql += " AND (LOWER(title) LIKE ? OR LOWER(authors) LIKE ? OR LOWER(venue) LIKE ? OR LOWER(content) LIKE ?)"
                    count_args.extend([like, like, like, like])

                sql += " ORDER BY published_date DESC, created_at DESC"
                sql += " LIMIT ? OFFSET ?"
                args.extend([page_size, (page - 1) * page_size])

                with self._connect() as conn:
                    total = int(conn.execute(count_sql, count_args).fetchone()["total"])
                    rows = conn.execute(sql, args).fetchall()

                self._send_json(
                    HTTPStatus.OK,
                    {
                        "publications": [self._format_publication(row) for row in rows],
                        "pagination": {
                            "page": page,
                            "pageSize": page_size,
                            "total": total,
                            "totalPages": max(1, (total + page_size - 1) // page_size),
                        },
                    },
                )
                return

            pub_file_id = self._parse_pub_id(parsed.path, with_suffix="file")
            if pub_file_id is not None:
                faculty = self._auth_faculty()
                if not faculty:
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                    return

                with self._connect() as conn:
                    row = conn.execute(
                        """
                        SELECT file_name, file_type, file_data
                        FROM publications
                        WHERE id = ? AND faculty_id = ?
                        """,
                        (pub_file_id, faculty["id"]),
                    ).fetchone()

                if not row or row["file_data"] is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "Attachment not found."})
                    return

                file_name = sanitize_filename(row["file_name"] or f"publication-{pub_file_id}")
                file_type = row["file_type"] or "application/octet-stream"
                self._send_binary(
                    HTTPStatus.OK,
                    row["file_data"],
                    file_type,
                    {"Content-Disposition": f'inline; filename="{file_name}"'},
                )
                return

            pub_id = self._parse_pub_id(parsed.path)
            if pub_id is not None:
                faculty = self._auth_faculty()
                if not faculty:
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                    return

                with self._connect() as conn:
                    row = conn.execute(
                        """
                        SELECT id, title, authors, venue, pub_type, conference_scope, indexing_params, published_date,
                               content, publication_status, citation_count, publisher_name, doi, file_name, created_at, updated_at
                        FROM publications
                        WHERE id = ? AND faculty_id = ?
                        """,
                        (pub_id, faculty["id"]),
                    ).fetchone()

                if not row:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "Publication not found."})
                    return

                self._send_json(HTTPStatus.OK, {"publication": self._format_publication(row)})
                return

            self._handle_static(parsed.path)
        except Exception:
            logging.exception("GET failed: %s", parsed.path)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal server error"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json_body()

            if parsed.path == "/api/auth/register":
                name = str(payload.get("name") or "").strip()
                email = str(payload.get("email") or "").strip().lower()
                password = str(payload.get("password") or "").strip()

                if not name:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Author name is required."})
                    return
                if not is_allowed_institution_email(email):
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": f"Only {ALLOWED_EMAIL_DOMAIN} email addresses are allowed."},
                    )
                    return
                if len(password) < 8:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Password must be at least 8 characters."})
                    return

                password_hash, password_salt = hash_password(password)

                with self._connect() as conn:
                    existing = conn.execute("SELECT id FROM faculties WHERE email = ?", (email,)).fetchone()
                    if existing:
                        self._send_json(HTTPStatus.CONFLICT, {"error": "Account already exists for this email."})
                        return

                    conn.execute(
                        """
                        INSERT INTO faculties (name, email, password_hash, password_salt, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (name, email, password_hash, password_salt, utc_now().isoformat()),
                    )
                    faculty = conn.execute(
                        "SELECT id, name, email FROM faculties WHERE email = ?",
                        (email,),
                    ).fetchone()
                    conn.commit()

                token = issue_token(faculty)
                self._send_json(
                    HTTPStatus.CREATED,
                    {"token": token, "faculty": {"id": faculty["id"], "name": faculty["name"], "email": faculty["email"]}},
                )
                return

            if parsed.path == "/api/auth/login":
                name = str(payload.get("name") or "").strip()
                email = str(payload.get("email") or "").strip().lower()
                password = str(payload.get("password") or "").strip()

                if not is_allowed_institution_email(email) or not password:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": f"Use a valid {ALLOWED_EMAIL_DOMAIN} email and password."},
                    )
                    return

                with self._connect() as conn:
                    faculty = conn.execute(
                        "SELECT id, name, email, password_hash, password_salt FROM faculties WHERE email = ?",
                        (email,),
                    ).fetchone()

                    if not faculty and name:
                        password_hash, password_salt = hash_password(password)
                        conn.execute(
                            """
                            INSERT INTO faculties (name, email, password_hash, password_salt, created_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (name, email, password_hash, password_salt, utc_now().isoformat()),
                        )
                        faculty = conn.execute(
                            "SELECT id, name, email, password_hash, password_salt FROM faculties WHERE email = ?",
                            (email,),
                        ).fetchone()
                        conn.commit()

                if not faculty or not verify_password(password, faculty["password_hash"], faculty["password_salt"]):
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Invalid credentials."})
                    return

                token = issue_token(faculty)
                self._send_json(
                    HTTPStatus.OK,
                    {"token": token, "faculty": {"id": faculty["id"], "name": faculty["name"], "email": faculty["email"]}},
                )
                return

            if parsed.path == "/api/auth/request-otp":
                email = str(payload.get("email") or "").strip().lower()
                if not is_allowed_institution_email(email):
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": f"Only {ALLOWED_EMAIL_DOMAIN} email addresses are allowed."},
                    )
                    return

                with self._connect() as conn:
                    faculty = conn.execute("SELECT id FROM faculties WHERE email = ?", (email,)).fetchone()
                    if not faculty:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "No account found for this email. Create account first."})
                        return

                    otp = generate_otp()
                    otp_hash, otp_salt = hash_password(otp)
                    expires_at = (utc_now() + timedelta(minutes=OTP_EXP_MINUTES)).isoformat()
                    conn.execute("DELETE FROM password_reset_otps WHERE email = ? AND used_at IS NULL", (email,))
                    conn.execute(
                        """
                        INSERT INTO password_reset_otps (email, otp_hash, otp_salt, expires_at, attempts, created_at)
                        VALUES (?, ?, ?, ?, 0, ?)
                        """,
                        (email, otp_hash, otp_salt, expires_at, utc_now().isoformat()),
                    )
                    conn.commit()

                sent = False
                try:
                    sent = send_otp_email(email, otp)
                except Exception:
                    logging.exception("OTP email send failed for %s", email)

                if not sent:
                    self._send_json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"error": "OTP delivery failed. Mail server is not configured. Contact administrator."},
                    )
                    return

                self._send_json(HTTPStatus.OK, {"ok": True, "message": "OTP sent to your institutional email."})
                return

            if parsed.path == "/api/auth/reset-password":
                email = str(payload.get("email") or "").strip().lower()
                otp = str(payload.get("otp") or "").strip()
                new_password = str(payload.get("newPassword") or "").strip()

                if not is_allowed_institution_email(email):
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": f"Only {ALLOWED_EMAIL_DOMAIN} email addresses are allowed."},
                    )
                    return
                if not otp.isdigit() or len(otp) != 6:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "OTP must be a 6-digit code."})
                    return
                if len(new_password) < 8:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Password must be at least 8 characters."})
                    return

                with self._connect() as conn:
                    reset_row = conn.execute(
                        """
                        SELECT id, otp_hash, otp_salt, expires_at, attempts
                        FROM password_reset_otps
                        WHERE email = ? AND used_at IS NULL
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (email,),
                    ).fetchone()
                    faculty = conn.execute(
                        "SELECT id FROM faculties WHERE email = ?",
                        (email,),
                    ).fetchone()

                    if not faculty or not reset_row:
                        self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid or expired OTP."})
                        return

                    if datetime.fromisoformat(reset_row["expires_at"]) < utc_now():
                        self._send_json(HTTPStatus.BAD_REQUEST, {"error": "OTP expired. Request a new one."})
                        return
                    if int(reset_row["attempts"]) >= MAX_OTP_ATTEMPTS:
                        self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Too many attempts. Request a new OTP."})
                        return

                    if not verify_password(otp, reset_row["otp_hash"], reset_row["otp_salt"]):
                        conn.execute(
                            "UPDATE password_reset_otps SET attempts = attempts + 1 WHERE id = ?",
                            (reset_row["id"],),
                        )
                        conn.commit()
                        self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid OTP."})
                        return

                    password_hash, password_salt = hash_password(new_password)
                    conn.execute(
                        "UPDATE faculties SET password_hash = ?, password_salt = ? WHERE email = ?",
                        (password_hash, password_salt, email),
                    )
                    conn.execute(
                        "UPDATE password_reset_otps SET used_at = ? WHERE id = ?",
                        (utc_now().isoformat(), reset_row["id"]),
                    )
                    conn.commit()

                self._send_json(HTTPStatus.OK, {"ok": True, "message": "Password reset successful."})
                return

            if parsed.path == "/api/auth/google":
                id_token = str(payload.get("idToken") or "").strip()
                google_user = verify_google_id_token(id_token)
                if not google_user:
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Invalid Google sign-in token."})
                    return

                email = google_user["email"]
                name = google_user["name"]
                with self._connect() as conn:
                    faculty = conn.execute(
                        "SELECT id, name, email FROM faculties WHERE email = ?",
                        (email,),
                    ).fetchone()
                    if not faculty:
                        temp_hash, temp_salt = hash_password(secrets.token_urlsafe(24))
                        conn.execute(
                            """
                            INSERT INTO faculties (name, email, password_hash, password_salt, created_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (name, email, temp_hash, temp_salt, utc_now().isoformat()),
                        )
                        faculty = conn.execute(
                            "SELECT id, name, email FROM faculties WHERE email = ?",
                            (email,),
                        ).fetchone()
                        conn.commit()

                token = issue_token(faculty)
                self._send_json(
                    HTTPStatus.OK,
                    {"token": token, "faculty": {"id": faculty["id"], "name": faculty["name"], "email": faculty["email"]}},
                )
                return

            if parsed.path == "/api/auth/logout":
                self._send_json(HTTPStatus.OK, {"ok": True})
                return

            if parsed.path == "/api/publications":
                faculty = self._auth_faculty()
                if not faculty:
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                    return

                try:
                    clean = parse_publication_payload(payload)
                except ValidationError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                with self._connect() as conn:
                    now = utc_now().isoformat()
                    conn.execute(
                        """
                        INSERT INTO publications (
                            faculty_id, title, authors, venue, pub_type, conference_scope, indexing_params,
                            published_date, content, publication_status, citation_count, publisher_name, doi,
                            file_name, file_type, file_data, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            faculty["id"],
                            clean["title"],
                            clean["authors"],
                            clean["venue"],
                            clean["pub_type"],
                            clean["conference_scope"],
                            ",".join(clean["indexing"]),
                            clean["submission_date"],
                            clean["content"],
                            "Submitted",
                            clean["impact_factor"],
                            clean["publisher_name"],
                            clean["doi"] or None,
                            clean["file_name"],
                            clean["file_type"],
                            clean["file_data"],
                            now,
                            now,
                        ),
                    )
                    publication_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
                    conn.commit()

                self._send_json(HTTPStatus.CREATED, {"ok": True, "publicationId": publication_id})
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except ValidationError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            logging.exception("POST failed: %s", parsed.path)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal server error"})

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)

        try:
            pub_id = self._parse_pub_id(parsed.path)
            if pub_id is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return

            faculty = self._auth_faculty()
            if not faculty:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                return

            payload = self._read_json_body()
            try:
                clean = parse_publication_payload(payload)
            except ValidationError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT id, file_name, file_type, file_data FROM publications WHERE id = ? AND faculty_id = ?",
                    (pub_id, faculty["id"]),
                ).fetchone()
                if not existing:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "Publication not found."})
                    return

                file_name = existing["file_name"]
                file_type = existing["file_type"]
                file_data = existing["file_data"]

                if clean["remove_attachment"]:
                    file_name = None
                    file_type = None
                    file_data = None
                elif clean["attachment_provided"]:
                    file_name = clean["file_name"]
                    file_type = clean["file_type"]
                    file_data = clean["file_data"]

                conn.execute(
                    """
                    UPDATE publications
                    SET title = ?, authors = ?, venue = ?, pub_type = ?, conference_scope = ?, indexing_params = ?,
                        published_date = ?, content = ?, publication_status = ?, citation_count = ?, publisher_name = ?,
                        doi = ?, file_name = ?, file_type = ?, file_data = ?, updated_at = ?
                    WHERE id = ? AND faculty_id = ?
                    """,
                    (
                        clean["title"],
                        clean["authors"],
                        clean["venue"],
                        clean["pub_type"],
                        clean["conference_scope"],
                        ",".join(clean["indexing"]),
                        clean["submission_date"],
                        clean["content"],
                        "Submitted",
                        clean["impact_factor"],
                        clean["publisher_name"],
                        clean["doi"] or None,
                        file_name,
                        file_type,
                        file_data,
                        utc_now().isoformat(),
                        pub_id,
                        faculty["id"],
                    ),
                )
                conn.commit()

            self._send_json(HTTPStatus.OK, {"ok": True})
        except ValidationError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            logging.exception("PUT failed: %s", parsed.path)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal server error"})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)

        try:
            pub_id = self._parse_pub_id(parsed.path)
            if pub_id is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return

            faculty = self._auth_faculty()
            if not faculty:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                return

            with self._connect() as conn:
                deleted = conn.execute(
                    "DELETE FROM publications WHERE id = ? AND faculty_id = ?",
                    (pub_id, faculty["id"]),
                ).rowcount
                conn.commit()

            if not deleted:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Publication not found."})
                return

            self._send_json(HTTPStatus.OK, {"ok": True})
        except Exception:
            logging.exception("DELETE failed: %s", parsed.path)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal server error"})


def run() -> None:
    setup_logging()
    ensure_database()
    host = os.environ.get("FPS_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("FPS_PORT", "8000")))
    server = ThreadingHTTPServer((host, port), FacultyPublicationHandler)
    logging.info("Faculty Publication System running at http://%s:%s", host, port)
    server.serve_forever()


if __name__ == "__main__":
    run()
