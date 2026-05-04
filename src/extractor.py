from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

from .schemas import (
    FetchedArticle,
    FetchedArticlesOutput,
    NormalizedPoliciesOutput,
    NumberThreshold,
    PolicyFactSheet,
    PolicyFactSheetsOutput,
    PolicyStatus,
    TimeRequirement,
    WeeklyPoliciesInput,
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

_STATUS_KEYWORDS: list[tuple[str, PolicyStatus]] = [
    ("征求意见稿", "征求意见稿"),
    ("公开征求意见", "征求意见稿"),
    ("修订草案", "修订草案"),
    ("草案", "修订草案"),
    ("行动方案", "计划"),
    ("工作方案", "计划"),
    ("专项行动", "专项行动"),
]

_POLICY_TYPE_KEYWORDS = [
    ("办法", "办法"),
    ("条例", "条例"),
    ("通知", "通知"),
    ("意见", "意见"),
    ("决定", "决定"),
    ("公告", "公告"),
    ("实施", "实施规定"),
    ("规则", "规则"),
    ("方案", "方案"),
    ("解释", "解释"),
]

_GENERIC_FORBIDDEN = [
    "该政策体现了",
    "该文件反映出",
    "这意味着",
    "从长期看",
    "从宏观层面看",
    "有助于",
    "进一步彰显",
    "要高度重视",
    "要认真学习领会",
    "要持续关注",
]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_configs() -> dict[str, Any]:
    return {
        "business_rules": _load_yaml(CONFIG_DIR / "business_rules.yaml"),
        "style": _load_yaml(CONFIG_DIR / "style.yaml"),
        "prompts": _load_yaml(CONFIG_DIR / "prompts.yaml"),
        "pingan_entities": _load_json(IMPACT_DIR / "pingan_entities.json"),
        "topic_families": _load_json(IMPACT_DIR / "topic_families.json"),
        "scene_families": _load_json(IMPACT_DIR / "scene_families.json"),
        "action_templates": _load_json(IMPACT_DIR / "action_templates.json"),
        "status_action_strength": _load_json(IMPACT_DIR / "status_action_strength.json"),
        "professional_company_impact_rules": _load_json(IMPACT_DIR / "professional_company_impact_rules.json"),
        "forbidden_expansion_library": _load_json(CONFIG_DIR / "forbidden_expansion_library.json"),
    }


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _cn_date(date_str: str) -> str:
    parts = date_str.split("-")
    if len(parts) == 3:
        return f"{int(parts[1])}月{int(parts[2])}日"
    return date_str


def _detect_policy_type(title: str, raw_text: str) -> str:
    combined = f"{title}\n{raw_text[:500]}"
    for keyword, value in _POLICY_TYPE_KEYWORDS:
        if keyword in combined:
            return value
    return "其他"


def _detect_status(title: str, raw_text: str) -> PolicyStatus:
    combined = f"{title}\n{raw_text[:2000]}"
    for keyword, status in _STATUS_KEYWORDS:
        if keyword in combined:
            return status
    if re.search(r"自.{0,8}(起|之日起).{0,6}(施行|实施)", combined):
        return "正式实施"
    if "公布" in title or "印发" in title or "发布" in title:
        return "正式实施"
    return "标题级分析"


def _extract_effective_or_deadline(raw_text: str, status: str) -> str:
    text = _normalize_text(raw_text)
    patterns = [
        r"自([^。；]{2,40})(施行|实施)",
        r"意见反馈截止时间[^。；]{0,40}",
        r"征求意见截止[^。；]{0,40}",
        r"过渡期[^。；]{0,40}",
        r"自发布之日起[^。；]{0,20}(施行|实施)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0)
    if status == "征求意见稿":
        return "当前处于征求意见阶段"
    if status == "修订草案":
        return "当前处于草案阶段"
    if status == "正式实施":
        return "文件已正式实施"
    return ""


def _split_sentences(text: str) -> list[str]:
    text = _normalize_text(text)
    parts = re.split(r"(?<=[。！？；])", text)
    return [p.strip() for p in parts if p.strip()]


def _extract_core_points(title: str, raw_text: str) -> list[str]:
    sentences = _split_sentences(raw_text)
    hits: list[str] = []
    keywords = ["明确", "提出", "要求", "围绕", "规范", "完善", "调整", "优化", "建立", "加强", "细化"]
    for sent in sentences:
        if len(sent) < 12 or len(sent) > 80:
            continue
        if any(k in sent for k in keywords):
            if title[:6] in sent:
                continue
            hits.append(sent)
        if len(hits) >= 4:
            break
    if hits:
        return hits[:4]
    fallback: list[str] = []
    if "监督管理" in title or "办法" in title:
        fallback.append("围绕业务边界、监管要求和执行安排作出调整。")
    if "通知" in title:
        fallback.append("对相关业务口径和执行要求作出明确。")
    if not fallback:
        fallback.append("文件围绕相关制度安排和执行口径作出部署。")
    return fallback


def _extract_numbers_and_thresholds(raw_text: str) -> list[NumberThreshold]:
    text = _normalize_text(raw_text)
    patterns = [
        r"\d+(?:\.\d+)?%",
        r"\d+(?:\.\d+)?倍",
        r"\d+(?:\.\d+)?年",
        r"\d+(?:\.\d+)?个月",
        r"\d+(?:\.\d+)?日",
        r"\d+(?:\.\d+)?万元",
        r"\d+(?:\.\d+)?亿元",
    ]
    found: list[NumberThreshold] = []
    seen: set[str] = set()
    for pat in patterns:
        for m in re.finditer(pat, text):
            token = m.group(0)
            if token in seen:
                continue
            seen.add(token)
            start = max(0, m.start() - 18)
            end = min(len(text), m.end() + 18)
            found.append(NumberThreshold(text=token, value=token, context=text[start:end]))
            if len(found) >= 8:
                return found
    return found


def _extract_time_requirements(raw_text: str) -> list[TimeRequirement]:
    text = _normalize_text(raw_text)
    results: list[TimeRequirement] = []
    patterns = [
        (r"\d{4}年\d{1,2}月\d{1,2}日", "截止时间"),
        (r"自[^。；]{1,30}(施行|实施)", "生效时间"),
        (r"过渡期[^。；]{1,30}", "过渡期"),
    ]
    seen: set[str] = set()
    for pat, category in patterns:
        for m in re.finditer(pat, text):
            token = m.group(0)
            if token in seen:
                continue
            seen.add(token)
            results.append(TimeRequirement(text=token, category=category))
            if len(results) >= 5:
                return results
    return results


def _base_title(title: str) -> str:
    t = re.sub(r"（[^）]*?征求意见稿[^）]*）", "", title)
    t = re.sub(r"（[^）]*?修订草案[^）]*）", "", t)
    t = re.sub(r"《|》", "", t)
    t = re.sub(r"关于实施.*?有关事项的公告", "", t)
    t = re.sub(r"实施[^\s]{0,20}公告", "", t)
    t = re.sub(r"公告", "", t)
    t = re.sub(r"通知", "", t)
    return re.sub(r"\s+", "", t)


def _build_grouping_key(article: FetchedArticle) -> Optional[str]:
    title = article.title
    if any(k in title for k in ["实施", "有关事项", "公告"]):
        return f"{article.issuer}|{article.date}|{_base_title(title)}"
    return None


def _merge_grouped_articles(articles: list[FetchedArticle]) -> list[FetchedArticle]:
    by_day_issuer: dict[tuple[str, str], list[FetchedArticle]] = defaultdict(list)
    for a in articles:
        by_day_issuer[(a.issuer, a.date)].append(a)

    merged: list[FetchedArticle] = []
    used: set[str] = set()

    for (_, _), group in by_day_issuer.items():
        for article in group:
            if article.policy_id in used:
                continue
            base = _base_title(article.title)
            partners = [p for p in group if p.policy_id != article.policy_id and _base_title(p.title) and _base_title(p.title) in base or base in _base_title(p.title)]
            # only merge if one of the titles is obviously implementation/announcement
            candidates = [p for p in partners if any(k in p.title for k in ["实施", "有关事项", "公告"]) or any(k in article.title for k in ["实施", "有关事项", "公告"])]
            if candidates:
                all_items = [article] + candidates
                all_items.sort(key=lambda x: ("公告" in x.title or "实施" in x.title, len(x.title)))
                master = all_items[0]
                merged_text = "\n".join([x.raw_text for x in all_items if x.raw_text])
                grouping_key = f"{master.issuer}|{master.date}|{_base_title(master.title)}"
                merged.append(
                    master.model_copy(
                        update={
                            "grouping_key": grouping_key,
                            "raw_text": merged_text or master.raw_text,
                            "metadata": {
                                **master.metadata,
                                "source_policy_ids": [x.policy_id for x in all_items],
                                "merged_count": len(all_items),
                            },
                        }
                    )
                )
                used.update(x.policy_id for x in all_items)
            else:
                merged.append(article)
                used.add(article.policy_id)
    return merged


def _score_by_keywords(text: str, keywords: Iterable[str]) -> int:
    score = 0
    for kw in keywords:
        if kw and kw in text:
            score += 1
    return score


def _merge_unique(*groups: Iterable[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in merged:
                merged.append(item)
    return merged


def _match_professional_company_rules(title: str, raw_text: str, rules_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return explicit professional-company impact rules matched by policy title/text.

    These rules are intentionally narrower than topic families. They are used to
    avoid generic second paragraphs when public source extraction is thin.
    """
    text = f"{title}\n{raw_text[:5000]}"
    matched: list[tuple[int, dict[str, Any]]] = []
    for rule in rules_config.get("rules", []):
        keywords = rule.get("keywords", [])
        score = _score_by_keywords(text, keywords)
        if score > 0:
            matched.append((score, rule))
    matched.sort(key=lambda item: item[0], reverse=True)
    return [rule for _, rule in matched[:3]]


def _iter_topic_families(topic_config: dict[str, Any]) -> list[dict[str, Any]]:
    return topic_config.get("families", [])


def _iter_scene_families(scene_config: dict[str, Any]) -> list[dict[str, Any]]:
    return scene_config.get("scene_families") or scene_config.get("families", [])


def _match_topic_hints(title: str, raw_text: str, topic_config: dict[str, Any]) -> list[str]:
    text = f"{title}\n{raw_text[:5000]}"
    scored: list[tuple[int, str]] = []
    for fam in _iter_topic_families(topic_config):
        score = _score_by_keywords(text, fam.get("aliases", []))
        score += _score_by_keywords(text, fam.get("indicative_keywords", []))
        score += 2 * _score_by_keywords(text, fam.get("indicative_topics", []))
        if score > 0:
            scored.append((score, fam.get("family_id", "")))
    scored.sort(reverse=True)
    result = [fid for _, fid in scored[:3] if fid]
    if not result and ("反外国不当域外管辖" in title or "域外管辖" in raw_text):
        result = ["overseas_legal_risk"]
    return result


def _match_scene_hints(title: str, raw_text: str, topic_hints: list[str], scene_config: dict[str, Any]) -> list[str]:
    text = f"{title}\n{raw_text[:5000]}"
    scored: list[tuple[int, str]] = []
    for fam in _iter_scene_families(scene_config):
        score = _score_by_keywords(text, fam.get("aliases", []))
        score += _score_by_keywords(text, fam.get("indicative_keywords", []))
        rel_topics = set(fam.get("related_topic_families", []))
        if rel_topics.intersection(topic_hints):
            score += 2
        if score > 0:
            scored.append((score, fam.get("scene_id", "")))
    scored.sort(reverse=True)
    return [sid for _, sid in scored[:3] if sid]


def _index_entities(entity_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e.get("entity_name", ""): e for e in entity_config.get("entities", [])}


def _index_topics(topic_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {t.get("family_id", ""): t for t in _iter_topic_families(topic_config)}


def _index_scenes(scene_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s.get("scene_id", ""): s for s in _iter_scene_families(scene_config)}


def _match_entities(topic_hints: list[str], scene_hints: list[str], entity_config: dict[str, Any], topic_config: dict[str, Any], scene_config: dict[str, Any]) -> list[str]:
    topics = _index_topics(topic_config)
    scenes = _index_scenes(scene_config)
    ranked: list[str] = []
    for tid in topic_hints:
        ranked.extend(topics.get(tid, {}).get("preferred_entities", []))
    for sid in scene_hints:
        ranked.extend(scenes.get(sid, {}).get("primary_entities", []))
        ranked.extend(scenes.get(sid, {}).get("typical_entities", []))
    valid = set(_index_entities(entity_config).keys())
    seen: list[str] = []
    for item in ranked:
        if item in valid and item not in seen:
            seen.append(item)
    return seen[:4]


def _iter_action_templates(action_config: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    data = action_config.get("action_templates") or action_config.get("templates") or {}
    if isinstance(data, dict):
        return data.items()
    return []


def _choose_action_candidates(status: str, topic_hints: list[str], scene_hints: list[str], entities: list[str], action_config: dict[str, Any]) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for key, tpl in _iter_action_templates(action_config):
        statuses = tpl.get("applicable_statuses", [])
        if statuses and status not in statuses:
            continue
        if tpl.get("applicable_topic_families") and not set(tpl["applicable_topic_families"]).intersection(topic_hints):
            continue
        if tpl.get("applicable_scene_families") and not set(tpl["applicable_scene_families"]).intersection(scene_hints):
            continue
        if tpl.get("applicable_entities") and not set(tpl["applicable_entities"]).intersection(entities):
            continue
        matched.append({"key": key, **tpl})
    matched.sort(key=lambda x: x.get("priority", 50), reverse=True)
    return matched


def _select_recommended_action(status: str, topic_hints: list[str], scene_hints: list[str], entities: list[str], action_config: dict[str, Any], strength_config: dict[str, Any]) -> tuple[str, list[str]]:
    candidates = _choose_action_candidates(status, topic_hints, scene_hints, entities, action_config)
    allowed = [c.get("template", "") for c in candidates if c.get("template")]
    if allowed:
        return allowed[0], allowed[:5]

    # fallback by strength
    status_cfg = (strength_config.get("status_levels") or {}).get(status, {})
    if status == "对标适用":
        fallback = "应对标其核心要求，优先补齐相关机制。"
    elif status in {"征求意见稿", "修订草案"}:
        fallback = "应优先评估相关影响并开展差距分析。"
    elif status == "计划":
        fallback = "可关注相关规则变化带来的业务机会。"
    elif status == "专项行动":
        fallback = "应开展相关链路排查。"
    else:
        fallback = "应开展相关要求与现有机制的差距映射。"
    return fallback, [fallback]


def _decide_paragraph2_mode(status: str, topic_hints: list[str], scene_hints: list[str], entities: list[str], topic_config: dict[str, Any], scene_config: dict[str, Any]) -> str:
    topics = _index_topics(topic_config)
    scenes = _index_scenes(scene_config)
    for sid in scene_hints:
        mode = scenes.get(sid, {}).get("paragraph2_mode_hint")
        if mode:
            return mode
    if any(topics.get(t, {}).get("benchmark_only") for t in topic_hints):
        return "benchmark"
    if any(topics.get(t, {}).get("opportunity_possible") for t in topic_hints) and status in {"计划", "征求意见稿", "正式实施"}:
        return "opportunity"
    if entities:
        return "direct"
    return "none"


def _decide_importance(status: str, topic_hints: list[str], scene_hints: list[str], entities: list[str], topic_config: dict[str, Any]) -> tuple[str, str]:
    if status == "专项行动":
        return "major", "属于专项整治或集中治理类文件。"
    if status == "对标适用":
        return "minor", "对平安集团以对标借鉴为主。"
    if any(t in topic_hints for t in [
        "cross_border_finance",
        "futures_license_and_boundary",
        "medical_service_collaboration",
        "personal_information_and_data_governance",
        "ai_model_and_interaction_governance",
    ]):
        return "major", "直接影响重点业务或集团穿透治理场景。"
    if any("平安证券投行业务" == e for e in entities) and "capital_market_reform" in topic_hints:
        return "major", "对投行业务或资本市场配置存在直接影响或机会。"
    if topic_hints == ["overseas_legal_risk"]:
        return "minor", "以涉外法治对标和风险识别为主。"
    if entities:
        return "major", "已识别出明确受影响主体。"
    return "minor", "当前更适合作为一般关注项处理。"


def _build_allowed_fact_lists(summary_anchor: str, core_points: list[str], effective_or_deadline: str, numbers: list[NumberThreshold], times: list[TimeRequirement]) -> list[str]:
    allowed: list[str] = []
    if summary_anchor:
        allowed.append(summary_anchor)
    allowed.extend(core_points)
    if effective_or_deadline:
        allowed.append(effective_or_deadline)
    allowed.extend([n.context or n.text for n in numbers[:3]])
    allowed.extend([t.text for t in times[:3]])
    return [a for a in allowed if a]


def _pick_focus_phrases(scene_hints: list[str], scene_config: dict[str, Any]) -> list[str]:
    scenes = _index_scenes(scene_config)
    phrases: list[str] = []
    for sid in scene_hints:
        phrases.extend(scenes.get(sid, {}).get("preferred_focus_phrases", []))
        phrase = scenes.get(sid, {}).get("focus_phrase")
        if phrase:
            phrases.append(phrase)
    seen: list[str] = []
    for p in phrases:
        if p and p not in seen:
            seen.append(p)
    return seen[:3]


def _rule_values(rules: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for rule in rules:
        value = rule.get(key, [])
        if isinstance(value, str):
            values.append(value)
        else:
            values.extend(value or [])
    return values


def _first_rule_value(rules: list[dict[str, Any]], key: str) -> str:
    for rule in rules:
        value = rule.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _filter_forbidden_patterns(topic_hints: list[str], scene_hints: list[str], forbidden_config: dict[str, Any]) -> list[str]:
    items = forbidden_config.get("items", [])
    patterns = [it.get("pattern", "") for it in items[:40] if it.get("pattern")]
    return _GENERIC_FORBIDDEN + patterns


def _is_irrelevant_content(raw_text: str, title: str) -> bool:
    """检测抓取内容是否与政策正文无关（如首页、导航栏、404页）。"""
    text = _normalize_text(raw_text)

    # 关键词命中检测
    skip_tokens = {"征求意见稿", "修订草案", "修订", "关于", "实施", "管理", "的", "通知", "办法", "规定", "规则"}
    keywords = [w for w in re.findall(r"[一-鿿]{2,8}", title) if w not in skip_tokens]
    if keywords:
        hits = sum(1 for kw in keywords if kw in text)
        if hits < max(1, len(keywords) // 2):
            return True  # 标题关键词都未命中 → 不相关

    # 内容质量检测：计算有效句子数（15字以上的中文段落）
    # 政策正文应至少有3个有效句子；纯导航页通常都是短片段
    meaningful = [
        seg for seg in re.split(r"[。！？；\n]", text)
        if len(re.findall(r"[一-鿿]", seg)) >= 15
    ]
    if len(meaningful) < 3:
        return True  # 有效句子不足3条 → 视为非政策正文

    return False


def _maybe_llm_refine_fact_sheet(
    fs: PolicyFactSheet,
    article: FetchedArticle,
    client: Any,
    configs: dict[str, Any],
    notes: str = "",
) -> PolicyFactSheet:
    if not client or anthropic is None:
        return fs
    raw_text = article.raw_text or ""
    # 检测是否为无效内容：字数不足，或抓到的是首页/导航页而非政策正文
    is_thin = len(raw_text) < 200 or _is_irrelevant_content(raw_text, article.title)
    try:
        if is_thin:
            # 无原文（或抓到首页噪声）时，让模型基于标题+备注主动推理政策内容
            system_prompt = (
                "你是中国金融监管政策专家，熟悉平安集团各子公司业务。\n"
                "你将收到一条政策的标题、发文机构、文件状态和人工备注。\n"
                "你的任务：推断该政策的2-4个核心制度变化点，以及对平安集团子公司的具体影响和行动建议。\n\n"
                "规则：\n"
                "- core_points 每条15-35字，直接描述具体制度变化（数字、门槛、期限、义务），不写套话\n"
                "- recommended_action 要点名具体子公司和具体动作\n"
                "- allowed_paragraph2_actions 列出2-4个不同力度的动作备选\n"
                "- 如有不确定，可在 quality_notes 中标注'LLM推断，需人工核实'\n"
                "- 只输出JSON，格式：\n"
                "{\"core_points\": [...], \"summary_anchor_sentence\": \"...\", "
                "\"recommended_action\": \"...\", \"allowed_paragraph2_actions\": [...], "
                "\"quality_notes\": [...]}"
            )
            payload = {
                "issuer": article.issuer,
                "title": article.title,
                "status": fs.status,
                "policy_type": fs.policy_type,
                "notes": notes,
                "affected_entities_hint": fs.affected_entities,
                "existing_core_points": fs.core_points,
            }
            model = "claude-sonnet-4-6"
        else:
            system_prompt = (
                configs.get("prompts", {}).get("fact_sheet_refine_prompt")
                or "你是监管政策事实卡润色器。只在不改变事实边界的前提下优化 summary_anchor_sentence、core_points 和 recommended_action。只输出 JSON。"
            )
            payload = {
                "fact_sheet": fs.model_dump(mode="json"),
                "article_text": raw_text[:3000],
                "notes": notes,
            }
            model = "claude-haiku-4-5-20251001"
        resp = client.messages.create(
            model=model,
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        allowed = fs.model_dump(mode="json")
        for key in [
            "summary_anchor_sentence",
            "core_points",
            "recommended_action",
            "allowed_paragraph1_facts",
            "allowed_paragraph2_actions",
        ]:
            if key in data and data[key]:
                allowed[key] = data[key]
        if is_thin:
            notes_list = [n for n in (allowed.get("quality_notes") or []) if n]
            allowed["quality_notes"] = notes_list + ["llm_inferred_from_title_and_notes"]
        return PolicyFactSheet(**allowed)
    except Exception:
        return fs


def extract_fact_sheets(
    fetched: FetchedArticlesOutput,
    input_data: WeeklyPoliciesInput | NormalizedPoliciesOutput,
    client: Any = None,
) -> PolicyFactSheetsOutput:
    configs = _load_configs()
    merged_articles = _merge_grouped_articles(fetched.articles)
    policy_map = {(p.issuer, p.title, p.date): p for p in input_data.policies}

    fact_sheets: list[PolicyFactSheet] = []
    for article in merged_articles:
        # 查找原始输入中的人工备注
        input_item = policy_map.get((article.issuer, article.title, article.date))
        notes_text = (input_item.notes or "").strip() if input_item else ""

        raw_text = article.raw_text or article.title
        # 如果抓到的是无关页面（首页/导航栏），退化为仅标题
        if raw_text and raw_text != article.title and _is_irrelevant_content(raw_text, article.title):
            raw_text = article.title
        policy_type = _detect_policy_type(article.title, raw_text)
        status = _detect_status(article.title, raw_text)
        effective_or_deadline = _extract_effective_or_deadline(raw_text, status)
        core_points = _extract_core_points(article.title, raw_text)
        numbers = _extract_numbers_and_thresholds(raw_text)
        times = _extract_time_requirements(raw_text)

        topic_hints = _match_topic_hints(article.title, raw_text, configs["topic_families"])
        scene_hints = _match_scene_hints(article.title, raw_text, topic_hints, configs["scene_families"])
        professional_rules = _match_professional_company_rules(
            article.title,
            raw_text,
            configs["professional_company_impact_rules"],
        )
        topic_hints = _merge_unique(topic_hints, _rule_values(professional_rules, "topic_hints"))
        scene_hints = _merge_unique(scene_hints, _rule_values(professional_rules, "scene_hints"))
        entities = _match_entities(topic_hints, scene_hints, configs["pingan_entities"], configs["topic_families"], configs["scene_families"])
        rule_entities = _rule_values(professional_rules, "entities")
        if rule_entities:
            # Explicit professional-company rules are curated from business weekly
            # report style, so prefer them over broad topic-family inference.
            include_inferred = any(rule.get("include_inferred_entities") for rule in professional_rules)
            entities = _merge_unique(rule_entities, entities if include_inferred else [])[:6]
        recommended_action, allowed_actions = _select_recommended_action(
            status,
            topic_hints,
            scene_hints,
            entities,
            configs["action_templates"],
            configs["status_action_strength"],
        )
        rule_actions = _rule_values(professional_rules, "actions")
        if rule_actions:
            recommended_action = rule_actions[0]
            allowed_actions = _merge_unique(rule_actions, allowed_actions)
        # notes 作为 P2 动作的优先上下文
        if notes_text and notes_text not in allowed_actions:
            allowed_actions = [notes_text] + allowed_actions

        paragraph2_mode = _decide_paragraph2_mode(status, topic_hints, scene_hints, entities, configs["topic_families"], configs["scene_families"])
        rule_mode = _first_rule_value(professional_rules, "paragraph2_mode")
        if rule_mode:
            paragraph2_mode = rule_mode
        importance, importance_reason = _decide_importance(status, topic_hints, scene_hints, entities, configs["topic_families"])
        rule_importance = _first_rule_value(professional_rules, "importance")
        if rule_importance:
            importance = rule_importance
            importance_reason = _first_rule_value(professional_rules, "importance_reason") or importance_reason
        impact_focus = _merge_unique(_rule_values(professional_rules, "impact_focus"), _pick_focus_phrases(scene_hints, configs["scene_families"]))[:4]

        title_for_sentence = article.title if article.title.startswith("《") else f"《{article.title}》"
        summary_anchor = f"{_cn_date(article.date)}，{article.issuer}{'就' if status == '征求意见稿' else '发布'}{title_for_sentence}，" + (core_points[0].rstrip("。") if core_points else "围绕相关制度安排作出部署。")
        allowed_p1 = _build_allowed_fact_lists(summary_anchor, core_points, effective_or_deadline, numbers, times)
        forbidden = _filter_forbidden_patterns(topic_hints, scene_hints, configs["forbidden_expansion_library"])
        source_ids = article.metadata.get("source_policy_ids", [article.policy_id]) if isinstance(article.metadata, dict) else [article.policy_id]

        fs = PolicyFactSheet(
            policy_id=article.policy_id,
            grouping_key=article.grouping_key,
            issuer=article.issuer,
            title=article.title,
            title_display=article.title_display,
            publish_date=article.date,
            url=article.url,
            policy_type=policy_type,
            status=status,
            effective_or_deadline=effective_or_deadline,
            summary_anchor_sentence=summary_anchor,
            core_points=core_points,
            numbers_and_thresholds=numbers,
            time_requirements=times,
            topic_hints=topic_hints,
            scene_hints=scene_hints,
            affected_entities=entities,
            recommended_action=recommended_action,
            paragraph2_mode=paragraph2_mode,
            impact_focus=impact_focus,
            importance=importance,
            importance_reason=importance_reason,
            allowed_paragraph1_facts=allowed_p1,
            allowed_paragraph2_entities=entities,
            allowed_paragraph2_actions=allowed_actions,
            forbidden_expansions=forbidden,
            quality_notes=["title_only fallback" if article.title_only_fallback else ""],
            source_excerpt=raw_text[:500],
            source_policy_ids=source_ids,
        )
        # 无论原文是否充足，只要有 client 就运行 LLM 提炼
        fs = _maybe_llm_refine_fact_sheet(fs, article, client, configs, notes=notes_text)
        fact_sheets.append(fs)

    fact_sheets.sort(key=lambda x: x.publish_date, reverse=True)
    return PolicyFactSheetsOutput(report_date=fetched.report_date, report_type="监管政策周报", fact_sheets=fact_sheets)
