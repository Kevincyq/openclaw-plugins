---
name: openclaw-pkb
description: 让 AI 使用 PKB 知识库做索引、检索与问答，并优先返回带 Nextcloud 溯源链接的结果。
---

# OpenClaw PKB Skill

本技能用于指导 Agent 正确使用 `openclaw-pkb` 插件暴露的工具。

## 适用场景

- 上传文件到 PKB 建索引
- 将文本写入 PKB 建索引
- 轮询等待索引完成
- 删除索引
- 做知识问答 / 内容检索

## 工具列表

- `pkb_upload_file`
- `pkb_upload_text`
- `pkb_wait_resource_indexed`
- `pkb_delete_resource`
- `pkb_list_resources`
- `pkb_ask`

## 调用约束

- 若来源是真源文件发生变化，优先遵循 **`file-ingest-pipeline`** 的顺序
- `pkb_upload_*` 时，尽量带上 `sourceUrl`，以便问答时直接返回 Nextcloud 公共链接
- `resourceName` 应与 Nextcloud 的 `remotePath` 对齐

## 问答与溯源

- `pkb_ask` 返回的 `sources` 中优先使用 `url`
- 若 `url` 为空，再退回 `path`

## 删除

- 只有在 Nextcloud 真源删除成功后，才执行 `pkb_delete_resource`
