#!/usr/bin/env python3
"""检查、生成和查询 AI 工作区主题索引。

只使用 Python 3.9+ 标准库。脚本默认假设自己位于
<工作区根>/.agents/tools/workspace_doctor.py，也可以用 --root 指定根目录。
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import unquote


START_MARKER = "<!-- ai-workspace-kit:topic-index:start -->"
END_MARKER = "<!-- ai-workspace-kit:topic-index:end -->"
KIT_VERSION = "v0.2.1"

DEFAULT_ROOT_ENTRIES = {
    "AGENTS.md",
    "README.md",
    ".agents",
    "work",
    "archive",
    "inbox",
    ".git",
    ".gitignore",
    ".gitattributes",
    "CLAUDE.md",
    "GEMINI.md",
    ".claude",
    ".gemini",
    ".codex",
    ".cursor",
    ".vscode",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}

STATUS_ORDER = {"active": 0, "paused": 1, "done": 2, "archived": 3}
STATUS_LABEL = {
    "active": "进行中",
    "paused": "暂停",
    "done": "已完成",
    "archived": "已归档",
}

INVALID_NAME_CHARS = set('\\/:*?"<>|')
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
H1_RE = re.compile(r"^#\s+(.+?)\s*#*\s*$")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\n]+)\)")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class WorkspaceError(Exception):
    """无法继续执行的输入或读写错误。"""


@dataclass
class Topic:
    section: str
    directory: Path
    name: str
    entry: Optional[Path] = None
    meta: Dict[str, object] = field(default_factory=dict)
    h1: Optional[str] = None
    errors: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class BlockLocation:
    ok: bool
    block: str = ""
    start: int = 0
    end: int = 0
    code: str = ""
    message: str = ""


def make_issue(code: str, path: str, message: str) -> Dict[str, str]:
    return {"code": code, "path": path, "message": message}


def relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceError("无法按 UTF-8 读取 {}: {}".format(path, exc)) from exc
    except OSError as exc:
        raise WorkspaceError("无法读取 {}: {}".format(path, exc)) from exc


def safe_is_file(root: Path, path: Path) -> bool:
    try:
        if path.is_symlink():
            try:
                path.resolve().relative_to(root)
            except ValueError:
                return False
            except (OSError, RuntimeError):
                return False
        return path.is_file()
    except OSError:
        return False


def path_within_root(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root)
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def detect_eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    if value[:1] in ("'", '"') or value[-1:] in ("'", '"'):
        raise ValueError("引号未闭合")
    return value


def parse_inline_list(value: str) -> List[str]:
    if not value.startswith("[") or not value.endswith("]"):
        raise ValueError("行内列表必须用 [ ] 包围")
    inner = value[1:-1].strip()
    if not inner:
        return []
    items: List[str] = []
    for part in inner.split(","):
        item = part.strip()
        if not item:
            raise ValueError("行内列表包含空项")
        if any(char in item for char in "[]{}"):
            raise ValueError("行内列表项包含不支持的括号")
        item = strip_quotes(item)
        if not item:
            raise ValueError("行内列表项不能为空")
        items.append(item)
    return items


def parse_front_matter(path: Path, rel_path: str) -> Tuple[Dict[str, object], Optional[str], List[Dict[str, str]]]:
    """解析本工具支持的 front matter 子集，不猜测复杂 YAML。"""
    errors: List[Dict[str, str]] = []
    text = read_text(path)
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        errors.append(make_issue("missing_front_matter", rel_path, "主题入口缺少 YAML front matter"))
        return {}, find_h1(lines), errors

    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        errors.append(make_issue("invalid_front_matter", rel_path, "front matter 缺少结束标记 ---"))
        return {}, find_h1(lines), errors

    meta: Dict[str, object] = {}
    for line_number, raw in enumerate(lines[1:closing], start=2):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[0].isspace():
            errors.append(
                make_issue("invalid_front_matter", rel_path, "第 {} 行使用了不支持的缩进 YAML".format(line_number))
            )
            continue
        if ":" not in raw:
            errors.append(
                make_issue("invalid_front_matter", rel_path, "第 {} 行不是 key: value 格式".format(line_number))
            )
            continue
        key, raw_value = raw.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not KEY_RE.match(key):
            errors.append(
                make_issue("invalid_front_matter", rel_path, "第 {} 行字段名无效".format(line_number))
            )
            continue
        if key in meta:
            errors.append(
                make_issue("invalid_front_matter", rel_path, "字段 {} 重复出现".format(key))
            )
            continue
        try:
            if value.startswith("["):
                meta[key] = parse_inline_list(value)
            else:
                if value.startswith(("{", "&", "*", "!", "|", ">")) or value.endswith("}"):
                    raise ValueError("不支持的 YAML 值")
                if "[" in value or "]" in value:
                    raise ValueError("不支持的 YAML 值")
                meta[key] = strip_quotes(value)
        except ValueError as exc:
            errors.append(
                make_issue(
                    "invalid_front_matter",
                    rel_path,
                    "第 {} 行无法解析 {}: {}".format(line_number, key, exc),
                )
            )

    return meta, find_h1(lines[closing + 1 :]), errors


def find_h1(lines: Sequence[str]) -> Optional[str]:
    for line in lines:
        match = H1_RE.match(line)
        if match:
            return match.group(1).strip()
    return None


def validate_topic(topic: Topic, root: Path) -> None:
    rel = relative_path(root, topic.directory)
    entry_rel = relative_path(root, topic.entry) if topic.entry else rel
    meta = topic.meta

    title = meta.get("title")
    if "title" not in meta:
        topic.errors.append(make_issue("missing_field", entry_rel, "缺少必需字段 title"))
    elif not isinstance(title, str) or not title.strip():
        topic.errors.append(make_issue("invalid_field", entry_rel, "title 必须是非空字符串"))

    for list_name in ("aliases", "tags"):
        value = meta.get(list_name, [])
        if not isinstance(value, list):
            topic.errors.append(make_issue("invalid_field", entry_rel, "{} 必须是行内列表".format(list_name)))
        elif any(not isinstance(item, str) or not item.strip() for item in value):
            topic.errors.append(make_issue("invalid_field", entry_rel, "{} 的列表项必须是非空字符串".format(list_name)))

    status = meta.get("status")
    if "status" not in meta:
        topic.errors.append(make_issue("missing_field", entry_rel, "缺少必需字段 status"))
    elif not isinstance(status, str) or status not in STATUS_ORDER:
        topic.errors.append(make_issue("invalid_status", entry_rel, "status 必须是 active、paused、done 或 archived"))

    updated = meta.get("updated")
    if "updated" not in meta:
        topic.errors.append(make_issue("missing_field", entry_rel, "缺少必需字段 updated"))
    elif not isinstance(updated, str) or not DATE_RE.match(updated):
        topic.errors.append(make_issue("invalid_updated", entry_rel, "updated 必须使用 YYYY-MM-DD 格式"))
    else:
        try:
            _datetime.date.fromisoformat(updated)
        except ValueError:
            topic.errors.append(make_issue("invalid_updated", entry_rel, "updated 不是有效日期"))

    if isinstance(status, str) and status in STATUS_ORDER:
        if topic.section == "work" and status == "archived":
            topic.errors.append(make_issue("status_location_conflict", entry_rel, "work/ 中的主题不能是 archived"))
        if topic.section == "archive" and status != "archived":
            topic.errors.append(make_issue("status_location_conflict", entry_rel, "archive/ 中的主题必须是 archived"))


def scan_topics(root: Path) -> Tuple[List[Topic], List[Dict[str, str]], List[Dict[str, str]]]:
    topics: List[Topic] = []
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    for section in ("work", "archive"):
        section_path = root / section
        if not section_path.exists():
            continue
        if not path_within_root(root, section_path):
            continue
        if not section_path.is_dir():
            errors.append(make_issue("invalid_section", section, "{} 必须是目录".format(section)))
            continue
        try:
            with os.scandir(section_path) as iterator:
                entries = sorted(iterator, key=lambda item: item.name.casefold())
        except OSError as exc:
            raise WorkspaceError("无法读取 {}: {}".format(section_path, exc)) from exc

        for entry in entries:
            if entry.is_symlink():
                continue
            if not entry.is_dir(follow_symlinks=False):
                errors.append(
                    make_issue(
                        "non_directory_topic",
                        "{}/{}".format(section, entry.name),
                        "{} 的直接子项必须是主题目录".format(section),
                    )
                )
                continue

            directory = Path(entry.path)
            topic = Topic(section=section, directory=directory, name=entry.name)
            if any(char.isspace() for char in entry.name) or any(char in INVALID_NAME_CHARS for char in entry.name):
                topic.warnings.append(
                    make_issue(
                        "invalid_directory_name",
                        "{}/{}".format(section, entry.name),
                        "主题目录名包含空白或特殊字符",
                    )
                )

            context = directory / "CONTEXT.md"
            readme = directory / "README.md"
            if safe_is_file(root, context):
                topic.entry = context
            elif safe_is_file(root, readme):
                topic.entry = readme

            if topic.entry is None:
                topic.errors.append(
                    make_issue(
                        "missing_entry",
                        relative_path(root, directory),
                        "主题缺少 CONTEXT.md 或 README.md 入口",
                    )
                )
            else:
                entry_rel = relative_path(root, topic.entry)
                meta, h1, front_matter_errors = parse_front_matter(topic.entry, entry_rel)
                topic.meta = meta
                topic.h1 = h1
                topic.errors.extend(front_matter_errors)

            if topic.entry is not None:
                validate_topic(topic, root)
            topics.append(topic)
            errors.extend(topic.errors)
            warnings.extend(topic.warnings)

    return topics, errors, warnings


def duplicate_warnings(topics: Iterable[Topic], root: Path) -> List[Dict[str, str]]:
    warnings: List[Dict[str, str]] = []
    seen: List[Tuple[Topic, str, str]] = []
    for topic in topics:
        values: List[Tuple[str, str]] = []
        title = topic.meta.get("title")
        if isinstance(title, str) and title.strip():
            values.append(("title", title))
        aliases = topic.meta.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and alias.strip():
                    values.append(("alias", alias))

        for kind, value in values:
            key = value.strip().casefold()
            for previous_topic, previous_kind, previous_value in seen:
                if previous_topic is topic:
                    continue
                if previous_value.strip().casefold() != key:
                    continue
                code = "duplicate_title" if kind == "title" else "duplicate_alias"
                warnings.append(
                    make_issue(
                        code,
                        relative_path(root, topic.directory),
                        "{}“{}”与其他主题的{}重复".format(
                            "标题" if kind == "title" else "别名",
                            value,
                            "标题" if previous_kind == "title" else "别名",
                        ),
                    )
                )
            seen.append((topic, kind, value))
    return warnings


def load_allowlist(root: Path) -> List[str]:
    path = root / ".agents" / "root-allowlist.txt"
    if not path.exists():
        return []
    if not path.is_file():
        raise WorkspaceError("{} 不是文件".format(path))
    values: List[str] = []
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            values.append(stripped)
    return values


def escape_cell(value: str) -> str:
    value = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return value.replace("|", "\\|")


def sort_key(topic: Topic) -> Tuple[int, str, str]:
    status = topic.meta.get("status")
    title = topic.meta.get("title")
    title_text = title if isinstance(title, str) else topic.name
    return (
        STATUS_ORDER.get(str(status), 99),
        title_text.casefold(),
        title_text,
    )


def render_index_content(topics: Sequence[Topic], root: Path) -> str:
    valid = [topic for topic in topics if not topic.errors and topic.entry is not None]
    valid.sort(key=sort_key)
    if not valid:
        return "暂无主题"

    rows = [
        "| 主题 | 入口 | 状态 | 标签 |",
        "| --- | --- | --- | --- |",
    ]
    for topic in valid:
        title = str(topic.meta["title"])
        status = str(topic.meta["status"])
        tags = topic.meta.get("tags", [])
        tag_text = ", ".join(tags) if isinstance(tags, list) else ""
        if not tag_text:
            tag_text = "-"
        entry_rel = topic.entry.relative_to(root).as_posix()
        target = "<{}>".format(entry_rel) if any(char.isspace() for char in entry_rel) else entry_rel
        entry_name = topic.entry.name
        rows.append(
            "| {} | [{}]({}) | {} | {} |".format(
                escape_cell(title),
                escape_cell(entry_name),
                escape_cell(target),
                escape_cell(STATUS_LABEL.get(status, status)),
                escape_cell(tag_text),
            )
        )
    return "\n".join(rows)


def render_block(topics: Sequence[Topic], root: Path, eol: str = "\n") -> str:
    content = render_index_content(topics, root)
    return START_MARKER + eol + content + eol + END_MARKER


def marker_alone_on_line(text: str, index: int, marker: str) -> bool:
    line_start = text.rfind("\n", 0, index) + 1
    prefix = text[line_start:index]
    if prefix.strip():
        return False
    line_end = text.find("\n", index)
    if line_end == -1:
        line_end = len(text)
    suffix = text[index + len(marker) : line_end]
    return not suffix.strip()


def locate_block(text: str) -> BlockLocation:
    start_count = text.count(START_MARKER)
    end_count = text.count(END_MARKER)
    if start_count == 0 or end_count == 0:
        return BlockLocation(
            ok=False,
            code="index_markers_missing",
            message="README.md 缺少主题索引标记",
        )
    if start_count != 1 or end_count != 1:
        return BlockLocation(
            ok=False,
            code="index_markers_duplicate",
            message="README.md 中的主题索引标记必须各出现一次",
        )
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start > end:
        return BlockLocation(
            ok=False,
            code="index_markers_invalid",
            message="主题索引结束标记位于开始标记之前",
        )
    if not marker_alone_on_line(text, start, START_MARKER) or not marker_alone_on_line(text, end, END_MARKER):
        return BlockLocation(
            ok=False,
            code="index_markers_invalid",
            message="主题索引标记必须各自独占一行",
        )
    end_index = end + len(END_MARKER)
    return BlockLocation(ok=True, block=text[start:end_index], start=start, end=end_index)


def markdown_links(text: str) -> Iterable[str]:
    kept: List[str] = []
    in_fence: Optional[str] = None
    for line in text.splitlines():
        stripped = line.lstrip()
        fence_match = re.match(r"^(```+|~~~+)", stripped)
        if fence_match:
            marker = fence_match.group(1)[0]
            if in_fence is None:
                in_fence = marker
            elif in_fence == marker:
                in_fence = None
            continue
        if in_fence is not None:
            continue
        kept.append(line)

    cleaned = "\n".join(kept)
    cleaned = re.sub(r"`[^`\n]*`", "", cleaned)
    for match in LINK_RE.finditer(cleaned):
        raw = match.group(1).strip()
        if not raw:
            continue
        if raw.startswith("<"):
            close = raw.find(">")
            target = raw[1:close] if close != -1 else raw[1:]
        else:
            target = raw.split()[0]
        yield target.strip()


def check_links(root: Path, topics: Sequence[Topic], errors: List[Dict[str, str]]) -> None:
    files: List[Path] = []
    for name in ("AGENTS.md", "README.md"):
        path = root / name
        if safe_is_file(root, path):
            files.append(path)

    agents = root / ".agents"
    if agents.is_dir() and path_within_root(root, agents):
        try:
            for path in sorted(agents.glob("*.md")):
                if safe_is_file(root, path):
                    files.append(path)
        except (OSError, ValueError, RuntimeError):
            pass

    for topic in topics:
        if topic.entry is not None and safe_is_file(root, topic.entry):
            files.append(topic.entry)

    checked = set()
    for path in files:
        try:
            key = str(path.resolve())
        except (OSError, RuntimeError):
            key = str(path)
        if key in checked:
            continue
        checked.add(key)
        text = read_text(path)
        base_dir = path.parent
        for target in markdown_links(text):
            if not target or target.startswith("#"):
                continue
            if target.startswith("//") or SCHEME_RE.match(target):
                continue
            if target.startswith(("/", "\\")):
                continue
            path_part = target.split("#", 1)[0].split("?", 1)[0]
            path_part = unquote(path_part)
            if not path_part:
                continue
            candidate = base_dir / path_part
            try:
                resolved = candidate.resolve(strict=False)
            except (OSError, RuntimeError):
                continue
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            if not candidate.exists():
                errors.append(
                    make_issue(
                        "broken_link",
                        relative_path(root, path),
                        "相对链接目标不存在: {}".format(target),
                    )
                )


def print_issues(errors: Sequence[Dict[str, str]], warnings: Sequence[Dict[str, str]]) -> None:
    if errors:
        print("错误:")
        for item in errors:
            print("- [{}] {}: {}".format(item["code"], item["path"], item["message"]))
    if warnings:
        print("警告:")
        for item in warnings:
            print("- [{}] {}: {}".format(item["code"], item["path"], item["message"]))


def check_command(root: Path, json_output: bool) -> int:
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    allowed = {item.casefold() for item in DEFAULT_ROOT_ENTRIES}
    allowed.update(item.casefold() for item in load_allowlist(root))
    try:
        with os.scandir(root) as iterator:
            root_entries = sorted(iterator, key=lambda item: item.name.casefold())
    except OSError as exc:
        raise WorkspaceError("无法读取根目录 {}: {}".format(root, exc)) from exc
    for entry in root_entries:
        if entry.name.casefold() not in allowed:
            warnings.append(
                make_issue(
                    "root_not_allowed",
                    entry.name,
                    "根目录存在未允许的条目；如属用户内容，请记录到 .agents/root-allowlist.txt",
                )
            )

    topics, topic_errors, topic_warnings = scan_topics(root)
    errors.extend(topic_errors)
    warnings.extend(topic_warnings)
    warnings.extend(duplicate_warnings(topics, root))

    readme = root / "README.md"
    if not safe_is_file(root, readme):
        errors.append(make_issue("missing_readme", "README.md", "根目录缺少 README.md"))
    else:
        readme_text = read_text(readme)
        location = locate_block(readme_text)
        if not location.ok:
            errors.append(make_issue(location.code, "README.md", location.message))
        else:
            generated = render_block(topics, root, detect_eol(readme_text))
            if location.block != generated:
                errors.append(
                    make_issue(
                        "index_outdated",
                        "README.md",
                        "主题索引区块与生成结果不同，请运行 index --write",
                    )
                )

    check_links(root, topics, errors)

    result = {"ok": not errors, "errors": errors, "warnings": warnings}
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_issues(errors, warnings)
        if errors:
            print("检查失败：{} 个错误，{} 条警告。".format(len(errors), len(warnings)))
        elif warnings:
            print("检查通过，有 {} 条警告。".format(len(warnings)))
        else:
            print("检查通过：未发现问题。")
    return 0 if not errors else 1


def atomic_write(path: Path, text: str) -> None:
    data = text.encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".workspace_doctor-",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def index_command(root: Path, write: bool, json_output: bool) -> int:
    readme = root / "README.md"
    if not safe_is_file(root, readme):
        raise WorkspaceError("根目录缺少 README.md，无法生成索引")
    text = read_text(readme)
    location = locate_block(text)
    if not location.ok:
        errors = [make_issue(location.code, "README.md", location.message)]
        if json_output:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "changed": False,
                        "written": False,
                        "content": "",
                        "errors": errors,
                        "warnings": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print_issues(errors, [])
        return 2

    topics, topic_errors, topic_warnings = scan_topics(root)
    eol = detect_eol(text)
    generated = render_block(topics, root, eol)
    changed = location.block != generated
    written = False
    if write and changed:
        new_text = text[: location.start] + generated + text[location.end :]
        atomic_write(readme, new_text)
        written = True

    result = {
        "ok": not topic_errors,
        "changed": changed,
        "written": written,
        "content": generated,
        "errors": topic_errors,
        "warnings": topic_warnings,
    }
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if topic_errors or topic_warnings:
            print_issues(topic_errors, topic_warnings)
        if changed:
            print("索引需要更新。")
            print("生成内容:")
            print(generated)
        else:
            print("索引已是最新。")
        if written:
            print("已写入 README.md。")
        elif changed:
            print("未写入；确认后使用 index --write。")

    if write:
        return 1 if topic_errors else 0
    return 1 if changed else 0


def find_command(root: Path, query: str, json_output: bool) -> int:
    query_text = " ".join(query.split())
    if not query_text:
        raise WorkspaceError("find 需要非空关键词")
    whole = query_text.casefold()
    terms = [term.casefold() for term in query_text.split()]
    topics, _, _ = scan_topics(root)
    results: List[Dict[str, object]] = []
    for topic in topics:
        title = topic.meta.get("title")
        title_text = title if isinstance(title, str) and title.strip() else topic.name
        status = topic.meta.get("status")
        status_text = status if isinstance(status, str) else ""
        aliases = topic.meta.get("aliases")
        alias_values = [item for item in aliases if isinstance(item, str)] if isinstance(aliases, list) else []
        tags = topic.meta.get("tags")
        tag_values = [item for item in tags if isinstance(item, str)] if isinstance(tags, list) else []

        title_terms = [title_text]
        if topic.h1 and topic.h1 != title_text:
            title_terms.append(topic.h1)
        title_alias_terms = title_terms + alias_values

        def matches_term(value: str, term: str) -> bool:
            return term in value.casefold()

        all_terms_match = True
        for term in terms:
            if not any(
                matches_term(value, term)
                for value in title_alias_terms + tag_values + [topic.name]
            ):
                all_terms_match = False
                break
        if not all_terms_match:
            continue

        exact = any(value.strip().casefold() == whole for value in title_alias_terms)
        phrase_match = any(whole in value.casefold() for value in title_alias_terms)
        title_alias_match = all(
            any(matches_term(value, term) for value in title_alias_terms)
            for term in terms
        )
        tag_match = any(
            any(matches_term(value, term) for term in terms)
            for value in tag_values
        )
        directory_match = any(matches_term(topic.name, term) for term in terms)

        if exact:
            priority = 0
        elif phrase_match:
            priority = 1
        elif title_alias_match:
            priority = 2
        elif tag_match:
            priority = 3
        else:
            priority = 4

        matched: List[str] = []
        if any(matches_term(title_text, term) for term in terms):
            matched.append("标题")
        if topic.h1 and any(matches_term(topic.h1, term) for term in terms):
            matched.append("一级标题")
        if any(
            any(matches_term(value, term) for term in terms)
            for value in alias_values
        ):
            matched.append("别名")
        if tag_match:
            matched.append("标签")
        if directory_match:
            matched.append("目录名")

        entry_text = relative_path(root, topic.entry) if topic.entry is not None else ""
        results.append(
            {
                "title": title_text,
                "status": status_text,
                "status_label": STATUS_LABEL.get(status_text, status_text),
                "entry": entry_text,
                "matched_fields": matched,
                "priority": priority,
            }
        )

    results.sort(key=lambda item: (int(item["priority"]), str(item["title"]).casefold(), str(item["entry"])))
    for item in results:
        item.pop("priority", None)

    if json_output:
        print(json.dumps({"ok": True, "query": query_text, "results": results}, ensure_ascii=False, indent=2))
    else:
        if not results:
            print("未找到匹配主题。")
        else:
            print("找到 {} 个主题：".format(len(results)))
            for item in results:
                label = item["status_label"] or item["status"] or "未知状态"
                print("- {} [{}] {}".format(item["title"], label, item["entry"]))
                print("  命中: {}".format("、".join(item["matched_fields"])))
    return 0


def resolve_root(value: Optional[str]) -> Path:
    path = Path(value).expanduser() if value else Path(__file__).resolve().parent.parent.parent
    try:
        root = path.resolve(strict=True)
    except OSError as exc:
        raise WorkspaceError("根目录不存在或无法访问: {}".format(path)) from exc
    if not root.is_dir():
        raise WorkspaceError("根目录不是目录: {}".format(root))
    return root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查、生成和查询 AI 工作区主题索引")
    parser.add_argument("--version", action="version", version="workspace_doctor {}".format(KIT_VERSION))
    parser.add_argument("--root", help="工作区根目录；默认为脚本所在目录向上两级")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="只读检查工作区")
    check.add_argument("--json", action="store_true", dest="json_output")
    check.add_argument("--root", default=argparse.SUPPRESS)

    index = subparsers.add_parser("index", help="生成或比较根主题索引")
    index.add_argument("--write", action="store_true")
    index.add_argument("--json", action="store_true", dest="json_output")
    index.add_argument("--root", default=argparse.SUPPRESS)

    find = subparsers.add_parser("find", help="按标题、别名、标签、目录名查找主题")
    find.add_argument("query")
    find.add_argument("--json", action="store_true", dest="json_output")
    find.add_argument("--root", default=argparse.SUPPRESS)
    return parser


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = resolve_root(args.root)
        if args.command == "check":
            return check_command(root, args.json_output)
        if args.command == "index":
            return index_command(root, args.write, args.json_output)
        if args.command == "find":
            return find_command(root, args.query, args.json_output)
        raise WorkspaceError("未知命令: {}".format(args.command))
    except WorkspaceError as exc:
        if getattr(args, "json_output", False):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "errors": [make_issue("io_or_argument_error", "", str(exc))],
                        "warnings": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print("错误: {}".format(exc), file=sys.stderr)
        return 2
    except (OSError, UnicodeError) as exc:
        print("错误: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
