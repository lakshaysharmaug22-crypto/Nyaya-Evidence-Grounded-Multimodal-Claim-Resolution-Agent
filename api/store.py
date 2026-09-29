"""SQLite persistence and full-text search (FTS5) for runs, human decisions, handoffs and replies."""
import json
import sqlite3
import threading
import time

FILTERS = {"decision": "decision", "rule": "rule", "lane": "lane", "type": "claim_type", "kind": "kind",
           "customer": "customer_id", "order": "order_id"}
HIT, END = "\x01", "\x02"          # snippet markers; the UI splits on these (no HTML is ever produced)


def _clean(q: str) -> str:
    return "".join(ch if ch.isprintable() or ch.isspace() else " " for ch in q)[:200]


def parse_query(q: str) -> tuple[list[str], dict[str, str]]:
    free, filt = [], {}
    for tok in _clean(q).split():
        key, _, val = tok.partition(":")
        if val and key.lower() in FILTERS:
            filt[FILTERS[key.lower()]] = val
        else:
            free.append(tok)
    return free, filt


def _q(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


class Store:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.conn.execute("create table if not exists events (kind text, ts real, body text)")
            self.conn.execute(
                "create virtual table if not exists docs using fts5("
                "kind, ref, id, order_id, customer_id, text, decision, rule, lane, claim_type, ts unindexed, "
                "tokenize='unicode61 remove_diacritics 2')")
            self.conn.commit()

    # --- events (source of truth, reloaded on startup)
    def save(self, kind: str, obj: dict):
        with self.lock:
            self.conn.execute("insert into events values (?, ?, ?)", (kind, obj.get("ts", time.time()), json.dumps(obj)))
            self.conn.commit()

    def load(self, kind: str) -> list[dict]:
        with self.lock:
            rows = self.conn.execute("select body from events where kind=? order by ts", (kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    # --- search index
    def index(self, kind: str, ref: str, **f):
        with self.lock:
            if kind == "claim":                                    # a re-run replaces the earlier entry
                self.conn.execute("delete from docs where kind='claim' and ref=?", (ref,))
            self.conn.execute(
                "insert into docs (kind, ref, id, order_id, customer_id, text, decision, rule, lane, claim_type, ts) "
                "values (?,?,?,?,?,?,?,?,?,?,?)",
                (kind, ref, f.get("id", ref), f.get("order_id") or "", f.get("customer_id") or "", f.get("text") or "",
                 f.get("decision") or "", f.get("rule") or "", f.get("lane") or "", f.get("claim_type") or "", f.get("ts", time.time())))
            self.conn.commit()

    def search(self, q: str, limit: int = 20) -> list[dict]:
        free, filt = parse_query(q.strip())
        parts = [_q(t) + "*" for t in free] + [f"{col} : {_q(v)}" for col, v in filt.items()]
        cols = "kind, ref, id, order_id, decision, rule, lane, claim_type, ts, snippet(docs, 5, char(1), char(2), '…', 14)"
        try:
            with self.lock:
                if parts:
                    sql = f"select {cols} from docs where docs match ? order by bm25(docs) limit ?"
                    rows = self.conn.execute(sql, (" AND ".join(parts), limit * 3)).fetchall()
                else:
                    rows = self.conn.execute(f"select {cols} from docs order by ts desc limit ?", (limit * 3,)).fetchall()
        except sqlite3.OperationalError:            # a query FTS cannot parse must never become a server error
            return []
        hits = [dict(zip(["kind", "ref", "id", "order_id", "decision", "rule", "lane", "claim_type", "ts", "snippet"], r)) for r in rows]
        exact = _clean(q).strip().lower()
        hits.sort(key=lambda h: (h["id"].lower() != exact and h["order_id"].lower() != exact))   # exact id / order first
        return hits[:limit]
