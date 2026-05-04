from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import anthropic
import yaml

from .schemas import (
    FinalReportContent,
    FinalReportItem,
    PolicyCardDraft,
    PolicyCardDraftsOutput,
    PolicyFactSheetsOutput,
    RetrievedExample,
    RetrievedExamplesOutput,
)

_CONFIG_DIR = Path(__file__).parent.parent / "config"
_FEW_SHOT_PATH = _CONFIG_DIR / "few_shot_library.json"
_FORBIDDEN_PATH = _CONFIG_DIR / "forbidden_expansion_library.json"


def _load_yaml(name: str) -> dict[str, Any]:
    p = _CONFIG_DIR / f"{name}.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text


def _score_few_shot_match(ex: dict, fs_mode: str, fs_importance: str, fs_topics: list[str]) -> int:
    score = 0
    tf = ex.get("trigger_features", {})
    if tf.get("paragraph2_mode") == fs_mode:
        score += 3
    if tf.get("importance") == fs_importance:
        score += 2
    for hint in fs_topics:
        if hint in str(tf.get("topic_hints", [])):
            score += 1
    return score


def retrieve_examples(
    fact_sheets_output: PolicyFactSheetsOutput,
) -> RetrievedExamplesOutput:
    """按 fact_sheet 的 mode/importance/topic_hints 检索 few-shot 样例。"""
    few_shots = _load_json(_FEW_SHOT_PATH).get("examples", [])
    examples_by_policy_id: dict[str, list[RetrievedExample]] = {}

    for fs in fact_sheets_output.fact_sheets:
        scored = sorted(
            few_shots,
            key=lambda ex: _score_few_shot_match(ex, fs.paragraph2_mode, fs.importance, fs.topic_hints),
            reverse=True,
        )
        top = scored[:3]
        examples_by_policy_id[fs.policy_id] = [
            RetrievedExample(
                example_id=ex.get("example_id", ""),
                example_type=ex.get("example_type", "direct_major"),
                trigger_features=ex.get("trigger_features", {}),
                paragraph1=ex.get("paragraph1", ""),
                paragraph2=ex.get("paragraph2", ""),
                notes=ex.get("notes", ""),
            )
            for ex in top
        ]

    return RetrievedExamplesOutput(
        report_date=fact_sheets_output.report_date,
        examples_by_policy_id=examples_by_policy_id,
    )


def build_generation_prompt(
    fact_sheets_output: PolicyFactSheetsOutput,
    retrieved_examples: RetrievedExamplesOutput | None = None,
) -> str:
    """组装一段完整的 Markdown 提示词，由调用方 LLM（如 Claude Code 会话）直接读取并产出 drafts。

    本函数不调 anthropic SDK，仅做数据汇总。
    """
    if retrieved_examples is None:
        retrieved_examples = retrieve_examples(fact_sheets_output)

    prompts_cfg = _load_yaml("prompts")
    business_rules = _load_yaml("business_rules")
    style_rules = _load_yaml("style")
    forbidden = _load_json(_FORBIDDEN_PATH).get("items", [])
    system_prompt = prompts_cfg.get("weekly_report_generation_prompt", "").strip()

    # 展平 few-shot
    seen_ids: set[str] = set()
    flat_examples: list[dict] = []
    for examples in retrieved_examples.examples_by_policy_id.values():
        for ex in examples:
            if ex.example_id not in seen_ids:
                seen_ids.add(ex.example_id)
                flat_examples.append(ex.model_dump())

    payload = {
        "report_date": fact_sheets_output.report_date,
        "report_type": "监管政策周报",
        "fact_sheets": [fs.model_dump() for fs in fact_sheets_output.fact_sheets],
        "few_shots": flat_examples[:8],
        "business_rules": business_rules,
        "style_rules": style_rules,
        "forbidden_expansions": [f["pattern"] for f in forbidden[:20]],
    }

    parts: list[str] = []
    parts.append("# 监管政策周报草稿生成任务")
    parts.append("")
    parts.append(f"**周报日期**：{fact_sheets_output.report_date}")
    parts.append(f"**待生成条数**：{len(fact_sheets_output.fact_sheets)}")
    parts.append("")
    parts.append("## 系统指令（写作规则）")
    parts.append("")
    parts.append(system_prompt or "_(prompts.yaml 未配置 weekly_report_generation_prompt)_")
    parts.append("")
    parts.append("## 输入数据（fact_sheets + few-shot + 业务规则）")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(payload, ensure_ascii=False, indent=2))
    parts.append("```")
    parts.append("")
    parts.append("## 输出要求")
    parts.append("")
    parts.append("严格输出以下 JSON 结构（不要 Markdown 代码块包裹，不要解释文字）：")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps({
        "report_date": fact_sheets_output.report_date,
        "items": [
            {
                "policy_id": "<对应 fact_sheets 的 policy_id>",
                "title": "<政策标题>",
                "url": "<官网原文 URL>",
                "paragraph1": "<P1 政策摘要：机构 / 文号 / 状态 / 关键阈值 / 时间要求>",
                "paragraph2": "<P2 平安影响（重点文件才有）：受影响主体 + 1 个关键动作>",
                "paragraph2_mode": "<direct | scene_direct_related | benchmark | opportunity | none>",
                "importance": "<major | minor>",
                "editor_notes": "<可选：留给人工编辑的备注>",
            }
        ],
    }, ensure_ascii=False, indent=2))
    parts.append("```")
    parts.append("")
    parts.append("将上述 JSON 直接写入 `policy_card_drafts.json`，然后运行 `python -m src.main finalize` 完成校验和 docx 渲染。")
    return "\n".join(parts)


