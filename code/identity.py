"""Resolve every identifier (current + historical) belonging to a requester."""
import hashlib
from dataclasses import dataclass, field

from loaders import Dataset


def sha256_email(email):
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


@dataclass
class Identity:
    user_id: str = ""
    names: set = field(default_factory=set)
    emails: set = field(default_factory=set)      # lowercase
    phones: set = field(default_factory=set)
    hashes: set = field(default_factory=set)
    audit_ids: dict = field(default_factory=dict)  # value -> audit_id that revealed it
    resolved_via: str = ""                          # "current" | "historical" | "unknown"

    def all_identifiers(self):
        return self.emails | self.phones | self.hashes | self.names | {self.user_id}


class IdentityResolver:
    def __init__(self, ds: Dataset):
        self.ds = ds
        self.by_email = {r["email"].lower(): r["user_id"] for r in ds.identities}
        self.by_old_email = {}
        for a in ds.audit_log:
            if a["field_name"] == "email":
                self.by_old_email[a["old_value"].lower()] = a["user_id"]
                self.by_old_email.setdefault(a["new_value"].lower(), a["user_id"])

    def resolve(self, email):
        email = email.strip().lower()
        ident = Identity()
        if email in self.by_email:
            ident.user_id, ident.resolved_via = self.by_email[email], "current"
        elif email in self.by_old_email:
            ident.user_id, ident.resolved_via = self.by_old_email[email], "historical"
        else:
            ident.resolved_via = "unknown"
            ident.emails.add(email)
            ident.hashes.add(sha256_email(email))
            return ident

        row = self.ds.ident_by_user.get(ident.user_id)
        if row:
            ident.names.add(row["name"])
            ident.emails.add(row["email"].lower())
            ident.phones.add(row["phone"])
            ident.hashes.add(row["email_hash"])
        for a in self.ds.audit_by_user[ident.user_id]:
            for v in (a["old_value"], a["new_value"]):
                v = v.lower() if a["field_name"] == "email" else v
                {"email": ident.emails, "phone": ident.phones,
                 "email_hash": ident.hashes}[a["field_name"]].add(v)
                ident.audit_ids.setdefault(v, a["audit_id"])
        ident.emails.add(email)
        ident.hashes |= {sha256_email(e) for e in ident.emails}
        return ident


if __name__ == "__main__":
    ds = Dataset()
    res = IdentityResolver(ds)
    counts = {}
    for r in ds.requests:
        i = res.resolve(r["email"])
        counts[i.resolved_via] = counts.get(i.resolved_via, 0) + 1
    print("resolved:", counts)
    for case in ("case_33", "case_34"):
        r = next(x for x in ds.requests if x["case_id"] == case)
        i = res.resolve(r["email"])
        print(case, i.user_id, i.resolved_via, sorted(i.emails), sorted(i.phones))
    hist = next(r for r in ds.requests
                if res.resolve(r["email"]).resolved_via == "historical")
    i = res.resolve(hist["email"])
    print(hist["case_id"], i.user_id, "emails:", sorted(i.emails))