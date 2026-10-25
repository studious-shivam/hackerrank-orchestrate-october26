"""Turn the PDF evidence files into facts (same shape as evidence.py facts).

Needs:  pip install pypdf
All four PDFs have a real text layer, so no OCR or vision model is used.
Each PDF type is recognised by its title line, then parsed with regexes that
work on whitespace-flattened text (so they don't depend on PDF layout).
"""
import re

from pypdf import PdfReader

from evidence import EMAIL_RE, _fact

PHONE_RE = re.compile(r"\+\d[\d ]{7,}\d")
USER_RE = re.compile(r"\buser_\d+\b")


def pdf_text(path):
    """All pages joined, whitespace collapsed to single spaces."""
    text = " ".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    return re.sub(r"\s+", " ", text)


def _delivery_attachment(text, file_id, captured_at):
    """Support attachment: 'reference CS-4827 / support_001' + requester details."""
    m = re.search(r"(CS-\d+)\s*/\s*(support_\d+)", text)
    if not m:
        return []
    ticket, rid = m.groups()
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)
    # Name sits between the 'received <date>' detail and the email address.
    name = None
    if email:
        n = re.search(r"received \d{1,2} \w{3} \d{4} (?:Detail )?(.+?) (?:Detail )?"
                      + re.escape(email.group(0)), text)
        name = n.group(1).strip() if n else None
    row = {"email": email.group(0) if email else None,
           "phone": phone.group(0) if phone else None,
           "name": name,
           "ticket_id": ticket}
    fn = re.search(r"file (\S+\.pdf)", text)
    if fn:
        row["file_name"] = fn.group(1)
    o = re.search(r"order (ORD-\d+)", text)
    if o:
        row["order_reference"] = o.group(1)
    return [_fact(file_id, captured_at, "pdf:ticket_attachment", "support_platform", rid,
                  "SUPPORT_ATTACHMENT", row, "PRESENT")]


def _security_journal(text, file_id, captured_at):
    """Compliance journal entry: 'Event reference audit_record_003 subject reference user_03'."""
    out = []
    for m in re.finditer(r"Event reference (audit_record_\w+) (?:Detail )?subject reference (user_\d+)", text):
        rid, user = m.groups()
        row = {"customer_reference": user}
        r = re.search(r"retain until (\d{1,2} \w{3} \d{4})", text[m.end():])
        if r:
            row["retained_until"] = r.group(1)
        e = re.search(r"event (.+?) (?:Detail )?actor", text[m.end():])
        if e:
            row["event_name"] = e.group(1).strip()
        out.append(_fact(file_id, captured_at, "pdf:compliance_journal", "security_service",
                         rid, "SECURITY_AUDIT_LOG", row, "PRESENT"))
    return out


def _legal_register(text, file_id, captured_at):
    """Disputed orders register: 'ORD-20264118 | user_08 | Card dispute | ... | Retain until ...'.

    The register has no legal-hold record id. The SQL/JSON evidence names these
    records legal_hold_<last 4 digits of the order number> (ORD-20268017 -> legal_hold_8017),
    so the same rule is used here.  CHECK this against the sample answers.
    """
    out = []
    for m in re.finditer(r"(ORD-\d+) \| (user_\d+) \| (.+?) \| (\d{1,2} \w{3} \d{4}) \| "
                         r"([A-Z]{3} [\d.,]+) \| Retain until (\d{1,2} \w{3} \d{4})", text):
        order, user, reason, _inv_date, _amount, until = m.groups()
        row = {"customer_reference": user, "order_reference": order,
               "retention_reason": reason, "retained_until": until}
        out.append(_fact(file_id, captured_at, "pdf:retention_register", "legal_service",
                         "legal_hold_" + order[-4:], "LEGAL_HOLD_RECORD", row, "PRESENT"))
    return out


def _customer_statement(text, file_id, captured_at):
    """Customer statement 'NST-2026-0718-1842'.  The data catalog (activity_4009) records it
    as export_1842, a user export owned by the named customer."""
    m = re.search(r"NST-\d{4}-\d{4}-(\d+)", text)
    email = EMAIL_RE.search(text)
    user = USER_RE.search(text)
    if not m:
        return []
    row = {"email": email.group(0) if email else None,
           "customer_reference": user.group(0) if user else None}
    return [_fact(file_id, captured_at, "pdf:customer_statement", "export_service",
                  "export_" + m.group(1), "USER_EXPORT", row, "PRESENT")]


PARSERS = (
    ("DELIVERY ADDRESS CORRECTION", _delivery_attachment),
    ("COMPLIANCE JOURNAL", _security_journal),
    ("DISPUTED ORDERS AND TAX RECORDS", _legal_register),
    ("CUSTOMER STATEMENT", _customer_statement),
)


def facts_from_pdf(path, file_id, captured_at=None):
    text = pdf_text(path)
    for marker, parser in PARSERS:
        if marker in text.upper():
            return parser(text, file_id, captured_at)
    return []


if __name__ == "__main__":
    from loaders import DATA, read_csv
    for ef in read_csv("evidence_files.csv"):
        if ef["file_path"].endswith(".pdf"):
            fs = facts_from_pdf(DATA / ef["file_path"], ef["file_id"], ef["captured_at"])
            print(ef["file_id"], ef["file_path"].split("/")[-1], "->", len(fs), "facts")
            for f in fs:
                print("   ", f["system_id"], f["resource_id"], f["record_type"], f["state"],
                      f["user_ref"], f["email"], f["name"])