"""Score predictions against a gold CSV:  python code/evaluation/main.py pred.csv gold.csv [--cases]"""
import csv
import json
import sys

FIELDS = ["phase", "system_id", "resource_id", "operation", "state", "evidence_id"]


def load(path):
    return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"]))
            for r in csv.DictReader(open(path, newline="", encoding="utf-8"))}


def tup(s):
    return tuple(s[k] for k in FIELDS)


def score(pred, gold):
    n = len(gold)
    status_ok = sum(pred.get(c, ("", []))[0] == g[0] for c, g in gold.items())
    tp = fp = fn = 0
    fld_ok = fld_tot = 0
    seq_ok = seq_noev_ok = 0
    per_case = {}
    for c, (gs, gsteps) in gold.items():
        ps, psteps = pred.get(c, ("", []))
        gset, pset = {tup(s) for s in gsteps}, {tup(s) for s in psteps}
        tp += len(gset & pset); fp += len(pset - gset); fn += len(gset - pset)
        gkey = {tup(s)[:4]: s for s in gsteps}
        for p in psteps:                      # field-level: steps that share (phase,system,resource,operation)
            g = gkey.get(tup(p)[:4])
            if g:
                for k in FIELDS:
                    fld_tot += 1; fld_ok += p[k] == g[k]
        seq_ok += [tup(s) for s in psteps] == [tup(s) for s in gsteps]
        noev = lambda ss: [tup(s)[:5] for s in ss]
        seq_noev_ok += noev(psteps) == noev(gsteps)
        per_case[c] = (ps == gs, sorted(gset - pset), sorted(pset - gset))
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"cases": n, "status_accuracy": status_ok / n, "step_precision": prec, "step_recall": rec,
            "step_f1": f1, "field_accuracy": fld_ok / fld_tot if fld_tot else 0.0,
            "sequence_accuracy_exact": seq_ok / n, "sequence_accuracy_ignoring_evidence_id": seq_noev_ok / n,
            "per_case": per_case}


if __name__ == "__main__":
    pred, gold = load(sys.argv[1]), load(sys.argv[2])
    r = score(pred, gold)
    for k, v in r.items():
        if k != "per_case":
            print(f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}")
    if "--cases" in sys.argv:
        for c, (ok, missing, extra) in r["per_case"].items():
            if not ok or missing or extra:
                print("\n", c, "status_ok" if ok else "STATUS WRONG")
                for m in missing[:8]: print("   MISSING", m)
                for e in extra[:8]: print("   EXTRA  ", e)
