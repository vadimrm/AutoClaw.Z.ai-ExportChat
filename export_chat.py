#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Экспорт диалогов AutoClaw в Markdown / TXT / JSON. Версия 4.

Читает базу рантайма приложения (runtime.sqlite, таблицы work_sessions и
neutral_session_entries) в режиме только-чтение и складывает переписку в один
файл.

Что нового в v4:
  * разделитель — 60 дефисов вместо 30;
  * BOM (EF BB BF) в начале создаваемых файлов: для md и txt по умолчанию,
    для json — только по флагу --bom;
  * запускатор работает с единственным именем export_chat.py (v2, v3, v4 —
    это архивные копии).

Примеры:
    python export_chat.py --list
    python export_chat.py                          # самый свежий диалог
    python export_chat.py --session кредит         # по части названия или id
    python export_chat.py --session bb5900ba --out chat.md --tools
    python export_chat.py --session Kimi --format txt --out chat.txt
    python export_chat.py --all --out-dir exports
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

__version__ = "4.0"

APP_DIR_NAMES = (
    "AutoClaw-oversea-official",
    "AutoClaw-official",
    "AutoClaw",
)

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(text: str, fallback: str = "chat") -> str:
    text = (text or "").strip().lower()
    text = "".join(TRANSLIT.get(ch, ch) for ch in text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:60] or fallback)


def roaming_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata and Path(appdata).is_dir():
        return Path(appdata)
    return Path.home() / "AppData" / "Roaming"


