# 项目维护约定

- 本仓库开发 AI 工作区模板。若存在本地 `CONTEXT.md`，先读它了解未公开的接续状态；再按任务读取 [README.md](README.md) 和相关模板文件。
- `workspace-template/` 是安装到目标工作区的内容。维护本仓库时，不在本仓库中执行模板里的建主题、索引或归档流程。
- 用户要求安装工作区时，从 README 的“AI 安装协议”入口读取 [安装与维护](docs/installation.md)，再按协议写入用户指定的目标目录，不安装到本仓库自身。
- 模板包含 `AGENTS.md`、`README.md`、`.agents/workspace.md`、`.agents/maintenance.md`、`.agents/old-chats.md`、`.agents/local.md`、`.agents/root-allowlist.txt` 和 `.agents/tools/workspace_doctor.py` 八个文件。`.agents/adopted.txt`、`.agents/moves.tsv` 和 `.agents/move-plan.tsv` 不属于模板，在工作区使用过程中按需产生。
- 用户要求整理已有工作区时，读取 [整理已有工作区](docs/reorganize.md)。整理和旧对话接续是两条线，都只由用户主动触发；移动必须先有用户确认的计划，并通过脚本的 `move` 命令执行。
- 修改模板、脚本或安装协议时，同步更新 README 概述和 `docs/installation.md` 的版本、目标结构、八文件清单、安装/升级/v0.1.0 迁移步骤、验收用例，`docs/reorganize.md` 的整理协议与上下文占用表，以及 `tests/`。仅调整文档呈现时保留现有行为测试。
- `workspace_doctor.py` 只使用 Python 3.9+ 标准库；修改后运行 `python -m py_compile workspace-template/.agents/tools/workspace_doctor.py` 和 `python -m unittest discover -s tests -v`。
- 模板保持客户端和平台中立，使用相对路径；不加入作者本机路径、用户名、聊天记录、凭据或固定 Shell 要求。
- 核心入口保持简短；每次落盘都要用的流程放在 `.agents/workspace.md`，不常用的放在 `.agents/maintenance.md`，只在旧对话中用的放在 `.agents/old-chats.md`，只在整理或安装时用的放在 `docs/`，不写入工作区。新增规则前先判断它属于哪一层。公开 README 只写可复用的安装和维护信息。
- 仓库地址为 `https://github.com/LinyiAIGC/ai-workspace-kit`，许可证为 MIT。不把未验证的客户端支持或未发布的版本写成既成事实；本地进度只写入 `CONTEXT.md`。
