# Faculty Publication System

Full-stack faculty publication tracker with:
- Python backend (`backend/server.py`) + SQLite
- HTML/CSS/JS frontend (`frontend/`)

## Project Structure

```text
Final project/
  backend/
    data/
      .gitkeep
    server.py
  frontend/
    css/
      style.css
    js/
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
  README.md
```

## Run in VS Code

1. Open folder in VS Code: `c:\Users\Sundhar\Desktop\Final project`
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

- Python launcher `py` is used (`py -3 ...`).
- Database file is created automatically at `backend/data/fps.db`.

