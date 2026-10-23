# Exporting a run from the system you actually use

The scorer only needs one JSON line per ticket with ranked hits:

```json
{"ticket": "t07", "hits": [{"path": "notes/workshop.md", "lines": [14, 17], "page": null, "text": "...", "score": 4.2}]}
```

Rules that keep runs honest:

- Call the **same** search path the agent uses, with the **same** settings and filters. A run from a test index you built for the occasion measures that index, not the agent.
- Send the ticket's `ask` exactly as written. Do not rewrite it, unless query rewriting is part of the system; then rewrite the way the system does and log the rewritten text in the hit list as `"query"`.
- Ask for more hits than k (for example 20) so the scorer can tell **buried** from **lost**.
- Make `path` relative to the same root as the tickets. Normalise backslashes.
- One file per configuration in `runs/`, named after the change (`c0-baseline.jsonl`, `c3-hybrid.jsonl`). Never overwrite.

## Pattern 1: an MCP search tool, driven by the agent

When the only door to the index is an MCP tool, let the agent do the loop, but make it mechanical:

1. Read `tickets.practice.jsonl`.
2. For each ticket, call the search tool once with `ask` as the query and the largest result count the tool allows (up to 20).
3. Write one line per ticket to `runs/<name>.jsonl` with the tool's results mapped to `path`, `lines` or `page`, `text` and `score`. Copy values; do not judge relevance while exporting.
4. Do not retry a ticket because the result "looks wrong". A retry is a different system.

## Pattern 2: an HTTP search API (Elasticsearch-style or similar)

```python
import json, urllib.request

def search(q, size=20):
    body = json.dumps({"size": size, "query": {"match": {"content": q}}}).encode()
    req = urllib.request.Request("http://localhost:9200/notes/_search", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)["hits"]["hits"]

with open("tickets.practice.jsonl") as fh, open("runs/c0.jsonl", "w") as out:
    for line in fh:
        t = json.loads(line)
        hits = [{"path": h["_source"]["path"],
                 "lines": h["_source"].get("lines"),
                 "text": h["_source"].get("content", "")[:2000],
                 "score": h["_score"]} for h in search(t["ask"])]
        out.write(json.dumps({"ticket": t["id"], "hits": hits}, ensure_ascii=False) + "\n")
```

Replace the query body with whatever the agent sends (hybrid, filters, rerank block). Field names differ per index; map them, do not rename the index.

## Pattern 3: SQLite FTS5

```python
import json, sqlite3
db = sqlite3.connect("notes.db")
q = "\"E-217\""  # the query, quoted the way the agent quotes it
rows = db.execute("SELECT path, start_line, end_line, body, bm25(chunks) AS s "
                  "FROM chunks WHERE chunks MATCH ? ORDER BY s LIMIT 20", (q,)).fetchall()
hits = [{"path": p, "lines": [a, b], "text": body, "score": -s} for p, a, b, body, s in rows]
```

FTS5 query syntax treats some punctuation as operators. If the agent escapes or quotes the query, do the same here, and note it: unescaped codes like `E-217` are a classic **code mangled** cause.

## Pattern 4: a vector store client

Embed the `ask` with the **same** model and the same prefix or instruction string the agent uses (many embedders expect a "query:" style prefix; a missing prefix silently lowers scores). Store the chunk's source path and line range as metadata at index time; without them you can only pin tickets by quote.

## Pattern 5: agent memory recall

Treat each memory entry as a hit with `path` set to a stable entry id or `memory/<namespace>/<id>`, and `text` set to the entry body. Pin `newest-wins` tickets to the current entry; when an older entry ranks above it, the autopsy row is **old copy**.

## Pattern 6: no code access at all

Ask the questions in the product's own search box, and for each, write down the first 10 results (file name and section) in a sheet with one row per ticket. Convert the sheet to JSONL later, or score it by hand: hit@k is "is a pinned spot in the first k rows", RR is "1 / row number of the first pinned spot".
