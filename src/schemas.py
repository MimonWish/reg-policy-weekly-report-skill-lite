from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =========================
# Common literals
# =========================

ReportType = Literal["监管政策周报"]

Paragraph2Mode = Literal[
    "direct",
    "scene_direct_related",
    "benchmark",
    "opportunity",
    "none",
]

Importance = Literal["major", "minor"]

PolicyStatus = Literal[
    "正式实施",
    "征求意见稿",
    "修订草案",
    "计划",
    "专项行动",
    "对标适用",
    "标题级分析",
]

PolicyType = Literal[
    "通知",
    "办法",
    "条例",
    "决定",
    "意见",
    "公告",
    "实施规定",
    "规则",
    "方案",
    "解释",
    "其他",
]

ValidationErrorCode = Literal[
    "unsupported_fact_in_p1",
    "unsupported_number_or_time",
    "forbidden_expansion_hit",
    "entity_not_allowed_in_p2",
    "action_not_allowed_in_p2",
    "p2_repeats_p1",
    "grouped_pair_not_merged",
    "benchmark_written_as_two_paragraphs",
    "opportunity_written_as_remediation",
    "invalid_paragraph2_mode",
    "missing_required_fact",
    "title_mismatch",
]

FetchStatus = Literal[
    "success",
    "title_only",
    "failed",
]


# =========================
# Base model
# =========================

