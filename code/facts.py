"""All evidence -> one flat fact list (SQL + JSON + text + logs), with states derived."""
from evidence import DATA, load_all_facts as static_facts, read_csv
from logfacts import facts_from_log
from docfacts import facts_from_pdf
from imgfacts import facts_from_images

TRUE = (True, 1, "1", "true", "True")


def _has_identifier(f):
    return any([f["user_ref"], f["name"], f["email"], f["phone"], f["email_hash"], f["text_emails"]])


def derive_state(f):
    """Fill in the detailed state of static (SQL/JSON) facts from their columns."""
    if f["state"] not in (None, "PRESENT"):
        return f
    t, x = f["record_type"], f["extra"]
    if t == "BACKUP_ARCHIVE" and "restore_allowed" in x:
        f["state"] = "ACTIVE" if x["restore_allowed"] in TRUE else "BLOCKED"
    elif t == "DATA_FLOW" and "enabled" in x:
        f["state"] = "ACTIVE" if x["enabled"] in TRUE else "DISABLED"
    elif t in ("ANALYTICS_PROFILE", "SUPPORT_MESSAGE"):
        f["state"] = "IDENTIFIABLE" if _has_identifier(f) else ("ANONYMIZED" if t == "ANALYTICS_PROFILE" else "REDACTED")
    else:
        f["state"] = "PRESENT"
    return f


def load_all_facts():
    facts = static_facts()
    for ef in read_csv("evidence_files.csv"):
        if ef["file_path"].endswith(".log"):
            facts += facts_from_log(DATA / ef["file_path"], ef["file_id"])
        elif ef["file_path"].endswith(".pdf"):
            facts += facts_from_pdf(DATA / ef["file_path"], ef["file_id"], ef["captured_at"])
        elif ef["file_path"].endswith(".png"):
            facts += facts_from_images(ef["file_id"], ef["captured_at"])
    return [derive_state(f) for f in facts]


if __name__ == "__main__":
    import collections
    facts = load_all_facts()
    print("facts:", len(facts))
    print(collections.Counter((f["record_type"], f["state"]) for f in facts).most_common())