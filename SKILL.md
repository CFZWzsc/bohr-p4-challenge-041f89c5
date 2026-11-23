---
name: research-proposal-novelty-assessment
description: Use when a proposed research idea must be assessed before funding or execution, requiring a falsifiable restatement, lexical prior-art overlap with an explicit non-global caveat, differentiators, feasibility checks against declared resources, typed risks, revisions and a transparent scorecard.
---

# 科研选题与创新性评估

## 用途与适用条件

当任务要求判断一个研究选题是否可检验、别人做到哪一步、增量在哪、现有条件能否做成时使用：先把选题改写为可检验形式，再与提供的先行研究做词项重叠比对并声明这不是全球查新，随后给出差异化特征、资源可行性检查、风险与修改建议。

**适用前提**：`case.json` 提供选题文本（`proposal`/`idea`/`hypothesis`/`research_question`）、先行研究数组，以及可选 `resources`/`constraints`（数据、样本量、时间、设备、技能）。

**不适用**：替代查新报告或专利检索、替代伦理审查、给出资助结论、生成完整实验方案或预算。

## 输入

| 输入 | 说明 |
|---|---|
| `/input/case.json` | `proposal`/`proposed_topic`/`idea`/`hypothesis`/`research_question`/`topic`；`prior_art`/`records`/`papers`（`source_id`、`title`、`abstract`、`year`、`doi`）；`resources`/`constraints`（`data`、`sample_size`、`time_months`、`equipment`、`skills`、伦理声明）。 |
| `task.md` | 可选，选题缺失时取前几行正文兜底。 |
| `--work` | 默认 `/app/work`。 |

## 处理流程（对应评分维度）

1. **可检验化**（任务完成度）：抽取干预、结局指标、人群与对照，判断是否同时具备可测结局与对照；标出 `better`/`有效` 等未操作化词。
2. **先行研究比对**（正确性）：对每条记录计算与选题共享词项比例，分为 `direct_overlap`/`partial_overlap`/`adjacent`；新颖度分数按最高重叠与近邻数量折算，并明确只对提供批次有效。
3. **差异化**（完整性）：把选题中未被最近先行研究覆盖的词项列为候选差异点；不宣称其绝对新颖。
4. **可行性**（正确性）：逐项检查数据、样本量、时间、方法设备与伦理声明；区分 `blocker` 与 `warning`，并给出 `verdict`。
5. **风险与修改**（可靠体验）：按先行拥挤、不可检验、模糊构念、可行性阻断、无先行研究生成风险；修改建议必须可执行。
6. **评分卡**（可核验性）：新颖度、可行性、可检验度三项分值公开计算口径，声明不作为资助或伦理决策。

## 输出契约

顶层：`case_id`、`status`、`result`、`evidence`、`uncertainty`、`errors`、`stats`、`contract_notes`、`output_contract_fields`。

`result` 含：`proposal`、`testable_form`、`novelty_assessment`、`prior_art_table`、`differentiators`、`feasibility`、`risks`、`recommended_revisions`、`research_gaps`、`scorecard`、`limitations`、`change_log`。

输入 `output_contract` 的字段名全部保留；无法产出写 `null` 并在 `contract_notes` 说明。

`status`：无选题或无先行研究 → `insufficient_input`；选题不可检验或缺资源声明 → `partial`；两者齐备 → `success`；解析失败 → `failed`。

## 异常处理

| 情形 | 处理 | 标记 |
|---|---|---|
| 无先行研究 | 不给出新颖度结论 | `status=insufficient_input` |
| 选题含模糊词 | 列出并要求操作化 | `risks.type=vague_constructs` |
| 无对照或无结局指标 | 判为不可检验 | `testable_form.tests.is_falsifiable=false` |
| 无资源声明 | 可行性只做部分检查 | `uncertainty.type=no_resources` |
| 样本不足 | 记为 blocker | `feasibility.blockers` |
| 涉及人或动物但无伦理声明 | 记为 warning | `check=ethics` |
| 输出不可写 | stderr 错误，退出码 3 | 无静默成功 |

