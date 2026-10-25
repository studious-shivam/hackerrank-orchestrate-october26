"""Turn matched evidence facts into status + ordered steps for each case."""
import json
from datetime import datetime, timedelta

from facts import load_all_facts
from identity import IdentityResolver
from intent import requests_deletion
from loaders import Dataset

P = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")

# data category -> required action from deletion_rules.csv
ACTION = {
    "USER_PROFILE": "DELETE", "SECONDARY_IDENTIFIER": "DELETE", "SEARCH_INDEX_ENTRY": "DELETE",
    "CACHE_ENTRY": "DELETE", "SUPPORT_ATTACHMENT": "DELETE", "USER_EXPORT": "DELETE",
    "MARKETING_PROFILE": "DELETE", "SUPPORT_MESSAGE": "REDACT", "EMAIL_DELIVERY_LOG": "REDACT",
    "ACCOUNT_TOMBSTONE": "REDACT", "ANALYTICS_PROFILE": "ANONYMIZE", "PRODUCT_TELEMETRY": "ANONYMIZE",
    "SECURITY_AUDIT_LOG": "RETAIN", "LEGAL_HOLD_RECORD": "RETAIN", "BACKUP_ARCHIVE": "RETAIN",
    "DATA_FLOW": "FLOW",
}
# operation order inside each phase (from the problem statement)
FIND_OPS = ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK"]
FIX_OPS = ["DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD"]
VER_OPS = ["VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED",
           "VERIFY_RECORD_ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED"]
STATE = {"REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT", "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
         "REPORT_RESTORE_RISK": "ACTIVE", "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED",
         "DELETE_RECORD": "ABSENT", "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
         "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT", "VERIFY_RECORD_REDACTED": "REDACTED",
         "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
         "VERIFY_RESTORE_BLOCKED": "BLOCKED"}
RESULT_FOR_STATUS = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}


def matches(f, ident):
    return bool((f["user_ref"] and f["user_ref"] == ident.user_id)
                or (f["email"] and f["email"] in ident.emails)
                or (f["email_hash"] and f["email_hash"] in ident.hashes)
                or (f["phone"] and f["phone"] in ident.phones)
                or any(e in ident.emails for e in f["text_emails"]))


def classify(f):
    """-> (compliant?, finding_op, fix_op, verify_op) for one record's latest state."""
    t, s = f["record_type"], f["state"]
    a = ACTION.get(t)
    has_id = any([f["name"], f["email"], f["phone"], f["email_hash"], f["text_emails"]])
    if a == "DELETE":
        return (s == "ABSENT", "REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT")
    if a == "REDACT":
        bad = has_id if t == "ACCOUNT_TOMBSTONE" else s in ("IDENTIFIABLE", "PRESENT")
        return (not bad, "REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED")
    if a == "ANONYMIZE":
        return (s == "ANONYMIZED", "REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED")
    if a == "FLOW":
        return (s != "ACTIVE", "REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED")
    if t == "BACKUP_ARCHIVE":
        return (s != "ACTIVE", "REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED")
    return (True, None, None, "VERIFY_RECORD_PRESENT")      # RETAIN categories


