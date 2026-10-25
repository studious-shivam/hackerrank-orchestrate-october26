"""Load the CSV inputs and build lookup indexes."""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "dataset"


def read_csv(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Dataset:
    def __init__(self, requests_file="deletion_requests.csv"):
        self.requests = read_csv(requests_file)
        self.identities = read_csv("user_identities.csv")
        self.audit_log = read_csv("user_audit_log.csv")
        self.activity = read_csv("system_activity.csv")
        self.rules = read_csv("deletion_rules.csv")
        self.evidence_files = read_csv("evidence_files.csv")

        self.ident_by_user = {r["user_id"]: r for r in self.identities}
        self.audit_by_user = defaultdict(list)
        for r in self.audit_log:
            self.audit_by_user[r["user_id"]].append(r)
        self.rules_by_category = {r["data_category"]: r for r in self.rules}


if __name__ == "__main__":
    ds = Dataset()
    print("requests:", len(ds.requests))
    print("identities:", len(ds.identities))
    print("audit events:", len(ds.audit_log))
    print("activity rows:", len(ds.activity))
    print("rules:", len(ds.rules))
    print("evidence files:", len(ds.evidence_files))