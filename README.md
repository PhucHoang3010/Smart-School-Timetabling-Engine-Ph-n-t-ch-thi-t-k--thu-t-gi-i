# Smart School Timetabling & Resource Allocation

FastAPI + OR-Tools CP-SAT application for school timetable generation, resource allocation, historical preference recommendation, conflict detection, and minimal-disturbance rescheduling.

## Structure

- `app/core`: environment configuration and SQLAlchemy connection.
- `app/models`: database ORM models.
- `app/schemas`: Pydantic request and response DTOs.
- `app/validators`: domain input validation.
- `app/ai_engine`: historical, data-driven preference recommendation.
- `app/solver`: CP-SAT engine, constraint weights, and evaluator.
- `app/services`: orchestration and persistence workflows.
- `app/api/v1`: FastAPI routes.
- `tests`: regression tests.

ORM models are split across `app/models/`; new code should import from `app` modules directly.

## Run locally

```powershell
$env:APP_ENV = "development"
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for Swagger UI.

Open `http://127.0.0.1:8000/` for the Tailwind Admin dashboard. The dashboard
uses browser `fetch()` calls to generate a timetable and display quality metrics.

## Demo authentication

The login page includes seeded development accounts:

- Admin: `admin` / `admin123`
- Teacher: `teacher1` / `teacher123`

Admin routes require an Admin token. Teachers can submit their own preference,
view their recommendations, and view only the timetable sections they teach.
These credentials are for local demonstration only; production deployments
should set a new `AUTH_SECRET` and manage users through a secure admin flow.

## Database

Development uses SQLite when `APP_ENV=development` and no `DATABASE_URL` is set. Production uses PostgreSQL by default. Set an explicit connection string when needed:

```powershell
$env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/timetabling_db"
$env:APP_ENV = "production"
```

## Tests

```powershell
\.\.venv\Scripts\python.exe -m pytest -q
```

The suite covers CP-SAT constraints, AI preference rewards, resource validation,
HTTP generation, authentication/RBAC, persistence, dashboard metrics, feedback,
versioning, rollback, logout revocation, system status, CRUD, and rescheduling.
The acceptance suite currently reports 26 passing tests.

## Docker

```powershell
docker build -t smart-school-timetabling .
docker run --rm -p 8000:8000 `
	-e DATABASE_URL="postgresql://postgres:postgres@host.docker.internal:5432/timetabling_db" `
	smart-school-timetabling
```
