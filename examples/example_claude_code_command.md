# example_claude_code_command.md

> 本文件用于演示在 Claude Code 中如何把整条链路串起来跑。Phase 3+ 实装后命令即可直接复制。

---

## 一、跑主链路（生成）

```bash
# 仓库根目录
python -m src.main generate \
  --input ./examples/example_weekly_policies.json \
  --output-dir ./output
```

期望执行步骤（在 `output/run_log.md` 中可见）：

1. `normalize_policies` — 规范化输入清单（去重、include 过滤、url 校验）
2. `fetch_articles` — 抓取每条政策的官网正文（retry / timeout / fallback）
3. `extract_facts` — 抽取正文 + 识别 grouped pair + 构建事实卡
4. `retrieve_examples` — 从 `config/few_shot_library.json` 检索每条最相近 few-shot
5. `generate_report_draft` — LLM 一次性生成整期周报草稿
6. `validate_drafts` — 跑硬校验
7. `rewrite_failed_items` — 失败项二次重写
8. `render_docx` — Word 渲染

期望产物（按顺序生成）：

```
output/normalized_policies.json
output/fetched_articles.json
output/policy_fact_sheets.json
output/retrieved_examples.json
output/policy_card_drafts.json
output/validation_report.json
output/final_report_content.json
output/监管政策周报_2026.04.19.docx
output/run_log.md
```

---

## 二、解析人工最终终稿

```bash
python -m src.main parse-final \
  --input ./examples/example_final_weekly_report.md \
  --output-dir ./output
```

LLM 解析 `example_final_weekly_report.md` 的每一条，落到与 `policy_card_drafts.json` 字段对齐的结构：

```
output/final_report_parsed.json
```

---

## 三、自进化：终稿 → few-shot / forbidden expansion

```bash
python -m src.main learn \
  --draft ./output/policy_card_drafts.json \
  --final ./output/final_report_parsed.json \
  --output-dir ./output
```

期望执行步骤：

1. `diff_draft_vs_final` — 逐条比对草稿与人工终稿（结构 / 主体 / 动作 / 句式 / 删改）
2. `extract_few_shot_candidates` — 终稿优秀范本 → few-shot 候选
3. `extract_forbidden_expansion_candidates` — 草稿被人工删掉的整段 → forbidden 候选
4. `update_few_shots` — 满足条件的候选直接追加进 `config/few_shot_library.json`
5. `update_forbidden_expansions` — 满足条件的候选直接追加进 `config/forbidden_expansion_library.json`

期望产物：

```
output/draft_final_diff.json
output/learning_update_report.json
config/few_shot_library.json            # 已追加更新
config/forbidden_expansion_library.json # 已追加更新
```

---

## 四、配置确认

```bash
python -m src.main upgrade --output-dir ./output
```

轻量版仅做"配置已更新"确认与日志写入，不做正式规则升格引擎。

---

## 五、整体一键流程（建议）

```bash
# 1. 生成本期 Word
python -m src.main generate \
  --input ./inbox/weekly_policies_$(date +%Y%m%d).json \
  --output-dir ./output

# 2. 编辑出最终终稿（人工）
#    保存到 ./inbox/final_$(date +%Y%m%d).md

# 3. 解析终稿
python -m src.main parse-final \
  --input ./inbox/final_$(date +%Y%m%d).md \
  --output-dir ./output

# 4. 跑学习
python -m src.main learn \
  --draft ./output/policy_card_drafts.json \
  --final ./output/final_report_parsed.json \
  --output-dir ./output

# 5. 升级确认
python -m src.main upgrade --output-dir ./output
```

---

## 六、Claude Code 中的最小提示词样板

> 直接贴给 Claude Code，用 example 输入跑一次端到端：

```
请在仓库根目录执行：
python -m src.main generate --input ./examples/example_weekly_policies.json --output-dir ./output

跑完后请：
1. 列出 output/ 下所有产物
2. 打开 output/监管政策周报_2026.04.19.docx 检查格式
3. 对照 QUALITY_CHECKLIST.md 做一遍核查，并给出未通过项
```
