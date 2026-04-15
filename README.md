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

## 在新 OpenClaw 环境中安装本仓库插件

先确认你的 **OpenClaw 网关**跑在哪里：

| 部署方式 | 要点 |
|----------|------|
| **主机 / 虚拟机 / WSL（非 Docker）** | 路径、依赖、`openclaw` CLI、配置都在同一套系统与用户环境中，按下面 **「非 Docker」** 即可。 |
| **Docker / Compose / Kubernetes** | 网关进程在**容器内**；插件路径、`python3`、依赖安装、`openclaw` 命令都必须在**容器视角**下一致，按 **「Docker 容器」** 操作。 |

以下将本仓库根目录记为 **`OPENCLAW_PLUGINS_ROOT`**（请替换为你的实际路径）。

---

### 非 Docker（主机、虚拟机、WSL 等）

前提：本机已安装 **OpenClaw CLI**（`openclaw` 可用），**Node.js** 建议 **≥ 22.14.0**。配置一般为 **`~/.openclaw/openclaw.json`**。

#### 1. 获取本仓库代码

```bash
git clone https://github.com/Kevincyq/openclaw-plugins.git
cd openclaw-plugins
```

（SSH / fork 请替换 URL。）

#### 2. 安装各插件的 Node 与 Python 依赖

```bash
cd "$OPENCLAW_PLUGINS_ROOT/plugins/openclaw-nextcloud"
pnpm install   # 或 npm install

cd "$OPENCLAW_PLUGINS_ROOT/plugins/openclaw-pkb"
pnpm install   # 或 npm install
```

Python（建议 venv，与系统 Python 隔离）：

```bash
python3 -m venv .venv-openclaw-plugins   # 可选
# source .venv-openclaw-plugins/bin/activate

pip install -r "$OPENCLAW_PLUGINS_ROOT/plugins/openclaw-nextcloud/requirements.txt"
pip install -r "$OPENCLAW_PLUGINS_ROOT/plugins/openclaw-pkb/requirements.txt"
```

确保 **运行 Gateway 的同一环境**里能执行 **`python3`**（与 systemd / 你启动 `openclaw` 的 `PATH` 一致）。

#### 3. 用 OpenClaw CLI 注册插件

在**能读写 `~/.openclaw` 的用户**下执行，路径使用**主机上的绝对路径**：

**方式 A：`--link`（推荐开发、目录长期保留）**

```bash
openclaw plugins install --link "$OPENCLAW_PLUGINS_ROOT/plugins/openclaw-nextcloud"
openclaw plugins install --link "$OPENCLAW_PLUGINS_ROOT/plugins/openclaw-pkb"
```

**方式 B：普通安装（由 CLI 处理安装目录）**

```bash
openclaw plugins install "$OPENCLAW_PLUGINS_ROOT/plugins/openclaw-nextcloud"
openclaw plugins install "$OPENCLAW_PLUGINS_ROOT/plugins/openclaw-pkb"
```

#### 4. 启用插件并写入配置

```bash
openclaw plugins enable nextcloud
openclaw plugins enable pkb
```

在 **`~/.openclaw/openclaw.json`** 的 **`plugins.entries`** 中填写 **`nextcloud`** / **`pkb`** 的 **`config`**（字段见各插件 **`openclaw.plugin.json`** 的 **`configSchema`**）。插件从 **`api.pluginConfig`** 读取（即 `plugins.entries.<id>.config`），勿与整份配置的根级字段混用。

#### 5. 重启网关并自检

例如使用**用户级 systemd**：

```bash
systemctl --user restart openclaw-gateway.service
```

（若手动前台运行 `openclaw gateway`，则停止后重新启动。）

```bash
openclaw plugins list --verbose
openclaw plugins inspect nextcloud
openclaw plugins inspect pkb
```

#### 6.（可选）加载仓库根目录技能

若需使用 **`skills/file-ingest-pipeline`**，可在 `openclaw.json` 中配置 **`skills.load.extraDirs`**，加入 **`$OPENCLAW_PLUGINS_ROOT/skills`**（键名以所用 OpenClaw 版本文档为准）。

