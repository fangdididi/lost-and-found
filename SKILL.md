---
name: lost-and-found
description: Measure and improve whether an agent's search, RAG or memory over your own files actually finds the right passage. Write claim tickets (real questions plus the exact spot that answers them), count what is really on the shelf, score the current setup at the depth the agent actually reads (hit@k, recall@k, MRR, nDCG), autopsy every miss with a nine-way chart, change one thing at a time on a practice half, confirm on a sealed half, and finish with a trust note the agent can follow. Use when someone says "my agent can't find things in our docs", "is hybrid better than keyword for us", "did the new chunking help", "RAG keeps citing the wrong file", or "test my local search / memory".
---

# Lost and Found

**Find out what your agent's search can and cannot find in your own material, fix it one change at a time, and leave behind a short, honest note of where it can be trusted.**

## What this is

Agents now search before they answer: a local index over a code base, a RAG pipeline over company docs, a vector store over meeting notes, a memory namespace that remembers past decisions. When the answer is wrong, people usually blame the model, swap the embedder, or bump `top_k` to 50 and hope. Nobody checks the simpler question first: **for the things we actually ask, does the right passage come back near the top?**

This skill turns that question into a small, repeatable measurement on *your* corpus, not a public benchmark:

1. A **scope note** that says which search is under test and how many hits the agent really reads.
2. **Claim tickets**: real questions, each pinned to the exact place in your files that answers it, plus a few questions the corpus cannot answer.
3. A **shelf count**: what exists versus what was actually indexed, before any query is run.
4. **Baseline runs** scored at the real reading depth, compared with a plain keyword yardstick.
5. A **miss autopsy** for every ticket that did not come back, using a nine-way chart of causes, each with a one-minute probe.
6. A **change log** where each change is a single hypothesis, judged ticket by ticket on a practice half and confirmed once on a sealed half.
7. A **trust note**: what the agent can find, what it cannot yet find, and what it must never rely on search for.

The helper `scripts/laf.py` (Python standard library only) validates tickets, splits them, builds a keyword baseline over a folder, scores any run file and compares two runs ticket by ticket. The method also works with no shell at all: a spreadsheet and patience are enough.

## When to use

- "The agent says it can't find X, but X is right there in the docs."
- "RAG answers cite the wrong file / an old version / a different product."
- Choosing between keyword, vector and hybrid search, a reranker, or chunk settings, **for this corpus**.
- Proving that a change (new embedder, new chunker, new PDF parser, query rewriting) actually helped, and did not quietly break something else.
- Checking an agent memory store: does it recall the newest decision, or an outdated one?
- Before letting an agent answer customers, auditors or teammates from internal material.

**Not for:** judging answer wording or tone (that is a generation check), web search quality, or public leaderboard benchmarking. If retrieval is already measured and solid, the problem is downstream; say so and stop.

## Working folder

Keep everything in one folder inside the project so it can be rerun later:

```
.lost-and-found/
  scope.md          # step 1
  tickets.jsonl     # step 2 (all tickets)
  tickets.practice.jsonl / tickets.sealed.jsonl
  shelf.md          # step 3
  runs/             # one JSONL per configuration, never overwritten
  autopsy.md        # step 5
  changes.md        # step 6
  trust-note.md     # step 7
```

Never put secrets, customer personal data or credentials into tickets. Use a safe paraphrase of the question and point at the location.

## Step 1 - Scope note

Write five lines before touching anything:

- **System under test**: the exact search path the agent uses (MCP tool name, API endpoint, library call, index name, memory namespace), with its current settings (mode, chunk size, embedder, filters, reranker).
- **Corpus**: which folders, file types and date range should be searchable. Name what is deliberately excluded.
- **Reading depth k**: how many results the agent actually puts in its context. If it takes 5, score at 5. Scoring at 10 when the agent reads 3 flatters the system.
- **Unit of answer**: does a hit mean "the right file" (navigation), "the right section" (most RAG), or "the right line / page" (citations)? Pick one; it decides how tickets are pinned.
- **What a miss costs**: wrong answer to a customer, wasted tokens, or the agent giving up. This sets how strict the end note must be.

