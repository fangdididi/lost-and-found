**English** | [简体中文](README.zh-CN.md)

# Lost and Found

**Does your agent's search actually find the right passage in your own files? An agent skill that measures it with real questions pinned to real locations, explains every miss, fixes one thing at a time, and ends with a trust note the agent can follow.**

Your coding agent searches a local index before it edits. Your support bot runs RAG over the help center. Your assistant keeps a memory of past decisions. When an answer comes back wrong, the usual reflexes are to blame the model, swap the embedding model, or raise `top_k` and hope. None of those answers the first question: *for the things we really ask, does the right passage reach the agent?*

Lost and Found makes the agent answer that question on **your** corpus, in seven steps:

- **Scope note.** Which search path is under test, its settings, and the reading depth `k` the agent really uses. Scoring at 10 when the agent reads 3 flatters the system.
- **Claim tickets.** Real questions, each pinned to the spot that answers it by path plus lines, page or a short quote, never by chunk id, so tickets survive re-chunking. Tagged by what makes them hard: synonyms, exact codes, two-place answers, PDFs and logs, newest-wins memory, other languages, and questions the corpus cannot answer.
- **Shelf count.** What exists versus what was indexed: skipped types, scanned PDFs with no text layer, ignore rules, size caps, stale index, duplicate or contradicting memory entries.
- **Baseline runs.** Export the real system's ranked hits, add a plain keyword yardstick, and score hit@k, recall@k, MRR and nDCG at the real `k`, per tag, with found / buried / lost per ticket.
- **Miss autopsy.** Every miss goes on one row of a nine-way chart (not on shelf, old copy, torn, drowned, word gap, code mangled, wrong room, crowded out, label wrong), each with a one-minute probe and the usual fixes.
- **One change at a time.** Hypothesis written first, run on a practice half, judged ticket by ticket (fixed / broken / rose / fell, exact sign test), kept only if every broken ticket is explained, then confirmed once on a sealed half.
- **Trust note.** A paste-ready block for the agent's instructions: what it finds reliably, what it finds unreliably and the workaround, what is not on the shelf, what never to rely on search for, and when to say "not found".

## Features

| | |
|---|---|
| Works for | local code/doc search, RAG pipelines, vector stores, hybrid search, MCP search tools, agent memory namespaces |
| Ticket pins | `path` + `lines`, `page` or `quote`; several answering spots per ticket; none-tickets for "not in the corpus" |
| Metrics | hit@k, recall@k, MRR@k, nDCG@k, found / buried / lost, per-tag table, small-set warnings |
| Comparisons | ticket-by-ticket fixed / broken / rose / fell with an exact sign test |
| Overfitting guard | stable hash split into practice and sealed halves |
| Keyword yardstick | built-in BM25 over a folder: line-window or heading-aware chunks, CJK character pairs, codes like `E-217` kept whole |
| Run export | patterns for MCP tools, HTTP search APIs, SQLite FTS5, vector stores, memory recall, or a plain spreadsheet |
| Helper | `scripts/laf.py`, Python standard library only, 22 tests |
| Privacy | everything runs locally; the skill flags rerankers and remote embedders that send text off the machine |
| Bilingual | full English and Chinese skill files, reference and worked example |

## Installation

The skill is the folder containing `SKILL.md` (English) and `SKILL.zh-CN.md` (Chinese). Copy the whole folder so `scripts/`, `references/` and `examples/` come with it.

**Claude Code**

```bash
git clone https://github.com/fangdididi/lost-and-found.git ~/.claude/skills/lost-and-found
```

**Codex / agents that read `~/.agents/skills`**

```bash
git clone https://github.com/fangdididi/lost-and-found.git ~/.agents/skills/lost-and-found
```

**Cursor** (project skills folder)

```bash
git clone https://github.com/fangdididi/lost-and-found.git .cursor/skills/lost-and-found
```

**Any other agent** (Gemini CLI, GitHub Copilot, OpenCode, Windsurf, Cline, Kimi, chat apps): paste `SKILL.md` into its instructions or project rules, or ask it to install the skill from this repository URL. For Chinese conversations use `SKILL.zh-CN.md`. Without a shell you lose the helper, but the method works with a spreadsheet: one row per ticket, the first ten results per row.

## Usage

Ask in plain words:

- "Our agent keeps saying it can't find things in `docs/`. Use lost-and-found to check the search."
- "We're thinking of switching to hybrid search. Measure whether it helps on our own questions first."
- "RAG cites old policy versions. Find out why."
- "Check whether the memory store recalls the newest decision."

The agent will write a scope note, build tickets with you, count the shelf, export runs, score, autopsy, run changes one at a time and write the trust note, all inside `.lost-and-found/` in your project.

Using the helper directly:

```bash
# validate tickets against the corpus
python3 scripts/laf.py check tickets.jsonl --root path/to/corpus

# practice / sealed split (stable)
python3 scripts/laf.py split tickets.jsonl --practice tickets.practice.jsonl --sealed tickets.sealed.jsonl

# plain keyword yardstick over the folder
python3 scripts/laf.py bm25 tickets.practice.jsonl --root path/to/corpus --chunk 20 --overlap 5 --out runs/yardstick.jsonl

# score any run at the depth the agent reads
python3 scripts/laf.py score tickets.practice.jsonl runs/current.jsonl -k 5 --root path/to/corpus

# ticket-by-ticket before/after
python3 scripts/laf.py compare tickets.practice.jsonl runs/c1.jsonl runs/c2.jsonl -k 5
```

Run the tests:

```bash
python3 -m unittest discover -s tests -v
```

## Example

Staff notes of a fictional bike shop, 12 tickets, an agent that reads only the top hit:

```
plain 4-line chunks      hit@1 9/11   buried: t02 (rank 3), t08 (rank 2)
autopsy                  t08 torn (rule's chunk lost the page title), t02 word gap ("three weeks" vs "14 days")
C1 heading-aware chunks  fixed t08, broke nothing -> kept     hit@1 10/11
C2 split codes           no change -> reverted
trust note               "time-limit questions phrased in weeks: unreliable; check returns.md"
                         "top hit unrelated: say not found" (gift-card none-ticket)
```

Full walk-through with every command and its real output: [`examples/worked-example.md`](examples/worked-example.md).

## File structure

```
lost-and-found/
├── SKILL.md                      # the skill (English)
├── SKILL.zh-CN.md                # the skill (Chinese, full)
├── README.md / README.zh-CN.md
├── LICENSE
├── scripts/
│   └── laf.py                    # check, split, bm25, score, compare (stdlib only)
├── references/
│   ├── exporting-runs.md         # how to export ranked hits from real systems
│   └── exporting-runs.zh-CN.md
├── examples/
│   ├── tiny-corpus/              # fictional bike-shop notes (EN + one Chinese file)
│   ├── tickets.jsonl             # 12 example tickets
│   ├── worked-example.md
│   └── worked-example.zh-CN.md
└── tests/
    └── test_laf.py               # 22 unit tests
```

## License

MIT, see [LICENSE](LICENSE).
