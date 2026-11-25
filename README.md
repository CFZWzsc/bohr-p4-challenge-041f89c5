# Runtime contract

Bohrium Playground Period 4 submission — challenge `challenge-041f89c5` (track: `deep-research-literature-review`).

This repository holds the complete skill package for the challenge: the skill
definition, its executable pipeline and all supporting documents. No precomputed
answers, private data or credentials are included.

## Skill

- Name: `research-proposal-novelty-assessment`
- Summary: Use when a research idea must be judged before funding or execution — restate it as a falsifiable claim, compare it record by record with a supplied prior-art batch, mark each innovation statement as covered or not found, check feasibility against declared resources, keep conflicting evidence unresolved, and write a contract-complete result.json. Runs offline with the Python standard library only.

## Contents

| File |
|------|
| `SKILL.md` |
| `assets/policy.json` |
| `examples/demo-case/case.json` |
| `examples/demo-case/example-result.json` |
| `examples/demo-case/sources/A1-crispr-knockout-screens-in-car-t-cells.md` |
| `examples/demo-case/sources/A2-car-t-persistence-without-genetic-screening.md` |
| `examples/quickstart.md` |
| `references/evidence-discipline.md` |
| `references/method.md` |
| `references/task-spec.md` |
| `scripts/run_skill.py` |
| `scripts/sk_entry.py` |
| `README.md` |

## How to run

```bash
python scripts/sk_entry.py --input /input --work /app/work --out /app/output
```

A single deterministic pass reads `/input`, computes the deliverable and writes a
contract-complete `/app/output/result.json` plus the human-readable review files
described in `SKILL.md`. The same input always produces byte-identical output; no
network access is used, and fields the materials cannot support are reported
explicitly instead of being left empty.

## Notes

- Pure Python standard library; no network access required.
- Every claim is anchored to paragraph-level evidence; unknown items are reported
  in `uncertainty` instead of being fabricated.
