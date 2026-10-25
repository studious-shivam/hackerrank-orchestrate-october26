# Evaluation report

Scored with `python code/evaluation/main.py <pred.csv> dataset/sample_output.csv` on the 32 public sample cases.

**Important caveat:** several heuristics below (account linking window, anonymized-analytics window, evidence-file choice) were tuned while looking at these 32 samples. The numbers are therefore optimistic for the hidden 518-case set, and no hidden-set score is known.

## Results on the 32 sample cases

| Metric | Value |
|---|---|
| Case-level status accuracy | 32/32 = 100.0% |
| Step precision (exact 6-field match) | 95.2% |
| Step recall | 92.2% |
| Step F1 | 93.7% |
| Field-level accuracy (steps matched on phase/system/resource/operation) | 100.0% |
| Sequence accuracy, exact array | 59.4% (19/32 cases) |
| Gold steps / predicted steps | 193 / 187 |

## Additional evaluation cases (written by us)

`python code/evaluation/custom_cases.py` - 5 of 5 pass.

1. Non-deletion requests (marketing-only, correction, information request) are `NOT_APPLICABLE`.
2. Deletion requests in German, Spanish, Japanese and Korean are detected.
3. Steps are ordered findings -> remediation -> verification, by operation table order, then system and resource, with consecutive numbering.
4. A request using a historical email resolves to the same `user_id` as the current email.
5. A tombstone holding an email hash is exposed PII; one holding only `user_id` is compliant.

These are small logic tests, not full end-to-end cases with evidence. End-to-end custom cases (for example a sync job recreating a deleted record) were not built.

## Failures found and improvements made

Changes were applied in small batches; each row shows the sample score after that batch, so a row can contain more than the one fix named in it.

| Step | Status accuracy | Step F1 | What was wrong -> fix |
|---|---|---|---|
| First pass | 68.8% | 59.6% | Intent regex too narrow, so natural-language requests came back `NOT_APPLICABLE`. Broadened it and kept negation guards. |
| + file-time filter | 90.6% | 82.3% | Log events inside a late-captured file were cited although the file was captured after `audit_at`. Now both the event and the file must be at or before `audit_at`. |
| + evidence rules | 90.6% | 84.6% | Future remediation and verification steps carried evidence ids. Now blank for INCOMPLETE. For COMPLETE, one primary evidence file (most records covered) is cited. |
| + legal holds dropped | 90.6% | 84.6% | Legal-hold steps never appear in the sample answers, so they are no longer emitted. Unconfirmed against the hidden set. |
| + support-message state | 100% | 92.5% | A support message that kept only `user_id` was treated as exposed. Only direct identifiers (name, email, phone, hash, email in text) now count. |
| + COMPLETE verification | 100% | 92.5% | COMPLETE cases now verify every compliant record (redacted, anonymized, blocked, disabled, absent). |
| + analytics linking | 100% | 93.7% | Anonymized analytics profiles carry no identifier. Linked through a successful ANONYMIZE_RECORD activity 1-35 minutes before `reported_at`. |

## Known remaining errors

- **Account profile id.** Often exists only in the activity stream, among decoys with similar timestamps. Resolved with a result-status match, a time window and a one-to-one assignment; ties fall back to the earliest candidate. About half of ambiguous cases resolve correctly.
- **Retained audit records** (for example `audit_record_6645`) appear in no evidence file for some samples, so they are omitted.
- **`object_19`** (object-storage screenshot) is emitted for case_07 but the sample answer does not include it.
- **Image facts** are a one-time hand transcription of 11 screenshots, not a runtime vision call.
