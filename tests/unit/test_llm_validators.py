import pytest

from daydayarxiv.llm.validators import LLMValidationError, is_valid_text, require_valid_text


def test_is_valid_text():
    assert is_valid_text("hello", ["fail"]) is True
    assert is_valid_text("", ["fail"]) is False
    assert is_valid_text("翻译失败", ["翻译失败"]) is False


def test_require_valid_text():
    assert require_valid_text(" ok ", ["bad"], "field") == "ok"
    with pytest.raises(LLMValidationError):
        require_valid_text("生成失败", ["生成失败"], "field")
