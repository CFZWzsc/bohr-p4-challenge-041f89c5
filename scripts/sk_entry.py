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


def overlap(proposal_terms, record, phrase_bonus=0.08):
    record_terms = set(tokenize(record["title"] + " " + record["abstract"], limit=60))
    shared = [term for term in proposal_terms if term in record_terms]
    ratio = len(shared) / float(len(proposal_terms)) if proposal_terms else 0.0
    phrases = sorted({phrase for phrase in bigrams(record["title"] + " " + record["abstract"]) if phrase in " ".join(proposal_terms)})
    effective = min(1.0, ratio + phrase_bonus * len(phrases))
    return shared, ratio, effective, phrases


def assess_novelty(proposal_terms, records, direct=0.45, partial=0.25, phrase_bonus=0.08):
    rows = []
    for record in records:
        shared, ratio, effective, phrases = overlap(proposal_terms, record, phrase_bonus)
        level = "direct_overlap" if effective >= direct else ("partial_overlap" if effective >= partial else "adjacent")
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


import hashlib
from difflib import get_close_matches

sys.dont_write_bytecode = True


def load_policy():
    path = Path(__file__).resolve().parent.parent / "assets" / "policy.json"
    try:
        data = load_json(path)
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def pol(policy, dotted, fallback):
    node = policy
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return fallback
    return node


def excerpt(text, limit):
    text = norm_space(text)
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    space = cut.rfind(" ")
    if space >= int(limit * 0.6):
        cut = cut[:space]
    return cut.rstrip(" ,;"), True


def text_of(record):
    return record["abstract"] or record["title"]


PROPOSAL_KEYS = ("proposal", "proposed_topic", "idea", "hypothesis", "research_question", "question", "topic", "aim")


def proposal_locator(case, task_text):
    if isinstance(case, dict):
        for key in PROPOSAL_KEYS:
            if case.get(key) not in (None, "", [], {}):
                return "/" + key
    return "/task.md" if task_text else "/proposal"


def build_manifest(root, limit, hash_bytes):
    rows = []
    if root is None:
        return rows
    root = Path(root)
    try:
        if not root.exists():
            return rows
    except OSError:
        return rows
    if root.is_file():
        candidates = [root]
    else:
        candidates = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda item: item.as_posix())
    for path in candidates:
        if len(rows) >= limit:
            break
        if "__pycache__" in path.parts or ".git" in path.parts:
            continue
        try:
            size = path.stat().st_size
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                remaining = hash_bytes
                while remaining > 0:
                    chunk = handle.read(min(65536, remaining))
                    if not chunk:
                        break
                    digest.update(chunk)
                    remaining -= len(chunk)
        except OSError:
            continue
        relative = path.name if root.is_file() else path.relative_to(root).as_posix()
        rows.append({"path": relative, "bytes": size, "sha256": digest.hexdigest(),
                     "hash_scope": "full" if size <= hash_bytes else "first_bytes"})
    return rows


def retrieval_scope(terms, records, task_text):
    missing_abstract = [record["source_id"] for record in records if not record["abstract"]]
    missing_year = [record["source_id"] for record in records if record["year"] is None]
    return {
        "query": " ".join(terms[:8]),
        "query_basis": "proposal terms after stop-word removal, plus CJK bigrams; no search engine or network call is used",
        "inclusion": "records supplied in the case file that carry a title, abstract, year or DOI, including nested record objects",
        "exclusion": [
            "no record is excluded for language, venue or recency; only entries that are not objects are skipped",
            "records without an abstract are compared on the title alone" if missing_abstract else "every supplied record carries an abstract",
            "records without a year are compared without any recency statement" if missing_year else "every supplied record carries a year",
        ],
        "batch_size": len(records),
        "screened_out": {"missing_abstract": len(missing_abstract), "missing_year": len(missing_year)},
        "external_search": False,
        "task_text_used": bool(task_text),
    }


