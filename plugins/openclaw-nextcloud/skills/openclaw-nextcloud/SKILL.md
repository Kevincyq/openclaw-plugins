---
name: openclaw-nextcloud
description: 让 AI 管理 Nextcloud 云盘文件，支持上传、下载、删除、分享、列目录。
---

# OpenClaw Nextcloud Skill

本技能用于指导 Agent 正确使用 `openclaw-nextcloud` 插件暴露的工具。

## 适用场景

- 上传文件到 Nextcloud
- 下载文件
- 删除文件
- 创建分享链接
- 列目录
- 直接写入/覆盖文本文件

## 路径规则

- `remotePath` 必须是 **未 URL 编码** 的 Unicode 路径，例如 `PKB/2026年周报.md`
- 不要手动对整段路径做 `%XX` 编码
- 本地临时文件名建议使用 ASCII，用户可见名称优先放在 `remotePath` 末段

## 工具列表

- `nextcloud_upload_file`
- `nextcloud_write_text_file`
- `nextcloud_download_file`
- `nextcloud_list_files`
- `nextcloud_share_file`
- `nextcloud_delete_file`

## 调用约束

- `openclaw-nextcloud` 只负责 Nextcloud 文件真源操作
- 如果场景是“上传/更新后继续同步 PKB”，统一遵循 **`file-ingest-pipeline`** 的固定顺序

## 典型场景

### 上传文件但不立刻编排 PKB

1. 调 `nextcloud_upload_file(localPath, remotePath)`
2. 若后续要做知识索引，再交给 `file-ingest-pipeline`

### 直接更新文本文件

1. 调 `nextcloud_write_text_file(remotePath, text)`
2. 若文件内容要可检索，再交给 `file-ingest-pipeline`

### 下载/分享

- 下载只用 `nextcloud_download_file`
- 分享只用 `nextcloud_share_file`
- 这两类场景不触发 PKB
