# 历史终稿对照分析与架构优化清单

> 输入：《监管政策周报_合并完整版_最终版.docx》（共 8 期、约 56 条政策）
> 对照：Phase 1 骨架 + Phase 2 已落盘 4 份配置（prompts / business_rules / style / few_shot）
> 立场：保持轻量原则，**不引入新的 .py 文件、不拆 schema、不增加 mode / status**；优化集中在 prompts / business_rules / style / few_shot / impact 这几份配置里。

---

## 摘要：12 处关键落差（按对终稿质感的影响排序）

| # | 落差点 | 严重度 | 涉及文件 |
|---|---|---|---|
| 1 | paragraph2 "只保留 1 个主动作" 硬约束 vs 终稿"多主体多动作并列写法" | 🔴 必改 | business_rules / prompts / style / 校验 |
| 2 | preferred_entities 23 项缺关键主体（壹钱包 / 陆控 / 平安消金 / 平安健康互联网 等） | 🔴 必改 | business_rules / impact/pingan_entities |
| 3 | 标题格式落差：当前规则"仅文件名"vs 终稿"机构 + 文件名" | 🔴 必改 | SKILL / examples / schemas / renderer |
| 4 | 【…已做专项解读】等编辑注记体系完全缺失 | 🔴 必改 | schemas / business_rules / prompts / few_shot |
| 5 | paragraph1 "2-4 句"上限 vs 终稿大量 5-8 句、含 4-6 个核心点 | 🟠 应改 | style.sentence_length / business_rules.paragraph_structure |
| 6 | benchmark 段当前规则"只能一句"vs 终稿大量长篇对标分析（如央企内控） | 🟠 应改 | business_rules / style / prompts |
| 7 | paragraph2 五种 mode 不覆盖终稿 4 种真实写法（多主体/现状判断/已开展工作/损益判断） | 🟠 应改 | business_rules.paragraph2_mode_rules / prompts / few_shot |
| 8 | 高亮上限 4 段 vs 终稿大量 5-8 处加粗 | 🟠 应改 | style.highlight_rules |
| 9 | policy_type / 动词措辞（印发/发布/审议通过/公开征求意见/联合发布/下发/修订发布）未细化 | 🟡 建议改 | business_rules / style / prompts |
| 10 | 7 个 status 覆盖不足（缺：法律/法律草案、司法解释、自律规则、内部函件） | 🟡 建议改 | business_rules.status_action_rules |
| 11 | 集团身份判断分级（不直接适用 / 不适用但对标 / 不适用但借鉴）不够细 | 🟡 建议改 | business_rules / prompts |
| 12 | 主流文件类型（顶层文件、产业政策、地方监管文件、行业协会自律规范）未识别分流 | 🟡 建议改 | business_rules / impact/topic_families |

---

## 落差 1：paragraph2 "只保留 1 个主动作" 硬约束 → 必须放宽

### 终稿现象

终稿里**两段式条目大量采用"多主体并列、每主体一个动作"的写法**。例：

> **金融产品网络营销管理办法**：
> "**平安银行**需清理数字营销矩阵中涉及不合规的从业人员及个人账号，灵活宝和闲钱宝业务需完善对客提示，重新审查与第三方平台的合作协议……；**壹钱包**需调整收银台页面，将支付工具与贷款等金融产品严格区隔展示……；**平安产险、平安寿险**需全面检视、调整与第三方平台的合作模式……" — 一条 P2 实际并列了 4 组主体，每组带 1-3 个动作。

> **个人贷款业务明示综合融资成本规定**：
> "**平安银行**方面……预计受新规影响较小；陆控**担保业务（融易）**方面……贷后催收压力将增加；陆控**消金业务**方面……预计届时客诉舆情压力将加大。" — 一条 P2 实际是 3 个主体的"现状判断 + 受影响程度评估"。

### 当前架构

`business_rules.paragraph_structure_rules.paragraph2.hard_constraints`：
- "最多两句"
- "只能保留一个主动作"

`prompts.weekly_report_generation_prompt`：
- "paragraph2 硬约束：最多 2 句。只能保留 1 个主动作。"

### 落差

