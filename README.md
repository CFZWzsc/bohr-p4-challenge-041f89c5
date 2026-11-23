# Runtime contract

Bohrium Playground Period 4 submission — challenge `challenge-041f89c5` (track: `deep-research-literature-review`).

This repository holds the complete skill package for the challenge: the skill
definition, its executable entry point and all supporting scripts. No precomputed
answers, private data or credentials are included.

## Skill

- Name: `research-proposal-novelty-assessment`
- Summary: Use when a research idea must be assessed before funding or execution: falsifiable restatement, batch-bounded prior-art overlap, differentiators, feasibility checks, typed risks and revisions.

## Contents

| File |
|------|
| `SKILL.md` |
| `scripts/run_skill.py` |
| `README.md` |

## How to run

```bash
python scripts/run_skill.py --case /input/case.json --output /app/output/result.json
```

The entry point is `SKILL.md`; input/output contracts, error handling and a minimal
usage example are documented there.

## Notes

- Pure Python standard library; no network access required.
- The result JSON keeps the input case id, the main results, per-item evidence,
  a run status and an uncertainty section.
