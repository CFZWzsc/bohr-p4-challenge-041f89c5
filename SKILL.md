---
name: research-proposal-novelty-assessment
description: Use when a research idea must be judged before funding or execution — restate it as a falsifiable claim, compare it record by record with a supplied prior-art batch, mark each innovation statement as covered or not found, check feasibility against declared resources, keep conflicting evidence unresolved, and write a contract-complete result.json. Runs offline with the Python standard library only.
---

# 科研选题与创新性评估

## 用途

把「一个研究设想 + 一批给定先行研究 + 已声明的资源条件」推进到可决策、可复核的评估结论，交付四类相互一致的产品：

1. **问题定义**：把设想改写成含干预、结局指标、人群与对照的可检验表述，标出不可操作化的措辞。
2. **已有工作比较**：对每条先行研究记录给出共享词项、重叠度、重叠类别，以及**无法直接比较的原因**。
3. **创新点识别**：把「干预新颖 / 结局未被测量 / 干预×结局组合未被占据 / 某差异词项」逐条判定为 `covered`、`partially_covered` 或 `not_found_in_batch`，并给出 `covered_by` 与判定依据。
4. **可行性判断**：只对**已声明**的数据、样本量、时间、方法设备与伦理逐项检查，区分 `blocker` 与 `warning`，给出带条件的 `verdict`。

在此之上补齐题面要求的另外两类内容：**冲突证据**（相反结论并列、不裁决）与**综合结论**（`go` / `conditional_go` / `hold` + 前提 + 停止条件），并把所有判断回链到输入 JSON Pointer 或输入目录下的源文件段落（`S1#P2`）。

```text
result.json
  ├─ review_report        中文成文评审（总体结论 / 五面小结 / 材料与筛选 / 问题清单 / 待复核）
  ├─ findings[]           逐条评审意见（aspect / category / severity / quote / location / evidence / status）
  ├─ aspect_coverage[]    五个面逐一 checked / checked_no_issue / gap
  ├─ severity_rubric      precheck 阶段声明的严重度分级
  └─ retrieval_scope      criteria[] / screening_log[] / flow（算术闭合）/ applied_protocol
```

本 Skill 的新颖度是**批内有界**的词项重叠判断，不是查新、专利检索或专家评审的替代品。

## 适用条件

- 输入提供选题文本（`proposal` / `idea` / `hypothesis` / `research_question` / `topic` / `aim` 之一）与至少 1 条先行研究记录；记录可位于 `prior_art` / `records` / `papers` / `literature` / `sources` / `documents` / `citations`，也可嵌套在更深的对象中。
- 记录含 `title`、`abstract`、`year`、`doi`、`venue` 中的任意字段即可参与比较；缺摘要的记录按标题比较并显式降级。
- 需要离线、确定性、仅标准库运行，且同一输入重复运行结果一致。
- 需要「判断是否值得继续、增量在哪、条件够不够」这类立项前评估，而不是写综述或做实验设计。

## 不适用

- 替代正式查新、专利 FTO 检索、伦理审查或基金评审结论。
- 输入只有选题、没有任何先行研究，却要求给出「全球首创」结论。
- 要求生成实验方案、样本量计算、预算模型或统计分析计划。
- 要求对相反结论做方法学裁决（本 Skill 只并列保留，裁决写入 `needs_human_confirmation`）。
- 要求联网补文献、核实 DOI 真实性或撤稿状态。

## 输入形态

```text
<input>/
  case.json        # 必需；缺失时按空输入处理，仍然 exit 0 并写出诚实状态
  task.md          # 可选；选题文本缺失时从中提取正文，并登记在 retrieval_scope.task_text_used
  <其他材料>        # md/txt/csv/json 读为文本，pdf 用 pdftotext 转换；按 DOI/标题/文件名挂到记录，
                   # 解析失败者列入 input_manifest.unparsed，其余登记到 input_manifest.files
```

`case.json` 关键字段：