如果按现规则跑，终稿里 30%+ 的条目会被 validator 判失败、或被 generator 强行裁成单一主体单一动作 → **直接破坏业务终稿质感**。这是当前架构与终稿最严重的偏差。

### 建议改法（轻量）

把 P2 的"主动作数"改为按 `paragraph2_mode` 分级，而不是一刀切：

| paragraph2_mode | 主体数 | 动作数 | 句数 |
|---|---|---|---|
| `direct` | 1-4 | 每主体 1 个 | 2-6 |
| `scene_direct_related` | 1-2 | 1 个 + 一个落点短语 | 2-3 |
| `benchmark` | 1（"平安集团"） | 0-1 | 1-3（允许长 benchmark，详见落差 6） |
| `opportunity` | 1-2 | 0（只写机会观察） | 1-2 |
| `none` | 0 | 0 | 0 |

实质：**保持"信息密"原则，但把数量约束从单一动作改成按 mode 分级**。

---

## 落差 2：preferred_entities 主体清单缺关键项 → 必须扩充

### 终稿出现但当前 preferred_entities (23 项) 没有的主体

| 终稿主体 | 出现频次 | 备注 |
|---|---|---|
| **壹钱包** | 2 期出现 | 平安壹钱包，独立运营主体 |
| **陆控** / 陆金所控股 | 2 期出现 | 集团重要金融科技板块 |
| **陆控担保业务（融易）** | 1 次 | 陆控旗下产品 |
| **陆控消金业务** | 1 次 | 陆控旗下产品 |
| **平安消金** | 2 次 | 平安消费金融，与平安银行不同 |
| **平安健康**（互联网医疗，非平安健康险） | 1 次 | 平安健康互联网医疗 |
| **平安产险农险部** | 1 次 | 业务部门级 |
| **平安期货风险管理子公司** | 1 次 | 期货持牌主体的子公司 |
| **集团反洗钱团队** | 1 次 | 集团团队级 |
| **灵活宝**、**闲钱宝** | 1 次 | 平安银行旗下产品 |

### 当前架构

`business_rules.entity_scope_rules.preferred_entities` 仅 23 项，集中在持牌主体。

### 落差

终稿里"产品线 / 业务线 / 团队级"的主体大量出现，且这些往往是受影响的真正主体。如果 fact sheet 的 `allowed_paragraph2_entities` 只来自这 23 项，generator 会被迫退到"平安银行"这类宽口径主体，**丢失业务颗粒度**。

### 建议改法

- `business_rules.entity_scope_rules.preferred_entities` 扩展到 ~35-40 项，按层级分组：
  - 集团总部 / 团队（集团合规部、集团消保团队、集团反洗钱团队、集团科技条线、集团财务部 等）
  - 持牌主体（平安银行、平安寿险、平安产险 等 已有项）
  - **产品线 / 业务线**（壹钱包、陆控、陆控担保业务（融易）、陆控消金业务、平安消金、平安健康（互联网医疗）、平安期货风险管理子公司 等 — **新增**）
  - 部门级（平安产险农险部、平安证券投行业务、平安证券交易与经纪 等）
- 增加 `entity_scope_rules.entity_groups`，定义"上位主体 → 可下钻产品 / 业务"的关联（如平安银行 → 灵活宝 / 闲钱宝 / 数字营销矩阵），便于 extractor 给 fact sheet 自动选主体颗粒度。
- `config/impact/pingan_entities.json` 应作为"主清单"承载这一切（带层级、别名、所属持牌主体）；`business_rules.preferred_entities` 仅是写作偏好的精选子集。

---

## 落差 3：标题格式 → 必须修正

### 终稿标题格式

| 期次 | 条目标题 |
|---|---|
| #2026.04.26 第 1 条 | **中国人民银行等八部门《金融产品网络营销管理办法》** |
| #2026.04.19 第 3 条 | **中国证监会《期货公司监督管理办法（征求意见稿）》** |
| #2026.04.12 第 5 条 | **国务院办公厅《关于加快建设分级诊疗体系的若干措施》** |

格式：**机构 + 《文件名》**。

### 当前架构

- `SKILL.md` 第 5 节明确："`title` 只写文件正式全称，不带机构前缀"
- `examples/example_weekly_policies.json` 输入 `title` 也是仅文件名
- `examples/expected_output_notes.md` 也按"仅文件名"描述

