# 方法与打分口径

本文件描述 `scripts/sk_entry.py` 实际执行的确定性算法。所有阈值来自 `assets/policy.json`，缺省值与脚本内置值一致。

## 1. 记录发现与归一化

- 首选键：`prior_art` / `records` / `papers` / `literature` / `sources` / `documents` / `citations` / `known_works` / `prior_works` / `candidates` / `search_results` / `screening_records` / `bibliography`。
- 若上述键不存在，则在 `case.json` 内递归查找含 `title`/`abstract`/`doi`/`year`/`authors` 的对象，深度上限 7，条数上限 2000。
- 归一化字段：`source_id`（缺失时 `A01` 起编号）、`locator`（`/<键>/<下标>`）、`title`、`abstract`、`year`、`doi`、`venue`、`date_raw`、`date_type`、`decision`、`duplicate_of`、`reason_code`、`criteria_ids`。
- `year` 解析移植自同赛道 `073af7d3` 的 `parse_year()`：先匹配 1800–2100 的四位年（`1[89]\d{2}|20\d{2}`），再退回整数；避免把「2021-03-04」中的月份/日期当成首位数字。解析不到即视为缺失。
- `date_type` 由 `date_raw` 归类：含 `preprint`/`arxiv`/`biorxiv`/`medrxiv` → `preprint`；含 `online`/`first`/`ahead of print` → `online-first`；含四位年 → `published`；否则 `unknown`。

## 1b. 输入原文的读取与挂载

1. 递归扫描输入根（跳过 `__pycache__`/`.git`/`node_modules`，跳过根目录的 `case.json` 与 `task.md`），只取 `.md/.markdown/.txt/.text/.csv/.json/.pdf`；按相对路径排序，最多 40 个文件、单文件 400k 字符、原始大小 2MB 上限。
2. 文本文件按 UTF-8（非法字节替换）读入，统一换行、去行尾空白、压缩 3 个以上空行为 1 个空行；pdf 调用 `pdftotext -layout`，不可用或失败则记 `unparsed` 与原因码（`pdftotext_unavailable` / `pdftotext_exit_N` / `read_failed` / `file_too_large` / `empty_text`）。
3. 解析成功的文件按排序编为 `S1`、`S2`…；`input_manifest.sources_found` 为成功数，`unparsed[]` 列出失败文件与原因，`skipped[]` 列出被上限或非普通文件跳过的条目。
4. 挂载顺序（命中即停）：DOI 精确（去 `https://doi.org/`/`doi:` 前缀、小写）→ 归一化标题（只留字母/数字/汉字）在源文本中出现且长度 ≥12 → 标题词项与文件名词项重叠 ≥ max(2, round(0.6×标题词项数)) → `difflib.get_close_matches` 标题与文件名相似度 ≥0.6。
5. 命中后记录 `source_file`/`source_key`，`text_of()` 优先返回原文（空白归一化），否则退回摘要、再退回标题。

## 1c. 证据定位符

- `case_locator` 始终是 JSON Pointer（`/proposal`、`/prior_art/0`）。
- `locator` 在记录匹配到源文件时升级为 `S<k>#P<n>`：在源文本中按空行切段，用引文每 30 字符滑窗探测首个命中段；无命中退回 `S<k>`（文件级）。
- 引文超 `caps.quote_chars` 时只取前缀并置 `truncated=true`；`quote_verified` 为引文对所引文本的逐字包含校验。

## 2. 词项与重叠

1. 英文按 `[A-Za-z][A-Za-z0-9-]{2,}` 切词并去停用词；中文按连续汉字的相邻二元组切分。
2. 提案词项去重后最多取 20 个（`caps.proposal_terms`）。
3. 记录覆盖比例 `ratio = |共享词项| / |提案词项|`。
4. 共享二元短语（记录短语出现在提案词项串中）每个加 `phrase_bonus=0.08`。
5. `effective = min(1.0, ratio + 0.08 × 短语数)`，四舍五入到 3 位。
6. 分档：`direct_overlap` ≥ 0.45；`partial_overlap` ≥ 0.25；其余 `adjacent`。