def build_comparison(novelty_rows, records, limit):
    by_id = {}
    for record in records:
        by_id[record["source_id"]] = record
    rows = []
    for row in novelty_rows[:limit]:
        record = by_id.get(row["source_id"])
        if record is None:
            continue
        if not record["abstract"]:
            reason = "title-only record: no abstract, so method, data and outcome cannot be compared"
        elif not row["shared_terms"]:
            reason = "no shared content term with the proposal; only topical adjacency is recorded"
        elif record["year"] is None:
            reason = "publication year absent, so recency relative to the proposal cannot be established"
        else:
            reason = None
        rows.append({
            "source_id": record["source_id"],
            "locator": record["locator"],
            "title": record["title"],
            "year": record["year"],
            "shared_terms": row["shared_terms"],
            "shared_phrases": row["shared_phrases"],
            "overlap": row["overlap"],
            "overlap_class": row["relation"],
            "comparison_fields": ["title", "abstract", "year"],
            "not_comparable_reason": reason,
        })
    return rows


def ids_mentioning(records, terms):
    found = []
    for record in records:
        blob = (record["title"] + " " + record["abstract"]).lower()
        if any(term in blob for term in terms):
            found.append(record["source_id"])
    return found


def innovation_checks(form, records, unique_terms, limit):
    checks = []
    intervention = form["intervention_terms"][:4]
    outcomes = form["outcome_indicators"][:3]
    if intervention:
        covered = ids_mentioning(records, intervention)
        checks.append({
            "claim": "the proposed intervention (%s) is itself novel" % ", ".join(intervention),
            "covered_by": covered,
            "verdict": "covered" if covered else "not_found_in_batch",
            "basis": "intervention terms were matched against every supplied title and abstract; coverage here is batch-bounded",
        })
    if outcomes:
        covered = ids_mentioning(records, outcomes)
        checks.append({
            "claim": "the stated outcome (%s) has not been measured before" % ", ".join(outcomes),
            "covered_by": covered,
            "verdict": "covered" if covered else "not_found_in_batch",
            "basis": "outcome indicators were matched against every supplied title and abstract",
        })
    if intervention and outcomes:
        both, only_intervention, only_outcome = [], [], []
        for record in records:
            blob = (record["title"] + " " + record["abstract"]).lower()
            has_intervention = any(term in blob for term in intervention)
            has_outcome = any(term in blob for term in outcomes)
            if has_intervention and has_outcome:
                both.append(record["source_id"])
            elif has_intervention:
                only_intervention.append(record["source_id"])
            elif has_outcome:
                only_outcome.append(record["source_id"])
        if both:
            verdict = "covered"
            basis = "at least one supplied record mentions both the intervention and the outcome"
        elif only_intervention and only_outcome:
            verdict = "partially_covered"
            basis = "the two parts appear separately in the batch but never in the same record"
        elif only_intervention or only_outcome:
            verdict = "partially_covered"
            basis = "one half of the combination appears in the batch"
        else:
            verdict = "not_found_in_batch"
            basis = "neither half of the combination appears in the batch"
        checks.append({
            "claim": "the intervention x outcome combination is unoccupied",
            "covered_by": both,
            "verdict": verdict,
            "basis": basis + "; this is a batch observation, not a novelty guarantee",
        })
    for term in unique_terms[:limit]:
        hits = ids_mentioning(records, [term])
        checks.append({
            "claim": "term '%s' is absent from every supplied title and abstract" % term if not hits
                     else "term '%s' also appears in other supplied records and is not a differentiator by itself" % term,
            "covered_by": hits,
            "verdict": "not_found_in_batch" if not hits else "covered",
            "basis": "term-by-term search over every supplied title and abstract",
        })
    if not checks:
        checks.append({
            "claim": "no innovation statement could be derived from the proposal text",
            "covered_by": [],
            "verdict": "not_found_in_batch",
            "basis": "neither an intervention nor an outcome indicator was found in the proposal",
        })
    return checks


POSITIVE_CUES = ("significant", "improved", "increase", "increased", "effective", "benefit", "superior",
                 "reduced", "higher", "outperform", "有效", "改善", "提高", "优于", "降低", "显著")
NEGATIVE_CUES = ("no significant", "not significant", "no difference", "did not", "failed to", "no effect",
                 "not improved", "no benefit", "无显著", "未见", "未改善", "无效", "没有差异")


def polarity(text):
    lowered = text.lower()
    if any(cue in lowered for cue in NEGATIVE_CUES):
        return "negative"
    if any(cue in lowered for cue in POSITIVE_CUES):
        return "positive"
    return "neutral"


