# 方法与打分口径

本文件描述 `scripts/sk_entry.py` 实际执行的确定性算法。所有阈值来自 `assets/policy.json`，缺省值与脚本内置值一致。

## 1. 记录发现与归一化

- 优先读取 `prior_art` / `records` / `papers` / `literature` / `sources` / `documents` / `citations` 中的对象数组。
- 若上述键不存在，则在 `case.json` 内递归查找含 `title`/`abstract`/`doi`/`year`/`authors` 的对象，深度上限 7，条数上限 2000。
- 归一化字段：`source_id`（缺失时 `A01` 起编号）、`locator`（`/<键>/<下标>`）、`title`、`abstract`、`year`、`doi`、`venue`。
- `year` 只接受 1800–2100 的整数或文本中第一个四位年份；否则记为缺失。

## 2. 词项与重叠

1. 英文按 `[A-Za-z][A-Za-z0-9-]{2,}` 切词并去停用词；中文按连续汉字的相邻二元组切分。
2. 提案词项去重后最多取 20 个（`caps.proposal_terms`）。
3. 记录覆盖比例 `ratio = |共享词项| / |提案词项|`。
4. 共享二元短语（记录短语出现在提案词项串中）每个加 `phrase_bonus=0.08`。
5. `effective = min(1.0, ratio + 0.08 × 短语数)`，四舍五入到 3 位。
6. 分档：`direct_overlap` ≥ 0.45；`partial_overlap` ≥ 0.25；其余 `adjacent`。

## 3. 新颖度分值

```
score = clamp(0, 100, round(100 − 110 × best_overlap − 6 × close_works))
level = high (score ≥ 65) / moderate (score ≥ 40) / low (其余)
```

- `best_overlap` 为批内最高重叠度，`close_works` 为 `direct_overlap` + `partial_overlap` 条数。
- 分值只表示「相对本批最近工作的词项距离」，`novelty_assessment.scope` 固定声明这不是全局新颖性检索。

## 4. 可检验性

- 干预词：`knockout`、`inhibitor`、`stimulation`、`treatment`、`dose`、`敲除`、`抑制` 等线索。
- 结局指标：`%`、`score`、`endpoint`、`metric`、`assay`、`sensitivity`、`auc`、`p<`、`rate`、`yield`、`灵敏度`、`指标` 等线索。
- 对照：`versus`、`vs`、`compared`、`control`、`placebo`、`对照`、`比较`。
- 人群：`in adults`、`in patients`、`among`、`在…人群` 等上下文片段。
- `is_falsifiable = 有结局指标 and 有对照`；`vague_terms` 记录 `better`、`improve`、`有效`、`显著`、`创新` 等未操作化词。

## 5. 创新点判定

| 陈述 | `covered` 条件 | `partially_covered` 条件 | 其余 |
|---|---|---|---|
| 干预本身新颖 | 任一记录含干预词 | — | `not_found_in_batch` |
| 结局未被测量 | 任一记录含结局指标 | — | `not_found_in_batch` |
| 干预×结局组合未占据 | 同一记录同时含两者 | 两者分别出现但从未共现；或只出现一半 | `not_found_in_batch` |
| 差异词项 | 词项在其他记录出现（则不算差异） | — | 全部记录均不含该词 → `not_found_in_batch` |

所有判定都是「批内」结论，`basis` 字段写明匹配范围；`covered_by` 只列真实命中的 `source_id`。

## 6. 冲突证据

1. 只在与 `outcome_indicators` 相关的记录上检测。
2. 负向线索优先（`no significant`、`did not`、`no difference`、`无显著`、`未改善` 等），其次正向线索（`improved`、`effective`、`提高`、`优于` 等）。
3. 正向与负向记录两两配对（各最多 3 条），`resolution` 固定 `unresolved`，双方均带 `locator` 与 `quote`。
4. 无相反配对时输出一条 `checked` 记录与 `not_applicable` 说明，明确「本批未检出冲突 ≠ 领域内一致」。

## 7. 可行性

| 检查 | 判定 |
|---|---|
| `data_available` | 有 `data`/`dataset`/`samples` 声明 → `pass`，否则 `blocker` |
| `sample_size` | 提案含 `n=`/`sample size of N` 时与声明值比较；不足 → `blocker`，仅提案有需求 → `warning` |
| `time` | 声明月份 ≥ 6 → `pass`，否则 `warning` |
| `methods_supported` | 提案提到的方法未出现在资源声明中 → `warning` |
| `ethics` | 涉及人或动物时，资源含 `ethic`/`irb`/`consent`/`伦理` → `pass`，否则 `warning` |

`verdict`：有 blocker → `not_feasible_as_stated`；仅 warning → `feasible_with_conditions`；否则 `feasible_as_stated`。

## 8. 综合结论

| 条件（按顺序） | `synthesis.verdict` |
|---|---|
| 无选题或无先行研究 | `hold` |
| 存在 feasibility blocker | `hold` |
| 新颖度为 `low` 或不可检验 | `conditional_go` |
| 其余 | `go` |

`conditions` 至少包含「最近工作需专家复核」；`stop_conditions` 固定列出三条（组合已被报告、blocker 无法解决、结局不可测）。

## 9. 状态判定

| `status` | 条件 |
|---|---|
| `insufficient_input` | 无选题或无先行研究 |
| `partial` | 不可检验，或无资源声明（可行性只做部分检查） |
| `success` | 有计划、有先行研究、可检验、有资源声明 |
| `failed` | case 损坏或运行异常；仍写出完整契约键并 exit 0 |

## 10. 契约投影

1. 顶层已有同名字段 → 直接使用。
2. `result` 内有同名字段 → 提升到顶层（`output_contract_fields.sources[键]="result"`）。
3. 已知别名 → 用真实结果填充并记 `contract_extras.aliases_applied`。
4. 其余 → `not_determinable` 对象（含 `field`、`reason`、`closest_produced_fields`、`next_action`），并记 `contract_extras.not_determinable_keys`。

## 11. 确定性

无随机数、无时间戳、无网络、无环境依赖排序；记录按输入顺序，输出按重叠度与 `source_id` 排序，重复运行字节级一致。
