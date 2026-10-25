"""Three+ custom evaluation cases written by us (not from the dataset).  Run:  python code/evaluation/custom_cases.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from intent import requests_deletion
from planner import Planner

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def non_deletion_requests_are_not_applicable():
    """C1: access / correction / marketing opt-out must never authorise deletion."""
    texts = ["Please remove me from marketing lists only.",
             "Can you correct my surname without removing any of my records?",
             "Send me a copy of my data. This is an information request, not a request to erase it."]
    return not any(requests_deletion(t) for t in texts)


@case
def multilingual_deletion_requests_are_detected():
    """C2: deletion requests in German / Spanish / Japanese / Korean."""
    texts = ["Bitte löschen Sie mein Konto dauerhaft.", "Solicito la eliminación permanente de mi cuenta.",
             "アカウントの削除を依頼します。", "계정의 영구 삭제를 요청합니다."]
    return all(requests_deletion(t) for t in texts)


@case
def steps_follow_phase_and_operation_order():
    """C3: findings -> remediation -> verification; ops in table order; numbering consecutive."""
    steps = Planner._number(
        [("REPORT_ACTIVE_DATA_FLOW", "integration_service", "data_flow_2", "e1"),
         ("REPORT_REMAINING_RECORD", "search_service", "search_9", "e1"),
         ("REPORT_REMAINING_RECORD", "search_service", "search_1", "e1")],
        [("DELETE_RECORD", "search_service", "search_1", ""), ("DISABLE_DATA_FLOW", "integration_service", "data_flow_2", "")],
        [("VERIFY_RECORD_ABSENT", "search_service", "search_1", ""), ("VERIFY_DATA_FLOW_DISABLED", "integration_service", "data_flow_2", "")])
    ops = [s["operation"] for s in steps]
    return (ops[:3] == ["REPORT_REMAINING_RECORD", "REPORT_REMAINING_RECORD", "REPORT_ACTIVE_DATA_FLOW"]
            and steps[0]["resource_id"] == "search_1" and ops[3] == "DISABLE_DATA_FLOW"
            and [s["step_no"] for s in steps] == list(range(1, 8)))


@case
def historical_email_resolves_to_same_user():
    """C4: a request that uses an OLD email must resolve to the same user as the current email."""
    pl = Planner()
    for a in pl.ds.audit_log:
        if a["field_name"] == "email":
            cur = pl.ds.ident_by_user.get(a["user_id"])
            if cur and a["old_value"].lower() != cur["email"].lower():
                old = pl.resolver.resolve(a["old_value"])
                return old.user_id == a["user_id"] and cur["email"].lower() in old.emails
    return False


@case
def tombstone_with_direct_identifiers_is_exposed_pii():
    """C5: a tombstone that keeps name/email/hash violates rule_15; one with only user_id is compliant."""
    from planner import classify
    base = {"record_type": "ACCOUNT_TOMBSTONE", "state": "PRESENT", "name": None, "email": None,
            "phone": None, "email_hash": None, "text_emails": []}
    ok_clean = classify(dict(base))[0]
    ok_dirty = classify(dict(base, email_hash="ab" * 32))[0]
    return ok_clean and not ok_dirty


if __name__ == "__main__":
    res = [(fn.__name__, fn.__doc__, bool(fn())) for fn in CASES]
    for n, d, ok in res:
        print("PASS" if ok else "FAIL", n, "-", d)
    print(f"{sum(o for _, _, o in res)}/{len(res)} custom cases passed")
