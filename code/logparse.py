"""Normalize every log line (8 shapes) into an event dict."""
import json
import re
from pathlib import Path

KV = re.compile(r'([A-Za-z_]+)=(?:"((?:[^"\\]|\\.)*)"|(\S+))')
TS = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+(.*)$')
BRACKET = re.compile(r'^\[(\w+)\] \[(\w+)\] (?:\[(\S+)\] )?(\w+): ?(.*)$')
PIPE = re.compile(r'^\| (\w+) \| (\w+) \| (\S+) \| (\w+) \| ?(.*)$')
SYSLOG = re.compile(r'^<\d+>1 \S+ (\S+) (\S+) - - (.*)$')


def _kv_clean(text):
    d = {}
    for k, q, v in KV.findall(text):
        d[k] = q if v == "" else v
    return d


def parse_line(line):
    line = line.rstrip("\n")
    m = TS.match(line)
    if not m:
        return None
    ts, rest = m.groups()
    ev = {"ts": ts, "service": None, "event": None, "trace_id": None, "level": None, "f": {}}
    if rest.startswith("{"):                                   # JSON lines
        j = json.loads(rest)
        ev.update(service=j.get("service"), event=j.get("event"),
                  trace_id=j.get("trace_id"), level=j.get("severity"))
        ev["f"] = {k: v for k, v in j.items() if v is not None}
    elif BRACKET.match(rest):                                  # [LVL] [svc] [trace] event: k=v
        lvl, svc, tr, event, body = BRACKET.match(rest).groups()
        ev.update(service=svc, event=event, trace_id=tr, level=lvl)
        ev["f"] = _kv_clean(body)
    elif PIPE.match(rest):                                     # LVL | svc | trace | event | k=v
        lvl, svc, tr, event, body = PIPE.match(rest).groups()
        ev.update(service=svc, event=event, trace_id=tr, level=lvl)
        ev["f"] = _kv_clean(body)
    elif SYSLOG.match(rest):                                   # <PRI>1 node svc trace - - k=v
        svc, tr, body = SYSLOG.match(rest).groups()
        f = _kv_clean(body)
        ev.update(service=svc, event=f.get("event"), trace_id=tr, level=f.get("level"))
        ev["f"] = f
    else:                                                      # key=value shapes
        if rest.startswith(("INFO ", "WARN ", "DEBUG ", "ERROR ")):
            rest = "level=" + rest
        f = _kv_clean(rest)
        if "message" in f:                                     # JSON-escaped nested message
            inner = f.pop("message").replace('\\"', '"')
            f.update(_kv_clean(inner))
            f["service"] = f.get("service") or f.get("function")
        ev.update(service=f.get("service"), event=f.get("event"),
                  trace_id=f.get("trace_id") or f.get("requestId"), level=f.get("level"))
        ev["f"] = f
    return ev


def parse_log(path):
    events = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = parse_line(line)
        if e is None:
            raise ValueError(f"unparsed line in {path}: {line[:120]}")
        if e["event"] is None:
            raise ValueError(f"no event in {path}: {line[:120]}")
        events.append(e)
    return events


if __name__ == "__main__":
    import collections
    from loaders import DATA
    tot = 0; ev = collections.Counter()
    for p in sorted((DATA / "evidence" / "logs").glob("*.log")):
        es = parse_log(p); tot += len(es)
        ev.update((e["service"], e["event"]) for e in es)
    print("events:", tot)
    for k, v in sorted(ev.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        if k[1] not in ("cache_lookup", "connection_acquired", "dependency_retry", "dependency_recovered"):
            print(v, k)