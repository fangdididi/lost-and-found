#!/usr/bin/env python3
"""laf.py - lost-and-found helper for measuring whether search finds things.

Standard library only. Subcommands:

  check    validate a tickets file against a corpus folder
  split    deterministically split tickets into practice / sealed halves
  bm25     build a plain keyword baseline run over a folder (line-window chunks)
  score    score a run against tickets (hit@k, recall@k, RR, nDCG@k, per tag)
  compare  question-by-question comparison of two runs (fixed / broken / same)

Tickets file (JSONL, one per line):
  {"id": "t01", "ask": "how long do refunds take",
   "where": [{"path": "policy/refunds.md", "lines": [12, 20]}],
   "tags": ["synonym"], "kind": "find"}
  kind "none" means the corpus does NOT contain the answer.
  A "where" entry needs "path" and may add "lines" [a, b], "page" n or "quote".

Run file (JSONL, one per ticket):
  {"ticket": "t01", "hits": [{"path": "...", "lines": [a, b], "page": n,
                               "text": "...", "score": 1.7}, ...]}
  Hits are in rank order. Only "path" is required.
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".py", ".js", ".ts", ".go",
            ".rs", ".java", ".c", ".h", ".cpp", ".rb", ".sh", ".yaml", ".yml",
            ".toml", ".json", ".jsonl", ".csv", ".log", ".html", ".sql", ".ini",
            ".cfg", ".org", ".tex"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
             "build", ".idea", ".vscode"}


# ---------------------------------------------------------------- io helpers
def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{n}: bad JSON ({exc.msg})")
    return rows


def norm_path(p):
    p = str(p).replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def squash(s):
    return re.sub(r"\s+", " ", str(s)).strip().lower()


# ---------------------------------------------------------------- tokenizer
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
WORD = re.compile(r"[A-Za-z0-9_]+(?:[-.][A-Za-z0-9_]+)*|[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]+")


def tokenize(text, keep_codes=True):
    """Lowercase word tokens; CJK runs become overlapping character bigrams.

    With keep_codes, a token like ERR-4021 or v2.3.1 is kept whole AND split,
    so both the exact code and its parts can match.
    """
    out = []
    for m in WORD.finditer(text):
        tok = m.group(0)
        if CJK.match(tok):
            if len(tok) == 1:
                out.append(tok)
            else:
                out.extend(tok[i:i + 2] for i in range(len(tok) - 1))
            continue
        low = tok.lower()
        parts = re.split(r"[-.]", low)
        if len(parts) > 1:
            if keep_codes:
                out.append(low)
            out.extend(p for p in parts if p)
        else:
            out.append(low)
    return out


# ---------------------------------------------------------------- corpus
def walk_corpus(root):
    """Yield (relpath, text) for readable text files; report skipped files."""
    skipped = []
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = norm_path(os.path.relpath(full, root))
            ext = os.path.splitext(name)[1].lower()
            if ext not in TEXT_EXT:
                skipped.append((rel, f"extension {ext or '(none)'} not read"))
                continue
            try:
                with open(full, encoding="utf-8") as fh:
                    files.append((rel, fh.read()))
            except UnicodeDecodeError:
                skipped.append((rel, "not UTF-8 text"))
            except OSError as exc:
                skipped.append((rel, f"unreadable ({exc.strerror})"))
    return files, skipped


def chunk_lines(text, size, overlap):
    """Split text into windows of `size` lines with `overlap` lines shared."""
    lines = text.splitlines()
    if not lines:
        return []
    step = max(1, size - overlap)
    chunks = []
    start = 0
    while start < len(lines):
        end = min(len(lines), start + size)
        chunks.append((start + 1, end, "\n".join(lines[start:end])))
        if end == len(lines):
            break
        start += step
    return chunks


def chunk_sections(text, size, overlap):
    """Line windows that never cross a markdown heading.

    Returns (start, end, body, heading_trail) so the heading trail can be
    indexed with the chunk even when the heading line itself is not inside it.
    """
    lines = text.splitlines()
    out = []
    trail = []
    sec_start = 0

    def flush(a, b):
        if b <= a:
            return
        body_lines = lines[a:b]
        step = max(1, size - overlap)
        s = 0
        while s < len(body_lines):
            e = min(len(body_lines), s + size)
            out.append((a + s + 1, a + e, "\n".join(body_lines[s:e]), " / ".join(t for _, t in trail)))
            if e == len(body_lines):
                break
            s += step

    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            flush(sec_start, i)
            level = len(m.group(1))
            trail = [(lv, t) for lv, t in trail if lv < level] + [(level, m.group(2).strip())]
            sec_start = i
    flush(sec_start, len(lines))
    return out


class BM25:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.k1, self.b = k1, b
        self.docs = docs  # list of (meta, tokens)
        self.tf = [Counter(toks) for _, toks in docs]
        self.len = [len(toks) for _, toks in docs]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 0.0
        df = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query_tokens, k):
        scores = []
        q = Counter(query_tokens)
        for i, tf in enumerate(self.tf):
            s = 0.0
            dl = self.len[i] or 1
            for t in q:
                f = tf.get(t)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avg or 1))
                s += self.idf[t] * f * (self.k1 + 1) / denom
            if s > 0:
                scores.append((s, i))
        scores.sort(key=lambda x: (-x[0], x[1]))
        return scores[:k]


def build_bm25_run(root, tickets, size=20, overlap=5, k=10, keep_codes=True,
                   headings=False):
    files, skipped = walk_corpus(root)
    docs = []
    for rel, text in files:
        if headings:
            for a, b, body, trail in chunk_sections(text, size, overlap):
                docs.append(((rel, a, b, body),
                             tokenize(rel + "\n" + trail + "\n" + body, keep_codes)))
        else:
            for a, b, body in chunk_lines(text, size, overlap):
                docs.append(((rel, a, b, body), tokenize(rel + "\n" + body, keep_codes)))
    index = BM25(docs)
    run = []
    for t in tickets:
        hits = []
        for score, i in index.search(tokenize(t.get("ask", ""), keep_codes), k):
            rel, a, b, body = docs[i][0]
            hits.append({"path": rel, "lines": [a, b], "score": round(score, 4),
                         "text": body})
        run.append({"ticket": t["id"], "hits": hits})
    return run, skipped, len(docs)


# ---------------------------------------------------------------- matching
def overlaps(a, b):
    return a[0] <= b[1] and b[0] <= a[1]


def hit_text(hit, root):
    if hit.get("text"):
        return hit["text"]
    if root and hit.get("lines"):
        full = os.path.join(root, norm_path(hit["path"]))
        try:
            with open(full, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except (OSError, UnicodeDecodeError):
            return ""
        a, b = hit["lines"]
        return "\n".join(lines[a - 1:b])
    return ""


def matches(hit, where, root=None):
    """Does one retrieved hit land on one gold location?"""
    if norm_path(hit.get("path", "")) != norm_path(where["path"]):
        return False
    if "page" in where and hit.get("page") is not None and hit["page"] != where["page"]:
        return False
    if "page" in where and hit.get("page") is None and "quote" not in where:
        return False
    if "lines" in where:
        if not hit.get("lines"):
            return False
        if not overlaps(tuple(hit["lines"]), tuple(where["lines"])):
            return False
    if "quote" in where:
        if squash(where["quote"]) not in squash(hit_text(hit, root)):
            return False
    return True


# ---------------------------------------------------------------- metrics
def score_ticket(ticket, hits, k, root=None):
    where = ticket.get("where", [])
    if ticket.get("kind", "find") == "none" or not where:
        top = hits[0] if hits else None
        return {"id": ticket["id"], "kind": "none", "top": top}
    found_at = []  # rank (1-based) of first hit per gold location, or None
    for w in where:
        r = None
        for rank, h in enumerate(hits, 1):
            if matches(h, w, root):
                r = rank
                break
        found_at.append(r)
    in_k = [r for r in found_at if r is not None and r <= k]
    first = min([r for r in found_at if r is not None], default=None)
    rr = (1.0 / first) if first is not None and first <= k else 0.0
    dcg = 0.0
    seen = set()
    for rank, h in enumerate(hits[:k], 1):
        for wi, w in enumerate(where):
            if wi not in seen and matches(h, w, root):
                seen.add(wi)
                dcg += 1.0 / math.log2(rank + 1)
                break
    ideal = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(where), k) + 1))
    if first is None:
        status = "lost"
    elif first <= k:
        status = "found"
    else:
        status = "buried"
    return {"id": ticket["id"], "kind": "find", "status": status,
            "first_rank": first, "hit": 1.0 if in_k else 0.0,
            "recall": len(in_k) / len(where), "rr": rr,
            "ndcg": dcg / ideal if ideal else 0.0,
            "tags": ticket.get("tags", [])}


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def score_run(tickets, run, k=5, root=None):
    by_id = {r["ticket"]: r.get("hits", []) for r in run}
    rows = []
    missing = []
    for t in tickets:
        if t["id"] not in by_id:
            missing.append(t["id"])
        rows.append(score_ticket(t, by_id.get(t["id"], []), k, root))
    finds = [r for r in rows if r["kind"] == "find"]
    summary = {
        "k": k, "find_tickets": len(finds),
        "none_tickets": len(rows) - len(finds),
        "hit@k": mean(r["hit"] for r in finds),
        "recall@k": mean(r["recall"] for r in finds),
        "mrr@k": mean(r["rr"] for r in finds),
        "ndcg@k": mean(r["ndcg"] for r in finds),
        "found": sum(r["status"] == "found" for r in finds),
        "buried": sum(r["status"] == "buried" for r in finds),
        "lost": sum(r["status"] == "lost" for r in finds),
        "missing_from_run": missing,
    }
    tags = defaultdict(list)
    for r in finds:
        for tg in r["tags"] or ["(untagged)"]:
            tags[tg].append(r)
    per_tag = {tg: {"n": len(rs), "hit@k": mean(x["hit"] for x in rs),
                    "mrr@k": mean(x["rr"] for x in rs)}
               for tg, rs in sorted(tags.items())}
    return summary, per_tag, rows


def thin_note(n):
    if n < 20:
        return "THIN SET: under 20 find-tickets; one ticket moves hit@k by 5+ points. Read tickets, not decimals."
    if n < 50:
        return "SMALL SET: under 50 find-tickets; treat differences under ~2 tickets as noise."
    return ""


# ---------------------------------------------------------------- compare
def compare_runs(tickets, run_a, run_b, k=5, root=None):
    _, _, ra = score_run(tickets, run_a, k, root)
    _, _, rb = score_run(tickets, run_b, k, root)
    out = {"fixed": [], "broken": [], "rose": [], "fell": [], "same": []}
    for a, b in zip(ra, rb):
        if a["kind"] != "find":
            continue
        if not a["hit"] and b["hit"]:
            out["fixed"].append(a["id"])
        elif a["hit"] and not b["hit"]:
            out["broken"].append(a["id"])
        elif b["rr"] > a["rr"]:
            out["rose"].append(a["id"])
        elif b["rr"] < a["rr"]:
            out["fell"].append(a["id"])
        else:
            out["same"].append(a["id"])
    return out


def sign_test_p(wins, losses):
    """Two-sided exact sign test p-value, ties dropped."""
    n = wins + losses
    if n == 0:
        return 1.0
    m = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(m + 1)) / 2 ** n
    return min(1.0, 2 * tail)


# ---------------------------------------------------------------- check / split
def check_tickets(tickets, root=None):
    problems = []
    seen = set()
    asks = set()
    for t in tickets:
        tid = t.get("id")
        if not tid:
            problems.append(("?", "ticket without id"))
            continue
        if tid in seen:
            problems.append((tid, "duplicate id"))
        seen.add(tid)
        ask = squash(t.get("ask", ""))
        if not ask:
            problems.append((tid, "empty ask"))
        elif ask in asks:
            problems.append((tid, "same ask as an earlier ticket"))
        asks.add(ask)
        kind = t.get("kind", "find")
        if kind not in ("find", "none"):
            problems.append((tid, f"unknown kind {kind!r}"))
        if kind == "find" and not t.get("where"):
            problems.append((tid, "kind find but no where"))
        if kind == "none" and t.get("where"):
            problems.append((tid, "kind none but has where"))
        for w in t.get("where", []):
            if "path" not in w:
                problems.append((tid, "where entry without path"))
                continue
            if not root:
                continue
            full = os.path.join(root, norm_path(w["path"]))
            if not os.path.exists(full):
                problems.append((tid, f"path not in corpus: {w['path']}"))
                continue
            try:
                with open(full, encoding="utf-8") as fh:
                    text = fh.read()
            except (UnicodeDecodeError, OSError):
                continue  # binary (e.g. PDF): cannot verify quote/lines here
            lines = text.splitlines()
            if "lines" in w:
                a, b = w["lines"]
                if a < 1 or b < a or b > len(lines):
                    problems.append((tid, f"lines {a}-{b} outside file ({len(lines)} lines)"))
            if "quote" in w:
                if squash(w["quote"]) not in squash(text):
                    problems.append((tid, f"quote not found in {w['path']}"))
                elif "lines" in w:
                    a, b = w["lines"]
                    if squash(w["quote"]) not in squash("\n".join(lines[a - 1:b])):
                        problems.append((tid, "quote is in file but not inside the given lines"))
    return problems


def split_tickets(tickets, salt="lost-and-found"):
    practice, sealed = [], []
    for t in tickets:
        h = hashlib.sha256((salt + ":" + t["id"]).encode()).hexdigest()
        (sealed if int(h[:8], 16) % 2 else practice).append(t)
    return practice, sealed


# ---------------------------------------------------------------- cli
def write_jsonl(rows, path):
    fh = open(path, "w", encoding="utf-8") if path != "-" else sys.stdout
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    if fh is not sys.stdout:
        fh.close()


def pct(x):
    return f"{100 * x:5.1f}%"


def cmd_check(a):
    tickets = read_jsonl(a.tickets)
    probs = check_tickets(tickets, a.root)
    finds = sum(t.get("kind", "find") == "find" for t in tickets)
    print(f"{len(tickets)} tickets ({finds} find, {len(tickets) - finds} none)")
    tags = Counter(tg for t in tickets for tg in t.get("tags", []))
    if tags:
        print("tags: " + ", ".join(f"{k}={v}" for k, v in tags.most_common()))
    if a.root:
        files, skipped = walk_corpus(a.root)
        print(f"corpus: {len(files)} text files read, {len(skipped)} skipped")
        for rel, why in skipped[:20]:
            print(f"  skipped {rel}: {why}")
    if not probs:
        print("OK: no problems found")
        return 0
    for tid, msg in probs:
        print(f"PROBLEM {tid}: {msg}")
    return 1


def cmd_split(a):
    tickets = read_jsonl(a.tickets)
    p, s = split_tickets(tickets, a.salt)
    write_jsonl(p, a.practice)
    write_jsonl(s, a.sealed)
    print(f"practice {len(p)} -> {a.practice}; sealed {len(s)} -> {a.sealed}")
    return 0


def cmd_bm25(a):
    tickets = read_jsonl(a.tickets)
    run, skipped, n = build_bm25_run(a.root, tickets, a.chunk, a.overlap, a.depth,
                                     not a.split_codes, a.headings)
    write_jsonl(run, a.out)
    mode = "heading-aware" if a.headings else "plain"
    print(f"indexed {n} {mode} chunks ({a.chunk} lines, {a.overlap} overlap); "
          f"{len(skipped)} files skipped; run -> {a.out}", file=sys.stderr)
    return 0


def cmd_score(a):
    tickets = read_jsonl(a.tickets)
    run = read_jsonl(a.run)
    s, per_tag, rows = score_run(tickets, run, a.k, a.root)
    if a.json:
        print(json.dumps({"summary": s, "per_tag": per_tag, "tickets": rows},
                         ensure_ascii=False, indent=2, default=str))
        return 0
    k = s["k"]
    print(f"find-tickets {s['find_tickets']}, none-tickets {s['none_tickets']}, k={k}")
    print(f"hit@{k} {pct(s['hit@k'])}  recall@{k} {pct(s['recall@k'])}  "
          f"MRR@{k} {s['mrr@k']:.3f}  nDCG@{k} {s['ndcg@k']:.3f}")
    print(f"found {s['found']}  buried(below k) {s['buried']}  lost {s['lost']}")
    note = thin_note(s["find_tickets"])
    if note:
        print(note)
    if s["missing_from_run"]:
        print("not in run (scored as lost): " + ", ".join(s["missing_from_run"]))
    print("\nby tag:")
    for tg, v in per_tag.items():
        print(f"  {tg:<18} n={v['n']:<3} hit@{k} {pct(v['hit@k'])}  MRR {v['mrr@k']:.3f}")
    print("\nnot found in top k:")
    for r in rows:
        if r["kind"] == "find" and r["status"] != "found":
            where = r["first_rank"] if r["first_rank"] else "-"
            print(f"  {r['id']:<8} {r['status']:<7} first rank {where}  tags {','.join(r['tags'])}")
    nones = [r for r in rows if r["kind"] == "none"]
    if nones:
        print("\nnone-tickets (should find nothing; review the top hit):")
        for r in nones:
            top = r["top"]
            if top:
                sc = top.get("score")
                print(f"  {r['id']:<8} top {top['path']}" + (f" score {sc}" if sc is not None else ""))
            else:
                print(f"  {r['id']:<8} returned nothing (good)")
    return 0


def cmd_compare(a):
    tickets = read_jsonl(a.tickets)
    ra, rb = read_jsonl(a.before), read_jsonl(a.after)
    sa, _, _ = score_run(tickets, ra, a.k, a.root)
    sb, _, _ = score_run(tickets, rb, a.k, a.root)
    c = compare_runs(tickets, ra, rb, a.k, a.root)
    k = a.k
    print(f"hit@{k}: {pct(sa['hit@k'])} -> {pct(sb['hit@k'])}   "
          f"MRR@{k}: {sa['mrr@k']:.3f} -> {sb['mrr@k']:.3f}")
    for key in ("fixed", "broken", "rose", "fell"):
        ids = c[key]
        print(f"{key:<7} {len(ids):<3} {' '.join(ids)}")
    print(f"same    {len(c['same'])}")
    wins = len(c["fixed"]) + len(c["rose"])
    losses = len(c["broken"]) + len(c["fell"])
    p = sign_test_p(wins, losses)
    print(f"tickets better {wins}, worse {losses}, sign-test p={p:.3f}")
    if c["broken"]:
        print("READ EVERY BROKEN TICKET before keeping this change.")
    if p > 0.2 and wins + losses > 0:
        print("Difference could easily be chance on this set; confirm on the sealed half.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="validate tickets (and corpus coverage)")
    p.add_argument("tickets")
    p.add_argument("--root", help="corpus folder to verify paths, lines and quotes")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("split", help="practice / sealed split")
    p.add_argument("tickets")
    p.add_argument("--practice", default="tickets.practice.jsonl")
    p.add_argument("--sealed", default="tickets.sealed.jsonl")
    p.add_argument("--salt", default="lost-and-found")
    p.set_defaults(fn=cmd_split)

    p = sub.add_parser("bm25", help="plain keyword baseline run")
    p.add_argument("tickets")
    p.add_argument("--root", required=True)
    p.add_argument("--chunk", type=int, default=20, help="lines per chunk")
    p.add_argument("--overlap", type=int, default=5)
    p.add_argument("--depth", type=int, default=10, help="hits kept per ticket")
    p.add_argument("--split-codes", action="store_true",
                   help="do NOT keep codes like ERR-4021 as whole tokens")
    p.add_argument("--headings", action="store_true",
                   help="never cross a markdown heading; index the heading trail with each chunk")
    p.add_argument("--out", default="-")
    p.set_defaults(fn=cmd_bm25)

    p = sub.add_parser("score", help="score a run")
    p.add_argument("tickets")
    p.add_argument("run")
    p.add_argument("-k", type=int, default=5, help="how many hits the agent really reads")
    p.add_argument("--root", help="corpus folder, used to read hit text for quote matching")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("compare", help="ticket-by-ticket before/after")
    p.add_argument("tickets")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("-k", type=int, default=5)
    p.add_argument("--root")
    p.set_defaults(fn=cmd_compare)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
