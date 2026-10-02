# CL

Standalone Craigslist search and listing application extracted from jmcausey/localservices.

Features:
- Craigslist listing and Pets feeds
- Configurable scheduled search jobs
- Manual job execution
- Independent SQLite database
- Google OIDC authentication for job administration

Local setup:
1. Create a Python virtual environment.
2. Install requirements.txt.
3. Set FLASK_SECRET_KEY, GOOGLE_CLIENT_ID, and GOOGLE_CLIENT_SECRET.
4. Run: flask --app app init-db
5. Run: flask --app app run --port 5001

The default database is instance/cl.sqlite. Set CL_DATABASE to override it.

Google callback: http://127.0.0.1:5001/auth/callback

Scheduler:
- python scheduler.py
- python scheduler.py --force