### 落差

输入端没问题（输入仍可只写文件名），但**渲染端的标题必须是"机构 + 《文件名》"**。当前架构把这一规则写反了：要求 generator/renderer **不要**带机构前缀，与终稿完全相反。

### 建议改法

- `schemas.PolicyFactSheet` 仍保留 `title`（仅文件名）和 `issuer`，新增 `title_display` 字段（机构 + 《文件名》），由 extractor 拼接生成。这是事实上 SKILL.md 第 4 节里你已经写过的字段名，**只是当前 example/expected 还没贯彻**。
- `renderer.py` 渲染条目标题用 `title_display`。
- `examples/expected_output_notes.md` 与 `SKILL.md` 第 5 节的措辞要订正过来。
- `prompts.weekly_report_generation_prompt` 输出 JSON 的 `items[].title` 应明确是 `title_display`，避免 generator 混淆。

---

## 落差 4：【…已做专项解读】等编辑注记完全缺失

### 终稿现象（高频出现）

- **【已做专项解读】** — 网络营销办法
- **【集团反洗钱团队已做专项解读】** — 非法金融活动监测预警通知
- **【集团消保团队已做专题解读】** — 产品适当性管理自律规范
- **【正在组织开展专题解读】** — 金融法草案
- **【稍后单独提交专题分析】** — 政府工作报告
- **【已另行形成专项解读】** — 个人信息保护专项行动
- 行内型："**平安产险**农险部已组织学习研读并提交反馈意见。" — 这种是放进段尾。

这些注记**是终稿结构的标准组成部分**，提示读者"集团相关团队已经/正在做更深的工作"，避免给到高管"周报漏写"的错觉。

### 当前架构

- `schemas.FinalReportItem.editor_notes` 字段存在，但**仅作内部审计字段**用途（不渲染、不参与 LLM 输入）。
- `prompts` 不要求 LLM 生成这类注记。
- `style.yaml` 没有约定如何渲染这些注记。
- `few_shot_library.json` 10 条全部不含这类注记。

### 落差

generator 即便事实上正确，也无法生成这种"集团已做工作"的标识。终稿里这种注记往往出现在**高优先级条目结尾**，是"高管已知此事被覆盖"的强信号。

### 建议改法

1. **新增 fact_sheet 字段**（在 `PolicyFactSheet` 中）：
   - `group_internal_status: Optional[str]` — 集团已做工作的状态，枚举：`"专项解读已做" | "专项解读进行中" | "专题分析进行中" | "已反馈意见" | "差距分析中" | "无"` 等。
   - `group_internal_status_team: Optional[str]` — 哪个团队做的（"集团反洗钱团队"、"集团消保团队"、"平安产险农险部" 等）。
   - 这些字段**不来自抓取**，只能通过 `weekly_policies.json` 输入端的 `notes` 字段或专门的 `group_internal_status` 字段录入（人工录入）。
2. **扩展 `weekly_policies.json` 输入 schema**，允许加 `group_internal_status` 与 `group_internal_status_team`（已在 SKILL.md 第 5 节字段表预留余地）。
3. **prompts.weekly_report_generation_prompt** 增加约束：
   - 如果 `group_internal_status != "无"` 且 `paragraph2_mode != none`，在 paragraph2 末尾或独立标记位输出形如 `【集团反洗钱团队已做专项解读】` / `【已做专项解读】`。
   - 如果 `paragraph2_mode == none`（如反外国不当域外管辖条例），允许把这类注记**直接挂在 paragraph1 末尾**。
4. **renderer.py** 把这类注记用粗体灰底或红色高亮渲染（具体由 `style.yaml` 决定）。
5. **few_shot_library.json** 至少补 2 条带集团注记的样例。

---

## 落差 5：paragraph1 句长上限偏紧

### 终稿现象

终稿的 paragraph1 经常 5-8 句，列出 4-6 个核心制度变化点，单句也常常 50-70 字。例：

> **基金管理公司绩效考核管理指引**（2026.04.19 第 4 条）：
> 6 句、≈ 250 字、列了 6 个核心制度变化点、3 处加粗。

> **网络营销管理办法**（2026.04.26 第 1 条）：
> 8 句、≈ 320 字、列了 5+ 个核心制度变化、4 处加粗。

