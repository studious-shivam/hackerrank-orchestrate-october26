"""Turn normalized log events into facts (same shape as evidence.py facts)."""
import re
from collections import defaultdict

from evidence import _fact
from logparse import parse_log

SERVICE_ALIAS = {"profile_service": "account_service"}
# fields in any event of a trace that can identify the data subject
ID_KEYS = ("lookup_key", "subject_key", "owner_key", "scan_key", "subject_ref", "match_key",
           "correlation_key", "email", "customer_email", "requester_email", "owner_email",
           "matched_value", "subject_reference", "customer_reference")
NULLS = ("", "null", "none")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
USER = re.compile(r"^user_\d+$")


def _t(v):
    return str(v).strip().lower() == "true"


def _has(v):
    return v is not None and str(v).strip().lower() not in NULLS


def _classify_ids(values):
    """Sort raw identifier strings into email / user ref / hash."""
    row = {}
    for v in values:
        if not _has(v):
            continue
        v = str(v).strip()
        if "@" in v:
            row.setdefault("email", v.lower())
        elif USER.match(v):
            row.setdefault("customer_reference", v)
        elif HEX64.match(v.lower()):
            row.setdefault("email_hash", v.lower())
    return row


def _state(system, event, f):
    """(record_type, state) for a result-bearing event, else None."""
    if event == "profile_lookup_completed":
        return "USER_PROFILE", ("PRESENT" if f.get("http_status") == "200" or f.get("rows") not in (None, "0") else "ABSENT")
    if event == "index_query_completed":
        return "SEARCH_INDEX_ENTRY", ("PRESENT" if f.get("result") == "hit" else "ABSENT")
    if event == "analytics_profile_read_completed":
        ident = any(_has(f.get(k)) for k in ("customer_reference", "email", "phone", "email_hash"))
        return "ANALYTICS_PROFILE", ("IDENTIFIABLE" if ident else "ANONYMIZED")
    if event == "analytics_profile_read":
        return "ANALYTICS_PROFILE", ("IDENTIFIABLE" if f.get("direct_identifiers") not in (None, "0") else "ANONYMIZED")
    if event == "analytics_identity_scan":
        return "ANALYTICS_PROFILE", "IDENTIFIABLE"
    if event == "contact_lookup_completed":
        return "MARKETING_PROFILE", ("PRESENT" if f.get("rows") != "0" else "ABSENT")
    if event == "message_pii_scan":
        return "SUPPORT_MESSAGE", "IDENTIFIABLE"
    if event == "attachment_pii_scan":
        return "SUPPORT_ATTACHMENT", "PRESENT"
    if event == "message_read":
        return "SUPPORT_MESSAGE", ("REDACTED" if "[REDACTED]" in f.get("message_text", "") else "IDENTIFIABLE")
    if event == "support_ticket_read_completed":
        ident = any(_has(f.get(k)) for k in ("requester_email", "requester_name", "requester_phone", "customer_reference"))
        return "SUPPORT_MESSAGE", ("IDENTIFIABLE" if ident else "REDACTED")
    if event == "contact_query_completed":                       # support replica contact index
        return "SECONDARY_IDENTIFIER", ("PRESENT" if f.get("rows") != "0" else "ABSENT")
    if event == "restore_candidate_evaluated":
        return "BACKUP_ARCHIVE", ("ACTIVE" if _t(f.get("eligible")) and not _t(f.get("deletion_block")) else "BLOCKED")
    if event == "restore_authorization_completed":
        return "BACKUP_ARCHIVE", ("BLOCKED" if f.get("decision") == "deny" else "ACTIVE")
    if event == "restore_policy_read_completed":
        return "BACKUP_ARCHIVE", ("ACTIVE" if _t(f.get("restore_allowed")) else "BLOCKED")
    if event == "connector_heartbeat":
        return "DATA_FLOW", ("ACTIVE" if _t(f.get("enabled")) and _t(f.get("scheduler_registered")) else "DISABLED")
    if event == "connector_config_loaded":
        return "DATA_FLOW", ("ACTIVE" if _t(f.get("enabled")) and _t(f.get("scheduler_registered")) else "DISABLED")
    if event == "connector_config_read_completed":
        return "DATA_FLOW", ("ACTIVE" if _t(f.get("enabled")) else "DISABLED")
    if event in ("export_download_check_completed", "export_metadata_read_completed"):
        return "USER_EXPORT", ("PRESENT" if _t(f.get("available")) else "ABSENT")
    if event == "audit_record_read_completed":
        return "SECURITY_AUDIT_LOG", ("PRESENT" if f.get("rows") != "0" else "ABSENT")
    if event == "retained_order_loaded":
        return "LEGAL_HOLD_RECORD", "PRESENT"
    return None


def facts_from_log(path, file_id):
    events = parse_log(path)
    ctx = defaultdict(list)                       # trace_id -> identifier strings seen in that trace
    for e in events:
        if e["trace_id"]:
            ctx[e["trace_id"]] += [e["f"].get(k) for k in ID_KEYS]
    out = []
    for e in events:
        f, ev = e["f"], e["event"]
        system = SERVICE_ALIAS.get(e["service"], e["service"])
        if ev == "record_lookup":                 # self-describing event
            row = dict(f)
            out.append(_fact(file_id, e["ts"], "log:record_lookup", f["system"], f["resource_id"],
                             f["record_type"], row, f["result"]))
            continue
        rid = f.get("resource_id")
        hit = _state(system, ev, f)
        if not rid or hit is None:
            continue
        rtype, state = hit
        if e["service"] == "support_replica":
            system = "support_platform"
        row = {k: v for k, v in f.items() if _has(v)}
        for k, v in _classify_ids([f.get(k) for k in ID_KEYS] + ctx.get(e["trace_id"], [])).items():
            row.setdefault(k, v)
        for k in ("lookup_key", "subject_key", "owner_key", "scan_key", "subject_ref", "match_key",
                  "correlation_key", "matched_value"):
            row.pop(k, None)
        out.append(_fact(file_id, e["ts"], "log:" + ev, system, rid, rtype, row, state))
    return out