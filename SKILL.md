---
name: reg-policy-weekly-report-skill-lite
description: 轻量版"监管政策周报解读 + 自进化学习" Skill。输入是本周政策清单 JSON，输出是符合平安集团高管阅读口径的《监管政策周报》Word 正式版。当用户提到"监管政策周报""监管周报""政策解读周报""平安政策周报""把本周政策跑成周报""本周政策清单生成周报"或类似工作流时，必须使用本 Skill；当用户给到本周政策清单 JSON 并要求出 Word 报告，或要求基于人工最终终稿做 few-shot / forbidden expansion 增量学习时，也必须使用本 Skill。
version: 0.3.0
---

# reg-policy-weekly-report-skill-lite

服务对象：平安集团合规管理与经营协同条线，面向集团高管的《监管政策周报》生产链路。

定位：**生成质量像业务终稿**，不是搭中台。

## 何时使用本 Skill

满足以下任一条件，必须调用本 Skill：

- 用户提供本周政策清单 JSON，要求生成 Word 周报
- 用户提到"监管政策周报""监管周报""政策解读周报""平安政策周报"等关键词
- 用户给到人工最终终稿，要求做 few-shot / forbidden expansion 增量学习
- 用户要求按平安集团高管阅读口径写"谁受影响、怎么改、先做什么"

## 项目结构

```
.
├── SKILL.md              # 本文件（Skill 入口）
├── README.md             # 面向开发者的安装与运行
├── pyproject.toml / requirements.txt
├── src/                  # 8 个核心 Python 文件
│   ├── main.py           # CLI 入口（generate/parse-final/learn/upgrade）
│   ├── schemas.py        # Pydantic schema
│   ├── fetcher.py        # 官网抓取
│   ├── extractor.py      # 抽取 + 聚合 + 事实卡构建
│   ├── generator.py      # few-shot 检索 + LLM 生成 + 重写
│   ├── validator.py      # 硬校验
│   ├── renderer.py       # python-docx 渲染
│   └── learning.py       # 终稿 diff + few-shot/forbidden 更新
├── config/               # 业务规则与知识库
│   ├── business_rules.yaml, prompts.yaml, style.yaml
│   ├── few_shot_library.json, forbidden_expansion_library.json
│   └── impact/{pingan_entities,topic_families,scene_families,action_templates,status_action_strength}.json
├── examples/             # 示例输入与人工终稿
├── docs/                 # 详细文档（写作规则、QA、命令、差距分析）
└── tests/                # 单元测试（pytest）
```

## 主链路（推荐：Skill-as-instructions 模式）

本 Skill 把"重活"分给会话中的 Claude（你正在使用的这个 LLM），Python 只负责确定性任务（抓取/解析/校验/渲染）。**无需独立的 ANTHROPIC_API_KEY**。

### Stage A：准备（python prepare）

```bash
python -m src.main prepare \
  --input ./examples/example_weekly_policies.json \
  --output-dir ./output
```

产物：
- `normalized_policies.json` / `fetched_articles.json` / `policy_fact_sheets.json`
- `retrieved_examples.json`
- **`generation_prompt.md`** — 包含完整提示词、fact_sheets、few-shot 的 Markdown，会话 LLM 直接读取它

### Stage B：会话 LLM 生成草稿（无需独立 API key）

调用本 Skill 的 Claude Code 会话直接：
1. `Read output/generation_prompt.md`
2. 严格按提示词中的写作规则与 schema 产出 drafts JSON
3. `Write output/policy_card_drafts.json`

**关键约束（会话 LLM 必须遵守）**：
- `paragraph1` 只能改写 `allowed_paragraph1_facts / core_points / numbers_and_thresholds / time_requirements`
- `paragraph2` 只能使用 `allowed_paragraph2_entities / allowed_paragraph2_actions`
- `paragraph2_mode` 必为 `direct / scene_direct_related / benchmark / opportunity / none` 之一
- `grouped_key` 相同的多条政策合并为 1 条
- 不写行业背景、宏观分析、空转套话；直接写"谁受影响、怎么改、先做什么"
- 详细规则见 `docs/REFERENCE.md`

