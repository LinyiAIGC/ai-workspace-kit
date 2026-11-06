# 安装与维护

[返回首页](../README.md)

当前版本：`v0.2.1`。本文保留完整 AI 安装协议、升级与迁移步骤、验收用例和脚本参考。

## 文件归属

| 文件或区块 | 归属 | 升级处理 |
| --- | --- | --- |
| `AGENTS.md` 中 Kit 标记区块 | Kit | 只替换标记区块 |
| `AGENTS.md` 标记区块外内容 | 用户 | 保留 |
| `README.md` 中索引标记区块 | 脚本生成 | 由脚本重新生成 |
| `README.md` 其他内容 | 安装后归用户 | 保留 |
| `.agents/workspace.md` | Kit | 展示差异后可整体替换 |
| `.agents/tools/workspace_doctor.py` | Kit | 展示差异后可整体替换 |
| `.agents/local.md` | 用户 | 不存在时创建，存在时永不覆盖 |
| `.agents/root-allowlist.txt` | 用户 | 不存在时创建，存在时只经同意追加 |
| 各主题入口 | 用户/主题 | 只按任务修改 |

## AI 安装协议

本节写给执行安装的 AI。用户要求“安装”“配置”或“创建 AI 工作区”时，按顺序执行；遇到需要用户决定的冲突，停在该步骤询问。

### 1. 获取模板

安装内容以以下六个文件为准：

| 本仓库中的源文件 | 写入目标工作区的位置 |
| --- | --- |
| [workspace-template/AGENTS.md](../workspace-template/AGENTS.md) | `AGENTS.md` |
| [workspace-template/README.md](../workspace-template/README.md) | `README.md` |
| [workspace-template/.agents/workspace.md](../workspace-template/.agents/workspace.md) | `.agents/workspace.md` |
| [workspace-template/.agents/local.md](../workspace-template/.agents/local.md) | `.agents/local.md` |
| [workspace-template/.agents/root-allowlist.txt](../workspace-template/.agents/root-allowlist.txt) | `.agents/root-allowlist.txt` |
| [workspace-template/.agents/tools/workspace_doctor.py](../workspace-template/.agents/tools/workspace_doctor.py) | `.agents/tools/workspace_doctor.py` |

- 能访问本仓库的本地副本时，直接读取上述六个文件。
- 只能联网读取时，使用与用户读取的仓库根 README 相同版本的原始文件：`https://raw.githubusercontent.com/LinyiAIGC/ai-workspace-kit/<ref>/<源文件路径>`。`<ref>` 使用读取 README 时的分支或标签；未指定时使用 `main`。本协议也必须从同一分支或标签读取。
- 必须读取全部六个文件的实际内容，并按 UTF-8 写入；不要凭首页概述、本协议或记忆重写模板，尤其不要重写检查脚本。
- 任一文件读取失败时停止，告诉用户缺少哪个文件。

### 2. 确定目标目录

- 用户指定路径时使用该路径；否则使用 AI 当前的工作目录。
- 不要安装到本 Kit 仓库自身。若当前目录同时包含本项目的根 README 和 `workspace-template/`，询问实际目标路径。
- 目标不存在时，确认路径无误后创建该目录。
- 目标已有 `.git`、软件包清单或其他明显的项目内容时，先说明安装会影响该目录中的 AI 行为，并取得确认。空目录或专门保存 AI 产物的普通文件夹可以直接继续。
- 开始写入前告诉用户最终的绝对路径。

### 3. 检查现有内容

列出目标根目录的直接内容，包括隐藏项；读取已存在的 `AGENTS.md`、`README.md` 和相关 `.agents/` 文件。不递归读取用户的全部文件。

安装前已经存在的根目录直接子项保持原位。除默认允许项之外的条目，写入新建的 `.agents/root-allowlist.txt`，不移动这些内容。默认允许项为：`AGENTS.md`、`README.md`、`.agents`、`work`、`archive`、`inbox`、`.git`、`.gitignore`、`.gitattributes`、`CLAUDE.md`、`GEMINI.md`、`.claude`、`.gemini`、`.codex`、`.cursor`、`.vscode`、`.DS_Store`、`Thumbs.db`、`desktop.ini`。

已有文件按下列规则处理：

