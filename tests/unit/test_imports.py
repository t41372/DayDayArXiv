import runpy
import sys

import pytest

import daydayarxiv
import daydayarxiv.__main__ as main_mod
from daydayarxiv.llm import LLMClient
from daydayarxiv.prompts import daily_summary_prompt, tldr_prompt, translate_title_prompt


def test_imports():
    assert isinstance(daydayarxiv.__version__, str)
    assert hasattr(main_mod, "main") is True
    assert hasattr(tldr_prompt, "TLDR_SYSTEM_PROMPT")
    assert hasattr(translate_title_prompt, "TRANSLATE_TITLE_SYSTEM_PROMPT")
    assert hasattr(daily_summary_prompt, "DAILY_SUMMARY_USER_INSTRUCTION")
    assert LLMClient is not None


def test_module_entrypoint(monkeypatch):
    import daydayarxiv.cli as cli

    monkeypatch.setattr(cli, "main", lambda: 0)
    sys.modules.pop("daydayarxiv.__main__", None)
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("daydayarxiv.__main__", run_name="__main__")
    assert exc.value.code == 0
