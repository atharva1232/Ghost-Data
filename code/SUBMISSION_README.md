# GhostTrace — HackerRank Orchestrate, October 2026

GhostTrace is a local multimodal deletion-audit application and a terminal-runnable submission solver. It reads only the participant-facing dataset and writes the official `case_id,deletion_status,steps_json` output format. It resolves current and historical identifiers, interprets snapshots and readback traces at the audit cutoff, checks policy, and emits findings, ordered remediation, and verification.

## Setup

Python 3.11+ is required.

```powershell
python -m pip install -r code/requirements.txt
```

PDF text uses pypdf. Screenshot text uses Windows' local English OCR engine on Windows, or Tesseract (`tesseract` with English language data on PATH) on Linux/macOS. No cloud key is needed for prediction. Ensure the Windows English OCR language is installed. If the environment blocks PowerShell scripts, run from an authorized local development shell; the program does not change execution policies.

Unzip code.zip so `code/`, `evaluation/`, and this README are at the repository root. Put the unmodified organizer `dataset/` beside `code/`. Do not replace it with the older requests-only file.

## Produce the submission

From the repository root:

```powershell
python code/main.py predict
python code/main.py validate
```

This writes the final `output.csv` at the root. The validator checks exact headers, request coverage, sort order, step fields, numbering, allowed operations and states, canonical phase/operation/system/resource ordering, evidence existence and cutoff, and evidence-free future actions. Validation establishes output contract compliance, not hidden-answer correctness.

Custom paths are supported:

```powershell
python code/main.py predict --dataset path/to/dataset --output output.csv --artifacts artifacts/run
```

Only prediction reads the evaluation request file. `sample_output.csv` is never opened by the predictor; it is opened only by the separate evaluator.

## Evaluate

```powershell
python code/main.py evaluate
cd code
python -m unittest discover -s tests -v
```

Public-sample predictions and strict aligned metrics are written under `artifacts/official/`. The packaged reports are under `evaluation/`. They document measured status, step, field, and full-sequence accuracy, independent custom cases, weaknesses, and runtime usage. Hidden-case accuracy is unavailable. Public samples influenced debugging, so their score is not an unbiased held-out estimate.

## Dashboard

```powershell
python code/start_app.py --open
```

Open http://127.0.0.1:8765. The dashboard includes the fictional demo and the official organizer dataset, request search, evidence views, run history, evaluation, internal audit downloads, and a distinct **Submission output.csv** download for official runs. The download is disabled for synthetic runs.

The Add evidence dialog supports the original normalized demo evidence contract; the full official multimodal corpus is loaded from the local `dataset/` folder. It is not imported through that dialog. Runs, input hashes, uploads, and extraction caches stay under `artifacts/` and are not submitted.

Optional AI advisory review requires OPENAI_API_KEY and an explicit model ID. It is separate from the final submission run, is not necessary to generate predictions, and does not override evidence verdicts. No live cloud model was used for the packaged output. The final run's model/token/cost accounting is in `evaluation/usage_report.md`.

## Investigation design

1. Read identity snapshots and identifier-change logs. Match normalized exact email/subject/hash relationships, including historical addresses; avoid matching on similar names alone.
2. Parse JSON business snapshots, service exports, text handovers, structured/unstructured logs, and in-memory SQLite snapshots, including replicas.
3. Extract PDFs and OCR screenshots locally; keep source file IDs and content hashes. Interpret the main business object rather than assuming all unrelated rows in a screenshot belong to the subject.
4. Match evidence by contents and grounded resource links. Operational activity provides resource attribution/context but reported operation success is not used as proof of absence.
5. Select usable observations at/before audit time. Later-captured files cannot establish an earlier verdict. Current-state checks use post-request observations; full inventory scopes support bounded absence checks.
6. Read policy actions from deletion_rules.csv. Preserve stable references on redacted account tombstones, redact shared support records, anonymize attributable analytics, and retain required security records.
7. Emit exact official operations. Disable flows and block restore before record actions. Sort all phases and operations as specified, followed by system and resource. Findings and COMPLETE verification cite participant IDs; future work cites an empty string.

## Important limitations

This is a submission candidate, not a production privacy compliance system. The public status score is stronger than detailed step/sequence matching; see measured results in the evaluation report. Temporal workflow-target association is heuristic when direct ownership is absent. Legacy resource attribution, anonymous records, OCR errors, and screenshot detail selection can cause missing or extra steps. Some source scopes do not explicitly enumerate every absent resource. Retention constraints requiring per-record recovery and arbitrary re-identification resistance are not fully modeled. The tool does not execute deletion, connect to production services, or prove that the provided corpus covers every real-world system.

No organizer-only truth, generator internals, hidden answers, or case-number patterns are used. The solution makes no claim of 100% hidden-answer accuracy.

## Upload artifacts

- `code.zip`: source, requirements, dashboard, tests, README, and both evaluation reports; no dataset, caches, virtual environments, secrets, or nested archives.
- `output.csv`: 518 rows generated from the official evaluation requests.
- `log.txt`: agent log and a labeled retrospective recovery of earlier user-facing development turns. Earlier prototype turns were not logged contemporaneously; the recovery preserves authentic conversation text rather than fabricating history.

Submit at https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists .
