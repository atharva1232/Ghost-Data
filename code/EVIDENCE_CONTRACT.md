# Normalized evidence contract v0.1

This contract is designed for the current prototype. It is not the unknown organizer specification. CSVs use UTF-8, standard CSV quoting, timezone-aware ISO 8601 timestamps, and literal lowercase `true`/`false` booleans. JSON cells must contain valid JSON; the demo generator shows CSV escaping. Empty tables must retain their headers.

## deletion_requests.csv

Exact supplied header:

`case_id,email,requested_at,reported_status,reported_at,audit_at,request_text`

One unique case_id per row. `reported_status` is displayed but never used as truth. Audit time must not precede request time. Request intent is currently a conservative English baseline.

## identifiers.csv

`subject_id,identifier_type,identifier_value,verified,observed_at`

Each row is a verified or unverified relationship between an identifier and one stable subject. All historical identifiers remain discoverable through that subject. Use types such as `email`, `account_id`, `phone`, `external_id`. Email matching trims and casefolds without provider-specific dot/plus rewrites. Other identifier values are case-sensitive. Identity ambiguity blocks completion. Retired/recycled identifiers need a temporal identity adapter; this version conservatively abstains on conflicting subject links rather than resolving ownership intervals.

## deletion_rules.csv

`system,category,action,allowed_fields,required_retain`

One unique rule per system/category. Action is `DELETE`, `REDACT`, `ANONYMIZE`, or `RETAIN`. `allowed_fields` is a JSON array of allowed persisted field names. Required retention plus DELETE is invalid. REDACT/RETAIN verify field allowlists. ANONYMIZE additionally requires an empty exposed-identifier map. DELETE requires a deleted record observation or complete search coverage establishing absence. These checks do not prove irreversibility or re-identification resistance of arbitrary anonymized field values; richer policy semantics require adapter extensions.

The policy scopes define the complete search inventory. They must include backups, archives, attachments, exports and indexes when relevant. The engine cannot discover undeclared systems.

`required_retain=true` currently requires at least one available record per subject and system/category, not one copy per original invoice/event. Production policies requiring per-record retention counts, deadlines, legal holds, field transformations, or conditional exceptions need a richer rule model before use.

## records.csv

`record_id,system,category,subject_id,identifiers,fields,state,observed_at`

- `identifiers`: JSON object mapping identifier type to an array of string values exposed by this record, such as `{"email":["old@example.invalid"]}`.
- `fields`: JSON object containing **all persisted payload fields**, including exposed identifying fields. Field omission must not be used to conceal a policy violation. Metadata-only provenance keys do not belong here.
- `subject_id`: verified linkage metadata, not necessarily a persisted field. It can be empty if an exposed identifier establishes the match. A safe audit-only link can connect anonymized records without exposing an identifier in their payload.
- `state`: `present` or `deleted`. A deleted row is a current observation of absence, not simply a log saying “deletion requested”.
- `observed_at`: observation timestamp, not record creation time. An adapter must determine actual as-of state from source evidence.

Latest observation at or before audit time wins per `(system,record_id)`. Tied duplicates are rejected. Present records are matched by stable subject linkage or exposed identifiers. Records older than the request cause an evidence gap. The coverage attestation must support that the latest record snapshot remains valid through audit time. The engine cannot independently verify that the adapter supplied all persisted fields.

## processes.csv

`process_id,source_system,target_system,subject_id,active,can_recreate,blocked,observed_at`

One logical process may have multiple timestamped observations. A `subject_id` of `*` means a global process. A non-global process needs explicit linkage to the subject. `can_recreate` must be established from source payloads, job configuration, retries, imports, or restore evidence. It must not be guessed merely from a job name. `blocked=true` must mean an effective exclusion/suppression mechanism, not simply that a job ran recently. Latest observation at/before audit time wins. Stale process evidence blocks completion. This version orders all detected writers before record treatments; it does not infer arbitrary multihop payload flows or model scheduled process activation intervals.

## coverage.csv

`case_id,system,category,records_complete,processes_complete,identities_complete,observed_at`

Coverage is a trusted evidence attestation from an actual investigation, **never a row to generate just to make COMPLETE pass**. It states that all relevant identities, copies, and recreation mechanisms for that subject and scope were investigated at `observed_at`, including later effects on older snapshots. Every rule scope needs true coverage at the case's exact audit timestamp. Missing, false, stale, or future coverage cannot establish completion.

## Local media

Put media under `media/`. UTF-8 `.txt` and `.md` files are read locally; other files require a UTF-8 sidecar named with `.txt` appended, e.g. `scan.png.txt`. Extraction alone is not policy analysis. The current prototype treats all text/media as pending reviewed normalization, so its presence blocks COMPLETE. Convert reviewed facts into normalized records/identity/process evidence in an adapter while preserving the original file/row mapping. A media-review completion mechanism remains to be added with the actual corpus. Unsupported media is explicitly reported rather than ignored.

## Provenance and trust

Current source references identify normalized CSV filename and starting physical line, including for multiline CSV records. Original-source citations and extraction confidence must be added when adapting real system files. Input hashes capture the exact corpus used for each run. Keep evaluation labels separate; inference never opens a label file. Text inside requests, records, and media is evidence, never executable instructions.