### Stage C：校验 + 渲染（python finalize）

```bash
python -m src.main finalize --output-dir ./output
```

产物：
- `validation_report.json` — 硬校验结果
- `final_report_content.json`
- `监管政策周报_YYYY.MM.DD.docx` — 最终交付物

如校验未通过，回 Stage B 修订对应条目后重跑 `finalize`。

## 旧模式（legacy generate，不推荐）

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python -m src.main generate --input ... --output-dir ...
```

旧模式在 Python 子进程内自调 anthropic SDK 一条龙生成，需要独立 API key。仅为兼容保留。

## 学习链路（自进化）

```
人工最终终稿 (md)
   ↓ parse-final
final_report_parsed.json
   ↓ learn (diff)
draft_final_diff.json
   ↓ 自动追加
config/few_shot_library.json
config/forbidden_expansion_library.json
```

**只做两件事**：few-shot 自动补充 + forbidden expansion 自动补充。
不做：复杂规则引擎、候选注册中心。

## 核心写作约束（必须强制）

- **结构**：非重点 1 段；重点最多 2 段（P1 政策摘要，P2 平安影响）
- **paragraph2_mode**：仅允许 `direct` / `scene_direct_related` / `benchmark` / `opportunity` / `none`
- **P2 必落具体平安主体**（见 `config/impact/pingan_entities.json`）
- **不写**：行业背景、宏观分析、空转套话
- **直接写**：谁受影响、怎么改、先做什么
- **grouped pair**（办法 + 实施公告）必须合并写成一条
- **第二段只保留 1 个主动作**

> 详细写作规则见 [docs/REFERENCE.md](docs/REFERENCE.md)

## CLI 命令（4 个）

```bash
# 必需环境变量
export ANTHROPIC_API_KEY="sk-ant-..."

# 1. 主生成链路
python -m src.main generate \
  --input ./examples/example_weekly_policies.json \
  --output-dir ./output

# 2. 解析人工最终终稿
python -m src.main parse-final \
  --input ./examples/example_final_weekly_report.md \
  --output-dir ./output

# 3. 学习闭环
python -m src.main learn \
  --draft ./output/policy_card_drafts.json \
  --final ./output/final_report_parsed.json \
  --output-dir ./output

# 4. 升级确认（轻量版仅做配置已更新确认）
python -m src.main upgrade --output-dir ./output
```

## 输入输出协议

### 输入：weekly_policies.json

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
      "notes": "可标注 grouped_pair_with / 直接影响 / 对标借鉴 等先验"
    }
  ]
}
```

规则：`include=false` 跳过；`title` 仅政策正式全称；`url` 优先官网。

### 输出（output/）

主链路：`normalized_policies.json` → `fetched_articles.json` → `policy_fact_sheets.json` → `retrieved_examples.json` → `policy_card_drafts.json` → `validation_report.json` → `final_report_content.json` → `监管政策周报_YYYY.MM.DD.docx` + `run_log.md`

学习链路：`final_report_parsed.json` → `draft_final_diff.json` → `learning_update_report.json`

## 设计原则

1. 复杂业务判断交给 **LLM + prompt + few-shot**
2. Python 代码只负责：**供数 / 约束 / 校验 / 渲染 / 简单学习闭环**
3. 优先"生成结果像业务终稿"，不是"代码层级架构漂亮"
4. 不允许新增 `src/impact/`、`src/generation/` 等子目录

## 相关文档

- [README.md](README.md) — 安装、运行、环境变量
- [docs/REFERENCE.md](docs/REFERENCE.md) — 完整写作规则、paragraph2_mode 详解、平安主体清单
- [docs/QUALITY_CHECKLIST.md](docs/QUALITY_CHECKLIST.md) — 交付前质量检查清单
- [docs/run_instructions.md](docs/run_instructions.md) — 详细运行手册与 FAQ
- [docs/expected_output_notes.md](docs/expected_output_notes.md) — 输出样例说明
- [docs/gap_analysis_against_real_report.md](docs/gap_analysis_against_real_report.md) — 与业务终稿的差距分析