def _build_generation_payload(
    fact_sheets: list[dict],
    retrieved: RetrievedExamplesOutput,
    business_rules: dict,
    style_rules: dict,
    forbidden: list[dict],
    report_date: str,
) -> str:
    # 把检索到的样例展平为列表（去重）
    seen_ids: set[str] = set()
    flat_examples: list[dict] = []
    for examples in retrieved.examples_by_policy_id.values():
        for ex in examples:
            if ex.example_id not in seen_ids:
                seen_ids.add(ex.example_id)
                flat_examples.append(ex.model_dump())

    payload = {
        "report_date": report_date,
        "report_type": "监管政策周报",
        "fact_sheets": fact_sheets,
        "few_shots": flat_examples[:8],
        "business_rules": business_rules,
        "style_rules": style_rules,
        "forbidden_expansions": [f["pattern"] for f in forbidden[:20]],
    }
    return json.dumps(payload, ensure_ascii=False)


def _coerce_draft_items(
    data: dict,
    report_date: str,
    fact_sheets: list | None = None,
) -> PolicyCardDraftsOutput:
    # 构建 title_display → policy_id 的回填映射
    title_to_pid: dict[str, str] = {}
    if fact_sheets:
        for fs in fact_sheets:
            if hasattr(fs, "title_display") and fs.title_display:
                title_to_pid[fs.title_display] = fs.policy_id
            if hasattr(fs, "title") and fs.title:
                title_to_pid[fs.title] = fs.policy_id

    items = []
    for item in data.get("items", []):
        mode = item.get("paragraph2_mode", "none")
        if mode not in {"direct", "scene_direct_related", "benchmark", "opportunity", "none"}:
            mode = "none"
        importance = item.get("importance", "minor")
        if importance not in {"major", "minor"}:
            importance = "minor"
        pid = item.get("policy_id", "") or title_to_pid.get(item.get("title", ""), "")
        items.append(PolicyCardDraft(
            policy_id=pid,
            title=item.get("title", ""),
            url=item.get("url", ""),
            paragraph1=item.get("paragraph1", ""),
            paragraph2=item.get("paragraph2", ""),
            paragraph2_mode=mode,
            importance=importance,
            editor_notes=item.get("editor_notes", ""),
        ))
    return PolicyCardDraftsOutput(report_date=report_date, items=items)


