"""Conservative audits over a documented normalized evidence contract.

No supplied case IDs, reported status, or evaluation labels influence verdicts.
REVIEW_REQUIRED is an internal abstention, not a competition status.
"""

import re
import unicodedata
from pathlib import Path

from .io import InputError, boolean, json_value, read_csv, timestamp, unique


REQUEST_COLUMNS = ("case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text")
TABLES = {
    "identifiers": ("subject_id", "identifier_type", "identifier_value", "verified", "observed_at"),
    "deletion_rules": ("system", "category", "action", "allowed_fields", "required_retain"),
    "records": ("record_id", "system", "category", "subject_id", "identifiers", "fields", "state", "observed_at"),
    "processes": ("process_id", "source_system", "target_system", "subject_id", "active", "can_recreate", "blocked", "observed_at"),
    "coverage": ("case_id", "system", "category", "records_complete", "processes_complete", "identities_complete", "observed_at"),
}


def norm(kind, value):
    value = unicodedata.normalize("NFKC", str(value)).strip()
    # No provider-specific alias rewriting. Other identifier types remain case-sensitive.
    return value.casefold() if kind == "email" else value


def intent(text):
    """A small transparent baseline. Unsupported language/ambiguity abstains."""
    text = unicodedata.normalize("NFKC", text).casefold().replace("’", "'")
    negatives = (r"not a request to (?:erase|delete)", r"don'?t (?:delete|erase)",
                 r"do not (?:delete|erase)", r"leave .{0,65}(?:in place|unchanged)",
                 r"want to continue using", r"still use (?:it|the service)")
    negative = any(re.search(p, text) for p in negatives)
    # Remove common polite framing; don't interpret 'could you delete' as ambiguity.
    positive = bool(re.search(r"\b(?:delete|erase|erased|deletion)\b", text))
    if negative:
        # An explicit correction that requests deletion after a negative is ambiguous.
        cleaned = text
        for pattern in negatives:
            cleaned = re.sub(pattern, "", cleaned)
        if re.search(r"\b(?:delete|erase|erased|deletion)\b", cleaned):
            return "UNKNOWN"
        return "NON_DELETION"
    if positive and re.search(r"\b(?:please|want|would like|request|process|begin|delete|erase)\b", text):
        return "DELETION"
    return "UNKNOWN"


