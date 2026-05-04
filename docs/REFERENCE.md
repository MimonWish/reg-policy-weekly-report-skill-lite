# REFERENCE — 写作规则与技术细节

本文档承载 SKILL.md 入口外的全部细节，包含：写作约束、平安主体清单、paragraph2_mode 详解、重点文件判断标准。

---

## 1. 写作视角

平安集团合规专家视角，服务对象是集团高管。

输出目标只有三件事：
1. 帮高管快速判断：**本周哪些政策值得关注**
2. 帮高管快速判断：**对平安哪些专业公司有影响**
3. 帮高管快速判断：**最关键动作是什么**

---

## 2. 结构规则

| 文件类别 | 段落数量 | 说明 |
|---------|---------|------|
| 非重点文件 | 1 段 | 仅 P1 政策摘要 |
| 重点文件 | 最多 2 段 | P1 政策摘要 + P2 平安影响 |

**P1（政策摘要）必须含**：
- 机构 / 文号 / 状态
- 关键阈值（数字、比例、期限）
- 时间要求（生效时间、截止时间、过渡期）

**P2（平安影响）必须含**：
- 受影响的具体平安主体（不能写"金融机构"等泛化主体）
- 一个最关键动作（不要拼接多个动作）

---

## 3. 内容规则（红线）

**禁止**：
- 写行业背景
- 写宏观分析
- 写空转套话（如"该政策体现了…的方向"）
- 写"有助于""进一步彰显""持续关注"等无信息量词
- 一段塞多个动作

**必须**：
- 直接写"谁受影响、怎么改、先做什么"
- 重点信息高亮（征求意见稿/正式实施/修订草案/专项行动 等状态词）
- 具体子公司点名 + 具体动作

---

## 4. paragraph2_mode 详解

只允许以下 5 种 mode：

| Mode | 含义 | 何时用 | P2 写法要点 |
|------|------|-------|-----------|
| `direct` | 直接影响平安核心牌照或重点业务 | 影响业务边界、资本要求、产品设计 | 点名具体子公司 + 1 个具体整改/调整动作 |
| `scene_direct_related` | 场景直接相关 | 行业征求意见涉及平安产品形态 | 点名涉及子公司 + 影响场景 + 1 个跟进动作 |
| `benchmark` | 行业对标 | 仅在 importance 高时给一句对标提示 | 默认不出 P2，例外仅一句对标提示 |
| `opportunity` | 机会型 | 政策可能带来新业务机会 | **不得写整改动作**，只能写跟进观察 |
| `none` | 明确无影响 | 与平安业务边界无关 | 不出 P2 |

---

## 5. 平安主体清单（P2 必须落到具体主体）

完整清单见 [config/impact/pingan_entities.json](../config/impact/pingan_entities.json)，重点包括：

- **银行**：平安银行
- **保险**：平安寿险 / 养老险 / 健康险 / 产险
- **资管**：平安理财 / 资管 / 基金 / 信托 / 资本
- **证券期货**：平安证券 / 平安期货
- **租赁**：平安租赁
- **医疗**：平安医疗健康板块
- **集团职能**：合规部 / 消保 / 科技 / 财务

---

## 6. 重点文件判断标准

满足以下任一即视为重点（importance="major"）：

- 直接影响核心牌照或重点业务
- 直接带来制度整改、系统改造、产品回溯、模型治理
- 直接影响集团战略方向
- 直接影响业务准入、创新资格、评级结果、处罚风险

---

## 7. 特殊写法规则

### grouped pair（办法 + 实施公告 / 规则 + 配套）

**必须合并写成一条**。识别条件：
- 同一发文机构
- 同一日期
- 文件题目存在主从关系（如《办法（征求意见稿）》+《关于实施 X 办法有关事项的公告》）

合并后：
- title 用主文件名
- url 用主文件 url
- 状态以主文件为准

如果识别失败，可在 input JSON 的 `notes` 字段手工标注 `grouped_pair_with: <另一条 title>` 强制合并。

### benchmark_only

某些主题（见 `config/impact/topic_families.json` 中 `benchmark_only=true`）：
- 默认不出 P2
- 仅在重点判断成立时给一句"对标借鉴"

### opportunity 主题

某些主题（见 `topic_families.json` 中 `opportunity_possible=true`）：
- **绝不写整改动作**
- 只写"可关注 / 可评估"等跟进观察

---

## 8. 红色高亮规则

`renderer.py` 自动高亮以下短语为红色：
- 状态词：征求意见稿、修订草案、正式实施、专项行动、平安集团不直接适用
- 关键影响短语：`对平安XX有直接影响`、`后续将改变XX`
- 关键动作短语：应立即/应尽快/应优先/应开展/应修订/应调整/应切换/可关注/可评估

每条政策最多保留 4 处高亮，避免泛红。

---

## 9. 配置文件作用

| 配置文件 | 作用 |
|---------|------|
| `config/business_rules.yaml` | 全局业务规则、状态映射、边界约束 |
| `config/prompts.yaml` | LLM 系统提示词（generator/extractor 共用） |
| `config/style.yaml` | 风格约束（句长、段落数、用词偏好） |
| `config/few_shot_library.json` | few-shot 示例库（learning 自动追加） |
| `config/forbidden_expansion_library.json` | 禁止扩展模式库（learning 自动追加） |
| `config/impact/pingan_entities.json` | 平安主体定义与匹配规则 |
| `config/impact/topic_families.json` | 主题家族（域外管辖、跨境金融、AI治理 等） |
| `config/impact/scene_families.json` | 场景家族（产品形态、业务条线 等） |
| `config/impact/action_templates.json` | 动作模板（按状态/主题/场景匹配） |
| `config/impact/status_action_strength.json` | 不同状态对应的动作力度词 |

---

## 10. 事实卡（PolicyFactSheet）字段说明

| 字段 | 作用 |
|------|------|
| `summary_anchor_sentence` | P1 第一句的锚点（机构 + 政策名 + 核心动作） |
| `core_points` | 政策核心要点（2-4 条，每条 15-35 字） |
| `numbers_and_thresholds` | 数字与阈值（带上下文） |
| `time_requirements` | 时间要求（生效/截止/过渡期） |
| `recommended_action` | 单条最关键动作 |
| `paragraph2_mode` | 必为 5 种之一 |
| `affected_entities` | 受影响的平安主体（必须在 pingan_entities 中） |
| `allowed_paragraph1_facts` | P1 允许引用的事实（generator 不得超出） |
| `allowed_paragraph2_actions` | P2 允许使用的动作（generator 不得自创） |
| `forbidden_expansions` | 禁止扩展模式（来自 forbidden_expansion_library） |
| `quality_notes` | 质量备注（如 `title_only fallback` / `llm_inferred_from_title_and_notes`） |

---

## 11. 抓取异常处理

| 场景 | 处理 |
|------|------|
| 抓取失败 | `fetch_status=failed`，`raw_text` 为空，使用 title-only 兜底 |
| 抓到首页/导航页（垃圾内容） | `_is_irrelevant_content()` 检测：标题关键词命中率 < 50% 或有效中文句子（≥15 字）少于 3 条 → 视为无效，退化为 title-only |
| 极短抓取（<200 字符） | `is_thin=True` → LLM 推断（claude-sonnet-4-6） |
| 正常抓取 | 走轻量润色路径（claude-haiku-4-5） |
