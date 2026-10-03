# CL

Standalone Craigslist search and listing application.

## Docker Compose + shared PostgreSQL

The repository includes a Compose stack with:

- **web** — Flask/Gunicorn app on port `5001`
- **scheduler** — continuous Craigslist job scheduler
- **postgres** — persistent PostgreSQL 17 database
- **cl_shared_data** — a named Docker network that other containerized apps can join

Start it:

```bash
cp .env.example .env
# Edit .env and set a strong POSTGRES_PASSWORD and FLASK_SECRET_KEY.
docker compose up -d --build
```

The web app is available at `http://localhost:5001`.

### PostgreSQL access from other containers

Containers attached to the same Docker network can use:

```text
postgresql://cl:<your-password>@postgres:5432/cl
```

For another Compose project, join the existing network:

```yaml
services:
  your-app:
    environment:
      DATABASE_URL: postgresql://cl:<your-password>@postgres:5432/cl
    networks:
      - cl_shared_data

networks:
  cl_shared_data:
    external: true
    name: cl_shared_data
```

The PostgreSQL service also publishes port `5432` on the Docker host by default. Set `POSTGRES_PORT` if that host port is already occupied. For containers on `cl_shared_data`, use the hostname `postgres` rather than the host-mapped port.

### Persistent data

PostgreSQL data is stored in the named Docker volume `cl_postgres_data`. Recreating containers does not remove the database. To intentionally destroy the database:

```bash
docker compose down -v
```

### Environment variables

See `.env.example`. Important values include `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `FLASK_SECRET_KEY`, `APP_PORT`, `POSTGRES_PORT`, and optional Google OAuth variables.

### Local development

Without Docker, the app can continue to use SQLite:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app init-db
flask --app app run --port 5001
```

Set `DATABASE_URL` to use PostgreSQL locally instead of SQLite.

## Scheduler

```bash
python scheduler.py
python scheduler.py --force
```

When using Compose, the scheduler service runs automatically.
