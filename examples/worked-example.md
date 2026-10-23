# Worked example: Kestrel Bikes staff notes

A fictional small bike shop keeps its staff knowledge in a folder: a returns policy, a warranty page, workshop notes, a point-of-sale error log and a short store notice in Chinese. The shop's assistant agent searches this folder and **reads only the top hit** before answering staff questions. Everything below can be rerun from the repository root.

Files: `examples/tiny-corpus/` (corpus) and `examples/tickets.jsonl` (12 tickets).

> Twelve tickets is a demonstration, not a measurement. A real run wants 30 to 60 find-tickets. The helper says so on every score ("THIN SET").

## 1. Scope note

```
System under test: keyword search over examples/tiny-corpus, 4-line chunks, 1 line overlap
Corpus:            all staff notes; nothing excluded
Reading depth:     k = 1 (the agent answers from the top hit only)
Unit of answer:    the right section (pinned by quote)
Cost of a miss:    staff give a customer the wrong refund or warranty answer
```

## 2. Tickets

Eleven find-tickets and one none-ticket. Tags cover synonyms, paraphrase, an exact error code, a log file, a two-place answer and two Chinese questions. Example lines:

```json
{"id": "t03", "ask": "what does E-217 mean", "where": [{"path": "errors.log", "quote": "E-217 card reader lost pairing"}], "tags": ["exact-code", "log"], "kind": "find"}
{"id": "t08", "ask": "Are refunds for faulty items handled under the returns policy?", "where": [{"path": "returns.md", "quote": "see warranty.md instead"}, {"path": "warranty.md", "quote": "To start a claim"}], "tags": ["two-places"], "kind": "find"}
{"id": "t12", "ask": "Do you sell gift cards?", "where": [], "tags": ["absent"], "kind": "none"}
```

```
$ python3 scripts/laf.py check examples/tickets.jsonl --root examples/tiny-corpus
12 tickets (11 find, 1 none)
tags: synonym=2, paraphrase=2, log=2, direct=2, chinese=2, exact-code=1, two-places=1, absent=1
corpus: 5 text files read, 0 skipped
OK: no problems found
```

With only 12 tickets the example skips the practice/sealed split. On a real set:

```
$ python3 scripts/laf.py split tickets.jsonl --practice tickets.practice.jsonl --sealed tickets.sealed.jsonl
```

## 3. Shelf count

| Type | On disk | Indexed | Gap |
|---|---|---|---|
| .md | 4 | 4 | 0 |
| .log | 1 | 1 | 0 |

No PDFs, nothing skipped, index built from the current files. Nothing to fix on the shelf.

## 4. Baseline

```
$ python3 scripts/laf.py bm25 examples/tickets.jsonl --root examples/tiny-corpus --chunk 4 --overlap 1 --out runs/c0.jsonl
indexed 23 plain chunks (4 lines, 1 overlap); 0 files skipped; run -> runs/c0.jsonl

$ python3 scripts/laf.py score examples/tickets.jsonl runs/c0.jsonl -k 1 --root examples/tiny-corpus
find-tickets 11, none-tickets 1, k=1
hit@1  81.8%  recall@1  81.8%  MRR@1 0.818  nDCG@1 0.818
found 9  buried(below k) 2  lost 0
THIN SET: under 20 find-tickets; one ticket moves hit@k by 5+ points. Read tickets, not decimals.

by tag:
  chinese            n=2   hit@1 100.0%  MRR 1.000
  direct             n=2   hit@1 100.0%  MRR 1.000
  exact-code         n=1   hit@1 100.0%  MRR 1.000
  log                n=2   hit@1 100.0%  MRR 1.000
  paraphrase         n=2   hit@1  50.0%  MRR 0.500
  synonym            n=2   hit@1 100.0%  MRR 1.000
  two-places         n=1   hit@1   0.0%  MRR 0.000

not found in top k:
  t02      buried  first rank 3  tags paraphrase
  t08      buried  first rank 2  tags two-places

none-tickets (should find nothing; review the top hit):
  t12      top notes/workshop.md score 2.3337
```

In tickets: 9 of 11 found at the top. Two buried, none lost, so the material is on the shelf; this is a ranking problem.

## 5. Autopsy

| Ticket | Cause | Probe | Proposed fix |
|---|---|---|---|
| t08 | Torn | The top hit is the page intro (lines 1-4: "Returns and refunds ... returns policy"). The rule ("see warranty.md instead", line 25) sits in a chunk that no longer carries the page title, so it has fewer of the asked words. | heading-aware chunks that index the heading trail |
| t02 | Word gap | "Can a customer return a complete bike after three weeks?" ranks the "Who can return" section first. Asked again in the document's own words ("complete bikes days delivery"), the right chunk comes first. | meaning-based (vector/hybrid) leg, or a rule to ask in the document's units |
| t12 | (none-ticket) | Top hit is a workshop passage that shares only common words. An agent reading it might invent an answer. | answer rule in the trust note |

## 6. Changes

```
C1  hypothesis: heading-aware chunks fix the torn miss (t08)
    change:     --headings (was plain), size 4, overlap 1
    expect:     t08 fixed, nothing broken
```

```
$ python3 scripts/laf.py compare examples/tickets.jsonl runs/c0.jsonl runs/c1.jsonl -k 1
hit@1:  81.8% ->  90.9%   MRR@1: 0.818 -> 0.909
fixed   1   t08
broken  0
rose    0
fell    0
same    10
tickets better 1, worse 0, sign-test p=1.000
Difference could easily be chance on this set; confirm on the sealed half.
```

The hypothesis was stated before the run, the fixed ticket is exactly the predicted one, and nothing broke. On a real set the keep rule asks for fixed minus broken of at least 2; here the set is a demo, so C1 is kept *provisionally* and marked for recheck on the next, larger set.

```
C2  hypothesis: keeping codes like E-217 whole is unnecessary here
    change:     --split-codes
    result:     same 11, fixed 0, broken 0  ->  reverted (no gain, nothing learned to keep it for)
```

After C1, `recall@1` is 86.4% even though `hit@1` is 90.9%: t08 has two answering spots and only one can fit in a single hit. That is fine for this agent (one spot answers the question) and would matter if the agent had to cite both pages.

## 7. Trust note

```
Search trust note - Kestrel staff notes, keyword search, heading-aware 4-line chunks, k=1, 12 demo tickets
Finds reliably:     direct questions, error codes in errors.log, Chinese store notices, synonyms tried so far
Finds unreliably:   time-limit questions phrased in different units (t02: "three weeks" vs "14 days");
                    open returns.md "Time limits" directly for return windows
Cannot find:        nothing known missing from the shelf
Do not rely on search for: stock levels and live prices (not in these notes)
When nothing relevant is in the top hit: say "not in the staff notes"; do not answer from the nearest passage
Recheck: when new notes are added, or before switching to vector or hybrid search
```

Next step for this shop: grow the tickets from real staff questions to 30+, split, and test a hybrid leg against t02-style paraphrases on the practice half only.
