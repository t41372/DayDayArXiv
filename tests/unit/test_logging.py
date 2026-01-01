from daydayarxiv.logging import configure_logging


def test_configure_logging(tmp_path):
    configure_logging("INFO", tmp_path)
