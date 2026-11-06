# AI 工作区

这里按主题保存 AI 聊天产生的文件。同主题的新聊天继续使用原目录，新主题需要保存文件时才建目录。

本模板对应 AI Workspace Kit `v0.2.1`。

AI 执行入口：[AGENTS.md](AGENTS.md)。详细流程：[工作区操作约定](.agents/workspace.md)。本地专属规则：[本地规则](.agents/local.md)。

## 目录用途

| 位置 | 内容 |
| --- | --- |
| `AGENTS.md` | 读取顺序和少量硬规则 |
| `.agents/workspace.md` | 选主题、写入口、放产物、检查和归档的具体流程 |
| `.agents/local.md` | 当前工作区专属规则，由用户维护 |
| `.agents/root-allowlist.txt` | 用户原有根目录内容清单 |
| `.agents/tools/workspace_doctor.py` | 检查、生成索引和查找主题的脚本 |
| `work/` | 日常主题，包括进行中、暂停和已完成的主题 |
| `archive/` | 用户明确要求归档的主题 |
| `inbox/` | 用户可选的投放区，不预建 |

目录按需创建。简单主题只需要一个入口文件和实际产物；复杂后再增加需要的子目录。

## 主题元数据

主题位于 `work/<目录名>/` 或 `archive/<目录名>/`。主题根目录有 `CONTEXT.md` 时以它为入口，否则使用 `README.md`。已有项目的 `README.md` 继续承担项目说明时，另建 `CONTEXT.md` 作为主题入口。

入口顶部使用以下简单 front matter：

```markdown
---
title: Linux 命令学习
aliases: [shell 学习, Linux 笔记]
tags: [linux, 学习]
status: active
updated: 2026-11-05
---
```

- `title`、`status`、`updated` 必需；`aliases`、`tags` 可省略，默认空列表。
- `status` 使用 `active`、`paused`、`done`、`archived`，对应“进行中”“暂停”“已完成”“已归档”。
- `work/` 中的主题不能是 `archived`；`archive/` 中的主题必须是 `archived`。
- 有实质产出或状态变化时更新 `updated`，不因阅读或格式整理更新。

## 主题索引

索引由脚本从主题入口生成，只替换下面标记之间的内容：

<!-- ai-workspace-kit:topic-index:start -->
暂无主题
<!-- ai-workspace-kit:topic-index:end -->

索引表包含主题、入口、状态、标签四列，按状态顺序、再按标题排序，不含更新日期。状态取值为“进行中”“暂停”“已完成”“已归档”。本表只做主题导航；目录是否存在以文件系统为准，主题细节以入口为准。

## 使用方式

- 新需求：直接说明要做什么。需要保存文件时，AI 会先查索引、`work/` 和 `archive/`，再用 `find` 辅助判断能否复用已有主题。
- 继续旧工作：说出主题名称或别名，也可以直接指定目录。
- 保存结论：说“把结论和下一步保存到这个主题”。
- 完成主题：把入口状态改为 `done`，文件留在原位。
- 归档主题：明确提出归档，AI 移动整个主题并同步索引和相关链接。

## 脚本检查

在工作区根目录运行：

```text
python .agents/tools/workspace_doctor.py check
python .agents/tools/workspace_doctor.py index
python .agents/tools/workspace_doctor.py index --write
python .agents/tools/workspace_doctor.py find <关键词>
python .agents/tools/workspace_doctor.py --version
```

命令示例统一写 `python`；按环境依次尝试 `python3`、`python`、`py -3`。`check` 只读；`index --write` 只改索引标记区块；`find` 匹配标题、别名、标签、目录名和入口一级标题，多个关键词以空白分隔且全部命中才匹配，整句精确匹配优先。脚本只使用 Python 3.9+ 标准库，也可用 `--root <路径>` 从其他目录运行。

`index --write` 只把元数据有效的主题写入索引；写入后若仍有主题元数据错误，脚本会报告错误并返回 `1`。

## 规则加载

以本目录作为 AI 客户端的工作目录。新聊天可以先问“你加载了哪些工作区规则？”，确认根 `AGENTS.md` 已生效。

单独打开某个子目录或嵌套 Git 项目时，客户端不一定读取本目录的规则。需要继承时，在该项目的规则入口中说明先读取本工作区的 `AGENTS.md`，同时保留项目自己的规则。

本约定不提供后台监听、写入拦截或完整聊天备份；`archive/` 也不等于独立备份。