class Corpus:
    def __init__(self, root):
        self.root = Path(root)
        self.requests = read_csv(self.root / "deletion_requests.csv", REQUEST_COLUMNS)
        unique(self.requests, "case_id")
        for row in self.requests:
            if not row["email"].strip() or not row["request_text"].strip():
                raise InputError(f"{row['_ref']}: email and request_text must be nonempty")
            for key in ("requested_at", "reported_at", "audit_at"):
                timestamp(row[key])
            if timestamp(row["audit_at"]) < timestamp(row["requested_at"]):
                raise InputError(f"{row['_ref']}: audit precedes request")
        self.tables = {name: read_csv(self.root / f"{name}.csv", columns, optional=True)
                       for name, columns in TABLES.items()}
        self.media_gaps = []
        # Read local text; other media must have an extracted UTF-8 sidecar.
        # All raw media remain a review gap until explicitly reviewed in coverage metadata.
        self.media = []
        media_root = self.root / "media"
        if media_root.exists():
            for path in sorted(media_root.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() in (".txt", ".md"):
                    try:
                        self.media.append({"source": path.relative_to(self.root).as_posix(),
                                           "text": path.read_text(encoding="utf-8-sig")})
                    except UnicodeError:
                        self.media_gaps.append(f"Unreadable text media: {path.name}")
                elif not Path(str(path) + ".txt").exists():
                    self.media_gaps.append(f"Media extraction missing: {path.name}")
        self._validate()

    def _validate(self):
        for name, rows in self.tables.items():
            for row in rows:
                if "observed_at" in row:
                    timestamp(row["observed_at"])
                for field in ("verified", "required_retain", "active", "can_recreate", "blocked",
                              "records_complete", "processes_complete", "identities_complete"):
                    if field in row:
                        row[field] = boolean(row[field])
                for field, kind in (("allowed_fields", list), ("identifiers", dict), ("fields", dict)):
                    if field in row:
                        row[field] = json_value(row[field], kind)
                if "identifiers" in row:
                    if any(not isinstance(v, list) or any(not isinstance(x, str) for x in v)
                           for v in row["identifiers"].values()):
                        raise InputError(f"{row['_ref']}: identifiers must map types to string arrays")
                if "allowed_fields" in row and any(not isinstance(v, str) for v in row["allowed_fields"]):
                    raise InputError(f"{row['_ref']}: allowed_fields must contain strings")
                if name == "deletion_rules":
                    if row["action"] not in ("DELETE", "REDACT", "ANONYMIZE", "RETAIN"):
                        raise InputError(f"{row['_ref']}: unsupported rule action")
                    if row["required_retain"] and row["action"] == "DELETE":
                        raise InputError(f"{row['_ref']}: DELETE conflicts with required retention")
                if name == "records" and row["state"] not in ("present", "deleted"):
                    raise InputError(f"{row['_ref']}: state must be present or deleted")
        rule_keys = [(x["system"], x["category"]) for x in self.tables["deletion_rules"]]
        if len(rule_keys) != len(set(rule_keys)):
            raise InputError("Conflicting or duplicate policy scopes")
        # Multiple timestamped observations are allowed, contradictory ties are not.
        for table, fields in (("records", ("system", "record_id")), ("processes", ("process_id",)),
                              ("coverage", ("case_id", "system", "category"))):
            seen = set()
            for row in self.tables[table]:
                key = tuple(row[f] for f in fields) + (timestamp(row["observed_at"]),)
                if key in seen:
                    raise InputError(f"{row['_ref']}: duplicate observation at same timestamp")
                seen.add(key)


def latest(rows, fields, at):
    selected = {}
    for row in rows:
        if timestamp(row["observed_at"]) > at:
            continue
        key = tuple(row[f] for f in fields)
        if key not in selected or timestamp(row["observed_at"]) > timestamp(selected[key]["observed_at"]):
            selected[key] = row
    return [selected[k] for k in sorted(selected)]


def audit(corpus, request):
    at = timestamp(request["audit_at"])
    threshold = timestamp(request["requested_at"])
    result = {"case_id": request["case_id"], "status": "REVIEW_REQUIRED", "intent": intent(request["request_text"]),
              "reported_status": request["reported_status"], "identifiers": [], "findings": [],
              "recreation_paths": [], "retained_records": [], "remediation": [], "proof": [],
              "gaps": [], "timeline": [], "request_source": request["_ref"]}
    if result["intent"] == "NON_DELETION":
        result["status"] = "NOT_APPLICABLE"
        result["proof"].append({"description": "Request text explicitly asks to preserve the account or excludes erasure.",
                                "source": request["_ref"]})
        return result
    if result["intent"] == "UNKNOWN":
        result["gaps"].append("Request intent is unsupported or ambiguous; requires language-aware review.")
        return result
    tables = corpus.tables
    rules = {(x["system"], x["category"]): x for x in tables["deletion_rules"]}
    if not rules:
        result["gaps"].append("Missing deletion_rules.csv: treatment and retention obligations are unknown.")
    known = {("email", norm("email", request["email"]))}
    subjects = set()
    links = [r for r in tables["identifiers"] if r["verified"] and timestamp(r["observed_at"]) <= at]
    # Expand only explicit verified links. If an identifier points at multiple people, abstain.
    changed = True
    ambiguous = False
    while changed:
        changed = False
        for row in sorted(links, key=lambda r: (r["subject_id"], r["identifier_type"], r["identifier_value"])):
            key = (row["identifier_type"], norm(row["identifier_type"], row["identifier_value"]))
            if key in known or row["subject_id"] in subjects:
                if len({x["subject_id"] for x in links if
                        (x["identifier_type"], norm(x["identifier_type"], x["identifier_value"])) == key}) > 1:
                    ambiguous = True
                    continue
                if row["subject_id"] not in subjects or key not in known:
                    subjects.add(row["subject_id"])
                    known.add(key)
                    changed = True
    if ambiguous or len(subjects) > 1:
        result["gaps"].append("Identity has conflicting subject links; refusing to merge people.")
        return result
    result["identifiers"] = [{"type": k, "value": v} for k, v in sorted(known)]
    result["proof"].extend({"description": "Verified identity relationship", "source": r["_ref"]}
                           for r in links if r["subject_id"] in subjects)

    def matches(row):
        return row["subject_id"] in subjects or any(
            (kind, norm(kind, value)) in known for kind, values in row.get("identifiers", {}).items() for value in values)

    records = [r for r in latest(tables["records"], ("system", "record_id"), at) if matches(r)]
    processes = [p for p in latest(tables["processes"], ("process_id",), at)
                 if p["subject_id"] in subjects or p["subject_id"] == "*"]
    cover = {(r["system"], r["category"]): r for r in latest(
        [r for r in tables["coverage"] if r["case_id"] == request["case_id"]], ("system", "category"), at)}
    result["gaps"].extend(corpus.media_gaps)
    if corpus.media:
        result["gaps"].append("Local text/media evidence needs reviewed normalization into records and identity links.")
    if not subjects:
        result["gaps"].append("No verified subject identity mapping is available.")
    for scope, rule in sorted(rules.items()):
        coverage = cover.get(scope)
        if (not coverage or timestamp(coverage["observed_at"]) != at
                or not all(coverage[k] for k in ("records_complete", "processes_complete", "identities_complete"))):
            result["gaps"].append(f"Incomplete or stale search coverage for {scope[0]}/{scope[1]}.")
        else:
            result["proof"].append({"description": f"Complete evidence search: {scope[0]}/{scope[1]}",
                                    "source": coverage["_ref"]})
        scoped = [r for r in records if (r["system"], r["category"]) == scope]
        if rule["required_retain"]:
            present = [r for r in scoped if r["state"] == "present"]
            if not present:
                if subjects and coverage and coverage["records_complete"] and timestamp(coverage["observed_at"]) == at:
                    result["findings"].append({"type": "MISSING_REQUIRED_RETENTION", "system": scope[0],
                        "category": scope[1], "source": coverage["_ref"], "policy": rule["_ref"],
                        "description": "Required retained record is unavailable.",
                        "action": "Recover the required record through an isolated, policy-filtered recovery; preserve only allowed fields."})
            result["retained_records"].extend(r["record_id"] for r in present)
    for row in records:
        result["timeline"].append({"at": row["observed_at"], "description": f"{row['system']}: {row['record_id']} is {row['state']}", "source": row["_ref"]})
        if timestamp(row["observed_at"]) < threshold:
            result["gaps"].append(f"Record observation predates request: {row['system']}/{row['record_id']}.")
            continue
        rule = rules.get((row["system"], row["category"]))
        if rule is None:
            result["gaps"].append(f"No policy for {row['system']}/{row['category']}.")
            continue
        if row["state"] == "deleted":
            result["proof"].append({"description": f"Deletion observed: {row['record_id']}", "source": row["_ref"]})
            continue
        forbidden = sorted(set(row["fields"]) - set(rule["allowed_fields"]))
        exposed_identifiers = bool(row["identifiers"]) and rule["action"] == "ANONYMIZE"
        if rule["action"] == "DELETE" or forbidden or exposed_identifiers:
            result["findings"].append({"type": "RESIDUAL_DATA", "record_id": row["record_id"],
                "system": row["system"], "category": row["category"], "source": row["_ref"],
                "policy": rule["_ref"], "forbidden_fields": forbidden,
                "description": f"Record fails {rule['action']} policy.",
                "action": f"{rule['action']} {row['system']}/{row['record_id']} according to {rule['_ref']}; preserve required allowed fields."})
        else:
            result["proof"].append({"description": f"Allowed fields verified: {row['record_id']}", "source": row["_ref"]})
    for row in processes:
        if timestamp(row["observed_at"]) < threshold:
            result["gaps"].append(f"Process observation predates request: {row['process_id']}.")
            continue
        result["timeline"].append({"at": row["observed_at"], "description": f"Process observed: {row['process_id']}", "source": row["_ref"]})
        if row["active"] and row["can_recreate"] and not row["blocked"]:
            result["recreation_paths"].append({"process_id": row["process_id"], "from": row["source_system"],
                "to": row["target_system"], "source": row["_ref"],
                "action": f"Block recreation by {row['process_id']} ({row['source_system']} -> {row['target_system']}) and verify suppression."})
        else:
            result["proof"].append({"description": f"No active unblocked recreation: {row['process_id']}", "source": row["_ref"]})
    result["timeline"].sort(key=lambda r: (timestamp(r["at"]), r["source"]))
    # Safety order: block every identified writer, then treat copies, then verify.
    for path in result["recreation_paths"]:
        result["remediation"].append({"step": len(result["remediation"]) + 1, "action": path["action"], "source": path["source"]})
    for finding in sorted(result["findings"], key=lambda f: (f["system"], f.get("record_id", ""), f["source"])):
        result["remediation"].append({"step": len(result["remediation"]) + 1, "action": finding["action"], "source": finding["source"]})
    if result["remediation"]:
        result["remediation"].append({"step": len(result["remediation"]) + 1,
                                     "action": "Refresh identity, record, retention, sync/import/restore evidence and rerun the audit.",
                                     "source": request["_ref"]})
    result["gaps"] = sorted(set(result["gaps"]))
    if result["findings"] or result["recreation_paths"]:
        result["status"] = "INCOMPLETE"
    elif not result["gaps"]:
        result["status"] = "COMPLETE"
    return result


def audit_all(corpus):
    return [audit(corpus, request) for request in corpus.requests]