### 当前架构

- `style.sentence_length_rules.paragraph1`: 偏好 25-45 字 / 上限 70 字
- `paragraph_structure_rules.paragraph1.sentence_rules`: min 2 句 / max 4 句
- `business_rules.paragraph_structure_rules.paragraph1.must_include`: "2-4 个核心制度变化"

### 落差

按 `max_sentences=4` + "2-4 个核心制度变化"，generator 会把网络营销办法这类含 5-7 个核心要点的文件**强行压成 3-4 句**，丢失关键政策事实。

### 建议改法

- `paragraph1.max_sentences` 改为按 `importance` 分级：major 6-8 / minor 2-4。
- "2-4 个核心制度变化"改为 "major 4-7 个；minor 2-3 个"。
- 单句字符上限 70 → 90（终稿不少句子 70-85 字）。
- 段落总字符做软上限：major P1 ≤ 350 字、minor P1 ≤ 150 字。

---

## 落差 6：benchmark 长篇对标分析

### 终稿现象

> **关于做好2026年中央企业内部控制体系建设与监督工作有关事项的通知**（2026.03.22 第 4 条）：
> P1 列了 5 大具体要求（每项一句话），共约 600 字。
> P2 是**非常长的 benchmark 段**，约 230 字：
> "平安集团不直接适用于此《通知》，但该文件作为央企内控工作的顶层行动指南……过去三年金融监管总局的内控发文……与国资委中央企业通知的监管思路高度吻合……值得我们深入研究并主动对标借鉴。"

> **金融法（草案）**（2026.03.22 第 1 条）：
> 类似的长篇 P1 + 短 P2：P1 约 500 字（4 大要点）、P2 约 50 字 + 【正在组织开展专题解读】。

### 当前架构

- `business_rules.benchmark_rules.rules`: "如确需保留 benchmark 句，只允许一句" / "不得扩写成长段分析"
- `style.benchmark_style_rules.rules`: "默认不出第二段" / "如必须保留 benchmark 句，只允许一句"
- `prompts`: "benchmark_only 默认 paragraph2 为空" / "如确需保留 benchmark 句，只允许一句"

### 落差

终稿里 benchmark 段经常是 100-300 字、3-5 句的真分析（用来给高管讲"虽不直接适用，但监管趋势如此，要主动对标"）。当前规则**直接禁用了这种高质量写法**。

### 建议改法

把 `paragraph2_mode` 拆成两个 benchmark 子模式（**仍然不增加 mode 总数 5 个**，只是在 mode 内部区分子类型，由 fact sheet 的 `paragraph2_subtype` 表达）：

| 子类型 | 段长 | 内容 |
|---|---|---|
| `benchmark_short` | 1 句 / ≤ 50 字 | 默认。形如"平安集团不直接适用，但应对标其核心要求，优先补齐 X。" |
| `benchmark_long` | 2-5 句 / 80-300 字 | 仅在 fact sheet 标 `importance=major` 且涉及战略导向时使用 |

或者更轻量：直接在 `paragraph2_mode_rules.benchmark` 的子规则里加 `allow_long: true | false` 参数，由 fact sheet 决定。

---

## 落差 7：paragraph2 五种 mode 不覆盖终稿真实写法

### 终稿出现但 5 种 mode 未覆盖的写法

| 终稿写法 | 例 | 当前 5 mode 哪个最近 |
|---|---|---|
| **影响 + 现状判断**（"现行管理较为完善，预计受新规影响较小") | 个人贷款明示综合融资成本规定 | 都不近 |
| **影响 + 集团已开展工作**（"已开展深入新规解读及差距分析") | 上海地方融资租赁通知 | 都不近 |
| **影响 + 受影响程度量化**（"将影响陆控23.9%的高息产品") | 同上 | 都不近 |
| **多主体多动作**（"平安银行需…；壹钱包需…；平安产险需…") | 网络营销办法 | direct（但被"单动作"硬约束破坏） |
| **影响指引型**（"业务发展方向具有指引意义；可关注…导向；可参照…要求") | 推进服务业扩能提质的意见 | opportunity（但终稿语气更弱、更多） |

### 建议改法（仍然不增加 mode 总数）