## 2b. 检索口径、筛选台账与去重

1. `criteria[]`：用例给出 `inclusion_criteria`/`inclusion`/`exclusion_criteria`/`exclusion` 等键时逐条读入（`origin=case`，编号 `I1..`/`X1..`）；否则用派生四条：I1 可识别（有标题或 DOI）、I2 可用标题/摘要/年份比较（缺字段记为差距而非剔除）、X1 重复（DOI 或归一化标题+年份）、X2 非记录/无标识。
2. `applied_protocol`：从 `search_protocol`/`retrieval_protocol`/`screening_protocol`/`protocol` 或顶层 `year_range`/`languages`/`designs`/`publication_types` 读取；完全未声明时写 `origin=derived` 并明示「范围仅限本批、未做外部检索」。
3. `screening_log[]` 每条记录一行：`source_id`、`doi`、`title`、`stage`（`deduplication`/`eligibility`）、`decision`（`include`/`exclude`/`duplicate`）、`reason_code`（`ELIGIBLE`/`NO_IDENTIFIER`/`DUPLICATE_DOI`/`DUPLICATE_TITLE_YEAR`）、`criteria_ids`、`duplicate_of`、`quote`、`quote_verified`、`locator`、`case_locator`、`source_file`。
4. 去重键：优先 `doi:<小写 DOI>`，否则 `title:<归一化标题>|<year 或 na>`；保留首次出现的记录，后续同键记录 `decision=duplicate` 并填 `duplicate_of`。
5. `flow`：`identified = duplicates + unique`；`unique = screened`；`screened = included + excluded`；布尔 `arithmetic_closure` 记录校验结果。后续比较、创新判定、冲突检测只用 `included` 记录。
6. `hits_per_query[]` 不再是记录总数：把查询串切成关键词（≥4 位英文/≥2 字中文，去布尔词），统计标题+摘要+已挂载原文中命中任一关键词的**纳入记录**数，并声明这是离线匹配、未查询任何数据库。

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

## 12. 评审意见、面覆盖与成文评审

`result.findings[]` 全部由既有中间结果派生，不引入新判断：

| 来源 | `aspect` | `category` | `severity` | `status` |
|---|---|---|---|---|
| 无结局指标 / 无对照（有选题时） | `question_definition` | `insufficient_evidence` | `critical` / `major` | `confirmed` |
| `testable_form.vague_terms`（最多 3 条） | `question_definition` | `norm_issue` | `major` | `confirmed` |
| `direct_overlap` / `partial_overlap`（最多 4 条） | `prior_work_comparison` | `norm_issue` | `critical` / `major` | `confirmed` |
| `comparison[].not_comparable_reason`（最多 4 条） | `prior_work_comparison` | `insufficient_evidence` | 标题级 `major`，其余 `minor` | `pending` |
| `innovation_checks` 中 `covered` / `partially_covered` | `novelty_identification` | `fact_error` / `insufficient_evidence` | `major` | 有命中记录 `confirmed`，否则 `pending` |
| 差异词项 `not_found_in_batch`（最多 2 条） | `novelty_identification` | `suggestion` | `minor` | `pending` |
| `feasibility.checks` 的 `blocker` / `warning` | `feasibility_judgment` | `insufficient_evidence` | `critical` / `major` | `pending` |
| 纳入记录未匹配原文（汇总 1 条） | `evidence_traceback` | `insufficient_evidence` | `major` | `pending` |
| `conflicting_evidence` 中未裁决的配对（1 条） | `evidence_traceback` | `insufficient_evidence` | `major` | `pending` |

- 上限 30 条，编号 `F01..` 按派生顺序生成，保证同输入同编号。
- `status`：`quote` 与 `location` 均能在材料中逐字确认的写作 `confirmed`；需要补全文、补资源声明或需专家裁决的一律 `pending`，不以推断值补齐。
- `aspect_coverage[]`：某面缺前置材料（无选题 / 无记录 / 无资源 / 无证据）→ `gap` 并写明原因；有 findings → `checked`；可查但无问题 → `checked_no_issue`。
- `review_report` 为六段中文成文（总体结论、五面小结、材料与筛选、问题清单、待复核、使用边界），长度 ≥200 字，所有数字取自本次 `result`，不写死。

