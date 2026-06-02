"""Offline unit tests for leetcode-assistant core logic.

Run with:  py -m unittest discover -s tests
No third-party deps, no network (roadmap data is bundled).
"""

import json
import tempfile
import unittest
from pathlib import Path

from leetcode_assistant import complexity, data, progress, readme, roadmap, scaffold


class TestComplexityClassification(unittest.TestCase):
    def test_slope_to_class(self):
        self.assertEqual(complexity._slope_to_class(0.1), "O(1)")
        self.assertEqual(complexity._slope_to_class(1.0), "O(n)")
        self.assertEqual(complexity._slope_to_class(1.5), "O(n log n)")
        self.assertEqual(complexity._slope_to_class(2.0), "O(n^2)")
        self.assertEqual(complexity._slope_to_class(3.0), "O(n^3)")

    def test_verdict(self):
        self.assertEqual(complexity._verdict("O(n)", "O(n)"), "optimal")
        self.assertEqual(complexity._verdict("O(n^2)", "O(n)"), "suboptimal")
        self.assertEqual(complexity._verdict("O(1)", "O(n)"), "optimal")
        self.assertEqual(complexity._verdict("O(n)", None), "unknown")


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
        self.assertIn("Optimal", md)
        self.assertIn("Suboptimal", md)
        self.assertIn("2m 5s", md)            # 125 seconds formatted
        self.assertIn("img.shields.io", md)   # badges present


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
                              topic="Arrays & Hashing", optimality="optimal")
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


if __name__ == "__main__":
    unittest.main()
