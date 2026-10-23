import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import laf  # noqa: E402

CORPUS = os.path.join(ROOT, "examples", "tiny-corpus")
TICKETS = os.path.join(ROOT, "examples", "tickets.jsonl")


def T(tid, where, kind="find", tags=None):
    return {"id": tid, "ask": "q " + tid, "where": where, "kind": kind,
            "tags": tags or []}


class TokenizeTests(unittest.TestCase):
    def test_codes_kept_whole_and_split(self):
        toks = laf.tokenize("Error E-217 on v2.3")
        self.assertIn("e-217", toks)
        self.assertIn("217", toks)
        self.assertIn("v2.3", toks)

    def test_codes_can_be_split_only(self):
        toks = laf.tokenize("E-217", keep_codes=False)
        self.assertNotIn("e-217", toks)
        self.assertEqual(toks, ["e", "217"])

    def test_cjk_bigrams(self):
        self.assertEqual(laf.tokenize("周一闭店"), ["周一", "一闭", "闭店"])


class ChunkTests(unittest.TestCase):
    def test_line_windows_overlap_and_cover_end(self):
        text = "\n".join(str(i) for i in range(1, 11))
        chunks = laf.chunk_lines(text, 4, 1)
        self.assertEqual([(a, b) for a, b, _ in chunks], [(1, 4), (4, 7), (7, 10)])

    def test_sections_do_not_cross_headings(self):
        text = "# A\none\ntwo\n## B\nthree\n# C\nfour"
        chunks = laf.chunk_sections(text, 10, 0)
        self.assertEqual([(a, b) for a, b, _, _ in chunks], [(1, 3), (4, 5), (6, 7)])
        self.assertEqual(chunks[1][3], "A / B")
        self.assertEqual(chunks[2][3], "C")


class MatchTests(unittest.TestCase):
    def test_path_and_line_overlap(self):
        w = {"path": "a/b.md", "lines": [10, 20]}
        self.assertTrue(laf.matches({"path": "./a/b.md", "lines": [18, 30]}, w))
        self.assertFalse(laf.matches({"path": "a/b.md", "lines": [21, 30]}, w))
        self.assertFalse(laf.matches({"path": "a/b.md"}, w))

    def test_quote_needs_text(self):
        w = {"path": "x.md", "quote": "Six  Working days"}
        self.assertTrue(laf.matches({"path": "x.md", "text": "within six working\ndays"}, w))
        self.assertFalse(laf.matches({"path": "x.md", "text": "store credit"}, w))

    def test_quote_read_from_root_when_hit_has_lines_only(self):
        w = {"path": "returns.md", "quote": "within 6 working days"}
        self.assertTrue(laf.matches({"path": "returns.md", "lines": [17, 20]}, w, CORPUS))
        self.assertFalse(laf.matches({"path": "returns.md", "lines": [1, 4]}, w, CORPUS))

    def test_page(self):
        w = {"path": "m.pdf", "page": 3}
        self.assertTrue(laf.matches({"path": "m.pdf", "page": 3}, w))
        self.assertFalse(laf.matches({"path": "m.pdf", "page": 4}, w))
        self.assertFalse(laf.matches({"path": "m.pdf"}, w))


class MetricTests(unittest.TestCase):
    def test_single_location_metrics(self):
        t = T("t", [{"path": "g.md"}])
        hits = [{"path": "x.md"}, {"path": "g.md"}]
        r = laf.score_ticket(t, hits, k=5)
        self.assertEqual(r["status"], "found")
        self.assertEqual(r["rr"], 0.5)
        self.assertAlmostEqual(r["ndcg"], 1 / laf.math.log2(3))

    def test_buried_and_lost(self):
        t = T("t", [{"path": "g.md"}])
        hits = [{"path": "x%d.md" % i} for i in range(5)] + [{"path": "g.md"}]
        self.assertEqual(laf.score_ticket(t, hits, k=5)["status"], "buried")
        self.assertEqual(laf.score_ticket(t, hits, k=5)["rr"], 0.0)
        self.assertEqual(laf.score_ticket(t, [], k=5)["status"], "lost")

    def test_two_locations_recall(self):
        t = T("t", [{"path": "a.md"}, {"path": "b.md"}])
        r = laf.score_ticket(t, [{"path": "a.md"}, {"path": "z.md"}], k=2)
        self.assertEqual(r["recall"], 0.5)
        self.assertEqual(r["hit"], 1.0)

    def test_one_chunk_cannot_count_twice_in_ndcg(self):
        t = T("t", [{"path": "a.md"}, {"path": "a.md", "lines": [1, 3]}])
        r = laf.score_ticket(t, [{"path": "a.md", "lines": [1, 2]}], k=3)
        self.assertEqual(r["recall"], 1.0)  # both spans really are inside it
        self.assertLess(r["ndcg"], 1.0)     # but one chunk earns gain once

    def test_none_tickets_excluded_from_means(self):
        tickets = [T("a", [{"path": "g.md"}]), T("n", [], kind="none")]
        run = [{"ticket": "a", "hits": [{"path": "g.md"}]},
               {"ticket": "n", "hits": [{"path": "q.md", "score": 3}]}]
        s, _, rows = laf.score_run(tickets, run, k=3)
        self.assertEqual(s["hit@k"], 1.0)
        self.assertEqual(s["none_tickets"], 1)
        self.assertEqual(rows[1]["top"]["path"], "q.md")

    def test_missing_ticket_counts_as_lost(self):
        s, _, _ = laf.score_run([T("a", [{"path": "g.md"}])], [], k=3)
        self.assertEqual(s["lost"], 1)
        self.assertEqual(s["missing_from_run"], ["a"])