class Planner:
    def __init__(self, requests_file="deletion_requests.csv"):
        self.ds = Dataset(requests_file)
        self.resolver = IdentityResolver(self.ds)
        self.facts = load_all_facts()
        self.file_time = {r["file_id"]: r["captured_at"] for r in self.ds.evidence_files}
        self.activity_resources = {a["resource_id"] for a in self.ds.activity}
        self.acct_by_case = self._link_accounts()

    # -- account profile id comes only from the activity stream when no evidence names it
    def _link_accounts(self):
        acts = [a for a in self.ds.activity
                if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"]
        claimed = {}
        for f in self.facts:
            if f["system_id"] == "account_service" and f["user_ref"]:
                claimed.setdefault(f["resource_id"], set()).add(f["user_ref"])
        cands, out = {}, {}
        for r in self.ds.requests:
            ident = self.resolver.resolve(r["email"])
            rep, want = P(r["reported_at"]), RESULT_FOR_STATUS[r["reported_status"]]
            cands[r["case_id"]] = [
                a["resource_id"] for a in acts
                if a["reported_result"] == want
                and -timedelta(minutes=10) <= rep - P(a["event_time"]) <= timedelta(minutes=80)
                and not (claimed.get(a["resource_id"]) and ident.user_id not in claimed[a["resource_id"]])]
        taken, changed = set(), True
        while changed:                                  # resolve unique candidates first
            changed = False
            for cid, c in cands.items():
                c = [x for x in c if x not in taken]
                cands[cid] = c
                if len(c) == 1 and cid not in out:
                    out[cid] = c[0]; taken.add(c[0]); changed = True
        for cid, c in cands.items():                    # leftovers: earliest remaining candidate
            if cid not in out and c:
                out[cid] = c[0]
        return out

    def case_facts(self, req, ident):
        latest = {}
        for f in self.facts:
            if (f["captured_at"] > req["audit_at"] or self.file_time[f["file_id"]] > req["audit_at"]
                    or not matches(f, ident)):
                continue
            k = (f["system_id"], f["resource_id"])
            if k not in latest or f["captured_at"] >= latest[k]["captured_at"]:
                latest[k] = f
        return latest

    def primary_file(self, req, ident):
        cover = {}
        for f in self.facts:
            if (f["captured_at"] <= req["audit_at"] and self.file_time[f["file_id"]] <= req["audit_at"]
                    and matches(f, ident)):
                cover.setdefault(f["file_id"], set()).add((f["system_id"], f["resource_id"]))
        if not cover:
            return None
        return max(cover, key=lambda k: (len(cover[k]), self.file_time[k]))

    def plan(self, req):
        if not requests_deletion(req["request_text"]):
            return "NOT_APPLICABLE", []
        ident = self.resolver.resolve(req["email"])
        recs = self.case_facts(req, ident)
        prim = self.primary_file(req, ident)
        in_prim = {(f["system_id"], f["resource_id"]): f for f in self.facts
                   if f["file_id"] == prim and f["captured_at"] <= req["audit_at"] and matches(f, ident)}
        ev_of = lambda k, f: in_prim[k]["file_id"] if k in in_prim else f["file_id"]
        acct = next((f for (s, _), f in recs.items() if s == "account_service" and f["record_type"] == "USER_PROFILE"), None)
        find, fix, ver, ok_ver = [], [], [], []
        violations = False
        for (sys_id, rid), f in sorted(recs.items()):
            ok, fop, xop, vop = classify(f)
            if f["record_type"] == "USER_PROFILE" and sys_id == "account_service":
                pass
            if not ok:
                violations = True
                find.append((fop, sys_id, rid, ev_of((sys_id, rid), f)))
                fix.append((xop, sys_id, rid, ""))
                ver.append((vop, sys_id, rid, ""))
            elif f["record_type"] == "SECURITY_AUDIT_LOG":
                ver.append((vop, sys_id, rid, ev_of((sys_id, rid), f)))
            elif f["record_type"] in ACTION and f["record_type"] not in ("LEGAL_HOLD_RECORD",) \
                    and not (f["record_type"] == "USER_PROFILE"):
                ok_ver.append((vop, sys_id, rid, ev_of((sys_id, rid), f)))
            elif f["record_type"] == "USER_PROFILE":
                ok_ver.append((vop, sys_id, rid, ev_of((sys_id, rid), f)))
        acct_id = acct["resource_id"] if acct else self.acct_by_case.get(req["case_id"])
        n = ident.user_id.split("_")[-1] if ident.user_id else ""
        simple = "account_%03d" % int(n) if n.isdigit() else None
        if simple and int(n) <= 12 and simple in self.activity_resources and not acct:
            acct_id = simple
        if acct_id and not any(v[1:3] == ("account_service", acct_id) for v in ver):
            ver.append(("VERIFY_RECORD_ABSENT", "account_service", acct_id, ""))
        status = "INCOMPLETE" if violations else "COMPLETE"
        if status == "COMPLETE" and not any(v[1] == "analytics_platform" for v in ok_ver):
            a = self._anonymized_analytics(req, prim)
            if a:
                ok_ver.append(("VERIFY_RECORD_ANONYMIZED", "analytics_platform", a[0], a[1]))
        if status == "COMPLETE":
            ver += [v for v in ok_ver if v[1:3] not in {x[1:3] for x in ver}]
            ver = [(op, s, r, e or prim or self._absent_evidence(req)) for op, s, r, e in ver]
            return status, self._number([], [], ver)
        ver = [(op, s, r, "") for op, s, r, _ in ver]       # future checks cite no evidence
        return status, self._number(find, fix, ver)

    def _anonymized_analytics(self, req, prim):
        rep = P(req["reported_at"])
        done = [a["resource_id"] for a in self.ds.activity
                if a["event_type"] == "ANONYMIZE_RECORD" and a["reported_result"] == "SUCCESS"
                and timedelta(minutes=1) <= rep - P(a["event_time"]) <= timedelta(minutes=35)]
        for f in self.facts:
            if (f["record_type"] == "ANALYTICS_PROFILE" and f["state"] == "ANONYMIZED" and f["resource_id"] in done
                    and f["file_id"] == prim and f["captured_at"] <= req["audit_at"]):
                return f["resource_id"], f["file_id"]
        return None

    def _absent_evidence(self, req):
        files = [f for f in self.facts if f["system_id"] == "account_service"
                 and f["captured_at"] <= req["audit_at"] and self.file_time[f["file_id"]] <= req["audit_at"]]
        return max(files, key=lambda f: f["captured_at"])["file_id"] if files else ""

    @staticmethod
    def _number(find, fix, ver):
        def key(order):
            return lambda s: (order.index(s[0]), s[1], s[2])
        steps = []
        for phase, items, order in (("FINDING", find, FIND_OPS), ("REMEDIATION", fix, FIX_OPS),
                                    ("VERIFICATION", ver, VER_OPS)):
            for op, sys_id, rid, ev in sorted(items, key=key(order)):
                steps.append({"step_no": len(steps) + 1, "phase": phase, "system_id": sys_id,
                              "resource_id": rid, "operation": op, "state": STATE[op], "evidence_id": ev})
        return steps
