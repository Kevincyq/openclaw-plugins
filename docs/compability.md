# OpenClaw 兼容说明

本仓库中的 **plugins** 在 `package.json` 的 `openclaw` 字段中声明与下列版本对齐（以各插件内实际声明为准）：

| 项目 | 典型声明 |
|------|----------|
| `openclaw` 依赖 | `2026.4.5` |
| `pluginApi` | `>=2026.4.5` |
| `minGatewayVersion` | `2026.4.5` |

升级网关或 `openclaw` 包时，请同时核对：

1. **`definePluginEntry` / `registerTool` API** 是否变更。  
2. **`openclaw.plugin.json` 的 `configSchema`** 是否与网关注入的 `api.config` 形状一致。  
3. **插件自带 skills**：若要让插件启用时一并加载 skill，需在 `openclaw.plugin.json` 里声明 `"skills": ["./skills"]`，并将技能放在插件根目录下的 `skills/<skill-name>/SKILL.md`。  
4. **子进程环境**：Nextcloud 插件与 PKB 插件都依赖本机 `python3` 以及各自 `scripts/` 目录下的桥接脚本。
5. **Python 运行依赖**：两个插件都依赖 `requests`；首次部署时请分别执行 `pip install -r plugins/openclaw-nextcloud/requirements.txt` 与 `pip install -r plugins/openclaw-pkb/requirements.txt`。

当前仓库同时存在两类 skill：

- 工作区级 skill：如 `skills/file-ingest-pipeline`，优先级更高，可覆盖插件内置 skill
- 插件内置 skill：如 `plugins/openclaw-nextcloud/skills/...` 与 `plugins/openclaw-pkb/skills/...`

随插件行为变更时，请同步更新两处 skill 内容，避免文档与实际流程漂移。
