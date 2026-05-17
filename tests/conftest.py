"""Shared pytest fixtures + path bootstrap."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Make src/ importable without install.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def isolate_telemetry_home(tmp_path, monkeypatch):
    """Send all telemetry state into a per-test tmp dir."""
    home = tmp_path / "milo-cost-auditor-home"
    monkeypatch.setenv("MILO_COST_AUDITOR_HOME", str(home))
    # Wipe in-process flags
    from milo_cost_auditor import telemetry
    telemetry.reset_for_tests()
    yield


@pytest.fixture
def openai_invoice_csv() -> str:
    return (HERE / "fixtures" / "sample_openai_invoice.csv").read_text(encoding="utf-8")


@pytest.fixture
def anthropic_invoice_csv() -> str:
    return (HERE / "fixtures" / "sample_anthropic_invoice.csv").read_text(encoding="utf-8")


@pytest.fixture
def json_invoice() -> str:
    """Tiny JSON-format invoice."""
    return (
        '[{"model":"claude-4-opus","input_tokens":300,"output_tokens":1200,"cost":0.094500},'
        '{"model":"claude-4-opus","input_tokens":250,"output_tokens":1000,"cost":0.078750}]'
    )
