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
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

DEFAULT_CASE = "/input/case.json"
DEFAULT_OUT = "/app/output/result.json"
DEFAULT_WORK = "/app/work"
RECORD_KEYS = ("prior_art", "records", "papers", "literature", "sources", "documents", "citations",
               "known_works", "prior_works", "candidates", "search_results", "screening_records", "bibliography")
SOURCE_EXTS = (".md", ".markdown", ".txt", ".text", ".csv", ".json", ".pdf")
TEXT_SOURCE_EXTS = (".md", ".markdown", ".txt", ".text", ".csv", ".json")
SKIP_DIRS = {"__pycache__", ".git", ".svn", ".hg", "node_modules"}
OUTPUT_NAMES = {"result.json", "report.md", "evidence.csv", "screening_log.csv", "provenance.json",
                "example-result.json"}
MAX_SOURCE_FILES = 40
MAX_SOURCE_CHARS = 400000
MAX_SOURCE_BYTES = 2000000
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

POPULATION_IN = re.compile(
    r"\b(?:in|among|for)\s+((?:(?:adult|elderly|paediatric|pediatric|older|healthy|human|treatment-naive|"
    r"paediatric|refractory|relapsed)\s+)*(?:patients?|adults?|children|mice|rats?|participants?|subjects?|"
    r"donors?|cohorts?|volunteers?))\b", re.I)
POPULATION_STANDALONE = re.compile(
    r"\b(adults?|children|elderly|patients?|participants?|subjects?|mice|rats?|donors?|volunteers?)\b", re.I)
COMPARATOR_RE = re.compile(
    r"\b(?:versus|vs\.?|compared\s+(?:with|to|against)|against|relative\s+to)\s+([^,.;]{3,70}?)(?=\s+(?:in|among|for|to|"
    r"and|with|while|whereas)\b|[,.;]|$)", re.I)
OUTCOME_PHRASE_RE = re.compile(
    r"\b([a-z][a-z\-]*(?:\s+[a-z][a-z\-]*)?)\s+(rate|rates|score|scores|level|levels|index|risk|yield|response|"
    r"survival|persistence|efficacy|burden)\b", re.I)

FUNCTION_WORDS = {
    "versus", "vs", "patients", "patient", "adult", "adults", "children", "elderly", "identify", "identifies",
    "gene", "genes", "study", "studies", "screen", "screens", "screening", "improve", "improves", "improved",
    "improving", "rate", "rates", "relative", "standard", "therapy", "cell", "cells", "using", "use", "based",
    "following", "among", "into", "within", "will", "would", "should", "could", "also", "more", "less", "than",
    "that", "this", "these", "those", "with", "from", "were", "when", "where", "which", "have", "has", "had",
    "their", "there", "such", "other", "each", "both", "only", "very", "much", "many", "most", "some", "any",
    "all", "can", "may", "not", "but", "and", "the", "for", "does", "do", "make", "makes", "made", "new",
    "novel", "best", "first", "high", "low", "large", "small", "single", "multiple", "potential", "promising",
}

VERB_CUES = {"improve", "improves", "improved", "improving", "increase", "increases", "increased", "reduce",
             "reduces", "reduced", "identify", "identifies", "identified", "affect", "affects", "determine",
             "determines", "test", "tests", "evaluate", "assess", "explore", "investigate", "lead", "leads",
             "change", "changes", "change", "cause", "causes", "drive", "drives", "predict", "predicts"}

OUTCOME_HEADS = {"rate", "rates", "score", "scores", "level", "levels", "index", "risk", "yield", "response",
                 "survival", "persistence", "efficacy", "burden", "count", "counts", "accuracy", "sensitivity",
                 "specificity", "auc", "error", "errors", "指标", "评分", "率"}

INNOVATION_CUES = {
    "method": ("screen", "screening", "knockout", "knock-in", "crispr", "sequencing", "assay", "algorithm",
               "protocol", "pipeline", "imaging", "ablation", "modelling", "modeling", "platform", "tool",
               "workflow", "perturbation", "editing"),
    "data": ("dataset", "datasets", "cohort", "registry", "biobank", "sample", "samples", "omics",
             "transcriptome", "transcriptomic", "single-cell", "database", "records", "measurements",
             "longitudinal", "wastewater", "claims"),
    "transfer": ("translation", "translational", "across", "domain", "species", "adapt", "transfer",
                 "apply", "repurpose", "reposition", "generalise", "generalize", "in vivo", "in vitro",
                 "field", "clinic", "bedside"),
    "conclusion": ("revisit", "correct", "contradict", "challenge", "reinterpret", "revise", "reassess",
                   "reconcile", "refute", "confirm", "overturn", "reanalyse", "reanalyze", "replication"),
}


def classify_innovation(term):
    lowered = str(term).lower()
    for kind in ("method", "data", "transfer", "conclusion"):
        if any(cue in lowered for cue in INNOVATION_CUES[kind]):
            return kind
    return "method"


def innovation_phrase(kind, term):
    templates = {
        "method": "the analytical method '%s' is not used by any supplied record",
        "data": "the data source '%s' is not used by any supplied record",
        "transfer": "the transfer target '%s' is not addressed by any supplied record",
        "conclusion": "the conclusion linked to '%s' is not revisited or corrected by any supplied record",
    }
    return templates.get(kind, templates["method"]) % term


def extract_population(text):
    """Return the population phrase stated in the proposal (e.g. 'adult patients')."""
    match = POPULATION_IN.search(text or "")
    if match:
        return norm_space(match.group(1))
    match = POPULATION_STANDALONE.search(text or "")
    if match:
        return norm_space(match.group(1))
    return ""


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


def parse_year(value):
    """Return the publication year; a four-digit year wins over day/month digits."""
    if isinstance(value, int):
        return value if 1800 <= value <= 2100 else None
    match = re.search(r"(1[89]\d{2}|20\d{2})", as_text(value))
    return int(match.group(1)) if match else None