| 字段 | 说明 |
|---|---|
| `case_id` | 原样回写到 `result.json`；缺失时为 `unknown` |
| `proposal` 等 | 选题原文；也可由 `task.md` 兜底 |
| `prior_art[]` 等 | 先行研究记录；`source_id` 缺失时按 `A01`、`A02` 编号 |
| `resources` / `constraints` | 数据、样本量、月份、设备/技能、伦理声明 |
| `output_contract` | 对象、字段名列表或 JSON Schema（含 `properties`）均可 |

## 调用方式

平台安装目录（`/skills/weekly-skill`）下：

```bash
python3 /skills/weekly-skill/scripts/sk_entry.py --input /input --work /app/work --out /app/output
```

等价薄封装（参数完全一致）：

```bash
python3 /skills/weekly-skill/scripts/run_skill.py --input /input --work /app/work --out /app/output
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--input` | `/input` | 输入目录，或直接指向 `case.json`；兼容旧名 `--case` |
| `--work` | `/app/work` | 工作目录；主输出不可写时的回退位置 |
| `--out` | `/app/output` | 输出目录（写 `result.json`）或 `.json` 文件路径；兼容旧名 `--output` |

无第三方依赖、不联网、无状态。**任何情况下退出码为 0**，并总是尝试写出 `result.json`。

## 输出契约

`result.json` 顶层固定字段：

| 字段 | 内容 |
|---|---|
| `case_id` | 与输入一致（缺失时为 `unknown`） |
| `status` | `success` / `partial` / `insufficient_input` / `failed`，唯一枚举 |
| `result` | 业务结果对象（见下表） |
| `evidence[]` | `evidence_id`、`kind`、`source_id`、`locator`、`case_locator`、`source_file`、`quote`、`quote_verified`、`truncated` |
| `uncertainty[]` | `type` + `detail`，覆盖无选题、无先行研究、无资源、不可检验、标题-only 记录、无原文/原文未解析/未匹配、批内有界 |
| `errors[]` | 输入或运行错误；无错误时为空数组 |
| `stats` | 记录数、去重数、纳入数、原文数、证据数、findings 数、已检查面数等 |
| `input_manifest` | 对象：`files[]`（相对路径、字节、sha256、哈希范围）、`sources_found`、`source_files[]`、`unparsed[]`、`skipped[]` |
| `run` | 入口、是否联网、是否确定性、是否读取原文、policy 版本（不写机器路径） |
| `contract_notes` | `output_contract` 每个键的满足方式 |
| `contract_extras` | `contract_shape`、`declared_keys`、`not_determinable_keys`、`aliases_applied`、`uninterpreted_input_keys` |
| `output_contract_fields` | `provided`、`present`、`sources`、`not_determinable` |

`result` 内固定字段：

