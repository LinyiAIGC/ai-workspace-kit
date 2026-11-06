# 项目维护约定

- 本仓库开发 AI 工作区模板。若存在本地 `CONTEXT.md`，先读它了解未公开的接续状态；再按任务读取 [README.md](README.md) 和相关模板文件。
- `workspace-template/` 是安装到目标工作区的内容。维护本仓库时，不在本仓库中执行模板里的建主题、索引或归档流程。
- 用户要求安装工作区时，从 README 的“AI 安装协议”入口读取 [安装与维护](docs/installation.md)，再按协议写入用户指定的目标目录，不安装到本仓库自身。
- 模板包含 `AGENTS.md`、`README.md`、`.agents/workspace.md`、`.agents/local.md`、`.agents/root-allowlist.txt` 和 `.agents/tools/workspace_doctor.py` 六个文件。
- 修改模板、脚本或安装协议时，同步更新 README 概述和 `docs/installation.md` 的版本、目标结构、六文件清单、安装/升级/v0.1.0 迁移步骤、验收用例，以及 `tests/`。仅调整文档呈现时保留现有行为测试。
- `workspace_doctor.py` 只使用 Python 3.9+ 标准库；修改后运行 `python -m py_compile workspace-template/.agents/tools/workspace_doctor.py` 和 `python -m unittest discover -s tests -v`。
- 模板保持客户端和平台中立，使用相对路径；不加入作者本机路径、用户名、聊天记录、凭据或固定 Shell 要求。
- 核心入口保持简短，详细流程放在 `.agents/workspace.md`；公开 README 只写可复用的安装和维护信息。
- 仓库地址为 `https://github.com/LinyiAIGC/ai-workspace-kit`，许可证为 MIT。不把未验证的客户端支持或未发布的版本写成既成事实；本地进度只写入 `CONTEXT.md`。