#### 离线或无法 `git clone`

可将仓库打成 **`.zip` / `.tgz`** 解压后从第 2 步继续；或尝试 **`openclaw plugins install ./插件包.tgz`**（见上游 CLI 说明）。

---

### Docker 容器部署

网关跑在容器内时，**`plugins install --link` 的路径必须是容器内可见的路径**；宿主机路径只有**挂载进容器**后才能在配置里引用。

#### 1. 把本仓库放进容器可访问的位置（常见做法）

- **卷挂载**：在 `docker-compose.yml`（或 K8s Volume）中把宿主机目录挂到容器内固定路径，例如：  
  `- /宿主机路径/openclaw-plugins:/opt/openclaw-plugins:ro`（开发可 `:rw`）  
  此时 **`OPENCLAW_PLUGINS_ROOT` 在容器内为** `/opt/openclaw-plugins`。
- 或在**构建镜像**时 `COPY` / `git clone` 到镜像内某目录（改插件需重建镜像或挂卷覆盖）。

#### 2. 在「运行 Gateway 的容器」内安装依赖

必须在 **`docker exec` 进入的容器**（或 Dockerfile 的 `RUN`）中执行，与宿主机隔离：

```bash
docker exec -it <网关容器名> sh   # 或 bash
# 以下在容器内执行：
cd /opt/openclaw-plugins/plugins/openclaw-nextcloud && pnpm install   # 或 npm install
cd /opt/openclaw-plugins/plugins/openclaw-pkb && pnpm install
pip install -r /opt/openclaw-plugins/plugins/openclaw-nextcloud/requirements.txt
pip install -r /opt/openclaw-plugins/plugins/openclaw-pkb/requirements.txt
```

**说明**：镜像若**未包含 `python3`/pip**，需自行在 Dockerfile 中安装（例如 `apt`/`apk` 安装 `python3`），否则桥接脚本无法运行。

#### 3. 在容器内执行 OpenClaw CLI

仍在**同一容器**内（或官方文档指定的、与网关共享配置的 sidecar）执行：

```bash
openclaw plugins install --link /opt/openclaw-plugins/plugins/openclaw-nextcloud
openclaw plugins install --link /opt/openclaw-plugins/plugins/openclaw-pkb
openclaw plugins enable nextcloud
openclaw plugins enable pkb
```

`openclaw.json` 所在位置以你的部署为准：常见为挂载卷中的 **`/root/.openclaw/openclaw.json`** 或环境变量 **`OPENCLAW_STATE_DIR` / `OPENCLAW_CONFIG_PATH`** 指向的文件，需在**该文件**中维护 **`plugins.entries.*.config`**。

#### 4. 重启网关进程

使用容器编排重启服务，例如：

```bash
docker compose restart <网关服务名>
# 或
kubectl rollout restart deployment/<openclaw-deployment>
```

**不要用**宿主机的 `systemctl --user` 去管容器内进程（除非你的 unit 本身就是 `docker compose up` 的封装）。

#### 5. 自检

```bash
docker exec -it <网关容器名> openclaw plugins list --verbose
docker exec -it <网关容器名> openclaw plugins inspect nextcloud
```

#### Docker 场景下易错点

- **`plugins.load.paths` / `--link` 路径**：填**容器内**路径，与 Volume 挂载一致。  
- **Python**：桥接用 **`python3`**，须在**跑 Gateway 的容器**里可用。  
- **配置与数据**：`openclaw.json` 若只在容器可写层，重建容器会丢；生产环境建议**持久化卷**挂载配置目录。

---

### 两种部署方式的共同说明

- **业务配置**均在 **`plugins.entries.nextcloud.config`** / **`plugins.entries.pkb.config`**（见下文「配置说明」）。  
- **技能 `skills/`**：若需 **`skills.load.extraDirs`**，Docker 下同样要把 **`OPENCLAW_PLUGINS_ROOT/skills`** 挂进容器并在配置里写**容器内路径**。

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