| 字段 | 内容 |
|---|---|
| `proposal` | 原样选题文本（归一化空白） |
| `review_report` | 中文成文评审（≥200 字），含总体结论、五面小结、材料与筛选计数、问题清单、待复核、使用边界 |
| `aspect_coverage[]` | 五个面各一行：`aspect`、`label`、`status`（`checked` / `checked_no_issue` / `gap`）、`findings`、`severity_max`、`note` |
| `findings[]` | `finding_id`、`aspect`、`category`（`fact_error` / `insufficient_evidence` / `norm_issue` / `suggestion`）、`severity`、`quote`、`location`、`evidence`、`revision_suggestion`、`status`（`confirmed` / `pending`） |
| `severity_rubric` | `levels[]`、`declared_at=precheck`、`category_enum`、`status_enum` |
| `testable_form` | `restated`、`population_hint`、`intervention_terms`、`outcome_indicators`、`has_comparator`、`vague_terms`、`tests`（四个布尔值 + `is_falsifiable`） |
| `novelty_assessment` | `score`、`level`、`best_overlap`、`close_works`、`scope` |
| `prior_art_table[]` | 逐记录共享词项、共享短语、重叠度、关系类别 |
| `comparison[]` | `source_id`、`locator`、`shared_terms`、`shared_phrases`、`overlap`、`overlap_class`、`comparison_fields`、`not_comparable_reason` |
| `differentiators[]` | 未被最近工作共享词项覆盖的候选差异词 |
| `innovation_checks[]` | `claim`、`covered_by`、`verdict`、`basis` |
| `conflicting_evidence[]` | `claim`、`supporting[]`、`conflicting[]`、`resolution`；无冲突时给出 `checked` + `not_applicable` 说明 |
| `feasibility` | `checks[]`、`blockers[]`、`warnings[]`、`verdict` |
| `synthesis` | `verdict`、`conditions[]`、`stop_conditions[]`、`basis[]`、`decision_scope` |
| `research_gaps[]` | 批内的空白观察及其依据（不是领域空白） |
| `risks[]` / `recommended_revisions[]` | 带类型与严重度的风险、可执行修改建议 |
| `needs_human_confirmation[]` | `item`、`locator`、`reason`：需要全文或专家判断的事项 |
| `retrieval_scope` | `query`、`query_basis`、`criteria[]`、`criteria_origin`、`screening_log[]`、`flow`（`identified/duplicates/unique/screened/excluded/included` + 闭合校验）、`applied_protocol`、`hits_per_query[]`（真实关键词命中）、`sources_found`、`source_files[]`、`unparsed_sources[]`、`coverage_gap[]` |
| `scorecard` | 透明的启发式分值及权重说明，不用于资助或伦理决策 |
| `method` / `limitations` / `change_log` | 判定规则、限制、本次处理步骤 |

`output_contract` 处理规则：

1. 每个契约键都出现在**顶层**；同名业务字段直接复用，`result` 内的同名同义字段提升到顶层。
2. 认识的别名（如 `report`/`summary` → `synthesis`、`prior_art` → `comparison`、`conflicts` → `conflicting_evidence`、`gaps` → `research_gaps`、`notes` → `uncertainty`）按真实结果填充，并记入 `contract_extras.aliases_applied`。
3. 无法映射的键写**结构化「无法判断」对象**（`status=not_determinable`、`field`、`reason`、`closest_produced_fields`、`next_action`），不留 `null`、不留空容器，并列入 `contract_extras.not_determinable_keys`。

## 处理流程

1. **读取与盘点**：解析 `case.json`；递归读取输入目录下的 md/txt/csv/json（pdf 走 `pdftotext`），按 DOI、标题、文件名挂到记录；无法解析者记 `unparsed`。汇总 `input_manifest` 与 `batch_size`。
2. **问题定义**：抽取干预动作、可测结局、人群线索与对照；未操作化词（`better`、`有效`、`显著` 等）列入 `testable_form.vague_terms`。
3. **筛选与去重**：声明 `criteria[]`（用例给的，或派生的 I1/I2/X1/X2）、`applied_protocol`；按 DOI 或「归一化标题+年份」去重并记 `duplicate_of`；逐记录写 `screening_log[]`，`flow` 必须算术闭合。
4. **先行研究比较**：对每条记录计算「提案词项被记录覆盖的比例 + 共享二元短语加成」；按 `direct_overlap`（≥0.45）、`partial_overlap`（≥0.25）、`adjacent` 分档；缺摘要、无共享词、缺年份分别写 `not_comparable_reason`。
5. **创新点判定**：对干预、结局、干预×结局组合、以及批内完全不出现的差异词逐条判定；`covered_by` 只列真实命中的 `source_id`，不宣称绝对新颖。
6. **冲突证据**：在与结局词项相关的记录上检测正/负极性；相反记录成对保留，`resolution` 固定 `unresolved`，并列出 `checked` 记录及其极性。
7. **可行性**：数据、样本量、时间、方法设备、伦理逐项检查；缺资源声明时只做部分检查并降级为 `partial`。
8. **评审成文**：由 `prior_art_table` / `innovation_checks` / `feasibility.blockers` 派生 `findings[]`，用 precheck 声明的 `severity_rubric` 定级，逐面写 `aspect_coverage[]`，再生成 `review_report`。
9. **综合与交付**：由可检验性、批内新颖度、可行性与已覆盖创新陈述推出 `go` / `conditional_go` / `hold`，写条件与停止条件；同时给出 gaps、risks、revisions、`needs_human_confirmation`，并写 `report.md`、`evidence.csv`、`screening_log.csv`、`provenance.json`。