| 情况 | 处理方式 |
| --- | --- |
| 文件不存在 | 写入模板原文。 |
| `AGENTS.md` 已存在，没有 Kit 标记 | 保留原内容，在末尾追加模板中的 Kit 标记区块（不重复一级标题）。原规则与模板冲突时先询问，不自行删除。 |
| `AGENTS.md` 已有完整 Kit 区块 | 只替换该区块，区块外内容逐字保留。 |
| `AGENTS.md` 的 Kit 标记损坏或重复 | 停止并询问，不猜测边界。 |
| `README.md` 已存在，没有索引标记 | 保留原文，在末尾追加工作区说明和空的主题索引标记区块，随后运行 `index --write`。 |
| `README.md` 已有索引标记 | 保留标记外内容，按“升级”处理索引区块。 |
| `.agents/workspace.md` 已存在但不是 Kit 文件 | 停止并询问是合并还是改用其他位置。 |
| `.agents/tools/workspace_doctor.py` 已存在但不是 Kit 文件 | 停止并询问，不覆盖。 |
| `.agents/local.md` 已存在 | 永不覆盖。 |
| `.agents/root-allowlist.txt` 已存在 | 不覆盖；只在用户同意时追加缺失的条目。 |

安装前已经存在的其他文件和目录保持原位。可以提示用户它们尚未整理，但整理和迁移属于另一项任务，需要用户明确要求。

#### 其他 AI 规则文件

检查目标根目录中是否存在其他 AI 客户端的规则文件或目录，例如：

- `AGENTS.override.md`、`AGENT.md`、`agents.md` 等与 `AGENTS.md` 相近的文件；
- `CLAUDE.md`、`CLAUDE.local.md`、`.claude/`；
- `GEMINI.md`、`.gemini/`；
- `.cursorrules`、`.cursor/rules/`、`.windsurfrules`、`.clinerules`；
- `.github/copilot-instructions.md`、`.github/instructions/`。

只读取这些规则文件，不读取其中引用的其他文件。处理方式：

- 不移动、改名、删除或自动合并这些文件，也不把它们的规则复制进 Kit 文件。
- 判断它们是否会被当前客户端读取。例如 `AGENTS.override.md` 可能优先于 `AGENTS.md`；`AGENT.md` 等相近名称通常不会被当作 `AGENTS.md` 读取。
- 指出其中与 Kit 硬规则冲突的内容，例如要求把产物放在根目录或允许直接覆盖文件。
- 询问用户：是否将仍需生效的工作区专属规则合并到 `.agents/local.md`；名称疑似写错时，是否改名或合并。用户确认前保持原样。
- 文件是当前客户端自己的规则入口时，按第 4 步只在其中增加读取或导入 `AGENTS.md` 的说明，不复制完整规则；修改前取得用户同意。

### 4. 写入并接入客户端

- 只写入六个模板文件和第 3 步确定需要的合并内容。
- 不创建 `work/`、`archive/`、`inbox/`、示例主题或主题内的空子目录。
- 当前客户端会读取目标根目录的 `AGENTS.md` 时，不增加其他入口。
- 当前客户端不读取 `AGENTS.md` 时，按其当前官方文档创建或配置它自己的项目规则入口，让入口引用或导入 `AGENTS.md`。不要在多个入口中复制完整规则。
- 无法确认客户端的加载方式时，不猜测配置；告诉用户新聊天开始时需要先让 AI 读取根 `AGENTS.md`。

### 5. 验证与交付

完成后检查：

- 写入的文件可以按 UTF-8 正常读取，本地链接和主题索引标记有效。
- 模板中没有被加入作者或其他用户的本机绝对路径。
- 安装前已有的文件仍在原位；合并文件保留了原内容。
- 没有预建空的 `work/`、`archive/`、`inbox/` 或示例主题。
- Python 可用时，运行 `python .agents/tools/workspace_doctor.py check` 和 `python .agents/tools/workspace_doctor.py index --write`（解释器按环境依次尝试 `python3`、`python`、`py -3`）；不可用时说明脚本检查未执行，并手动完成最小验收。

最后向用户报告：目标绝对路径、新建与合并的文件、发现的其他 AI 规则文件及其处理建议、客户端接入方式、未能验证的事项，以及“安装后验收”中的测试方法。

### 6. 升级

目标文件含有 `ai-workspace-kit` 版本标记时，先比较目标与新模板的差异。替换前展示差异摘要。

