from pathlib import Path

import os

import pytest

os.environ["JB_NO_DOTENV"] = "1"   # never read the developer's real backend/.env in tests

MONOLITHS = Path(__file__).resolve().parents[2] / "test_monoliths"


@pytest.fixture
def read_java():
    return lambda name: (MONOLITHS / f"{name}.java").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    """Every test starts with no LLM configuration; tests opt in via monkeypatch.setenv."""
    for k in list(os.environ):
        if k.startswith(("GEMINI_", "LLM_", "OLLAMA_")):
            monkeypatch.delenv(k, raising=False)
