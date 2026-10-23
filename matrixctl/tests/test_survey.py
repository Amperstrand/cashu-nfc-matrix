"""matrixctl survey tests: fixture-driven, no hardware."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, str(Path(__file__).parents[2]))

import yaml

from matrixctl.__main__ import _delta, survey, STATE_PATH  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def test_survey_fake_reads_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr("matrixctl.__main__.STATE_PATH", tmp_path / "s.yaml")
    monkeypatch.setattr("matrixctl.__main__.STATE_HISTORY", tmp_path / "h")
    st = survey(str(FIX / "bench-a.json"), "RF8NB01ZYAH")
    assert st["phone"]["adb_state"] == "device"
    assert st["boards"]["nucula_c3"]["fwid"] == "esp32-ccid"
    assert st["survey_mode"].startswith("fake:")
    yaml.safe_dump(st)  # state must round-trip yaml


def test_delta_finds_fw_and_reader_changes():
    a = json.loads((FIX / "bench-a.json").read_text())
    b = json.loads((FIX / "bench-b.json").read_text())
    d = "\n".join(_delta(a["boards"], b["boards"], "boards."))
    assert "'esp32-ccid' -> 'bolty'" in d
    ra, rb = {"n": len(a["pcscd"]["readers"])}, {"n": len(b["pcscd"]["readers"])}
    assert _delta(ra, rb)[0].startswith("~ n:")
