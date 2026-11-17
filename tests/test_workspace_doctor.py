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
            self.assertIn("workspace_doctor v0.3.0", result.stdout)

    def make_adopted(self, root, rel, title, **kwargs):
        topic_dir = make_topic(root, "", rel, title, entry_name="CONTEXT.md", **kwargs)
        adopted = root / ".agents" / "adopted.txt"
        previous = read_text(adopted) if adopted.exists() else "# adopted\n"
        write_text(adopted, previous + rel + "\n")
        return topic_dir

    def test_adopted_topic_is_indexed_found_and_allowed_in_place(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            write_text(root / "old-app" / "README.md", "# Old App\n\nproject readme without front matter\n")
            self.make_adopted(root, "old-app", "老应用", aliases=["legacy app"])
            self.make_adopted(root, "projects/api", "接口服务")

            write_result = run_doctor(root, "index", "--write")
            self.assertEqual(write_result.returncode, 0, write_result.stderr + write_result.stdout)
            readme = read_text(root / "README.md")
            self.assertIn("(old-app/CONTEXT.md)", readme)
            self.assertIn("(projects/api/CONTEXT.md)", readme)

            result, data = run_json(root, "check")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(data["warnings"], [])

            _, by_alias = run_json(root, "find", "legacy")
            self.assertEqual(by_alias["results"][0]["entry"], "old-app/CONTEXT.md")
            _, by_path = run_json(root, "find", "projects/api")
            self.assertEqual(by_path["results"][0]["title"], "接口服务")
            self.assertEqual(read_text(root / "old-app" / "README.md"), "# Old App\n\nproject readme without front matter\n")

    def test_adopted_registry_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            make_topic(root, "work", "kept", "Kept")
            (root / "no-entry").mkdir()
            write_text(
                root / ".agents" / "adopted.txt",
                "gone\n../outside\nwork/kept\nno-entry\n",
            )
            run_doctor(root, "index", "--write")
            result, data = run_json(root, "check")
            self.assertEqual(result.returncode, 1)
            codes = sorted(item["code"] for item in data["errors"])
            self.assertEqual(codes, ["adopted_invalid", "adopted_invalid", "adopted_missing", "missing_entry"])

    def test_adopted_topic_cannot_be_archived(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            self.make_adopted(root, "old-app", "老应用", status="archived")
            _, data = run_json(root, "check")
            self.assertIn("status_location_conflict", [item["code"] for item in data["errors"]])

    def test_scan_lists_existing_content_without_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            write_text(root / "old-app" / "AGENTS.md", "rules\n")
            write_text(root / "old-app" / "package.json", "{}\n")
            write_text(root / "old-app" / "src" / "main.js", "x\n")
            write_text(root / "old-app" / "node_modules" / "dep" / "index.js", "skipped\n")
            (root / "old-app" / ".git").mkdir()
            write_text(root / "notes.txt", "note\n")
            before = read_text(root / ".agents" / "root-allowlist.txt")

            result, data = run_json(root, "scan")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(data["unregistered"], ["notes.txt", "old-app"])
            directory = data["directories"][0]
            self.assertEqual(directory["name"], "old-app")
            self.assertEqual(directory["files"], 3)
            self.assertEqual(directory["markers"], ["git", "project", "agent"])
            self.assertEqual(data["files"][0]["name"], "notes.txt")
            self.assertEqual(data["written"], 0)
            self.assertEqual(read_text(root / ".agents" / "root-allowlist.txt"), before)

            text_result = run_doctor(root, "scan", "--limit", "0")
            self.assertEqual(text_result.returncode, 0)
            self.assertIn("未登记 2 个", text_result.stdout)
            self.assertNotIn("- old-app/", text_result.stdout)

    def test_scan_write_allowlist_appends_once_and_keeps_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_workspace(root)
            write_text(root / ".agents" / "root-allowlist.txt", "# user allowlist\nkept-item")
            write_text(root / "old-app" / "main.py", "print(1)\n")
            write_text(root / "notes.txt", "note\n")
            self.make_adopted(root, "legacy", "Legacy")

            result, data = run_json(root, "scan", "--write-allowlist")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(data["written"], 2)
            self.assertEqual(
                read_text(root / ".agents" / "root-allowlist.txt"),
                "# user allowlist\nkept-item\nnotes.txt\nold-app\n",
            )
            states = {item["name"]: item["state"] for item in data["directories"]}
            self.assertEqual(states, {"legacy": "adopted", "old-app": "allowlisted"})

            _, again = run_json(root, "scan", "--write-allowlist")
            self.assertEqual(again["written"], 0)
            self.assertEqual(again["unregistered"], [])
            self.assertTrue((root / "old-app" / "main.py").is_file())

            run_doctor(root, "index", "--write")
            check_result, check_data = run_json(root, "check")
            self.assertEqual(check_result.returncode, 0, check_result.stdout)
            self.assertEqual(check_data["warnings"], [])

    def make_messy_workspace(self, root):
        init_workspace(root)
        write_text(root / "a.txt", "a\n")
        write_text(root / "报告 final.docx", "b\n")
        write_text(root / "新建文件夹 (2)" / "x" / "c.md", "c\n")
        write_text(root / "proj" / "main.py", "d\n")

    def write_plan(self, root, lines):
        write_text(root / ".agents" / "move-plan.tsv", "# plan\n" + "\n".join(lines) + "\n")
        return ".agents/move-plan.tsv"

    def test_move_dry_run_then_apply_records_and_where_resolves(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_messy_workspace(root)
            plan = self.write_plan(
                root,
                [
                    "a.txt\twork/2026-01-01-misc/a.txt",
                    "报告 final.docx -> work/2026-01-01-misc/报告 final.docx",
                    "新建文件夹 (2)\twork/2026-02-02-notes",
                ],
            )

            dry, dry_data = run_json(root, "move", "--plan", plan)
            self.assertEqual(dry.returncode, 0, dry.stdout)
            self.assertFalse(dry_data["applied"])
            self.assertTrue((root / "a.txt").is_file())
            self.assertFalse((root / ".agents" / "moves.tsv").exists())

            applied, applied_data = run_json(root, "move", "--plan", plan, "--apply")
            self.assertEqual(applied.returncode, 0, applied.stdout)
            self.assertEqual(len(applied_data["moved"]), 3)
            self.assertFalse((root / "a.txt").exists())
            self.assertEqual(read_text(root / "work" / "2026-02-02-notes" / "x" / "c.md"), "c\n")

            result, data = run_json(
                root, "where", "新建文件夹 (2)\\x\\c.md", str(root / "a.txt"), "proj/main.py", "gone.txt"
            )
            self.assertEqual(result.returncode, 1)
            by_query = {item["query"]: item for item in data["results"]}
            self.assertEqual(by_query["新建文件夹 (2)/x/c.md"]["current"], "work/2026-02-02-notes/x/c.md")
            self.assertEqual(by_query["a.txt"]["current"], "work/2026-01-01-misc/a.txt")
            self.assertFalse(by_query["proj/main.py"]["moved"])
            self.assertTrue(by_query["proj/main.py"]["exists"])
            self.assertFalse(by_query["gone.txt"]["exists"])

    def test_move_chain_is_followed_and_undo_restores_last_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_messy_workspace(root)
            first = self.write_plan(root, ["proj\twork/2026-01-01-proj"])
            self.assertEqual(run_doctor(root, "move", "--plan", first, "--apply").returncode, 0)
            second = self.write_plan(root, ["work/2026-01-01-proj/main.py\twork/2026-03-03-tools/main.py"])
            self.assertEqual(run_doctor(root, "move", "--plan", second, "--apply").returncode, 0)

            _, data = run_json(root, "where", "proj/main.py")
            self.assertEqual(data["results"][0]["current"], "work/2026-03-03-tools/main.py")

            undo, undo_data = run_json(root, "move", "--undo")
            self.assertEqual(undo.returncode, 0, undo.stdout)
            self.assertEqual(len(undo_data["moved"]), 1)
            self.assertTrue((root / "work" / "2026-01-01-proj" / "main.py").is_file())
            _, after = run_json(root, "where", "proj/main.py")
            self.assertEqual(after["results"][0]["current"], "work/2026-01-01-proj/main.py")

    def test_move_rejects_invalid_plan_without_moving_anything(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_messy_workspace(root)
            write_text(root / "taken.txt", "keep\n")
            plan = self.write_plan(
                root,
                [
                    "a.txt\twork/ok/a.txt",
                    "proj\tproj/sub",
                    "missing\twork/x",
                    "AGENTS.md\twork/y",
                    "报告 final.docx\ttaken.txt",
                    "proj/main.py\twork/z.py",
                    "proj\twork/p",
                    "a.txt\t../outside.txt",
                    "新建文件夹 (2)\t.agents/hidden",
                ],
            )
            result, data = run_json(root, "move", "--plan", plan, "--apply")
            self.assertEqual(result.returncode, 1)
            self.assertFalse(data["applied"])
            self.assertEqual({item["code"] for item in data["errors"]}, {"plan_invalid"})
            self.assertEqual(len(data["errors"]), 7)
            self.assertTrue((root / "a.txt").is_file())
            self.assertEqual(read_text(root / "taken.txt"), "keep\n")
            self.assertFalse((root / ".agents" / "moves.tsv").exists())
            self.assertFalse((root / "work").exists())

    def test_scan_marks_abspath_env_cache_and_nested_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            init_workspace(root)
            backslash = str(root).replace("/", "\\")
            write_text(root / "kepu" / "SKILL.md", "run {}\\bin\\x.mjs\n".format(backslash.upper()))
            write_text(root / "kepu" / ".venv" / "pyvenv.cfg", "home = x\n")
            write_text(root / "kepu" / "data.json", '{"p": "%s"}\n' % backslash.replace("\\", "\\\\"))
            write_text(root / "plain" / "a.txt", "nothing here\n")
            write_text(root / "deep" / "tools" / "runtime" / ".venv" / "pyvenv.cfg", "home = x\n")
            write_text(root / ".npm-cache" / "_logs" / "d.log", "cwd {}\n".format(str(root).replace("\\", "/")))
            write_text(root / "loose.md", "see {}\n".format(backslash))
            write_text(root / "other.md", "see {}2\n".format(backslash[:-1]))

            result, data = run_json(root, "scan")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            dirs = {item["name"]: item for item in data["directories"]}
            self.assertEqual(dirs["kepu"]["markers"], ["agent", "env", "abspath"])
            self.assertEqual(dirs["kepu"]["abspath_files"], 2)
            self.assertEqual(dirs["plain"]["markers"], [])
            self.assertEqual(dirs["deep"]["markers"], ["env"])
            self.assertEqual(dirs[".npm-cache"]["markers"], ["cache", "abspath"])
            files = {item["name"]: item for item in data["files"]}
            self.assertEqual(files["loose.md"]["markers"], ["abspath"])
            self.assertEqual(files["other.md"]["markers"], [])

            text = run_doctor(root, "scan").stdout
            self.assertIn("写死绝对路径的文件 2 个", text)
            self.assertNotIn("x.mjs", text)

    def test_scan_subdirectory_lists_next_level_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_messy_workspace(root)
            result, data = run_json(root, "scan", "新建文件夹 (2)")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual([item["name"] for item in data["directories"]], ["x"])
            self.assertEqual(data["files"], [])
            self.assertEqual(data["unregistered"], [])
            self.assertEqual(run_doctor(root, "scan", "nope").returncode, 2)


if __name__ == "__main__":
    unittest.main()
