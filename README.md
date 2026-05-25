# Training Companion

A mobile-first strength training and powerlifting progression management app.

**Stack:** React Native (Expo) + FastAPI + PostgreSQL (Supabase)  
**Distribution:** iOS App Store | **Backend hosting:** Railway

---

## Repository Structure

```
training-companion/
├── backend/        # FastAPI application
├── frontend/       # Expo React Native application
├── docs/           # Specs, ADRs, notes
└── docker-compose.yml
```

---

## Backend

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose

### Local Development (Docker)

The `docker-compose.yml` spins up two services:

| Service | Description |
|---|---|j
| `backend` | FastAPI app with hot reload |
| `db` | Local Postgres instance (dev only — production uses Supabase) |

**1. Copy the environment file**

```bash
cp backend/.env.example backend/.env
```

The defaults in `.env` point `DATABASE_URL` at the local `db` container — no changes needed to get running locally.

**2. Start the stack**

```bash
docker compose up --build
```

**3. Verify the health check**

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"training-companion-api"}
```

**4. Interactive API docs**

`DEBUG=true` is set in the default `.env`, so Swagger UI is available at:

```
http://localhost:8000/docs
```

**5. Tear down**

```bash
docker compose down        # stop containers, keep DB data
docker compose down -v     # stop containers and wipe DB volume
```

---

### Environment Variables

| Variable | Description |
|---|---|
| `ENVIRONMENT` | `development` or `production` |
| `DEBUG` | Enables `/docs` when `true` |
| `DATABASE_URL` | Postgres connection string |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_JWT_SECRET` | JWT secret from Supabase dashboard (used to validate auth tokens) |
| `SENTRY_DSN` | Sentry DSN for error tracking (optional) |

> **Production note:** `DATABASE_URL` in Railway/production points to your Supabase Postgres connection string, not the local container.

---

### Running Tests

The `dev` Docker stage includes all test dependencies. The `production` stage does not.

```bash
# Unit tests (no DB required) — fast, run these constantly
docker compose exec backend pytest -m "not integration"

# All tests including integration (requires the db container to be up)
docker compose exec backend pytest
```

In CI, the pipeline builds the `dev` target, runs the full test suite, then builds the `production` target for deploy. This keeps test tooling out of the production image.

---

## Frontend

> Setup instructions to be added when Expo scaffolding is complete.

---

## Deployment

### Backend (Railway)

Railway deploys from git. On push to `main`:

1. Railway builds from `backend/Dockerfile`
2. Set all environment variables in the Railway dashboard (use Supabase connection string for `DATABASE_URL`)
3. No manual steps required — Railway handles the rest

---

## Architecture Notes

- Business logic lives entirely in FastAPI backend services — never in the frontend
- Supabase is used as managed Postgres + auth provider only
- Auth flow: Mobile → Supabase Auth → JWT → FastAPI validates token
- See `CLAUDE.md` for full architecture decisions and constraints
