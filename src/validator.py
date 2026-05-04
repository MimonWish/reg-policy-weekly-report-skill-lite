from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from .schemas import (
    PolicyCardDraft,
    PolicyCardDraftsOutput,
    PolicyFactSheet,
    PolicyFactSheetsOutput,
    ValidationError,
    ValidationItem,
    ValidationReport,
    ValidationWarning,
)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_forbidden_patterns() -> list[str]:
    path = CONFIG_DIR / "forbidden_expansion_library.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [item.get("pattern", "") for item in data.get("items", []) if item.get("pattern")]


def _normalize_text(text: str) -> str:
    return re.sub(r"[\s，。；：、“”‘’（）()《》【】\-]", "", text or "")


def _contains_any(text: str, phrases: Iterable[str]) -> str | None:
    for phrase in phrases:
        if phrase and phrase in text:
            return phrase
    return None


def _extract_entities_from_text(text: str, allowed_entities: list[str]) -> list[str]:
    return [e for e in allowed_entities if e and e in text]


def _extract_action_candidate(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    parts = re.split(r"。|；", text)
    for part in parts:
        part = part.strip()
        if part.startswith(("应", "可")):
            return part + ("。" if not part.endswith("。") else "")
    return parts[-1].strip() + "。" if parts and parts[-1].strip() else ""


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_text(a), _normalize_text(b)).ratio()


def _validate_paragraph1_facts(draft: PolicyCardDraft, fs: PolicyFactSheet) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not draft.paragraph1 or not fs.allowed_paragraph1_facts:
        return errors
    clauses = [c.strip() for c in re.split(r"[。；]", draft.paragraph1) if c.strip()]
    allowed = fs.allowed_paragraph1_facts + fs.core_points
    if not clauses:
        return errors
    bad_clauses: list[str] = []
    for clause in clauses[1:]:  # skip lead sentence
        if len(clause) < 8:
            continue
        if max((_similar(clause, af) for af in allowed), default=0.0) < 0.32:
            bad_clauses.append(clause)
    if bad_clauses:
        errors.append(
            ValidationError(
                code="unsupported_fact_in_p1",
                message="paragraph1 存在疑似超出事实卡的制度变化描述",
                evidence=bad_clauses[0][:80],
                suggested_fix="删除越界事实，改回 allowed_paragraph1_facts 或 core_points。",
            )
        )
    return errors


def _validate_paragraph2_entities(draft: PolicyCardDraft, fs: PolicyFactSheet) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not draft.paragraph2:
        return errors
    all_known = set(fs.allowed_paragraph2_entities + fs.affected_entities)
    detected = _extract_entities_from_text(draft.paragraph2, list(all_known))
    disallowed = [x for x in detected if x not in fs.allowed_paragraph2_entities]
    if disallowed:
        errors.append(
            ValidationError(
                code="entity_not_allowed_in_p2",
                message="paragraph2 使用了不允许的主体",
                evidence="、".join(disallowed),
                suggested_fix=f"只使用：{'、'.join(fs.allowed_paragraph2_entities[:3])}",
            )
        )
    return errors


def _validate_paragraph2_actions(draft: PolicyCardDraft, fs: PolicyFactSheet) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not draft.paragraph2 or not fs.allowed_paragraph2_actions:
        return errors
    candidate = _extract_action_candidate(draft.paragraph2)
    if not candidate:
        return errors
    if max((_similar(candidate, act) for act in fs.allowed_paragraph2_actions), default=0.0) < 0.40:
        errors.append(
            ValidationError(
                code="action_not_allowed_in_p2",
                message="paragraph2 主动作不在允许动作列表中",
                evidence=candidate,
                suggested_fix=f"改为：{fs.allowed_paragraph2_actions[0]}",
            )
        )
    return errors


def _validate_forbidden_expansions(draft: PolicyCardDraft, forbidden_patterns: list[str]) -> list[ValidationError]:
    text = f"{draft.paragraph1}\n{draft.paragraph2}"
    hit = _contains_any(text, forbidden_patterns)
    if hit:
        return [
            ValidationError(
                code="forbidden_expansion_hit",
                message="命中禁写模式",
                evidence=hit,
                suggested_fix="删除该扩写或改回事实卡允许表达。",
            )
        ]
    return []


