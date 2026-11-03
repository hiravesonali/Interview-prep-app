"""Prompt Lab results store (data/prompt_lab.json): one record per technique run."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class LabRecord:
    time: str
    technique: str
    model: str
    question: str
    answer_preview: str
    overall: int
    cost_usd: float
    latency_s: float
    tokens: int
    rating: int | None = None  # 1-5, the human's usefulness rating
    note: str = ""
    judge_overall: int | None = None  # 1-5, LLM-as-a-judge rating of the feedback
    judge_model: str = ""


@dataclass(frozen=True)
class LeaderboardRow:
    technique: str
    runs: int
    rated: int
    avg_rating: float | None
    avg_judge: float | None
    avg_overall: float
    avg_cost_usd: float
    avg_latency_s: float
    avg_tokens: float


def _path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "prompt_lab.json"


def load_records(data_dir: Path) -> list[LabRecord]:
    p = _path(data_dir)
    if not p.exists():
        return []
    try:
        return [LabRecord(**r) for r in json.loads(p.read_text(encoding="utf-8"))]
    except (ValueError, TypeError):
        return []


def append_records(records: list[LabRecord], data_dir: Path) -> None:
    existing = load_records(data_dir)
    _path(data_dir).write_text(
        json.dumps([asdict(r) for r in [*existing, *records]], indent=2), encoding="utf-8"
    )


def leaderboard(records: list[LabRecord]) -> list[LeaderboardRow]:
    groups: dict[str, list[LabRecord]] = defaultdict(list)
    for r in records:
        groups[r.technique].append(r)
    rows = []
    for technique, rs in groups.items():
        rated = [r.rating for r in rs if r.rating]
        judged = [r.judge_overall for r in rs if r.judge_overall]
        rows.append(
            LeaderboardRow(
                technique=technique,
                runs=len(rs),
                rated=len(rated),
                avg_rating=round(sum(rated) / len(rated), 2) if rated else None,
                avg_judge=round(sum(judged) / len(judged), 2) if judged else None,
                avg_overall=round(sum(r.overall for r in rs) / len(rs), 2),
                avg_cost_usd=round(sum(r.cost_usd for r in rs) / len(rs), 4),
                avg_latency_s=round(sum(r.latency_s for r in rs) / len(rs), 1),
                avg_tokens=round(sum(r.tokens for r in rs) / len(rs)),
            )
        )
    # Human rating first, then the judge's score, then name; unrated techniques go last.
    return sorted(
        rows,
        key=lambda r: (
            r.avg_rating is None,
            -(r.avg_rating or 0),
            -(r.avg_judge or 0),
            r.technique,
        ),
    )


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
