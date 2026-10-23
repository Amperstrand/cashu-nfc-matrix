"""registry/plan/set/verify tests — fixture-driven, no hardware."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, str(Path(__file__).parents[2]))

import pytest

from matrixctl import registry as reg  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def facts(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "FACTS_PATH", tmp_path / "facts.yaml")
    return tmp_path / "facts.yaml"


def test_plan_blocks_on_c3_duty(facts):
    facts.write_text("phone: {at: nucula-coil}\nboards: {c3: bolty}\n")
    p = reg.plan(str(FIX / "bench-a.json"), "core")
    assert p["runnable"] == []
    assert all("c3 duty" in b["blocked"] for b in p["blocked"])


def test_plan_runs_when_duty_and_geometry_align(facts):
    facts.write_text("phone: {at: m5stick-coil}\nboards: {c3: bolty}\n")
    p = reg.plan(str(FIX / "bench-a.json"), "core")
    names = [r["cell"] for r in p["runnable"]]
    assert "cashu_me-m5stick-read" in names
    assert "cashu_me-m5stick-payment" in names
    assert p["wall_min_total"] == 4


def test_set_validates_values(facts, capsys):
    class A:
        fact, value = "phone.at", "mars"
    assert reg.cmd_set(A()) == 2
    class B:
        fact, value = "phone.at", "acr-stack"
    assert reg.cmd_set(B()) == 0
    import yaml
    assert yaml.safe_load(facts.read_text())["phone"]["at"] == "acr-stack"


def test_verify_state_catches_drift(facts):
    facts.write_text("phone: {at: m5stick-coil}\nboards: {c3: bolty}\n")
    class A:
        assume, fake = None, str(FIX / "bench-a.json")
    import json as j
    tmp = facts.parent / "assume.json"
    tmp.write_text(j.dumps({"phone.at": "m5stick-coil"}))
    A.assume = str(tmp)
    assert reg.cmd_verify(A()) == 0
    tmp.write_text(j.dumps({"phone.at": "acr-stack"}))
    assert reg.cmd_verify(A()) == 1
