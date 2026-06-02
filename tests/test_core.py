"""Offline unit tests for leetcode-assistant core logic.

Run with:  py -m unittest discover -s tests
No third-party deps, no network (roadmap data is bundled).
"""

import json
import tempfile
import unittest
from pathlib import Path

from leetcode_assistant import data, progress, readme, roadmap, scaffold


class TestRoadmap(unittest.TestCase):
    def test_preset_counts(self):
        self.assertEqual(len(roadmap.problems_for_preset("blind75")), 75)
        self.assertEqual(len(roadmap.problems_for_preset("neetcode150")), 150)
        self.assertEqual(len(roadmap.problems_for_preset("neetcode250")), 250)
        self.assertGreater(len(roadmap.problems_for_preset("all")), 250)

    def test_topic_for_slug(self):
        self.assertEqual(roadmap.topic_for_slug("two-sum"), "Arrays & Hashing")

    def test_resolve_topic(self):
        self.assertEqual(roadmap.resolve_topic("two pointers"), "Two Pointers")
        self.assertEqual(roadmap.resolve_topic("1-d dp"), "1-D Dynamic Programming")

    def test_normalize_preset(self):
        self.assertEqual(roadmap.normalize_preset("250"), "neetcode250")
        self.assertEqual(roadmap.normalize_preset(None), "neetcode150")


class TestReadme(unittest.TestCase):
    def test_generate(self):
        entries = [
            {"date": "2026-01-01", "number": 1, "slug": "two-sum", "title": "Two Sum",
             "difficulty": "easy", "topic": "Arrays & Hashing", "optimality": "optimal",
             "url": "https://leetcode.com/problems/two-sum/", "seconds": 125},
            {"date": "2026-01-02", "number": 2, "slug": "x", "title": "X",
             "difficulty": "medium", "topic": "Stack", "optimality": "suboptimal"},
        ]
        md = readme.generate(entries, streak=2)
        self.assertIn("# LeetCode Solutions", md)
        self.assertIn("Two Sum", md)
        self.assertIn("2m 5s", md)            # 125 seconds formatted
        self.assertIn("img.shields.io", md)   # badges present
        # self-reported approach column is rendered
        self.assertIn("Approach", md)
        self.assertIn("Optimal", md)
        self.assertIn("Suboptimal", md)

    def test_generate_unmarked_approach(self):
        # entries with no self-reported approach show "-" and no optimal badge
        entries = [{"date": "2026-01-01", "number": 1, "slug": "two-sum",
                    "title": "Two Sum", "difficulty": "easy", "topic": "Arrays & Hashing"}]
        md = readme.generate(entries, streak=1)
        self.assertIn("Approach", md)
        self.assertNotIn("Solved optimally", md)


class TestScaffoldSignatures(unittest.TestCase):
    def test_python_signature(self):
        snippet = ("class Solution:\n"
                   "    def twoSum(self, nums: List[int], target: int) -> List[int]:\n")
        name, params = scaffold._python_signature(snippet)
        self.assertEqual(name, "twoSum")
        self.assertEqual(params, ["nums", "target"])

    def test_js_signature(self):
        snippet = "var twoSum = function(nums, target) {\n};"
        name, params = scaffold._js_signature(snippet)
        self.assertEqual(name, "twoSum")
        self.assertEqual(params, ["nums", "target"])


class TestDataParsing(unittest.TestCase):
    def test_html_to_text(self):
        self.assertEqual(data.html_to_text("a&nbsp;b"), "a b")

    def test_parse_example_outputs(self):
        text = "Input: nums = [1]\nOutput: [0,1]\nExplanation: x\nOutput: 5"
        self.assertEqual(data.parse_example_outputs(text), ["[0,1]", "5"])


