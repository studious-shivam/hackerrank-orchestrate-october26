# Ghost Data Still Exists - deletion audit agent

Deterministic pipeline: no LLM or API key is needed at run time.

## Setup
    python -m venv .venv
    source .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install pypdf                # only third-party dependency (PDF text layer)

## Run
    python code/main.py                                   # all 518 requests -> output.csv at repo root
    python code/main.py sample_deletion_requests.csv /tmp/sample_pred.csv   # file name is relative to dataset/

## Evaluate
    python code/evaluation/main.py /tmp/sample_pred.csv dataset/sample_output.csv --cases
    python code/evaluation/custom_cases.py

Reports: `evaluation/evaluation_report.md`, `evaluation/usage_report.md`.

## Pipeline (code/)
1. `intent.py` - does `request_text` authorise deletion? (multilingual, with negation guards) else `NOT_APPLICABLE`.
2. `identity.py` - request email (current or historical) -> `user_id` and every email, phone and hash.
3. `evidence.py`, `logparse.py`, `logfacts.py`, `docfacts.py`, `imgfacts.py`, `facts.py` - SQL, JSON, text, logs, PDFs and screenshots become one list of facts with a state.
4. `planner.py` - keep the latest state at or before `audit_at`, apply `deletion_rules.csv`, decide the status, emit ordered steps.
5. `main.py` - writes `output.csv` sorted by `case_id`.

## Known limits
See "Known remaining errors" in `evaluation/evaluation_report.md`.
