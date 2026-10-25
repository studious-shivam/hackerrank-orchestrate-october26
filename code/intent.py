"""Decide whether request_text actually authorizes deletion (deterministic, multilingual)."""
import re

DELETE = re.compile(
    r"delet|erase|erasure|account[- ]deletion|permanent(ly)? (account )?(removal|closure)|"
    r"remove my account|close (my|this) account|"
    r"suppression|supprim|eliminaci|elimin|borrar|borra |exclus[aã]o|exclu[ií]r|\bremov|\bclosed?\b|\bwipe|\bpurge|profile is gone|account (still )?exists|"
    r"삭제|削除|删除|刪除|löschung|löschen|eliminare|cancellazione", re.I)
NEGATED = re.compile(r"do not (close|delete)|don't (close|delete)|keep the account|leave (my|the) (account|profile)|"
                     r"marketing lists only|promotional emails|"
                     r"not a request to (erase|delete)|information request|without removing|don't delete", re.I)


def requests_deletion(text: str) -> bool:
    return bool(DELETE.search(text)) and not NEGATED.search(text)


if __name__ == "__main__":
    from loaders import Dataset
    ds = Dataset()
    bad = [r["case_id"] for r in ds.requests if not requests_deletion(r["request_text"])]
    print(len(bad), "non-deletion:", bad)
