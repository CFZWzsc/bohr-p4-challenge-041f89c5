# 题面要求 → 实现落点（`challenge-041f89c5`）

本文件把 `03_brief/statement.md` 的要求逐条映射到包内可运行的部分，便于评审按条复核；不是评分自述，也不代表平台分数。

## 1. 四项交付必须齐全且相互一致

| 题面要求 | 实现位置 | 检查方式 |
|---|---|---|
| 研究问题定义：拆成研究对象、变量、基线、预期结论、可证伪条件 | `result.testable_form`（`restated`、`population_hint`、`intervention_terms`、`outcome_indicators`、`has_comparator`、`vague_terms`、`tests`） | 观察 `tests.is_falsifiable` 是否同时要求结局指标与对照 |
| 已有工作比较：按任务/方法/数据/评价/结论建立比较矩阵，标出无法比较的原因 | `result.comparison[]`（`shared_terms`、`shared_phrases`、`overlap`、`overlap_class`、`comparison_fields`、`not_comparable_reason`） | 记录缺摘要、无共享词、缺年份时 `not_comparable_reason` 必须非空 |
| 创新点识别：区分方法/数据/场景迁移/结论修正，逐条判定是否被覆盖 | `result.innovation_checks[]`（`claim`、`covered_by`、`verdict`、`basis`）+ `result.differentiators[]` | 每条 `verdict` 与 `covered_by` 必须一致；不出现「绝对新颖」表述 |
| 可行性判断：数据、算力/设备、时间、人员能力，输出带条件结论与失败风险 | `result.feasibility`（`checks`、`blockers`、`warnings`、`verdict`）+ `result.risks[]` | 每个结论前提都能指到 `resources` 字段；未声明者进 `needs_human_confirmation` |
| 四项相互一致 | `result.synthesis` 由上述三者推出，`basis[]` 逐项引用 | `synthesis.verdict` 与 `feasibility.blockers`、`novelty_assessment.level`、`testable_form.tests.is_falsifiable` 矛盾即视为失败 |

## 2. 六类内容覆盖

| 题面内容 | 字段 |
|---|---|
| 问题拆解 | `testable_form` |
| 检索覆盖 | `retrieval_scope`（`query`、`inclusion`、`exclusion`、`batch_size`、`screened_out`、`external_search=false`） |
| 证据回链 | `evidence[]`（`locator` 为输入 JSON Pointer，`quote` 为精确子串） |
| 冲突证据 | `conflicting_evidence[]`（双方 `locator` + `quote`，`resolution=unresolved`） |
| 综合结论 | `synthesis`（`go` / `conditional_go` / `hold` + 条件 + 停止条件） |
| 研究空白 | `research_gaps[]`（只写批内观察与依据） |

## 3. 可核验性

- `retrieval_scope` 说明本批文献如何进入评估；不声称外部检索。
- `evidence[].locator` 使用 `case.json` 的 JSON Pointer（`/prior_art/0`、`/proposal` 等），不使用生成文档的页码。
- `evidence[].quote_verified` 逐条记录子串校验结果；`truncated` 说明是否截断。
- `stats` 与 `contract_extras` 给出可复算的计数与契约映射方式。
- `input_manifest[]` 记录输入文件的相对路径、字节数与 sha256（超过 1MB 时标注哈希范围）。

## 4. 判断口径（题面第 1 节末段）

| 题面判据 | 对应实现 |
|---|---|
| 研究问题是否被拆成可检验表述 | `testable_form.tests` 四个布尔值 + `restated` |
| 创新点是否与最近工作逐条划清边界 | `innovation_checks` 对每条陈述给出 `covered_by` 与 `verdict` |
| 可行性每个前提是否有来源或被标为假设 | `feasibility.checks[].detail` 引用 `resources`；未声明项进 `needs_human_confirmation` |

## 5. 输出与异常

- 每个案例返回 `result.json`，保留 `case_id`、主结果、证据定位、运行状态、不确定性。
- 材料缺失、无法判断、运行失败分别对应 `insufficient_input`、`partial` 中的具体不确定性类型、`failed`。
- 部分结果必须标明限制（`limitations`、`uncertainty`、`needs_human_confirmation`）。

## 6. 交付材料对照

| 题面材料 | 包内位置 |
|---|---|
| Skill 本体与处理流程 | `SKILL.md` |
| 运行必需的脚本与资源 | `scripts/sk_entry.py`、`scripts/run_skill.py`、`assets/policy.json` |
| 使用与方法说明 | `SKILL.md`、`references/method.md`、`references/evidence-discipline.md` |
| 最小调用示例 | `examples/demo-case/`、`examples/quickstart.md`（明确标注为示例） |
| GitHub 链接文件 | 根目录 `GITHUB_URL.txt`（原样保留） |

## 7. 明确不做

- 不提交预制答案或正式案例结果；`examples/demo-case` 是合成演示。
- 不声称官方评分、排名或增益数据；平台对照由组织方生成。
- 不联网、不核实文献真实性、不做查新或专利检索。
