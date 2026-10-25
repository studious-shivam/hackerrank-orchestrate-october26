# Token usage and cost

## Final full-dataset run (518 cases, produces `output.csv`)

| Item | Value |
|---|---|
| Model providers / models | none |
| Model calls | 0 |
| Input tokens | 0 |
| Output tokens | 0 |
| Total tokens / average per request | 0 / 0 |
| Estimated cost (total / per request) | $0.00 / $0.00 |

The final run is fully deterministic Python (SQLite, regex, `pypdf`). No API is called, so no API key is needed.

## One-time work done before the final run

The 11 PNG screenshots were read once by a vision-capable model and transcribed by hand into `code/imgfacts.py`. That transcription is not repeated at run time. Its token usage was **not recorded**, so no figure is reported here.