class CompareTests(unittest.TestCase):
    def test_fixed_broken_rose(self):
        tickets = [T("a", [{"path": "a"}]), T("b", [{"path": "b"}]), T("c", [{"path": "c"}])]
        before = [{"ticket": "a", "hits": [{"path": "z"}]},
                  {"ticket": "b", "hits": [{"path": "b"}]},
                  {"ticket": "c", "hits": [{"path": "z"}, {"path": "c"}]}]
        after = [{"ticket": "a", "hits": [{"path": "a"}]},
                 {"ticket": "b", "hits": [{"path": "z"}]},
                 {"ticket": "c", "hits": [{"path": "c"}]}]
        c = laf.compare_runs(tickets, before, after, k=1)
        self.assertEqual(c["fixed"], ["a", "c"])
        self.assertEqual(c["broken"], ["b"])
        c2 = laf.compare_runs(tickets, before, after, k=2)
        self.assertEqual(c2["rose"], ["c"])

    def test_sign_test(self):
        self.assertEqual(laf.sign_test_p(0, 0), 1.0)
        self.assertAlmostEqual(laf.sign_test_p(1, 0), 1.0)
        self.assertLess(laf.sign_test_p(10, 0), 0.01)


class CheckSplitTests(unittest.TestCase):
    def test_example_tickets_are_clean(self):
        tickets = laf.read_jsonl(TICKETS)
        self.assertEqual(laf.check_tickets(tickets, CORPUS), [])

    def test_check_catches_problems(self):
        tickets = [T("a", [{"path": "returns.md", "quote": "no such words"}]),
                   T("a", [{"path": "nope.md"}]),
                   T("c", [], kind="find"),
                   T("d", [{"path": "returns.md", "lines": [1, 999]}])]
        msgs = " | ".join(m for _, m in laf.check_tickets(tickets, CORPUS))
        for want in ("quote not found", "duplicate id", "path not in corpus",
                     "no where", "outside file"):
            self.assertIn(want, msgs)

    def test_split_is_stable_and_complete(self):
        tickets = [T("t%02d" % i, [{"path": "x"}]) for i in range(40)]
        p1, s1 = laf.split_tickets(tickets)
        p2, s2 = laf.split_tickets(list(reversed(tickets)))
        self.assertEqual(sorted(t["id"] for t in p1), sorted(t["id"] for t in p2))
        self.assertEqual(len(p1) + len(s1), 40)
        self.assertTrue(p1 and s1)


class EndToEndTests(unittest.TestCase):
    def test_heading_chunks_fix_two_place_ticket(self):
        tickets = laf.read_jsonl(TICKETS)
        plain, skipped, _ = laf.build_bm25_run(CORPUS, tickets, 4, 1, 10)
        heads, _, _ = laf.build_bm25_run(CORPUS, tickets, 4, 1, 10, headings=True)
        self.assertEqual(skipped, [])
        c = laf.compare_runs(tickets, plain, heads, k=1)
        self.assertIn("t08", c["fixed"])
        self.assertEqual(c["broken"], [])

    def test_cli_score_runs(self):
        with tempfile.TemporaryDirectory() as d:
            run = os.path.join(d, "run.jsonl")
            script = os.path.join(ROOT, "scripts", "laf.py")
            subprocess.run([sys.executable, script, "bm25", TICKETS, "--root", CORPUS,
                            "--out", run], check=True, capture_output=True)
            out = subprocess.run([sys.executable, script, "score", TICKETS, run, "-k", "3"],
                                 check=True, capture_output=True, text=True).stdout
            self.assertIn("hit@3", out)
            self.assertIn("THIN SET", out)
            with open(run, encoding="utf-8") as fh:
                self.assertEqual(len([json.loads(x) for x in fh]), 12)


if __name__ == "__main__":
    unittest.main()
