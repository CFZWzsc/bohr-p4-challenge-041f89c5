# 证据定位与不编造纪律

本文件是运行与复核时必须遵守的证据规则。脚本只做词项与规则匹配，真正的可信度取决于每条判断能否回到输入原文。

## 1. 定位符（locator）

- 统一使用 `case.json` 的 JSON Pointer：`/prior_art/0`、`/records/3`、`/proposal`、`/research_question`、`/resources`。
- 不使用生成报告的页码、段落序号或自建编号作为定位符。
- 选题来自 `task.md` 时，`locator` 为 `/task.md`，并在 `retrieval_scope.task_text_used=true`。
- 记录缺少 `source_id` 时按 `A01` 起编号，但 `locator` 始终指向其在输入中的真实位置。

## 2. 引文（quote）

- `quote` 必须是指定字段的**精确子串**，不做同义改写、不加省略号、不拼接多个字段。
- 超长时截取前缀，`truncated=true`；`quote_verified` 记录脚本内子串校验结果。
- 引用摘要时不得把标题内容混入引文；标题-only 记录必须显式说明。

## 3. 三类陈述必须分开

| 类型 | 写法 | 落点 |
|---|---|---|
| 材料事实 | 有 `locator` + `quote` 支撑 | `evidence`、`comparison`、`conflicting_evidence` |
| 合理推断 | 由本批统计推出，写明口径与范围 | `novelty_assessment`、`research_gaps`、`synthesis`（`basis` 引用事实项） |
| 无法确定 | 明确列出缺什么、需要谁来判断 | `needs_human_confirmation`、`uncertainty` |

不得把第三类写成第一类。

## 4. 禁止事项

- 不编造文献、作者、年份、DOI、期刊、样本量、伦理批号、效应量或置信区间。
- 不把「本批未出现」写成「领域内尚无人研究」；只能写 `not_found_in_batch`。
- 不把一种方法的旧方案说成新方法，不把应用场景迁移说成理论创新。
- 不在无对照、无结局指标时给出「可行」结论。
- 不对相反结论选边；`resolution` 只能是 `unresolved` 或 `not_applicable`。

## 5. 冲突与取舍

- 相反记录必须成对保留，双方 `quote` 与 `locator` 同时出现。
- 允许写「两篇记录方向相反」，不允许写「总体证据支持某一边」——除非输入同时提供设计与效应量字段。
- 冲突未裁决时，`synthesis` 必须给出条件或停止条件，而不是无条件的 `go`。

## 6. 空白（gap）的写法

- 只写批内观察：哪些记录数、哪些词项、哪种比较无法完成。
- 每条 gap 必须带 `basis`，说明是「无记录」「仅有标题」「无资源声明」还是「术语信号过薄」。
- 不把检索遗漏、语言限制或数据库覆盖不足写成领域空白。

## 7. 复核步骤（人工或 Agent）

1. 打开 `result.json`，取一条 `evidence`，按 `locator` 打开 `case.json` 对应字段。
2. 逐字比对 `quote`；不一致则该条证据作废，相关判断必须降级或删除。
3. 抽查 `comparison[].not_comparable_reason`：缺摘要/缺年份的记录是否如实标注。
4. 抽查 `innovation_checks[].covered_by`：列出的 `source_id` 是否真的包含该词。
5. 检查所有冲突项 `resolution` 仍为 `unresolved`；若被改成单边结论，视为违规。
6. 检查 `needs_human_confirmation` 是否覆盖了全文精读、专家裁决与资源补齐三类事项。

## 8. 输入边界

- 除 `case.json` 记录外不解析其他材料文件；其他文件仅登记到 `input_manifest`。
- 不联网、不调用外部模型；所有判断可由同一脚本复跑复现。
- 不读取或输出任何令牌、密钥、账号信息或个人路径。
