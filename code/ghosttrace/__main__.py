import argparse
import collections
import json
import sys
from pathlib import Path

from . import __version__
from .engine import Corpus, audit_all
from .io import InputError, manifest, read_csv, unique, write_csv, write_json
from .report import render_report


AUDIT_COLUMNS = ("case_id", "status", "intent", "reported_status", "identifiers", "findings", "recreation_paths", "remediation", "gaps", "proof")
COMPETITION_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}


def run_audit(args):
    root, output = Path(args.data).resolve(), Path(args.out).resolve()
    if output == root or root in output.parents:
        raise InputError("Output directory must be outside the input dataset to preserve reproducible manifests")
    corpus = Corpus(root)
    results = audit_all(corpus)
    if args.ai_review:
        if not args.model:
            raise InputError("Set --model explicitly when enabling --ai-review")
        from .ai import review
        for result in results[:args.ai_limit]:
            result["ai_review"] = review(result, args.model)
    summary = {"version": __version__, "demo": (root / "SYNTHETIC_DEMO").exists(),
               "requests": len(results), "counts": dict(collections.Counter(r["status"] for r in results)),
               "competition_ready": False,
               "schema_note": "Internal schema; exact competition specification has not been supplied.",
               "ai_reviews": sum("ai_review" in r for r in results), "inputs": manifest(root)}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "audit.json", {"summary": summary, "results": results})
    write_csv(output / "audit.csv", results, AUDIT_COLUMNS)
    write_json(output / "summary.json", summary)
    render_report(output / "report.html", results, summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "inputs"}, indent=2))
    print(f"Report: {output / 'report.html'}")


def evaluate(args):
    predictions = json.loads(Path(args.audit).read_text(encoding="utf-8"))["results"]
    expected = read_csv(args.expected, ("case_id", "status"))
    unique(expected, "case_id")
    truth = {r["case_id"]: r["status"] for r in expected}
    if any(x not in COMPETITION_STATUSES for x in truth.values()):
        raise InputError("Reference labels must use COMPLETE, INCOMPLETE, or NOT_APPLICABLE")
    if len({r["case_id"] for r in predictions}) != len(predictions):
        raise InputError("Duplicate predicted request IDs")
    by_id = {r["case_id"]: r for r in predictions}
    if set(truth) - set(by_id):
        raise InputError("Some labeled requests have no prediction")
    matrix = collections.Counter()
    abstain = false_complete = correct = 0
    failures = []
    for key, status in truth.items():
        predicted = by_id[key]["status"]
        matrix[(status, predicted)] += 1
        abstain += predicted == "REVIEW_REQUIRED"
        correct += status == predicted
        false_complete += predicted == "COMPLETE" and status != "COMPLETE"
        if status != predicted:
            failures.append({"case_id": key, "expected": status, "predicted": predicted})
    total = len(truth)
    result = {"labeled_cases": total, "accuracy_including_abstentions": correct / total if total else None,
              "abstentions": abstain, "false_complete": false_complete,
              "prediction_coverage": (total - abstain) / total if total else None,
              "confusion_matrix": [{"expected": a, "predicted": b, "count": n} for (a, b), n in sorted(matrix.items())],
              "failures": failures,
              "note": "Status metrics only; evidence and remediation need separate review or official field-level references."}
    write_json(args.out, result)
    print(json.dumps(result, indent=2))


def export(args):
    data = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    if data["summary"].get("demo"):
        raise InputError("Refusing competition export from synthetic demo data")
    results = data["results"]
    if any(r["status"] not in COMPETITION_STATUSES for r in results):
        raise InputError("Unresolved requests remain; REVIEW_REQUIRED cannot be silently mapped to a competition label")
    mapping = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    if not isinstance(mapping, dict) or not mapping or any(v not in AUDIT_COLUMNS for v in mapping.values()):
        raise InputError("Schema must map each official column name to an internal audit field")
    rows = [{target: r[source] for target, source in mapping.items()} for r in results]
    write_csv(args.out, rows, tuple(mapping))
    print(f"Wrote {len(rows)} rows using the supplied schema mapping. Check serialization against the official specification.")


def main():
    parser = argparse.ArgumentParser(description="GhostTrace · evidence-backed deletion audits")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("audit", help="Audit local CSV evidence and create an interactive report")
    run.add_argument("--data", required=True)
    run.add_argument("--out", default="artifacts/audit")
    run.add_argument("--ai-review", action="store_true", help="Send minimized findings to OpenAI for advisory review")
    run.add_argument("--model", help="Explicit structured-output-capable OpenAI model ID")
    run.add_argument("--ai-limit", type=int, default=3, help="Maximum AI-reviewed cases (default: 3)")
    run.set_defaults(func=run_audit)
    ev = commands.add_parser("evaluate", help="Evaluate predictions separately from inference")
    ev.add_argument("--audit", required=True)
    ev.add_argument("--expected", required=True)
    ev.add_argument("--out", default="artifacts/evaluation.json")
    ev.set_defaults(func=evaluate)
    ex = commands.add_parser("export", help="Export resolved real cases using a user-supplied official column mapping")
    ex.add_argument("--audit", required=True)
    ex.add_argument("--schema", required=True)
    ex.add_argument("--out", default="output.csv")
    ex.set_defaults(func=export)
    args = parser.parse_args()
    try:
        if getattr(args, "ai_limit", 0) < 0:
            raise InputError("--ai-limit must be nonnegative")
        args.func(args)
    except (InputError, OSError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
