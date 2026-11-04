"""Import the Sprint 1 JSON files (data/sessions/*.json, data/prompt_lab.json) into the database.

    uv run python scripts/import_json_data.py

Safe to rerun: already imported sessions are updated in place, duplicate lab records skipped.
"""

from __future__ import annotations

from interview_app.config import get_settings
from interview_app.storage.import_json import import_all
from interview_app.storage.store import open_store

if __name__ == "__main__":
    settings = get_settings()
    report = import_all(open_store(settings), settings.data_dir)
    print(f"database: {settings.database_url}")
    print(f"sessions imported: {report.sessions} (unreadable: {report.sessions_skipped})")
    print(f"lab records imported: {report.lab_records} (duplicates: {report.lab_records_skipped})")
