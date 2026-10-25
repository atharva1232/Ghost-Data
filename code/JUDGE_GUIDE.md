# GhostTrace — Judge interview and demo guide

## Opening pitch (30 seconds)

GhostTrace investigates whether a customer's deletion is actually complete. A successful account deletion does not prove that replicas, support attachments, logs, or backups are safe. We connect current and historical identities to the supplied evidence, apply the deletion policy at the audit cutoff, and return an evidence-linked verdict, ordered remediation, and verification checks. The solution runs locally and exports the exact submission CSV.

## Three-minute demonstration

1. Launch START_GHOSTTRACE.cmd from the project root and select Present project. Use Next chapter or the left/right arrows.
2. Explain the failure: a surviving replica or sync can recreate deleted personal data.
3. Show Resolve → Investigate → Apply policy → Plan & prove. Describe one concrete input at each stage.
4. Open Live investigation. Its figures come from the currently selected saved run. If none is loaded, use Overview to select the official dataset and run an audit first.
5. Click Inspect an incomplete case. Show identity aliases, one evidence citation, a recreation path, and the remediation/proof sections. This case is selected from actual run findings, not a hardcoded answer.
6. Open Evaluation and run it. Explain the difference between correct status, correct detailed steps, and exact sequence. End with Engineering choices and Competition handoff.

The presentation includes Print / save PDF. Use the browser's print dialog to export all six chapters. Generated PDF layout has not been separately certified; check the print preview before sharing.

## Questions to prepare for

**Why is this an AI-powered project?** Local OCR extracts text from screenshots, while PDF extraction and structured parsers recover other evidence. The core uses deterministic identity and policy checks. An optional OpenAI advisory review is implemented, but was not called in the submitted prediction run. Do not describe the final run as autonomous LLM reasoning.

**How do you find historical identities?** The current identity snapshot and identity audit history connect stable subject references to previous identifiers. Those aliases are searched across the participant evidence. Ambiguous resource ownership remains a known weakness.

**How do you prevent a false proof from future evidence?** Each case has an audit cutoff. Observations and captures after that cutoff cannot establish the earlier state. Workflow completion messages are claims until supported by state evidence.

**Why not delete every matching record?** Supplied rules may require retention, redaction, anonymization, or an account tombstone. The plan must preserve permitted stable references and required retained records.

**Why stop a process first?** A running sync or restore path can recreate the data after deletion. The output prioritizes disabling relevant flows and blocking unsafe restores before record treatment. Validate actual dependencies before operational use.

**What proves the implementation works?** The recorded candidate passed 52 tests and all 518 output rows passed contract validation. A fresh extraction of the packaged source produced byte-identical output. Those checks demonstrate reproducibility and format compliance, not complete semantic correctness.

**What accuracy did you achieve?** On 32 public development samples: 100% status, 55.05% exact aligned steps, 68.54% aligned fields, and 28.12% exact sequences. These samples influenced development; hidden accuracy is unknown. The detailed plan is the largest measured weakness.

**Where would you improve it?** Stronger resource ownership links, verification for absent resources, OCR confidence handling, and less ambiguous temporal workflow associations. Evaluate improvements on new independently designed cases as well as public samples.

**What does it cost?** The recorded full inference run used zero cloud LLM calls and incurred $0 external API cost. Local OCR, hardware, and electricity still have costs; they were not estimated. The recorded cold run took about 21.4 seconds on this machine.

**Does it execute deletion?** No. It audits provided evidence and proposes actions and checks. Production execution would need connectors, authorization, retention controls, and verification against live systems.

## Score categories shown in the supplied screenshot

| Category | Maximum | What to show |
|---|---:|---|
| Chat transcript | 10 | Authentic root log.txt, including decisions and limitations |
| AI judge interview | 30 | Explain the implementation and one real evidence trail |
| Output CSV | 30 | Exact contract, public metrics, and known detailed-step errors |
| Code ZIP | 30 | Setup, runnable CLI, tests, architecture, and evaluation reports |

These are category maximums from the screenshot, not official detailed scoring criteria or a score prediction. Visual polish does not change CSV accuracy. Do not invent evaluation results, judge scores, or development history.