- 不增加 mode，但在 `business_rules.paragraph2_mode_rules.mode_definitions` 中**为每个 mode 加 `subtypes` 子字段**：
  - `direct.subtypes`: `direct_single` / `direct_multi_entity` / `direct_with_status_assessment` / `direct_with_group_progress`
  - `scene_direct_related.subtypes`: `scene_single` / `scene_multi`
  - `benchmark.subtypes`: `benchmark_short` / `benchmark_long`
  - `opportunity.subtypes`: `opportunity_watch` / `opportunity_indicative`（指引型，比 watch 更弱）
  - `none.subtypes`: 仅 `none`
- `prompts.weekly_report_generation_prompt` 中根据 `paragraph2_subtype` 给出对应写法 pattern。
- `few_shot_library.json` 每个 subtype 至少 1 条样例（增量从 10 条 → ~16 条）。

---

## 落差 8：高亮上限偏紧

### 终稿现象

数了几条终稿的加粗段：

| 条目 | P1 加粗数 | P2 加粗数 |
|---|---:|---:|
| 网络营销办法 | 4 | 5 |
| 期货公司监督管理办法 | 4 | 0 |
| 基金绩效考核指引 | 6 | 1 |
| 央企内控通知 | 4 | 0 |

### 当前架构

`style.highlight_rules.max_highlight_segments_per_item: 4`

### 建议改法

- `max_highlight_segments_per_item: 4 → 8`
- 拆成 P1 / P2 各自上限：`paragraph1.max_segments: 6` / `paragraph2.max_segments: 4`
- 与已有 `benchmark_mode.max_highlight_segments: 1` / `opportunity_mode.max_highlight_segments: 1` 共存（这两个保持）。

---

## 落差 9：policy_type 与措辞动词未细化

### 终稿动词分布（影响 paragraph1 开头写法）

| 动词 | 终稿示例 |
|---|---|
| **发布** | "发布《XX管理办法》" — 部门规章 / 公告 |
| **印发** | "国务院办公厅印发《XX意见》" — 国务院、部委文件 |
| **联合发布** | "中国人民银行、金融监管总局……八部门联合发布" |
| **公开征求意见** | "就《XX（征求意见稿）》公开征求意见" |
| **修订发布** | "修订发布《XX指引》" |
| **审议通过** | "国务院常务会议审议通过《XX（修订草案）》" |
| **下发** | "向各保险公司征求……函" / "下发《XX通知》" — 内部函件 |
| **公布** | "国务院公布《XX条例》" — 行政法规 |
| **修订** | "中国证券业协会修订发布《XX指引》" |

### 当前架构

`style.preferred_openers.paragraph1` 给了 4 种通用句式：
- "X月X日，X部门发布《XXXX》。"
- "X月X日，X部门印发《XXXX》。"
- "X月X日，X部门就《XXXX》公开征求意见。"
- "X月X日，X部门公布《XXXX》。"

### 落差

差"联合发布"、"修订发布"、"审议通过"、"下发"四种典型动词。其中"审议通过"对应草案阶段的特殊动词，错用就会失真。

### 建议改法

- `style.preferred_openers.paragraph1` 增加 4 条句式。
- `business_rules` 新增 `policy_type_to_verb` 字典：
  - `部门规章` / `部门公告` → 发布 / 修订发布 / 联合发布
  - `国务院文件` / `国务院办公厅文件` → 印发 / 公布
  - `行政法规` → 公布
  - `法律 / 法律草案` → 审议通过 / 公开征求意见
  - `部门通知 / 公告（内部）` → 下发 / 印发
  - `行业协会规范 / 自律规则` → 发布 / 修订发布
  - `司法解释` → 联合发布
- `prompts.weekly_report_generation_prompt` 增加："paragraph1 的动词必须与 fact sheet 的 `policy_type` 匹配"。

---

## 落差 10：7 个 status 覆盖不足

### 终稿出现但 7 个 status 未覆盖的状态

