"""Connectivity check for DATABASE_URL: connect, create missing tables, print row counts.

    uv run python scripts/check_db.py                                  # the .env / default SQLite
    DATABASE_URL="postgresql+psycopg://..." uv run python scripts/check_db.py   # a hosted Postgres

Run this with the Neon URL before pasting it into Community Cloud secrets.
"""

from __future__ import annotations

import sys
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from interview_app.config import get_settings
from interview_app.storage.db import Base, make_engine


def _redacted(url: str) -> str:
    if url.startswith("sqlite"):
        return url
    parts = urlsplit(url)
    host = parts.hostname or ""
    return f"{parts.scheme}://{parts.username or ''}:***@{host}{parts.path}"


def main() -> int:
    url = get_settings().database_url
    print(f"database: {_redacted(url)}")
    try:
        engine = make_engine(url)  # creates missing tables
        with engine.connect() as conn:
            for table in Base.metadata.sorted_tables:
                count = conn.execute(select(func.count()).select_from(table)).scalar()
                print(f"  {table.name:18} {count:>6} rows")
    except SQLAlchemyError as err:
        print(f"FAILED: {err.__class__.__name__}: {str(err).splitlines()[0]}")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
