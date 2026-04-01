# Faculty Publication System Report

## Objective
The system helps faculty members manage publication records through a secure web application with institutional login, publication analytics, filtering, and attachment support.

## Technology Stack
- Frontend: HTML, CSS, JavaScript modules
- Backend: Python standard-library HTTP server
- Database: SQLite
- Authentication: JWT
- Testing: Python `unittest`
- Deployment Target: Render

## Key Features
- Secure faculty registration and login with institutional email restriction
- Full CRUD for publication records
- Search, filtering, export, and pagination
- Responsive UI with loaders, toasts, and animated transitions
- Publication metrics for scope and indexing categories

## Performance Notes
- Indexed SQLite queries for publication filters
- Page-wise code splitting using dynamic `import()`
- Paginated API responses to avoid loading large datasets at once

## Testing
- Basic backend validation tests are included in `tests/test_server.py`
- CI runs automatically with GitHub Actions on push and pull request

## Deployment Notes
- `render.yaml` is included for Render deployment
- SQLite data is mounted to a persistent disk path in Render
- `PORT` and `FPS_HOST` are supported for hosted environments

## Viva Talking Points
- Why JWT was chosen over session storage on the server
- How SQLite indexing improves filtered publication retrieval
- How dynamic import gives lightweight code splitting for page-specific logic
- How Render deployment and GitHub Actions provide a simple CI/CD workflow