class TestProgress(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_path = progress.PROGRESS_PATH
        self._orig_ensure = progress.ensure_home
        progress.PROGRESS_PATH = Path(self._tmp.name) / "progress.json"
        progress.ensure_home = lambda: None

    def tearDown(self):
        progress.PROGRESS_PATH = self._orig_path
        progress.ensure_home = self._orig_ensure
        self._tmp.cleanup()

    def _write(self, entries):
        progress.PROGRESS_PATH.write_text(json.dumps({"solved": entries}), encoding="utf-8")

    def test_record_and_slugs(self):
        progress.record_solve(1, "two-sum", "Two Sum", "easy",
                              topic="Arrays & Hashing")
        self.assertIn("two-sum", progress.solved_slugs())

    def test_longest_streak(self):
        self._write([
            {"date": "2026-01-01", "slug": "a"},
            {"date": "2026-01-02", "slug": "b"},
            {"date": "2026-01-03", "slug": "c"},
            {"date": "2026-01-10", "slug": "d"},
        ])
        self.assertEqual(progress.longest_streak(), 3)

    def test_due_for_review(self):
        from datetime import date, timedelta
        old = (date.today() - timedelta(days=30)).isoformat()
        recent = date.today().isoformat()
        self._write([
            {"date": old, "number": 1, "slug": "old", "title": "Old", "difficulty": "easy"},
            {"date": recent, "number": 2, "slug": "new", "title": "New", "difficulty": "easy"},
        ])
        due = progress.due_for_review(days=7)
        slugs = [d["slug"] for d in due]
        self.assertIn("old", slugs)
        self.assertNotIn("new", slugs)

    def test_optimality_recorded_and_counted(self):
        progress.record_solve(1, "a", "A", "easy", optimality="optimal")
        progress.record_solve(2, "b", "B", "easy", optimality="suboptimal")
        progress.record_solve(3, "c", "C", "easy")            # unmarked / skipped
        progress.record_solve(4, "d", "D", "easy", optimality="garbage")  # ignored
        s = progress.stats()
        self.assertEqual(s["graded"], 2)   # only the two valid marks count
        self.assertEqual(s["optimal"], 1)
        a = progress._load()["solved"][0]
        self.assertEqual(a.get("optimality"), "optimal")
        c = progress._load()["solved"][2]
        self.assertNotIn("optimality", c)  # skipped -> key omitted


class TestReviewSRS(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_path = progress.PROGRESS_PATH
        self._orig_ensure = progress.ensure_home
        self._orig_iv = progress.review_intervals
        progress.PROGRESS_PATH = Path(self._tmp.name) / "progress.json"
        progress.ensure_home = lambda: None
        progress.review_intervals = lambda: [7, 30, 90, 365]
        progress.PROGRESS_PATH.write_text('{"solved": [], "reviews": {}}', encoding="utf-8")

    def tearDown(self):
        progress.PROGRESS_PATH = self._orig_path
        progress.ensure_home = self._orig_ensure
        progress.review_intervals = self._orig_iv
        self._tmp.cleanup()

    def _meta(self):
        return {"number": 1, "title": "Two Sum", "difficulty": "easy",
                "topic": "Arrays & Hashing", "url": "u"}

    def test_ladder(self):
        from datetime import date, timedelta
        # first solve -> level 0, due in 7 days
        r = progress.schedule_review("two-sum", self._meta(), rating=None)
        self.assertEqual(r["level"], 0)
        self.assertEqual(r["due"], (date.today() + timedelta(days=7)).isoformat())
        # aced -> level 1 (30d)
        r = progress.schedule_review("two-sum", self._meta(), rating="aced")
        self.assertEqual(r["level"], 1)
        self.assertEqual(r["due"], (date.today() + timedelta(days=30)).isoformat())
        # hard -> reset to level 0 (7d)
        r = progress.schedule_review("two-sum", self._meta(), rating="hard")
        self.assertEqual(r["level"], 0)

    def test_due_reviews(self):
        from datetime import date, timedelta
        progress.schedule_review("x", self._meta())
        # force it overdue
        data = json.loads(progress.PROGRESS_PATH.read_text())
        data["reviews"]["x"]["due"] = (date.today() - timedelta(days=2)).isoformat()
        progress.PROGRESS_PATH.write_text(json.dumps(data), encoding="utf-8")
        due = progress.due_reviews()
        self.assertEqual(due[0]["slug"], "x")
        self.assertEqual(due[0]["days_overdue"], 2)

    def test_resolve_before_due_does_not_advance(self):
        # First solve schedules level 0 / due +7. Re-solving the same problem
        # before it's due (no rating) must NOT advance the level or push the
        # date out -- it's just practice.
        r1 = progress.schedule_review("two-sum", self._meta(), rating=None)
        self.assertEqual(r1["level"], 0)
        due_after_first = r1["due"]
        r2 = progress.schedule_review("two-sum", self._meta(), rating=None)
        self.assertEqual(r2["level"], 0)
        self.assertEqual(r2["due"], due_after_first)   # unchanged
        self.assertEqual(r2.get("reps"), 2)            # but practice counted

    def test_is_review_due(self):
        from datetime import date, timedelta
        progress.schedule_review("x", self._meta())
        self.assertFalse(progress.is_review_due("x"))      # due in 7 days
        self.assertFalse(progress.is_review_due("nope"))   # untracked
        data = json.loads(progress.PROGRESS_PATH.read_text())
        data["reviews"]["x"]["due"] = (date.today() - timedelta(days=1)).isoformat()
        progress.PROGRESS_PATH.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(progress.is_review_due("x"))

    def test_readme_review_section(self):
        from datetime import date
        reviews = {"two-sum": {"level": 1, "due": date.today().isoformat(),
                               "number": 1, "title": "Two Sum", "difficulty": "easy",
                               "url": "u", "last_rating": "aced"}}
        md = readme.generate([], streak=0, reviews=reviews)
        self.assertIn("Review schedule", md)
        self.assertIn("Familiar", md)
        self.assertIn("DUE", md)


class TestTopicTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_path = progress.PROGRESS_PATH
        self._orig_ensure = progress.ensure_home
        progress.PROGRESS_PATH = Path(self._tmp.name) / "progress.json"
        progress.ensure_home = lambda: None
        progress.PROGRESS_PATH.write_text('{"solved": []}', encoding="utf-8")

    def tearDown(self):
        progress.PROGRESS_PATH = self._orig_path
        progress.ensure_home = self._orig_ensure
        self._tmp.cleanup()

    def test_in_progress_then_pass(self):
        slugs = ["a", "b", "c"]
        r = progress.record_test_outcome("T", "blind75", "a", "clean", slugs)
        self.assertEqual(r["status"], "in_progress")
        self.assertEqual(r["done"], 1)
        self.assertEqual(r["remaining"], ["b", "c"])
        progress.record_test_outcome("T", "blind75", "b", "unsure", slugs)
        r = progress.record_test_outcome("T", "blind75", "c", "help", slugs)
        self.assertEqual(r["status"], "passed")
        rec = r["record"]
        self.assertEqual(rec["total"], 3)
        self.assertEqual((rec["clean"], rec["unsure"], rec["help"]), (1, 1, 1))
        self.assertFalse(rec["clean_pass"])
        # cleared from in-progress, present in passed tests
        self.assertNotIn("T", progress.test_in_progress())
        self.assertIn("T", progress.passed_tests())

    def test_clean_sweep(self):
        slugs = ["a", "b"]
        progress.record_test_outcome("T", "blind75", "a", "clean", slugs)
        r = progress.record_test_outcome("T", "blind75", "b", "clean", slugs)
        self.assertTrue(r["record"]["clean_pass"])

    def test_higher_preset_supersedes_not_downgrade(self):
        slugs = ["a"]
        progress.record_test_outcome("T", "neetcode250", "a", "clean", slugs)
        # a lower-preset pass must NOT overwrite the higher one
        progress.record_test_outcome("T", "blind75", "a", "help", slugs)
        self.assertEqual(progress.passed_tests()["T"]["preset"], "neetcode250")
        # but a higher preset does replace a lower one
        progress.record_test_outcome("T2", "blind75", "a", "clean", ["a"])
        progress.record_test_outcome("T2", "all", "a", "unsure", ["a"])
        self.assertEqual(progress.passed_tests()["T2"]["preset"], "all")

    def test_status_states(self):
        slugs = ["a", "b"]
        st = progress.test_status("T", "blind75", slugs)
        self.assertEqual(st["state"], "not_started")
        progress.record_test_outcome("T", "blind75", "a", "clean", slugs)
        st = progress.test_status("T", "blind75", slugs)
        self.assertEqual(st["state"], "in_progress")
        self.assertEqual(st["done"], 1)
        progress.record_test_outcome("T", "blind75", "b", "clean", slugs)
        st = progress.test_status("T", "blind75", slugs)
        self.assertEqual(st["state"], "passed")
        # a pass at a lower preset counts as passed when viewing a higher one too?
        # higher preset is harder, so a blind75 pass should NOT show as passed at 'all'
        st_high = progress.test_status("T", "all", slugs)
        self.assertNotEqual(st_high["state"], "passed")

    def test_readme_testing_section(self):
        tests = {"Arrays & Hashing": {
            "preset": "neetcode250", "completed_at": "2026-06-02 10:00",
            "total": 2, "clean": 2, "unsure": 0, "help": 0, "clean_pass": True,
            "problems": [{"slug": "two-sum", "outcome": "clean"},
                         {"slug": "valid-anagram", "outcome": "clean"}]}}
        md = readme.generate([], streak=0, tests=tests)
        self.assertIn("Topic tests", md)
        self.assertIn("Arrays & Hashing", md)
        self.assertIn("NeetCode 250", md)
        self.assertIn("clean sweep", md)
        self.assertIn("two-sum", md)


if __name__ == "__main__":
    unittest.main()
