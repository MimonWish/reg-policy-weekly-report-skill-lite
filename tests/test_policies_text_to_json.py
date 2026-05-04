from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "policies_text_to_json.py"
spec = importlib.util.spec_from_file_location("policies_text_to_json", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_build_weekly_input_from_full_width_delimited_rows() -> None:
    text = "\n".join(
        [
            "2026-04-27｜民政部、财政部、税务总局｜《关于慈善组织开展慈善活动年度支出、管理费用和募捐成本的规定》",
            "2026-04-30｜全国人大常委会｜《中华人民共和国社会救助法》",
        ]
    )

    payload = module.build_weekly_input(text)

    assert payload["report_date"] == "2026.05.03"
    assert payload["report_type"] == "监管政策周报"
    assert len(payload["policies"]) == 2
    assert payload["policies"][0]["issuer"] == "民政部、财政部、税务总局"
    assert payload["policies"][0]["url"] == ""
    assert payload["policies"][0]["include"] is True


def test_build_weekly_input_accepts_report_date_override() -> None:
    payload = module.build_weekly_input(
        "2026-04-30|全国人大常委会|《中华人民共和国监狱法》修订版",
        report_date="2026.05.04",
    )

    assert payload["report_date"] == "2026.05.04"
