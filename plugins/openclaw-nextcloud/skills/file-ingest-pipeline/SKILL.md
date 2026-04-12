---
name: file-ingest-pipeline
description: >-
  统一编排「Nextcloud 文件真源 + PKB 索引副本」的固定顺序技能。凡是会改变文件真源或需要问答检索，
  都优先使用本技能定义的步骤，而不是让模型自行组合 nextcloud/pkb 工具。
---

# 文件入库流水线（Bundled）

这是随 `openclaw-nextcloud` 插件一起加载的**总控 skill**。它不替代原子工具，而是约束调用顺序。

## 目标

- Nextcloud 是唯一文件真源
- PKB 只保存索引，不保存原始真源
- 上传、更新、删除后保持两侧尽量一致
- PKB 索引必须带上 Nextcloud 公共链接，供问答结果溯源

## 何时必须使用

- 用户上传文件并要求后续可检索
- 用户提交文本并要求保存/更新到某个文件
- 用户删除文件并要求同步删除索引

## 不适用场景

- 单纯下载文件
- 单纯分享文件
- 单纯列目录
- 单纯知识问答

## 固定顺序

### 上传本地文件

1. `nextcloud_upload_file(localPath, remotePath)`
2. `nextcloud_share_file(remotePath)`
3. `pkb_upload_file(localPath, resourceName=remotePath, sourceUrl=<share-url>)`
4. `pkb_wait_resource_indexed(resourceName=remotePath)`

### 创建或更新文本文件

1. `nextcloud_write_text_file(remotePath, text)`
2. `nextcloud_share_file(remotePath)`
3. `pkb_upload_text(text, resourceName=remotePath, sourceUrl=<share-url>, suffix=<按扩展名推断>)`
4. `pkb_wait_resource_indexed(resourceName=remotePath)`

### 删除文件

1. `nextcloud_delete_file(remotePath)`
2. `pkb_delete_resource(resourceName=remotePath)`

## 强约束

- 不要跳过 `nextcloud_share_file`
- 不要跳过 `pkb_wait_resource_indexed`
- 不要先删 PKB 再删 Nextcloud

## 参数规范

- `remotePath`：Nextcloud 逻辑路径，未 URL 编码
- `resourceName`：与 `remotePath` 一致，去掉前导 `/`
- `sourceUrl`：Nextcloud 公共访问链接
