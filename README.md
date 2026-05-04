# reg-policy-weekly-report-skill-lite

轻量版 **监管政策周报解读 + 自进化学习** Skill。

> 这是开发者面向的安装/运行手册。Skill 触发逻辑见 [SKILL.md](SKILL.md)，写作规则见 [docs/REFERENCE.md](docs/REFERENCE.md)。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 环境变量

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# 可选：覆盖默认模型
# export REG_POLICY_LLM_MODEL="claude-opus-4-7"
```

未设置 `ANTHROPIC_API_KEY` 时：
- `extractor.py` 跳过 LLM 精炼（事实卡仅基于规则提取）
- `generator.py` 直接报错（必须有 key）

## 快速开始

```bash
# 1. 主生成链路（输出 docx）
python -m src.main generate \
  --input ./examples/example_weekly_policies.json \
  --output-dir ./output

# 2. 解析人工最终终稿
python -m src.main parse-final \
  --input ./examples/example_final_weekly_report.md \
  --output-dir ./output

# 3. 学习闭环（更新 few-shot / forbidden）
python -m src.main learn \
  --draft ./output/policy_card_drafts.json \
  --final ./output/final_report_parsed.json \
  --output-dir ./output

# 4. 升级确认
python -m src.main upgrade --output-dir ./output
```

## 项目结构

```
.
├── SKILL.md                     # Skill 入口（触发逻辑 + 链路概览）
├── README.md                    # 本文件（开发者安装与运行）
├── pyproject.toml / requirements.txt
├── .gitignore
│
├── src/                         # 8 个核心 Python 文件
│   ├── main.py                  # CLI 入口
│   ├── schemas.py               # Pydantic schema
│   ├── fetcher.py               # 官网抓取
│   ├── extractor.py             # 抽取 + 事实卡构建
│   ├── generator.py             # few-shot 检索 + LLM 生成
│   ├── validator.py             # 硬校验
│   ├── renderer.py              # python-docx 渲染
│   └── learning.py              # diff + few-shot/forbidden 更新
│
├── config/                      # 业务规则与知识库（统一收口）
│   ├── business_rules.yaml
│   ├── prompts.yaml
│   ├── style.yaml
│   ├── few_shot_library.json
│   ├── forbidden_expansion_library.json
│   └── impact/
│       ├── pingan_entities.json
│       ├── topic_families.json
│       ├── scene_families.json
│       ├── action_templates.json
│       └── status_action_strength.json
│
├── examples/                    # 示例输入与人工终稿
│   ├── example_weekly_policies.json
│   ├── example_final_weekly_report.md
│   └── example_claude_code_command.md
│
├── docs/                        # 详细文档
│   ├── REFERENCE.md             # 完整写作规则、平安主体、paragraph2_mode
│   ├── QUALITY_CHECKLIST.md
│   ├── run_instructions.md
│   ├── expected_output_notes.md
│   ├── gap_analysis_against_real_report.md
│   └── CLAUDE_CODE_PROMPT.md
│
└── tests/                       # 单元测试
    ├── test_extractor.py
    └── fixtures/
```

## 输出文件

| 文件 | 阶段 | 说明 |
|------|------|------|
| `normalized_policies.json` | normalize | 去重过滤后 |
| `fetched_articles.json` | fetch | 官网抓取结果 |
| `policy_fact_sheets.json` | extract | 事实卡（生成依据） |
| `retrieved_examples.json` | retrieve | 命中的 few-shot |
| `policy_card_drafts.json` | generate | LLM 一次性生成的整期草稿 |
| `validation_report.json` | validate | pass/fail 列表 |
| `final_report_content.json` | finalize | 重写后的最终结构化稿 |
| `监管政策周报_YYYY.MM.DD.docx` | render | **最终交付物** |
| `run_log.md` | all | 全链路执行日志 |

## 测试

```bash
pip install pytest
pytest tests/ -v
```

## 常见问题

详见 [docs/run_instructions.md](docs/run_instructions.md) 的"常见问题"章节。

## 相关文档

- [SKILL.md](SKILL.md) — Skill 入口与触发逻辑
- [docs/REFERENCE.md](docs/REFERENCE.md) — 完整写作规则、paragraph2_mode 详解
- [docs/QUALITY_CHECKLIST.md](docs/QUALITY_CHECKLIST.md) — 交付前质量检查
- [docs/run_instructions.md](docs/run_instructions.md) — 详细运行手册
