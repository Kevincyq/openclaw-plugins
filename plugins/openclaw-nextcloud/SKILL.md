---
name: openclaw-nextcloud
description: 让 AI 管理 Nextcloud 云盘文件，支持上传、下载、删除、分享、列目录。
---

# OpenClaw Nextcloud Skill

让 AI 以用户身份管理 Nextcloud 云盘文件。

## 路径与文件名编码（OpenClaw / 飞书等入口）

本 skill 在 **WebDAV** 侧会按 UTF-8 对路径做百分号编码（`urllib.parse.quote`），并在入口处对路径做 **`normalize_nextcloud_path` 规范化**（按 `/` 分段尝试修复「UTF-8 字节被误当成 Latin-1 解码」导致的乱码）。调用方仍应遵守下列约定，才能与 Nextcloud 上显示的中文文件名一致。

### 调用方必须遵守

1. **`remote_path`（及 CLI 里传给 upload/share/download/delete/list 的路径参数）** 必须是 **Python 3 的 `str`，且语义上为 UTF-8 下的 Unicode 文本**（例如 `PKB/2021年中国户用光伏市场研究报告.pdf`），**不要**传入已做过 URL 编码的字符串（例如含 `%E4%B8%AD` 的整段路径），否则可能 **双重编码**，云盘上会出现错误文件名。
2. **不要把「仅在本机磁盘上合法的路径字符串」未经确认就当远程路径使用**：在 Windows 上若某环节按系统 ANSI/代码页解码了中文，再拼进 `remote_path`，可能已是乱码；应在 **进入本 skill 之前** 保证文件名来自 **正确的 Unicode**（与飞书文档库显示一致并不代表经 WebSocket/OpenClaw 转给 Agent 的字符串一定同源，但若上游已正确，此处即可与云盘一致）。
3. **本地临时文件**建议用 **ASCII 文件名**（如 UUID + 扩展名）落盘，**用户可见的中文名只放在 `remote_path` 的末段**（远程路径），避免磁盘/子进程编码与远程路径混用。

### 本 skill 能做的上限

- 对已出现的 **典型 mojibake**（整段仍是 Latin-1 可编码、且字节流仍是完整 UTF-8）可尝试自动纠正；若文件名中部分字节已被替换为 `_` 等字符，**原始 UTF-8 已损坏，无法自动还原**。
- 若乱码在 **飞书→OpenClaw 网关或 Agent 编排** 中已产生且传入 skill 的已是错误码点，仅靠 skill **无法**从信息论意义上「猜回」真实中文；需在上游修编码或传参方式。

### OpenClaw Agent 侧提示词示例

可将下列片段并入 Agent / 项目的系统提示或工具调用说明（按需删减）。

```text
【Nextcloud 上传 / 路径】
- 调用 `openclaw-nextcloud` 上传时，remote_path 必须使用「人类可读的中文/英文文件名」组成的逻辑路径，例如：PKB/用户提供的原始文件名.pdf。
- remote_path 必须是未做 URL 编码的纯文本；禁止把含 %XX 的字符串当作 remote_path 传入（避免双重编码）。
- 若用户从飞书等渠道提供了原始文件名，应优先使用该名称作为路径最后一段；本地落盘可用 UUID+扩展名等仅 ASCII 的临时路径，与 remote_path 解耦。
- 列出、下载、删除、分享时，路径参数同样使用 Unicode 逻辑路径，不要手动 percent-encode。
```

## 配置

## 与总控流水线的关系

- `openclaw-nextcloud` 只负责 Nextcloud 文件真源操作，不负责 PKB 同步。
- 若场景是“上传后立即入 PKB”“更新文本后刷新索引”“删除文件并同步删索引”，统一使用 **`skills/file-ingest-pipeline`** 定义的固定顺序。

### 环境变量（推荐）

在 `.env` 文件中设置：

```bash
# Nextcloud 配置
NEXTCLOUD_BASE_URL=https://nextcloud.kmchat.cloud
NEXTCLOUD_USERNAME=your_username
NEXTCLOUD_APP_PASSWORD=your_app_password
```

或设置环境变量：
```bash
export NEXTCLOUD_USERNAME=xxx
export NEXTCLOUD_APP_PASSWORD=xxx
```

## 使用方法

### Python 模块方式

```python
import sys
sys.path.insert(0, "/path/to/openclaw-nextcloud/scripts")

from api import get_api

# 上传文件
api = get_api()
api.upload_file("/local/file.txt", "PKB/file.txt")

# 创建分享链接
url = api.create_share_link("PKB/file.txt")
print(url)

# 列出文件
files = api.list_files("/PKB")
for f in files:
    print(f)
```

### CLI 方式

```bash
# 列出文件
python -m scripts.main list /PKB

# 上传文件
python -m scripts.main upload /local/file.txt PKB/file.txt

# 创建分享链接
python -m scripts.main share PKB/file.txt

# 下载文件
python -m scripts.main download PKB/file.txt /local/file.txt

# 删除文件
python -m scripts.main delete PKB/file.txt
```

## 配置优先级

1. 环境变量（最高优先级）
2. .env 文件
3. 默认值
