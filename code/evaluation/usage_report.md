# GhostTrace final-run usage report

This report describes the recorded full-dataset prediction run that produced output.csv, not development conversation usage or optional dashboard reviews.

| Measure | Value |
| --- | --- |
| Requests | 518 |
| Recorded wall time, including extraction/loading | 21.422 seconds |
| Output SHA-256 | 08c2795861ff7ff2823c8e1a3c565252d0146148763bdb522620ea31f1ed334a |
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
| Microsoft Windows.Media.Ocr.OcrEngine, en-US, local OS engine | 11 | 0 | Not token based (0 billed text tokens) | Not token based (0 billed text tokens) | USD 0.00 |
| OpenAI language models | 0 | 0 | 0 | 0 | USD 0.00 |
| Overall external token-based inference | 0 | 0 | 0 | 0 | USD 0.00 |

Extraction methods observed: {"Windows.Media.Ocr.OcrEngine/en-US": 11, "pypdf": 4}. Across PDF/image extraction there were 0 cache hits. Four PDFs are parsed with pypdf (deterministic extraction, not model calls). Eleven screenshots are read with the installed local OCR engine. Its underlying model version and pixel-based compute usage are not exposed by the Windows OCR API; no model version or pixel cost is invented. Text-token counts are zero because there are no token-metered inference calls, not because OCR performs no computation.

The code supports Tesseract on non-Windows platforms, but it was not used in this recorded run. Local CPU, electricity, machine ownership, and operating-system costs are not measured or included in the API-cost estimate.

The coding assistant used during development was Codex with runtime model gpt-6.1-sol, verified from local session metadata. Those development tokens are outside the final application inference run and are not presented as final-run usage. Optional OpenAI advisory reviews are also excluded: no such review was invoked for the submitted predictions. Credentials are read only from environment variables and are not included in the package.
