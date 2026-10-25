"""Reproduce Markdown evaluation and usage reports from a recorded run."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, default=root / 'artifacts' / 'official')
    parser.add_argument('--tests', type=int, default=0, help='Previously verified regression test count; this utility does not rerun tests')
    args = parser.parse_args()
    score = json.loads((args.run_dir / 'sample_metrics.json').read_text(encoding='utf-8'))
    run = json.loads((args.run_dir / 'run_validation.json').read_text(encoding='utf-8'))
    output = root / 'code' / 'evaluation'
    output.mkdir(parents=True, exist_ok=True)
    percentages = {k: f'{score[k]*100:.2f}%' for k in ('status_accuracy','step_accuracy','field_accuracy','sequence_accuracy')}
    failures = ', '.join(r['case_id'] for r in score['failures'])
    report = f'''# GhostTrace evaluation report

## Measured public-sample results

Evaluation used the 32 participant-facing sample requests and their public reference output. Reference labels are read only by the evaluator, never the predictor. These samples were used during debugging, so the scores are development-set results, not unbiased held-out estimates. Hidden-case accuracy is unknown.

| Metric | Result |
| --- | --- |
| Case-level deletion-status accuracy | {percentages['status_accuracy']} |
| Exact aligned step accuracy | {percentages['step_accuracy']} |
| Aligned field accuracy | {percentages['field_accuracy']} |
| Exact full-sequence accuracy | {percentages['sequence_accuracy']} |

Status accuracy is matching verdicts divided by labeled requests. Steps are compared at their array positions; the denominator is the sum of the larger predicted/reference step counts per case, so missing and extra steps are penalized. Field accuracy compares all seven required fields at those aligned positions. Sequence accuracy requires the entire ordered array to equal the reference; object-key order and JSON whitespace are ignored. Empty matching arrays are valid for non-deletion requests. This is our documented evaluation protocol, not a claim to reproduce the hidden grader.

## Additional participant-created evaluation cases

These independent synthetic cases are executable in tests/test_official.py. They do not use organizer case IDs or hidden labels.

| Custom case | Input evidence | Expected behavior | Result |
| --- | --- | --- | --- |
| Stable tombstone | Post-request tombstone has only an allowed stable subject reference and is redacted | COMPLETE; VERIFY_RECORD_REDACTED; never DELETE_RECORD | Pass |
| Exposed tombstone | Tombstone still exposes direct PII | INCOMPLETE; report PII, redact while preserving reference, verify redaction; future steps have empty evidence IDs | Pass |
| Active restore plus profile | Present profile and active backup restoration path | INCOMPLETE; BLOCK_RESTORE precedes DELETE_RECORD, with both verification checks | Pass |
| Future cleanup | Present profile before audit; deletion observation after audit | INCOMPLETE; future evidence cannot hide the present profile | Pass |

Other regression cases cover historical aliases, decoy identities, multilingual authorization, SQL integer booleans, cloud/app/syslog/pipe log envelopes, retained PII, replica resurrection, malformed uploads, evidence time limits, output sorting, source citation validation, and separated reference evaluation. The last recorded suite passed {args.tests} tests. Report generation does not itself rerun tests.

## Failures found and improvements made

- Initial public-sample status accuracy was 62.5%. The first request classifier missed confirmation-of-deletion and several removal formulations. Explicit authorization patterns were expanded without case-number rules.
- Unicode accent folding decomposed Hangul into Jamo and broke Korean deletion recognition. NFC recomposition fixed that issue; a Korean regression case now protects it.
- SQL boolean fields use 1/0 as well as true/false. Incorrect inactive interpretations were fixed and tested.
- Some evidence wraps events in cloud message strings, bracketed application records, pipe streams, or syslog headers. Added transport normalization and trace-key propagation so those evidence records are not silently skipped.
- Source attribution initially treated unrelated sidebar links as the main screenshot object. Main-object selection and conflicting-identity checks reduce those false associations.
- Added replica-aware inventory absence handling, future-capture exclusion, official sorting and citation validation, and a rule forbidding empty COMPLETE verification arrays.

## Remaining errors and limitations

Detailed step arrays differ on {len(score['failures'])} of {score['cases']} public samples: {failures}.

Status agreement does not imply a complete or correct remediation plan. Remaining discrepancies include absent or anonymized resources that cannot be confidently linked from the readback contents, temporal workflow-target association ambiguity, stale legacy resource links, support-record category classification, extra inferred resources, and evidence-selection differences. Workflow timing is heuristic and can join unrelated activity. Some inventories do not explicitly enumerate every absent resource. OCR text can contain character confusions or column-order errors. The system does not prove arbitrary anonymization strength or model every possible retention recovery action.

No hidden-answer score is claimed. Do not describe this as 100% overall accuracy or guaranteed correct deletion certification.

## Full evaluation-request output

The generated file contains {run['rows']} sorted request rows and {run['steps']} steps. Counts: {json.dumps(run['statuses'], sort_keys=True)}. Contract validation checks headers, request coverage, allowed operations/states, exact step fields, numbering, official order, citation existence/cutoff, and empty citations for future actions. It does not establish semantic correctness against hidden answers.
'''
    (output / 'evaluation_report.md').write_text(report, encoding='utf-8')
    methods = Counter(r['method'] for r in run['extractions'])
    cache_hits = sum(r['cache_hit'] for r in run['extractions'])
    ocr_calls = sum(not r['cache_hit'] for r in run['extractions'] if 'Ocr' in r['method'] or 'Tesseract' in r['method'])
    digest = hashlib.sha256((root / 'output.csv').read_bytes()).hexdigest()
    usage = f'''# GhostTrace final-run usage report

This report describes the recorded full-dataset prediction run that produced output.csv, not development conversation usage or optional dashboard reviews.

| Measure | Value |
| --- | --- |
| Requests | {run['rows']} |
| Recorded wall time, including extraction/loading | {run['seconds']} seconds |
| Output SHA-256 | {digest} |
| Cloud language-model providers/models used for prediction | None |
| Cloud language-model calls | 0 |
| Input text tokens | 0 |
| Output text tokens | 0 |
| Total text tokens | 0 |
| Average text tokens per request | 0 |
| Estimated external model/API cost, total | USD 0.00 |
| Estimated external model/API cost per request | USD 0.00 |

## Per-engine and overall accounting

| Provider / engine | Calls in recorded run | Cached artifacts reused | Input tokens | Output tokens | Estimated API cost |
| --- | --- | --- | --- | --- | --- |
| Microsoft Windows.Media.Ocr.OcrEngine, en-US, local OS engine | {ocr_calls} | {sum(r['cache_hit'] for r in run['extractions'] if 'Ocr' in r['method'])} | Not token based (0 billed text tokens) | Not token based (0 billed text tokens) | USD 0.00 |
| OpenAI language models | 0 | 0 | 0 | 0 | USD 0.00 |
| Overall external token-based inference | 0 | 0 | 0 | 0 | USD 0.00 |

Extraction methods observed: {json.dumps(dict(methods), sort_keys=True)}. Across PDF/image extraction there were {cache_hits} cache hits. Four PDFs are parsed with pypdf (deterministic extraction, not model calls). Eleven screenshots are read with the installed local OCR engine. Its underlying model version and pixel-based compute usage are not exposed by the Windows OCR API; no model version or pixel cost is invented. Text-token counts are zero because there are no token-metered inference calls, not because OCR performs no computation.

The code supports Tesseract on non-Windows platforms, but it was not used in this recorded run. Local CPU, electricity, machine ownership, and operating-system costs are not measured or included in the API-cost estimate.

The coding assistant used during development was Codex with runtime model gpt-6.1-sol, verified from local session metadata. Those development tokens are outside the final application inference run and are not presented as final-run usage. Optional OpenAI advisory reviews are also excluded: no such review was invoked for the submitted predictions. Credentials are read only from environment variables and are not included in the package.
'''
    (output / 'usage_report.md').write_text(usage, encoding='utf-8')
    print('Wrote evaluation/evaluation_report.md and evaluation/usage_report.md')


if __name__ == '__main__':
    main()
