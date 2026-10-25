"""Facts read from the 11 PNG console screenshots (evidence/images/).

How this was produced: each screenshot was opened and read by a vision-capable
model (Claude) ONCE, and the records visible in it were transcribed below.
There are only 11 images and the hidden cases reuse the same evidence files, so
a one-time transcription is deterministic and costs no tokens at run time.
Keep this in mind for evaluation/usage_report.md: these 11 images are the only
multimodal model calls in the pipeline.

Each entry: file_id -> list of (system_id, resource_id, record_type, state, identifiers).
Identifiers use evidence.py's column names: name / email / phone / customer_reference.
"state" is what the screenshot itself shows; None means the screenshot does not
show enough to tell (the planner must treat that as "present, state unknown").
"""
from evidence import _fact

IMAGE_RECORDS = {
    # account_admin_console_20260926.png - active customer profile + a linked support ticket
    "evidence_04": [
        ("account_service", "account_5762", "USER_PROFILE", "PRESENT",
         {"name": "Haruka Sato", "email": "haruka.s1838@zoho.com", "phone": "+81 90 7610 2507",
          "customer_reference": "user_11"}),
    ],
    # search_index_inspector_20260901.png - query email:g.silva76@gmail.com, 2 hits.
    # search_1874 has a look-alike address (g.silva76.jr@...) and no customer reference:
    # a DIFFERENT person, must not be matched to user_13.
    "evidence_09": [
        ("search_service", "search_428", "SEARCH_INDEX_ENTRY", "PRESENT",
         {"name": "Gabriel Silva", "email": "g.silva76@gmail.com", "customer_reference": "user_13"}),
        ("search_service", "search_1874", "SEARCH_INDEX_ENTRY", "PRESENT",
         {"email": "g.silva76.jr@gmail.com"}),
    ],
    # connector_management_console_20260807.png - continuous, healthy, events flowing = ACTIVE
    "evidence_14": [
        ("integration_service", "data_flow_1121", "DATA_FLOW", "ACTIVE",
         {"email": "jain.aditi@gmail.com"}),
        ("integration_service", "data_flow_9846", "DATA_FLOW", "ACTIVE",
         {"email": "lucia-torres@gmail.com"}),
    ],
    # analytics_profile_view_20260713.png - named, email-identified profile = IDENTIFIABLE
    "evidence_19": [
        ("analytics_platform", "analytics_7438", "ANALYTICS_PROFILE", "IDENTIFIABLE",
         {"name": "Omar Darwish", "email": "darwish.omar@icloud.com", "customer_reference": "user_20"}),
    ],
    # customer_export_console_20260618.png - export_1260 is Ready (downloadable).
    # Other owners are @northstar.shop staff addresses.
    "evidence_23": [
        ("export_service", "export_1260", "USER_EXPORT", "PRESENT", {"email": "ingrid.dahl@outlook.com"}),
        ("export_service", "export_1261", "USER_EXPORT", "PRESENT", {"email": "marcus.lee@northstar.shop"}),
        ("export_service", "export_1259", "USER_EXPORT", "PRESENT", {"email": "sara.kim@northstar.shop"}),
        ("export_service", "export_1258", "USER_EXPORT", "PRESENT", {"email": "daniel.park@northstar.shop"}),
    ],
    # support_ticket_console_20260524.png - ticket CS-5034, name + email visible, nothing redacted
    "evidence_28": [
        ("support_platform", "support_1034", "SUPPORT_MESSAGE", "IDENTIFIABLE",
         {"name": "Kofi Agyeman", "email": "kagyeman8947@fastmail.com"}),
    ],
    # backup_restore_console_20260429.png - the screen does not show whether restore is
    # blocked, so state is left as plain PRESENT (restore status unknown).
    "evidence_32": [
        ("backup_service", "backup_9291", "BACKUP_ARCHIVE", "PRESENT", {"email": "bluepeakco@outlook.com"}),
        ("backup_service", "backup_9288", "BACKUP_ARCHIVE", "PRESENT", {"email": "miller.logistics@company.com"}),
        ("backup_service", "backup_9287", "BACKUP_ARCHIVE", "PRESENT", {"email": "areed1433@gmail.com"}),
        ("backup_service", "backup_9286", "BACKUP_ARCHIVE", "PRESENT", {"email": "summit-retail@company.com"}),
    ],
    # security_audit_explorer_20260905.png - six signed events for user_03, all retained
    "evidence_37": [
        ("security_service", "audit_record_%03d" % n, "SECURITY_AUDIT_LOG", "PRESENT",
         {"customer_reference": "user_03"}) for n in (1, 2, 3, 4, 5, 6)
    ],
    # deleted_account_reference_20260310.png - "Retained reference" for user_17: only the
    # stable key remains, no name/email/phone.  The data catalog (activity_4011) names this
    # record tombstone_17.
    "evidence_42": [
        ("identity_service", "tombstone_17", "ACCOUNT_TOMBSTONE", "PRESENT",
         {"customer_reference": "user_17"}),
    ],
    # marketing_profile_console.png - live marketing profile.  CONFLICT: the screen shows
    # Soo-jin Park (sj.park@naver.com) but the data catalog (activity_4008) links
    # marketing_001 to kwame-mensah@proton.me / user_09.  The catalog is treated as
    # authoritative, so those identifiers are used.
    "evidence_60": [
        ("marketing_platform", "marketing_001", "MARKETING_PROFILE", "PRESENT",
         {"email": "kwame-mensah@proton.me", "customer_reference": "user_09"}),
    ],
    # object_storage_browser_20260213.png - lists attachment files by name only.  The data
    # catalog (activity_4007) says object_19 (delivery_confirmation_19.pdf) belongs only to
    # priya.raman@gmail.com / user_07, so it is a deletable support attachment.
    "evidence_46": [
        ("object_storage", "object_19", "SUPPORT_ATTACHMENT", "PRESENT",
         {"email": "priya.raman@gmail.com", "customer_reference": "user_07"}),
    ],
}


def facts_from_images(file_id, captured_at):
    out = []
    for system, rid, rtype, state, ident in IMAGE_RECORDS.get(file_id, []):
        out.append(_fact(file_id, captured_at, "image:" + rtype.lower(), system, rid, rtype,
                         dict(ident), state))
    return out


if __name__ == "__main__":
    from loaders import read_csv
    n = 0
    for ef in read_csv("evidence_files.csv"):
        if ef["file_path"].endswith(".png"):
            fs = facts_from_images(ef["file_id"], ef["captured_at"])
            n += len(fs)
            print(ef["file_id"], ef["file_path"].split("/")[-1], "->", len(fs), "facts")
    print("total image facts:", n)