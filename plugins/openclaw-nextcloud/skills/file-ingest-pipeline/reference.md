# 文件入库流水线 — Bundled Reference

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
| `remotePath` | Nextcloud 逻辑路径 | Unicode、未 URL 编码 |
| `resourceName` | PKB 资源名 | 与 `remotePath` 一致，去掉前导 `/` |
| `sourceUrl` | Nextcloud 公共链接 | 上传到 PKB 前先获取 |
