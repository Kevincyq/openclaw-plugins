---
name: file-ingest-pipeline
description: >-
  统一编排「Nextcloud 文件真源 + PKB 索引副本」的固定顺序技能。凡是会改变文件真源或需要问答检索，
  都优先使用本技能定义的步骤，而不是让模型自行组合 nextcloud/pkb 工具。
---

# 文件入库流水线（File Ingest Pipeline）

这是本仓库里**总控流程 skill**。它的职责不是提供原子能力，而是**强制规定工具调用顺序**，保证：

- **Nextcloud** 永远是唯一文件真源
- **PKB** 只保存索引，不作为真源
- 上传、更新、删除后，Nextcloud 与 PKB 尽量保持一致
- PKB 中保留 **Nextcloud 公共链接**，供问答检索结果直接溯源访问

## 何时必须使用本技能

- 用户上传文件，要求保存到知识库 / 云盘并可检索
- 用户删除文件，要求同时删掉检索索引
- 用户提交一段文字，要求写入或更新某个文件
- 用户要求“保持 Nextcloud 和 PKB 一致”

以下场景**不要**走本技能：

- 仅下载文件
- 仅分享文件
- 仅列出目录
- 仅做知识问答 / 内容检索

## 参与者与职责

- `nextcloud_*` 工具：只负责**文件真源**相关动作
- `pkb_*` 工具：只负责**知识库索引/检索**动作
- `file-ingest-pipeline`：负责**顺序控制**

## 统一命名规则

- `remotePath`：Nextcloud 逻辑路径，必须是**未 URL 编码**的 Unicode，例如 `PKB/周报/2026-04-11.md`
- `resourceName`：传给 PKB 的资源名，必须与 `remotePath` 对齐，去掉前导 `/` 即可
- `sourceUrl`：Nextcloud 公共访问链接，必须在写入 PKB 前拿到

## 固定流程

### 场景 A：用户上传本地文件

严格按下面顺序：

1. 调 `nextcloud_upload_file(localPath, remotePath)`
2. 检查返回是否成功；失败则立刻停止
3. 调 `nextcloud_share_file(remotePath)` 获取或创建公共链接
4. 调 `pkb_upload_file(localPath, resourceName=remotePath, sourceUrl=<上一步链接>)`
5. 调 `pkb_wait_resource_indexed(resourceName=remotePath)` 轮询确认索引完成
6. 只有前 5 步都成功，才能向用户返回“上传并入库成功”

原因：

- 第 1 步先落真源
- 第 3 步拿到可访问的溯源链接
- 第 4 步把 `sourceUrl` 一并写入 PKB
- 第 5 步避免“已发起索引但实际尚不可检索”的假成功

### 场景 B：用户提交一段文字，要求创建/更新某个文件

严格按下面顺序：

1. 调 `nextcloud_write_text_file(remotePath, text)`
2. 检查返回是否成功；失败则立刻停止
3. 调 `nextcloud_share_file(remotePath)`
4. 调 `pkb_upload_text(text, resourceName=remotePath, sourceUrl=<上一步链接>, suffix=<按扩展名推断>)`
5. 调 `pkb_wait_resource_indexed(resourceName=remotePath)`
6. 成功后再告知用户“文本文件已更新且索引已刷新”

### 场景 C：用户删除文件

严格按下面顺序：

1. 调 `nextcloud_delete_file(remotePath)`
2. 只有 Nextcloud 删除成功后，才继续
3. 调 `pkb_delete_resource(resourceName=remotePath)`
4. 两边都成功后，才告知用户“文件与索引均已删除”

说明：

- 删除顺序必须是 **先真源、后索引**
- 若第 1 步失败，不允许先删 PKB

### 场景 D：下载 / 分享

- 下载只调 `nextcloud_download_file`
- 分享只调 `nextcloud_share_file`
- 不要触发 PKB

### 场景 E：内容检索 / 知识问答

- 只调 `pkb_ask`
- 返回答案时优先使用结果中的 `url` 作为溯源文件链接
- 若 `url` 为空，再退回 `path`

## 失败处理

### 上传 / 更新时

- 若 Nextcloud 成功但 PKB 失败：
  - 明确告诉用户：**真源已写入，但索引未完成**
  - 返回 `remotePath` 供后续补偿
  - 可重试第 3 到第 5 步，不要重新上传真源

### 删除时

- 若 Nextcloud 成功但 PKB 删除失败：
  - 明确告诉用户：**真源已删除，但索引清理失败**
  - 后续只需要重试 `pkb_delete_resource`

## 不要做的事

- 不要把整段 `remotePath` 预先 URL 编码
- 不要跳过 `pkb_wait_resource_indexed`
- 不要把 PKB 当文件真源

## 关联实现

- `plugins/openclaw-nextcloud/index.ts`
- `plugins/openclaw-nextcloud/scripts/openclaw_bridge.py`
- `plugins/openclaw-pkb/index.ts`
- `plugins/openclaw-pkb/scripts/openclaw_bridge.py`

## 最小执行模板

```text
上传文件：
1) nextcloud_upload_file(...)
2) nextcloud_share_file(...)
3) pkb_upload_file(..., sourceUrl=...)
4) pkb_wait_resource_indexed(...)

更新文本：
1) nextcloud_write_text_file(...)
2) nextcloud_share_file(...)
3) pkb_upload_text(..., sourceUrl=...)
4) pkb_wait_resource_indexed(...)

删除文件：
1) nextcloud_delete_file(...)
2) pkb_delete_resource(...)
```
