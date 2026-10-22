# AutoClaw.Z.ai-ExportChat

export AutoClaw chats to Markdown, TXT and JSON

A command-line utility that reads AutoClaw's local database and saves a conversation to a single file — Markdown, plain text or JSON.

Unofficial tool. Not affiliated with Z.ai, works only with the local database and never goes online.

**English** · [Русский](README.ru.md) · [中文](README.zh.md)

Version 1.1.

## Features

- list every conversation: date, number of requests, title;
- export one conversation (by id or part of the title) or all of them at once;
- three output formats: `.md`, `.txt`, `.json`;
- the default (short) output shows the names of attached files and of files ready to download;
- `/tools` adds tool calls with arguments and results;
- the database is opened read-only, so the app can keep running;
- output labels in Russian (default), English or Chinese — switch with `/lang ru|en|zh`.

## Requirements

- Windows 10 or 11;
- Python 3.10+ — or the interpreter bundled with AutoClaw (the `.bat` finds it automatically).

No separate Python installation is needed if AutoClaw is already installed.

## Installation

1. Download `export_chat.py` and `export_chat.bat` into one folder.
2. That is all — run `export_chat.bat`.

## Quick start

Running with no arguments (including a double-click on `export_chat.bat`) prints a short English help screen with the main options and the link to the repository. An export always needs an explicit option.



From a console:

```bat
cd C:\path\to\folder
export_chat.bat /list
export_chat.bat /chat credits /out chat.md
export_chat.bat /chat Kimi /format txt /out kimi.txt
```

With a system Python available as `python`:

```powershell
python export_chat.py /list
python export_chat.py /chat bb5900ba /format json /out chat.json
```

## Options

| Option | Description |
| --- | --- |
| `/list` | Show all conversations: id, last update, number of requests, title |
| `/chat <id\|part of title>` | Which conversation to export. Default: the most recent one |
| `/out <file>` | Output file name |
| `/all` | Export every conversation, one file per conversation |
| `/out-dir <folder>` | Destination folder for `/all` (default `chat-exports`) |
| `/format md\|txt\|json` | Output format (default `md`) |
| `/lang ru\|en\|zh` | Language of the labels in the exported file and of console messages (default `ru`) |
| `/tools` | Include tool calls with arguments and results |
| `/narration` | Include intermediate assistant remarks |
| `/no-files` | Hide the file blocks |
| `/all-files` | Also show service files (scripts, drafts) |
| `/tool-limit <N>` | How many characters of a tool result to keep (default 4000) |
| `/no-bom` | Do not write the BOM (`EF BB BF`) at the start of md and txt files |
| `/db <path>` | Point to `runtime.sqlite` explicitly |
| `/ver` | Print the version |

## Examples

```bat
:: list conversations
export_chat.bat /list

:: one conversation in Markdown, with tools and service files
export_chat.bat /chat "chat export" /tools /all-files /out full.md

:: every conversation in JSON
export_chat.bat /all /format json /out-dir exports
```

## Files in the export

- **Attached** — taken from the `Attached workspace files` block in the request text: name, type, size. The block itself is removed from the message body.
- **Created** — read from the `governed_tool_artifacts` table and linked by `tool_call_id`, so a file lands in the turn where it appeared.
- **"Ready to download"** — files the agent handed over through `deliver_file`.
- **`/all-files`** — additionally shows everything created along the way: scripts, drafts, patches.

File names are printed in double quotes; service directives such as `:zwork-file-citation{...}` never reach the output.

## Formats

| Format | Content |
| --- | --- |
| `md` | Markdown kept as is: headings, lists, tables, code |
| `txt` | Markdown stripped to plain text: no `**`, backticks, `#`, table pipes; lists become `•`, links become `text (url)` |
| `json` | Structure: `session` plus `turns[]`, each turn holds `request`, `attachments`, `answers`, `citations`, `files` |

A UTF-8 BOM (three bytes `EF BB BF`) is written by default to `.md` and `.txt`. JSON files never get a BOM — strict parsers reject it. Use `/no-bom` to disable the BOM for text files.

## How it works

The tool reads `runtime.sqlite` from the AutoClaw profile:

```
%APPDATA%\AutoClaw-oversea-official\accounts\<id>\runtime\runtime.sqlite
```

Three tables are used:

- `work_sessions` — the list of conversations;
- `neutral_session_entries` — messages (requests, answers, tool calls);
- `governed_tool_artifacts` — created files.

The connection is opened in `mode=ro`; nothing is ever written to the database.

## Limitations

- The database schema is internal and undocumented: an AutoClaw update may change it. When that happens the script reports the problem instead of damaging data.
- `txt` loses formatting — that is its purpose.
- With `/tools` files grow quickly: a single turn can hold 60+ calls.
- Images and binaries are not exported — only names, types and sizes.
- The tool is not affiliated with Z.ai and is not an official export feature.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Console prints only `Python` | The Microsoft Store stub was invoked. Run `export_chat.bat`, it takes Python from AutoClaw |
| `Conversation not found` | The title may have changed. Check `/list` and use the id |
| Empty conversation list | Wrong profile or account. Pass the path manually: `/db "C:\...\runtime.sqlite"` |
| File was not created | Check folder permissions and that the `/out` path exists |

## Links

Repository: <https://github.com/vadimrm/AutoClaw.Z.ai-ExportChat>

## License

MIT — see the `LICENSE` file.

Authors: Vadim Madgazin, AutoClaw.Z.ai