## Step 2 - Claim tickets

A ticket is one question plus the place(s) in the corpus that answer it.

```json
{"id": "t07", "ask": "Do customers get a courtesy bike while theirs is repaired?",
 "where": [{"path": "notes/workshop.md", "quote": "free loan bike"}],
 "tags": ["synonym"], "kind": "find"}
```

**Where questions come from, best first**

1. Questions the agent (or people) really asked: chat logs, agent transcripts where it called search, support tickets, "where is..." messages.
2. Things you had to dig up yourself last month.
3. Questions written by someone who knows the domain but did **not** just read the file.
4. Model-generated questions, only after a human rewrites them. Generated questions copy the document's own words and make keyword search look perfect.

**Pin by location, not by chunk id.** Chunk ids change every time you change chunking, so tickets pinned to chunk ids die after the first experiment. Pin with `path` plus one of `lines` `[a, b]`, `page` n, or a short `quote` that must appear in the retrieved text. A quote of 3 to 8 distinctive words is the most robust pin.

**Pin every spot that answers.** If the answer lives in two files, list both. A missing second location punishes a system for finding a valid answer.

**Mix on purpose.** Tag each ticket with what makes it hard, and cover at least these:

| Tag | Example shape |
|---|---|
| `direct` | uses the document's own words |
| `synonym` / `paraphrase` | user words differ from document words ("courtesy bike" vs "loan bike") |
| `exact-code` | error codes, SKUs, function names, ticket numbers, versions |
| `two-places` | answer needs two passages |
| `file-type` (`pdf`, `log`, `csv`, `code`, `slides`) | answer lives in a non-markdown file |
| `newest-wins` | an older note says something different; only the latest is right |
| language tags (`chinese`, ...) | question or document in another language or mixed |
| `none` | the corpus does not contain the answer |

Aim for 30 to 60 find-tickets and 3 to 6 none-tickets. Fewer than 20 is a smoke test: report tickets, not percentages. Run the checker:

```bash
python3 scripts/laf.py check .lost-and-found/tickets.jsonl --root path/to/corpus
```

It catches duplicate ids, repeated questions, paths that do not exist, line ranges outside the file and quotes that are not where the ticket says they are. Fix every problem before measuring; a broken ticket looks exactly like a search miss.

**Split once, then seal.**

```bash
python3 scripts/laf.py split .lost-and-found/tickets.jsonl \
  --practice .lost-and-found/tickets.practice.jsonl --sealed .lost-and-found/tickets.sealed.jsonl
```

The split is a stable hash of ticket ids. Tune only on the practice half. Do not open the sealed half's per-ticket results until the final confirmation in step 6.

## Step 3 - Shelf count

Before running a single query, compare what exists with what was indexed. Many "search failures" are files that were never on the shelf.

