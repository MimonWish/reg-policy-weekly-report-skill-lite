# QUALITY_CHECKLIST.md

> 终稿质量清单。每次跑完 `generate` 后，对照本清单逐项核查 `output/监管政策周报_YYYY.MM.DD.docx` 与 `output/validation_report.json`。
> 任何一项不过 → 必须重写或回到对应阶段排查。

---

## A. 链接与来源

- [ ] **A1** 每条政策的 `url` 都是发布机构官网原文链接（证监会/银保监/央行/金管总局/外管局/交易所等）
- [ ] **A2** 非官网链接已在 `validation_report.json` 中告警，且 `editor_notes` 标注"待人工核验"
- [ ] **A3** 抓取失败的条目已走 title-only fallback，未把抓取错误传到正文

## B. 结构与字数

- [ ] **B1** 非重点文件 → 只写一段
- [ ] **B2** 重点文件 → 最多两段，第一段政策摘要、第二段平安影响
- [ ] **B3** 第二段没有出现行业背景 / 宏观分析 / 空转套话
- [ ] **B4** 第二段只保留 **1 个主动作**（不堆动作清单）
- [ ] **B5** P1 与 P2 没有出现高度重复（同一句话拆两段）

## C. 写作口径

- [ ] **C1** 站在平安集团合规专家视角，服务对象是集团高管
- [ ] **C2** 直接写"谁受影响、怎么改、先做什么"
- [ ] **C3** 没有"宜""可考虑""建议关注"等空话动词
- [ ] **C4** P2 主体落到具体平安主体（平安银行 / 平安寿险 / 平安证券 / 平安理财 / 平安产险 等），不写"集团各业务条线"这类无信息量的范围

## D. 特殊写法

- [ ] **D1** `grouped pair`（办法+实施公告 / 规则+配套公告）已**合并**为一条，没有被拆成两条独立条目
- [ ] **D2** `benchmark` 类（行业对标）默认**不出 P2**，仅在 importance 高时给一句对标提示
- [ ] **D3** `benchmark_only` 没有被误写两段
- [ ] **D4** `opportunity` 类没有被写成整改动作（只写跟进观察）
- [ ] **D5** `none` 模式没有被强行凑出 P2

## E. paragraph2_mode

- [ ] **E1** 每条 item 的 `paragraph2_mode` 在 `direct / scene_direct_related / benchmark / opportunity / none` 五值之内
- [ ] **E2** mode 与正文一致（mode=none 但写了 P2 → 严重不合格）

## F. 事实卡引用

- [ ] **F1** P1 中的事实（机构 / 文号 / 状态 / 阈值 / 时间）来自 fact sheet 的 `allowed_paragraph1_facts`
- [ ] **F2** P2 中提到的主体来自 `allowed_paragraph2_entities`
- [ ] **F3** P2 中的动作来自 `allowed_paragraph2_actions`
- [ ] **F4** 没有出现 fact sheet 之外的具体数字、阈值、日期、机构名

## G. 红线（forbidden expansion）

- [ ] **G1** 没有命中 `config/forbidden_expansion_library.json` 中的 pattern
- [ ] **G2** 没有出现禁止词（详见 `config/style.yaml.forbidden_phrases`）
- [ ] **G3** 没有伪推论（用"由此可见""可推断"延伸到 fact sheet 之外的结论）

## H. 渲染与高亮

- [ ] **H1** 标题样式正常，没有整体泛红
- [ ] **H2** 红色高亮范围受控，仅命中以下任意一类：
    - "征求意见稿" / "正式实施" 等状态词
    - "对平安XXX有直接影响"
    - "应立即…… / 应优先…… / 应开展……" 关键动作短语
    - P1 中关键的制度变化短语
    - P2 中最关键动作短语
- [ ] **H3** 文件名为 `监管政策周报_YYYY.MM.DD.docx`

## I. 整体观感

- [ ] **I1** 通读一遍像**业务终稿**，不像程序拼接稿
- [ ] **I2** 高管 1 分钟内能读完一条并知道"要不要管 / 谁受影响 / 先做什么"
- [ ] **I3** 没有冗余开场白、没有无意义结尾

## J. 反过拟合

- [ ] **J1** 历史周报仅用于结构、颗粒度、主体映射和高亮逻辑，没有复用历史正文成句
- [ ] **J2** 如历史周报中存在同一期或同一政策，已把该历史段落列为"禁复制样稿"
- [ ] **J3** 除标题、日期、机构、文号、生效期等事实短语外，P1/P2 没有连续 20 个汉字以上与历史样稿一致
- [ ] **J4** 任一 P1/P2 与历史同类段落高度近似时，已基于政策原文重新组织句式、要点顺序和业务动作表达
- [ ] **J5** 红色/黑色高亮是根据本次新正文重新选择的精确子串，没有照搬历史高亮清单

## K. 自进化

- [ ] **K1** 对照专家终稿时，已先输出 `gap_analysis.md/json` 和 `learning_proposals.md`，未直接修改 Skill
- [ ] **K2** 学习建议均为"触发条件 + 判断模式 + 适用边界"，不包含专家稿长句
- [ ] **K3** 高置信候选规则已自动写入 `config/evolution_rules.json` 并标记为 `active`
- [ ] **K4** 中低置信候选规则仍为 `pending_confirmation`，用户确认前没有更新 `SKILL.md`、`config/impact`、`few_shot_library.json` 或 `forbidden_expansion_library.json`
- [ ] **K5** 确认后更新的规则能说明适用范围和过拟合风险
- [ ] **K6** 更新后已重跑测试和反过拟合检查

---

## 不过时的快速回滚

| 现象 | 回到哪一阶段 |
|------|------|
| 抓取失败 / 链接错 | `fetcher.py` |
| 主体错 / 动作错 / 事实漏 | `extractor.py` 的 fact sheet |
| 文笔像程序拼接 / few-shot 没生效 | `generator.py`、`config/few_shot_library.json` |
| 命中红线 / 出现禁止词 | `config/forbidden_expansion_library.json`、`config/style.yaml` |
| 高亮泛红 / 文件名错 | `renderer.py` |

---

## 做完一次 review 后

- 通过 → 把这一期人工最终终稿放进 `examples/`，跑一次 `parse-final` + `learn`，自动补充 few-shot / forbidden expansion
- 不通过 → 在 `validation_report.json` 中找到第一条 fail，按上表回到对应阶段