## 限制

- 新颖度是词项重叠，不是查新或专利检索，不能证明全球首创。
- 可行性只覆盖已声明资源，未声明能力不作推断。
- 分值为启发式，不得用于资助、伦理或人事决策。
- 不生成实验方案、样本量计算或预算。

## 最小调用示例（示例，非正式案例结果）

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /input/case.json --out /app/output/result.json --work /app/work
```

```json
{"case_id":"demo-pr-01",
 "proposal":"A CRISPR knockout screen will identify genes that improve CAR-T persistence versus standard CAR-T in patients.",
 "resources":{"data":"primary T cells","sample_size":20,"time_months":12,"equipment":"sequencing","ethics":"IRB approved"},
 "prior_art":[{"source_id":"A1","title":"CRISPR screens in CAR-T cells","abstract":"CRISPR knockout screens identified regulators of CAR-T persistence.","year":2021}]}
```

示意输出（示例）：`{"status":"success","result":{"novelty_assessment":{"level":"low"},"feasibility":{"verdict":"feasible_with_conditions"}}}`。不代表任何官方固定案例结果。


## 交付保证与评分对齐

调用顺序（固定）：

1. 先运行包内脚本（若存在）：`python scripts/run_skill.py`（默认读 `/input/case.json`，写 `/app/output/result.json`）；路径不同时用 `--case` / `--out` 指定。
2. 再完成脚本无法自动完成的实质工作（译文、论述、图表、修订、结论等），把结果写回 `result.json` 对应字段。
3. 最后自检：`case_id` 与输入一致；`output_contract` 每个字段都存在；`status` 为 `completed`（仅在确实缺输入时为 `partial`）；无 `pending` 占位；数字、引用、来源可逐条回溯。

运行保证：

- 输入缺失、JSON 损坏、字段异常、输出目录不存在时，仍须写出结构化 `result.json` 并正常结束，不得崩溃或非零退出。
- 不联网、不伪造数据、不声称平台评分或官方案例结果。
- 交付物必须是可直接编辑与复核的成品，而不是流程说明。

评分对齐（本题五个维度）：

- 实际效果（40）：完整产出任务要求的最终成品，覆盖全部输入条目，可直接进入修改流程。
- 使用增益（25）：体现相对基础 Agent 的可验证改进（结构化、术语/数字/引用核对、可编辑性）。
- 创新增益（15）：保留方法学增量（分块、对齐、二次校验、版本比对等），并用结果证明其价值。
- 可靠体验（10）：异常输入有明确降级与说明，不同长度/文体/重复运行下稳定产出。
- 生态贡献（10）：用途、调用、输入输出、限制、示例、维护信息齐全，资源可被他人复用。

## 最终交付强制要求

1. **调用 Agent 必须交付成品，不是流程说明**：脚本产出只是索引、核对或规格骨架；调用 Agent 必须在同一 `result.json` 中补齐本题要求的最终产物（正文/译文/审稿意见/综述/分析结论/图表源文件与导出件/幻灯片页内容与讲稿/实验方案等）。交付字段为空、只有标题骨架，或含 `pending`、`TODO` 之类占位，一律视为未完成。
2. **必须覆盖全部输入条目**：输入中的每个章节、问题、文献、图、页面、指标都要有对应条目，不得只处理示例或首条；确实缺失的条目写入 `uncertainty` / `limitations` 并说明原因，不得静默跳过。
3. **必须自检后再交付**：`case_id` 与输入一致；`output_contract` 每个字段都存在；状态值取本题契约规定的枚举；数字、单位、引用、来源可逐条回溯；结果内部无自相矛盾。
4. **参数等价**：`python scripts/run_skill.py --case <输入> --out <输出>` 与 `--output <输出>` 等价；默认 `/input/case.json` → `/app/output/result.json`。
5. **平台用 3 个固定案例分别运行**：逻辑要由输入驱动，不针对某一份示例硬编码；字段命名差异走别名匹配与显式降级，并在 `uncertainty` 记录假设。