class StrictBaseModel(BaseModel):
    """Base model for all schemas in the lightweight weekly report skill."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        str_strip_whitespace=True,
    )


# =========================
# Input layer
# =========================

class WeeklyPolicyItem(StrictBaseModel):
    """
    Single policy item from weekly input JSON.

    Notes:
    - title should be the formal document name only, without issuer prefix
    - url should preferably be an official website link
    """

    date: str = Field(..., description="官网发布日期，格式 YYYY-MM-DD")
    issuer: str = Field(..., description="正式发文机构名称")
    title: str = Field(..., description="文件正式全称，不带机构前缀")
    url: str = Field(..., description="官网原文链接")
    include: bool = Field(..., description="是否纳入本期周报")
    notes: str = Field(default="", description="人工备注，可为空字符串")
    group_internal_status: str = Field(default="无", description="集团已做工作状态，枚举见 business_rules.editor_notes_rules")
    group_internal_status_team: str = Field(default="", description="做工作的集团团队，枚举见 business_rules.editor_notes_rules.allowed_subjects")


class WeeklyPoliciesInput(StrictBaseModel):
    """Top-level input payload for weekly report generation."""

    report_date: str = Field(..., description="周报日期，格式 YYYY.MM.DD")
    report_type: ReportType = Field(default="监管政策周报", description="固定值")
    policies: List[WeeklyPolicyItem] = Field(default_factory=list, description="本周政策清单")

    @field_validator("report_date")
    @classmethod
    def validate_report_date(cls, v: str) -> str:
        if len(v.split(".")) != 3:
            raise ValueError("report_date 必须为 YYYY.MM.DD 格式")
        return v


class NormalizedPoliciesOutput(StrictBaseModel):
    """Normalized policy list after filtering, de-duplication and sorting."""

    report_date: str
    report_type: ReportType = "监管政策周报"
    policies: List[WeeklyPolicyItem] = Field(default_factory=list)


# =========================
# Fetch / extract layer
# =========================

class FetchedArticle(StrictBaseModel):
    """
    Raw fetched result for a policy URL.

    If fetch failed, the pipeline may still continue in `title_only` mode.
    """

    policy_id: str = Field(..., description="系统生成的政策ID")
    grouping_key: Optional[str] = Field(default=None, description="分组键，同组政策共享")
    issuer: str = Field(..., description="发文机构")
    title: str = Field(..., description="输入标题")
    title_display: str = Field(..., description="最终展示标题，通常为 机构《文件名》")
    date: str = Field(..., description="输入中的发布日期")
    url: str = Field(..., description="原文链接")
    fetch_status: FetchStatus = Field(..., description="抓取状态")
    fetch_error: str = Field(default="", description="抓取失败原因")
    raw_text: str = Field(default="", description="抓取到的正文文本")
    raw_html: str = Field(default="", description="可选，抓取到的HTML")
    official_link_warning: str = Field(default="", description="非官网或可疑链接提示")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="抓取元数据")
    title_only_fallback: bool = Field(default=False, description="是否仅基于标题继续后续流程")


class FetchedArticlesOutput(StrictBaseModel):
    """Container for fetched article results."""

    report_date: str
    report_type: ReportType = "监管政策周报"
    articles: List[FetchedArticle] = Field(default_factory=list)


class NumberThreshold(StrictBaseModel):
    """Numeric threshold or percentage extracted from policy text."""

    text: str = Field(..., description="原始数字或阈值表达")
    value: Optional[str] = Field(default=None, description="可解析后的值")
    unit: Optional[str] = Field(default=None, description="单位，如 %, 年, 月")
    context: str = Field(default="", description="该数字在政策中的上下文说明")


class TimeRequirement(StrictBaseModel):
    """Effective time, deadline or transition arrangement extracted from policy text."""

    text: str = Field(..., description="原始时间要求表达")
    normalized_date: Optional[str] = Field(default=None, description="标准化日期，如 YYYY-MM-DD")
    category: Literal["生效时间", "截止时间", "过渡期", "实施阶段", "其他"] = Field(
        default="其他",
        description="时间要求类别",
    )
    context: str = Field(default="", description="该时间要求在政策中的上下文说明")


class PolicyFactSheet(StrictBaseModel):
    """
    Core fact sheet used by generator and validator.

    This is the single source of truth for:
    - paragraph1 allowed facts
    - paragraph2 allowed entities/actions
    - paragraph2 mode
    """

    # identity
    policy_id: str = Field(..., description="系统生成的政策ID")
    grouping_key: Optional[str] = Field(default=None, description="政策分组键")
    issuer: str = Field(..., description="发文机构")
    title: str = Field(..., description="文件正式全称")
    title_display: str = Field(..., description="展示标题，通常为 机构《文件名》")
    publish_date: str = Field(..., description="发布日期，格式 YYYY-MM-DD")
    url: str = Field(..., description="原文链接")

    # classification
    policy_type: PolicyType = Field(default="其他", description="文件类型")
    status: PolicyStatus = Field(..., description="文件状态")
    effective_or_deadline: str = Field(default="", description="生效时间、截止时间或当前阶段说明")

    # paragraph1 fact source
    summary_anchor_sentence: str = Field(
        default="",
        description="用于 paragraph1 起草的锚定摘要句，可由 extractor 或 LLM 生成",
    )
    core_points: List[str] = Field(default_factory=list, description="核心制度变化列表")
    numbers_and_thresholds: List[NumberThreshold] = Field(default_factory=list, description="数字或阈值信息")
    time_requirements: List[TimeRequirement] = Field(default_factory=list, description="时间要求信息")

    # topic / scene hints
    topic_hints: List[str] = Field(default_factory=list, description="主题提示，用于 few-shot 检索和生成")
    scene_hints: List[str] = Field(default_factory=list, description="场景提示，用于 second paragraph 落点")

    # paragraph2 source
    affected_entities: List[str] = Field(default_factory=list, description="受影响主体候选")
    recommended_action: str = Field(default="", description="推荐主动作")
    paragraph2_mode: Paragraph2Mode = Field(default="none", description="第二段写作模式")
    impact_focus: List[str] = Field(default_factory=list, description="业务落点短语候选")

    # importance
    importance: Importance = Field(default="minor", description="重点程度")
    importance_reason: str = Field(default="", description="重点/非重点原因")

    # validator controls
    allowed_paragraph1_facts: List[str] = Field(
        default_factory=list,
        description="paragraph1 允许使用的事实句或事实点",
    )
    allowed_paragraph2_entities: List[str] = Field(
        default_factory=list,
        description="paragraph2 允许使用的主体",
    )
    allowed_paragraph2_actions: List[str] = Field(
        default_factory=list,
        description="paragraph2 允许使用的动作",
    )
    forbidden_expansions: List[str] = Field(
        default_factory=list,
        description="该条政策禁止扩写的词或短语",
    )

    # debugging / quality
    quality_notes: List[str] = Field(default_factory=list, description="质量备注")
    source_excerpt: str = Field(default="", description="原文摘要或关键片段，便于追溯")
    source_policy_ids: List[str] = Field(
        default_factory=list,
        description="若为 grouped pair，可记录同组 policy_id 列表",
    )

    @field_validator("affected_entities", "allowed_paragraph2_entities", "allowed_paragraph2_actions")
    @classmethod
    def dedupe_str_list(cls, v: List[str]) -> List[str]:
        seen: List[str] = []
        for item in v:
            if item and item not in seen:
                seen.append(item)
        return seen

    @field_validator("core_points", "topic_hints", "scene_hints", "impact_focus", "forbidden_expansions")
    @classmethod
    def normalize_str_list(cls, v: List[str]) -> List[str]:
        return [item for item in v if item]


class PolicyFactSheetsOutput(StrictBaseModel):
    """Container for fact sheets."""

    report_date: str
    report_type: ReportType = "监管政策周报"
    fact_sheets: List[PolicyFactSheet] = Field(default_factory=list)


# =========================
# Few-shot retrieval layer
# =========================

class RetrievedExample(StrictBaseModel):
    """Few-shot example retrieved for a specific fact sheet."""

    example_id: str
    example_type: Literal[
        "direct_major",
        "scene_direct_related",
        "benchmark_only",
        "opportunity_watch",
        "grouped_policy_pair",
    ]
    trigger_features: Dict[str, Any] = Field(default_factory=dict)
    paragraph1: str = ""
    paragraph2: str = ""
    notes: str = ""


class RetrievedExamplesOutput(StrictBaseModel):
    """Container for retrieved few-shot examples."""

    report_date: str
    report_type: ReportType = "监管政策周报"
    examples_by_policy_id: Dict[str, List[RetrievedExample]] = Field(default_factory=dict)


# =========================
# Generation layer
# =========================

class PolicyCardDraft(StrictBaseModel):
    """
    Single policy card draft produced by generator.

    This is the primary intermediate output before validation.
    """

    policy_id: str = Field(..., description="来源 fact sheet 的 policy_id")
    grouping_key: Optional[str] = Field(default=None, description="分组键")
    title: str = Field(..., description="展示标题")
    url: str = Field(..., description="原文链接")
    paragraph1: str = Field(default="", description="政策摘要段")
    paragraph2: str = Field(default="", description="平安影响段")
    paragraph2_mode: Paragraph2Mode = Field(default="none", description="第二段模式")
    importance: Importance = Field(default="minor", description="重点程度")
    editor_notes: str = Field(default="", description="生成器或重写器备注")
    paragraph1_red_bold: List[str] = Field(default_factory=list, description="P1 中需要红色加粗的精确片段")
    paragraph1_black_bold: List[str] = Field(default_factory=list, description="P1 中需要黑色加粗的精确片段")
    paragraph2_red_bold: List[str] = Field(default_factory=list, description="P2 中需要红色加粗的精确片段")
    paragraph2_black_bold: List[str] = Field(default_factory=list, description="P2 中需要黑色加粗的精确片段")


class PolicyCardDraftsOutput(StrictBaseModel):
    """Container for all generated policy card drafts."""

    report_title: str = "监管政策周报"
    report_date: str
    items: List[PolicyCardDraft] = Field(default_factory=list)


class FinalReportItem(StrictBaseModel):
    """Single item in final report content."""

    title: str = Field(..., description="展示标题")
    url: str = Field(..., description="原文链接")
    paragraph1: str = Field(default="", description="政策摘要段")
    paragraph2: str = Field(default="", description="平安影响段")
    paragraph2_mode: Paragraph2Mode = Field(default="none", description="第二段模式")
    importance: Importance = Field(default="minor", description="重点程度")
    editor_notes: str = Field(default="", description="最终编辑备注")
    paragraph1_red_bold: List[str] = Field(default_factory=list, description="P1 中需要红色加粗的精确片段")
    paragraph1_black_bold: List[str] = Field(default_factory=list, description="P1 中需要黑色加粗的精确片段")
    paragraph2_red_bold: List[str] = Field(default_factory=list, description="P2 中需要红色加粗的精确片段")
    paragraph2_black_bold: List[str] = Field(default_factory=list, description="P2 中需要黑色加粗的精确片段")


class FinalReportContent(StrictBaseModel):
    """Final structured report before docx rendering."""

    report_title: str = Field(default="监管政策周报", description="报告标题")
    report_date: str = Field(..., description="报告日期，格式 YYYY.MM.DD")
    items: List[FinalReportItem] = Field(default_factory=list, description="正文条目列表")


# =========================
# Validation layer
# =========================

class ValidationError(StrictBaseModel):
    """Hard validation error for a single report item."""

    code: ValidationErrorCode = Field(..., description="错误码")
    message: str = Field(..., description="错误说明")
    evidence: str = Field(default="", description="用于定位问题的证据")
    suggested_fix: str = Field(default="", description="建议修复方式")


class ValidationWarning(StrictBaseModel):
    """Soft warning for a single report item."""

    code: str = Field(..., description="警告码")
    message: str = Field(..., description="警告说明")
    evidence: str = Field(default="", description="辅助证据")


class ValidationItem(StrictBaseModel):
    """Validation result for one policy card."""

    policy_id: str = Field(..., description="对应 fact sheet 的 policy_id")
    title: str = Field(..., description="展示标题")
    passed: bool = Field(..., description="是否通过硬校验")
    errors: List[ValidationError] = Field(default_factory=list, description="硬校验错误")
    warnings: List[ValidationWarning] = Field(default_factory=list, description="软警告")
    rewrite_required: bool = Field(default=False, description="是否需要重写")


class ValidationReport(StrictBaseModel):
    """Whole-report validation result."""

    report_title: str = Field(default="监管政策周报")
    report_date: str
    passed: bool = Field(..., description="整期是否通过")
    items: List[ValidationItem] = Field(default_factory=list, description="逐条校验结果")
    summary: str = Field(default="", description="总体说明")


# =========================
# Parse-final / learning layer
# =========================

class FinalReportParsedItem(StrictBaseModel):
    """
    Structured item parsed from manually edited final report.

    Used for learning diff.
    """

    title: str = Field(..., description="展示标题")
    paragraph1: str = Field(default="", description="政策摘要段")
    paragraph2: str = Field(default="", description="平安影响段")
    paragraph2_mode: Paragraph2Mode = Field(default="none", description="第二段模式")
    entities: List[str] = Field(default_factory=list, description="从最终终稿中提取的主体")
    action: str = Field(default="", description="从最终终稿中提取的主动作")
    focus_phrase: str = Field(default="", description="从最终终稿中提取的业务落点短语")


class FinalReportParsed(StrictBaseModel):
    """Parsed structure of the manually edited final report."""

    report_title: str = Field(default="监管政策周报")
    report_date: str = Field(..., description="周报日期")
    items: List[FinalReportParsedItem] = Field(default_factory=list)


class DraftFinalDiffItem(StrictBaseModel):
    """Diff result for one item between system draft and manual final report."""

    title: str = Field(..., description="条目标题")
    draft_paragraph1: str = Field(default="", description="系统草稿第一段")
    draft_paragraph2: str = Field(default="", description="系统草稿第二段")
    final_paragraph1: str = Field(default="", description="人工终稿第一段")
    final_paragraph2: str = Field(default="", description="人工终稿第二段")
    paragraph2_mode: Paragraph2Mode = Field(default="none", description="第二段模式")
    entity_diff: str = Field(default="", description="主体差异摘要")
    action_diff: str = Field(default="", description="动作差异摘要")
    focus_phrase_diff: str = Field(default="", description="落点短语差异摘要")
    removed_errors: List[str] = Field(default_factory=list, description="草稿中被终稿删除的错误内容")
    fact_sheet: Optional[PolicyFactSheet] = Field(default=None, description="关联事实卡")


class DraftFinalDiffOutput(StrictBaseModel):
    """Container for draft vs final diff results."""

    report_date: str
    items: List[DraftFinalDiffItem] = Field(default_factory=list)


class LearningUpdateReport(StrictBaseModel):
    """Summary of lightweight self-improvement update results."""

    report_date: str = Field(..., description="本次学习对应的周报日期")
    few_shot_added_count: int = Field(default=0, description="新增 few-shot 数量")
    forbidden_expansion_added_count: int = Field(default=0, description="新增 forbidden expansion 数量")
    few_shot_added_ids: List[str] = Field(default_factory=list, description="新增 few-shot ID")
    forbidden_expansion_added_ids: List[str] = Field(
        default_factory=list,
        description="新增 forbidden expansion ID",
    )
    notes: List[str] = Field(default_factory=list, description="学习更新说明")


# =========================
# Convenience output layer
# =========================

class RunLogItem(StrictBaseModel):
    """Optional structured log entry."""

    level: Literal["INFO", "WARNING", "ERROR"] = "INFO"
    stage: str = Field(..., description="所属阶段，如 fetch/extract/generate/validate/render/learn")
    message: str = Field(..., description="日志内容")


class RunLogOutput(StrictBaseModel):
    """Structured run log, optional alongside markdown log."""

    report_date: str
    items: List[RunLogItem] = Field(default_factory=list)
