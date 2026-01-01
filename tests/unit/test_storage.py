from daydayarxiv.storage import read_json, write_json_atomic


def test_write_and_read_json_atomic(tmp_path):
    path = tmp_path / "data.json"
    payload = {"hello": "world"}
    write_json_atomic(path, payload)
    assert path.exists()
    assert read_json(path) == payload