def find_db(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise SystemExit(f"Файл базы не найден: {p}")
        return p

    candidates: list[Path] = []
    root = roaming_dir()
    for name in APP_DIR_NAMES:
        acc_root = root / name / "accounts"
        if not acc_root.is_dir():
            continue
        candidates += list(acc_root.glob("*/runtime/runtime.sqlite"))

    if not candidates:
        raise SystemExit(
            "Не нашёл runtime.sqlite. Укажите путь вручную: --db <путь>"
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


def connect(db: Path) -> sqlite3.Connection:
    uri = "file:" + db.as_posix() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def local_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return dt.astimezone().strftime("%d.%m.%Y %H:%M")


def load_sessions(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        con.execute(
            """
            select session_id, title, created_at, updated_at
            from work_sessions
            where deleted_at is null
            order by updated_at desc
            """
        )
    )


def pick_session(sessions: list[sqlite3.Row], needle: str | None) -> sqlite3.Row:
    if not sessions:
        raise SystemExit("В базе нет ни одного диалога.")
    if not needle:
        return sessions[0]

    needle_l = needle.strip().lower()
    exact = [s for s in sessions if s["session_id"] == needle_l]
    if exact:
        return exact[0]
    by_id = [s for s in sessions if s["session_id"].lower().startswith(needle_l)]
    if len(by_id) == 1:
        return by_id[0]
    by_title = [s for s in sessions if needle_l in (s["title"] or "").lower()]
    if len(by_title) == 1:
        return by_title[0]
    if len(by_title) > 1:
        lines = "\n".join(f"  {s['session_id']}  {s['title']}" for s in by_title)
        raise SystemExit(f"Подходит несколько диалогов, уточните:\n{lines}")
    raise SystemExit(f"Диалог не найден: {needle}")


def parse_payload(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def text_of_request(data: dict) -> str:
    return (
        data.get("text")
        or strip_attachment_block(data.get("effectivePrompt") or "")
        or data.get("prompt")
        or ""
    ).strip()


ATTACH_MARKER = "Attached workspace files"

ATTACH_ITEM_RE = re.compile(
    r"^- (?P<name>.+?): (?P<path>.+?) \((?P<mime>[^,()]+), (?P<size>\d+) bytes\)\s*$"
)

DIRECTIVE_RE = re.compile(r":zwork-[a-z0-9\-]+\{([^{}]*)\}")
ATTR_RE = re.compile(r"(\w+)\s*=\s*\"([^\"]*)\"")


def extract_citations(text: str) -> tuple[str, list[dict]]:
    """Превращает :zwork-file-citation{...} в кавычки с именем файла."""
    if not text or ":zwork-" not in text:
        return text, []

    citations: list[dict] = []

    def replace(match: re.Match) -> str:
        attrs = dict(ATTR_RE.findall(match.group(1)))
        path = (attrs.get("path") or attrs.get("file") or "").strip()
        if not path:
            return ""
        citations.append(
            {
                "path": path,
                "purpose": attrs.get("purpose") or "",
                "kind": attrs.get("artifact_kind") or "",
            }
        )
        return f'"{path}"'

    lines: list[str] = []
    for line in text.split("\n"):
        if ":zwork-" in line:
            line = DIRECTIVE_RE.sub(replace, line)
            line = re.sub(r"[ \t]{2,}", " ", line).rstrip()
        lines.append(line)
    return "\n".join(lines), citations


def strip_attachment_block(prompt: str) -> str:
    index = prompt.find(ATTACH_MARKER)
    if index < 0:
        return prompt
    return prompt[:index].rstrip()


def parse_attachments(prompt: str) -> list[dict]:
    index = prompt.find(ATTACH_MARKER)
    if index < 0:
        return []
    attachments = []
    for line in prompt[index:].splitlines()[1:]:
        line = line.strip()
        if not line.startswith("- "):
            if attachments:
                break
            continue
        match = ATTACH_ITEM_RE.match(line)
        if not match:
            continue
        attachments.append(
            {
                "name": match.group("name").strip(),
                "path": match.group("path").strip(),
                "media": match.group("mime").strip(),
                "size": int(match.group("size")),
            }
        )
    return attachments


def format_size(size: int | None) -> str:
    if not size or size < 0:
        return ""
    if size < 1024:
        return f"{size} Б"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} КБ".replace(".", ",")
    return f"{size / (1024 * 1024):.1f} МБ".replace(".", ",")


def file_kind(name: str) -> str:
    suffix = Path(name).suffix.lower().lstrip(".")
    return suffix or "файл"


def dedupe_files(items: list[dict], key: str = "path") -> list[dict]:
    seen: dict[str, dict] = {}
    order: list[str] = []
    for item in items:
        value = item.get(key) or item.get("name") or ""
        if value not in seen:
            order.append(value)
        seen[value] = item
    return [seen[value] for value in order]


def load_artifacts(con: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = con.execute(
        """
        select artifact_id, tool_call_id, tool_id, display_name, source_path,
               media_type, byte_length, created_at
        from governed_tool_artifacts
        where session_id = ? and artifact_presentation = 'card'
        order by created_at
        """,
        (session_id,),
    )
    artifacts = []
    for row in rows:
        artifacts.append(
            {
                "id": row["artifact_id"],
                "call_id": row["tool_call_id"],
                "tool": row["tool_id"] or "",
                "name": (row["display_name"] or row["source_path"] or "файл").strip(),
                "path": (row["source_path"] or row["display_name"] or "").strip(),
                "media": row["media_type"] or "",
                "size": row["byte_length"] or 0,
                "at": row["created_at"],
                "delivered": (row["tool_id"] or "").endswith("deliver"),
            }
        )
    return artifacts


def build_turns(
    con: sqlite3.Connection, session_id: str, artifacts: list[dict]
) -> list[dict]:
    rows = con.execute(
        """
        select session_seq, entry_type, payload, committed_at
        from neutral_session_entries
        where session_id = ?
        order by session_seq
        """,
        (session_id,),
    )

    turns: list[dict] = []
    current: dict | None = None

    for row in rows:
        entry_type = row["entry_type"]
        payload = parse_payload(row["payload"])
        data = payload.get("data") or {}

        if entry_type == "request":
            prompt = data.get("effectivePrompt") or ""
            request_text, request_citations = extract_citations(text_of_request(data))
            current = {
                "request": request_text,
                "citations": request_citations,
                "request_at": row["committed_at"],
                "attachments": parse_attachments(prompt),
                "answers": [],
                "tools": [],
                "narration": [],
                "call_ids": [],
                "created": [],
            }
            turns.append(current)
            continue

        if current is None:
            continue

        if entry_type == "tool_call":
            call_id = data.get("toolCallId") or ""
            if call_id:
                current["call_ids"].append(call_id)
            current["tools"].append(
                {
                    "name": data.get("toolName") or "tool",
                    "input": data.get("input"),
                    "output": None,
                }
            )
        elif entry_type == "tool_result":
            content = data.get("content")
            if current["tools"] and current["tools"][-1]["output"] is None:
                current["tools"][-1]["output"] = content
        elif entry_type == "assistant":
            blocks = data.get("content")
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                text = ""
                if isinstance(block, str):
                    text = block
                elif isinstance(block, dict) and block.get("type") in (None, "text"):
                    text = block.get("text") or ""
                if text.strip():
                    clean, _ = extract_citations(text.strip())
                    current["narration"].append(clean)
        elif entry_type == "answer":
            text, citations = extract_citations((data.get("text") or "").strip())
            if text:
                current["answers"].append(
                    {"text": text, "at": row["committed_at"], "citations": citations}
                )

    turns = [t for t in turns if t["request"] or t["answers"]]
    assign_artifacts(turns, artifacts)
    return turns


def assign_artifacts(turns: list[dict], artifacts: list[dict]) -> None:
    if not turns or not artifacts:
        return

    by_call: dict[str, list[dict]] = {}
    for artifact in artifacts:
        by_call.setdefault(artifact["call_id"], []).append(artifact)

    used: set[str] = set()
    for turn in turns:
        for call_id in turn["call_ids"]:
            for artifact in by_call.get(call_id, []):
                if artifact["id"] in used:
                    continue
                used.add(artifact["id"])
                turn["created"].append(artifact)

    for artifact in artifacts:
        if artifact["id"] in used:
            continue
        for index, turn in enumerate(turns):
            start = turn["request_at"]
            end = (
                turns[index + 1]["request_at"]
                if index + 1 < len(turns)
                else "9999"
            )
            if start <= artifact["at"] < end:
                turn["created"].append(artifact)
                used.add(artifact["id"])
                break

    for turn in turns:
        turn["created"] = dedupe_files(turn["created"])
        turn["attachments"] = dedupe_files(turn["attachments"])


def plural(n: int, one: str, few: str, many: str) -> str:
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


def human_size(text: str) -> str:
    return f"{len(text)} симв."


def render_tool(tool: dict, limit: int) -> str:
    head = f"<details><summary>🔧 {tool['name']}</summary>\n"
    parts = [head]
    if tool["input"] not in (None, {}, []):
        payload = json.dumps(tool["input"], ensure_ascii=False, indent=2)
        parts.append("\n**Вызов**\n\n```json\n" + payload + "\n```\n")
    output = tool["output"]
    if isinstance(output, str) and output.strip():
        body = output.strip()
    elif output is not None:
        body = json.dumps(output, ensure_ascii=False, indent=2)
    else:
        body = ""
    if body:
        cut = body[:limit]
        if len(body) > limit:
            cut += f"\n… (обрезано, всего {human_size(body)})"
        parts.append("\n**Результат**\n\n```text\n" + cut + "\n```\n")
    parts.append("</details>\n")
    return "".join(parts)


def session_meta(session: sqlite3.Row, turns: list[dict]) -> dict:
    attached = dedupe_files([a for t in turns for a in t["attachments"]])
    files = dedupe_files([f for t in turns for f in t["created"]])
    return {
        "id": session["session_id"],
        "title": (session["title"] or "").strip() or "Диалог AutoClaw",
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "created_local": local_time(session["created_at"]),
        "updated_local": local_time(session["updated_at"]),
        "requests": len(turns),
        "answers": sum(len(t["answers"]) for t in turns),
        "attachments": attached,
        "files": files,
        "delivered": [f for f in files if f["delivered"]],
    }


CODE_FENCE_RE = re.compile(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```[ \t]*$", re.S | re.M)
TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$", re.M)
HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.M)
QUOTE_RE = re.compile(r"^[ \t]{0,3}>[ \t]?", re.M)
BULLET_RE = re.compile(r"^([ \t]*)[-*+][ \t]+", re.M)
RULE_RE = re.compile(r"^[ \t]{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$", re.M)
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BOLD_RE = re.compile(r"(?<!\w)(\*\*|__)(?=\S)(.+?)(?<=\S)\1(?!\w)", re.M)
POWER_RE = re.compile(r"(?<=\w)\*\*(?=\w)")
POWER_PLACEHOLDER = "\x00pow\x00"
STRAY_BOLD_RE = re.compile(r"\*{2,}(?=\s|$)")
STRAY_TICKS_RE = re.compile(r"`")
STRAY_STRIKE_RE = re.compile(r"~~(?=\s|$)")
STRIKE_RE = re.compile(r"~~(.+?)~~", re.S)
ITALIC_STAR_RE = re.compile(r"(?<!\*)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)")
ITALIC_UND_RE = re.compile(r"(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])")
INLINE_CODE_RE = re.compile(r"`+([^`\n]*)`+")
BLANKS_RE = re.compile(r"\n{3,}")


def md_to_text(text: str) -> str:
    """Убирает Markdown-разметку, оставляя читаемый текст."""
    if not text:
        return ""

    # Блоки кода: снимаем забор, содержимое оставляем как есть.
    text = CODE_FENCE_RE.sub(lambda m: m.group(1).rstrip("\n"), text)

    lines = text.split("\n")
    table_rows: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if TABLE_SEP_RE.match(stripped):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            table_rows.append(" — ".join(c for c in cells if c))
        else:
            table_rows.append(line)
    text = "\n".join(table_rows)

    text = HEADING_RE.sub("", text)
    text = RULE_RE.sub("-" * 60, text)
    text = QUOTE_RE.sub("", text)
    text = BULLET_RE.sub(lambda m: m.group(1) + "• ", text)
    text = IMAGE_RE.sub(lambda m: (m.group(1) or m.group(2)), text)
    text = LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})", text)
    text = INLINE_CODE_RE.sub(lambda m: m.group(1), text)
    text = POWER_RE.sub(POWER_PLACEHOLDER, text)
    text = BOLD_RE.sub(lambda m: m.group(2), text)
    text = STRIKE_RE.sub(lambda m: m.group(1), text)
    text = STRAY_BOLD_RE.sub("", text)
    text = STRAY_STRIKE_RE.sub("", text)
    text = ITALIC_STAR_RE.sub(lambda m: m.group(1), text)
    text = ITALIC_UND_RE.sub(lambda m: m.group(1), text)
    text = text.replace(POWER_PLACEHOLDER, "**")
    text = STRAY_TICKS_RE.sub("", text)
    text = BLANKS_RE.sub("\n\n", text)
    return text.strip("\n")


def render_text(
    session: sqlite3.Row,
    turns: list[dict],
    with_files: bool = True,
    all_files: bool = False,
) -> str:
    meta = session_meta(session, turns)
    out: list[str] = []
    out.append(f"{meta['title']}\n")
    out.append(f"Сессия: {meta['id']}\n")
    out.append(f"Создана: {meta['created_local']}\n")
    out.append(f"Обновлена: {meta['updated_local']}\n")
    out.append(f"Сообщений: {meta['requests']} / ответов: {meta['answers']}\n")
    out.append(
        f"Файлы: вложено {len(meta['attachments'])}, "
        f"готово к скачиванию {len(meta['delivered'])}\n"
    )
    out.append("\n" + "-" * 60 + "\n")

    for index, turn in enumerate(turns, 1):
        out.append(f"\n[{index}] ВЫ — {local_time(turn['request_at'])}\n")
        out.append((md_to_text(turn["request"]) or "[пустой запрос]") + "\n")
        if with_files and turn["attachments"]:
            out.append("\nВложено:\n")
            for item in turn["attachments"]:
                out.append(
                    f'  - "{item["name"]}" ({file_kind(item["name"])}, '
                    f"{format_size(item['size'])})\n"
                )

        for answer in turn["answers"]:
            stamp = local_time(answer["at"])
            out.append(f"\nОТВЕТ — {stamp}\n")
            out.append(md_to_text(answer["text"]) + "\n")

        if with_files and turn["created"]:
            delivered = [f for f in turn["created"] if f["delivered"]]
            other = [f for f in turn["created"] if not f["delivered"]]
            if delivered:
                out.append("\nГотово к скачиванию:\n")
                for item in delivered:
                    out.append(
                        f'  - "{item["name"]}" ({file_kind(item["name"])}, '
                        f"{format_size(item['size'])})\n"
                    )
            if all_files and other:
                out.append("\nПрочие файлы:\n")
                for item in other:
                    out.append(
                        f'  - "{item["name"]}" ({file_kind(item["name"])}, '
                        f"{format_size(item['size'])})\n"
                    )

    return "".join(out)


def render_json(
    session: sqlite3.Row,
    turns: list[dict],
    with_files: bool = True,
    all_files: bool = False,
) -> str:
    meta = session_meta(session, turns)
    payload = {
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "session": {
            key: meta[key]
            for key in (
                "id",
                "title",
                "created_at",
                "updated_at",
                "created_local",
                "updated_local",
                "requests",
                "answers",
            )
        },
        "turns": [],
    }
    for index, turn in enumerate(turns, 1):
        created = turn["created"]
        if with_files:
            created = [f for f in created if f["delivered"]] if not all_files else created
        else:
            created = []
        payload["turns"].append(
            {
                "index": index,
                "request": {
                    "text": turn["request"],
                    "at": turn["request_at"],
                    "at_local": local_time(turn["request_at"]),
                    "citations": turn.get("citations", []),
                },
                "attachments": turn["attachments"] if with_files else [],
                "answers": [
                    {
                        "text": a["text"],
                        "at": a["at"],
                        "at_local": local_time(a["at"]),
                        "citations": a.get("citations", []),
                    }
                    for a in turn["answers"]
                ],
                "files": [
                    {
                        "name": f["name"],
                        "path": f["path"],
                        "kind": file_kind(f["name"]),
                        "size": f["size"],
                        "delivered": f["delivered"],
                        "at": f["at"],
                    }
                    for f in created
                ],
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_markdown(
    session: sqlite3.Row,
    turns: list[dict],
    with_tools: bool,
    with_narration: bool,
    tool_limit: int,
    with_files: bool = True,
    all_files: bool = False,
) -> str:
    title = (session["title"] or "").strip() or "Диалог AutoClaw"
    answers = sum(len(t["answers"]) for t in turns)
    attached_all = dedupe_files([a for t in turns for a in t["attachments"]])
    created_all = dedupe_files([f for t in turns for f in t["created"]])
    delivered_all = [f for f in created_all if f["delivered"]]
    other_all = [f for f in created_all if not f["delivered"]]

    out: list[str] = []
    out.append(f"# {title}\n\n")
    out.append("---\n")
    out.append(f"- **Сессия:** \"{session['session_id']}\"\n")
    out.append(f"- **Создана:** {local_time(session['created_at'])}\n")
    out.append(f"- **Обновлена:** {local_time(session['updated_at'])}\n")
    out.append(
        f"- **Сообщений:** {len(turns)} "
        f"{plural(len(turns), 'запрос', 'запроса', 'запросов')}, {answers} "
        f"{plural(answers, 'ответ', 'ответа', 'ответов')}\n"
    )
    files_line = (
        f"- **Файлы:** вложено {len(attached_all)} · "
        f"готово к скачиванию {len(delivered_all)}"
    )
    if all_files:
        files_line += f" · прочих созданных {len(other_all)}"
    out.append(files_line + "\n")
    out.append(
        f"- **Экспорт:** {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
    )
    out.append("\n---\n")

    for index, turn in enumerate(turns, 1):
        out.append(
            f"\n## {index}. Вы — {local_time(turn['request_at'])}\n\n"
        )
        out.append((turn["request"] or "_[пустой запрос]_") + "\n")

        if with_files and turn["attachments"]:
            out.append("\n**📎 Вложено:**\n")
            for item in turn["attachments"]:
                meta = ", ".join(
                    part
                    for part in (
                        file_kind(item["name"]),
                        format_size(item["size"]),
                    )
                    if part
                )
                out.append(f'- "{item["name"]}" — {meta}\n')

        if with_tools and turn["tools"]:
            out.append(f"\n**Инструменты: {len(turn['tools'])}**\n\n")
            for tool in turn["tools"]:
                out.append(render_tool(tool, tool_limit) + "\n")

        if with_narration and turn["narration"]:
            out.append("\n> " + "\n>\n> ".join(turn["narration"]) + "\n")

        for answer in turn["answers"]:
            stamp = local_time(answer["at"])
            suffix = f" — {stamp}" if stamp else ""
            out.append(f"\n### AutoClaw{suffix}\n\n")
            out.append(answer["text"] + "\n")

        if with_files and turn["created"]:
            delivered = [f for f in turn["created"] if f["delivered"]]
            other = [f for f in turn["created"] if not f["delivered"]]
            if delivered:
                out.append("\n**📄 Готово к скачиванию:**\n")
                for item in delivered:
                    meta = ", ".join(
                        part
                        for part in (
                            file_kind(item["name"]),
                            format_size(item["size"]),
                        )
                        if part
                    )
                    out.append(f'- "{item["name"]}" — {meta}\n')
            if all_files and other:
                out.append("\n**🗂 Прочие файлы:**\n")
                for item in other:
                    meta = ", ".join(
                        part
                        for part in (
                            file_kind(item["name"]),
                            format_size(item["size"]),
                        )
                        if part
                    )
                    out.append(f'- "{item["name"]}" — {meta}\n')

    return "".join(out)


def export_one(
    con: sqlite3.Connection,
    session: sqlite3.Row,
    out_path: Path,
    with_tools: bool,
    with_narration: bool,
    tool_limit: int,
    with_files: bool = True,
    all_files: bool = False,
    fmt: str = "md",
    bom: str = "auto",
) -> tuple[Path, int]:
    artifacts = load_artifacts(con, session["session_id"])
    turns = build_turns(con, session["session_id"], artifacts)
    if not turns:
        raise SystemExit(f"В диалоге нет сообщений: {session['session_id']}")
    if fmt == "json":
        body = render_json(session, turns, with_files, all_files)
    elif fmt == "txt":
        body = render_text(session, turns, with_files, all_files)
    else:
        body = render_markdown(
            session, turns, with_tools, with_narration, tool_limit, with_files, all_files
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    use_bom = bom == "always" or (bom == "auto" and fmt != "json")
    out_path.write_text(body, encoding="utf-8-sig" if use_bom else "utf-8")
    return out_path, len(turns)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(
        description="Экспорт диалога AutoClaw в Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--version", action="version", version=f"export_chat {__version__}")
    ap.add_argument("--db", help="путь к runtime.sqlite")
    ap.add_argument("--list", action="store_true", help="показать список диалогов")
    ap.add_argument("--session", help="id или часть названия диалога")
    ap.add_argument("--out", help="файл назначения (.md)")
    ap.add_argument("--all", action="store_true", help="выгрузить все диалоги")
    ap.add_argument("--out-dir", default="chat-exports", help="папка для --all")
    ap.add_argument("--tools", action="store_true", help="включить вызовы инструментов")
    ap.add_argument("--narration", action="store_true", help="включить промежуточные реплики")
    ap.add_argument(
        "--no-files",
        action="store_true",
        help="не показывать вложенные и созданные файлы",
    )
    ap.add_argument(
        "--all-files",
        action="store_true",
        help="показывать и промежуточные файлы (скрипты, черновики)",
    )
    ap.add_argument(
        "--format",
        dest="fmt",
        choices=("md", "txt", "json"),
        default="md",
        help="формат экспорта (по умолчанию md)",
    )
    bom_group = ap.add_mutually_exclusive_group()
    bom_group.add_argument(
        "--bom",
        dest="bom",
        action="store_const",
        const="always",
        help="добавлять BOM (EF BB BF) во все форматы, включая json",
    )
    bom_group.add_argument(
        "--no-bom",
        dest="bom",
        action="store_const",
        const="never",
        help="не добавлять BOM",
    )
    ap.set_defaults(bom="auto")
    ap.add_argument(
        "--tool-limit",
        type=int,
        default=4000,
        help="сколько символов результата инструмента оставлять (по умолчанию 4000)",
    )
    args = ap.parse_args()

    db = find_db(args.db)
    con = connect(db)
    sessions = load_sessions(con)

    if args.list:
        print(f"База: {db}\n")
        for s in sessions:
            turns = con.execute(
                "select count(*) from neutral_session_entries where session_id=? and entry_type='request'",
                (s["session_id"],),
            ).fetchone()[0]
            print(
                f"{s['session_id']}  {local_time(s['updated_at'])}  "
                f"{turns:>3} запр.  {s['title']}"
            )
        return 0

    if not sessions:
        raise SystemExit("В базе нет диалогов.")

    if args.all:
        out_dir = Path(args.out_dir)
        for s in sessions:
            name = f"{local_time(s['updated_at'])[:10].replace('.', '-')}-{slugify(s['title'], s['session_id'][:8])}.{args.fmt}"
            path, count = export_one(
                con,
                s,
                out_dir / name,
                args.tools,
                args.narration,
                args.tool_limit,
                not args.no_files,
                args.all_files,
                args.fmt,
                args.bom,
            )
            print(f"{path}  ({count} {plural(count, 'запрос', 'запроса', 'запросов')})")
        return 0

    session = pick_session(sessions, args.session)
    if args.out:
        out_path = Path(args.out)
    else:
        stamp = local_time(session["updated_at"])[:10].replace(".", "-")
        out_path = Path(
            f"{slugify(session['title'], session['session_id'][:8])}-{stamp}.{args.fmt}"
        )

    path, count = export_one(
        con,
        session,
        out_path,
        args.tools,
        args.narration,
        args.tool_limit,
        not args.no_files,
        args.all_files,
        args.fmt,
        args.bom,
    )
    print(f"Готово: {path.resolve()}")
    print(f"Диалог: {session['title']}  ({count} {plural(count, 'запрос', 'запроса', 'запросов')})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
