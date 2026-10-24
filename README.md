# GhostTrace

**An evidence-backed agent for the “Ghost Data Still Exists” hackathon.**

GhostTrace investigates deletion requests, links historical identifiers, checks policy treatments and retention, flags sync/import/restore risks, and generates ordered remediation with source references. It produces a portable, searchable HTML audit workspace and machine-readable reports.

## Current state — read this first

The supplied organizer file has **518 requests** with these columns:

`case_id,email,requested_at,reported_status,reported_at,audit_at,request_text`

It does **not** contain the system records, historical identity links, deletion rules, local media, reference labels, or the exact output schema from `problem_statement.md`. Reported statuses describe what a dashboard claims; they are not ground truth. The attached screenshots explicitly warn that a reported COMPLETE can conceal residual data.

The project therefore includes a working, tested **prototype and evidence contract**, not a claim to have solved the hidden cases. With the supplied file alone, most requests receive the internal abstention `REVIEW_REQUIRED`. This is intentionally **not** a fourth competition label. Unsupported languages and ambiguous request intent also abstain. The current English rule baseline identifies a few explicit non-deletion requests; these still need organizer validation.

The synthetic demo exercises real code paths but cannot measure performance on the organizer dataset. Exact competition export requires the missing specification and evidence. Do not submit `audit.csv` as the official predictions file.

## Run now

Requires Python 3.11 or later. Offline operation needs no packages, credentials, or installation.

From the repository root:

```powershell
cd code
python make_demo.py
python -m ghosttrace audit --data examples/demo --out ../artifacts/demo
Start-Process ../artifacts/demo/report.html
```

The demo is explicitly marked **SYNTHETIC**. It shows five cases: data recreated under an old email, a verified clean deletion, an information-only request, an invoice exposing a forbidden email, and a missing required invoice. Example policies are illustrative, not organizer rules or legal advice.

Run the supplied requests:

```powershell
python -m ghosttrace audit --data ../dataset --out ../artifacts/organizer
Start-Process ../artifacts/organizer/report.html
```

Each run produces:

| File | Purpose |
| --- | --- |
| `report.html` | Search/filter cases and inspect evidence, risks, remediation, and proof |
| `audit.json` | Full case results, observations, provenance, and input SHA-256 hashes |
| `audit.csv` | Provisional internal audit schema, **not** the official competition export |
| `summary.json` | Counts, version, input manifest, and readiness limitations |

## How the audit works

1. Validate CSV structure, timestamps, JSON cells, boolean values, duplicate IDs, and conflicting policy scopes.
2. Classify explicit English deletion/non-deletion intent conservatively; abstain on unsupported intent.
3. Expand current and historical identifiers through verified subject relationships. Shared or conflicting identifiers cause review rather than merging people.
4. Select the latest evidence observations at or before the case's audit time. Future cleanup cannot hide a residual record at audit time.
5. Apply per-system/category policy rules. Check forbidden retained fields and availability of required retained record categories.
6. Flag active, unblocked subject-specific or global processes explicitly marked as capable of recreating personal data.
7. Require complete identity, record, and process search coverage **at the audit timestamp**, across every policy scope, before asserting COMPLETE.
8. Block identified recreation paths before treating copies; finish with fresh verification. The tool proposes actions and never performs actual deletion.

Known violations produce INCOMPLETE even if other evidence is missing. COMPLETE requires no detected violations and no coverage gaps. NOT_APPLICABLE derives from explicit request intent. Every remaining uncertain case receives REVIEW_REQUIRED internally.

## Evidence format

See [code/EVIDENCE_CONTRACT.md](code/EVIDENCE_CONTRACT.md). This is our normalized adapter contract, **not a claim about the organizer's missing file schemas**. Once original evidence is available, write source-specific adapters that preserve original provenance and map onto this contract. Never manufacture “complete coverage” rows from the absence of records.

Local UTF-8 text/Markdown is read. Other media is inventoried and requires extraction into a `.txt` sidecar; raw/unreviewed media blocks completion. Automated OCR, PDF/video/audio extraction and semantic normalization are not yet implemented. The optional AI reviewer currently explains existing audit evidence; it does not extract media or resolve multilingual intent.

## Optional AI review

This feature sends minimized audit findings to the OpenAI API for a structured advisory review. It does not alter verdicts. It excludes resolved identifier lists and raw record contents, but record IDs, source references, and finding text can still appear in the payload. Enable it only for data you intend to send to that provider.

Set `OPENAI_API_KEY` locally and choose an available model supporting Structured Outputs:

```powershell
$env:OPENAI_API_KEY = '<your local API key>'
python -m ghosttrace audit --data examples/demo --out ../artifacts/ai-demo --ai-review --model '<your-model-id>' --ai-limit 3
```

Do not commit credentials. The implementation uses the Responses API, structured JSON output, `store: false`, a bounded number of reviews, exact source-reference validation, and a versioned review prompt. Model prose is advisory and can still be wrong. Network failure or refusal is reported explicitly. This integration has local mocked tests; a live provider run requires credentials and has not been performed.

API reference: [official OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

## Tests and evaluation

From `code/`:

```powershell
python -m unittest discover -s tests -v
python -m ghosttrace evaluate --audit ../artifacts/demo/audit.json --expected examples/demo/expected.csv --out ../artifacts/demo/evaluation.json
```

The evaluation command reads labels separately from prediction, reports status accuracy including abstentions, prediction coverage, a confusion matrix, mismatches, and false COMPLETE counts. Organizer labels, if provided, must be in a separate CSV with `case_id,status` for this evaluator. Extra organizer fields need an adapter and field-level scoring. There are no organizer reference labels in the current repository.

Regression tests cover historical aliases, resurrection, retained PII, missing required retention, future observations, stale evidence, ambiguous identities, global restore paths, malformed inputs, media gaps, HTML escaping, and export guards.

## Competition export and packaging

When all real cases are resolved and the exact official schema is available, create a JSON object mapping each official CSV column to an internal audit field, then run:

```powershell
python -m ghosttrace export --audit ../artifacts/organizer/audit.json --schema official_schema.json --out ../output.csv
python package_submission.py
```

The export refuses synthetic demo results and unresolved requests. Mapping supports renaming and selecting columns; if the official specification needs different nested serialization or derived fields, extend the adapter first. The tool cannot validate a specification it has not received.

Packaging creates `dist/code.zip` with the `code/` directory, excluding datasets, outputs, example CSV corpora, environments, caches, and credentials. The demo generator is included, so examples can be regenerated. Upload the official `output.csv` and organizer-required chat transcript `log.txt` separately. Transcript logging location remains unknown until the organizer supplies that instruction; this app cannot invent an authentic chat log.

## Repository layout

```text
dataset/deletion_requests.csv   Supplied organizer requests, unchanged
code/ghosttrace/                Audit engine, CLI, optional AI review, HTML report
code/tests/                    Synthetic regression tests
code/examples/demo/             Explicitly synthetic evidence
code/make_demo.py               Reproducible synthetic demo generator
code/package_submission.py      Code-only ZIP builder
artifacts/                     Generated local results (ignored by Git)
```

## Remaining hackathon work

- Obtain `problem_statement.md`, `deletion_rules.csv`, system records, and local media from the organizer.
- Implement adapters for those actual source schemas and preserve original row/media citations.
- Add language-aware request interpretation, evidence extraction, richer system dependency analysis, and field-level evaluation as the corpus requires.
- Replace the provisional CSV layout with the exact required output schema and rerun every request.
- Validate organizer examples, package the final submission, and rehearse the demo using clearly labeled data.
