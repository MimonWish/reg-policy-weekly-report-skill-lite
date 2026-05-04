# CLAUDE_CODE_PROMPT.md

> 给 Claude Code 的最小运行说明。在 Claude Code 中打开本仓库后，直接把下面任意一段贴给 Claude Code 即可启动。

---

## 启动前的硬约束（必须告诉 Claude Code）

1. **代码文件总数**：`src/` 下严格 **8 个 .py 文件**，分别是
   `main.py / schemas.py / fetcher.py / extractor.py / generator.py / validator.py / renderer.py / learning.py`。
   不允许新增 `src/impact/`、`src/generation/`、`src/validators/`、`src/learning/` 等子目录。
2. **CLI 命令**：仅 4 个 → `generate / parse-final / learn / upgrade`。`main.py` 内自实现 CLI，不再拆 `cli.py`。
3. **生成主体**：交给 LLM 一次性产出整期周报草稿，**禁止**逐条拼句、禁止从 `full_text` fallback 拼句。
4. **校验主体**：只做高价值硬校验（fact 引用 / 主体范围 / 动作范围 / forbidden 命中 / grouped 合并 / benchmark 误两段 / opportunity 误整改 / P1-P2 重复），**禁止**做评分引擎。
5. **自进化范围**：仅 `few-shot 自动补充` + `forbidden expansion 自动补充` 两件事。
6. **写作口径**：站在平安集团合规专家视角，服务对象是集团高管，输出"谁受影响 / 怎么改 / 先做什么"。

---

## 命令清单（贴给 Claude Code 用）

### A. 跑主链路，出 Word 周报

```bash
python -m src.main generate \
  --input ./examples/example_weekly_policies.json \
  --output-dir ./output
```

期望产物：
- `output/normalized_policies.json`
- `output/fetched_articles.json`
- `output/policy_fact_sheets.json`
- `output/retrieved_examples.json`
- `output/policy_card_drafts.json`
- `output/final_report_content.json`
- `output/validation_report.json`
- `output/监管政策周报_YYYY.MM.DD.docx`
- `output/run_log.md`

### B. 解析人工最终终稿

```bash
python -m src.main parse-final \
  --input ./examples/example_final_weekly_report.md \
  --output-dir ./output
```

期望产物：`output/final_report_parsed.json`

### C. 自进化：终稿差异 → few-shot / forbidden expansion

```bash
python -m src.main learn \
  --draft ./output/policy_card_drafts.json \
  --final ./output/final_report_parsed.json \
  --output-dir ./output
```

期望产物：
- `output/draft_final_diff.json`
- `output/learning_update_report.json`
- 更新后的 `config/few_shot_library.json`
- 更新后的 `config/forbidden_expansion_library.json`

### D. 升级确认（轻量版仅做配置已更新确认）

```bash
python -m src.main upgrade --output-dir ./output
```

---

## 阶段执行（Claude Code 必须按 Phase 顺序）

> 一次只做一个 Phase，做完停下来等确认。

- **Phase 1**：工程骨架（已完成 ✅）
- **Phase 2**：配置与 schema → `config/*`、`src/schemas.py`、`docs/`
- **Phase 3**：主链路代码 → `fetcher / extractor / generator / validator / renderer / main`，要求 `generate` 命令可跑通并出 docx
- **Phase 4**：学习闭环 → `learning.py` 与 `parse-final / learn / upgrade` 命令
- **Phase 5**：测试与联调 → `tests/*`，`example_weekly_policies.json` 跑通主链路

每个 Phase 完成后必须输出：
1. 新建/修改的文件清单
2. 每个文件的核心职责
3. 下一阶段的入口命令

---

## 给 Claude Code 的开场提示词（直接贴用）

```
我在仓库 reg-policy-weekly-report-skill-lite 中，已完成 Phase 1。

请按 SKILL.md 第 9 节的路线图，执行 Phase 2：
1. 创建 config/prompts.yaml（包含 weekly_report_generation_prompt、report_rewrite_prompt、final_report_parser_prompt、few_shot_update_prompt、forbidden_expansion_update_prompt 五个 prompt，使用中文）
2. 创建 config/business_rules.yaml（角色定位、输出目标、重点/非重点判断标准、paragraph_count_rules、paragraph2_mode_rules、entity_scope_rules、status_action_rules、benchmark_rules、opportunity_rules、grouped_policy_rules、validation_hard_rules）
3. 创建 config/style.yaml
4. 创建 config/few_shot_library.json（覆盖 direct_major / scene_direct_related / benchmark_only / opportunity_watch / grouped_policy_pair 五类首版样例）
5. 创建 config/forbidden_expansion_library.json（v1 空骨架 + 1-2 条样例）
6. 创建 config/impact/* 五个 JSON
7. 创建 src/schemas.py，集中定义全部 Pydantic schema（不拆多个 schema 文件）
8. 创建 docs/architecture.md（说明轻量版架构选型）和 docs/schemas.md（说明输入输出 schema）

硬约束：
- 不得创建 src/impact/、src/generation/、src/validators/、src/learning/ 等子目录
- 不得新增 .py 文件（schemas.py 之外）
- 全部 schema 集中在 src/schemas.py 中

完成后，请输出新建文件清单 + 用途说明 + 进入 Phase 3 的入口命令。
```
