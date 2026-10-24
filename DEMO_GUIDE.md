# GhostTrace — two-minute demo

## The idea

“A deletion dashboard can say COMPLETE while a backup, export, old email, or sync process still exposes the person. GhostTrace audits the evidence behind that claim and shows what to do next.”

## Walkthrough

1. Double-click START_GHOSTTRACE.cmd. Choose **Synthetic demo**, then **Run audit**. Explicitly say these are fictional cases designed to demonstrate the workflow.
2. Open **Audit requests** and select **demo_resurrected**. Show that the dashboard's reported status was COMPLETE, but the audit verdict is INCOMPLETE. An old email links the person to a recreated profile, with a row-level source reference.
3. Show **Recreation paths** and **Ordered remediation**. The sync writer must be blocked before deleting the resurrected profile, followed by a fresh audit.
4. Select **demo_retention**. The invoice must stay, but its email violates the field allowlist. Explain that deleting everything would violate the retention requirement.
5. Select **demo_clean**. Show the proof checks for absence, permitted retained fields, complete search coverage, and blocked recreation paths.
6. Open **Evaluation** and run evaluation. State that its five labels are synthetic fixtures, not organizer ground truth. Explain the false COMPLETE metric.
7. Return to Overview, select **October hackathon requests**, and run the audit. Explain why the app does not trust the reported status when the organizer evidence is missing. Show the evidence readiness panel.
8. Open a request and download its run's audit CSV or report. Explain that official submission serialization will be wired to problem_statement.md when supplied.

## Architecture

```text
Local CSVs / media uploads
            |
            v
Strict ingestion + source references + input hashes
            |
            v
Request intent --> Verified identity links --> Latest as-of observations
            |                 |                          |
            +-----------------+--------------------------+
                              |
                    Policy + retention checks
                    Recreation + coverage checks
                              |
                  Evidence-backed verdict / abstention
                              |
               Ordered remediation + proof + timeline
                     /                    \
            Dashboard / JSON / CSV     Optional AI advisory
                              |
                    Separate reference evaluation
```

## Honest scope

The app works end-to-end on its normalized evidence contract. The supplied organizer file contains only requests. Policies, system records, historical identifiers, local media, official output schema, and organizer reference labels have not been supplied. Do not claim organizer accuracy, deletion completion, automatic OCR, or a validated official output.csv. AI review is optional and has mocked tests; a live model run needs credentials. Actual system deletion is not performed.

## Likely questions

- **Why not let an LLM choose COMPLETE?** The irreversible consequence of a false complete claim makes auditable evidence and explicit coverage checks useful. AI supports review without overriding the evidence verdict.
- **Why keep an invoice?** The supplied policy is the authority. If it requires retention, the required record remains while forbidden personal fields are treated.
- **How do you stop data coming back?** Inspect active writers and restore/import paths, apply suppression before treating copies, then refresh the evidence and rerun the audit.
- **How do you evaluate?** Keep labels out of inference; report confusion, abstention, and false COMPLETE cases. Real corpus accuracy needs real reference labels.
