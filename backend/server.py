import base64
import json
import mimetypes
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_DIR = ROOT_DIR / "backend" / "data"
DB_PATH = DATA_DIR / "fps.db"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                faculty_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (faculty_id) REFERENCES faculties(id) ON DELETE CASCADE
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
                FOREIGN KEY (faculty_id) REFERENCES faculties(id) ON DELETE CASCADE
            )
            """
        )

        # Lightweight migration for existing databases created before file/content fields.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(publications)").fetchall()}
        if "content" not in columns:
            conn.execute("ALTER TABLE publications ADD COLUMN content TEXT NOT NULL DEFAULT ''")
        if "conference_scope" not in columns:
            conn.execute("ALTER TABLE publications ADD COLUMN conference_scope TEXT NOT NULL DEFAULT ''")
        if "indexing_params" not in columns:
            conn.execute("ALTER TABLE publications ADD COLUMN indexing_params TEXT NOT NULL DEFAULT ''")
        if "publication_status" not in columns:
            conn.execute("ALTER TABLE publications ADD COLUMN publication_status TEXT NOT NULL DEFAULT 'Submitted'")
        if "citation_count" not in columns:
            conn.execute("ALTER TABLE publications ADD COLUMN citation_count INTEGER NOT NULL DEFAULT 0")
        if "publisher_name" not in columns:
            conn.execute("ALTER TABLE publications ADD COLUMN publisher_name TEXT NOT NULL DEFAULT ''")
        if "file_name" not in columns:
            conn.execute("ALTER TABLE publications ADD COLUMN file_name TEXT")
        if "file_type" not in columns:
            conn.execute("ALTER TABLE publications ADD COLUMN file_type TEXT")
        if "file_data" not in columns:
            conn.execute("ALTER TABLE publications ADD COLUMN file_data BLOB")

        conn.commit()


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return digest.hex(), salt.hex()


def verify_password(password: str, expected_hash: str, salt_hex: str) -> bool:
    candidate_hash, _ = hash_password(password, salt_hex)
    return secrets.compare_digest(candidate_hash, expected_hash)


def _normalize_name(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def names_match(input_name: str, saved_name: str) -> bool:
    if not input_name or not saved_name:
        return False
    return _normalize_name(input_name) == _normalize_name(saved_name)


class FacultyPublicationHandler(BaseHTTPRequestHandler):
    server_version = "FPS/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _get_token(self) -> str | None:
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header.removeprefix("Bearer ").strip()
        return None

    def _auth_faculty(self) -> sqlite3.Row | None:
        token = self._get_token()
        if not token:
            return None

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT f.id, f.name, f.email, s.expires_at
                FROM sessions s
                JOIN faculties f ON f.id = s.faculty_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()

            if not row:
                return None

            if datetime.fromisoformat(row["expires_at"]) < utc_now():
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                return None

            return row

    def _handle_static(self, path: str) -> None:
        route_path = "login.html" if path == "/" else path.lstrip("/")
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
        self._send_text(HTTPStatus.OK, content, content_type)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET,POST,DELETE,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
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
                    SELECT pub_type, publication_status, COUNT(*) AS count
                    FROM publications
                    WHERE faculty_id = ?
                    GROUP BY pub_type, publication_status
                    """,
                    (faculty["id"],),
                ).fetchall()
            stats = {"total": 0, "journals": 0, "conferences": 0, "submitted": 0, "accepted": 0, "published": 0}
            for row in rows:
                stats["total"] += row["count"]
                if row["pub_type"] == "Journal":
                    stats["journals"] += row["count"]
                if row["pub_type"] == "Article":
                    stats["journals"] += row["count"]
                if row["pub_type"] == "Conference":
                    stats["conferences"] += row["count"]
                status = row["publication_status"]
                if status == "Submitted":
                    stats["submitted"] += row["count"]
                if status == "Accepted":
                    stats["accepted"] += row["count"]
                if status == "Published":
                    stats["published"] += row["count"]
            self._send_json(HTTPStatus.OK, {"stats": stats})
            return

        if parsed.path.startswith("/api/publications/") and parsed.path.endswith("/file"):
            faculty = self._auth_faculty()
            if not faculty:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                return

            parts = parsed.path.strip("/").split("/")
            if len(parts) != 4 or parts[0] != "api" or parts[1] != "publications" or parts[3] != "file":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return

            publication_id = parts[2]
            if not publication_id.isdigit():
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid publication id."})
                return

            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT file_name, file_type, file_data
                    FROM publications
                    WHERE id = ? AND faculty_id = ?
                    """,
                    (int(publication_id), faculty["id"]),
                ).fetchone()

            if not row or row["file_data"] is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Attachment not found."})
                return

            file_name = (row["file_name"] or f"publication-{publication_id}").replace('"', "")
            file_type = row["file_type"] or "application/octet-stream"
            file_bytes = row["file_data"]

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", file_type)
            self.send_header("Content-Length", str(len(file_bytes)))
            self.send_header("Content-Disposition", f'attachment; filename="{file_name}"')
            self.end_headers()
            self.wfile.write(file_bytes)
            return

        if parsed.path == "/api/publications":
            faculty = self._auth_faculty()
            if not faculty:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                return

            query_params = parse_qs(parsed.query)
            q = query_params.get("q", [""])[0].strip().lower()
            pub_type = query_params.get("type", [""])[0].strip()
            status_filter = query_params.get("status", [""])[0].strip()
            year_filter = query_params.get("year", [""])[0].strip()

            sql = """
                SELECT id, title, authors, venue, pub_type, conference_scope, indexing_params, published_date, content, publication_status, citation_count, publisher_name, doi, file_name, created_at
                FROM publications
                WHERE faculty_id = ?
            """
            args: list = [faculty["id"]]
            if pub_type:
                sql += " AND pub_type = ?"
                args.append(pub_type)
            if status_filter:
                sql += " AND publication_status = ?"
                args.append(status_filter)
            if year_filter and year_filter.isdigit():
                sql += " AND strftime('%Y', published_date) = ?"
                args.append(year_filter)
            if q:
                sql += " AND (LOWER(title) LIKE ? OR LOWER(authors) LIKE ? OR LOWER(venue) LIKE ?)"
                like = f"%{q}%"
                args.extend([like, like, like])
            sql += " ORDER BY published_date DESC, created_at DESC"

            with self._connect() as conn:
                rows = conn.execute(sql, args).fetchall()
            publications = [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "authors": row["authors"],
                    "venue": row["venue"],
                    "type": row["pub_type"],
                    "conferenceScope": row["conference_scope"] or "",
                    "indexing": [value for value in (row["indexing_params"] or "").split(",") if value],
                    "publishedDate": row["published_date"],
                    "content": row["content"] or "",
                    "status": row["publication_status"] or "Submitted",
                    "citationCount": int(row["citation_count"] or 0),
                    "publisherName": row["publisher_name"] or "",
                    "doi": row["doi"] or "",
                    "hasAttachment": bool(row["file_name"]),
                    "fileName": row["file_name"] or "",
                    "createdAt": row["created_at"],
                }
                for row in rows
            ]
            self._send_json(HTTPStatus.OK, {"publications": publications})
            return

        self._handle_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json_body()

        if parsed.path == "/api/auth/login":
            name = (payload.get("name") or "").strip()
            email = (payload.get("email") or "").strip().lower()
            password = (payload.get("password") or "").strip()
            recover = bool(payload.get("recover"))

            if not email or not password:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Email and password are required."})
                return

            with self._connect() as conn:
                faculty = conn.execute(
                    "SELECT id, name, email, password_hash, password_salt FROM faculties WHERE email = ?",
                    (email,),
                ).fetchone()

                if faculty and not verify_password(password, faculty["password_hash"], faculty["password_salt"]):
                    name_matches = names_match(name, faculty["name"])
                    allow_recovery = name_matches and recover
                    if allow_recovery:
                        password_hash, password_salt = hash_password(password)
                        conn.execute(
                            """
                            UPDATE faculties
                            SET password_hash = ?, password_salt = ?
                            WHERE id = ?
                            """,
                            (password_hash, password_salt, faculty["id"]),
                        )
                        faculty = conn.execute(
                            "SELECT id, name, email, password_hash, password_salt FROM faculties WHERE email = ?",
                            (email,),
                        ).fetchone()
                    else:
                        self._send_json(
                            HTTPStatus.UNAUTHORIZED,
                            {
                                "error": (
                                    "Invalid credentials. Enter your author name and enable password reset "
                                    "to set a new password."
                                )
                            },
                        )
                        return

                if not faculty:
                    if not name:
                        self._send_json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "Author name is required for first-time login."},
                        )
                        return
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

                token = secrets.token_urlsafe(32)
                expires_at = (utc_now() + timedelta(days=7)).isoformat()
                conn.execute(
                    """
                    INSERT INTO sessions (token, faculty_id, expires_at, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (token, faculty["id"], expires_at, utc_now().isoformat()),
                )
                conn.commit()

            self._send_json(
                HTTPStatus.OK,
                {
                    "token": token,
                    "faculty": {"id": faculty["id"], "name": faculty["name"], "email": faculty["email"]},
                },
            )
            return

        if parsed.path == "/api/auth/logout":
            token = self._get_token()
            if token:
                with self._connect() as conn:
                    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                    conn.commit()
            self._send_json(HTTPStatus.OK, {"ok": True})
            return

        if parsed.path.startswith("/api/publications/") and parsed.path.endswith("/status"):
            faculty = self._auth_faculty()
            if not faculty:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                return

            parts = parsed.path.strip("/").split("/")
            if len(parts) != 4 or parts[0] != "api" or parts[1] != "publications" or parts[3] != "status":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return

            pub_id = parts[2]
            if not pub_id.isdigit():
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid publication id."})
                return

            status = (payload.get("status") or "").strip()
            if status not in {"Draft", "Submitted", "Accepted", "Published"}:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid publication status."})
                return

            with self._connect() as conn:
                updated = conn.execute(
                    """
                    UPDATE publications
                    SET publication_status = ?
                    WHERE id = ? AND faculty_id = ?
                    """,
                    (status, int(pub_id), faculty["id"]),
                ).rowcount
                conn.commit()

            if not updated:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Publication not found."})
                return

            self._send_json(HTTPStatus.OK, {"ok": True})
            return

        if parsed.path == "/api/publications":
            faculty = self._auth_faculty()
            if not faculty:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
                return

            title = (payload.get("title") or "").strip()
            authors = (payload.get("authors") or "").strip()
            venue = (payload.get("venue") or "").strip()
            pub_type = (payload.get("type") or "").strip()
            conference_scope = (payload.get("conferenceScope") or "").strip()
            indexing_values = payload.get("indexing") or []
            published_date = (payload.get("publishedDate") or "").strip()
            content = (payload.get("content") or "").strip()
            status = (payload.get("status") or "").strip() or "Submitted"
            citation_count_raw = payload.get("citationCount")
            publisher_name = (payload.get("publisherName") or "").strip()
            doi = (payload.get("doi") or "").strip()
            attachment = payload.get("attachment") or {}
            file_name = (attachment.get("name") or "").strip()
            file_type = (attachment.get("type") or "").strip()
            file_data_b64 = (attachment.get("data") or "").strip()
            file_data: bytes | None = None

            try:
                citation_count = int(citation_count_raw or 0)
            except (TypeError, ValueError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Citation count must be numeric."})
                return
            if citation_count < 0:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Citation count cannot be negative."})
                return
            if status not in {"Draft", "Submitted", "Accepted", "Published"}:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid publication status."})
                return

            if file_data_b64:
                try:
                    file_data = base64.b64decode(file_data_b64, validate=True)
                except Exception:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid file encoding."})
                    return
                if len(file_data) > MAX_UPLOAD_BYTES:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "File size exceeds 10 MB limit."})
                    return
                if not file_name:
                    file_name = "attachment"
                if not file_type:
                    file_type = "application/octet-stream"

            if not isinstance(indexing_values, list):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid indexing payload."})
                return

            allowed_indexing = {"Scopus", "SCI"}
            normalized_indexing: list[str] = []
            for value in indexing_values:
                current = str(value).strip()
                if not current:
                    continue
                if current not in allowed_indexing:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Unsupported indexing parameter."})
                    return
                if current not in normalized_indexing:
                    normalized_indexing.append(current)

            if pub_type == "Conference":
                if conference_scope not in {"National", "International"}:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "Conference scope must be National or International."},
                    )
                    return
            else:
                conference_scope = "N/A"

            if (
                not title
                or not authors
                or not venue
                or pub_type not in {"Journal", "Conference", "Article"}
                or not published_date
                or not content
            ):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid publication payload."})
                return

            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO publications (
                        faculty_id, title, authors, venue, pub_type, conference_scope, indexing_params, published_date, content, publication_status, citation_count, publisher_name, doi, file_name, file_type, file_data, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        faculty["id"],
                        title,
                        authors,
                        venue,
                        pub_type,
                        conference_scope,
                        ",".join(normalized_indexing),
                        published_date,
                        content,
                        status,
                        citation_count,
                        publisher_name,
                        doi,
                        file_name or None,
                        file_type or None,
                        file_data,
                        utc_now().isoformat(),
                    ),
                )
                conn.commit()
            self._send_json(HTTPStatus.CREATED, {"ok": True})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/publications/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        faculty = self._auth_faculty()
        if not faculty:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
            return

        pub_id_str = parsed.path.rsplit("/", 1)[-1]
        if not pub_id_str.isdigit():
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid publication id."})
            return

        pub_id = int(pub_id_str)
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


def run() -> None:
    ensure_database()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), FacultyPublicationHandler)
    print("Faculty Publication System running at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    run()
