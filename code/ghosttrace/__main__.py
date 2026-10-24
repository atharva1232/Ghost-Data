import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .io import InputError, write_csv, write_json
from .report import render_report
from .service import AUDIT_COLUMNS, evaluate_results, perform_audit


COMPETITION_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}


def run_audit(args):
    root, output = Path(args.data).resolve(), Path(args.out).resolve()
    if output == root or root in output.parents:
        raise InputError("Output directory must be outside the input dataset to preserve reproducible manifests")
    data = perform_audit(root, output)
    results, summary = data["results"], data["summary"]
    if args.ai_review:
        if not args.model:
            raise InputError("Set --model explicitly when enabling --ai-review")
        from .ai import review
        for result in results[:args.ai_limit]:
            result["ai_review"] = review(result, args.model)
    summary["ai_reviews"] = sum("ai_review" in r for r in results)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "audit.json", {"summary": summary, "results": results})
    write_csv(output / "audit.csv", results, AUDIT_COLUMNS)
    write_json(output / "summary.json", summary)
    render_report(output / "report.html", results, summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "inputs"}, indent=2))
    print(f"Report: {output / 'report.html'}")


def evaluate(args):
    predictions = json.loads(Path(args.audit).read_text(encoding="utf-8"))["results"]
    result = evaluate_results(predictions, args.expected)
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


def run_server(args):
    if not 1 <= args.port <= 65535:
        raise InputError("Port must be between 1 and 65535")
    from .server import serve
    serve(port=args.port, open_browser=args.open)


def main():
    parser = argparse.ArgumentParser(description="GhostTrace · evidence-backed deletion audits")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    web = commands.add_parser("serve", help="Start the local GhostTrace dashboard")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--open", action="store_true", help="Open the dashboard in your default browser")
    web.set_defaults(func=run_server)
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
