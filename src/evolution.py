from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from docx import Document

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_RULE_REGISTRY = CONFIG_DIR / "evolution_rules.json"


def _json_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _alignment_name(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.split(" ")[0] if text else ""


def _run_color(run: Any) -> str:
    if run.font.color and run.font.color.rgb:
        return str(run.font.color.rgb)
    return ""


def _strip_item_number(text: str) -> str:
    return re.sub(r"^\s*\d+[\.、]\s*", "", text).strip()


def normalize_title(text: str) -> str:
    text = _strip_item_number(text)
    m = re.search(r"《(.+?)》", text)
    if m:
        text = m.group(1)
    else:
        text = re.sub(r"《|》", "", text)
    return re.sub(r"\s+", "", text)


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", "", text or "")
    return re.sub(r"[，。；：、“”‘’（）()《》#\-—_｜|\[\]【】]", "", text)


def similarity(a: str, b: str) -> float:
    na = normalize_text(a)
    nb = normalize_text(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _load_pingan_entities() -> list[str]:
    path = CONFIG_DIR / "impact" / "pingan_entities.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    entities = data.get("entities", [])
    names: list[str] = []
    for item in entities:
        if isinstance(item, dict) and item.get("entity_name"):
            names.append(item["entity_name"])
        elif isinstance(item, str):
            names.append(item)
    # Common business labels may appear in expert drafts but not in the base entity file.
    names.extend(
        [
            "集团合规部",
            "集团科技条线",
            "集团品牌传播条线",
            "集团公益条线",
            "平安公益基金会",
            "平安银行对公业务",
            "平安银行普惠业务",
            "平安银行上海业务",
            "平安产险新能源车险",
            "平安健康险",
            "保险再保相关团队",
        ]
    )
    seen: list[str] = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return seen


def extract_entities(text: str) -> list[str]:
    return [entity for entity in _load_pingan_entities() if entity in text]


def detect_paragraph2_mode(text: str) -> str:
    if not text:
        return "none"
    if "不直接" in text or "对标" in text:
        if "可关注" not in text and "机会" not in text:
            return "benchmark"
    if "可关注" in text or "机会" in text or "方向性指引" in text:
        return "opportunity"
    if "场景" in text or "链路" in text:
        if "直接影响" not in text:
            return "scene_direct_related"
    if "直接影响" in text or "需" in text or "应" in text:
        return "direct"
    return "none"


def _paragraph_runs(paragraph: Any) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for run in paragraph.runs:
        if not run.text:
            continue
        runs.append(
            {
                "text": run.text,
                "bold": bool(run.bold),
                "color": _run_color(run),
            }
        )
    return runs


def _highlight_phrases(paragraphs: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    red: list[str] = []
    black: list[str] = []
    for paragraph in paragraphs:
        for run in paragraph.get("runs", []):
            text = run.get("text", "").strip()
            if not text or not run.get("bold"):
                continue
            if run.get("color") == "FF0000":
                red.append(text)
            elif run.get("color") in {"000000", ""}:
                black.append(text)
    return {"red_bold": red, "black_bold": black}


def extract_docx_report(path: Path | str) -> dict[str, Any]:
    docx_path = Path(path)
    doc = Document(str(docx_path))
    raw_paragraphs: list[dict[str, Any]] = []
    for idx, paragraph in enumerate(doc.paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue
        raw_paragraphs.append(
            {
                "index": idx,
                "text": text,
                "style": paragraph.style.name if paragraph.style else "",
                "alignment": _alignment_name(paragraph.alignment),
                "runs": _paragraph_runs(paragraph),
            }
        )

    report_title = ""
    report_date = ""
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for paragraph in raw_paragraphs:
        text = paragraph["text"]
        style = paragraph["style"]
        is_item_heading = bool(re.match(r"^\s*\d+[\.、]\s+", text))

        if style == "Heading 1" and not report_title:
            report_title = text
            continue
        if (style == "Heading 2" or text.startswith("#")) and not is_item_heading:
            report_date = text.lstrip("#")
            continue
        if is_item_heading:
            current = {
                "title": _strip_item_number(text),
                "title_numbered": text,
                "title_norm": normalize_title(text),
                "heading_style": style,
                "heading_alignment": paragraph["alignment"],
                "paragraphs": [],
            }
            items.append(current)
            continue
        if current is not None:
            current["paragraphs"].append(paragraph)
        elif not report_title:
            report_title = text

    for item in items:
        body_texts = [p["text"] for p in item["paragraphs"]]
        item["paragraph1"] = body_texts[0] if body_texts else ""
        item["paragraph2"] = body_texts[1] if len(body_texts) > 1 else ""
        item["paragraph2_mode"] = detect_paragraph2_mode(item["paragraph2"])
        item["entities"] = extract_entities(item["paragraph2"])
        item["highlights"] = _highlight_phrases(item["paragraphs"])

    style_summary = {
        "title": raw_paragraphs[0] if raw_paragraphs else {},
        "date": next((p for p in raw_paragraphs if p["text"].startswith("#") or p["style"] == "Heading 2"), {}),
        "item_heading_alignments": [item["heading_alignment"] for item in items],
        "red_bold_count": sum(len(item["highlights"]["red_bold"]) for item in items),
        "black_bold_count": sum(len(item["highlights"]["black_bold"]) for item in items),
    }
    return {
        "path": str(docx_path),
        "report_title": report_title,
        "report_date": report_date,
        "paragraph_count": len(raw_paragraphs),
        "item_count": len(items),
        "style_summary": style_summary,
        "items": items,
        "raw_paragraphs": raw_paragraphs,
    }


def _match_items(system: dict[str, Any], expert: dict[str, Any]) -> list[dict[str, Any]]:
    system_by_norm = {item["title_norm"]: item for item in system["items"]}
    matched_system: set[str] = set()
    rows: list[dict[str, Any]] = []

    for expert_item in expert["items"]:
        norm = expert_item["title_norm"]
        system_item = system_by_norm.get(norm)
        match_score = 1.0 if system_item else 0.0
        if system_item is None:
            best: tuple[float, dict[str, Any] | None] = (0.0, None)
            for candidate in system["items"]:
                score = SequenceMatcher(None, norm, candidate["title_norm"]).ratio()
                if score > best[0]:
                    best = (score, candidate)
            if best[0] >= 0.72:
                match_score, system_item = best
        if system_item is None:
            rows.append(
                {
                    "status": "missing_in_system",
                    "title": expert_item["title"],
                    "expert_title": expert_item["title"],
                    "system_title": "",
                    "match_score": 0.0,
                }
            )
            continue

        matched_system.add(system_item["title_norm"])
        system_entities = set(system_item.get("entities", []))
        expert_entities = set(expert_item.get("entities", []))
        system_mode = system_item.get("paragraph2_mode", "none")
        expert_mode = expert_item.get("paragraph2_mode", "none")
        p1_similarity = similarity(system_item.get("paragraph1", ""), expert_item.get("paragraph1", ""))
        p2_similarity = similarity(system_item.get("paragraph2", ""), expert_item.get("paragraph2", ""))
        rows.append(
            {
                "status": "matched",
                "title": expert_item["title"],
                "expert_title": expert_item["title"],
                "system_title": system_item["title"],
                "match_score": round(match_score, 3),
                "paragraph1_similarity": round(p1_similarity, 3),
                "paragraph2_similarity": round(p2_similarity, 3),
                "system_mode": system_mode,
                "expert_mode": expert_mode,
                "mode_changed": system_mode != expert_mode,
                "entities_added_by_expert": sorted(expert_entities - system_entities),
                "entities_removed_by_expert": sorted(system_entities - expert_entities),
                "system_red_bold_count": len(system_item["highlights"]["red_bold"]),
                "expert_red_bold_count": len(expert_item["highlights"]["red_bold"]),
                "system_black_bold_count": len(system_item["highlights"]["black_bold"]),
                "expert_black_bold_count": len(expert_item["highlights"]["black_bold"]),
                "system_p1_length": len(system_item.get("paragraph1", "")),
                "expert_p1_length": len(expert_item.get("paragraph1", "")),
                "system_p2_length": len(system_item.get("paragraph2", "")),
                "expert_p2_length": len(expert_item.get("paragraph2", "")),
            }
        )

    for system_item in system["items"]:
        if system_item["title_norm"] not in matched_system:
            rows.append(
                {
                    "status": "missing_in_expert",
                    "title": system_item["title"],
                    "expert_title": "",
                    "system_title": system_item["title"],
                    "match_score": 0.0,
                }
            )
    return rows


def _proposal_for_row(row: dict[str, Any]) -> list[dict[str, str]]:
    if row.get("status") != "matched":
        return [
            {
                "learning_type": "selection_rule",
                "trigger": row.get("title", ""),
                "system_gap": "系统稿与专家稿条目集合不一致。",
                "expert_pattern": "需要由 Codex 人工判断该条应纳入、剔除、合并或拆分。",
                "proposed_change": "更新筛选/合并规则或本期条目判断说明。",
                "risk": "需避免把单周取舍当作长期规则。",
                **_confidence_fields(row, "selection_rule"),
            }
        ]

    proposals: list[dict[str, str]] = []
    title = row.get("title", "")
    if row.get("mode_changed"):
        proposals.append(
            {
                "learning_type": "p2_mode_rule",
                "trigger": title,
                "system_gap": f"系统为 {row.get('system_mode')}，专家为 {row.get('expert_mode')}。",
                "expert_pattern": "专家对第二段性质的判断不同，需抽象为触发条件而非照搬正文。",
                "proposed_change": "补充 paragraph2_mode 判断边界和适用场景。",
                "risk": "同类政策可能因业务范围不同而变化，需限定适用边界。",
                **_confidence_fields(row, "p2_mode_rule"),
            }
        )
    if row.get("entities_added_by_expert") or row.get("entities_removed_by_expert"):
        added = "、".join(row.get("entities_added_by_expert", [])) or "无"
        removed = "、".join(row.get("entities_removed_by_expert", [])) or "无"
        proposals.append(
            {
                "learning_type": "impact_mapping",
                "trigger": title,
                "system_gap": f"专家新增主体：{added}；专家删除主体：{removed}。",
                "expert_pattern": "专家对受影响专业公司和业务链路的映射更细或更克制。",
                "proposed_change": "更新专业公司影响映射或 P2 主体选择规则。",
                "risk": "不得把专家稿主体清单机械套用到所有同主题政策。",
                **_confidence_fields(row, "impact_mapping"),
            }
        )
    if row.get("system_red_bold_count") != row.get("expert_red_bold_count") or row.get("system_black_bold_count") != row.get("expert_black_bold_count"):
        proposals.append(
            {
                "learning_type": "highlight_rule",
                "trigger": title,
                "system_gap": f"红字 {row.get('system_red_bold_count')}→{row.get('expert_red_bold_count')}，黑体 {row.get('system_black_bold_count')}→{row.get('expert_black_bold_count')}。",
                "expert_pattern": "专家稿对监管硬事实和业务主体的强调范围不同。",
                "proposed_change": "更新红字/黑体高亮选择逻辑。",
                "risk": "只学习高亮类别，不学习专家稿原句高亮片段。",
                **_confidence_fields(row, "highlight_rule"),
            }
        )
    if abs(row.get("system_p1_length", 0) - row.get("expert_p1_length", 0)) > 80 or abs(row.get("system_p2_length", 0) - row.get("expert_p2_length", 0)) > 60:
        proposals.append(
            {
                "learning_type": "style_rule",
                "trigger": title,
                "system_gap": "系统稿与专家稿段落长度差异较大。",
                "expert_pattern": "专家可能更重视要点密度、压缩背景或扩展业务影响。",
                "proposed_change": "补充同类政策 P1/P2 字数和信息颗粒度规则。",
                "risk": "长度差异需结合政策重要性判断，不宜一刀切。",
                **_confidence_fields(row, "style_rule"),
            }
        )
    return proposals


def _confidence_fields(row: dict[str, Any], learning_type: str) -> dict[str, Any]:
    score = 0.35
    reasons: list[str] = []
    if row.get("status") == "matched":
        score = 0.45
        if row.get("match_score", 0) >= 0.95:
            score += 0.20
            reasons.append("条目标题精确或高度匹配")
        elif row.get("match_score", 0) >= 0.85:
            score += 0.10
            reasons.append("条目标题可匹配")

    if learning_type == "p2_mode_rule":
        score += 0.20
        reasons.append("P2模式发生明确变化")
    elif learning_type == "impact_mapping":
        if row.get("entities_added_by_expert") or row.get("entities_removed_by_expert"):
            score += 0.20
            reasons.append("专家稿主体映射发生明确变化")
        if row.get("entities_added_by_expert") and not row.get("entities_removed_by_expert"):
            score += 0.05
            reasons.append("新增主体为可抽取的平安主体")
    elif learning_type == "highlight_rule":
        red_delta = abs(row.get("system_red_bold_count", 0) - row.get("expert_red_bold_count", 0))
        black_delta = abs(row.get("system_black_bold_count", 0) - row.get("expert_black_bold_count", 0))
        if red_delta + black_delta >= 2:
            score += 0.15
            reasons.append("高亮数量存在稳定可见差异")
        if row.get("expert_black_bold_count", 0) > row.get("system_black_bold_count", 0):
            score += 0.05
            reasons.append("专家稿更充分标注业务主体")
    elif learning_type == "style_rule":
        score += 0.10
        reasons.append("段落长度差异超过阈值")
    elif learning_type == "selection_rule":
        score += 0.05
        reasons.append("条目集合差异需要人工判断")

    if row.get("paragraph1_similarity", 0) >= 0.9 or row.get("paragraph2_similarity", 0) >= 0.9:
        score -= 0.10
        reasons.append("文本相似度过高，需防止把句式差异误判为规则")
    if learning_type == "selection_rule":
        score = min(score, 0.50)

    score = max(0.0, min(0.99, score))
    if score >= 0.78:
        confidence = "high"
        status = "active"
    elif score >= 0.55:
        confidence = "medium"
        status = "pending_confirmation"
    else:
        confidence = "low"
        status = "pending_confirmation"
    return {
        "confidence": confidence,
        "confidence_score": round(score, 2),
        "status": status,
        "activation_reason": "；".join(reasons) if reasons else "差异信号不足，需人工确认",
    }


def _rule_key(proposal: dict[str, Any]) -> str:
    basis = "|".join(
        [
            proposal.get("learning_type", ""),
            proposal.get("trigger", ""),
            proposal.get("proposed_change", ""),
            proposal.get("expert_pattern", ""),
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _rule_scope(learning_type: str) -> str:
    return {
        "selection_rule": "policy_selection_and_grouping",
        "p2_mode_rule": "paragraph2_mode_boundary",
        "impact_mapping": "professional_company_impact_mapping",
        "highlight_rule": "red_black_highlight_logic",
        "style_rule": "paragraph_granularity_and_tone",
    }.get(learning_type, "general_weekly_report_instruction")


def _infer_policy_family(trigger: str) -> str:
    text = trigger or ""
    keyword_map = [
        ("金融产品网络营销", "financial_product_marketing"),
        ("董事会秘书", "listed_company_governance"),
        ("服务业", "service_sector_policy"),
        ("期货", "securities_futures"),
        ("证券", "securities_futures"),
        ("基金", "asset_management"),
        ("信托", "trust_business"),
        ("数据出境", "data_cross_border"),
        ("数据", "data_governance"),
        ("慈善", "public_welfare"),
        ("募捐", "public_welfare"),
        ("动力电池", "green_recycling"),
        ("科技创新", "technology_finance"),
        ("设备更新", "technology_finance"),
        ("社会救助", "social_governance"),
        ("监狱法", "justice_administration"),
    ]
    for keyword, family in keyword_map:
        if keyword in text:
            return family
    return "general_regulatory_policy"


def _lifecycle_fields(proposal: dict[str, Any], source_reports: list[dict[str, str]] | None = None) -> dict[str, Any]:
    today = datetime.now().date()
    learning_type = proposal.get("learning_type", "")
    return {
        "scope": _rule_scope(learning_type),
        "policy_family": _infer_policy_family(proposal.get("trigger", "")),
        "evidence_count": 1,
        "support_count": 1,
        "source_reports": source_reports or [],
        "review_after": (today + timedelta(days=90)).isoformat(),
        "expires_at": (today + timedelta(days=365)).isoformat(),
        "deactivation_condition": "若后续2次专家稿对同一scope和policy_family给出相反判断，降级为 pending_confirmation 并等待人工复核。",
    }


def _candidate_rule(proposal: dict[str, Any], source_reports: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "rule_key": _rule_key(proposal),
        "learning_type": proposal.get("learning_type", ""),
        "trigger": proposal.get("trigger", ""),
        "rule": proposal.get("proposed_change", ""),
        "expert_pattern": proposal.get("expert_pattern", ""),
        "evidence": proposal.get("system_gap", ""),
        "risk": proposal.get("risk", ""),
        "confidence": proposal.get("confidence", "low"),
        "confidence_score": proposal.get("confidence_score", 0.0),
        "status": proposal.get("status", "pending_confirmation"),
        "activation_reason": proposal.get("activation_reason", ""),
        **_lifecycle_fields(proposal, source_reports),
    }


def compare_reports(system_path: Path | str, expert_path: Path | str, historical_paths: Iterable[Path | str] = ()) -> dict[str, Any]:
    system = extract_docx_report(system_path)
    expert = extract_docx_report(expert_path)
    item_rows = _match_items(system, expert)
    proposals: list[dict[str, str]] = []
    for row in item_rows:
        proposals.extend(_proposal_for_row(row))
    source_reports = [
        {"role": "system", "path": str(Path(system_path))},
        {"role": "expert", "path": str(Path(expert_path))},
    ]
    candidate_rules = [_candidate_rule(proposal, source_reports) for proposal in proposals]

    aggregate = {
        "system_item_count": system["item_count"],
        "expert_item_count": expert["item_count"],
        "matched_count": sum(1 for row in item_rows if row["status"] == "matched"),
        "missing_in_system_count": sum(1 for row in item_rows if row["status"] == "missing_in_system"),
        "missing_in_expert_count": sum(1 for row in item_rows if row["status"] == "missing_in_expert"),
        "mode_changed_count": sum(1 for row in item_rows if row.get("mode_changed")),
        "entity_changed_count": sum(1 for row in item_rows if row.get("entities_added_by_expert") or row.get("entities_removed_by_expert")),
        "highlight_changed_count": sum(
            1
            for row in item_rows
            if row.get("system_red_bold_count") != row.get("expert_red_bold_count")
            or row.get("system_black_bold_count") != row.get("expert_black_bold_count")
        ),
    }
    overfit = check_overfit(system_path, historical_paths) if historical_paths else {"hits": [], "max_similarity": 0.0}
    return {
        "system_report": {k: v for k, v in system.items() if k not in {"raw_paragraphs", "items"}},
        "expert_report": {k: v for k, v in expert.items() if k not in {"raw_paragraphs", "items"}},
        "aggregate": aggregate,
        "items": item_rows,
        "learning_proposals": proposals,
        "candidate_rules": candidate_rules,
        "overfit_check": overfit,
        "guardrails": [
            "专家稿只用于提炼模式，不直接沉淀专家原句。",
            "高置信候选规则可自动进入 active；中低置信规则必须保持 pending_confirmation。",
            "同一期专家段落不得作为 few-shot 原文复用。",
        ],
    }


def _merge_source_reports(existing_reports: list[Any], new_reports: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for report in [*existing_reports, *new_reports]:
        if not isinstance(report, dict):
            continue
        key = f"{report.get('role', '')}|{report.get('path', '')}"
        if key in seen:
            continue
        seen.add(key)
        merged.append(report)
    return merged


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def update_active_rules_registry(candidate_rules: list[dict[str, Any]], registry_path: Path | str = DEFAULT_RULE_REGISTRY) -> dict[str, Any]:
    path = Path(registry_path)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}
    data.setdefault("version", "1.0")
    data.setdefault("rules", [])

    existing = {rule.get("rule_key"): rule for rule in data["rules"]}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    active_added: list[str] = []
    active_updated: list[str] = []
    pending_count = 0
    for candidate in candidate_rules:
        if candidate.get("status") != "active" or candidate.get("confidence") != "high":
            pending_count += 1
            continue
        key = candidate["rule_key"]
        entry = {
            **candidate,
            "status": "active",
            "activation": "auto_high_confidence",
            "updated_at": now,
        }
        if key in existing:
            previous = existing[key]
            entry["created_at"] = previous.get("created_at", now)
            entry["support_count"] = _safe_int(previous.get("support_count")) + max(1, _safe_int(candidate.get("support_count"), 1))
            entry["evidence_count"] = _safe_int(previous.get("evidence_count")) + max(1, _safe_int(candidate.get("evidence_count"), 1))
            entry["source_reports"] = _merge_source_reports(previous.get("source_reports", []), candidate.get("source_reports", []))
            existing[key].update(entry)
            active_updated.append(key)
        else:
            entry["created_at"] = now
            data["rules"].append(entry)
            existing[key] = entry
            active_added.append(key)

    data["updated_at"] = now
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "registry_path": str(path),
        "active_added": active_added,
        "active_updated": active_updated,
        "pending_confirmation_count": pending_count,
        "active_total": sum(1 for rule in data["rules"] if rule.get("status") == "active"),
    }


def _body_paragraphs(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in report["items"]:
        for idx, paragraph in enumerate(item.get("paragraphs", []), start=1):
            text = paragraph["text"]
            if len(normalize_text(text)) >= 28:
                rows.append({"title": item["title"], "paragraph_index": str(idx), "text": text})
    return rows


def check_overfit(candidate_path: Path | str, historical_paths: Iterable[Path | str], threshold: float = 0.72) -> dict[str, Any]:
    candidate_file = Path(candidate_path)
    candidate_resolved = candidate_file.resolve()
    candidate_hash = _file_sha256(candidate_file)
    candidate = extract_docx_report(candidate_file)
    candidate_body = _body_paragraphs(candidate)
    hits: list[dict[str, Any]] = []
    max_similarity = 0.0
    for hist_path in historical_paths:
        path = Path(hist_path)
        if not path.exists():
            continue
        try:
            if path.resolve() == candidate_resolved:
                continue
        except Exception:
            pass
        try:
            if _file_sha256(path) == candidate_hash:
                continue
        except Exception:
            pass
        try:
            historical = extract_docx_report(path)
        except Exception:
            continue
        historical_body = _body_paragraphs(historical)
        for cand in candidate_body:
            best = {"similarity": 0.0, "historical_title": "", "historical_text": ""}
            for hist in historical_body:
                score = similarity(cand["text"], hist["text"])
                if score > best["similarity"]:
                    best = {
                        "similarity": score,
                        "historical_title": hist["title"],
                        "historical_text": hist["text"][:180],
                    }
            max_similarity = max(max_similarity, best["similarity"])
            if best["similarity"] >= threshold:
                hits.append(
                    {
                        "candidate_title": cand["title"],
                        "candidate_paragraph_index": cand["paragraph_index"],
                        "candidate_text": cand["text"][:180],
                        "historical_path": str(path),
                        "historical_title": best["historical_title"],
                        "historical_text": best["historical_text"],
                        "similarity": round(best["similarity"], 3),
                    }
                )
    return {
        "candidate_path": str(candidate_path),
        "threshold": threshold,
        "max_similarity": round(max_similarity, 3),
        "hit_count": len(hits),
        "hits": hits,
    }


def render_gap_markdown(result: dict[str, Any]) -> str:
    agg = result["aggregate"]
    lines = [
        "# 周报落差分析",
        "",
        "## 总览",
        "",
        f"- 系统稿条目数：{agg['system_item_count']}",
        f"- 专家稿条目数：{agg['expert_item_count']}",
        f"- 匹配条目：{agg['matched_count']}",
        f"- 专家有而系统无：{agg['missing_in_system_count']}",
        f"- 系统有而专家无：{agg['missing_in_expert_count']}",
        f"- P2 模式变化：{agg['mode_changed_count']}",
        f"- 主体映射变化：{agg['entity_changed_count']}",
        f"- 高亮数量变化：{agg['highlight_changed_count']}",
        "",
        "## 逐条差异",
        "",
        "| 条目 | 状态 | P1相似度 | P2相似度 | 模式变化 | 专家新增主体 | 高亮变化 |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for row in result["items"]:
        title = row.get("title", "").replace("|", "\\|")
        status = row.get("status", "")
        p1 = row.get("paragraph1_similarity", "")
        p2 = row.get("paragraph2_similarity", "")
        mode = f"{row.get('system_mode')}→{row.get('expert_mode')}" if row.get("mode_changed") else ""
        added = "、".join(row.get("entities_added_by_expert", []))
        highlight = ""
        if row.get("status") == "matched":
            highlight = f"红{row.get('system_red_bold_count')}→{row.get('expert_red_bold_count')} / 黑{row.get('system_black_bold_count')}→{row.get('expert_black_bold_count')}"
        lines.append(f"| {title} | {status} | {p1} | {p2} | {mode} | {added} | {highlight} |")
    lines.extend(
        [
            "",
            "## 反过拟合提示",
            "",
            f"- 历史相似命中数：{result.get('overfit_check', {}).get('hit_count', 0)}",
            f"- 最高正文相似度：{result.get('overfit_check', {}).get('max_similarity', 0)}",
            "",
            "## 自动激活",
            "",
            f"- 新增 active 规则：{len(result.get('activation_summary', {}).get('active_added', []))}",
            f"- 更新 active 规则：{len(result.get('activation_summary', {}).get('active_updated', []))}",
            f"- 待人工确认规则：{result.get('activation_summary', {}).get('pending_confirmation_count', 0)}",
            "",
            "## 使用边界",
            "",
            "- 本分析可自动激活高置信抽象规则，但不自动修改 `SKILL.md` 或核心配置。",
            "- 专家稿只用于提炼判断模式，不作为正文素材库。",
            "- 中低置信规则需要由用户确认 `learning_proposals.md` 后再执行结构性更新。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_learning_proposals_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 自进化学习建议",
        "",
        "高置信候选规则会自动进入 active；中低置信规则保持待确认。所有规则均为抽象模式，不包含专家稿长句。",
        "",
        "| 类型 | 状态 | 置信度 | 触发条目 | 系统落差 | 建议更新 | 风险 |",
        "|---|---|---:|---|---|---|---|",
    ]
    for proposal in result.get("learning_proposals", []):
        lines.append(
            "| {learning_type} | {status} | {confidence}({confidence_score}) | {trigger} | {system_gap} | {proposed_change} | {risk} |".format(
                **{k: str(v).replace("|", "\\|") for k, v in proposal.items()}
            )
        )
    if not result.get("learning_proposals"):
        lines.append("| 无 | - | 未发现需要沉淀的稳定差异 | - | - |")
    lines.extend(
        [
            "",
            "## 确认后建议落点",
            "",
            "- `SKILL.md`：只更新核心流程、边界和硬约束。",
            "- `references/HISTORICAL_BUSINESS_REPORT_PATTERNS.md`：沉淀可复用业务写法模式。",
            "- `config/impact/professional_company_impact_rules.json`：沉淀专业公司与业务链路映射。",
            "- `references/QUALITY_CHECKLIST.md`：沉淀新增质检项。",
            "- 不直接写入专家稿原句。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_patch_plan_markdown(result: dict[str, Any]) -> str:
    touched = sorted({p["learning_type"] for p in result.get("learning_proposals", [])})
    lines = [
        "# 自进化补丁计划",
        "",
        "本文件供用户确认中低置信规则后执行。高置信规则可能已写入 active registry，但不代表已经修改 Skill 主体文件。",
        "",
        "## 建议修改范围",
        "",
    ]
    if not touched:
        lines.append("- 暂无建议修改。")
    else:
        if "p2_mode_rule" in touched:
            lines.append("- 更新 `SKILL.md` 或历史模式文档中的 paragraph2_mode 判断边界。")
        if "impact_mapping" in touched:
            lines.append("- 更新 `config/impact/professional_company_impact_rules.json` 的主体/场景映射。")
        if "highlight_rule" in touched:
            lines.append("- 更新高亮规则说明和质检项。")
        if "style_rule" in touched:
            lines.append("- 更新段落颗粒度、压缩/展开规则。")
        if "selection_rule" in touched:
            lines.append("- 更新政策筛选、合并、剔除规则。")
    lines.extend(
        [
            "",
            "## 执行前检查",
            "",
            "- 用户已确认本周学习建议。",
            "- 拟更新内容已抽象为规则，不含专家稿长句。",
            "- 更新后需重跑测试和一份历史样例回归。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_evolution_outputs(
    result: dict[str, Any],
    output_dir: Path | str,
    *,
    activate_high_confidence: bool = True,
    registry_path: Path | str = DEFAULT_RULE_REGISTRY,
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if activate_high_confidence:
        result["activation_summary"] = update_active_rules_registry(result.get("candidate_rules", []), registry_path)
    else:
        result["activation_summary"] = {
            "active_added": [],
            "active_updated": [],
            "pending_confirmation_count": sum(1 for rule in result.get("candidate_rules", []) if rule.get("status") != "active"),
            "skipped": True,
        }
    _json_dump(out / "gap_analysis.json", result)
    _json_dump(out / "candidate_rules.json", result.get("candidate_rules", []))
    (out / "gap_analysis.md").write_text(render_gap_markdown(result), encoding="utf-8")
    (out / "learning_proposals.md").write_text(render_learning_proposals_markdown(result), encoding="utf-8")
    (out / "evolution_patch_plan.md").write_text(render_patch_plan_markdown(result), encoding="utf-8")


def _paths_from_args(values: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        p = Path(value)
        if p.is_dir():
            paths.extend(path for path in sorted(p.glob("*.docx")) if not path.name.startswith("~$"))
        elif p.suffix.lower() == ".docx" and not p.name.startswith("~$"):
            paths.append(p)
    return paths


def compare_reports_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Compare system weekly report with expert final report.")
    parser.add_argument("--system", required=True, help="System-generated .docx")
    parser.add_argument("--expert", required=True, help="Expert final .docx")
    parser.add_argument("--historical", action="append", default=[], help="Historical .docx or directory; can repeat")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--no-auto-activate", action="store_true", help="Do not write high-confidence rules to active registry")
    parser.add_argument("--registry", default=str(DEFAULT_RULE_REGISTRY), help="Evolution rule registry path")
    args = parser.parse_args(argv)
    result = compare_reports(args.system, args.expert, _paths_from_args(tuple(args.historical)))
    write_evolution_outputs(
        result,
        args.output_dir,
        activate_high_confidence=not args.no_auto_activate,
        registry_path=args.registry,
    )
    print(f"wrote evolution outputs -> {args.output_dir}")


def extract_docx_style_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract structured paragraphs and styles from a .docx report.")
    parser.add_argument("--input", required=True, help="Input .docx")
    parser.add_argument("--output", required=True, help="Output JSON")
    args = parser.parse_args(argv)
    _json_dump(Path(args.output), extract_docx_report(args.input))
    print(f"wrote style extraction -> {args.output}")


def check_overfit_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Check whether a report reuses historical expert paragraphs.")
    parser.add_argument("--candidate", required=True, help="Candidate .docx")
    parser.add_argument("--historical", action="append", required=True, help="Historical .docx or directory; can repeat")
    parser.add_argument("--threshold", type=float, default=0.72)
    parser.add_argument("--output", required=True, help="Output JSON")
    args = parser.parse_args(argv)
    result = check_overfit(args.candidate, _paths_from_args(tuple(args.historical)), args.threshold)
    _json_dump(Path(args.output), result)
    print(f"wrote overfit report -> {args.output}")
