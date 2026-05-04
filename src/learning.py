from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from docx import Document

from .schemas import (
    DraftFinalDiffItem,
    DraftFinalDiffOutput,
    FinalReportParsed,
    FinalReportParsedItem,
    PolicyCardDraft,
    PolicyCardDraftsOutput,
    PolicyFactSheetsOutput,
)

try:
    import anthropic  # type: ignore
except Exception:  # pragma: no cover
    anthropic = None

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
IMPACT_DIR = CONFIG_DIR / "impact"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _maybe_client(client: Any = None) -> Any:
    if client is not None:
        return client
    if anthropic is None:
        return None
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def _read_text_from_input(input_path: Path) -> str:
    suffix = input_path.suffix.lower()
    if suffix == ".docx":
        doc = Document(str(input_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return input_path.read_text(encoding="utf-8")


def _strip_title_number(text: str) -> str:
    return re.sub(r"^\s*\d+[\.、]\s*", "", text).strip()


def _normalize_title(text: str) -> str:
    text = _strip_title_number(text)
    # 去掉机构前缀（书名号前的部分）
    m = re.search(r"《(.+?)》", text)
    if m:
        text = m.group(1)
    else:
        text = re.sub(r"《|》", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def _load_entities() -> list[str]:
    entities = _load_json(IMPACT_DIR / "pingan_entities.json").get("entities", [])
    return [e.get("entity_name", "") for e in entities if e.get("entity_name")]


def _load_scene_focus_phrases() -> list[str]:
    data = _load_json(IMPACT_DIR / "scene_families.json")
    scenes = data.get("scene_families") or data.get("families") or []
    phrases: list[str] = []
    for scene in scenes:
        if scene.get("focus_phrase"):
            phrases.append(scene["focus_phrase"])
        phrases.extend(scene.get("preferred_focus_phrases", []))
    seen: list[str] = []
    for p in phrases:
        if p and p not in seen:
            seen.append(p)
    return seen


def _extract_entities(text: str) -> list[str]:
    return [e for e in _load_entities() if e in text]


def _extract_action(text: str) -> str:
    sentences = [s.strip() for s in re.split(r"[。；]", text) if s.strip()]
    for sent in sentences:
        if sent.startswith(("应", "可")):
            return sent + "。"
    return ""


def _extract_focus_phrase(text: str) -> str:
    m = re.search(r"后续将改变([^。；]{2,40})", text)
    if m:
        return m.group(1)
    for phrase in _load_scene_focus_phrases():
        if phrase in text:
            return phrase
    return ""


def _detect_mode(paragraph2: str) -> str:
    if not paragraph2:
        return "none"
    if paragraph2.startswith("平安集团不直接适用"):
        return "benchmark"
    if "可关注" in paragraph2 or "可评估" in paragraph2:
        return "opportunity"
    if "后续将改变" in paragraph2:
        return "scene_direct_related"
    if "有直接影响" in paragraph2:
        return "direct"
    return "none"


def _try_llm_parse(final_text: str, report_date: str, client: Any) -> Optional[FinalReportParsed]:
    prompts = _load_yaml(CONFIG_DIR / "prompts.yaml")
    system_prompt = prompts.get("final_report_parser_prompt", "")
    if not system_prompt or client is None:
        return None
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=5000,
            system=system_prompt,
            messages=[{"role": "user", "content": final_text}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        return FinalReportParsed.model_validate(data)
    except Exception:
        return None


def _fallback_parse(final_text: str, report_date: str) -> FinalReportParsed:
    text = final_text.strip()
    # split by numbered items
    blocks = re.split(r"(?m)^\s*(?=\d+[\.、])", text)
    items: list[FinalReportParsedItem] = []
    for block in blocks:
        block = block.strip()
        if not block or not re.match(r"^\d+[\.、]", block):
            continue
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        title = _strip_title_number(lines[0])
        body = "\n".join(lines[1:]).strip()
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        if len(paras) <= 1:
            sentences = [s.strip() for s in re.split(r"(?<=[。；])", body) if s.strip()]
            paragraph1 = sentences[0] if sentences else body
            paragraph2 = "".join(sentences[1:]) if len(sentences) > 1 else ""
        else:
            paragraph1 = paras[0]
            paragraph2 = paras[1] if len(paras) > 1 else ""
        items.append(
            FinalReportParsedItem(
                title=title,
                paragraph1=paragraph1,
                paragraph2=paragraph2,
                paragraph2_mode=_detect_mode(paragraph2),
                entities=_extract_entities(paragraph2),
                action=_extract_action(paragraph2),
                focus_phrase=_extract_focus_phrase(paragraph2),
            )
        )
    return FinalReportParsed(report_title="监管政策周报", report_date=report_date, items=items)


def parse_final_report(final_text: str, report_date: str, client: Any = None) -> FinalReportParsed:
    client = _maybe_client(client)
    parsed = _try_llm_parse(final_text, report_date, client)
    if parsed is not None:
        return parsed
    return _fallback_parse(final_text, report_date)


def _match_items_by_title(drafts: PolicyCardDraftsOutput, final_parsed: FinalReportParsed) -> list[tuple[PolicyCardDraft, FinalReportParsedItem]]:
    exact = {d.title: d for d in drafts.items}
    norm = {_normalize_title(d.title): d for d in drafts.items}
    pairs: list[tuple[PolicyCardDraft, FinalReportParsedItem]] = []
    for final_item in final_parsed.items:
        draft = exact.get(final_item.title) or norm.get(_normalize_title(final_item.title))
        if draft:
            pairs.append((draft, final_item))
    return pairs


def _collect_removed_errors(draft_text: str, final_text: str) -> list[str]:
    forbidden = _load_json(CONFIG_DIR / "forbidden_expansion_library.json").get("items", [])
    removed: list[str] = []
    for item in forbidden:
        pattern = item.get("pattern", "")
        if pattern and pattern in draft_text and pattern not in final_text:
            removed.append(pattern)
    return removed[:10]


def diff_draft_vs_final(
    drafts: PolicyCardDraftsOutput,
    final_parsed: FinalReportParsed,
    fact_sheets_output: PolicyFactSheetsOutput | None = None,
) -> DraftFinalDiffOutput:
    fs_map = {fs.title_display: fs for fs in fact_sheets_output.fact_sheets} if fact_sheets_output else {}
    fs_map_norm = {_normalize_title(fs.title_display): fs for fs in fact_sheets_output.fact_sheets} if fact_sheets_output else {}
    items: list[DraftFinalDiffItem] = []
    for draft, final_item in _match_items_by_title(drafts, final_parsed):
        draft_entities = _extract_entities(draft.paragraph2)
        draft_action = _extract_action(draft.paragraph2)
        draft_focus = _extract_focus_phrase(draft.paragraph2)
        fs = fs_map.get(draft.title) or fs_map_norm.get(_normalize_title(draft.title))
        items.append(
            DraftFinalDiffItem(
                title=final_item.title,
                draft_paragraph1=draft.paragraph1,
                draft_paragraph2=draft.paragraph2,
                final_paragraph1=final_item.paragraph1,
                final_paragraph2=final_item.paragraph2,
                paragraph2_mode=final_item.paragraph2_mode,
                entity_diff=f"draft={draft_entities}; final={final_item.entities}",
                action_diff=f"draft={draft_action}; final={final_item.action}",
                focus_phrase_diff=f"draft={draft_focus}; final={final_item.focus_phrase}",
                removed_errors=_collect_removed_errors(draft.paragraph1 + draft.paragraph2, final_item.paragraph1 + final_item.paragraph2),
                fact_sheet=fs,
            )
        )
    return DraftFinalDiffOutput(report_date=drafts.report_date, items=items)


def _next_id(prefix: str, existing_ids: set[str]) -> str:
    idx = 1
    while f"{prefix}_{idx:03d}" in existing_ids:
        idx += 1
    return f"{prefix}_{idx:03d}"


def _few_shot_type(mode: str, diff_item: DraftFinalDiffItem) -> str:
    if mode == "benchmark":
        return "benchmark_only"
    if mode == "opportunity":
        return "opportunity_watch"
    if mode == "scene_direct_related":
        return "scene_direct_related"
    return "direct_major"


def update_few_shots(diff: DraftFinalDiffOutput, client: Any = None) -> int:
    path = CONFIG_DIR / "few_shot_library.json"
    data = _load_json(path) or {"version": "1.0", "examples": []}
    examples = data.get("examples", [])
    existing_keys = {(e.get("paragraph1", ""), e.get("paragraph2", ""), e.get("example_type", "")) for e in examples}
    existing_ids = {e.get("example_id", "") for e in examples}
    added = 0
    for item in diff.items:
        key = (item.final_paragraph1, item.final_paragraph2, _few_shot_type(item.paragraph2_mode, item))
        if not item.final_paragraph1 or key in existing_keys:
            continue
        example = {
            "example_id": _next_id("fs_new", existing_ids),
            "example_type": _few_shot_type(item.paragraph2_mode, item),
            "trigger_features": {
                "paragraph2_mode": item.paragraph2_mode,
                "status": item.fact_sheet.status if item.fact_sheet else "",
                "topic_hints": item.fact_sheet.topic_hints if item.fact_sheet else [],
                "scene_hints": item.fact_sheet.scene_hints if item.fact_sheet else [],
                "importance": item.fact_sheet.importance if item.fact_sheet else "major",
            },
            "paragraph1": item.final_paragraph1,
            "paragraph2": item.final_paragraph2,
            "notes": "由人工终稿差异学习自动追加。",
        }
        examples.append(example)
        existing_keys.add(key)
        existing_ids.add(example["example_id"])
        added += 1
    data["examples"] = examples
    _save_json(path, data)
    return added


def update_forbidden_expansions(diff: DraftFinalDiffOutput, client: Any = None) -> int:
    path = CONFIG_DIR / "forbidden_expansion_library.json"
    data = _load_json(path) or {"version": "1.0", "items": []}
    items = data.get("items", [])
    existing_keys = {(e.get("pattern", ""), e.get("type", "")) for e in items}
    existing_ids = {e.get("id", "") for e in items}
    added = 0
    for diff_item in diff.items:
        for pattern in diff_item.removed_errors:
            key = (pattern, "over_expansion")
            if key in existing_keys:
                continue
            entry = {
                "id": _next_id("fe_new", existing_ids),
                "pattern": pattern,
                "type": "over_expansion",
                "reason": "由人工终稿删除的错误扩写自动沉淀。",
            }
            items.append(entry)
            existing_keys.add(key)
            existing_ids.add(entry["id"])
            added += 1
    data["items"] = items
    _save_json(path, data)
    return added
