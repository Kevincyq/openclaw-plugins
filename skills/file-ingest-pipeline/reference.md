# 文件入库流水线 — 参考表

## 推荐工具顺序

| 场景 | 固定顺序 |
|------|----------|
| 上传本地文件 | `nextcloud_upload_file` → `nextcloud_share_file` → `pkb_upload_file` → `pkb_wait_resource_indexed` |
| 创建/更新文本文件 | `nextcloud_write_text_file` → `nextcloud_share_file` → `pkb_upload_text` → `pkb_wait_resource_indexed` |
| 删除文件 | `nextcloud_delete_file` → `pkb_delete_resource` |
| 下载文件 | `nextcloud_download_file` |
| 分享文件 | `nextcloud_share_file` |
| 问答/检索 | `pkb_ask` |

## 参数对照

| 参数 | 含义 | 规则 |
|------|------|------|
| `remotePath` | Nextcloud 逻辑路径 | Unicode、未 URL 编码，例如 `PKB/报告.pdf` |
| `resourceName` | PKB 资源名 | 与 `remotePath` 一致，去掉前导 `/` |
| `sourceUrl` | Nextcloud 公共链接 | 上传到 PKB 前必须先获取 |

## 配置来源

| 组件 | 主要配置 |
|------|----------|
| `openclaw-nextcloud` | `baseUrl`、`username`、`appPassword` |
| `openclaw-pkb` | `baseUrl`、`apiKey`、`userId` |
| `openclaw-pkb` Python CLI | `PKB_BASE_URL`、`PKB_API_KEY`、`PKB_USER_ID`，以及可选 Nextcloud env |

## 失败补偿

| 失败点 | 处理方式 |
|--------|----------|
| Nextcloud 成功，PKB 上传失败 | 保留真源，重试 `nextcloud_share_file` → `pkb_upload_*` → `pkb_wait_resource_indexed` |
| Nextcloud 删除成功，PKB 删除失败 | 不恢复真源，只重试 `pkb_delete_resource` |

## 说明

- 本 skill 的核心目标是：**顺序集中在流程层，不分散在两个插件的自然语言描述里**。
- `openclaw-nextcloud` 只负责 Nextcloud 真源操作，PKB 同步统一由本 skill 编排。
