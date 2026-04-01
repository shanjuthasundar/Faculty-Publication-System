# Faculty Publication System

Full-stack faculty publication tracker with:
- Python backend (`backend/server.py`) + SQLite
- HTML/CSS/JS frontend (`frontend/`)
- JWT authentication + secure API headers + input validation
- Redux-style centralized frontend state store (`frontend/js/store.js`)
- Search, filtering, pagination, loaders, toast notifications, and CSV export
- Dynamic JavaScript module loading for page-level code splitting
- Render deployment config and GitHub Actions CI

## Project Structure

```text
Final project/
  backend/
    data/
      .gitkeep
    __init__.py
    postman/
      Faculty-Publication-System.postman_collection.json
    server.py
  docs/
    openapi.json
  frontend/
    css/
      style.css
    js/
      core/
        api.js
        ui.js
      pages/
        dashboard-page.js
        login-page.js
        publication-form-page.js
      store.js
      app.js
    login.html
    dashboard.html
    new-report.html
  scripts/
    start.ps1
    stop.ps1
  .vscode/
    launch.json
    tasks.json
    extensions.json
  ER_DIAGRAM.md
  .github/
    workflows/
      ci.yml
  render.yaml
  PROJECT_REPORT.md
  README.md
```

## Run in VS Code

1. Open folder in VS Code: `c:\Users\RITIK ROSHAN\Documents\Final project`
2. Open `Terminal` in VS Code (PowerShell).
3. Start app:
   - `.\scripts\start.ps1`
4. Open in browser:
   - `http://127.0.0.1:8000/login.html`

## VS Code Tasks

- `Run FPS (Server + Chrome)`: starts backend and opens Chrome.
- `Start FPS Backend`: starts only backend.
- `Open FPS in Chrome`: opens login page.
- `Stop FPS Backend`: stops backend process.

Run from:
- `Terminal` -> `Run Task...`

## Debug Backend in VS Code

- Go to `Run and Debug`.
- Select `Python: FPS Backend`.
- Press `F5`.

## Notes

- Database file is created automatically at `backend/data/fps.db`.
- Basic server logs are written to `backend/logs/server.log`.
- Hosted deployment reads `PORT` and binds to `0.0.0.0`.

## API Routes

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/request-otp`
- `POST /api/auth/reset-password`
- `POST /api/auth/google`
- `GET /api/auth/config`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `GET /api/publications`
- `GET /api/publications/{id}`
- `POST /api/publications`
- `PUT /api/publications/{id}`
- `DELETE /api/publications/{id}`
- `GET /api/publications/{id}/file`
- `GET /api/publications/stats`

## Postman / Thunder Client Testing

1. Import `backend/postman/Faculty-Publication-System.postman_collection.json`
2. Run requests in this order:
   - `Health` -> `Register` -> `Login` -> `Create Publication` -> `List Publications` -> `Get Publication By ID` -> `Update Publication` -> `Delete Publication`
3. `token` and `publicationId` are auto-saved as collection variables from test scripts.

## Tests

- Run locally:
  - `python -m unittest discover -s tests -v`
- CI runs automatically through `.github/workflows/ci.yml`

## Deployment

- Recommended live host: Render
- Included file: `render.yaml`
- Render setup:
  1. Connect the GitHub repository to Render
  2. Create a new Blueprint deployment
  3. Set `FPS_JWT_SECRET` in Render environment variables
  4. Deploy and use the generated Render URL on any device
- SQLite persistence is handled with the attached Render disk mount in `render.yaml`

## API Documentation

- Postman collection: `backend/postman/Faculty-Publication-System.postman_collection.json`
- OpenAPI document: `docs/openapi.json`

## Viva Support

- Project report: `PROJECT_REPORT.md`
- Architecture support: `ER_DIAGRAM.md`

## Auth Configuration

- Allowed email domain is locked to: `@bitsathy.ac.in`
- For OTP email delivery, set:
  - `FPS_SMTP_HOST`
  - `FPS_SMTP_PORT` (default: `587`)
  - `FPS_SMTP_USER`
  - `FPS_SMTP_PASSWORD`
  - `FPS_SMTP_FROM`
- OTP is sent only via email; it is never returned in API response/UI logs.
- For Google sign-in, set:
  - `FPS_GOOGLE_CLIENT_ID`