| 终稿状态 | 例 | 当前最接近的 status |
|---|---|---|
| **法律草案 / 法律修订** | 《金融法（草案）》 | "修订草案"（勉强，但法律级别更高） |
| **司法解释** | "两高"《关于办理贪污贿赂刑事案件适用法律若干问题的解释（二）》 | 无对应 |
| **行业协会自律规则** | 《银行业金融机构合规管理自律规范》 | "正式实施"（但语调和约束力不同） |
| **内部函件** | 《农业保险地块基础信息库数据安全管理办法（试行）》征求意见函 | 无对应 |
| **顶层文件** | 《政府工作报告》/《十五五规划纲要》 | "计划"（勉强） |
| **地方监管文件** | 上海地方融资租赁通知 / 深圳保险业行动方案 | 无对应 |

### 建议改法（不增加 status 总数）

- 7 个 status 总数保持不变。
- 给每个 status 加 `subtypes`：
  - `正式实施.subtypes`: `部门规章正式实施` / `行政法规正式实施` / `司法解释正式实施` / `行业自律正式实施` / `地方文件正式实施`
  - `征求意见稿.subtypes`: `公开征求意见` / `内部函件征求意见`
  - `修订草案.subtypes`: `修订草案` / `法律草案`
  - `计划.subtypes`: `部门工作计划` / `行业行动方案` / `顶层规划`
- `business_rules.status_action_rules.status_levels.*.subtypes.*.allowed_action_styles` 在子粒度上调整。

---

## 落差 11：集团身份判断分级不够细

### 终稿三种"集团身份判断"

| 写法 | 例 | 备注 |
|---|---|---|
| **直接适用** | "《规则》直接适用于 A 股上市的平安集团、平安银行" | 直接义务 |
| **不直接适用** | "《条例》……不直接适用于平安集团及其下属机构" | 完全不适用 |
| **不直接适用 + 对标借鉴** | "平安集团不直接适用于此《通知》，但其在完善公司治理、强化合规经营方面提供了参考标准" | 中间状态，常用 |
| **参照执行** | "商租公司参照执行金租公司法规" | 类比适用，但来自其他主体的规则 |

### 当前架构

`business_rules.benchmark_rules` 只区分了 benchmark / non-benchmark，没区分中间状态。

### 建议改法

- 新增 `business_rules.applicability_rules`：
  - `directly_applicable`：直接适用 → 走 direct / scene_direct_related
  - `not_applicable`：完全不适用 → 走 none
  - `not_applicable_but_reference`：不直接适用但应对标 → 走 benchmark
  - `reference_execution`：参照执行（特殊，很少出现）→ 走 direct，但需说明来源
- 对应 fact sheet 字段 `applicability` 来表达。
- `prompts` 增加约束："paragraph2 的开头必须与 applicability 一致"。

---

## 落差 12：主流文件类型未识别分流

### 终稿出现的文件类型

| 类型 | 数量 | 例 |
|---|---:|---|
| 部门规章（正式实施 / 征求意见） | 25+ | 网络营销办法 / 期货公司办法 / 投资基金运作指引 |
| 国务院 / 国办文件 | 6 | 分级诊疗 / 投资审批改革 / 服务业扩能 |
| 行政法规 / 条例 | 3 | 反外国不当域外管辖条例 |
| 法律 / 草案 | 1 | 金融法草案 |
| 司法解释 | 1 | 两高贪污贿赂解释（二） |
| 行业协会自律规则 | 5 | 适当性规范、合规自律规范、薪酬制度指引等 |
| 行动方案 / 工作计划 / 顶层规划 | 5 | 政府工作报告 / 十五五规划 / 物联网行动方案 / 立法计划 |
| 地方监管文件 | 3 | 上海融资租赁 / 深圳保险业 |
| 内部函件 | 2 | 农险地块信息库征求意见函 / 人身险负面清单 |
| 内控通知（央企） | 1 | 央企内控通知 |

### 当前架构

`config/impact/topic_families.json` 还没创建，但 `business_rules` 中也没有"文件类型 → 写作策略"的映射。

### 建议改法

`config/impact/topic_families.json` 不仅要按主题分（金融营销 / 跨境业务 / 资管 / 期货 / 医疗等），还要建立 **policy_type 字典**：

```json
{
  "policy_types": {
    "部门规章": { ... },
    "国务院文件": { ... },
    "行政法规": { ... },
    "法律": { ... },
    "司法解释": { ... },
    "行业自律规则": { ... },
    "顶层规划": { ... },
    "地方监管文件": { ... },
    "内部函件": { ... }
  }
}
```

