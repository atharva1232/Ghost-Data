# GhostTrace code package

Requires Python 3.11+. No third-party runtime dependencies.

From this directory:

```powershell
python make_demo.py
python -m ghosttrace audit --data examples/demo --out ../artifacts/demo
python -m unittest discover -s tests -v
python -m ghosttrace evaluate --audit ../artifacts/demo/audit.json --expected examples/demo/expected.csv --out ../artifacts/evaluation.json
```

For organizer data, use `--data ../dataset`. Input and output directories must be separate. Open the generated `report.html` in a browser.

Only `deletion_requests.csv` was supplied. System evidence, identity mappings, policy rules, local media, official output schema, and organizer reference labels remain missing. The engine abstains with internal REVIEW_REQUIRED when evidence cannot establish a competition verdict. This provisional audit CSV is not the official output.csv.

See `EVIDENCE_CONTRACT.md` for the normalized evidence format and current limitations. Synthetic demo expectations test known scenarios; they do not establish accuracy on organizer data.

Optional AI explanation: set OPENAI_API_KEY locally and pass `--ai-review --model <explicit-model-id> --ai-limit 3`. This sends minimized audit findings to OpenAI, never changes verdicts, and has not been live-tested. No key is needed for offline audit, tests, evaluation, or reports.

Export requires all cases to be resolved plus an official column mapping: `python -m ghosttrace export --audit ../artifacts/organizer/audit.json --schema official_schema.json --out ../output.csv`. Extend serialization if the organizer schema needs it. Demo exports and unresolved cases are rejected.

Run `python package_submission.py` to regenerate a code-only ZIP. Example CSVs are excluded; `make_demo.py` regenerates them. The organizer requires predictions and an authentic chat log separately.
