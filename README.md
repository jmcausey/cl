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

### Schema and upgrades

`schema_postgres.sql` defines the PostgreSQL schema, including the normalized `regions`, `subregions`, `sections`, `categories`, `postings`, attributes, and media tables. `schema.sql` provides the SQLite equivalent, including JSON validation, FTS5 search indexing, and timestamp triggers. Search jobs, users, and authored blog posts remain as application tables.

The web and scheduler services run `flask --app app init-db` at startup. Initialization is idempotent, seeds the category taxonomy, and migrates existing rows from `craigslist_postings` into `postings` and `media`. The legacy listings table is removed after the copy succeeds; jobs, users, and blog posts are retained.

### Clear application data

To remove postings, media, search jobs, users, and blog posts while keeping the schema and category taxonomy, stop the scheduler and run the guarded utility:

```bash
docker compose stop scheduler
docker compose run --rm --no-deps web python tools/clear_database.py --confirm
docker compose start scheduler
```

The utility requires `--confirm`; it permanently deletes application data. To remove the PostgreSQL database volume and all schema/data instead, use `docker compose down -v`.

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
The same `flask --app app init-db` command initializes the selected backend and applies the legacy-listings migration.

## Scheduler

```bash
python scheduler.py
python scheduler.py --force
```

When using Compose, the scheduler service runs automatically.
