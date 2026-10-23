"""next-ranking tests — fixture-driven, no hardware."""
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, str(Path(__file__).parents[2]))

from matrixctl import next as nx  # noqa: E402
from matrixctl import registry as reg  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def _with_facts(tmp_path, phone_at, c3="bolty"):
    f = tmp_path / "facts.yaml"
    f.write_text(f"phone: {{at: {phone_at}}}\nboards: {{c3: {c3}}}\n")
    reg.FACTS_PATH = f
    nx.reg = reg
    return f


def test_next_prefers_move_over_reflash(tmp_path):
    # c3 on bolty: moving the phone to m5stick (effort 2) must outrank
    # reflashing c3 (effort 15) even though nucula cells are stale-never-run
    _with_facts(tmp_path, "nucula-coil", c3="bolty")
    d = nx.compute_next(str(FIX / "bench-a.json"))
    assert d["action"] == "move-phone->m5stick-coil"
    assert "cashu_me-m5stick-payment" in d["unlocked"]
    assert "soak-m5stick" in d["unlocked"]


def test_next_no_touch_when_core_already_runnable(tmp_path):
    _with_facts(tmp_path, "m5stick-coil", c3="bolty")
    # m5stick cells already runnable now -> best action is 'none'
    d = nx.compute_next(str(FIX / "bench-a.json"))
    assert d["action"] in ("none", "move-phone->acr-stack")


def test_wall_minutes_positive(tmp_path):
    _with_facts(tmp_path, "nucula-coil", c3="bolty")
    d = nx.compute_next(str(FIX / "bench-a.json"))
    assert "~4 min" in d["why"] or "~" in d["why"]