def date_type_of(value):
    text = as_text(value).lower()
    if not text:
        return "unknown"
    if "preprint" in text or "arxiv" in text or "biorxiv" in text or "medrxiv" in text:
        return "preprint"
    if "online" in text or "first" in text or "ahead of print" in text:
        return "online-first"
    if re.search(r"(1[89]\d{2}|20\d{2})", text):
        return "published"
    return "unknown"


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
    date_raw = as_text(pick(raw, ("year", "publication_year", "date", "published", "published_at")))
    return {
        "source_id": as_text(pick(raw, ("source_id", "record_id", "paper_id", "id"))) or ("A%02d" % (index + 1)),
        "locator": locator,
        "title": as_text(pick(raw, ("title", "name"))),
        "abstract": as_text(pick(raw, ("abstract", "summary"))),
        "year": parse_year(pick(raw, ("year", "publication_year", "date", "published", "published_at"))),
        "date_raw": date_raw,
        "date_type": date_type_of(date_raw),
        "doi": as_text(pick(raw, ("doi", "DOI"))),
        "venue": as_text(pick(raw, ("venue", "journal", "conference"))),
        "source_file": None,
        "source_key": None,
        "decision": None,
        "duplicate_of": None,
        "reason_code": None,
        "criteria_ids": [],
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
    population = extract_population(proposal)
    comparison = bool(re.search(r"versus|\bvs\.?\b|compared|control|placebo|对比|比较|对照", lowered))
    comparator_match = COMPARATOR_RE.search(proposal)
    comparator = norm_space(comparator_match.group(1)) if comparator_match else ""
    outcome_terms = []
    tokens = re.findall(r"[A-Za-z][A-Za-z\-]*", proposal)
    candidates = []
    for index, token in enumerate(tokens):
        if token.lower() not in OUTCOME_HEADS:
            continue
        qualifier = []
        position = index - 1
        while position >= 0 and len(qualifier) < 2:
            word = tokens[position].lower()
            if word in FUNCTION_WORDS or word in VERB_CUES or word in STOP:
                break
            qualifier.insert(0, word)
            position -= 1
        candidates.append(" ".join(qualifier + [token.lower()]))
    kept = []
    for phrase in sorted(set(candidates), key=lambda item: (-len(item.split()), item)):
        words = phrase.split()
        if any(all(word in other for word in words) for other in kept):
            continue
        kept.append(phrase)
    for phrase in sorted(kept, key=lambda item: proposal.lower().find(item)):
        outcome_terms.append(phrase)
    for cue in MEASURABLE:
        if cue in lowered and not any(cue in existing for existing in outcome_terms):
            outcome_terms.append(cue)
    independent = []
    for cue in ("crispr", "knockout", "knock-in", "screen", "screening", "inhibitor", "stimulation", "training",
                "diet", "dose", "treatment", "exposure", "car-t", "干预", "处理", "敲除", "抑制", "训练", "暴露"):
        if cue in lowered:
            independent.append(cue)
    intervention_phrase = ""
    lead = re.match(r"\s*(?:a|an|the)?\s*([^.;]{3,70}?)\s+will\s+", proposal or "", re.I)
    if lead:
        candidate = norm_space(lead.group(1))
        if 3 <= len(candidate) <= 70:
            intervention_phrase = candidate
    if not intervention_phrase:
        intervention_phrase = ", ".join(independent) or "the proposed intervention"
    vague = [word for word in VAGUE if word in lowered]
    if population:
        restated = "In %s, test whether %s changes %s" % (
            population, intervention_phrase, ", ".join(outcome_terms[:2]) if outcome_terms else "the stated outcome")
    else:
        restated = "Test whether %s changes %s" % (
            intervention_phrase, ", ".join(outcome_terms[:2]) if outcome_terms else "the stated outcome")
    if comparator:
        restated += " relative to %s" % comparator
    elif comparison:
        restated += " relative to a comparator"
    else:
        restated += " (no comparator stated)"
    return {
        "restated": restated,
        "population_hint": population or None,
        "comparator_hint": comparator or None,
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


def norm_key(text):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (text or "").lower())


DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)


def doi_key(value):
    text = norm_space(value).lower()
    return DOI_PREFIX.sub("", text).rstrip(".")


