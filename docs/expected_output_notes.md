# expected_output_notes.md

> 配合 `example_weekly_policies.json` 使用。说明跑完 `generate` 后每个产物**应当长什么样**，以及关键检查点。

---

## A. normalized_policies.json

- 8 条原始 → 7 条入选（剔除 `include=false` 的"信息披露指引"）
- 每条包含规范化后的 `policy_id`, `issuer`, `title`, `title_display`, `url`, `notes`, `is_official_url`
- "互联网贷款办法 + 实施公告" 两条共享同一个 `grouping_key`（如 `nfra_internet_loan_2026`）

## B. fetched_articles.json

- 7 条均产出 `fetch_status`
- 抓取成功的 `full_text` 不为空
- 抓取失败的需写明 `fetch_error`，但不影响后续流程
- 公告类（短文）允许只抓到不到 1KB

## C. policy_fact_sheets.json

7 条事实卡，期望要点：

| # | 文件 | paragraph2_mode | importance | 关键 fact |
|---|------|-----------------|-----------|----------|
| 1 | 互联网贷款办法 + 实施公告（grouped） | direct | high | 单户限额 / 集中度 / 过渡期 12 个月 |
| 2 | 期货公司监督管理办法 | direct | high | 业务范围扩展 / 净资本 / 风险子并表 |
| 3 | 备付金存管办法（修订） | direct | high | 正式实施 2026-07-01 / 场景分账户 |
| 4 | 偿二代 II 期通报 | benchmark | mid | 行业均值 / 平安偿付能力对标 |
| 5 | 私募证券基金运作指引 | opportunity | low | 杠杆 / 集中度 / 信披频率 |
| 6 | 财产保险销售从业人员管理办法 | direct | high | 持证 / 培训 / 回访留痕 / 佣金 |
| 7 | 跨境融资便利化通知 | opportunity | low | 宏观审慎调节参数 |

每条事实卡必须填齐：
- `allowed_paragraph1_facts`：P1 允许引用的事实清单
- `allowed_paragraph2_entities`：P2 允许使用的平安主体
- `allowed_paragraph2_actions`：P2 允许使用的动作短语
- `forbidden_expansions`：本条专属的禁止延伸点

## D. retrieved_examples.json

每条 fact sheet 至少检索到 1 条 few-shot：
- 互联网贷款办法 → `direct_major` + `grouped_policy_pair`
- 期货公司办法 → `direct_major`
- 备付金办法（正式实施）→ `direct_major`（带"正式实施"状态强调）
- 偿二代通报 → `benchmark_only`
- 私募基金指引 → `opportunity_watch`
- 财产保险销售办法 → `direct_major`
- 跨境融资 → `opportunity_watch`

## E. policy_card_drafts.json

- `items` 数量 = 7（grouped pair 已合并为 1 条）
- 每条包含 `paragraph1`, `paragraph2`, `paragraph2_mode`, `importance`, `editor_notes`
- `benchmark` 类的 `paragraph2` 应为空字符串或仅一句对标
- `opportunity` 类的 `paragraph2` 不得包含整改动作

## F. validation_report.json

期望全部 pass。常见失败项（如出现需重写）：

- `fact_used_outside_sheet`：用了 fact sheet 之外的数字 / 阈值 / 日期
- `entity_outside_scope`：P2 出现 fact sheet 之外的平安主体
- `action_outside_scope`：P2 出现 fact sheet 之外的动作
- `forbidden_expansion_hit`：命中 `forbidden_expansion_library.json`
- `grouped_pair_split`：grouped pair 没合并
- `benchmark_two_paragraphs`：benchmark 误写两段
- `opportunity_writes_remediation`：opportunity 误写整改
- `p1_p2_high_overlap`：P1 与 P2 高度重复

## G. final_report_content.json

结构：

```json
{
  "report_title": "监管政策周报",
  "report_date": "2026.04.19",
  "items": [
    {
      "title": "...",
      "url": "...",
      "paragraph1": "...",
      "paragraph2": "...",
      "paragraph2_mode": "direct",
      "importance": "high",
      "editor_notes": ""
    }
  ]
}
```

## H. 监管政策周报_2026.04.19.docx

期望渲染：
- 标题：`监管政策周报 #2026.04.19`
- 每条条目：编号 + 标题 + 来源行（机构 · 日期 · 原文链接）+ P1（必有）+ P2（按 mode 决定有无）
- 红色高亮范围受控：状态词（"征求意见稿""正式实施"）、关键动作短语（"应立即……""应优先……""应开展……"）、关键制度变化短语
- 不得出现整段泛红
- 文件名严格为 `监管政策周报_2026.04.19.docx`

## I. run_log.md

- 各阶段开始/结束时间戳
- LLM 调用次数与 token 估算（如能拿到）
- 抓取成功 / 失败统计
- 校验 pass / fail 统计与重写次数

---

## 与人工最终终稿（example_final_weekly_report.md）的对比要点

跑完 `parse-final` + `learn` 后，期望从 diff 中提取出：

- **few-shot 候选**：终稿"互联网贷款办法 + 实施公告"合并写法、备付金办法"正式实施 + 场景分账户"写法（这两条非常具有教学价值）
- **forbidden 候选**：草稿如果出现"行业整体进入新一轮规范期"等空话句式 → 应进入 forbidden expansion

`learning_update_report.json` 应明确写出本次新增的 few-shot id 与 forbidden id。
