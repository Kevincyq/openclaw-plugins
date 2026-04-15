/**
 * openclaw-nextcloud 插件（TypeScript 入口）
 *
 * 数据流：Agent 调工具 → registerTool → runBridge → scripts/openclaw_bridge.py
 *        → NextcloudAPI（api.py）用 WebDAV/OCS 访问网盘「文件真源」。
 *
 * 与 openclaw-pkb 的关系：Nextcloud 管存储路径；PKB 管检索索引。入库流水线见 skills/file-ingest-pipeline。
 *
 * 配置：OpenClaw 注入为 api.pluginConfig（同 plugins.entries.nextcloud.config），
 * 勿使用 api.config（那是整份 openclaw.json）。
 */
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { Type } from "@sinclair/typebox";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

type NextcloudConfig = {
  baseUrl: string;
  username: string;
  appPassword: string;
};

function bridgeScriptPath(): string {
  return path.join(__dirname, "scripts", "openclaw_bridge.py");
}

/**
 * 执行 Python 桥：argv[1] 为整段 JSON，成功时 stdout 一行 JSON。
 * 失败时 Python 仍可能把错误写在 stdout（exit≠0），故需同时解析 stdout 与 stderr（与 pkb 插件一致）。
 */
function runBridge(payload: Record<string, unknown>) {
  return new Promise<unknown>((resolve, reject) => {
    const p = spawn("python3", [bridgeScriptPath(), JSON.stringify(payload)], {
      cwd: __dirname,
      env: process.env
    });
    let stdout = "";
    let stderr = "";

    p.stdout.on("data", (d) => {
      stdout += d.toString();
    });
    p.stderr.on("data", (d) => {
      stderr += d.toString();
    });

    p.on("close", (code) => {
      const trimmed = stdout.trim();
      let parsed: { ok?: boolean; error?: string; result?: unknown } | null = null;
      if (trimmed) {
        try {
          parsed = JSON.parse(trimmed) as { ok?: boolean; error?: string; result?: unknown };
        } catch {
          parsed = null;
        }
      }
      if (parsed?.ok === false) {
        reject(new Error(parsed.error || "bridge error"));
        return;
      }
      if (code !== 0) {
        const fromJson =
          parsed && typeof parsed === "object" && "error" in parsed
            ? String((parsed as { error?: string }).error || "")
            : "";
        const detail =
          fromJson ||
          stderr.trim() ||
          (trimmed ? `stdout: ${trimmed.slice(0, 1200)}` : "") ||
          `python exited with code ${code ?? "null"}`;
        reject(new Error(detail));
        return;
      }
      if (!parsed) {
        reject(new Error(`invalid JSON from bridge: stdout=${trimmed.slice(0, 500)}`));
        return;
      }
      resolve("result" in parsed && parsed.result !== undefined ? parsed.result : parsed);
    });
  });
}

/** WebDAV/OCS 共用的 Nextcloud 连接信息（应用密码，非登录网页密码）。 */
function basePayload(cfg: NextcloudConfig, action: string) {
  return {
    action,
    baseUrl: cfg.baseUrl,
    username: cfg.username,
    appPassword: cfg.appPassword
  };
}

export default definePluginEntry({
  id: "nextcloud",
  name: "Nextcloud",
  description: "Nextcloud WebDAV：上传、文本写入、下载、列目录、分享链接、删除。",
  register(api) {
    const cfg = (api.pluginConfig ??
      api.config.plugins?.entries?.nextcloud?.config ??
      {}) as NextcloudConfig;

    api.registerTool({
      name: "nextcloud_upload_file",
      description: "上传本地文件到 Nextcloud。",
      parameters: Type.Object({
        localPath: Type.String({ description: "本地文件绝对或工作区相对路径" }),
        remotePath: Type.String({ description: "远程路径，例如 PKB/报告.pdf" })
      }),
      async execute(_id, params) {
        const result = await runBridge({
          ...basePayload(cfg, "upload"),
          localPath: params.localPath,
          remotePath: params.remotePath
        });
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });

    api.registerTool({
      name: "nextcloud_write_text_file",
      description: "在 Nextcloud 直接创建或覆盖文本文件。",
      parameters: Type.Object({
        remotePath: Type.String({ description: "远程路径，例如 PKB/日报.md" }),
        text: Type.String({ description: "待写入的文本内容" })
      }),
      async execute(_id, params) {
        const result = await runBridge({
          ...basePayload(cfg, "write_text"),
          remotePath: params.remotePath,
          text: params.text
        });
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });

    api.registerTool({
      name: "nextcloud_download_file",
      description: "从 Nextcloud 下载文件到本地路径。",
      parameters: Type.Object({
        remotePath: Type.String(),
        localPath: Type.String()
      }),
      async execute(_id, params) {
        const result = await runBridge({
          ...basePayload(cfg, "download"),
          remotePath: params.remotePath,
          localPath: params.localPath
        });
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });

    api.registerTool({
      name: "nextcloud_list_files",
      description: "列出 Nextcloud 某目录下的文件与文件夹。",
      parameters: Type.Object({
        path: Type.Optional(Type.String({ description: "目录路径，默认根目录 /" }))
      }),
      async execute(_id, params) {
        const result = await runBridge({
          ...basePayload(cfg, "list"),
          ...(params.path !== undefined ? { path: params.path } : {})
        });
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });

    api.registerTool({
      name: "nextcloud_share_file",
      description: "获取或创建 Nextcloud 文件的公开分享链接。",
      parameters: Type.Object({
        remotePath: Type.String()
      }),
      async execute(_id, params) {
        const result = await runBridge({
          ...basePayload(cfg, "share"),
          remotePath: params.remotePath
        });
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });

    api.registerTool({
      name: "nextcloud_delete_file",
      description: "删除 Nextcloud 上的文件。",
      parameters: Type.Object({
        remotePath: Type.String()
      }),
      async execute(_id, params) {
        const result = await runBridge({
          ...basePayload(cfg, "delete"),
          remotePath: params.remotePath
        });
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });
  }
});