extractor 在构建 fact sheet 时填 `policy_type`，generator 用 `policy_type` 决定 paragraph1 的动词与语气。

---

## 影响地图：哪些文件需要修改

| 文件 | 涉及落差 | 修改幅度 |
|---|---|---|
| `config/business_rules.yaml` | 1, 2, 5, 6, 7, 9, 10, 11 | 🔴 大改（约 30% 内容） |
| `config/style.yaml` | 5, 6, 7, 8, 9 | 🟠 中改（约 15%） |
| `config/prompts.yaml` | 1, 3, 4, 6, 7, 9, 11 | 🟠 中改（在 prompt 主干上加约束） |
| `config/few_shot_library.json` | 1, 4, 6, 7 | 🟠 中改（10 条 → ~18 条） |
| `config/impact/pingan_entities.json` | 2 | 🔴 创建并大于 preferred_entities |
| `config/impact/topic_families.json` | 9, 12 | 🔴 创建时含 policy_types |
| `SKILL.md` | 3 | 🟡 小改（订正 title 规则） |
| `examples/example_weekly_policies.json` | 4 | 🟡 小改（增加 group_internal_status） |
| `examples/expected_output_notes.md` | 3, 4 | 🟡 小改 |
| `src/schemas.py` | 3, 4, 7, 11 | 🟠 中改（新增字段：title_display 已在、group_internal_status / group_internal_status_team / paragraph2_subtype / applicability / policy_type 细化） |

注意：**没有任何一处改动需要新增 .py 文件、新增 src 子目录、新增 mode 总数、新增 status 总数**。全部在已有 8 个 .py 文件 + 已有配置文件骨架内消化。

---

## 优先级与建议落地顺序

### 必改（如不改，generator 必出"程序拼接味"或失败）

1. **落差 1**（P2 多动作）— 这是终稿质感的根基，必须先改。
2. **落差 2**（主体清单）— 新建 `pingan_entities.json` 并扩展 preferred_entities。
3. **落差 3**（标题格式）— 一处订正贯穿 SKILL / examples / schemas。
4. **落差 4**（编辑注记）— 新增 schema 字段并打通 prompts / renderer。

### 应改（关系到稿子像不像终稿）

5. **落差 5**（P1 句长）— 数字调整。
6. **落差 6**（benchmark 长篇）— 引入 `benchmark_short` / `benchmark_long`。
7. **落差 7**（mode subtypes）— 不增 mode 总数，加 subtypes。
8. **落差 8**（高亮上限）— 数字调整。

### 建议改（精雕）

9. **落差 9**（动词细化）
10. **落差 10**（status subtypes）
11. **落差 11**（applicability 分级）
12. **落差 12**（policy_type 字典）

---

## 不能动的核心约束（确认仍然有效）

- 总共 5 种 paragraph2_mode、7 种 status — **维持**（仅在内部加 subtypes）
- 8 个核心 .py 文件 — **维持**
- 4 个 CLI 命令 — **维持**
- 自进化只做 few-shot + forbidden expansion — **维持**
- 不引入候选注册中心 / 多层评分引擎 — **维持**
- LLM-first + 事实卡约束 + 少量硬校验 — **维持**

---

## 备注：8 期 56 条政策的写作模式分布（粗算）

| 模式 / 写法 | 条目数 | 占比 |
|---|---:|---:|
| `direct` 单主体单动作 | 8 | 14% |
| `direct_multi_entity` 多主体多动作 | 11 | 20% |
| `direct_with_group_progress` 含集团已做工作 | 6 | 11% |
| `direct_with_status_assessment` 含现状判断 | 4 | 7% |
| `scene_direct_related` 场景型 | 5 | 9% |
| `benchmark_short` 短对标 | 4 | 7% |
| `benchmark_long` 长对标 | 3 | 5% |
| `opportunity_watch` 标准机会项 | 3 | 5% |
| `opportunity_indicative` 指引型机会 | 4 | 7% |
| `none` 仅一段 | 8 | 14% |

可见：**多主体多动作 + 含集团已做工作 = 31%**，是终稿的主流写法之一。当前架构对这两种几乎完全不支持。这就是现架构与终稿落差最大的来源。
