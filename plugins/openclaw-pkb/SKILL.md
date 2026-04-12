---
name: openclaw-pkb
description: 让 AI 使用 PKB 个人知识库做检索、问答与索引同步，并为答案附加云盘溯源链接。
---

# OpenClaw PKB Skill

让 AI 管理 PKB 知识库，包括问答和同步功能。

## 路径与文件名编码（OpenClaw / 飞书等入口）

### 与 Nextcloud 直连 WebDAV 时（`sync` 命令）

- 参数 **`nc_path`**（如 `/PKB`）须为 **UTF-8 语义的 Unicode 字符串**，**不要**预先整段 URL 编码后再传入。
- `scripts/main.py` 中的 **`cmd_sync`** 会对 **`nc_path` 及解析得到的远程路径** 使用与 **`openclaw-nextcloud`** 一致的 **`normalize_nextcloud_path`**，并对 WebDAV URL 使用 **`quote`**，避免中文目录/文件名未编码或常见乱码形态未纠正。
- 若在扩展代码中自行拼 Nextcloud URL，可从 `api` 导入 **`normalize_nextcloud_path`**，与 Nextcloud skill 行为对齐。

### 本地上传到 PKB（`upload` 命令 / `upload_resource`）

- **`file_path`** 为本地路径；**展示在知识库中的名称**来自 **`os.path.basename(file_path)`**（或你传入的 `file_name`）。请保证 **调用环境中的文件名字符串为正确 Unicode**；若本地名已是乱码，PKB 侧也会是乱码。
- 同样建议：**磁盘上的临时文件可用 ASCII/UUID 命名**，真实标题通过参数或后续 API 字段传递（若你的编排支持）。

### 能力边界

- **normalize** 只能处理 **特定类型的编码错位**，不能修复已被破坏的字节流；**不能**替代上游（网关、Agent）对 UTF-8 的正确解码与传参。
- 与 **`openclaw-nextcloud`** 配合时：云盘路径规范以 Nextcloud skill 的 **`remote_path` 约定**为准；本 skill 的 `sync` 与之一致化处理。

### OpenClaw Agent 侧提示词示例

可将下列片段并入 Agent / 项目的系统提示或工具调用说明（按需删减）。

```text
【PKB 与 Nextcloud 同步】
- 执行 sync 时，nc_path 使用未编码的 Unicode 路径，例如 /PKB 或 /PKB/子目录；不要预先整段 URL 编码。
- 执行 upload 到知识库时：若文件先落在临时目录，优先保证最终传入 API 的「展示名」与用户原始文件名一致（Unicode）；临时文件可用 UUID 文件名，避免把 Windows 乱码路径当作展示名。
- 问答结果中的来源路径若需再调 Nextcloud 分享接口，路径格式与 `openclaw-nextcloud` 的 remote_path 约定一致（Unicode、未预编码）。
- 云盘上的权威命名以 `openclaw-nextcloud` 上传时的 remote_path 为准；PKB 索引侧看到的文件名应与之一致。
```

## 配置

## 与总控流水线的关系

- 若调用目的是“Nextcloud 真源变更后刷新 PKB 索引”，优先遵循 **`skills/file-ingest-pipeline`** 的固定顺序。
- 本 skill 侧更偏向 **PKB 原子能力**：上传建索引、删除索引、问答检索；不要单独假定它负责 Nextcloud 真源写入。

### 环境变量（推荐）

在 `.env` 文件中设置：

```bash
# PKB 知识库配置
PKB_BASE_URL=https://api.miaoda.io
PKB_API_KEY=your_api_key
PKB_USER_ID=your_user_id

# Nextcloud 配置（用于同步）
NEXTCLOUD_BASE_URL=https://nextcloud.kmchat.cloud
NEXTCLOUD_USERNAME=your_username
NEXTCLOUD_APP_PASSWORD=your_app_password
```

或设置环境变量：
```bash
export PKB_API_KEY=xxx
export PKB_USER_ID=xxx
export NEXTCLOUD_USERNAME=xxx
export NEXTCLOUD_APP_PASSWORD=xxx
```

## 使用方法

### Python 模块方式

```python
import sys
sys.path.insert(0, "/path/to/openclaw-pkb/scripts")

from api import get_api

# 问答
api = get_api()
result = api.ask("什么是量子计算?")
print(result["answer"])
print(result["sources"])
```

### CLI 方式

```bash
# 问答
python -m scripts.main ask "什么是量子计算?"

# 同步 Nextcloud 目录到知识库
python -m scripts.main sync /PKB

# 上传文件
python -m scripts.main upload /local/file.pdf

# 删除知识库资源
python -m scripts.main delete "PKB/file.pdf"
```

## 配置优先级

1. 环境变量（最高优先级）
2. .env 文件
3. 默认值
