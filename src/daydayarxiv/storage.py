"""Filesystem helpers for reading and writing JSON data."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OutputPaths:
    base_dir: Path

    def daily_path(self, date: str, category: str) -> Path:
        return self.base_dir / date / f"{category}.json"

    def raw_path(self, date: str, category: str) -> Path:
        return self.base_dir / date / f"{category}_raw.json"

    def ensure_dir(self, date: str) -> Path:
        output_dir = self.base_dir / date
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
