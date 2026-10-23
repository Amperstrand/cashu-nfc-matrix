"""render_matrix unit tests (plain pytest, no hardware)."""


def test_render_from_synthetic_jsonl(tmp_path, monkeypatch):
    import json
    import sys
    sys.path.insert(0, ".")
    from bench import render_matrix as rm

    d = tmp_path / "payment-soak-test.jsonl"
    rows = [
        {"cycle": 0, "ok": True, "reader": "M5stick GemPC", "wallet": "cashu_me"},
        {"cycle": 1, "ok": True, "reader": "M5stick GemPC", "wallet": "cashu_me"},
        {"cycle": 2, "ok": False, "reader": "M5stick GemPC", "wallet": "cashu_me"},
    ]
    d.write_text("\n".join(json.dumps(r) for r in rows))
    monkeypatch.setattr(rm, "RESULTS", tmp_path)
    cells = rm.collect()
    cell = cells[("cashu_me", "m5stick/MFRC522")]
    assert cell["ok"] == 2 and cell["fail"] == 1
    md = rm.render(cells)
    assert "2 ok / 1 fail" in md
    assert "GENERATED" in md


def test_geometry_gating_declarations():
    import sys
    sys.path.insert(0, ".")
    from bench import geometry

    assert geometry.phone_at() == "unknown"  # nothing declared in-repo
    live, _ = geometry.cell_live("Nucula CCID")
    assert live  # unknown => legacy behavior: all cells run
    geometry_skip = __import__("os").environ.get("PHONE_AT")
    assert geometry_skip in (None, "")  # env not set in test env
