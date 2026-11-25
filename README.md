# 研究提案评估 Skill（challenge-041f89c5）

对一份研究提案做结构化评审：把研究问题拆成可检验表述、比较已有工作、识别创新点、判断可行性，并给出可追溯的证据与成文评审。输出单一 `result.json`（外加 `evidence.csv` / `screening_log.csv` / `provenance.json`）。

## 输入

- `--input <dir>`：包含 `case.json`（`proposal` / `prior_art` / `resources` 等），并可选包含真实原文材料（`*.md` / `*.txt` / `*.csv` / `*.json`，PDF 需系统有 `pdftotext`）。脚本会递归扫描目录并把原文按标题/DOI 匹配到题录，证据定位到 `S3#P7`（源文件#段落）。
- `--work <dir>`：工作目录（默认 `/app/work`）。
- `--out <dir|file.json>`：输出位置（默认 `/app/output`）。

## 运行

```bash
python -B scripts/run_skill.py --input /input --work /app/work --out /app/output
```

## 输出字段

`case_id`、`status`、`result`（`testable_form`、`comparison`、`innovation_checks`、`feasibility`、`synthesis`、`retrieval_scope`、`screening_log`、`findings`、`aspect_coverage`、`review_report` 等）、`evidence`、`uncertainty`、`errors`、`stats`、`contract_notes`。契约键全部保留，未知键写入 `contract_notes`。

## 限制

- 不联网、不核实文献真实性、不做查新或专利检索。
- 无原文时退化为标题/摘要层评估，并在 `input_manifest.sources_found=0` 与 `limitations` 中标注。
- 失败分级与阈值来源见 `references/method.md`；示例输出 `examples/example-result.json` 为合成 demo，不代表任何官方案例结果。

## 文件

- `SKILL.md`：技能定义与流程
- `scripts/sk_entry.py`：主流程；`scripts/run_skill.py`：薄封装（异常恒写 `result.json`、exit 0）
- `assets/policy.json`：阈值与词表
- `references/`：方法、任务映射、证据纪律
- `examples/demo-case/` + `examples/example-result.json`：合成示例
- `requirements.txt`：依赖声明
