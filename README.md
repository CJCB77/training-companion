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
| `SUPABASE_JWKS_URL` | Derived automatically from `SUPABASE_URL` — no need to set manually |
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

## Authentication

Supabase owns the entire auth lifecycle. The backend never handles passwords, tokens, or email confirmation — it only validates JWTs issued by Supabase.

### Registration + first use

```
User taps "Sign Up"
  → supabase.auth.signUp({ email, password })        # Expo app → Supabase
  → Supabase creates auth.users record (private)
  → Supabase sends confirmation email
  → User confirms → account active

User taps "Login"
  → supabase.auth.signInWithPassword({ email, password })
  → Supabase returns access_token (JWT) + refresh_token
  → Expo app calls GET /profile with Authorization: Bearer <access_token>
  → FastAPI validates JWT, extracts sub + email
  → No profile row found → INSERT new profiles row
  → Returns profile JSON
```

### Every subsequent request

```
Expo app calls any protected endpoint
  → Supabase SDK attaches access_token automatically
  → FastAPI validates JWT → extracts sub
  → Profile row found → return existing profile (SELECT only)
```

### Token expiry

```
access_token expires (default 1 hour)
  → Supabase SDK uses refresh_token to silently get a new access_token
  → User is never interrupted
```

### JWT validation (backend)

- Supabase signs JWTs with an asymmetric key (ES256)
- Backend fetches the public key from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`
- Public key is cached for 15 minutes (Supabase caches it for 10 min on their edge)
- Invalid or expired tokens return `401 Unauthorized`

### Testing the flow locally

```bash
# 1. Get a JWT for a test user (create one via Supabase dashboard first)
curl -X POST 'https://YOUR_PROJECT.supabase.co/auth/v1/token?grant_type=password' \
  -H 'apikey: YOUR_PUBLISHABLE_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"email": "test@example.com", "password": "yourpassword"}'

# 2. Call a protected endpoint with the returned access_token
curl http://localhost:8000/profile \
  -H 'Authorization: Bearer ACCESS_TOKEN_FROM_STEP_1'
```

The first call creates the profile row automatically. The second call returns the existing one.

---

## Architecture Notes

- Business logic lives entirely in FastAPI backend services — never in the frontend
- Supabase is used as managed Postgres + auth provider only
- See `CLAUDE.md` for full architecture decisions and constraints