阈值与上限由 `assets/policy.json` 提供（重叠阈值、引文长度、比较行数、清单上限），脚本缺省值与之相同。

## 证据要求

- `evidence` 每条含 `source_id`、`locator`、`quote`。`locator` 两种形态：`/prior_art/0`（`case.json` 的 JSON Pointer，选题为 `/proposal`）或 `S1#P2`（输入目录下第 1 份已解析源文件的第 2 段）；`case_locator` 始终保留 JSON Pointer 以便回溯。
- `quote` 必须是所引文本的**精确子串**；超长时截取前缀并置 `truncated=true`，`quote_verified` 记录子串校验结果。
- 源文件匹配按 DOI → 标题归一化子串 → 文件名词项重叠 → 文件名相似度依次尝试；未匹配者仍可用标题/摘要出证，但 locator 退回 JSON Pointer 并在 `findings` / `uncertainty` 中标注。
- `comparison`、`innovation_checks`、`conflicting_evidence` 中出现的 `source_id` 必须能在输入记录中找到。
- 没有来源的判断（需要读全文、需要专家裁决、需要补资源声明）只能写进 `needs_human_confirmation`，不得伪装成材料事实。
- 不编造文献、年份、DOI、样本量、伦理批号或效应量；不把「批内没检索到」写成「尚无人研究」。

## 异常处理

| 情形 | 处理 | 标记 |
|---|---|---|
| `case.json` 缺失 | 按空输入分析，仍写 `result.json` 并 exit 0 | `status=insufficient_input`，`errors[].type=case_file_missing` |
| `case.json` 损坏或非对象 | 写结构化失败结果，仍 exit 0 | `status=failed`，`errors[].type=case_unreadable` |
| 无选题文本 | 不生成新颖度/可行性结论 | `status=insufficient_input`，`uncertainty.type=no_proposal` |
| 无先行研究 | 不生成新颖度结论 | `status=insufficient_input`，`research_gaps.type=no_prior_art_batch` |
| 无对照或无可测结局 | 判不可检验 | `testable_form.tests.is_falsifiable=false` |
| 无资源声明 | 可行性只做部分检查 | `status=partial`，`uncertainty.type=no_resources` |
| 记录缺摘要 | 按标题比较并说明 | `comparison[].not_comparable_reason`，`uncertainty.type=title_only_records` |
| 记录缺年份 | 不做时效性判断 | `uncertainty` / `needs_human_confirmation` |
| 样本量不足或数据缺失 | 记 `blocker` | `feasibility.blockers` |
| 涉及人或动物但无伦理声明 | 记 `warning` | `feasibility.checks[].check=ethics` |
| 记录结论相反 | 并列保留，不裁决 | `conflicting_evidence[].resolution=unresolved` |
| 源文件 pdf 但无 `pdftotext` | 该文件标 `unparsed`，不臆造正文 | `input_manifest.unparsed[].reason=pdftotext_unavailable` |
| 源文件解析失败或超限 | 记 `unparsed`（`read_failed` / `file_too_large` / `empty_text`），证据留在题录级 | `input_manifest.unparsed[]` |
| 记录未匹配到源文件 | 用标题/摘要出证，locator 为 JSON Pointer | `findings[].aspect=evidence_traceback`，`uncertainty.type=source_unmatched` |
| 输出目录不可写 | 回退到 `--work`；仍失败只向 stderr 报错 | 退出码仍为 0 |
| 未知契约键 | 结构化 `not_determinable` 对象 + `contract_extras` | 顶层键不缺 |

## 限制