def conflicting_evidence(records, outcome_terms, quote_limit):
    eligible = []
    for record in records:
        blob = (record["title"] + " " + record["abstract"]).lower()
        if outcome_terms and any(term in blob for term in outcome_terms):
            eligible.append((record, polarity(blob)))
    positives = [item[0] for item in eligible if item[1] == "positive"]
    negatives = [item[0] for item in eligible if item[1] == "negative"]
    rows = []
    for positive in positives[:3]:
        for negative in negatives[:3]:
            rows.append({
                "claim": "supplied records disagree on the stated outcome",
                "supporting": [{"source_id": positive["source_id"], "locator": positive["locator"],
                                "quote": excerpt(text_of(positive), quote_limit)[0]}],
                "conflicting": [{"source_id": negative["source_id"], "locator": negative["locator"],
                                 "quote": excerpt(text_of(negative), quote_limit)[0]}],
                "resolution": "unresolved: both directions are kept; the batch supplies no design or effect-size fields with which to adjudicate",
                "needs_full_text": True,
            })
    if rows:
        return rows
    checked = [{"source_id": record["source_id"], "locator": record["locator"], "polarity": label}
               for record, label in eligible]
    return [{
        "claim": "no directly opposing pair was detected among the supplied records on the stated outcome",
        "checked": checked if checked else "no supplied record addresses the stated outcome indicators",
        "resolution": "not_applicable: polarity cues were consistent or absent; this is not evidence of agreement in the field",
    }]


def synthesis(form, novelty, feasible, checks, records, proposal):
    conditions = ["obtain expert review of the closest work before any novelty claim is made"]
    covered = [check for check in checks if check["verdict"] == "covered"]
    if not proposal or not records:
        verdict = "hold"
        conditions.insert(0, "provide a proposal and a prior-art batch before a go/hold judgement")
    elif feasible["blockers"]:
        verdict = "hold"
        conditions.insert(0, "resolve blockers: " + ", ".join(feasible["blockers"]))
    elif novelty["level"] == "low" or not form["tests"]["is_falsifiable"]:
        verdict = "conditional_go"
        if novelty["level"] == "low":
            conditions.append("reframe the claim against the closest work or change the comparator")
        if not form["tests"]["is_falsifiable"]:
            conditions.append("state a measurable outcome and an explicit comparator")
    else:
        verdict = "go"
    if feasible["warnings"]:
        conditions.append("close the declared warnings: " + ", ".join(feasible["warnings"]))
    return {
        "verdict": verdict,
        "conditions": conditions,
        "stop_conditions": [
            "a supplied record already reports the intervention x outcome combination",
            "a feasibility blocker cannot be resolved with the declared resources",
            "the outcome cannot be measured with an available instrument",
        ],
        "basis": [
            "testability: %s" % ("falsifiable as written" if form["tests"]["is_falsifiable"] else "not falsifiable as written"),
            "novelty in batch: %s (score %d)" % (novelty["level"], novelty["score"]),
            "feasibility: %s" % feasible["verdict"],
            "innovation statements already covered in batch: %d" % len(covered),
        ],
        "decision_scope": "planning aid only; not a funding, ethics, personnel or publication decision",
    }


def needs_human_confirmation(case, proposal_loc, form, records, novelty_rows, feasible, conflicts, resources):
    items = []
    for record in records:
        if not record["abstract"]:
            items.append({"item": "read the full text of %s" % record["source_id"], "locator": record["locator"],
                          "reason": "no abstract supplied; the comparison uses the title only"})
        elif record["year"] is None:
            items.append({"item": "confirm the publication year of %s" % record["source_id"], "locator": record["locator"],
                          "reason": "a year is required to judge whether the work is the most recent prior art"})
    for term in form["vague_terms"][:4]:
        items.append({"item": "operationalise '%s'" % term, "locator": proposal_loc,
                      "reason": "the term has no measurable definition in the proposal text"})
    if not resources:
        items.append({"item": "declare available data, sample, time and methods", "locator": "/resources",
                      "reason": "no resource declaration was supplied; feasibility is only partially checked"})
    if novelty_rows and novelty_rows[0]["relation"] != "adjacent":
        locator = "/"
        for record in records:
            if record["source_id"] == novelty_rows[0]["source_id"]:
                locator = record["locator"]
                break
        items.append({"item": "check the closest work %s in full text" % novelty_rows[0]["source_id"],
                      "locator": locator,
                      "reason": "lexical overlap flags it as close; only full-text reading can confirm or reject coverage"})
    if any(str(row.get("resolution", "")).startswith("unresolved") for row in conflicts):
        items.append({"item": "adjudicate the conflicting outcome reports", "locator": "/",
                      "reason": "the batch contains opposing polarity cues and no design fields with which to resolve them"})
    if not form["tests"]["has_comparator"]:
        items.append({"item": "add a comparator or control condition", "locator": proposal_loc,
                      "reason": "without a comparator the claim cannot be falsified"})
    if not items:
        items.append({"item": "expert review of the whole assessment", "locator": "/",
                      "reason": "the deterministic checks found no specific open item; domain judgement remains external"})
    return items


def build_evidence(records, proposal, proposal_loc, novelty_rows, quote_limit):
    rows = []
    if proposal:
        quote, truncated = excerpt(proposal, quote_limit)
        rows.append({"kind": "proposal", "source_id": "proposal", "locator": proposal_loc,
                     "quote": quote, "quote_verified": quote in proposal, "truncated": truncated})
    overlap_by_id = {}
    for row in novelty_rows:
        overlap_by_id[row["source_id"]] = row
    for record in records:
        source = text_of(record)
        quote, truncated = excerpt(source, quote_limit)
        row = overlap_by_id.get(record["source_id"], {})
        rows.append({"kind": "prior_art", "source_id": record["source_id"], "locator": record["locator"],
                     "quote": quote, "quote_verified": bool(quote) and quote in source, "truncated": truncated,
                     "year": record["year"], "overlap": row.get("overlap"),
                     "overlap_class": row.get("relation")})
    return rows


def build_payload(case, task_text, input_root=None):
    policy = load_policy()
    max_terms = pol(policy, "caps.proposal_terms", 20)
    quote_limit = pol(policy, "caps.quote_chars", 240)
    max_rows = pol(policy, "caps.max_comparison_rows", 200)
    max_checks = pol(policy, "caps.max_differentiators", 15)
    direct = pol(policy, "overlap.direct_threshold", 0.45)
    partial = pol(policy, "overlap.partial_threshold", 0.25)
    phrase_bonus = pol(policy, "overlap.phrase_bonus", 0.08)

    raw_records = find_records(case)
    records = [normalize(raw, locator, index) for index, (locator, raw) in enumerate(raw_records)]
    proposal = proposal_of(case, task_text)
    proposal_loc = proposal_locator(case, task_text)
    resources = resources_of(case)
    terms = tokenize(proposal, limit=max_terms)
    form = testable_form(proposal)
    novelty_rows, novelty = assess_novelty(terms, records, direct, partial, phrase_bonus)
    feasible = feasibility(proposal, resources)
    unique = differentiators(terms, novelty_rows)[:max_checks]
    batch_unique = [term for term in terms if not ids_mentioning(records, [term])][:max_checks]

    scope = retrieval_scope(terms, records, task_text)
    comparison = build_comparison(novelty_rows, records, max_rows)
    checks = innovation_checks(form, records, batch_unique, max_checks)
    conflicts = conflicting_evidence(records, form["outcome_indicators"], quote_limit)
    synth = synthesis(form, novelty, feasible, checks, records, proposal)
    evidence = build_evidence(records, proposal, proposal_loc, novelty_rows, quote_limit)
    human = needs_human_confirmation(case, proposal_loc, form, records, novelty_rows, feasible, conflicts, resources)

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
        gaps.append({"type": "no_prior_art_batch", "basis": "the novelty score is not meaningful without prior art"})
    if novelty["close_works"] == 0 and records:
        gaps.append({"type": "no_close_work_in_batch",
                     "basis": "no supplied record exceeds the partial-overlap threshold; this is a batch observation, not proof of novelty"})
    if not resources:
        gaps.append({"type": "no_resources_declared", "basis": "feasibility only checks what is declared"})
    if any(not record["abstract"] for record in records):
        gaps.append({"type": "title_only_records",
                     "basis": "records without an abstract cannot support a method-level comparison"})

    uncertainty = []
    if not proposal:
        uncertainty.append({"type": "no_proposal", "detail": "No proposal or research question was found."})
    if not records:
        uncertainty.append({"type": "no_prior_art", "detail": "No prior-art record was supplied."})
    if not resources:
        uncertainty.append({"type": "no_resources", "detail": "No resources or constraints were declared; feasibility checks are incomplete."})
    if not form["tests"]["is_falsifiable"]:
        uncertainty.append({"type": "not_falsifiable_as_written", "detail": "The proposal lacks a measurable outcome and/or comparator."})
    if any(not record["abstract"] for record in records):
        uncertainty.append({"type": "title_only_records", "detail": "At least one record has no abstract; its comparison uses the title only."})
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
        "retrieval_scope": scope,
        "comparison": comparison,
        "innovation_checks": checks,
        "conflicting_evidence": conflicts,
        "synthesis": synth,
        "needs_human_confirmation": human,
        "scorecard": {
            "novelty_score": novelty["score"],
            "feasibility_score": max(0, 100 - 30 * len(feasible["blockers"]) - 10 * len(feasible["warnings"])),
            "testability_score": sum(1 for value in form["tests"].values() if value) * 25,
            "weights": "equal thirds for transparent reading only; not a funding decision",
        },
        "method": {
            "novelty_rule": "share of proposal terms found in the record title/abstract, plus a phrase bonus; thresholds direct>=%.2f, partial>=%.2f" % (direct, partial),
            "comparison_rule": "every supplied record is compared on title, abstract and year; records that cannot be compared carry not_comparable_reason",
            "conflict_rule": "positive and negative outcome cues are detected on the stated outcome terms; opposing records are kept unresolved",
            "feasibility_rule": "only declared resources are checked; undeclared capacity is never inferred",
            "deterministic": True,
            "network": False,
        },
        "limitations": [
            "Novelty is lexical overlap with the supplied prior art, not a patent or literature search.",
            "Feasibility covers only declared resources; undeclared capacity cannot be inferred.",
            "Scores are heuristic and must not be used as a funding or ethics decision.",
            "No experimental plan, power calculation or budget model is produced.",
            "Conflict detection relies on polarity cues in title/abstract and cannot replace a methodological appraisal.",
        ],
        "change_log": [
            "Restated the proposal and checked whether it is falsifiable as written.",
            "Declared the retrieval scope and the batch size actually screened.",
            "Compared proposal terms with each supplied prior-art record and recorded comparability.",
            "Checked each innovation statement against every supplied record.",
            "Kept opposing outcome reports unresolved and carried them into the synthesis.",
            "Checked feasibility against declared data, sample, time, methods and ethics.",
            "Assembled risks, revisions, a conditional synthesis and a transparent scorecard.",
        ],
    }
    return {
        "case_id": case_identifier(case) or "unknown",
        "status": status,
        "result": result,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "errors": [],
        "stats": {"records": len(records), "proposal_terms": len(terms), "close_works": novelty["close_works"],
                  "blockers": len(feasible["blockers"]), "innovation_checks": len(checks),
                  "conflicts": len([row for row in conflicts if "conflicting" in row]),
                  "human_confirmation_items": len(human), "network": "disabled"},
        "input_manifest": build_manifest(input_root, pol(policy, "caps.max_manifest_files", 200),
                                         pol(policy, "caps.manifest_hash_bytes", 1048576)),
        "run": {"entrypoint": "scripts/sk_entry.py", "network": "disabled", "stdlib_only": True,
                "deterministic": True, "policy_version": pol(policy, "version", "unknown")},
    }


