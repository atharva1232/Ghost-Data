# GhostTrace evaluation report

## Measured public-sample results

Evaluation used the 32 participant-facing sample requests and their public reference output. Reference labels are read only by the evaluator, never the predictor. These samples were used during debugging, so the scores are development-set results, not unbiased held-out estimates. Hidden-case accuracy is unknown.

| Metric | Result |
| --- | --- |
| Case-level deletion-status accuracy | 100.00% |
| Exact aligned step accuracy | 55.05% |
| Aligned field accuracy | 68.54% |
| Exact full-sequence accuracy | 28.12% |

Status accuracy is matching verdicts divided by labeled requests. Steps are compared at their array positions; the denominator is the sum of the larger predicted/reference step counts per case, so missing and extra steps are penalized. Field accuracy compares all seven required fields at those aligned positions. Sequence accuracy requires the entire ordered array to equal the reference; object-key order and JSON whitespace are ignored. Empty matching arrays are valid for non-deletion requests. This is our documented evaluation protocol, not a claim to reproduce the hidden grader.

## Additional participant-created evaluation cases

These independent synthetic cases are executable in tests/test_official.py. They do not use organizer case IDs or hidden labels.

| Custom case | Input evidence | Expected behavior | Result |
| --- | --- | --- | --- |
| Stable tombstone | Post-request tombstone has only an allowed stable subject reference and is redacted | COMPLETE; VERIFY_RECORD_REDACTED; never DELETE_RECORD | Pass |
| Exposed tombstone | Tombstone still exposes direct PII | INCOMPLETE; report PII, redact while preserving reference, verify redaction; future steps have empty evidence IDs | Pass |
| Active restore plus profile | Present profile and active backup restoration path | INCOMPLETE; BLOCK_RESTORE precedes DELETE_RECORD, with both verification checks | Pass |
| Future cleanup | Present profile before audit; deletion observation after audit | INCOMPLETE; future evidence cannot hide the present profile | Pass |

Other regression cases cover historical aliases, decoy identities, multilingual authorization, SQL integer booleans, cloud/app/syslog/pipe log envelopes, retained PII, replica resurrection, malformed uploads, evidence time limits, output sorting, source citation validation, and separated reference evaluation. The last recorded suite passed 52 tests. Report generation does not itself rerun tests.

## Failures found and improvements made

- Initial public-sample status accuracy was 62.5%. The first request classifier missed confirmation-of-deletion and several removal formulations. Explicit authorization patterns were expanded without case-number rules.
- Unicode accent folding decomposed Hangul into Jamo and broke Korean deletion recognition. NFC recomposition fixed that issue; a Korean regression case now protects it.
- SQL boolean fields use 1/0 as well as true/false. Incorrect inactive interpretations were fixed and tested.
- Some evidence wraps events in cloud message strings, bracketed application records, pipe streams, or syslog headers. Added transport normalization and trace-key propagation so those evidence records are not silently skipped.
- Source attribution initially treated unrelated sidebar links as the main screenshot object. Main-object selection and conflicting-identity checks reduce those false associations.
- Added replica-aware inventory absence handling, future-capture exclusion, official sorting and citation validation, and a rule forbidding empty COMPLETE verification arrays.

## Remaining errors and limitations

Detailed step arrays differ on 23 of 32 public samples: case_03, case_04, case_06, case_07, case_08, case_09, case_10, case_15, case_17, case_18, case_20, case_21, case_22, case_23, case_24, case_25, case_26, case_27, case_28, case_29, case_30, case_31, case_32.

Status agreement does not imply a complete or correct remediation plan. Remaining discrepancies include absent or anonymized resources that cannot be confidently linked from the readback contents, temporal workflow-target association ambiguity, stale legacy resource links, support-record category classification, extra inferred resources, and evidence-selection differences. Workflow timing is heuristic and can join unrelated activity. Some inventories do not explicitly enumerate every absent resource. OCR text can contain character confusions or column-order errors. The system does not prove arbitrary anonymization strength or model every possible retention recovery action.

No hidden-answer score is claimed. Do not describe this as 100% overall accuracy or guaranteed correct deletion certification.

## Full evaluation-request output

The generated file contains 518 sorted request rows and 2782 steps. Counts: {"COMPLETE": 149, "INCOMPLETE": 359, "NOT_APPLICABLE": 10}. Contract validation checks headers, request coverage, allowed operations/states, exact step fields, numbering, official order, citation existence/cutoff, and empty citations for future actions. It does not establish semantic correctness against hidden answers.