def clean_source_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def pdf_source_text(path):
    """Convert a PDF with pdftotext when it is installed; otherwise report the file as unparsed."""
    executable = shutil.which("pdftotext")
    if not executable:
        return "", "pdftotext_unavailable"
    try:
        proc = subprocess.run([executable, "-layout", str(path), "-"], capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return "", "pdftotext_failed"
    if proc.returncode != 0:
        return "", "pdftotext_exit_%d" % proc.returncode
    return clean_source_text(proc.stdout.decode("utf-8", errors="replace")), None


def collect_materials(root):
    """Read the real text materials under the input root so evidence can cite them."""
    materials = {"sources": [], "unparsed": [], "skipped": [], "errors": []}
    if root is None:
        return materials
    root = Path(root)
    try:
        if not root.exists():
            materials["errors"].append({"stage": "materials", "type": "root_missing",
                                        "message": "the resolved input root was not found"})
            return materials
    except OSError:
        return materials
    if root.is_file():
        base, candidates = root.parent, [root]
    else:
        base = root
        candidates = []
        try:
            for dirpath, dirnames, filenames in os.walk(str(root)):
                dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
                for name in sorted(filenames):
                    candidates.append(Path(dirpath) / name)
        except OSError:
            materials["errors"].append({"stage": "materials", "type": "walk_failed",
                                        "message": "the input root could not be walked"})
        candidates.sort(key=lambda item: item.as_posix())
    for path in candidates:
        try:
            relative = path.relative_to(base).as_posix()
        except ValueError:
            relative = path.name
        if path.name.lower() in ("case.json", "task.md", "result.json", "example-result.json"):
            continue
        if path.suffix.lower() not in SOURCE_EXTS:
            continue
        if len(materials["sources"]) >= MAX_SOURCE_FILES:
            materials["skipped"].append({"path": relative, "reason": "source_cap_reached"})
            continue
        try:
            if path.is_symlink() or not path.is_file():
                materials["skipped"].append({"path": relative, "reason": "not_a_regular_file"})
                continue
            size = path.stat().st_size
        except OSError:
            materials["unparsed"].append({"path": relative, "reason": "stat_failed"})
            continue
        if size > MAX_SOURCE_BYTES:
            materials["unparsed"].append({"path": relative, "reason": "file_too_large"})
            continue
        reason = None
        if path.suffix.lower() == ".pdf":
            text, reason = pdf_source_text(path)
        else:
            try:
                text = clean_source_text(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                text, reason = "", "read_failed"
        if not text:
            materials["unparsed"].append({"path": relative, "reason": reason or "empty_text"})
            continue
        truncated = len(text) > MAX_SOURCE_CHARS
        if truncated:
            text = text[:MAX_SOURCE_CHARS]
        materials["sources"].append({"key": "S%d" % (len(materials["sources"]) + 1), "path": relative,
                                     "ext": path.suffix.lower(), "chars": len(text),
                                     "truncated": truncated, "text": text})
    return materials


def attach_source_text(records, materials):
    """Match each record to a parsed source file by DOI, title or file name; return key hit counts."""
    sources = materials.get("sources") or []
    matched = {}
    if not sources:
        return matched
    stems = [Path(source["path"]).stem for source in sources]
    for record in records:
        target = None
        doi = doi_key(record.get("doi") or "")
        if doi:
            for source in sources:
                if doi in source["text"].lower():
                    target = source
                    break
        if target is None and record.get("title"):
            title_key = norm_key(record["title"])
            if len(title_key) >= 12:
                for source in sources:
                    if title_key in norm_key(source["text"]):
                        target = source
                        break
        if target is None and record.get("title"):
            title_tokens = set(tokenize(record["title"], 30))
            if title_tokens:
                for source, stem in zip(sources, stems):
                    stem_tokens = set(tokenize(stem.replace("_", " ").replace("-", " "), 30))
                    if not stem_tokens:
                        continue
                    if len(title_tokens & stem_tokens) >= max(2, int(round(0.6 * len(title_tokens)))):
                        target = source
                        break
        if target is None and record.get("title"):
            close = get_close_matches(record["title"], stems, n=1, cutoff=0.6)
            if close:
                for source, stem in zip(sources, stems):
                    if stem == close[0]:
                        target = source
                        break
        if target is not None:
            record["source_file"] = target["path"]
            record["source_key"] = target["key"]
            record["file_text"] = target["text"]
            record["file_text_flat"] = norm_space(target["text"])
            matched[target["key"]] = matched.get(target["key"], 0) + 1
    return matched


def text_of(record):
    return record.get("file_text_flat") or record["abstract"] or record["title"]


def source_locator(record, quote):
    """S3#P7 = paragraph 7 of the third parsed source file; falls back to the JSON pointer."""
    key = record.get("source_key")
    if not key:
        return record["locator"]
    text = record.get("file_text") or ""
    quote = norm_space(quote)
    if not quote or not text:
        return key
    paragraphs = [norm_space(block) for block in re.split(r"\n\s*\n", text) if norm_space(block)]
    for start in range(0, max(1, len(quote) - 29), 30):
        probe = quote[start:start + 30]
        if len(probe.strip()) < 10:
            continue
        for index, paragraph in enumerate(paragraphs, 1):
            if probe in paragraph:
                return "%s#P%d" % (key, index)
    return key


PROPOSAL_KEYS = ("proposal", "proposed_topic", "idea", "hypothesis", "research_question", "question", "topic", "aim")


def proposal_locator(case, task_text):
    if isinstance(case, dict):
        for key in PROPOSAL_KEYS:
            if case.get(key) not in (None, "", [], {}):
                return "/" + key
    return "/task.md" if task_text else "/proposal"


INCLUSION_KEYS = ("inclusion_criteria", "inclusion", "include_criteria", "eligibility_inclusion", "eligibility")
EXCLUSION_KEYS = ("exclusion_criteria", "exclusion", "exclude_criteria", "eligibility_exclusion")
PROTOCOL_KEYS = ("search_protocol", "retrieval_protocol", "screening_protocol", "protocol", "eligibility_protocol")
PROTOCOL_FIELDS = (("year_range", ("year_range", "date_range", "years", "time_window", "publication_window")),
                   ("languages", ("languages", "language")),
                   ("designs", ("designs", "study_designs", "design")),
                   ("publication_types", ("publication_types", "publication_type", "pub_types")))


def flatten_texts(value):
    if value is None:
        return []
    if isinstance(value, str):
        text = norm_space(value)
        return [text] if text else []
    if isinstance(value, dict):
        out = []
        for key in sorted(value.keys()):
            out.extend(flatten_texts(value[key]))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(flatten_texts(item))
        return out
    text = as_text(value)
    return [text] if text else []


def criteria_of(case):
    """Inclusion/exclusion criteria declared by the case, or a derived set that matches this run."""
    inclusions = flatten_texts(pick(case, INCLUSION_KEYS))
    exclusions = flatten_texts(pick(case, EXCLUSION_KEYS))
    if inclusions or exclusions:
        rows = []
        for index, text in enumerate(inclusions, 1):
            rows.append({"id": "I%d" % index, "text": text, "type": "inclusion", "origin": "case"})
        for index, text in enumerate(exclusions, 1):
            rows.append({"id": "X%d" % index, "text": text, "type": "exclusion", "origin": "case"})
        return rows, "case"
    derived = [
        ("I1", "inclusion", "the entry is a record object that carries a title or a DOI, so it can be identified uniquely"),
        ("I2", "inclusion", "the record's title, abstract and year are used for comparison; missing fields become a comparability gap rather than an exclusion"),
        ("X1", "exclusion", "a later record repeats the DOI, or the normalised title plus year, of an earlier record and is removed as a duplicate"),
        ("X2", "exclusion", "the entry is not a record object or carries neither a title nor a DOI"),
    ]
    return [{"id": i, "text": t, "type": k, "origin": "derived"} for i, k, t in derived], "derived"


def protocol_of(case):
    """Read a prospective screening/search protocol; state derived defaults when none is supplied."""
    raw = pick(case, PROTOCOL_KEYS)
    node = raw if isinstance(raw, dict) else {}
    protocol = {}
    for out_key, names in PROTOCOL_FIELDS:
        protocol[out_key] = as_text(pick(node, names)) or as_text(pick(case, names)) or None
    if any(protocol[key] for key, _ in PROTOCOL_FIELDS):
        protocol["origin"] = "case"
        protocol["note"] = "protocol fields were read from the case file"
    else:
        protocol.update({
            "year_range": "not restricted (no window declared)",
            "languages": "not restricted (no language restriction declared)",
            "designs": "not restricted (no design restriction declared)",
            "publication_types": "not restricted (no publication-type restriction declared)",
            "origin": "derived",
            "note": "no prospective protocol was supplied; the scope is the supplied batch only and no external search is claimed",
        })
    return protocol


def screening_flow(records, criteria):
    """One screening row per record plus a de-duplicated flow that closes arithmetically."""
    include_ids = [row["id"] for row in criteria if row["type"] == "inclusion"]
    exclude_ids = [row["id"] for row in criteria if row["type"] == "exclusion"]
    log, seen, duplicates = [], {}, 0
    for record in records:
        if record["doi"]:
            key = "doi:" + doi_key(record["doi"])
        elif record["title"]:
            key = "title:" + norm_key(record["title"]) + "|" + (str(record["year"]) if record["year"] is not None else "na")
        else:
            key = ""
        duplicate_of = None
        if key and key in seen:
            duplicate_of = seen[key]
            duplicates += 1
            record["decision"] = "duplicate"
            record["duplicate_of"] = duplicate_of
            record["reason_code"] = "DUPLICATE_DOI" if key.startswith("doi:") else "DUPLICATE_TITLE_YEAR"
            record["criteria_ids"] = exclude_ids
        else:
            if key:
                seen[key] = record["source_id"]
            if not (record["title"] or record["doi"]):
                record["decision"] = "exclude"
                record["reason_code"] = "NO_IDENTIFIER"
                record["criteria_ids"] = include_ids
            else:
                record["decision"] = "include"
                record["reason_code"] = "ELIGIBLE"
                record["criteria_ids"] = include_ids
        quote, _ = excerpt(text_of(record), 160)
        log.append({
            "source_id": record["source_id"],
            "doi": record["doi"] or None,
            "title": record["title"] or None,
            "stage": "deduplication" if record["decision"] == "duplicate" else "eligibility",
            "decision": record["decision"],
            "reason_code": record["reason_code"],
            "criteria_ids": record["criteria_ids"],
            "duplicate_of": record["duplicate_of"],
            "quote": quote,
            "quote_verified": bool(quote) and quote in text_of(record),
            "locator": source_locator(record, quote),
            "case_locator": record["locator"],
            "source_file": record.get("source_file") or None,
        })
    identified = len(records)
    unique = identified - duplicates
    included = sum(1 for record in records if record["decision"] == "include")
    excluded = unique - included
    flow = {
        "identified": identified,
        "duplicates": duplicates,
        "unique": unique,
        "screened": unique,
        "excluded": excluded,
        "included": included,
        "arithmetic_closure": identified == duplicates + unique and unique == included + excluded,
        "closure_rule": "identified = duplicates + unique; unique = screened = included + excluded",
    }
    return log, flow


QUERY_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9\-]{3,}|[\u4e00-\u9fff]{2,}")


def query_keywords(query):
    words = []
    for token in QUERY_TOKEN.findall(query or ""):
        lowered = token.lower()
        if lowered in ("and", "or", "not", "the", "with", "from", "versus"):
            continue
        if lowered not in words:
            words.append(lowered)
    return words


def query_hits(query, records):
    words = query_keywords(query)
    if not words:
        return 0
    hits = 0
    for record in records:
        blob = " ".join([record["title"], record["abstract"], record.get("file_text_flat") or ""]).lower()
        if any(word in blob for word in words):
            hits += 1
    return hits


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
        if path.name.lower() in OUTPUT_NAMES and not root.is_file():
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


def build_manifest_summary(root, materials, policy):
    files = build_manifest(root, pol(policy, "caps.max_manifest_files", 200),
                           pol(policy, "caps.manifest_hash_bytes", 1048576))
    sources = materials.get("sources") or []
    return {
        "files": files,
        "file_count": len(files),
        "sources_found": len(sources),
        "source_files": [{"key": source["key"], "path": source["path"], "ext": source["ext"],
                          "chars": source["chars"], "truncated": source["truncated"]} for source in sources],
        "unparsed": materials.get("unparsed") or [],
        "skipped": materials.get("skipped") or [],
        "note": "case.json is the case definition and is not treated as a source paper; md/txt/csv/json files are read as text, pdf files are converted with pdftotext when it is installed",
    }


def retrieval_scope(terms, records, included, task_text, criteria, criteria_origin, screening_log, flow,
                    protocol, materials):
    missing_abstract = [record["source_id"] for record in included
                        if not record["abstract"] and not record.get("file_text_flat")]
    missing_year = [record["source_id"] for record in included if record["year"] is None]
    unmatched = [record["source_id"] for record in included if not record.get("source_file")]
    sources = materials.get("sources") or []
    unparsed = materials.get("unparsed") or []
    phrases = []
    for record in included:
        for phrase in sorted(bigrams(record["title"])):
            if phrase in " ".join(terms) and phrase not in phrases:
                phrases.append(phrase)
    core = [term for term in terms if len(term) >= 4][:6]
    queries = []
    if phrases[:2]:
        queries.append('"%s" AND (%s)' % (phrases[0], " OR ".join('"%s"' % item for item in phrases[1:3] or core[:2])))
    if len(core) >= 2:
        queries.append("(%s) AND (%s)" % (" OR ".join(core[:3]), " OR ".join(core[3:6] or core[:3])))
    if not queries:
        queries.append(" ".join(core) if core else "(no retrievable terms in the proposal)")
    hits = [{"query": query, "hits": query_hits(query, included),
             "method": "offline keyword match over the supplied titles, abstracts and attached source text; no database was queried"}
            for query in queries]
    inclusion_rows = [row for row in criteria if row["type"] == "inclusion"]
    exclusion_rows = [row for row in criteria if row["type"] == "exclusion"]
    coverage_gap = [
        "no external database search was run, so recall beyond the supplied batch is unknown",
        "no text material was found under the input root, so locators stay at JSON-pointer level" if not sources
        else "%d source file(s) were parsed as text and matched to records" % len(sources),
    ]
    if unparsed:
        coverage_gap.append("%d source file(s) could not be parsed and are listed in unparsed_sources" % len(unparsed))
    if unmatched:
        coverage_gap.append("%d included record(s) could not be matched to a source file; they are cited by JSON pointer"
                            % len(unmatched))
    if missing_abstract:
        coverage_gap.append("%d record(s) carry neither an abstract nor a source file" % len(missing_abstract))
    if missing_year:
        coverage_gap.append("%d record(s) carry no year" % len(missing_year))
    return {
        "query": " ".join(terms[:8]),
        "queries": queries,
        "query_basis": "Boolean strings built from proposal terms and title bigrams; they are stated so a human can paste them into a literature database, but no search engine or network call is executed here",
        "database": "not_applicable (supplied batch only)",
        "executed_on": "supplied_batch",
        "executed_at": "not_applicable (offline run, no wall-clock anchor)",
        "identified_count": flow.get("identified", 0),
        "included_count": flow.get("included", len(included)),
        "hits_per_query": hits,
        "criteria": criteria,
        "criteria_origin": criteria_origin,
        "screening_log": screening_log,
        "flow": flow,
        "applied_protocol": protocol,
        "inclusion": "; ".join("%s: %s" % (row["id"], row["text"]) for row in inclusion_rows) or "no inclusion criterion is declared",
        "exclusion": ["%s: %s" % (row["id"], row["text"]) for row in exclusion_rows],
        "batch_size": len(records),
        "screened_out": {"duplicates": flow.get("duplicates", 0), "excluded": flow.get("excluded", 0),
                         "missing_abstract": len(missing_abstract), "missing_year": len(missing_year)},
        "sources_found": len(sources),
        "source_files": [{"key": source["key"], "path": source["path"], "ext": source["ext"],
                          "chars": source["chars"], "truncated": source["truncated"]} for source in sources],
        "unparsed_sources": unparsed,
        "coverage_gap": coverage_gap,
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
        if not record["abstract"] and not record.get("file_text_flat"):
            reason = "title-only record: no abstract and no source file, so method, data and outcome cannot be compared"
        elif not row["shared_terms"]:
            reason = "no shared content term with the proposal; only topical adjacency is recorded"
        elif record["year"] is None:
            reason = "publication year absent, so recency relative to the proposal cannot be established"
        else:
            reason = None
        rows.append({
            "source_id": record["source_id"],
            "locator": record["locator"],
            "source_file": record.get("source_file"),
            "title": record["title"],
            "year": record["year"],
            "shared_terms": row["shared_terms"],
            "shared_phrases": row["shared_phrases"],
            "overlap": row["overlap"],
            "overlap_class": row["relation"],
            "comparison_fields": ["title", "abstract", "source_file", "year"],
            "not_comparable_reason": reason,
        })
    return rows


def ids_mentioning(records, terms):
    found = []
    for record in records:
        blob = (record["title"] + " " + text_of(record)).lower()
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
            "innovation_type": "method",
            "scope": "structural",
            "covered_by": covered,
            "verdict": "covered" if covered else "not_found_in_batch",
            "basis": "intervention terms were matched against every supplied title and abstract; coverage here is batch-bounded",
        })
    if outcomes:
        covered = ids_mentioning(records, outcomes)
        checks.append({
            "claim": "the stated outcome (%s) has not been measured before" % ", ".join(outcomes),
            "innovation_type": "conclusion",
            "scope": "structural",
            "covered_by": covered,
            "verdict": "covered" if covered else "not_found_in_batch",
            "basis": "outcome indicators were matched against every supplied title and abstract",
        })
    if intervention and outcomes:
        both, only_intervention, only_outcome = [], [], []
        for record in records:
            blob = (record["title"] + " " + text_of(record)).lower()
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
            "innovation_type": "method",
            "scope": "structural",
            "covered_by": both,
            "verdict": verdict,
            "basis": basis + "; this is a batch observation, not a novelty guarantee",
        })
    for term in unique_terms[:limit]:
        hits = ids_mentioning(records, [term])
        kind = classify_innovation(term)
        checks.append({
            "claim": innovation_phrase(kind, term) if not hits
                     else "term '%s' also appears in other supplied records and is not a differentiator by itself" % term,
            "innovation_type": kind,
            "scope": "differentiator",
            "term": term,
            "covered_by": hits,
            "verdict": "not_found_in_batch" if not hits else "covered",
            "basis": "term-by-term search over every supplied title and abstract; a batch observation, not a priority claim",
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
        blob = (record["title"] + " " + text_of(record)).lower()
        if outcome_terms and any(term in blob for term in outcome_terms):
            eligible.append((record, polarity(blob)))
    positives = [item[0] for item in eligible if item[1] == "positive"]
    negatives = [item[0] for item in eligible if item[1] == "negative"]
    rows = []
    for positive in positives[:3]:
        for negative in negatives[:3]:
            rows.append({
                "claim": "supplied records disagree on the stated outcome",
                "supporting": [{"source_id": positive["source_id"],
                                "locator": source_locator(positive, excerpt(text_of(positive), quote_limit)[0]),
                                "quote": excerpt(text_of(positive), quote_limit)[0]}],
                "conflicting": [{"source_id": negative["source_id"],
                                 "locator": source_locator(negative, excerpt(text_of(negative), quote_limit)[0]),
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
    combo_rows = [check for check in checks if "intervention x outcome" in str(check.get("claim", ""))]
    combo_covered = any(check["verdict"] == "covered" for check in combo_rows)
    open_differentiators = [check for check in checks
                            if check.get("scope") == "differentiator" and check["verdict"] == "not_found_in_batch"]
    if not proposal or not records:
        verdict = "hold"
        conditions.insert(0, "provide a proposal and a prior-art batch before a go/hold judgement")
    elif feasible["blockers"]:
        verdict = "hold"
        conditions.insert(0, "resolve blockers: " + ", ".join(feasible["blockers"]))
    elif combo_covered and not open_differentiators:
        verdict = "hold"
        covered_ids = sorted({source for check in combo_rows for source in check.get("covered_by", [])})
        conditions.insert(0, "the intervention x outcome combination is already reported by %s; state a "
                             "substantive differentiator (method, data, transfer or conclusion revision) before "
                             "claiming novelty" % (", ".join(covered_ids) or "the supplied batch"))
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
            "intervention x outcome already reported: %s; open differentiators: %d"
            % ("yes" if combo_covered else "no", len(open_differentiators)),
        ],
        "decision_scope": "planning aid only; not a funding, ethics, personnel or publication decision",
    }


def needs_human_confirmation(case, proposal_loc, form, records, novelty_rows, feasible, conflicts, resources):
    items = []
    for record in records:
        if not record["abstract"] and not record.get("file_text_flat"):
            items.append({"item": "read the full text of %s" % record["source_id"], "locator": record["locator"],
                          "reason": "no abstract or source file was supplied; the comparison uses the title only"})
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
                locator = source_locator(record, excerpt(text_of(record), 240)[0])
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
        rows.append({"evidence_id": "E%02d" % (len(rows) + 1), "kind": "proposal", "source_id": "proposal",
                     "locator": proposal_loc, "case_locator": proposal_loc, "source_file": None,
                     "decision": None, "reason_code": None, "criteria_ids": [],
                     "quote": quote, "quote_verified": quote in proposal, "truncated": truncated})
    overlap_by_id = {}
    for row in novelty_rows:
        overlap_by_id[row["source_id"]] = row
    for record in records:
        source = text_of(record)
        quote, truncated = excerpt(source, quote_limit)
        row = overlap_by_id.get(record["source_id"], {})
        rows.append({"evidence_id": "E%02d" % (len(rows) + 1), "kind": "prior_art",
                     "source_id": record["source_id"], "locator": source_locator(record, quote),
                     "case_locator": record["locator"], "source_file": record.get("source_file"),
                     "decision": record.get("decision"), "reason_code": record.get("reason_code"),
                     "criteria_ids": record.get("criteria_ids") or [],
                     "quote": quote, "quote_verified": bool(quote) and quote in source, "truncated": truncated,
                     "year": record["year"], "overlap": row.get("overlap"),
                     "overlap_class": row.get("relation")})
    return rows


SEVERITY_RANK = {"critical": 3, "major": 2, "minor": 1}

ASPECTS = (("question_definition", "问题定义"),
           ("prior_work_comparison", "已有工作比较"),
           ("novelty_identification", "创新点识别"),
           ("feasibility_judgment", "可行性判断"),
           ("evidence_traceback", "证据回链"))


def severity_rubric():
    return {
        "declared_at": "precheck",
        "scale": "critical > major > minor",
        "levels": [
            {"level": "critical", "definition": "the proposal cannot be defended as written: a feasibility blocker, a non-falsifiable claim, or an innovation statement already covered by a supplied record",
             "action": "resolve before any go decision"},
            {"level": "major", "definition": "a claim needs a stated boundary, comparator, full-text check or source that is currently missing",
             "action": "revise the proposal text or obtain the missing material"},
            {"level": "minor", "definition": "presentation or traceability gap that does not change the verdict",
             "action": "fix in the next revision"},
        ],
        "category_enum": ["fact_error", "insufficient_evidence", "norm_issue", "suggestion"],
        "status_enum": ["confirmed", "pending"],
        "note": "levels are declared before any finding is produced so each finding is read against a fixed scale",
    }


def finding_entry(out, aspect, category, severity, quote, location, evidence, suggestion, status):
    out.append({"finding_id": "F%02d" % (len(out) + 1), "aspect": aspect, "category": category,
                "severity": severity, "quote": quote or "", "location": location or "",
                "evidence": evidence or [], "revision_suggestion": suggestion, "status": status})


def build_findings(proposal, proposal_loc, form, novelty_rows, comparison, checks, feasible, conflicts,
                   records, evidence_ids, resources):
    findings = []
    if proposal:
        if not form["tests"]["has_outcome_measure"]:
            finding_entry(findings, "question_definition", "insufficient_evidence", "critical",
                          excerpt(proposal, 160)[0], proposal_loc, [],
                          "写出主结局指标、测量工具与判定阈值，使结论可被证伪。", "confirmed")
        if not form["tests"]["has_comparator"]:
            finding_entry(findings, "question_definition", "insufficient_evidence", "major",
                          excerpt(proposal, 160)[0], proposal_loc, [],
                          "补充明确的对照或基线条件，否则观察到的差异无法归因。", "confirmed")
        for term in form["vague_terms"][:3]:
            position = proposal.lower().find(term.lower())
            quote = proposal[position:position + len(term)] if position >= 0 else term
            finding_entry(findings, "question_definition", "norm_issue", "major", quote, proposal_loc, [],
                          "把「%s」替换为可操作的量化定义，或直接删去该措辞。" % term, "confirmed")
    by_id = {}
    for record in records:
        by_id[record["source_id"]] = record
    for row in novelty_rows[:4]:
        if row["relation"] not in ("direct_overlap", "partial_overlap"):
            continue
        record = by_id.get(row["source_id"])
        if record is None:
            continue
        quote = excerpt(text_of(record), 160)[0]
        finding_entry(findings, "prior_work_comparison", "norm_issue",
                      "critical" if row["relation"] == "direct_overlap" else "major",
                      quote, source_locator(record, quote), evidence_ids.get(record["source_id"], []),
                      "在提案中逐条写明与 %s 的方法、数据或结论差异，否则重叠会被读成重复工作。" % record["source_id"],
                      "confirmed")
    for row in comparison[:4]:
        reason = row.get("not_comparable_reason")
        if not reason:
            continue
        record = by_id.get(row["source_id"])
        if record is None:
            continue
        quote = excerpt(text_of(record), 160)[0]
        finding_entry(findings, "prior_work_comparison", "insufficient_evidence",
                      "major" if "title-only" in reason else "minor", quote,
                      source_locator(record, quote), evidence_ids.get(record["source_id"], []),
                      "补全该记录的摘要、年份或全文后重新比较，不要以标题级信息下结论。", "pending")
    for check in checks:
        if check.get("verdict") not in ("covered", "partially_covered"):
            continue
        covered_ids = [item for item in check.get("covered_by") or [] if item in by_id]
        first = by_id[covered_ids[0]] if covered_ids else None
        quote = excerpt(text_of(first), 160)[0] if first is not None else ""
        location = source_locator(first, quote) if first is not None else proposal_loc
        evidence = [eid for source_id in covered_ids[:2] for eid in evidence_ids.get(source_id, [])]
        finding_entry(findings, "novelty_identification",
                      "fact_error" if check.get("verdict") == "covered" else "insufficient_evidence",
                      "major", quote, location, evidence,
                      "该创新陈述（%s）已被批内记录覆盖或部分覆盖；改写为未被覆盖的差异点或撤回。" % str(check.get("claim"))[:80],
                      "confirmed" if first is not None else "pending")
        if len(findings) >= 24:
            break
    for check in checks:
        if check.get("scope") != "differentiator" or check.get("verdict") != "not_found_in_batch":
            continue
        finding_entry(findings, "novelty_identification", "suggestion", "minor", "", proposal_loc, [],
                      "差异词项「%s」只在批内未出现，须经全文与查新复核后才能作为创新点。" % (check.get("term") or "?"),
                      "pending")
        if len(findings) >= 26:
            break
    for check in feasible["checks"]:
        if check["status"] == "pass":
            continue
        finding_entry(findings, "feasibility_judgment", "insufficient_evidence",
                      "critical" if check["status"] == "blocker" else "major", "", "/resources", [],
                      "%s：%s；在提案中补齐该前提，或把它明确标为假设。" % (check["check"], check["detail"]),
                      "pending")
        if len(findings) >= 28:
            break
    unmatched = [record for record in records if not record.get("source_file")]
    if unmatched:
        finding_entry(findings, "evidence_traceback", "insufficient_evidence", "major", "",
                      unmatched[0]["locator"], [],
                      "有 %d 条纳入记录未匹配到输入目录下的原文；取得原文或 PDF 后重跑，使定位从 JSON 指针升级为源文件段落（如 S1#P2）。"
                      % len(unmatched), "pending")
    for row in conflicts:
        if not str(row.get("resolution", "")).startswith("unresolved"):
            continue
        supporting = (row.get("supporting") or [{}])[0]
        conflicting = (row.get("conflicting") or [{}])[0]
        finding_entry(findings, "evidence_traceback", "insufficient_evidence", "major",
                      supporting.get("quote") or conflicting.get("quote") or "",
                      supporting.get("locator") or conflicting.get("locator") or "/", [],
                      "相反结论并列保留；补齐研究设计与效应量字段后再裁决，不要单边取舍。", "pending")
        break
    if not resources:
        finding_entry(findings, "feasibility_judgment", "insufficient_evidence", "major", "",
                      "/resources", [],
                      "未声明数据、样本、时间与方法条件；可行性只能做部分检查，须补交资源声明。", "pending")
    return findings[:30]


def build_aspect_coverage(findings, proposal, records, resources, evidence):
    gaps = {}
    if not proposal:
        gaps["question_definition"] = "no proposal text was found in the case or the task file"
    if not records:
        gaps["prior_work_comparison"] = "no prior-art record could be compared"
        gaps["novelty_identification"] = "novelty cannot be tested without prior-art records"
    if not resources:
        gaps["feasibility_judgment"] = "no resource or constraint declaration was supplied"
    if not evidence:
        gaps["evidence_traceback"] = "no evidence row could be attached to any source"
    rows = []
    for aspect, label in ASPECTS:
        hits = [item for item in findings if item["aspect"] == aspect]
        if aspect in gaps:
            status, note = "gap", gaps[aspect]
        elif hits:
            status = "checked"
            note = "%d issue(s) recorded against this aspect" % len(hits)
        else:
            status, note = "checked_no_issue", "checked with the supplied material; no issue was recorded"
        severity_max = None
        if hits:
            severity_max = max((item["severity"] for item in hits), key=lambda level: SEVERITY_RANK.get(level, 0))
        rows.append({"aspect": aspect, "label": label, "status": status, "findings": len(hits),
                     "severity_max": severity_max, "note": note})
    return rows


def render_review_report(case_id, status, result, findings, coverage, evidence, sources_found):
    form = result.get("testable_form") or {}
    novelty = result.get("novelty_assessment") or {}
    feasible = result.get("feasibility") or {}
    synth = result.get("synthesis") or {}
    scope = result.get("retrieval_scope") or {}
    flow = scope.get("flow") or {}
    tests = form.get("tests") or {}
    counts = {"critical": 0, "major": 0, "minor": 0}
    for item in findings:
        counts[item.get("severity", "minor")] = counts.get(item.get("severity", "minor"), 0) + 1
    checked = [row for row in coverage if row["status"] in ("checked", "checked_no_issue")]
    located = len([row for row in evidence if "#P" in str(row.get("locator") or "")])
    first = findings[0] if findings else None
    pending = [item for item in result.get("needs_human_confirmation") or []]
    paragraphs = [
        "一、总体结论。案例 %s 的运行状态为 %s。研究设想被改写为「%s」；可检验性判为%s，%s。批内新颖度为 %s（%d 分），与本批最近工作的词项重叠为 %.2f；可行性判为 %s；综合建议为 %s。以上判断只覆盖输入提供的材料，不构成全局查新、专利检索或资助结论。"
        % (case_id or "unknown", status, form.get("restated") or "（材料不足以改写）",
           "可检验" if tests.get("is_falsifiable") else "尚不可检验",
           "结局指标与对照均已给出" if tests.get("is_falsifiable") else "缺可测结局或对照",
           novelty.get("level"), novelty.get("score", 0), novelty.get("best_overlap") or 0.0,
           feasible.get("verdict"), synth.get("verdict")),
        "二、五面小结。题面要求的问题定义、已有工作比较、创新点识别、可行性判断与证据回链共 %d 个面，%d 个面已检查，%d 个面因材料不足记为 gap（%s）。"
        % (len(coverage), len(checked), len(coverage) - len(checked),
           "、".join("%s=%s" % (row["label"], row["status"]) for row in coverage)),
        "三、材料与筛选。输入目录内解析到 %d 份原文；题录共 %d 条，去重后 %d 条，纳入筛选 %d 条，纳入比较 %d 条；证据条目 %d 条，其中 %d 条已定位到源文件段落（形如 S1#P2），其余回到 JSON 指针。"
        % (sources_found, flow.get("identified", 0), flow.get("unique", 0), flow.get("screened", 0),
           flow.get("included", 0), len(evidence), located),
        "四、问题清单。共记录 %d 条评审意见：critical %d 条、major %d 条、minor %d 条。%s"
        % (len(findings), counts["critical"], counts["major"], counts["minor"],
           ("最需要先处理的是 %s（%s，%s）：%s" % (first["finding_id"], first["aspect"], first["severity"],
                                                    first["revision_suggestion"]))
           if first else "在已检查项上未发现需要修改的问题，但仍需专家复核。"),
        "五、待复核。%s"
        % ("；".join("%s［%s］" % (item.get("item"), item.get("locator")) for item in pending[:5]) or "无"),
        "六、使用边界。本报告由确定性脚本在离线环境生成，阈值与分级口径见 references/method.md；证据定位符 /prior_art/0 指向 case.json 字段，S1#P2 指向输入目录下第 1 份源文件的第 2 段。"
    ]
    return "\n\n".join(paragraphs)


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
    materials = collect_materials(input_root)
    attach_source_text(records, materials)
    proposal = proposal_of(case, task_text)
    proposal_loc = proposal_locator(case, task_text)
    resources = resources_of(case)
    criteria, criteria_origin = criteria_of(case)
    screening_log, flow = screening_flow(records, criteria)
    included = [record for record in records if record.get("decision") == "include"]
    terms = tokenize(proposal, limit=max_terms)
    form = testable_form(proposal)
    novelty_rows, novelty = assess_novelty(terms, included, direct, partial, phrase_bonus)
    feasible = feasibility(proposal, resources)
    unique = differentiators(terms, novelty_rows)[:max_checks]
    batch_candidates = [term for term in terms if not ids_mentioning(included, [term])]
    batch_unique = [term for term in batch_candidates
                    if term.lower() not in FUNCTION_WORDS and len(term) >= 3][:max_checks]
    style_notes = [term for term in batch_candidates if term not in batch_unique]

    scope = retrieval_scope(terms, records, included, task_text, criteria, criteria_origin,
                            screening_log, flow, protocol_of(case), materials)
    comparison = build_comparison(novelty_rows, included, max_rows)
    checks = innovation_checks(form, included, batch_unique, max_checks)
    conflicts = conflicting_evidence(included, form["outcome_indicators"], quote_limit)
    synth = synthesis(form, novelty, feasible, checks, included, proposal)
    evidence = build_evidence(included, proposal, proposal_loc, novelty_rows, quote_limit)
    human = needs_human_confirmation(case, proposal_loc, form, included, novelty_rows, feasible, conflicts, resources)

    if not proposal or not included:
        status = "insufficient_input"
    elif not form["tests"]["is_falsifiable"] or not resources:
        status = "partial"
    else:
        status = "success"

    evidence_ids = {}
    for row in evidence:
        if row.get("kind") == "prior_art":
            evidence_ids.setdefault(row["source_id"], []).append(row["evidence_id"])
    findings = build_findings(proposal, proposal_loc, form, novelty_rows, comparison, checks, feasible,
                              conflicts, included, evidence_ids, resources)
    coverage = build_aspect_coverage(findings, proposal, included, resources, evidence)
    sources_found = len(materials.get("sources") or [])
    review_report = render_review_report(
        case_identifier(case) or "unknown", status,
        {"testable_form": form, "novelty_assessment": novelty, "feasibility": feasible,
         "synthesis": synth, "retrieval_scope": scope, "needs_human_confirmation": human},
        findings, coverage, evidence, sources_found)

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
    if not included:
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
    if not included:
        gaps.append({"type": "no_prior_art_batch", "basis": "the novelty score is not meaningful without prior art"})
    if novelty["close_works"] == 0 and included:
        gaps.append({"type": "no_close_work_in_batch",
                     "basis": "no supplied record exceeds the partial-overlap threshold; this is a batch observation, not proof of novelty"})
    if not resources:
        gaps.append({"type": "no_resources_declared", "basis": "feasibility only checks what is declared"})
    if any(not record["abstract"] and not record.get("file_text_flat") for record in included):
        gaps.append({"type": "title_only_records",
                     "basis": "records without an abstract or a source file cannot support a method-level comparison"})
    if sources_found == 0:
        gaps.append({"type": "no_source_text",
                     "basis": "no parsable source file was found under the input root; evidence stays at the JSON-pointer level"})

    uncertainty = []
    if not proposal:
        uncertainty.append({"type": "no_proposal", "detail": "No proposal or research question was found."})
    if not included:
        uncertainty.append({"type": "no_prior_art", "detail": "No prior-art record was supplied."})
    if not resources:
        uncertainty.append({"type": "no_resources", "detail": "No resources or constraints were declared; feasibility checks are incomplete."})
    if not form["tests"]["is_falsifiable"]:
        uncertainty.append({"type": "not_falsifiable_as_written", "detail": "The proposal lacks a measurable outcome and/or comparator."})
    if any(not record["abstract"] and not record.get("file_text_flat") for record in included):
        uncertainty.append({"type": "title_only_records", "detail": "At least one record has neither an abstract nor a source file."})
    if sources_found == 0:
        uncertainty.append({"type": "no_source_text",
                            "detail": "No text material was parsed from the input root; locators are JSON pointers into case.json."})
    if materials.get("unparsed"):
        uncertainty.append({"type": "source_unparsed",
                            "detail": "%d source file(s) could not be parsed; see input_manifest.unparsed." % len(materials["unparsed"])})
    if sources_found and any(not record.get("source_file") for record in included):
        uncertainty.append({"type": "source_unmatched",
                            "detail": "At least one included record could not be matched to a parsed source file."})
    uncertainty.append({"type": "batch_only", "detail": "Novelty is relative to the supplied batch; no external search or expert panel was used."})

    result = {
        "proposal": proposal,
        "review_report": review_report,
        "aspect_coverage": coverage,
        "findings": findings,
        "severity_rubric": severity_rubric(),
        "testable_form": form,
        "novelty_assessment": novelty,
        "prior_art_table": novelty_rows,
        "differentiators": unique,
        "style_notes": {
            "note": "single function words or generic verbs found only in the proposal are recorded here and are not counted as innovation claims",
            "terms": style_notes,
        },
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
            "comparison_rule": "every included record is compared on title, abstract and year; records that cannot be compared carry not_comparable_reason",
            "screening_rule": "records are identified from the case, de-duplicated by DOI or normalised title plus year, and screened against the declared criteria; the flow closes arithmetically",
            "material_rule": "md/txt/csv/json files under the input root are read as text and matched to records by DOI, title or file name; PDFs are converted with pdftotext when available, otherwise they are listed as unparsed",
            "evidence_rule": "quotes are exact substrings of the cited text; locators are S1#P2 (paragraph 2 of the first source file) when a source file is matched, else a JSON pointer such as /prior_art/0",
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
            "Source matching relies on DOI, title and file-name similarity; a renamed file without a DOI or title may stay unmatched.",
        ],
        "change_log": [
            "Restated the proposal and checked whether it is falsifiable as written.",
            "Read the text materials under the input root and matched them to records.",
            "Declared the criteria, protocol and screening log, and closed the identified/duplicate/included counts.",
            "Compared proposal terms with each included prior-art record and recorded comparability.",
            "Checked each innovation statement against every supplied record.",
            "Kept opposing outcome reports unresolved and carried them into the synthesis.",
            "Checked feasibility against declared data, sample, time, methods and ethics.",
            "Derived review findings with a pre-declared severity scale, coverage per aspect, and a written review report.",
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
        "stats": {"records": len(included), "records_identified": flow.get("identified", 0),
                  "duplicates": flow.get("duplicates", 0), "excluded": flow.get("excluded", 0),
                  "sources_found": sources_found, "sources_unparsed": len(materials.get("unparsed") or []),
                  "evidence": len(evidence), "findings": len(findings),
                  "findings_critical": sum(1 for item in findings if item["severity"] == "critical"),
                  "aspects_checked": sum(1 for row in coverage if row["status"] in ("checked", "checked_no_issue")),
                  "report_chars": len(review_report),
                  "proposal_terms": len(terms), "close_works": novelty["close_works"],
                  "blockers": len(feasible["blockers"]), "innovation_checks": len(checks),
                  "conflicts": len([row for row in conflicts if "conflicting" in row]),
                  "human_confirmation_items": len(human), "network": "disabled"},
        "input_manifest": build_manifest_summary(input_root, materials, policy),
        "run": {"entrypoint": "scripts/sk_entry.py", "network": "disabled", "stdlib_only": True,
                "deterministic": True, "reads_source_text": True,
                "policy_version": pol(policy, "version", "unknown")},
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
    "findings": "findings",
    "issues": "findings",
    "review_findings": "findings",
    "review_report": "review_report",
    "report_markdown": "review_report",
    "aspect_coverage": "aspect_coverage",
    "coverage": "aspect_coverage",
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
        "result": {
            "assessment": {"status": "not_produced",
                           "reason": "the run failed before any assessment could be produced"},
            "review_report": "本次运行在生成评审结论前失败，未产出任何评估结果。result.json 仍然写出，以保留运行状态、错误信息与空的证据表；失败原因见 errors[]。修复输入后可用同一命令重跑。所有缺失字段都不以推断值填充。",
            "aspect_coverage": [],
            "findings": [],
            "severity_rubric": severity_rubric(),
        },
        "evidence": [],
        "uncertainty": [{"type": "run_failure", "detail": "Run failed; no assessment is reported."}],
        "errors": list(errors),
        "stats": {"records": 0, "network": "disabled"},
        "input_manifest": {"files": [], "file_count": 0, "sources_found": 0, "source_files": [],
                           "unparsed": [], "skipped": []},
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


def write_artifacts(out_dir, payload):
    """Write the report, the evidence table, the screening log and a provenance map next to result.json."""
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    if not result:
        return []
    target = Path(out_dir)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return []
    form = result.get("testable_form") or {}
    novelty = result.get("novelty_assessment") or {}
    feasible = result.get("feasibility") or {}
    synth = result.get("synthesis") or {}
    scope = result.get("retrieval_scope") or {}
    written = []

    def register(name):
        if os.path.exists(str(target / name)):
            written.append(name)

    lines = ["# Research proposal novelty and feasibility assessment", "",
             "Status: %s | Case: %s" % (payload.get("status"), payload.get("case_id")), ""]
    review = result.get("review_report")
    if review:
        lines += ["## 0. 评审成文", "", review, ""]
    lines += ["## 1. Testable form", "",
              "- Restated: %s" % (form.get("restated") or "not derived"),
              "- Population: %s" % (form.get("population_hint") or "not stated"),
              "- Comparator: %s" % (form.get("comparator_hint") or ("stated generically" if form.get("has_comparator") else "not stated")),
              "- Outcome indicators: %s" % (", ".join(form.get("outcome_indicators") or []) or "none"),
              "- Falsifiable as written: %s" % ("yes" if (form.get("tests") or {}).get("is_falsifiable") else "no"),
              "", "## 2. Novelty against the supplied batch", "",
              "- Score: %s (%s); closest overlap %.2f" % (novelty.get("score"), novelty.get("level"), novelty.get("best_overlap") or 0.0),
              "- Scope: %s" % (novelty.get("scope") or ""), "",
              "| source | year | overlap | class | title |", "|---|---|---|---|---|"]
    for row in result.get("prior_art_table") or []:
        lines.append("| %s | %s | %.2f | %s | %s |" % (row.get("source_id"), row.get("year") if row.get("year") is not None else "n/a",
                                                        row.get("overlap") or 0.0, row.get("relation"), row.get("title")))
    lines += ["", "## 3. Innovation checks by type", ""]
    checks = result.get("innovation_checks") or []
    for kind in ("method", "data", "transfer", "conclusion"):
        rows = [check for check in checks if check.get("innovation_type") == kind]
        if not rows:
            continue
        lines.append("**%s**" % kind)
        for check in rows:
            lines.append("- %s -> %s (%s)" % (check.get("claim"), check.get("verdict"),
                                               ", ".join(check.get("covered_by") or []) or "no hit"))
        lines.append("")
    style = (result.get("style_notes") or {}).get("terms") or []
    if style:
        lines += ["Function words recorded but excluded from coverage: %s" % ", ".join(style), ""]
    lines += ["## 4. Feasibility", "", "- Verdict: %s" % feasible.get("verdict"),
              "- Blockers: %s" % (", ".join(feasible.get("blockers") or []) or "none"),
              "- Warnings: %s" % (", ".join(feasible.get("warnings") or []) or "none"), ""]
    conflicts = result.get("conflicting_evidence") or []
    lines += ["## 5. Conflicting evidence", ""]
    if conflicts:
        for row in conflicts:
            lines.append("- %s: %s" % (row.get("claim") or "outcome", row.get("resolution") or "unresolved"))
    else:
        lines.append("- none detected in the supplied batch")
    lines += ["", "## 6. Synthesis", "", "- Verdict: %s" % synth.get("verdict")]
    for condition in synth.get("conditions") or []:
        lines.append("- Condition: %s" % condition)
    lines += ["- Basis: %s" % "; ".join(synth.get("basis") or []), "",
              "## 7. Gaps and human confirmation", ""]
    for gap in result.get("research_gaps") or []:
        lines.append("- Gap (%s): %s" % (gap.get("type"), gap.get("basis")))
    for item in result.get("needs_human_confirmation") or []:
        lines.append("- Confirm: %s [%s]" % (item.get("item"), item.get("locator")))
    lines += ["", "## 8. Findings and aspect coverage", "",
              "| finding | aspect | category | severity | status | location |", "|---|---|---|---|---|---|"]
    for item in result.get("findings") or []:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (item.get("finding_id"), item.get("aspect"),
                                                          item.get("category"), item.get("severity"),
                                                          item.get("status"), item.get("location")))
    lines += ["", "| aspect | status | findings | note |", "|---|---|---|---|"]
    for row in result.get("aspect_coverage") or []:
        lines.append("| %s | %s | %d | %s |" % (row.get("label"), row.get("status"), row.get("findings"), row.get("note")))
    lines += ["", "## 9. Screening and flow", "",
              "| source | decision | reason | duplicate_of | locator |", "|---|---|---|---|---|"]
    for row in scope.get("screening_log") or []:
        lines.append("| %s | %s | %s | %s | %s |" % (row.get("source_id"), row.get("decision"),
                                                    row.get("reason_code"), row.get("duplicate_of") or "",
                                                    row.get("locator")))
    flow = scope.get("flow") or {}
    lines += ["", "- Flow: identified=%s, duplicates=%s, unique=%s, screened=%s, excluded=%s, included=%s (closure=%s)"
              % (flow.get("identified"), flow.get("duplicates"), flow.get("unique"), flow.get("screened"),
                 flow.get("excluded"), flow.get("included"), flow.get("arithmetic_closure")), ""]

    with open(target / "report.md", "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    register("report.md")

    with open(target / "evidence.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["evidence_id", "kind", "source_id", "locator", "case_locator", "source_file",
                         "decision", "reason_code", "criteria_ids", "year", "overlap", "overlap_class",
                         "quote_verified", "quote"])
        for row in payload.get("evidence") or []:
            writer.writerow([row.get("evidence_id"), row.get("kind"), row.get("source_id"), row.get("locator"),
                             row.get("case_locator"), row.get("source_file") or "",
                             row.get("decision") or "", row.get("reason_code") or "",
                             ";".join(row.get("criteria_ids") or []),
                             row.get("year") if row.get("year") is not None else "",
                             row.get("overlap") if row.get("overlap") is not None else "",
                             row.get("overlap_class") or "", row.get("quote_verified"),
                             (row.get("quote") or "").replace("\n", " ")])
    register("evidence.csv")

    with open(target / "screening_log.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["source_id", "doi", "title", "stage", "decision", "reason_code", "criteria_ids",
                         "duplicate_of", "quote_verified", "quote", "locator", "case_locator", "source_file"])
        for row in scope.get("screening_log") or []:
            writer.writerow([row.get("source_id"), row.get("doi") or "", row.get("title") or "",
                             row.get("stage"), row.get("decision"), row.get("reason_code"),
                             ";".join(row.get("criteria_ids") or []), row.get("duplicate_of") or "",
                             row.get("quote_verified"), (row.get("quote") or "").replace("\n", " "),
                             row.get("locator"), row.get("case_locator"), row.get("source_file") or ""])
    register("screening_log.csv")

    provenance = {
        "schema_version": "provenance/v1",
        "case_id": payload.get("case_id") or "unknown",
        "note": "Every evidence row resolves through its locator: S1#P2 is paragraph 2 of the first parsed source file, /prior_art/0 is a JSON pointer into case.json.",
        "source_files": scope.get("source_files") or [],
        "flow": flow,
        "evidence": [{"evidence_id": row.get("evidence_id"), "source_id": row.get("source_id"),
                      "locator": row.get("locator"), "case_locator": row.get("case_locator"),
                      "source_file": row.get("source_file"), "quote_verified": row.get("quote_verified")}
                     for row in payload.get("evidence") or []],
        "findings": [{"finding_id": item.get("finding_id"), "aspect": item.get("aspect"),
                      "severity": item.get("severity"), "status": item.get("status"),
                      "location": item.get("location"), "evidence": item.get("evidence") or []}
                     for item in result.get("findings") or []],
        "aspect_coverage": result.get("aspect_coverage") or [],
        "artifacts": ["result.json", "report.md", "evidence.csv", "screening_log.csv", "provenance.json"],
    }
    try:
        with open(target / "provenance.json", "w", encoding="utf-8", newline="\n") as handle:
            json.dump(provenance, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except (OSError, ValueError):
        pass
    register("provenance.json")
    return written


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
    try:
        payload["artifacts"] = write_artifacts(Path(out_path).parent, payload)
        if payload["artifacts"]:
            write_result(out_path, payload, work_dir)
    except BaseException as exc:
        payload["artifacts"] = []
        payload["artifact_error"] = "%s: %s" % (type(exc).__name__, str(exc)[:200])
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
