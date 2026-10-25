# GhostTrace submission demo

1. Launch START_GHOSTTRACE.cmd and select October hackathon requests.
2. Run the official audit. Explain that the solver reads the full participant corpus, follows historical identity links, and uses actual post-request/as-of evidence rather than reported workflow success.
3. Inspect an INCOMPLETE request: source-cited findings, active copy/restore risks, ordered remediation, and future verification. The app does not execute deletion.
4. Inspect a COMPLETE request: evidence-backed verification steps. Account tombstones may keep permitted stable references; direct identifiers must be removed.
5. Download Submission output.csv. Explain the exact three-column schema and canonical step sorting.
6. Run Evaluation. It uses 32 public samples, not hidden answers. Report status, step, field, and sequence scores separately; do not describe status accuracy as overall accuracy.
7. Switch to the explicitly synthetic demo to demonstrate a recreated profile, retained invoice PII, and missing required retention.

Submission package: code.zip, output.csv, and log.txt. Reports are inside evaluation/ in code.zip. The inference run uses local OCR and deterministic rules, with no cloud language-model calls or billed text tokens. Optional cloud AI review is a separate feature.

Known weaknesses include temporal resource attribution, some missing/extra verification steps, record category inference, OCR ambiguity, and source selection. Detailed measured results are in code/evaluation/evaluation_report.md. No hidden-case accuracy is claimed.
