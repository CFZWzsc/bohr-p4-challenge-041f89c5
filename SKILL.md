---
name: research-proposal-novelty-assessment
description: Use when a research idea must be assessed before funding or execution: falsifiable restatement, batch-bounded prior-art overlap, differentiators, feasibility checks, typed risks and revisions.
---

# 科研选题与创新性评估

## 用途与适用条件

判断选题是否可检验、先行研究做到哪、增量在哪、现有条件能否做成；四项产物必须齐全且相互一致。

- 适用前提：`case.json` 提供选题（`proposal`/`idea`/`hypothesis`/`research_question`/`topic`）与先行研究数组，可选 `resources`/`constraints`（数据、样本量、时间、设备、技能、伦理）。
- 不适用：替代查新/专利检索或伦理审查；给出资助结论；生成实验方案、样本量计算或预算。

## 输入

| 输入 | 用途 |
|---|---|
| `/input/case.json` | `prior_art`/`records`/`papers`（`source_id`、`title`、`abstract`、`year`、`doi`）；`resources`/`constraints` |
| `task.md` | 可选；选题缺失时取前几行兜底 |
| `--work` | 默认 `/app/work` |

## 处理流程

1. **问题定义**：抽取干预、结局指标、人群与对照，判断是否同时具备可测结局与对照；标出 `better`/`有效` 等未操作化词。
2. **先行研究比较**：逐条计算共享词项比例，分 `direct_overlap`/`partial_overlap`/`adjacent`；新颖度只对提供批次有效。
3. **创新点识别**：把未被最近先行研究覆盖的词项列为候选差异点，逐条判定是否已被覆盖，不宣称绝对新颖。
4. **可行性**：逐项检查数据、样本量、时间、方法设备与伦理；区分 `blocker` 与 `warning` 并给 `verdict`。
5. **冲突与空白**：登记结论相反或无法直接比较的记录及取舍理由；空白仅限批内观察。
6. **风险、修改与评分卡**：风险带 `type`/`severity`/`detail`；建议可执行；评分卡公开计算口径，不作资助或伦理决策。

## 输出契约

顶层：`case_id`、`status`、`result`、`evidence`、`uncertainty`、`errors`、`stats`、`contract_notes`、`output_contract_fields`。

`status`：无选题或无先行研究 → `insufficient_input`；选题不可检验或缺资源声明 → `partial`；两者齐备 → `success`；解析或运行失败 → `failed`（唯一枚举，不使用其他取值）。

`result` 必含：`proposal`、`testable_form`、`novelty_assessment`、`prior_art_table`、`differentiators`、`feasibility`、`risks`、`recommended_revisions`、`research_gaps`、`scorecard`、`limitations`、`change_log`。调用 Agent 必须补齐（`output_contract` 声明时置于顶层，否则并入 `result`）：

| 字段 | 内容 |
|---|---|
| `retrieval_scope` | `query`/`inclusion`/`exclusion`/`batch_size`，说明本批文献如何进入评估；无外部检索须明示 |
| `comparison[]` | `source_id`、`locator`、`shared_terms`、`overlap_class`、`not_comparable_reason` |
| `innovation_checks[]` | `claim`、`covered_by`、`verdict`（`covered`/`partially_covered`/`not_found_in_batch`）、`basis` |
| `conflicting_evidence[]` | `claim`、`supporting`、`conflicting`、`resolution` |
| `synthesis` | 带条件的总体判断 `go`/`conditional_go`/`hold`、前提与停止条件 |
| `needs_human_confirmation[]` | `item`、`locator`、`reason` |

输入 `output_contract` 的每个字段名写到顶层；脚本未产出者置 `null` 并记 `contract_notes`，调用 Agent 必须用真实结果替换，确实无法产出才保留 `null`。

## 证据要求

- `evidence` 每条含 `source_id`、`locator`、`quote`；`locator` 用输入 JSON Pointer（如 `/prior_art/0`），不是页码。
- `differentiators`、`innovation_checks` 与可行性结论都能回到具体记录或声明字段；无来源判断写入 `needs_human_confirmation`。
- 不编造文献、年份、DOI、样本量或伦理批号。

## 异常处理

| 情形 | 处理 | 标记 |
|---|---|---|
| 无先行研究 | 不给新颖度结论 | `status=insufficient_input` |
| 无对照或无结局指标 | 判不可检验 | `testable_form.tests.is_falsifiable=false` |
| 无资源声明 | 可行性只做部分检查 | `status=partial`，`uncertainty.type=no_resources` |
| 样本不足 | 记 blocker | `feasibility.blockers` |
| 涉及人或动物无伦理声明 | 记 warning | `check=ethics` |
| 记录无法直接比较 | 保留并说明原因，不强判优劣 | `not_comparable_reason` |
| 输出不可写 | stderr 报错，退出码 3 | 无静默成功 |

## 限制

新颖度是词项重叠，不是查新或专利检索；可行性只覆盖已声明资源；分值为启发式，不用于资助、伦理或人事决策；不生成实验方案、样本量计算或预算。

## 最小调用示例（示例，非正式案例结果）

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /input/case.json --out /app/output/result.json --work /app/work
# --output 与 --out 等价
```

```json
{"case_id":"demo-pr-01","proposal":"A CRISPR knockout screen will identify genes that improve CAR-T persistence versus standard CAR-T in patients.","resources":{"data":"primary T cells","sample_size":20,"time_months":12,"equipment":"sequencing","ethics":"IRB approved"},"prior_art":[{"source_id":"A1","title":"CRISPR screens in CAR-T cells","abstract":"CRISPR knockout screens identified regulators of CAR-T persistence.","year":2021}]}
```

示意输出（示例）：`{"status":"success","result":{"novelty_assessment":{"level":"low"},"feasibility":{"verdict":"feasible_with_conditions"}}}`。不代表任何官方固定案例结果。

## 交付与自检

1. **四项交付齐全**：问题定义、已有工作比较、创新点识别、可行性判断都要有成品内容，不能只有标题骨架或 `pending`/`TODO`。
2. **逐条回溯**：数字、引用、样本量、伦理声明与覆盖判定都能回到 `locator` + `quote`。
3. **契约自检**：`case_id` 与输入一致；`output_contract` 每字段存在；`status` 只取四个枚举；重复运行结果相同。
4. **输入驱动**：不针对示例硬编码；缺失输入显式降级并记录假设；不联网、不声称官方评分。
