"""单元测试：零外部依赖，用 unittest.mock 打桩网络调用。"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from research_pipeline.arxiv import parse_atom
from research_pipeline.cli import build_parser, main
from research_pipeline.config import Config, load_config
from research_pipeline.models import ImportResult, Paper
from research_pipeline.notes import filename, render, write_notes
from research_pipeline.pipeline import _extract_collection_key, import_papers
from research_pipeline.zotero import ZoteroClient


SAMPLE_ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v1</id>
    <title>  A  Sample   Paper on\n Detection </title>
    <summary>We propose &amp; test a method for object detection.</summary>
    <published>2024-01-15T00:00:00Z</published>
    <author><name>Zhang, S.</name></author>
    <author><name>Li, W.</name></author>
  </entry>
</feed>"""


class TestArxivParse(unittest.TestCase):
    def test_parse_atom(self):
        papers = parse_atom(SAMPLE_ATOM)
        self.assertEqual(len(papers), 1)
        p = papers[0]
        self.assertEqual(p.arxiv_id, "2401.01234v1")
        self.assertEqual(p.identifier, "arXiv:2401.01234v1")
        self.assertEqual(p.title, "A Sample Paper on Detection")
        self.assertEqual(p.year, "2024")
        self.assertEqual(p.authors, ["Zhang, S.", "Li, W."])
        self.assertIn("&", p.abstract)

    def test_parse_empty(self):
        self.assertEqual(parse_atom("<feed></feed>"), [])


class TestNotes(unittest.TestCase):
    def make_paper(self):
        return Paper(
            title="A Study: Small Objects", authors=["Zhang, S.", "Li, W."],
            year="2025", source="arXiv", zotero_key="ABCD1234",
            collection="检测/小目标", keywords=["small", "detection"],
            main_findings="Method improves AP by 5 points.",
            research_question="How to detect small objects?",
        )

    def test_render_replaces_placeholders(self):
        out = render(self.make_paper(), created="2026-01-01")
        self.assertNotIn("{{", out)
        self.assertIn("Method improves AP by 5 points.", out)
        self.assertIn("@ABCD1234", out)
        self.assertEqual(out.count("## "), 11)

    def test_filename_sanitizes(self):
        p = self.make_paper()
        # 规则：取标题冒号前的短名
        self.assertEqual(filename(p), "2025-A Study.md")
        # 冒号 / 非法字符应被清理
        p2 = Paper(title="A/B:C? D", year="2024")
        self.assertEqual(filename(p2), "2024-A_B.md")

    def test_write_notes_skip_existing(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.make_paper()
            first = write_notes([p], d, created="2026-01-01")
            self.assertEqual(len(first), 1)
            second = write_notes([p], d)  # 默认跳过
            self.assertEqual(len(second), 0)
            third = write_notes([p], d, overwrite=True)
            self.assertEqual(len(third), 1)


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = Config()
        self.assertEqual(cfg.batch_size, 3)
        self.assertFalse(cfg.save_attachments)

    def test_validate_bad_batch(self):
        with self.assertRaises(ValueError):
            Config(batch_size=0).validate()

    def test_env_override(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["ZOTERO_MCP_URL"] = "http://localhost:9999/mcp"
            try:
                cfg = load_config(os.path.join(d, "missing.json"))
                self.assertEqual(cfg.zotero_mcp_url, "http://localhost:9999/mcp")
            finally:
                del os.environ["ZOTERO_MCP_URL"]


class TestPipelineHelpers(unittest.TestCase):
    def test_extract_collection_key_variants(self):
        self.assertEqual(_extract_collection_key([{"name": "A", "key": "K1"}], "A"), "K1")
        self.assertEqual(_extract_collection_key({"collections": [{"title": "B", "key": "K2"}]}, "B"), "K2")
        self.assertIsNone(_extract_collection_key([], "X"))

    def test_import_papers_batches(self):
        class FakeClient:
            def __init__(self):
                self.calls = []
            def add_by_identifier(self, ids, **kwargs):
                self.calls.append(ids)
                return {"succeeded": ids}
        fake = FakeClient()
        result = import_papers(fake, ["a", "b", "c", "d"], "KEY", batch_size=3)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(len(result.succeeded), 4)
        self.assertIn("成功 4", result.summary())


class TestCLI(unittest.TestCase):
    def test_parser_builds(self):
        p = build_parser()
        self.assertIsNotNone(p)

    def test_init_command(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "cfg.json")
            code = main(["init", path])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as f:
                self.assertIn("zotero_mcp_url", json.load(f))

    def test_notes_command(self):
        with tempfile.TemporaryDirectory() as d:
            inp = os.path.join(d, "papers.json")
            with open(inp, "w", encoding="utf-8") as f:
                json.dump([{
                    "title": "CLI Test Paper", "authors": ["A"], "year": "2025",
                    "main_findings": "Finding", "zotero_key": "K",
                }], f)
            outdir = os.path.join(d, "notes")
            code = main(["--config", os.path.join(d, "nope.json"), "notes", inp, "--out", outdir])
            self.assertEqual(code, 0)
            files = list(Path(outdir).glob("*.md"))
            self.assertEqual(len(files), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
