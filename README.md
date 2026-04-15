# openclaw-plugins

面向 [OpenClaw](https://github.com/openclaw/openclaw) 的自定义插件与技能集合：将 **Nextcloud** 作为文件真源、**PKB** 作为可检索索引，并通过技能 **`file-ingest-pipeline`** 约定「上传 / 更新 / 删除」时的工具调用顺序。

## 仓库结构

| 路径 | 说明 |
|------|------|
| `plugins/openclaw-nextcloud/` | Nextcloud WebDAV / 分享插件（TypeScript + Python 桥） |
| `plugins/openclaw-pkb/` | PKB 知识库插件（问答、索引、FileSaaS 上传链） |
| `skills/file-ingest-pipeline/` | 工作区级技能：编排 Nextcloud + PKB 的固定流水线（可与插件内置技能合并/覆盖） |
| `docs/compability.md` | OpenClaw / 网关版本与升级时注意点 |

各插件目录下也可包含 `skills/`，在对应 `openclaw.plugin.json` 中通过 `"skills": ["./skills"]` 声明。

## 环境要求

- **Node.js**：与 OpenClaw 一致，建议 **≥ 22.14.0**（参见上游 `engines`）。
- **OpenClaw 网关**：与各插件 `package.json` 中 `minGatewayVersion` / `pluginApi` 对齐（当前典型为 **2026.4.5**）。
- **Python 3**：两个插件均通过 `python3` 调用 `scripts/openclaw_bridge.py`。
- 依赖安装：
  - 每个插件目录：`pnpm install` 或 `npm install`
  - Python：`pip install -r plugins/openclaw-nextcloud/requirements.txt` 与 `pip install -r plugins/openclaw-pkb/requirements.txt`

## 安装插件

推荐使用 OpenClaw CLI（在已配置网关的机器上执行）：

```bash
openclaw plugins install --link /绝对路径/openclaw-plugins/plugins/openclaw-nextcloud
openclaw plugins install --link /绝对路径/openclaw-plugins/plugins/openclaw-pkb
openclaw plugins enable nextcloud
openclaw plugins enable pkb
```

并在 `~/.openclaw/openclaw.json` 的 `plugins.entries` 中填写各插件的 `config`（字段见各插件目录下的 `openclaw.plugin.json` 内 `configSchema`）。

插件入口从 **`api.pluginConfig`** 读取业务配置（对应 `plugins.entries.<id>.config`），勿与整份 `openclaw.json` 根对象混淆。

## 配置说明（摘要）

### Nextcloud（`plugins.entries.nextcloud.config`）

- `baseUrl`：站点根 URL  
- `username`：登录名  
- `appPassword`：应用专用密码（非网页登录密码）

### PKB（`plugins.entries.pkb.config`）

- `baseUrl`、`apiKey`、`userId`：PKB API 访问信息  
- `fileSaaS`（可选）：上传链路所需，字段名可与 `tenantId` / `uploadServer` 等别名对应；亦可由插件目录 `.env` 或本地 `config.json` 的 `fileSaaS` 块提供（勿提交密钥到 Git）

本地开发可复制各插件下的 **`config.json.example`** 为 **`config.json`** 并填入真实值；`config.json` 已被 `.gitignore` 忽略。

## 技能 `file-ingest-pipeline`

用于约束 Agent：**先落 Nextcloud 真源 → 再取公开链接 → 再写入 PKB 索引并等待就绪**，避免只改一端。详细步骤见 `skills/file-ingest-pipeline/SKILL.md`。

若使用仓库根 `skills/`，可能需在 OpenClaw 配置中通过 `skills.load.extraDirs` 指向本仓库 `skills` 目录（视你的 OpenClaw 版本与加载方式而定）。

## 安全与仓库规范

- **切勿**将真实密钥、`config.json`、`.env` 提交到 Git；仓库已提供 `.gitignore` 与 `*.example` 模板。
- 若历史提交中曾包含密钥，请**轮换**相关密码与 API Key，并视情况用 `git filter-repo` 等工具清理历史。

## 文档

- 版本与升级注意：`docs/compability.md`

## 许可证

以各子目录内声明为准；未单独声明时由维护者自行补充。