## 13. 阈值来源与失败分级

### 13.1 阈值来源

| 参数 | 值 | 来源 | 用途 |
|---|---|---|---|
| `overlap.direct_threshold` | 0.45 | `assets/policy.json` | 判 `direct_overlap` |
| `overlap.partial_threshold` | 0.25 | `assets/policy.json` | 判 `partial_overlap` |
| `overlap.phrase_bonus` | 0.08 | `assets/policy.json` | 每个共享二元短语的加成 |
| `caps.proposal_terms` | 20 | `assets/policy.json` | 提案词项上限 |
| `caps.quote_chars` | 240 | `assets/policy.json` | 引文截断长度 |
| `caps.max_comparison_rows` | 200 | `assets/policy.json` | `comparison` 行数上限 |
| `caps.max_differentiators` | 15 | `assets/policy.json` | 差异词与创新检查上限 |
| `caps.max_manifest_files` | 200 | `assets/policy.json` | 清单文件数上限 |
| `caps.manifest_hash_bytes` | 1 MB | `assets/policy.json` | 哈希取样字节 |
| 分值系数 110 / 6，等级 65 / 40 | — | 脚本常量 | `score` 与 `level` |
| 样本 ≥20、工期 ≥6 月 | — | 脚本常量 | 可行性 `sample_size` / `time` |
| 源文件 40 个 / 40 万字符 / 2 MB | — | 脚本常量 | 材料读取上限 |
| 引文滑窗 30 字符 | — | 脚本常量 | `S<k>#P<n>` 段落定位 |

所有阈值在 `precheck` 阶段确定（policy 或常量），不随单次输入调整；`severity_rubric.declared_at` 显式记录这一点。

### 13.2 失败分级

| 级别 | 触发条件 | 对外表现 |
|---|---|---|
| L0 `failed` | `case.json` 不可读 / 运行异常 | 仍写 `result.json` 与契约骨架，`errors[]` 给出原因，exit 0 |
| L1 `insufficient_input` | 无选题或无可用记录 | 不产出新颖度/可行性结论，`uncertainty` + `research_gaps` 说明 |
| L2 `partial` | 不可检验，或无资源声明 | 结论带条件，可行性只做已声明部分 |
| L3 `success` + `pending` findings | 记录只有标题/摘要、缺原文，或冲突未裁决 | 结论成立但证据深度降级，逐条标 `pending` |
| L4 `success` + 全 `checked` | 原文齐全、`quote_verified=true` | 可全链回链到 `S<k>#P<n>` |

证据深度阶梯（由高到低）：源文件段落 `S<k>#P<n>` → 源文件级 `S<k>` → 摘要 → 仅标题 → 无。阶梯下降不阻断结论，但必须同时出现在 `uncertainty` 与 `findings[].aspect=evidence_traceback` 中。

## 14. 产物与自检

| 产物 | 内容 |
|---|---|
| `result.json` | 主契约（含 `review_report`、`aspect_coverage`、`findings`、`severity_rubric`） |
| `report.md` | 第 0 节为成文评审，其后为各面明细与 `findings` / `aspect_coverage` / `screening_log` 表格 |
| `evidence.csv` | 列：`evidence_id`、`kind`、`source_id`、`locator`、`case_locator`、`source_file`、`decision`、`reason_code`、`criteria_ids`、`year`、`overlap`、`overlap_class`、`quote_verified`、`quote` |
| `screening_log.csv` | 每条记录一行：`source_id`、`doi`、`title`、`stage`、`decision`、`reason_code`、`criteria_ids`、`duplicate_of`、`quote_verified`、`quote`、`locator`、`case_locator`、`source_file` |
| `provenance.json` | `evidence_id → locator/case_locator/source_file/quote_verified`、`finding_id → location/evidence`、`aspect_coverage`、`flow`、`source_files` |

每个产物写盘后先 `os.path.exists` 自检，通过才登记到 `result.artifacts`；写失败不伪造条目。