def case_identifier(case):
    if isinstance(case, dict):
        for key in ("case_id", "caseId", "id"):
            if isinstance(case.get(key), str) and case[key].strip():
                return case[key]
    return ""


RESERVED_FIELDS = {"case_id", "status", "result", "evidence", "uncertainty", "errors", "stats",
                   "contract_notes", "contract_extras", "output_contract_fields", "input_manifest", "run"}

INTERPRETED_INPUT_KEYS = {"case_id", "caseId", "id", "title", "proposal", "proposed_topic", "idea", "hypothesis",
                          "research_question", "question", "topic", "aim", "prior_art", "records", "papers",
                          "literature", "sources", "documents", "citations", "resources", "constraints",
                          "available_resources", "capabilities", "output_contract"}

CONTRACT_ALIASES = {
    "report": "synthesis",
    "summary": "synthesis",
    "findings": "novelty_assessment",
    "novelty": "novelty_assessment",
    "prior_art": "comparison",
    "prior_art_comparison": "comparison",
    "comparison_matrix": "comparison",
    "novelty_checks": "innovation_checks",
    "differentiation": "innovation_checks",
    "conflicts": "conflicting_evidence",
    "conflict_evidence": "conflicting_evidence",
    "gaps": "research_gaps",
    "verdict": "synthesis",
    "recommendation": "synthesis",
    "recommendations": "recommended_revisions",
    "risks_and_mitigations": "risks",
    "assumptions": "needs_human_confirmation",
    "open_questions": "needs_human_confirmation",
    "human_confirmation": "needs_human_confirmation",
    "search_scope": "retrieval_scope",
    "retrieval": "retrieval_scope",
    "sources": "evidence",
    "citations": "evidence",
    "notes": "uncertainty",
    "uncertainties": "uncertainty",
    "testability": "testable_form",
    "feasibility_check": "feasibility",
    "recommended_changes": "recommended_revisions",
}


