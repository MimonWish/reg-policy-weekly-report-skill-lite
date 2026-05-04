# 受控自进化流程

本流程用于每周系统稿生成后，对照业务专家最终版周报进行落差分析，并按置信度执行自进化。用户不需要手动运行 Python 命令；当用户上传专家稿并要求“落差分析 / 自我进化 / 学习专家口径”时，Codex 直接按本流程触发。

## 输入

- 系统稿：本 Skill 生成的 `.docx`，或由 `final_report_content.json` 渲染得到的 Word。
- 专家稿：业务专家最终确认的 `.docx`。
- 历史专家稿：可选，用于判断本周差异是否是稳定模式。

## Skill 触发方式

用户自然语言触发即可，例如：

- “对比这周系统稿和专家稿，做落差分析并自进化。”
- “基于这份业务专家终稿优化 Skill。”
- “把高置信规则自动激活，中低置信规则给我确认。”

Codex 可在内部调用确定性辅助脚本抽取 Word 结构和差异，但不要求用户手动执行命令。

输出：

- `gap_analysis.json`：结构化差异，包括条目匹配、P1/P2 相似度、P2 模式变化、主体变化和高亮数量变化。
- `gap_analysis.md`：面向人的落差分析底稿。
- `learning_proposals.md`：待用户确认的学习建议。
- `evolution_patch_plan.md`：确认后建议修改的文件范围。
- `candidate_rules.json`：候选规则，包含 `confidence`、`confidence_score` 和 `status`。

## 置信度与自动激活

- `high`：候选规则自动写入 `config/evolution_rules.json`，状态为 `active`。
- `medium`：保留为 `pending_confirmation`，需要用户确认后再写入结构性规则。
- `low`：保留为 `pending_confirmation`，默认只作为观察项。

高置信自动激活只适用于抽象规则，不适用于专家稿正文、专家稿整段高亮或单周临时取舍。
每条 active 规则必须带生命周期字段：`scope`、`policy_family`、`evidence_count`、`support_count`、`source_reports`、`review_after`、`expires_at` 和 `deactivation_condition`。超过 `review_after` 的规则下次使用前需复核；超过 `expires_at` 或触发降级条件时，不得继续作为强约束。

## 分析维度

- 条目取舍：是否新增、删除、合并或拆分。
- P1：是否遗漏发布时间、文号、适用范围、生效期、比例阈值、监管定位。
- P2：是否遗漏平安专业公司、具体产品线、业务链路、动作强度。
- `paragraph2_mode`：是否应从 `none/benchmark/opportunity` 调整为 `direct/scene_direct_related`，或反向收敛。
- 高亮：红色是否命中监管硬事实，黑色是否命中平安主体或内部工作标记。
- 样式：标题、日期、条目标题、正文样式是否符合业务版式。
- 反过拟合：是否与历史专家稿出现正文段落级复用。

## 学习建议格式

每条建议必须抽象为：

```json
{
  "learning_type": "impact_mapping | highlight_rule | p2_mode_rule | style_rule | selection_rule | forbidden_pattern",
  "trigger": "什么政策、场景或业务特征触发",
  "system_gap": "系统稿哪里弱",
  "expert_pattern": "专家体现出的判断模式，不粘贴专家原句",
  "proposed_change": "建议更新到哪个文件或规则",
  "risk": "过拟合或误用风险",
  "scope": "规则适用范围",
  "policy_family": "政策类型",
  "review_after": "复核日期",
  "expires_at": "失效日期"
}
```

## 禁止事项

- 不把专家稿 P1/P2 原文直接写入 few-shot。
- 不把单周专家选择直接升级为普遍规则。
- 不在用户确认前修改 `SKILL.md`、`references/` 历史模式文档或核心配置；高置信候选仅允许写入 `config/evolution_rules.json` 的 active registry。
- 不用专家稿覆盖系统稿后宣称“自进化完成”。

## 确认后更新优先级

0. `config/evolution_rules.json`：高置信候选自动 active。
1. `references/HISTORICAL_BUSINESS_REPORT_PATTERNS.md`：稳定写法模式。
2. `config/impact/professional_company_impact_rules.json`：专业公司和业务链路映射。
3. `references/QUALITY_CHECKLIST.md`：新增质检项。
4. `SKILL.md`：核心流程或硬边界。
5. `src/renderer.py`：仅限 Word 样式或高亮渲染。

## 更新后验证

Codex 内部执行测试和反过拟合检查，并在最终回复中说明结果。若反过拟合命中正文高相似段，先重写规则表达或本期正文，再交付。
