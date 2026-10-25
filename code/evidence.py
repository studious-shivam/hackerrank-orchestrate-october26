"""Turn evidence files into a flat list of 'facts' (one per record seen)."""
import json
import re
import sqlite3
from pathlib import Path

from loaders import DATA, read_csv

# SQL table -> (system_id, record_type)
TABLE_MAP = {
    "customer_profiles": ("account_service", "USER_PROFILE"),
    "customer_profiles_primary": ("account_service", "USER_PROFILE"),
    "customer_profiles_failover_replica": ("account_service", "USER_PROFILE"),
    "customer_search_documents": ("search_service", "SEARCH_INDEX_ENTRY"),
    "search_documents_primary": ("search_service", "SEARCH_INDEX_ENTRY"),
    "customer_analytics_profiles": ("analytics_platform", "ANALYTICS_PROFILE"),
    "support_records": ("support_platform", "SUPPORT_MESSAGE"),
    "customer_exports": ("export_service", "USER_EXPORT"),
    "connector_subscriptions": ("integration_service", "DATA_FLOW"),
    "backup_restore_entries": ("backup_service", "BACKUP_ARCHIVE"),
    "security_audit_records": ("security_service", "SECURITY_AUDIT_LOG"),
}
# Replica "collection_name" -> canonical record type (system comes from origin_system)
COLLECTION_MAP = {
    "customer_profiles": "USER_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY",
    "customer_analytics_reports": "ANALYTICS_PROFILE",
    "support_conversations": "SUPPORT_MESSAGE",
    "ticket_attachments": "SUPPORT_ATTACHMENT",
    "customer_export_jobs": "USER_EXPORT",
    "connector_configurations": "DATA_FLOW",
    "backup_catalog": "BACKUP_ARCHIVE",
    "security_audit_events": "SECURITY_AUDIT_LOG",
    "retained_order_records": "LEGAL_HOLD_RECORD",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE",
}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Columns that hold each kind of identifier, depending on the table
NAME_COLS = ("full_name", "display_name", "requester_name", "name")
EMAIL_COLS = ("email", "requester_email", "owner_email", "customer_email",
              "subject_selector", "uploaded_by")
PHONE_COLS = ("phone", "requester_phone", "owner_phone")
REF_COLS = ("customer_reference", "user_id", "subject_reference")


def _clean(v):
    return None if v in (None, "", "None", "null") else v


def _flatten(row):
    row = dict(row)
    doc = row.pop("document", None)
    if isinstance(doc, dict):
        row.update(doc)
    return row


def _fact(file_id, captured_at, container, system, resource_id, rtype, row):
    row = _flatten(row)
    f = {
        "file_id": file_id, "captured_at": captured_at, "container": container,
        "system_id": system, "resource_id": resource_id, "record_type": rtype,
        "user_ref": None, "name": None, "email": None, "phone": None,
        "email_hash": _clean(row.get("email_hash")), "extra": {},
    }
    for c in NAME_COLS:
        if _clean(row.get(c)): f["name"] = row[c]
    for c in EMAIL_COLS:
        if _clean(row.get(c)): f["email"] = row[c].strip().lower()
    for c in PHONE_COLS:
        if _clean(row.get(c)): f["phone"] = row[c]
    for c in REF_COLS:
        if _clean(row.get(c)): f["user_ref"] = row[c]
    sref = row.get("subject_reference")
    if sref and "@" in str(sref):                     # reference is an email, not a user_id
        f["user_ref"], f["email"] = None, str(sref).strip().lower()
    f["text_emails"] = sorted({m.lower() for k in ("message_text", "message_excerpt")
                               for m in EMAIL_RE.findall(str(row.get(k) or ""))})
    skip = set(NAME_COLS + EMAIL_COLS + PHONE_COLS + REF_COLS + ("email_hash", "resource_id"))
    f["extra"] = {k: v for k, v in row.items() if k not in skip}
    return f


def facts_from_sql(path, file_id, captured_at):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(Path(path).read_text(encoding="utf-8"))
    out = []
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    for t in tables:
        if t == "snapshot_scope":
            continue
        for r in con.execute(f'select * from "{t}"'):
            row = dict(r)
            if "record_json" in row:                      # generic replica tables
                payload = json.loads(row["record_json"])
                payload.setdefault("resource_id", row["resource_id"])
                payload["updated_at"] = row["updated_at"]
                rtype = COLLECTION_MAP.get(row["collection_name"], row["collection_name"])
                out.append(_fact(file_id, captured_at, t, row["origin_system"],
                                 row["resource_id"], rtype, payload))
            elif t in TABLE_MAP:
                system, rtype = TABLE_MAP[t]
                out.append(_fact(file_id, captured_at, t, system, row["resource_id"], rtype, row))
    return out


def load_all_facts():
    facts = []
    for ef in read_csv("evidence_files.csv"):
        p = DATA / ef["file_path"]
        if p.suffix == ".sql":
            facts += facts_from_sql(p, ef["file_id"], ef["captured_at"])
    return facts


if __name__ == "__main__":
    import collections
    facts = load_all_facts()
    print("SQL facts:", len(facts))
    print(collections.Counter((f["system_id"], f["record_type"]) for f in facts).most_common())