def contract_entries(case):
    contract = case.get("output_contract") if isinstance(case, dict) else None
    shape = "absent"
    names = []
    if isinstance(contract, dict):
        if isinstance(contract.get("properties"), dict):
            shape = "json_schema"
            names = [str(key) for key in contract["properties"].keys()]
        else:
            shape = "mapping"
            names = [str(key) for key in contract.keys()]
    elif isinstance(contract, list):
        shape = "list"
        for item in contract:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                for key in ("name", "field", "key", "id"):
                    if isinstance(item.get(key), str):
                        names.append(item[key])
                        break
    elif isinstance(contract, str):
        shape = "string"
        names = [contract]
    ordered = []
    seen = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered, shape


def not_determinable(name, candidates):
    lowered = [candidate.lower() for candidate in candidates]
    close = get_close_matches(str(name).lower(), lowered, n=3, cutoff=0.35)
    mapping = {}
    for candidate in candidates:
        mapping[candidate.lower()] = candidate
    closest = [mapping[item] for item in close] or sorted(candidates)[:3]
    return {
        "status": "not_determinable",
        "produced": False,
        "field": str(name),
        "reason": "No derivation in this skill maps to the declared contract field, and the supplied batch does not contain the data that would decide it.",
        "closest_produced_fields": closest,
        "next_action": "Derive this field from the input materials during review, or keep it explicitly unavailable; do not fabricate a value.",
    }


def apply_contract(payload, case):
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    candidates = [str(key) for key in payload.keys()] + [str(key) for key in result.keys() if key not in payload]
    names, shape = contract_entries(case)
    notes, sources, unknown, aliases = {}, {}, [], {}
    for name in names:
        if name in RESERVED_FIELDS:
            notes[name] = "already produced as a top-level field; kept unchanged"
            sources[name] = "top_level"
            continue
        if name in payload:
            notes[name] = "produced directly by this run"
            sources[name] = "top_level"
            continue
        if name in result:
            payload[name] = result[name]
            notes[name] = "lifted from result.%s so the declared field exists at top level" % name
            sources[name] = "result"
            continue
        target = CONTRACT_ALIASES.get(name.lower())
        if target and target in result:
            payload[name] = result[target]
            notes[name] = "aliased to result.%s" % target
            sources[name] = "alias:%s" % target
            aliases[name] = target
            continue
        if target and target in payload:
            payload[name] = payload[target]
            notes[name] = "aliased to top-level %s" % target
            sources[name] = "alias:%s" % target
            aliases[name] = target
            continue
        payload[name] = not_determinable(name, candidates)
        notes[name] = "no derivation available; a structured not_determinable object was written instead of null"
        sources[name] = "not_determinable"
        unknown.append(name)
    payload["contract_notes"] = notes
    payload["contract_extras"] = {
        "contract_shape": shape,
        "declared_keys": names,
        "not_determinable_keys": unknown,
        "aliases_applied": aliases,
        "uninterpreted_input_keys": sorted(str(key) for key in (case.keys() if isinstance(case, dict) else [])
                                           if str(key) not in INTERPRETED_INPUT_KEYS),
    }
    payload["output_contract_fields"] = {
        "provided": names,
        "present": dict((name, True) for name in names),
        "sources": sources,
        "not_determinable": unknown,
    }
    return payload