- 新颖度是词项/短语重叠，不是语义相似度，也不是查新或专利检索；同义改写与跨语言表述会低估重叠。
- 可行性只覆盖已声明资源，未声明的算力、时间与人员能力无法推断。
- 冲突检测依赖标题/摘要中的极性线索，不能替代全文方法学评价。
- 分值为启发式透明分值，不得用于资助、伦理、人事或发表决策。
- 不生成实验方案、样本量计算、预算或统计分析计划。
- 只解析输入目录下的 md/txt/csv/json 与可转换的 pdf；扫描件、加密 pdf 与图片不做 OCR。
- 不访问网络。

## 最小示例（示例，非正式案例结果）

```bash
python3 scripts/sk_entry.py --input examples/demo-case --work /tmp/demo-work --out /tmp/demo-out
```

演示输入是**合成数据**（`examples/demo-case/case.json` + `sources/` 下 2 份玩具原文）：1 条选题、3 条先行研究（A1 支持、A2 相反、A3 无摘要无年份且无原文）、1 份完整资源声明、10 个 `output_contract` 键。预期：

- `status=success`，`case_id=demo-proposal-001`；
- `input_manifest.sources_found=2`，A1/A2 的 `evidence.locator` 为 `S1#P1` / `S2#P1`，A3 退回 `/prior_art/2`；
- `retrieval_scope.flow` 为 identified=3、duplicates=0、unique=3、screened=3、included=3，且 `arithmetic_closure=true`；
- `comparison` 3 行，A3 带 `not_comparable_reason`；
- `conflicting_evidence` 至少 1 组（A1 阳性 vs A2 阴性，`resolution=unresolved`）；
- `synthesis.verdict=conditional_go`（批内新颖度低）；
- `review_report` ≥200 字，`aspect_coverage` 5 行，`findings` 按 precheck 分级；
- 10 个契约键全部位于顶层，`not_determinable` 为空。
- 输出目录另有 `report.md`、`evidence.csv`、`screening_log.csv`、`provenance.json`；`examples/demo-case/example-result.json` 是一次真实运行留存（标注 TOY）。

示意输出（截断）：

```json
{"status": "success", "case_id": "demo-proposal-001",
 "result": {"synthesis": {"verdict": "conditional_go"},
            "conflicting_evidence": [{"resolution": "unresolved: both directions are kept ..."}],
            "aspect_coverage": [{"aspect": "evidence_traceback", "status": "checked"}]}}
```

完整数值以实际运行为准；示例不代表任何平台固定案例结果。运行说明见 `examples/quickstart.md`。

## 交付自检

- [ ] `python3 scripts/sk_entry.py --input <案例目录> --work <临时目录> --out <临时目录>` 退出码为 0，`result.json` 存在。
- [ ] `case_id` 与输入一致；`status` 只取四个枚举，且与 `uncertainty`、`research_gaps` 自洽。
- [ ] `output_contract` 每个键都在顶层，值不是 `null`/`pending`/`TODO`；无法产出者带 `status=not_determinable` 与原因。
- [ ] 四类交付（`testable_form`、`comparison`、`innovation_checks`、`feasibility`）都有实质内容，不是占位骨架。
- [ ] 每条 `evidence` 的 `quote` 能在 `locator` 指向的文本中逐字找到（`quote_verified=true`）；`S1#P2` 与 `case_locator` 均可回溯。
- [ ] `retrieval_scope.flow.arithmetic_closure=true`，`screening_log` 行数等于 `flow.identified`。
- [ ] `review_report` ≥200 字，`aspect_coverage` 五行齐全且状态只取 `checked` / `checked_no_issue` / `gap`。
- [ ] 冲突记录双方 `quote` 与 `locator` 均存在，`resolution` 未被改成单边结论。
- [ ] 未支持判断都在 `needs_human_confirmation`，没有伪装成材料事实。
- [ ] 重复运行两次，`result.json` 内容一致；包内无 `__pycache__`、无符号链接、无令牌或密钥。
- [ ] 提交目录保留 `GITHUB_URL.txt` 原样，文件数与总大小在 50 个 / 2MB 以内。
