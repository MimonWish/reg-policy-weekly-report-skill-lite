#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path


def _split_policy_line(line: str, line_number: int) -> dict[str, object]:
    parts = re.split(r"\s*[｜|]\s*", line.strip(), maxsplit=2)
    if len(parts) != 3:
        raise ValueError(
            f"第 {line_number} 行必须使用 日期｜发文机构｜政策标题 格式：{line}"
        )

    publish_date, issuer, title = [part.strip() for part in parts]
    try:
        datetime.strptime(publish_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"第 {line_number} 行日期 {publish_date!r} 无效，应为 YYYY-MM-DD"
        ) from exc

    if not issuer or not title:
        raise ValueError(f"第 {line_number} 行发文机构或政策标题为空：{line}")

    return {
        "date": publish_date,
        "issuer": issuer,
        "title": title,
        "url": "",
        "include": True,
        "notes": "",
        "group_internal_status": "无",
        "group_internal_status_team": "",
    }


def parse_policy_rows(text: str) -> list[dict[str, object]]:
    policies: list[dict[str, object]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        policies.append(_split_policy_line(line, line_number))
    if not policies:
        raise ValueError("未找到政策行。")
    return policies


def infer_report_date(policies: list[dict[str, object]]) -> str:
    latest = max(
        datetime.strptime(str(policy["date"]), "%Y-%m-%d").date()
        for policy in policies
    )
    days_until_sunday = (6 - latest.weekday()) % 7
    return (latest + timedelta(days=days_until_sunday)).strftime("%Y.%m.%d")


def build_weekly_input(text: str, report_date: str | None = None) -> dict[str, object]:
    policies = parse_policy_rows(text)
    return {
        "report_date": report_date or infer_report_date(policies),
        "report_type": "监管政策周报",
        "policies": policies,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="将 日期｜发文机构｜政策标题 政策行转换为 weekly_policies.json。"
    )
    parser.add_argument("--input", required=True, help="包含政策行的 UTF-8 文本文件")
    parser.add_argument("--output", required=True, help="生成的 weekly_policies.json 路径")
    parser.add_argument("--report-date", default="", help="期号日期，格式 YYYY.MM.DD")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    payload = build_weekly_input(
        input_path.read_text(encoding="utf-8"),
        report_date=args.report_date.strip() or None,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"已转换 {len(payload['policies'])} 条政策 -> {output_path} "
        f"(report_date={payload['report_date']})"
    )


if __name__ == "__main__":
    main()