def _validate_mode_specific_rules(draft: PolicyCardDraft) -> tuple[list[ValidationError], list[ValidationWarning]]:
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []
    valid_modes = {"direct", "scene_direct_related", "benchmark", "opportunity", "none"}
    if draft.paragraph2_mode not in valid_modes:
        errors.append(ValidationError(code="invalid_paragraph2_mode", message="paragraph2_mode 非法", evidence=draft.paragraph2_mode))
        return errors, warnings

    strong_prefixes = ["应立即", "应尽快", "应开展专项排查", "应全面修订", "应统一牵头"]
    if draft.paragraph2_mode == "benchmark" and draft.paragraph2:
        if len(re.split(r"[。；]", draft.paragraph2.strip("。；"))) > 1:
            warnings.append(ValidationWarning(code="benchmark_written_as_two_paragraphs", message="benchmark 第二段过长", evidence=draft.paragraph2[:80]))
        for prefix in strong_prefixes:
            if prefix in draft.paragraph2:
                errors.append(ValidationError(code="benchmark_written_as_two_paragraphs", message="benchmark 模式不应出现强整改动作", evidence=prefix))
                break
    if draft.paragraph2_mode == "opportunity" and draft.paragraph2:
        strong_remediation = ["应立即整改", "应立即执行", "应立即开展专项排查", "应全面修订", "应开展专项排查"]
        for phrase in strong_remediation:
            if phrase in draft.paragraph2:
                errors.append(ValidationError(code="opportunity_written_as_remediation", message="opportunity 模式写成了整改动作", evidence=phrase))
                break
    return errors, warnings


def _validate_similarity(draft: PolicyCardDraft) -> list[ValidationError]:
    if not draft.paragraph1 or not draft.paragraph2:
        return []
    if _similar(draft.paragraph1, draft.paragraph2) > 0.68:
        return [ValidationError(code="p2_repeats_p1", message="paragraph2 与 paragraph1 高度重复", evidence=draft.paragraph2[:80])]
    overlap = set(re.split(r"[。；，]", draft.paragraph1)) & set(re.split(r"[。；，]", draft.paragraph2))
    overlap = {x for x in overlap if len(x.strip()) >= 12}
    if overlap:
        return [ValidationError(code="p2_repeats_p1", message="paragraph2 重复复述 paragraph1", evidence=list(overlap)[0][:80])]
    return []


def _validate_title(draft: PolicyCardDraft, fs: PolicyFactSheet) -> list[ValidationError]:
    if _similar(draft.title, fs.title_display) < 0.50:
        return [ValidationError(code="title_mismatch", message="标题与事实卡展示标题疑似不一致", evidence=draft.title)]
    return []


def _validate_grouped_pair(drafts: PolicyCardDraftsOutput, fact_sheets: PolicyFactSheetsOutput) -> dict[str, str]:
    errors_by_policy_id: dict[str, str] = {}
    group_counts: dict[str, list[str]] = {}
    for item in drafts.items:
        if item.grouping_key:
            group_counts.setdefault(item.grouping_key, []).append(item.policy_id)
    for key, ids in group_counts.items():
        if len(ids) > 1:
            for pid in ids:
                errors_by_policy_id[pid] = key
    return errors_by_policy_id


def validate_drafts(
    drafts: PolicyCardDraftsOutput,
    fact_sheets_output: PolicyFactSheetsOutput,
    forbidden_patterns: list[str] | None = None,
) -> ValidationReport:
    forbidden_patterns = forbidden_patterns or _load_forbidden_patterns()
    fact_sheet_map = {fs.policy_id: fs for fs in fact_sheets_output.fact_sheets}
    grouped_pair_errors = _validate_grouped_pair(drafts, fact_sheets_output)

    items: list[ValidationItem] = []
    for draft in drafts.items:
        fs = fact_sheet_map.get(draft.policy_id)
        errors: list[ValidationError] = []
        warnings: list[ValidationWarning] = []
        if fs is None:
            errors.append(ValidationError(code="missing_required_fact", message="未找到对应 fact sheet", evidence=draft.policy_id))
        else:
            errors.extend(_validate_title(draft, fs))
            errors.extend(_validate_paragraph1_facts(draft, fs))
            errors.extend(_validate_paragraph2_entities(draft, fs))
            errors.extend(_validate_paragraph2_actions(draft, fs))
            errors.extend(_validate_forbidden_expansions(draft, forbidden_patterns + fs.forbidden_expansions))

        mode_errors, mode_warnings = _validate_mode_specific_rules(draft)
        errors.extend(mode_errors)
        warnings.extend(mode_warnings)
        errors.extend(_validate_similarity(draft))

        if draft.policy_id in grouped_pair_errors:
            errors.append(
                ValidationError(
                    code="grouped_pair_not_merged",
                    message="同一 grouped pair 被拆成多条输出",
                    evidence=grouped_pair_errors[draft.policy_id],
                    suggested_fix="合并成一条主卡片。",
                )
            )

        passed = not errors
        items.append(
            ValidationItem(
                policy_id=draft.policy_id,
                title=draft.title,
                passed=passed,
                errors=errors,
                warnings=warnings,
                rewrite_required=not passed,
            )
        )

    passed = all(item.passed for item in items)
    failed = sum(1 for item in items if not item.passed)
    summary = f"共 {len(items)} 条，全部通过" if passed else f"共 {len(items)} 条，{failed} 条未通过硬校验"
    return ValidationReport(
        report_title=drafts.report_title,
        report_date=drafts.report_date,
        passed=passed,
        items=items,
        summary=summary,
    )
