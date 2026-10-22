# AutoClaw.Z.ai-ExportChat

将 AutoClaw 对话导出为 Markdown、TXT 和 JSON

命令行工具：读取 AutoClaw 的本地数据库，把对话保存成单个文件——Markdown、纯文本或 JSON。

非官方工具，与 Z.ai 无关，只读取本地数据库，不联网。

[English](README.md) · [Русский](README.ru.md) · **中文**

版本 1.1。

## 功能

- 列出全部对话：日期、请求数量、标题；
- 导出单个对话（按 id 或标题片段）或一次性导出全部；
- 三种输出格式：`.md`、`.txt`、`.json`；
- 默认（简短）输出会显示附件文件名，以及已生成、可直接下载的文件名；
- 加 `/tools` 可包含工具调用、参数与返回结果；
- 数据库以只读方式打开，AutoClaw 无需关闭；
- 输出标签可选俄语（默认）、英语或中文，用 `/lang ru|en|zh` 切换。

## 环境要求

- Windows 10 或 11；
- Python 3.10+，或使用 AutoClaw 自带的解释器（`.bat` 会自动找到它）。

已安装 AutoClaw 时无需另外安装 Python。

## 安装

1. 把 `export_chat.py` 和 `export_chat.bat` 下载到同一个文件夹。
2. 完成，直接运行 `export_chat.bat`。

## 快速开始

不带参数运行（包括双击 `export_chat.bat`）会显示一份简短的英文帮助：主要参数与仓库链接。导出需要明确指定参数。



在命令行中：

```bat
cd C:\path\to\folder
export_chat.bat /list
export_chat.bat /chat credits /out chat.md
export_chat.bat /chat Kimi /format txt /out kimi.txt
```

如果系统里已安装 Python 并可通过 `python` 调用：

```powershell
python export_chat.py /list
python export_chat.py /chat bb5900ba /format json /out chat.json
```

## 参数

| 参数 | 说明 |
| --- | --- |
| `/list` | 列出全部对话：id、更新时间、请求数、标题 |
| `/chat <id\|标题片段>` | 指定要导出的对话。默认导出最近一次 |
| `/out <文件>` | 输出文件名 |
| `/all` | 导出全部对话，每个对话一个文件 |
| `/out-dir <目录>` | `/all` 的输出目录（默认 `chat-exports`） |
| `/format md\|txt\|json` | 输出格式（默认 `md`） |
| `/lang ru\|en\|zh` | 文件标签与控制台信息的语言（默认 `ru`） |
| `/tools` | 包含工具调用及参数、结果 |
| `/narration` | 包含助手的中间说明 |
| `/no-files` | 不显示文件区块 |
| `/all-files` | 同时显示过程文件（脚本、草稿） |
| `/tool-limit <N>` | 每个工具结果保留的字符数（默认 4000） |
| `/no-bom` | 不在 md 和 txt 文件开头写入 BOM（`EF BB BF`） |
| `/db <路径>` | 手动指定 `runtime.sqlite` |
| `/ver` | 显示版本 |

## 示例

```bat
:: 列出对话
export_chat.bat /list

:: 导出单个对话为 Markdown，含工具调用和过程文件
export_chat.bat /chat "chat export" /tools /all-files /out full.md

:: 全部对话导出为 JSON
export_chat.bat /all /format json /out-dir exports
```

## 导出中的文件

- **附件** —— 取自请求文本中的 `Attached workspace files` 区块（名称、类型、大小），该区块本身会从正文中移除。
- **生成的文件** —— 取自 `governed_tool_artifacts` 表，按 `tool_call_id` 关联，因此文件会落在它真正出现的那一轮。
- **“可下载”** —— 助手通过 `deliver_file` 交付的文件。
- **`/all-files`** —— 额外显示过程中产生的全部文件：脚本、草稿、补丁。

文件名一律放在双引号中；`:zwork-file-citation{...}` 之类的内部指令不会出现在输出里。

## 格式

| 格式 | 内容 |
| --- | --- |
| `md` | 原样保留 Markdown：标题、列表、表格、代码 |
| `txt` | 去除标记转为纯文本：没有 `**`、反引号、`#`、表格竖线；列表变为 `•`，链接变为 `文本 (地址)` |
| `json` | 结构化：`session` 加 `turns[]`，每轮包含 `request`、`attachments`、`answers`、`citations`、`files` |

`.md` 与 `.txt` 默认写入 UTF-8 BOM（三个字节 `EF BB BF`）。JSON 文件从不写入 BOM——严格的解析器会报错。`/no-bom` 可关闭文本文件的 BOM。

## 工作原理

读取 AutoClaw 配置目录中的 `runtime.sqlite`：

```
%APPDATA%\AutoClaw-oversea-official\accounts\<id>\runtime\runtime.sqlite
```

使用三张表：

- `work_sessions` —— 对话列表；
- `neutral_session_entries` —— 消息（请求、回答、工具调用）；
- `governed_tool_artifacts` —— 生成的文件。

连接以 `mode=ro` 打开，不会向数据库写入任何内容。

## 限制

- 数据库结构属于内部实现且未公开文档化：AutoClaw 更新后可能变化。出错时脚本会说明原因，不会破坏数据。
- `txt` 会丢失格式，这正是它的用途。
- 加 `/tools` 时文件体积增长很快：单轮可能有 60 次以上调用。
- 不导出图片和二进制文件，只记录名称、类型和大小。
- 本工具与 Z.ai 无关，不是官方导出功能。

## 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| 控制台只显示 `Python` | 触发了 Microsoft Store 的占位程序。请运行 `export_chat.bat`，它会使用 AutoClaw 自带的 Python |
| `Диалог не найден`（找不到对话） | 标题可能已修改。先看 `/list`，再用 id 指定 |
| 对话列表为空 | 配置文件或账号不对。手动指定路径：`/db "C:\...\runtime.sqlite"` |
| 文件没有生成 | 检查目录权限，以及 `/out` 指定的路径是否存在 |

## 相关链接

仓库：<https://github.com/vadimrm/AutoClaw.Z.ai-ExportChat>

## 许可证

MIT，详见 `LICENSE` 文件。

作者：Vadim Madgazin、AutoClaw.Z.ai
