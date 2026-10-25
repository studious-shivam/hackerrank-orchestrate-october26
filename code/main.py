"""Run the audit agent:  python code/main.py [requests_csv] [output_csv]"""
import csv
import json
import sys
from pathlib import Path

from planner import Planner

ROOT = Path(__file__).resolve().parent.parent


def run(requests_file="deletion_requests.csv", out_path=None):
    pl = Planner(requests_file)
    rows = []
    for req in sorted(pl.ds.requests, key=lambda r: r["case_id"]):
        status, steps = pl.plan(req)
        rows.append({"case_id": req["case_id"], "deletion_status": status,
                     "steps_json": json.dumps(steps, ensure_ascii=False, separators=(",", ":"))})
    out_path = Path(out_path or ROOT / "output.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
        w.writeheader()
        w.writerows(rows)
    return rows


if __name__ == "__main__":
    a = sys.argv[1:]
    rows = run(*(a[:2]))
    print("wrote", len(rows), "rows")
