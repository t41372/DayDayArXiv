import pytest

from daydayarxiv.storage import (
    OutputPaths,
    build_data_index,
    load_data_index,
    read_json,
    update_data_index,
    write_json_atomic,
)


def test_write_and_read_json_atomic(tmp_path):
    path = tmp_path / "data.json"
    payload = {"hello": "world"}
    write_json_atomic(path, payload)
    assert path.exists()
    assert read_json(path) == payload


def test_build_data_index(tmp_path):
    base_dir = tmp_path / "data"
    base_dir.mkdir(parents=True)
    (base_dir / "notes.txt").write_text("ignore", encoding="utf-8")
    date_dir = base_dir / "2025-01-01"
    date_dir.mkdir(parents=True)
    (date_dir / "cs.AI.json").write_text("{}", encoding="utf-8")
    (date_dir / "cs.AI_raw.json").write_text("{}", encoding="utf-8")
    invalid_dir = base_dir / "2025-0A-01"
    invalid_dir.mkdir()
    invalid_day_dir = base_dir / "2025-01-0A"
    invalid_day_dir.mkdir()
    invalid_date_dir = base_dir / "2025-02-30"
    invalid_date_dir.mkdir()
    empty_dir = base_dir / "2025-01-02"
    empty_dir.mkdir()
    (empty_dir / "cs.AI_raw.json").write_text("{}", encoding="utf-8")
    (base_dir / "logs").mkdir()

    index = build_data_index(base_dir)
    assert index.available_dates == ["2025-01-01"]
    assert index.categories == ["cs.AI"]
    assert index.by_date["2025-01-01"] == ["cs.AI"]


def test_build_data_index_missing_dir(tmp_path):
    index = build_data_index(tmp_path / "missing")
    assert index.available_dates == []
    index.touch()
    assert index.last_updated is not None


def test_load_data_index_invalid(tmp_path):
    path = tmp_path / "index.json"
    path.write_text("not-json", encoding="utf-8")
    assert load_data_index(path) is None


def test_update_data_index_creates_file(tmp_path):
    base_dir = tmp_path / "data"
    date_dir = base_dir / "2025-01-02"
    date_dir.mkdir(parents=True)
    (date_dir / "cs.CL.json").write_text("{}", encoding="utf-8")

    paths = OutputPaths(base_dir)
    index = update_data_index(paths, "2025-01-02", "cs.CL")
    assert paths.index_path().exists()
    assert index.by_date["2025-01-02"] == ["cs.CL"]
    loaded = load_data_index(paths.index_path())
    assert loaded is not None


def test_update_data_index_adds_date_and_category(tmp_path):
    base_dir = tmp_path / "data"
    date_dir = base_dir / "2025-01-01"
    date_dir.mkdir(parents=True)
    (date_dir / "cs.AI.json").write_text("{}", encoding="utf-8")

    paths = OutputPaths(base_dir)
    update_data_index(paths, "2025-01-01", "cs.AI")

    index = update_data_index(paths, "2025-01-02", "cs.CL")
    assert "2025-01-02" in index.available_dates
    assert index.by_date["2025-01-02"] == ["cs.CL"]
    assert "cs.CL" in index.categories


def test_update_data_index_invalid_date(tmp_path):
    base_dir = tmp_path / "data"
    base_dir.mkdir(parents=True)
    paths = OutputPaths(base_dir)
    with pytest.raises(ValueError):
        update_data_index(paths, "2025-02-30", "cs.AI")