- 只替换 `AGENTS.md` 的 Kit 标记区块、`.agents/workspace.md` 和 `.agents/tools/workspace_doctor.py` 等 Kit 文件。
- 保留用户文件、`.agents/local.md`、`.agents/root-allowlist.txt` 的既有条目，以及索引标记外的 README 内容。
- 不因升级重写主题入口；需要补元数据时，先列出拟修改的主题并取得同意。
- 版本号相同、差异含义不明或无法区分本地修改时，展示差异并询问。
- 升级后运行 `check` 和 `index --write`，确认本地规则仍在、索引可重建。

### 7. 从 v0.1.0 迁移

v0.1.0 的规则是分散的纯文本约定。迁移时：

1. 保留原规则和用户修改，不直接丢弃。
2. 把通用规则改为 `AGENTS.md` 中的 Kit 标记区块，区块外只保留工作区专属说明。
3. 把工作区专属规则移入 `.agents/local.md`；该文件存在时只追加，不覆盖。
4. 列出需要补 front matter 的现有主题，取得同意后再修改入口；不得批量猜测标题、别名或状态。
5. 安装检查脚本，运行 `check`，再用 `index --write` 替换旧索引。
6. 迁移完成后抽查一个旧主题，确认可通过别名或目录名找到，入口链接有效。

## 安装后验收

在新聊天中使用目标工作区作为工作目录，依次尝试：

| 你说 | 期望行为 |
| --- | --- |
| “你加载了哪些工作区规则？” | 能指出目标根目录的 `AGENTS.md`，或客户端引用它的规则入口。 |
| “解释一下相对路径，不需要保存。” | 只回答，不新建目录。 |
| “把相对路径的解释保存成笔记。” | 检查索引、运行 `find` 或查看 `work/` 后创建主题，写入 front matter，告知路径并生成索引。 |
| “继续完善相对路径笔记。” | 复用原主题，不因换聊天而新建目录。 |
| “用别名找一下旧主题。” | 能用标题、别名、标签或目录名找到旧主题，并给出入口路径。 |
| “执行工作区检查。” | 运行 `python .agents/tools/workspace_doctor.py check`，按错误和警告分组报告。 |
| “这个主题完成了。” | 把入口 `status` 改为 `done`，更新 `updated` 和索引，目录保持原位。 |
| “把这个主题归档。” | 整体移入 `archive/`，`status` 改为 `archived`，同步索引和受影响的链接。 |
| “升级后我的本地规则还在吗？” | `.agents/local.md` 未被覆盖，Kit 区块和 Kit 文件按差异更新。 |

## 脚本命令

在工作区根目录运行：

```text
python .agents/tools/workspace_doctor.py check
python .agents/tools/workspace_doctor.py index
python .agents/tools/workspace_doctor.py index --write
python .agents/tools/workspace_doctor.py find <关键词>
python .agents/tools/workspace_doctor.py --version
```

命令示例统一写 `python`；按环境依次尝试 `python3`、`python`、`py -3`。

- `check` 只读检查根目录、主题入口、元数据、重复标题/别名、索引和相对链接。
- `index` 显示索引是否需要更新和生成内容；`--write` 只替换索引标记区块。索引表包含主题、入口、状态、标签四列，按状态顺序、再按标题排序，不含更新日期。
- `index --write` 只写入元数据有效的主题；写入后若仍有主题元数据错误，返回 `1`。
- `find` 按标题、别名、标签、目录名和入口一级标题做不区分大小写的包含匹配；多个关键词以空白分隔且全部命中才匹配，整句精确匹配优先。
- `--version` 输出当前脚本版本 `v0.2.1`。
- 脚本只使用 Python 3.9+ 标准库；从其他目录运行时可用 `--root <路径>` 指定工作区。

退出码：`0` 成功且检查无错误；`1` 检查有错误、未写入时索引过期，或 `index --write` 后仍有主题元数据错误；`2` 参数、根目录或文件读写错误。警告不导致退出码 `1`。

## 边界

本 Kit 提供文件约定、元数据和 AI 行为规则，不提供后台监听、强制写入拦截、自动聊天备份或权限隔离。AI 是否加载并遵守规则，取决于所用客户端；重要工作区仍需使用独立备份。`archive/` 只是整理位置，不等于备份。