- List files by type in the corpus folder and in the index (document counts per path or type, from the system's stats, admin API or a `match_all` style dump).
- Check **text layer**: scanned PDFs and images have no text unless OCR ran. Open three PDFs in the index and look at the extracted text.
- Check **ignore rules and size caps**: `.gitignore`, hidden folders, max file size, max pages, binary detection, unsupported extensions.
- Check **freshness**: the index build or last-update time against the newest file modification times. Note any watcher or reindex job.
- For **memory stores**: count entries, duplicates, and entries that contradict each other on the same subject.

`laf.py check --root` prints which files a plain text reader skipped and why; use it as a first pass, then confirm against the real index. Write `shelf.md` as a short table: type, files on disk, files indexed, gap, reason.

## Step 4 - Baseline runs

**Export a run from the real system.** For each ticket, call the exact search path from step 1 with the ticket's `ask` and save the ranked hits:

```json
{"ticket": "t07", "hits": [{"path": "notes/workshop.md", "lines": [14, 17], "score": 4.2, "text": "..."}]}
```

Only `path` is required; add `lines`, `page` and `text` when the system returns them, so line and quote pins can be checked. If hits carry no text but do carry line ranges, pass `--root` and the scorer reads the lines from disk. Save each configuration as its own file in `runs/` and never overwrite one. See `references/exporting-runs.md` for patterns (MCP tool loop, HTTP search API, SQLite FTS, vector-store client, memory recall).

If the system has modes (keyword, vector, hybrid), export one run per mode. Same tickets, same k, nothing else changed.

**Add a keyword yardstick.** A plain BM25 run over the same folder tells you whether the fancy setup beats the simplest thing:

```bash
python3 scripts/laf.py bm25 .lost-and-found/tickets.practice.jsonl --root path/to/corpus \
  --chunk 20 --overlap 5 --out .lost-and-found/runs/yardstick.jsonl
```

It reads text files only, splits Chinese, Japanese and Korean runs into character pairs, and keeps codes like `E-217` whole as well as split. `--headings` keeps chunks inside markdown sections and indexes the heading trail with each chunk.

**Score at the real depth.**

```bash
python3 scripts/laf.py score .lost-and-found/tickets.practice.jsonl \
  .lost-and-found/runs/current.jsonl -k 5 --root path/to/corpus
```

| Number | Question it answers |
|---|---|
| hit@k | Did at least one answering spot reach the agent? This is the headline. |
| recall@k | Of all answering spots, how many reached it? Matters for `two-places` tickets. |
| MRR@k | How high was the first good hit? Matters when the agent trusts the top result. |
| nDCG@k | Order quality when several spots answer. |
| found / buried / lost | In top k / retrieved but below k / not retrieved at all. Buried and lost need different fixes. |

Read the per-tag table and the list of misses before the averages. A setup with 85% overall and 0% on `exact-code` is a setup that will fail on every error message.

For none-tickets, the scorer shows the top hit. If it is a confident, unrelated passage, the agent will likely answer from it. Note it; the fix is usually an answer rule ("say not found when the top hit does not contain the asked term") rather than a search change.

## Step 5 - Miss autopsy

Take every practice ticket that is buried or lost and place it on exactly one row of the chart. Do the probe; do not guess.

| Cause | What happened | One-minute probe | Usual fixes |
|---|---|---|---|
| **Not on shelf** | file never indexed (type, ignore rule, size cap, scanned PDF) | search for a unique phrase copied from the answer; zero hits means it is not there | add the type or parser, OCR, lift the cap, fix ignore rules |
| **Old copy** | index holds an older version of the file | compare the indexed text with the file on disk | reindex, turn on watching, schedule rebuilds |
| **Torn** | the answer is split across two chunks; neither half matches enough | look at the chunk boundaries around the answer lines | heading-aware chunks, more overlap, smaller units for tables |
| **Drowned** | the chunk is so large the answer is a small part of it | check chunk length around the answer; whole-file chunks are a red flag | smaller chunks, per-passage scoring |
| **Word gap** | user words differ from document words | rerun with the document's own words; if it is now found, it is a word gap | vector or hybrid mode, synonym list, query rewrite, a glossary file |
| **Code mangled** | an exact token (error code, SKU, identifier) was split or ignored | search the code alone; check how the tokenizer splits it | keep codes whole, add a keyword leg to vector search, exact-match field |
| **Wrong room** | a filter, namespace, path scope or permission excluded it | rerun with filters removed | fix metadata, scope or default filter |
| **Crowded out** | near-duplicates, old versions or boilerplate fill the top k | look at what ranks above the answer | dedupe, drop old versions, demote boilerplate, diversify results |
| **Label wrong** | the ticket's pin is wrong or incomplete; the system found a valid answer | read the hits that ranked first | fix the ticket (log the fix), never the score |

Write each autopsy as one line in `autopsy.md`: ticket, cause, probe result, proposed fix. Then count rows. The cause with the most tickets is the first change to try, unless a cheaper change covers a near-equal count.

Memory stores add one pattern: the `newest-wins` ticket where an older entry outranks the current one. That is an **old copy** problem inside memory; fixes are superseding or expiring entries, not tuning the retriever.

## Step 6 - One change at a time

Each change gets an entry in `changes.md` **before** it runs:

```
C2  hypothesis: heading-aware chunks fix "torn" misses (t08, t15, t22)
    change:     chunker = headings, size 4 lines, overlap 1 (was plain 4/1)
    expect:     those 3 fixed, nothing broken
```

Run the practice half with the change, then compare with the previous kept run:

```bash
python3 scripts/laf.py compare .lost-and-found/tickets.practice.jsonl runs/c1.jsonl runs/c2.jsonl -k 5
```

The comparison lists tickets **fixed**, **broken**, **rose** and **fell**, plus an exact sign test on the better/worse counts.

**Keep a change only if:** every broken ticket has been read and explained; fixed minus broken is at least 2 tickets (or the sign test is convincing on a large set); and the change does not cost something the scope note cares about (latency, privacy, money). Otherwise revert and log why. Never change two things in one run; if a change "helps" you will not know which half did it.

When the practice half stops improving, run the final configuration and the original baseline **once** on the sealed half. If the sealed gain is much smaller than the practice gain, you tuned to the practice questions; report the sealed number.

## Step 7 - Trust note

End with `trust-note.md`, short enough to paste into the agent's instructions:

```
Search trust note - <system>, <date>, k=<k>, <n> sealed tickets
Finds reliably:     <tags/areas with high hit@k, with numbers>
Finds unreliably:   <tags/areas, numbers, and the workaround: e.g. "search the error code alone">
Cannot find:        <what is not on the shelf, e.g. scanned PDFs before 2024>
Do not rely on search for: <things that need the source system, e.g. live prices>
When nothing relevant is in the top <k>: say so; do not answer from the nearest passage.
Recheck: <trigger: new file types, reindex, embedder change, every N weeks>
```

Also report, in a few lines: baseline versus final numbers on the sealed half, the changes kept and reverted, tickets still lost and their causes, and any ticket fixes.

## Example (short)

A small bike shop's staff notes (returns, warranty, workshop, a POS error log, a Chinese store notice) and 12 tickets. Agent reads only the top hit (k=1).

- Plain 4-line chunks: hit@1 9/11. Misses: `t02` (buried, rank 3) and `t08` (buried, rank 2).
- Autopsy: `t08` is **torn**: the rule's chunk lost the page title ("Returns and refunds"), so the intro paragraph that repeats "returns policy" outranks it. `t02` is a **word gap**: "after three weeks" versus "14 days".
- C1, heading-aware chunks: fixed `t08`, broke nothing, so it was kept. hit@1 is now 10/11.
- `t02` needs meaning, not keywords: it goes to the trust note as "finds unreliably: time-limit questions phrased in weeks; ask in days or check returns.md directly" until a hybrid leg is tested.
- The none-ticket "Do you sell gift cards?" still returns a workshop passage with a nonzero score, so the trust note gets the "say not found" rule.

The full walk-through with commands and output is in `examples/worked-example.md`.

## Tips

- **k is a fact, not a setting you pick for the report.** Find out what the agent really reads.
- **Small sets lie in decimals.** With 20 tickets, one ticket is 5 points. Talk in tickets.
- **Buried is not lost.** Buried answers need ranking help (reranker, hybrid weights, dedupe). Lost answers need indexing or vocabulary help.
- **Keyword baselines are hard to beat on codes and names.** Vector search is hard to beat on paraphrase. Hybrid usually wins only when both kinds of ticket exist, so check per tag, not overall.
- **Do not grade on a chunk id.** Pin to path plus lines, page or quote so tickets survive re-chunking.
- **Never fix a score by editing a ticket** unless the autopsy shows the label was wrong, and log the edit.
- **Rerankers and remote embedders may send your text off the machine.** Note that in the change log and get the owner's agreement before trying one on private material.
- **Grow the tickets.** Every real miss someone reports becomes a new ticket, tagged with its cause.
- **Rerun on change.** New file types, a reindex, a new embedder or a new chunker all mean rerunning the sealed half.
