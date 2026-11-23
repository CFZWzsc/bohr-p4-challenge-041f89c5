# 快速开始（示例）

本目录是**合成演示**，用于验证接口与复核流程，不是任何平台固定案例的正式结果，也不含真实临床或科研结论。

## 1. 运行

在 `06_code/submission` 目录下：

```bash
python3 scripts/sk_entry.py \
  --input examples/demo-case \
  --work /tmp/demo-work \
  --out /tmp/demo-out
```

Windows PowerShell：

```powershell
python scripts/sk_entry.py --input examples/demo-case --work .\demo-work --out .\demo-out
```

等价的薄封装：

```bash
python scripts/run_skill.py --input examples/demo-case --work /tmp/demo-work --out /tmp/demo-out
```

也可以直接给 `result.json` 路径：

```bash
python scripts/sk_entry.py --input examples/demo-case --out /tmp/demo-out/result.json
```

退出码应为 0，并生成 `result.json`。若 `--out` 目录不可写，脚本会回退到 `--work/result.json`。

## 2. 示例输入

`examples/demo-case/case.json`（合成数据）：

| 记录 | 内容 | 设计意图 |
|---|---|---|
| 选题 | CRISPR 敲除筛选改善 CAR-T 持久化率（对照 + 可测结局 + 人群） | 展示可检验表述 |
| `A1` | 2021，CRISPR 筛选使持久化率改善 | 最近工作，阳性 |
| `A2` | 2023，标准 CAR-T 无显著改善 | 与 A1 方向相反 |
| `A3` | 仅标题、无摘要、无年份 | 展示 `not_comparable_reason` 与降级 |
| `resources` | 数据、样本 20、12 个月、测序与流式、伦理批准 | 展示可行性检查 |
| `output_contract` | 10 个字段 | 展示契约覆盖 |

## 3. 期望输出要点

数值以实际运行为准，结构应一致：

- `status = success`，`case_id = demo-proposal-001`；
- `result.testable_form.tests.is_falsifiable = true`（有 `rate` 与 `versus`）；
- `result.comparison` 3 行；`A3` 的 `not_comparable_reason` 非空；
- `result.innovation_checks` 同时包含 `covered` 与 `not_found_in_batch` 判定；
- `result.conflicting_evidence` 至少一组，`A1` 阳性 vs `A2` 阴性，`resolution = unresolved`；
- `result.synthesis.verdict = conditional_go`，并列出条件与停止条件；
- 外层 10 个契约键全部位于顶层，`output_contract_fields.not_determinable` 为空；
- `evidence` 含选题与三条记录，`quote_verified` 为 `true`。

## 4. 复核

1. 打开 `result.json`，取 `evidence[0].locator`（`/proposal`）与 `quote`，在 `case.json` 中逐字比对。
2. 取 `comparison` 中 `A3` 一行，确认 `not_comparable_reason` 说明「无摘要」。
3. 打开 `conflicting_evidence[0]`，确认 `supporting` 与 `conflicting` 两方 `quote` 均来自原文。
4. 确认 `needs_human_confirmation` 至少包含 `A3` 全文精读与最近工作复核。
5. 用相同命令再跑一次，确认 `result.json` 内容一致。

## 5. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `status=insufficient_input` | 没有选题或没有先行研究 | 检查 `--input` 是否指向案例根目录，`case.json` 是否有 `proposal` 与记录数组 |
| 某条记录 `not_comparable_reason` 非空 | 缺摘要、无共享词或缺年份 | 属预期降级；读取全文后再人工补判，不要放宽阈值 |
| `novelty_assessment.level=low` | 最近工作词项重叠高 | 查看 `comparison` 与 `innovation_checks`，改用未被覆盖的差异点 |
| 契约键出现 `not_determinable` | 该键无法从本批数据推导 | 按 `next_action` 在复核阶段补充，不得伪造值 |
| `status=failed` | `case.json` 损坏或非对象 | 修正输入；失败结果仍保留全部契约键并 exit 0 |
