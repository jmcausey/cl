#!/usr/bin/env python3
"""Delete all application data while preserving the database schema."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cl import create_app, get_db, init_db

TABLES = (
    "blog_posts",
    "users",
    "post_attributes",
    "media",
    "postings",
    "craigslist_jobs",
    "subregions",
    "regions",
)


def main():
    parser = argparse.ArgumentParser(
        description="Delete all rows from the configured application database."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="confirm permanent deletion of all application data",
    )
    args = parser.parse_args()
    if not args.confirm:
        parser.error("refusing to clear the database without --confirm")

    app = create_app()
    with app.app_context():
        init_db()
        db = get_db()
        try:
            deleted = {}
            for table in TABLES:
                cursor = db.execute(f"DELETE FROM {table}")
                deleted[table] = cursor.rowcount
            db.commit()
        except Exception:
            db.rollback()
            raise

    for table, count in deleted.items():
        print(f"Deleted {count} rows from {table}.")


if __name__ == "__main__":
    main()
