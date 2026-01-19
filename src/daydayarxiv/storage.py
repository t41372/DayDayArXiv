"""Filesystem helpers for reading and writing JSON data."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from daydayarxiv.models import DataIndex


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

    def index_path(self) -> Path:
        return self.base_dir / "index.json"


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


def build_data_index(base_dir: Path) -> DataIndex:
    index = DataIndex()
    if not base_dir.exists():
        return index

    for date_dir in sorted(base_dir.iterdir()):
        if not date_dir.is_dir():
            continue
        date_str = date_dir.name
        if len(date_str) != 10:
            continue
        if not date_str[0:4].isdigit() or date_str[4] != "-" or not date_str[5:7].isdigit():
            continue
        if date_str[7] != "-" or not date_str[8:10].isdigit():
            continue

        categories: list[str] = []
        for file in sorted(date_dir.glob("*.json")):
            if file.name.endswith("_raw.json"):
                continue
            category = file.stem
            categories.append(category)

        if not categories:
            continue

        index.available_dates.append(date_str)
        index.by_date[date_str] = sorted(set(categories))
        for category in categories:
            if category not in index.categories:
                index.categories.append(category)

    index.available_dates.sort()
    index.categories.sort()
    index.last_updated = datetime.now(UTC)
    return index


def load_data_index(path: Path) -> DataIndex | None:
    if not path.exists():
        return None
    try:
        data = read_json(path)
        return DataIndex.model_validate(data)
    except Exception:
        return None


def update_data_index(paths: OutputPaths, date: str, category: str) -> DataIndex:
    index_path = paths.index_path()
    index = load_data_index(index_path)
    if index is None:
        index = build_data_index(paths.base_dir)

    if date not in index.available_dates:
        index.available_dates.append(date)
        index.available_dates.sort()

    categories = index.by_date.get(date, [])
    if category not in categories:
        categories.append(category)
        categories.sort()
    index.by_date[date] = categories

    if category not in index.categories:
        index.categories.append(category)
        index.categories.sort()

    index.last_updated = datetime.now(UTC)
    write_json_atomic(index_path, index.model_dump(mode="json"))
    return index
