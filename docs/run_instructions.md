# run_instructions.md

> 安装、运行、命令、示例、常见问题。

---

## 1. 环境

- Python ≥ 3.10
- 可访问 LLM（默认调用 Anthropic API；Phase 3 实现时通过环境变量配置）

---

## 2. 安装

```bash
git clone <repo-url> reg-policy-weekly-report-skill-lite
cd reg-policy-weekly-report-skill-lite
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

环境变量（Phase 3 实装后必填）：

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# 可选：模型选择
export REG_POLICY_LLM_MODEL="claude-opus-4-7"
```

---

## 3. 命令总览（仅 4 个）

| 命令 | 作用 | 主要产物 |
|------|------|---------|
| `generate`     | 主生成链路：JSON → Word | `监管政策周报_YYYY.MM.DD.docx` |
| `parse-final`  | 解析人工最终终稿（md → 结构化 JSON） | `final_report_parsed.json` |
| `learn`        | 终稿差异 → 更新 few-shot / forbidden expansion | `learning_update_report.json` |
| `upgrade`      | 配置已更新确认（轻量版仅做确认，不做引擎升级） | `run_log.md` 写入升级记录 |

---

## 4. 主链路：从政策清单到 Word 周报

### Step 1. 准备本周政策清单

参考 `examples/example_weekly_policies.json`，编辑或粘贴本周的清单：

```json
{
  "report_date": "2026.04.19",
  "report_type": "监管政策周报",
  "policies": [
    {
      "date": "2026-04-17",
      "issuer": "中国证监会",
      "title": "期货公司监督管理办法（征求意见稿）",
      "url": "https://www.csrc.gov.cn/...",
      "include": true,
      "notes": ""
    }
  ]
}
```

注意：
- `include=false` 直接跳过（用于"已发现但本期不写"的占位）
- `title` 只写文件正式全称，不带机构前缀
- `url` **优先官网原文链接**；非官网会被 fetcher 告警
- `notes` 用来给写稿时提示"机会型/对标/直接影响"等先验

### Step 2. 跑生成命令

```bash
python -m src.main generate \
  --input ./examples/example_weekly_policies.json \
  --output-dir ./output
```

完成后查看：

```
output/
├── normalized_policies.json     ← 规范化后的政策清单
├── fetched_articles.json        ← 抓取结果
├── policy_fact_sheets.json      ← 事实卡（生成依据）
├── retrieved_examples.json      ← 检索到的 few-shot
├── policy_card_drafts.json      ← LLM 一次生成的整期草稿
├── final_report_content.json    ← 重写后的最终结构化稿
├── validation_report.json       ← 校验报告（pass/fail 列表）
├── 监管政策周报_2026.04.19.docx  ← 最终交付物
└── run_log.md                   ← 全链路执行日志
```

### Step 3. 对照 QUALITY_CHECKLIST.md 通审

按 `QUALITY_CHECKLIST.md` 逐项打勾。任一项不过 → 找 `run_log.md` 中对应阶段，修配置或修事实卡后重跑。

---

## 5. 自进化链路：从人工终稿回流

### Step 1. 解析人工最终终稿

把这一期编辑后的最终终稿（Markdown）放到 `examples/` 或任意位置：

```bash
python -m src.main parse-final \
  --input ./examples/example_final_weekly_report.md \
  --output-dir ./output
```

产物：`output/final_report_parsed.json`（与 `policy_card_drafts.json` 字段对齐，便于后续 diff）。

### Step 2. 跑学习闭环

```bash
python -m src.main learn \
  --draft ./output/policy_card_drafts.json \
  --final ./output/final_report_parsed.json \
  --output-dir ./output
```

产物：
- `output/draft_final_diff.json` — 草稿与终稿逐条差异
- `output/learning_update_report.json` — 本次新增的 few-shot 与 forbidden expansion 列表
- `config/few_shot_library.json`（追加更新）
- `config/forbidden_expansion_library.json`（追加更新）

> 轻量版直接追加。如果想观察前后差异：先备份 `config/few_shot_library.json` 与 `config/forbidden_expansion_library.json`，跑完后 `diff` 一下即可。

### Step 3. 配置确认

```bash
python -m src.main upgrade --output-dir ./output
```

轻量版只输出"配置已更新确认"，不做复杂升级引擎；主要用于统一命令接口与审计日志。

---

## 6. 常见问题

### Q1. 抓取失败怎么办？

`fetcher.py` 已实现 retry + timeout + title-only fallback。
- 单条失败 → 在 `fetched_articles.json` 里 `fetch_status=failed`，事实卡只用 title 作为兜底
- 批量失败 → 优先排查网络 / 代理；个别官网（央行/金管）有 UA 校验，可在 `fetcher.py` 调整 UA

### Q2. 生成稿出现"程序拼接味"

- 检查 `config/few_shot_library.json` 是否包含同类型样例
- 检查 `policy_fact_sheets.json` 中 `paragraph2_mode` 与实际是否匹配
- 直接把这一期人工终稿跑 `learn`，让 few-shot 库自动补充

### Q3. 出现禁止词 / 红线

- 把"被人工删掉的整段"作为反例放进 `forbidden_expansion_library.json`
- 也可以直接跑 `learn`，会自动从 diff 中提取候选 forbidden expansion

### Q4. grouped pair 被拆成两条

- 检查 `extractor.py` 中 `grouping_key` 的识别逻辑是否覆盖该机构 / 该文件家族
- 必要时在 `notes` 字段手工标注 `"grouped_pair_with: <另一条 title>"` 强制合并

### Q5. P2 主体写错 / 不在平安主体范围

- 检查 `config/impact/pingan_entities.json`
- 检查 fact sheet 中 `allowed_paragraph2_entities` 是否被收窄

### Q6. 红色高亮泛红

- 收紧 `renderer.py` 的高亮规则（轻量版默认只高亮状态词、关键动作短语、关键制度变化短语）

### Q7. 命令找不到

```bash
# 必须从仓库根目录运行，且使用 -m 形式
python -m src.main generate --input ... --output-dir ...
```

不要用 `python src/main.py`，否则相对导入会失败。

---

## 7. 阶段路线图（提醒）

- Phase 1（已完成 ✅）：工程骨架
- Phase 2：配置与 schema
- Phase 3：主链路代码 → `generate` 跑通
- Phase 4：学习闭环 → `parse-final / learn / upgrade` 跑通
- Phase 5：测试与联调

每个 Phase 完成后必须输出新建文件清单 + 用途 + 下一阶段入口。
