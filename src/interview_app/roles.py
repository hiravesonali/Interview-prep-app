"""Role presets loaded from data/roles.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_ROLES_FILE = Path(__file__).parent / "data" / "roles.yaml"


@dataclass(frozen=True)
class Role:
    name: str
    icon: str
    topics: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.icon} {self.name}"


@lru_cache(maxsize=1)
def load_roles() -> tuple[Role, ...]:
    raw = yaml.safe_load(_ROLES_FILE.read_text(encoding="utf-8"))
    return tuple(
        Role(name=r["name"], icon=r.get("icon", ""), topics=tuple(r.get("topics", [])))
        for r in raw["roles"]
    )


def find_role(name: str) -> Role | None:
    return next((r for r in load_roles() if r.name == name), None)
