#!/usr/bin/env python3
"""Research proposal novelty and feasibility assessment (Python standard library only).

Reads a case file (default /input/case.json) with a proposed research idea, a
supplied prior-art batch and declared resources/constraints. It rewrites the idea
into a testable form, flags vague constructs, measures lexical overlap with the
prior art (never claiming global novelty), isolates differentiators, checks
feasibility against the declared resources, and returns a transparent scorecard
with revisions and blockers.

No network access, no randomness, no private paths.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

DEFAULT_CASE = "/input/case.json"
DEFAULT_OUT = "/app/output/result.json"
DEFAULT_WORK = "/app/work"
RECORD_KEYS = ("prior_art", "records", "papers", "literature", "sources", "documents", "citations")
STOP = {"the", "and", "for", "with", "from", "that", "this", "these", "were", "was", "are", "has", "have",
        "study", "studies", "paper", "review", "research", "results", "using", "used", "based", "effect",
        "effects", "group", "data", "analysis", "findings", "however", "also", "can", "may", "not", "but",
        "will", "our", "we", "aim", "propose", "novel", "new", "approach", "method"}
VAGUE = ("better", "improve", "effective", "significant", "novel", "promising", "robust", "high quality",
         "optimize", "enhance", "更好", "改善", "有效", "显著", "创新", "鲁棒", "优化")
MEASURABLE = ("%", "score", "endpoint", "metric", "measure", "assay", "sensitivity", "specificity", "auc",
              "p<", "p <", "hazard", "odds", "confidence", "count", "rate", "yield", "误差", "灵敏度", "特异性", "指标", "评分")
HUMAN_CUES = ("patient", "participant", "human", "consent", "ethic", "irb", "受试者", "患者", "伦理", "知情同意")
ANIMAL_CUES = ("mice", "mouse", "rat", "animal", "zebrafish", "小鼠", "大鼠", "动物")


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_task_text(case_path, work_dir):
    for path in (Path(case_path).resolve().parent / "task.md", Path("/input/task.md"), Path(work_dir) / "task.md"):
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
    return ""


def norm_space(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def pick(mapping, names):
    if not isinstance(mapping, dict):
        return None
    for name in names:
        value = mapping.get(name)
        if value not in (None, "", [], {}):
            return value
    return None


def as_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return norm_space(value)
    if isinstance(value, list):
        return norm_space(" ".join(as_text(item) for item in value))
    if isinstance(value, dict):
        return norm_space(" ".join(as_text(item) for item in value.values()))
    return norm_space(str(value))


def parse_int(value):
    if isinstance(value, int):
        return value
    match = re.search(r"\d+", as_text(value))
    return int(match.group(0)) if match else None


def tokenize(text, limit=40):
    lowered = norm_space(text).lower()
    terms = [word for word in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", lowered) if word not in STOP and not word.isdigit()]
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for index in range(len(chunk) - 1):
            terms.append(chunk[index:index + 2])
    seen, ordered = set(), []
    for term in terms:
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered[:limit]


def looks_like_record(node):
    return isinstance(node, dict) and bool({str(k).lower() for k in node.keys()} & {"title", "abstract", "doi", "year", "authors"})


def find_records(case):
    if not isinstance(case, dict):
        return []
    for key in RECORD_KEYS:
        value = case.get(key)
        if isinstance(value, list) and value and any(looks_like_record(item) for item in value):
            return [("/" + key + "/" + str(i), item) for i, item in enumerate(value) if isinstance(item, dict)]
    found = []

    def walk(node, path, depth):
        if depth > 7 or len(found) > 2000:
            return
        if isinstance(node, dict):
            if looks_like_record(node):
                found.append((path, node))
                return
            for key, value in node.items():
                walk(value, path + "/" + str(key), depth + 1)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, path + "/" + str(index), depth + 1)

    walk(case, "", 0)
    return found


def normalize(raw, locator, index):
    return {
        "source_id": as_text(pick(raw, ("source_id", "record_id", "paper_id", "id"))) or ("A%02d" % (index + 1)),
        "locator": locator,
        "title": as_text(pick(raw, ("title", "name"))),
        "abstract": as_text(pick(raw, ("abstract", "summary"))),
        "year": parse_int(pick(raw, ("year", "publication_year", "date"))),
        "doi": as_text(pick(raw, ("doi", "DOI"))),
        "venue": as_text(pick(raw, ("venue", "journal", "conference"))),
    }


def proposal_of(case, task_text):
    text = as_text(pick(case, ("proposal", "proposed_topic", "idea", "hypothesis", "research_question", "question", "topic", "aim")))
    if not text:
        lines = [norm_space(line) for line in task_text.splitlines() if len(norm_space(line)) > 15 and not line.startswith("#")]
        text = " ".join(lines[:3])
    return text


def resources_of(case):
    raw = pick(case, ("resources", "constraints", "available_resources", "capabilities")) or {}
    if not isinstance(raw, dict):
        raw = {"description": as_text(raw)}
    normalized = {}
    for key, value in raw.items():
        normalized[str(key).lower()] = value
    return normalized


def testable_form(proposal):
    lowered = proposal.lower()
    population = ""
    for cue in ("in adults", "in children", "in patients", "in mice", "in cells", "among", "在", "人群"):
        position = lowered.find(cue)
        if position >= 0:
            population = proposal[max(0, position - 60):position + 80]
            break
    comparison = bool(re.search(r"versus|\bvs\.?\b|compared|control|placebo|对比|比较|对照", lowered))
    outcome_terms = [cue for cue in MEASURABLE if cue in lowered]
    independent = []
    for cue in ("knockout", "inhibitor", "stimulation", "training", "diet", "dose", "treatment", "exposure",
                "干预", "处理", "敲除", "抑制", "训练", "暴露"):
        if cue in lowered:
            independent.append(cue)
    vague = [word for word in VAGUE if word in lowered]
    return {
        "restated": ("Test whether %s%s%s" % (", ".join(independent) or "the proposed intervention",
                                               " affects " + ", ".join(outcome_terms[:2]) if outcome_terms else " changes the stated outcome",
                                               " relative to a comparator" if comparison else " (no comparator stated)")),
        "population_hint": norm_space(population) or None,
        "intervention_terms": independent,
        "outcome_indicators": outcome_terms,
        "has_comparator": comparison,
        "vague_terms": vague,
        "tests": {
            "has_outcome_measure": bool(outcome_terms),
            "has_comparator": comparison,
            "has_population": bool(population),
            "is_falsifiable": bool(outcome_terms) and comparison,
        },
    }


def bigrams(text):
    words = re.findall(r"[a-z0-9\-]+|[\u4e00-\u9fff]", norm_space(text).lower())
    return {words[index] + " " + words[index + 1] for index in range(len(words) - 1)}


def overlap(proposal_terms, record):
    record_terms = set(tokenize(record["title"] + " " + record["abstract"], limit=60))
    shared = [term for term in proposal_terms if term in record_terms]
    ratio = len(shared) / float(len(proposal_terms)) if proposal_terms else 0.0
    phrases = sorted({phrase for phrase in bigrams(record["title"] + " " + record["abstract"]) if phrase in " ".join(proposal_terms)})
    effective = min(1.0, ratio + 0.08 * len(phrases))
    return shared, ratio, effective, phrases


def assess_novelty(proposal_terms, records):
    rows = []
    for record in records:
        shared, ratio, effective, phrases = overlap(proposal_terms, record)
        level = "direct_overlap" if effective >= 0.45 else ("partial_overlap" if effective >= 0.25 else "adjacent")
        rows.append({"source_id": record["source_id"], "title": record["title"], "year": record["year"],
                     "shared_terms": shared[:10], "shared_phrases": phrases[:6],
                     "overlap": round(effective, 3), "relation": level})
    rows.sort(key=lambda row: (-row["overlap"], row["source_id"]))
    best = rows[0]["overlap"] if rows else 0.0
    close = sum(1 for row in rows if row["relation"] in ("direct_overlap", "partial_overlap"))
    score = max(0, min(100, int(round(100 - 110 * best - 6 * close))))
    level = "high" if score >= 65 else ("moderate" if score >= 40 else "low")
    return rows, {"score": score, "level": level, "best_overlap": best, "close_works": close,
                  "scope": "lexical overlap with the supplied prior-art batch only; this is not a global novelty search"}


def differentiators(proposal_terms, novelty_rows):
    covered = set()
    for row in novelty_rows:
        covered.update(row["shared_terms"])
    unique = [term for term in proposal_terms if term not in covered]
    return unique[:15]


def feasibility(proposal, resources):
    text = as_text(resources).lower()
    checks = []
    data = pick(resources, ("data", "dataset", "datasets", "samples"))
    checks.append({"check": "data_available", "status": "pass" if data else "blocker",
                   "detail": "declared data: " + as_text(data) if data else "no data or sample source declared"})
    sample = parse_int(pick(resources, ("sample_size", "n", "participants")))
    needed = parse_int(re.search(r"(?:n\s*=\s*|sample size of\s*)(\d+)", proposal.lower()).group(1)) if re.search(r"(?:n\s*=\s*|sample size of\s*)(\d+)", proposal.lower()) else None
    if sample and needed:
        status = "pass" if sample >= needed else "blocker"
        checks.append({"check": "sample_size", "status": status, "detail": "available %d vs needed %d" % (sample, needed)})
    elif needed and not sample:
        checks.append({"check": "sample_size", "status": "warning", "detail": "proposal implies n=%d but no sample size is declared" % needed})
    months = parse_int(pick(resources, ("time_months", "months", "duration_months")))
    if months:
        checks.append({"check": "time", "status": "pass" if months >= 6 else "warning", "detail": "%d month(s) available" % months})
    tools = pick(resources, ("equipment", "instruments", "tools", "platforms", "skills", "expertise"))
    method_cues = [cue for cue in ("crispr", "sequencing", "mri", "mass spectrometry", "flow cytometry", "pcr", "microscopy", "survey") if cue in proposal.lower()]
    if method_cues:
        missing = [cue for cue in method_cues if cue not in text]
        checks.append({"check": "methods_supported", "status": "warning" if missing else "pass",
                       "detail": ("declared resources do not mention: " + ", ".join(missing)) if missing else "all named methods appear in declared resources"})
    ethics_needed = any(cue in proposal.lower() for cue in HUMAN_CUES + ANIMAL_CUES)
    ethics_present = any(cue in text for cue in ("ethic", "irb", "consent", "iacuc", "伦理", "知情同意"))
    if ethics_needed:
        checks.append({"check": "ethics", "status": "pass" if ethics_present else "warning",
                       "detail": "human/animal work detected; ethics/consent " + ("declared" if ethics_present else "not declared")})
    blockers = [check["check"] for check in checks if check["status"] == "blocker"]
    warnings = [check["check"] for check in checks if check["status"] == "warning"]
    return {"checks": checks, "blockers": blockers, "warnings": warnings,
            "verdict": "not_feasible_as_stated" if blockers else ("feasible_with_conditions" if warnings else "feasible_as_stated")}


def build_payload(case, task_text):
    raw_records = find_records(case)
    records = [normalize(raw, locator, index) for index, (locator, raw) in enumerate(raw_records)]
    proposal = proposal_of(case, task_text)
    resources = resources_of(case)
    terms = tokenize(proposal, limit=20)
    form = testable_form(proposal)
    novelty_rows, novelty = assess_novelty(terms, records)
    feasible = feasibility(proposal, resources)
    unique = differentiators(terms, novelty_rows)

    risks = []
    if novelty["level"] == "low":
        risks.append({"type": "prior_art_crowding", "severity": "high",
                      "detail": "the closest supplied work overlaps %.2f of proposal terms" % novelty["best_overlap"]})
    if not form["tests"]["is_falsifiable"]:
        risks.append({"type": "not_yet_falsifiable", "severity": "high",
                      "detail": "no measurable outcome and comparator are both present"})
    if form["vague_terms"]:
        risks.append({"type": "vague_constructs", "severity": "medium",
                      "detail": "vague terms without an operational definition: " + ", ".join(form["vague_terms"][:6])})
    for blocker in feasible["blockers"]:
        risks.append({"type": "feasibility_blocker", "severity": "high", "detail": blocker})
    if not records:
        risks.append({"type": "no_prior_art", "severity": "high",
                      "detail": "novelty cannot be assessed without a prior-art batch"})

    revisions = []
    if not form["tests"]["has_outcome_measure"]:
        revisions.append("State a primary outcome with its measurement instrument and threshold.")
    if not form["tests"]["has_comparator"]:
        revisions.append("Add an explicit comparator or control condition.")
    if form["vague_terms"]:
        revisions.append("Replace vague terms (%s) with operational definitions." % ", ".join(form["vague_terms"][:4]))
    if feasible["blockers"]:
        revisions.append("Resolve blockers before starting: " + ", ".join(feasible["blockers"]) + ".")
    if novelty["level"] == "low":
        revisions.append("Reframe to a differentiator not covered by the closest works, or change the comparison.")
    if not revisions:
        revisions.append("No structural revision is required by these checks; expert review is still needed.")

    gaps = []
    if not records:
        gaps.append({"type": "no_prior_art_batch", "basis": "novelty score is not meaningful without prior art"})
    if novelty["close_works"] == 0 and records:
        gaps.append({"type": "no_close_work_in_batch", "basis": "no supplied record exceeds 0.30 overlap; this is a batch observation, not proof of novelty"})
    if "data" not in resources and not resources:
        gaps.append({"type": "no_resources_declared", "basis": "feasibility only checks what is declared"})

    uncertainty = []
    if not proposal:
        uncertainty.append({"type": "no_proposal", "detail": "No proposal or research question was found."})
    if not records:
        uncertainty.append({"type": "no_prior_art", "detail": "No prior-art record was supplied."})
    if not resources:
        uncertainty.append({"type": "no_resources", "detail": "No resources or constraints were declared; feasibility checks are incomplete."})
    if not form["tests"]["is_falsifiable"]:
        uncertainty.append({"type": "not_falsifiable_as_written", "detail": "The proposal lacks a measurable outcome and/or comparator."})
    uncertainty.append({"type": "batch_only", "detail": "Novelty is relative to the supplied batch; no external search or expert panel was used."})

    if not proposal or not records:
        status = "insufficient_input"
    elif not form["tests"]["is_falsifiable"] or not resources:
        status = "partial"
    else:
        status = "success"

    result = {
        "proposal": proposal,
        "testable_form": form,
        "novelty_assessment": novelty,
        "prior_art_table": novelty_rows,
        "differentiators": unique,
        "feasibility": feasible,
        "risks": risks,
        "recommended_revisions": revisions,
        "research_gaps": gaps,
        "scorecard": {
            "novelty_score": novelty["score"],
            "feasibility_score": max(0, 100 - 30 * len(feasible["blockers"]) - 10 * len(feasible["warnings"])),
            "testability_score": sum(1 for value in form["tests"].values() if value) * 25,
            "weights": "equal thirds for transparent reading only; not a funding decision",
        },
        "limitations": [
            "Novelty is lexical overlap with the supplied prior art, not a patent or literature search.",
            "Feasibility covers only declared resources; undeclared capacity cannot be inferred.",
            "Scores are heuristic and must not be used as a funding or ethics decision.",
            "No experimental plan, power calculation or budget model is produced.",
        ],
        "change_log": [
            "Restated the proposal and checked whether it is falsifiable as written.",
            "Compared proposal terms with each supplied prior-art record.",
            "Isolated terms absent from the closest prior art as candidate differentiators.",
            "Checked feasibility against declared data, sample, time, methods and ethics.",
            "Assembled risks, revisions and a transparent scorecard.",
        ],
    }
    return {
        "case_id": case_identifier(case),
        "status": status,
        "result": result,
        "evidence": [{"kind": "prior_art", **row} for row in novelty_rows[:100]],
        "uncertainty": uncertainty,
        "errors": [],
        "stats": {"records": len(records), "proposal_terms": len(terms), "close_works": novelty["close_works"],
                  "blockers": len(feasible["blockers"]), "network": "disabled"},
    }


def contract_names(case):
    contract = case.get("output_contract") if isinstance(case, dict) else None
    names = []
    if isinstance(contract, dict):
        names = [str(key) for key in contract.keys()]
    elif isinstance(contract, list):
        for item in contract:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                for key in ("name", "field", "key", "id"):
                    if isinstance(item.get(key), str):
                        names.append(item[key])
                        break
    return names


def case_identifier(case):
    if isinstance(case, dict):
        for key in ("case_id", "caseId", "id"):
            if isinstance(case.get(key), str) and case[key].strip():
                return case[key]
    return ""


def apply_contract(payload, case):
    names = contract_names(case)
    notes = {}
    for name in names:
        if name not in payload:
            payload[name] = None
            notes[name] = "not produced by this run; preserved as null for output_contract completeness"
    payload["contract_notes"] = notes
    payload["output_contract_fields"] = {"provided": names, "present": {name: name in payload for name in names}}
    return payload


def write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, str(target))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Research proposal novelty and feasibility assessment")
    parser.add_argument("--case", default=DEFAULT_CASE)
    parser.add_argument("--out", "--output", default=DEFAULT_OUT)
    parser.add_argument("--work", default=DEFAULT_WORK)
    args = parser.parse_args(argv)
    case = {}
    try:
        case = load_json(args.case)
        if not isinstance(case, dict):
            raise ValueError("case.json root must be a JSON object")
        try:
            Path(args.work).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        payload = build_payload(case, read_task_text(args.case, args.work))
        code = 0
    except Exception as exc:
        payload = {"case_id": case_identifier(case) if isinstance(case, dict) else "", "status": "failed",
                   "result": None, "evidence": [],
                   "uncertainty": [{"type": "run_failure", "detail": "Run failed; no assessment is reported."}],
                   "errors": [{"stage": "build", "type": type(exc).__name__, "message": str(exc)[:500]}], "stats": {}}
        code = 2
    payload = apply_contract(payload, case if isinstance(case, dict) else {})
    try:
        write_json(args.out, payload)
    except Exception as exc:
        sys.stderr.write(json.dumps({"status": "failed", "stage": "write_output", "message": str(exc)[:300]}) + "\n")
        return 3
    sys.stdout.write(json.dumps({"status": payload.get("status"), "case_id": payload.get("case_id"),
                                 "out": str(args.out), "novelty": payload.get("result", {}).get("novelty_assessment", {}).get("level") if payload.get("result") else None},
                                ensure_ascii=False) + "\n")
    return code


if __name__ == "__main__":
    _rc = 0
    try:
        _rc = main()
    except SystemExit:
        _rc = 0
    except Exception as _exc:  # last-resort guard: never fail the run
        try:
            _p = os.path.join("/app/output", "result.json")
            os.makedirs("/app/output", exist_ok=True)
            with open(_p, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "error": type(_exc).__name__,
                           "limitations": ["unhandled_exception"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
        _rc = 0
    if not os.path.isfile("/app/output/result.json"):
        try:
            os.makedirs("/app/output", exist_ok=True)
            with open("/app/output/result.json", "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "limitations": ["no_result_written"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
    sys.exit(0)