def write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, str(target))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def failed_payload(case, errors):
    return {
        "case_id": (case_identifier(case) if isinstance(case, dict) else "") or "unknown",
        "status": "failed",
        "result": {"assessment": {"status": "not_produced",
                                  "reason": "the run failed before any assessment could be produced"}},
        "evidence": [],
        "uncertainty": [{"type": "run_failure", "detail": "Run failed; no assessment is reported."}],
        "errors": list(errors),
        "stats": {"records": 0, "network": "disabled"},
        "input_manifest": [],
        "run": {"entrypoint": "scripts/sk_entry.py", "network": "disabled", "stdlib_only": True,
                "deterministic": True},
    }


def parse_cli(argv):
    parser = argparse.ArgumentParser(description="Research proposal novelty and feasibility assessment")
    parser.add_argument("--input", "--case", dest="input", default=DEFAULT_CASE, help="input directory or case.json")
    parser.add_argument("--work", default=DEFAULT_WORK)
    parser.add_argument("--out", "--output", dest="out", default=DEFAULT_OUT, help="output directory or result.json")
    return parser.parse_args(argv)


def resolve_out(value):
    path = Path(value)
    if path.suffix.lower() == ".json":
        return path.parent, path
    return path, path / "result.json"


def resolve_inputs(value):
    path = Path(value)
    if path.is_dir():
        return path / "case.json", path
    return path, path.parent


def write_result(out_path, payload, work_dir):
    for target in (Path(out_path), Path(work_dir) / "result.json"):
        try:
            write_json(target, payload)
            return str(target)
        except Exception:
            continue
    return ""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out_path = Path(DEFAULT_OUT) / "result.json"
    work_dir = Path(DEFAULT_WORK)
    case = {}
    errors = []
    broken_input = False
    payload = None
    try:
        args = parse_cli(argv)
        work_dir = Path(args.work)
        _out_dir, out_path = resolve_out(args.out)
        case_path, input_root = resolve_inputs(args.input)
        if not case_path.is_file():
            errors.append({"stage": "input", "type": "case_file_missing",
                           "message": "no case.json was found at the resolved input path"})
        else:
            try:
                case = load_json(case_path)
                if not isinstance(case, dict):
                    raise ValueError("case.json root must be a JSON object")
            except Exception as exc:
                case = {}
                broken_input = True
                errors.append({"stage": "input", "type": "case_unreadable", "message": str(exc)[:500]})
        try:
            Path(work_dir).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        task_text = read_task_text(str(case_path), str(work_dir))
        payload = build_payload(case, task_text, input_root)
    except BaseException as exc:
        payload = failed_payload(case, [{"stage": "build", "type": type(exc).__name__, "message": str(exc)[:500]}])
    if not isinstance(payload, dict):
        payload = failed_payload(case, [{"stage": "build", "type": "invalid_payload", "message": "payload was not a dict"}])
    if errors:
        payload["errors"] = list(payload.get("errors") or []) + errors
    if broken_input:
        payload["status"] = "failed"
    try:
        payload = apply_contract(payload, case if isinstance(case, dict) else {})
    except BaseException as exc:
        payload["contract_notes"] = {}
        payload["contract_extras"] = {"error": "%s: %s" % (type(exc).__name__, str(exc)[:200])}
        payload["output_contract_fields"] = {"provided": [], "present": {}}
    written = write_result(out_path, payload, work_dir)
    if not written:
        sys.stderr.write(json.dumps({"status": payload.get("status"), "stage": "write_output",
                                     "message": "result.json could not be written"}, ensure_ascii=False) + "\n")
    summary = {"status": payload.get("status"), "case_id": payload.get("case_id"), "out": written,
               "contract_keys": len((payload.get("output_contract_fields") or {}).get("provided") or [])}
    sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        try:
            fallback = Path(DEFAULT_OUT) / "result.json"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback, "w", encoding="utf-8") as handle:
                json.dump({"case_id": "unknown", "status": "failed",
                           "result": {"assessment": {"status": "not_produced"}},
                           "evidence": [], "uncertainty": [{"type": "run_failure"}], "errors": [],
                           "stats": {}, "contract_notes": {}}, handle, ensure_ascii=False, indent=2)
        except BaseException:
            pass
    sys.exit(0)
