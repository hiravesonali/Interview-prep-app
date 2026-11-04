"""One-off import of the Sprint 1 JSON files into the database (see scripts/import_json_data.py).

Idempotent: a session's id is derived from its file name and lab records are skipped when an
identical one is already stored, so the script can be rerun safely.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from interview_app.features.practice import PracticeSession
from interview_app.storage.prompt_lab import LabRecord
from interview_app.storage.store import Store


@dataclass
class ImportReport:
    sessions: int = 0
    sessions_skipped: int = 0
    lab_records: int = 0
    lab_records_skipped: int = 0


def import_all(store: Store, data_dir: Path) -> ImportReport:
    report = ImportReport()
    for path in sorted((data_dir / "sessions").glob("*.json")):
        try:
            session = PracticeSession.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            report.sessions_skipped += 1
            continue
        session.id = uuid5(NAMESPACE_URL, path.name).hex
        store.save_session(session)
        report.sessions += 1

    lab_file = data_dir / "prompt_lab.json"
    if lab_file.exists():
        existing = {_key(r) for r in store.load_lab_records()}
        new: list[LabRecord] = []
        for raw in json.loads(lab_file.read_text(encoding="utf-8")):
            record = LabRecord(**raw)
            if _key(record) in existing:
                report.lab_records_skipped += 1
            else:
                new.append(record)
                existing.add(_key(record))
        store.append_lab_records(new)
        report.lab_records = len(new)
    return report


def _key(r: LabRecord) -> tuple[str, str, str, str]:
    return (r.time, r.technique, r.model, r.note)