def generate_drafts(
    fact_sheets_output: PolicyFactSheetsOutput,
    retrieved_examples: RetrievedExamplesOutput | None = None,
    client: anthropic.Anthropic | None = None,
) -> PolicyCardDraftsOutput:
    if client is None:
        client = anthropic.Anthropic()
    if retrieved_examples is None:
        retrieved_examples = retrieve_examples(fact_sheets_output)

    prompts_cfg = _load_yaml("prompts")
    business_rules = _load_yaml("business_rules")
    style_rules = _load_yaml("style")
    forbidden = _load_json(_FORBIDDEN_PATH).get("items", [])
    generation_prompt = prompts_cfg.get("weekly_report_generation_prompt", "")

    fs_dicts = [fs.model_dump() for fs in fact_sheets_output.fact_sheets]
    user_content = _build_generation_payload(
        fs_dicts, retrieved_examples, business_rules, style_rules, forbidden,
        fact_sheets_output.report_date,
    )

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        system=generation_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = _strip_fences(response.content[0].text)
    data = json.loads(raw)
    return _coerce_draft_items(data, fact_sheets_output.report_date, fact_sheets_output.fact_sheets)


def rewrite_failed_items(
    drafts: PolicyCardDraftsOutput,
    fact_sheets_output: PolicyFactSheetsOutput,
    validation_report: Any,
    retrieved_examples: RetrievedExamplesOutput | None = None,
    client: anthropic.Anthropic | None = None,
) -> PolicyCardDraftsOutput:
    """重写校验失败的条目，未失败条目保持不变，返回 PolicyCardDraftsOutput。"""
    failed_ids = {item.policy_id for item in validation_report.items if not item.passed}
    if not failed_ids:
        return drafts

    if client is None:
        client = anthropic.Anthropic()

    prompts_cfg = _load_yaml("prompts")
    rewrite_prompt = prompts_cfg.get("report_rewrite_prompt", "")
    business_rules = _load_yaml("business_rules")
    style_rules = _load_yaml("style")

    # 展平 few-shots
    flat_examples: list[dict] = []
    if retrieved_examples:
        seen: set[str] = set()
        for examples in retrieved_examples.examples_by_policy_id.values():
            for ex in examples:
                if ex.example_id not in seen:
                    seen.add(ex.example_id)
                    flat_examples.append(ex.model_dump())

    payload = {
        "report_date": drafts.report_date,
        "draft_report": {"items": [d.model_dump() for d in drafts.items]},
        "fact_sheets": [fs.model_dump() for fs in fact_sheets_output.fact_sheets],
        "validation_report": validation_report.model_dump(),
        "few_shots": flat_examples[:6],
        "business_rules": business_rules,
        "style_rules": style_rules,
    }

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        system=rewrite_prompt,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    raw = _strip_fences(response.content[0].text)
    data = json.loads(raw)

    rewritten_map: dict[str, PolicyCardDraft] = {}
    for item in data.get("items", []):
        pid = item.get("policy_id", "")
        if pid in failed_ids:
            mode = item.get("paragraph2_mode", "none")
            if mode not in {"direct", "scene_direct_related", "benchmark", "opportunity", "none"}:
                mode = "none"
            importance = item.get("importance", "minor")
            if importance not in {"major", "minor"}:
                importance = "minor"
            rewritten_map[pid] = PolicyCardDraft(
                policy_id=pid,
                title=item.get("title", ""),
                url=item.get("url", ""),
                paragraph1=item.get("paragraph1", ""),
                paragraph2=item.get("paragraph2", ""),
                paragraph2_mode=mode,
                importance=importance,
                editor_notes=item.get("editor_notes", ""),
            )

    merged = [rewritten_map.get(d.policy_id, d) for d in drafts.items]
    return PolicyCardDraftsOutput(report_date=drafts.report_date, items=merged)


def build_final_report_content(drafts: PolicyCardDraftsOutput) -> FinalReportContent:
    """将 PolicyCardDraftsOutput 转为 FinalReportContent。"""
    items = [
        FinalReportItem(
            title=d.title,
            url=d.url,
            paragraph1=d.paragraph1,
            paragraph2=d.paragraph2,
            paragraph2_mode=d.paragraph2_mode,
            importance=d.importance,
            editor_notes=d.editor_notes,
        )
        for d in drafts.items
    ]
    return FinalReportContent(report_date=drafts.report_date, items=items)
