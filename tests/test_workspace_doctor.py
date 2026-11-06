import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "workspace-template" / ".agents" / "tools" / "workspace_doctor.py"
START = "<!-- ai-workspace-kit:topic-index:start -->"
END = "<!-- ai-workspace-kit:topic-index:end -->"


def write_text(path, text, newline=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as handle:
        handle.write(text)


def read_text(path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def inline_list(values):
    return "[" + ", ".join(values) + "]"


def write_readme(root, block_content="暂无主题", prefix="", suffix="", eol="\n"):
    text = prefix + START + eol + block_content + eol + END + suffix
    write_text(root / "README.md", text)
    return text


def init_workspace(root, eol="\n"):
    write_text(root / "AGENTS.md", "# Workspace\n\nRules.\n")
    write_text(root / ".agents" / "root-allowlist.txt", "# user allowlist\n")
    write_readme(root, eol=eol)


def make_topic(
    root,
    section,
    name,
    title,
    status="active",
    updated="2026-01-01",
    aliases=None,
    tags=None,
    entry_name="README.md",
    h1=None,
    body="",
):
    aliases = aliases or []
    tags = tags or []
    heading = h1 if h1 is not None else title
    text = (
        "---\n"
        "title: {}\n"
        "aliases: {}\n"
        "tags: {}\n"
        "status: {}\n"
        "updated: {}\n"
        "---\n\n"
        "# {}\n\n"
        "{}\n"
    ).format(title, inline_list(aliases), inline_list(tags), status, updated, heading, body)
    topic_dir = root / section / name
    write_text(topic_dir / entry_name, text)
    return topic_dir


def run_doctor(root, *args):
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    command = [sys.executable, str(SCRIPT), "--root", str(root)]
    command.extend(args)
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_json(root, *args):
    result = run_doctor(root, *(list(args) + ["--json"]))
    return result, json.loads(result.stdout)


class WorkspaceDoctorTests(unittest.TestCase):
    def test_empty_workspace_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            result, data = run_json(root, "check")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(data["ok"])
            self.assertEqual(data["errors"], [])

    def test_root_file_is_warning(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            write_text(root / "notes.txt", "ordinary file\n")
            result, data = run_json(root, "check")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(data["ok"])
            self.assertTrue(any(item["code"] == "root_not_allowed" for item in data["warnings"]))

    def test_metadata_errors_are_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            (root / "work" / "no-entry").mkdir(parents=True)
            no_fields = root / "work" / "no-fields"
            write_text(no_fields / "README.md", "# No fields\n")
            bad_status = root / "work" / "bad-status"
            write_text(
                bad_status / "README.md",
                "---\ntitle: Bad\nstatus: unknown\nupdated: 2026-99-99\n---\n\n# Bad\n",
            )
            make_topic(root, "archive", "active-topic", "Active in archive", status="active")

            result, data = run_json(root, "check")
            self.assertEqual(result.returncode, 1)
            codes = {item["code"] for item in data["errors"]}
            self.assertIn("missing_entry", codes)
            self.assertIn("missing_field", codes)
            self.assertIn("invalid_status", codes)
            self.assertIn("invalid_updated", codes)
            self.assertIn("status_location_conflict", codes)

    def test_context_entry_wins_over_readme(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            topic = root / "work" / "context-priority"
            write_text(topic / "README.md", "# Project README\n\nThis is a project description.\n")
            write_text(
                topic / "CONTEXT.md",
                "---\ntitle: Context Wins\naliases: []\ntags: []\nstatus: active\nupdated: 2026-01-01\n---\n\n# Context Wins\n",
            )
            write_result = run_doctor(root, "index", "--write")
            self.assertEqual(write_result.returncode, 0, write_result.stderr + write_result.stdout)
            check_result, data = run_json(root, "check")
            self.assertEqual(check_result.returncode, 0, check_result.stderr + check_result.stdout)
            self.assertTrue(data["ok"])
            find_result, find_data = run_json(root, "find", "context")
            self.assertEqual(find_result.returncode, 0)
            self.assertEqual(find_data["results"][0]["title"], "Context Wins")
            self.assertTrue(find_data["results"][0]["entry"].endswith("CONTEXT.md"))

    def test_index_write_preserves_outside_and_newlines(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            prefix = "# Workspace\r\n\r\nIntro with `inline code`.\r\n\r\n"
            suffix = "\r\n\r\nTail text stays exactly.\r\n"
            before = write_readme(root, block_content="old content", prefix=prefix, suffix=suffix, eol="\r\n")
            start = before.index(START)
            end = before.index(END) + len(END)
            old_prefix = before[:start]
            old_suffix = before[end:]

            make_topic(root, "work", "alpha", "Alpha")
            result = run_doctor(root, "index", "--write")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            after = read_text(root / "README.md")
            self.assertTrue(after.startswith(old_prefix))
            self.assertTrue(after.endswith(old_suffix))
            self.assertIn("Alpha", after)
            self.assertNotIn("old content", after)
            self.assertIn("\r\n", after)
            self.assertNotIn("Intro with `inline code`.\n", after)

    def test_index_sorting_and_markdown_escaping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            make_topic(root, "work", "zeta", "Zeta", updated="2026-01-01")
            make_topic(root, "work", "alpha", "A | B", updated="2026-02-01", tags=["x|y", "z"])
            make_topic(root, "work", "newer", "Newer", updated="2026-03-01")
            make_topic(root, "work", "paused", "Paused", status="paused", updated="2026-04-01")
            make_topic(root, "work", "done", "Done", status="done", updated="2026-05-01")
            make_topic(root, "archive", "old", "Old", status="archived", updated="2026-06-01")

            result = run_doctor(root, "index", "--write")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            text = read_text(root / "README.md")
            positions = [text.index(name) for name in ("A \\| B", "Newer", "Zeta", "Paused", "Done", "Old")]
            self.assertEqual(positions, sorted(positions))
            self.assertNotIn("| 更新 |", text)
            self.assertIn("| 主题 | 入口 | 状态 | 标签 |", text)
            self.assertIn("x\\|y, z", text)
            self.assertIn("进行中", text)

    def test_updated_change_does_not_invalidate_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            topic = make_topic(root, "work", "alpha", "Alpha", updated="2026-01-01")
            write_result = run_doctor(root, "index", "--write")
            self.assertEqual(write_result.returncode, 0, write_result.stderr + write_result.stdout)

            entry = topic / "README.md"
            entry_text = read_text(entry).replace("updated: 2026-01-01", "updated: 2026-03-03")
            write_text(entry, entry_text)

            check_result, check_data = run_json(root, "check")
            self.assertEqual(check_result.returncode, 0, check_result.stderr + check_result.stdout)
            self.assertTrue(check_data["ok"])
            index_result, index_data = run_json(root, "index")
            self.assertEqual(index_result.returncode, 0, index_result.stderr + index_result.stdout)
            self.assertFalse(index_data["changed"])

    def test_index_write_with_metadata_errors_returns_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            make_topic(root, "work", "valid", "Valid Topic")
            bad = root / "work" / "bad"
            write_text(
                bad / "README.md",
                "---\ntitle: Bad Topic\nstatus: invalid\nupdated: 2026-01-01\n---\n\n# Bad Topic\n",
            )

            result = run_doctor(root, "index", "--write", "--json")
            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            data = json.loads(result.stdout)
            self.assertTrue(data["written"])
            self.assertTrue(any(item["code"] == "invalid_status" for item in data["errors"]))
            text = read_text(root / "README.md")
            self.assertIn("Valid Topic", text)
            self.assertNotIn("Bad Topic", text)

    def test_find_matches_and_orders_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            make_topic(root, "work", "exact", "Exact Topic", aliases=["linux"], tags=["shell"])
            make_topic(root, "work", "contains", "Linux Notes", tags=[])
            make_topic(root, "work", "tag", "Tag Topic", tags=["Linux"])
            make_topic(root, "work", "linux-dir", "Directory Topic")
            make_topic(root, "work", "h1", "Hidden Topic", h1="Hidden Linux Heading")

            result, data = run_json(root, "find", "linux")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            titles = [item["title"] for item in data["results"]]
            self.assertEqual(titles[:4], ["Exact Topic", "Hidden Topic", "Linux Notes", "Tag Topic"])
            self.assertIn("Directory Topic", titles)
            self.assertIn("别名", data["results"][0]["matched_fields"])

            h1_result, h1_data = run_json(root, "find", "hidden linux")
            self.assertEqual(h1_result.returncode, 0)
            self.assertEqual(h1_data["results"][0]["title"], "Hidden Topic")

    def test_find_requires_all_terms_and_prefers_exact_phrase(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            make_topic(
                root,
                "work",
                "linux-learning",
                "Linux 命令学习",
                aliases=["shell 学习笔记"],
            )
            make_topic(root, "work", "exact-phrase", "Linux 笔记")
            make_topic(root, "work", "linux-only", "Linux Only")

            result, data = run_json(root, "find", "linux 笔记")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            titles = [item["title"] for item in data["results"]]
            self.assertEqual(titles[0], "Linux 笔记")
            self.assertIn("Linux 命令学习", titles)
            self.assertNotIn("Linux Only", titles)
            combined = next(item for item in data["results"] if item["title"] == "Linux 命令学习")
            self.assertIn("标题", combined["matched_fields"])
            self.assertIn("别名", combined["matched_fields"])

    def test_links_check_relative_and_skip_external(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            make_topic(
                root,
                "work",
                "links",
                "Links",
                body=(
                    "[ok](../../AGENTS.md)\n"
                    "[broken](missing.md)\n"
                    "[external](https://example.com/not-local)\n"
                    "[anchor](#section)\n"
                ),
            )
            write_result = run_doctor(root, "index", "--write")
            self.assertEqual(write_result.returncode, 0, write_result.stderr + write_result.stdout)
            result, data = run_json(root, "check")
            self.assertEqual(result.returncode, 1)
            broken = [item for item in data["errors"] if item["code"] == "broken_link"]
            self.assertEqual(len(broken), 1)
            self.assertIn("missing.md", broken[0]["message"])
            self.assertFalse(any("example.com" in item["message"] for item in data["errors"]))

    def test_index_write_refuses_missing_or_duplicate_markers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            no_markers = "# Workspace\n\nNo markers here.\n"
            write_text(root / "README.md", no_markers)
            result = run_doctor(root, "index", "--write")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(read_text(root / "README.md"), no_markers)

            duplicate = "# Workspace\n\n" + START + "\n暂无主题\n" + START + "\n暂无主题\n" + END + "\n"
            write_text(root / "README.md", duplicate)
            result = run_doctor(root, "index", "--write", "--json")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(read_text(root / "README.md"), duplicate)
            data = json.loads(result.stdout)
            self.assertFalse(data["ok"])

    def test_json_outputs_are_parseable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            make_topic(root, "work", "json-topic", "JSON Topic")

            check_result, check_data = run_json(root, "check")
            self.assertEqual(check_result.returncode, 1)
            self.assertFalse(check_data["ok"])
            self.assertIsInstance(check_data["errors"], list)

            index_result = run_doctor(root, "index", "--json")
            self.assertEqual(index_result.returncode, 1)
            index_data = json.loads(index_result.stdout)
            self.assertTrue(index_data["changed"])
            self.assertFalse(index_data["written"])

            find_result, find_data = run_json(root, "find", "json")
            self.assertEqual(find_result.returncode, 0)
            self.assertEqual(find_data["results"][0]["title"], "JSON Topic")

    def test_version_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            result = run_doctor(root, "--version")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("workspace_doctor v0.2.1", result.stdout)


if __name__ == "__main__":
    unittest.main()
