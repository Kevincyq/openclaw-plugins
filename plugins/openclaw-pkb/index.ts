/**
 * openclaw-pkb 插件（TypeScript 入口）
 *
 * 数据流：OpenClaw Agent 调工具 → 本文件 registerTool → runBridge 起子进程
 *        → scripts/openclaw_bridge.py 解析 JSON → PKBAPI（api.py）调 PKB/FileSaaS HTTP。
 *
 * 配置来源：api.pluginConfig（即 plugins.entries.pkb.config，含 baseUrl/apiKey/userId/fileSaaS）；
 * 勿使用 api.config（整份 OpenClaw 配置）。
 * FileSaaS 也可由插件目录 .env、config.json 在 Python 侧补全（见 api._filesaas_settings）。
 */
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { Type } from "@sinclair/typebox";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

type PKBConfig = {
  baseUrl: string;
  apiKey: string;
  userId: string;
  /** 可选：与 .env / 插件 config.json 等价，写入子进程环境供 Python 读取 FILESAAS_* */
  fileSaaS?: {
    appId?: string;
    appSecret?: string;
    /** 与 config.json 的 tenantId 二选一 */
    tenant?: string;
    tenantId?: string;
    /** 与 config.json 的 uploadServer 二选一 */
    server?: string;
    uploadServer?: string;
  };
};

/** Python 桥脚本绝对路径（与 cwd=插件根目录配合，便于读 config.json/.env）。 */
function bridgeScriptPath(): string {
  return path.join(__dirname, "scripts", "openclaw_bridge.py");
}

/** 把 OpenClaw 里的 fileSaaS 配置映射成子进程环境变量，供 api.py 读取 FILESAAS_*。 */
function bridgeEnvForConfig(cfg: PKBConfig): NodeJS.ProcessEnv {
  const env = { ...process.env };
  const fs = cfg.fileSaaS;
  if (fs?.appId) {
    env.FILESAAS_APP_ID = fs.appId;
  }
  if (fs?.appSecret) {
    env.FILESAAS_APP_SECRET = fs.appSecret;
  }
  const tenant = fs?.tenant ?? fs?.tenantId;
  if (tenant) {
    env.FILESAAS_TENANT = tenant;
  }
  const server = fs?.server ?? fs?.uploadServer;
  if (server) {
    env.FILESAAS_SERVER = server;
  }
  return env;
}

/**
 * Python 桥在失败时会把 {"ok":false,"error":"..."} 打在 stdout 且 exit code≠0；
 * 若不在此解析 stdout，日志里只会出现「python exited with code 1」而丢失真实原因。
 */
function runBridge(
  payload: Record<string, unknown>,
  env: NodeJS.ProcessEnv
): Promise<unknown> {
  return new Promise<unknown>((resolve, reject) => {
    const p = spawn("python3", [bridgeScriptPath(), JSON.stringify(payload)], {
      cwd: __dirname,
      env
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
        reject(
          new Error(
            `invalid JSON from bridge: stdout=${trimmed.slice(0, 500)}`
          )
        );
        return;
      }
      resolve("result" in parsed && parsed.result !== undefined ? parsed.result : parsed);
    });
  });
}

/** 每个桥调用都带的 PKB 身份（由 Gateway 注入的插件 config，非仅依赖 .env）。 */
function basePayload(cfg: PKBConfig, action: string) {
  return {
    action,
    baseUrl: cfg.baseUrl,
    apiKey: cfg.apiKey,
    userId: cfg.userId
  };
}

export default definePluginEntry({
  id: "pkb",
  name: "PKB",
  description: "PKB 知识库工具：上传索引、等待索引完成、问答检索与删除资源。",
  register(api) {
    const cfg = (api.pluginConfig ??
      api.config.plugins?.entries?.pkb?.config ??
      {}) as PKBConfig;
    const bridgeEnv = bridgeEnvForConfig(cfg);

    api.registerTool({
      name: "pkb_upload_file",
      description: "上传本地文件到 PKB 建索引；可附带 Nextcloud 公共链接用于问答溯源。",
      parameters: Type.Object({
        localPath: Type.String({ description: "本地文件路径" }),
        resourceName: Type.String({ description: "知识库资源名，建议使用与 Nextcloud 一致的逻辑路径" }),
        sourceUrl: Type.Optional(Type.String({ description: "Nextcloud 公共访问链接" }))
      }),
      async execute(_id, params) {
        const result = await runBridge(
          {
            ...basePayload(cfg, "upload_file"),
            localPath: params.localPath,
            resourceName: params.resourceName,
            ...(params.sourceUrl !== undefined ? { sourceUrl: params.sourceUrl } : {})
          },
          bridgeEnv
        );
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });

    api.registerTool({
      name: "pkb_upload_text",
      description: "将一段文本直接写入 PKB 建索引；适合配合 Nextcloud 文本文件更新后同步。",
      parameters: Type.Object({
        text: Type.String({ description: "文本内容" }),
        resourceName: Type.String({ description: "知识库资源名，建议与 Nextcloud 路径一致" }),
        sourceUrl: Type.Optional(Type.String({ description: "Nextcloud 公共访问链接" })),
        suffix: Type.Optional(Type.String({ description: "临时文件后缀，例如 .md 或 .txt" }))
      }),
      async execute(_id, params) {
        const result = await runBridge(
          {
            ...basePayload(cfg, "upload_text"),
            text: params.text,
            resourceName: params.resourceName,
            ...(params.sourceUrl !== undefined ? { sourceUrl: params.sourceUrl } : {}),
            ...(params.suffix !== undefined ? { suffix: params.suffix } : {})
          },
          bridgeEnv
        );
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });

    api.registerTool({
      name: "pkb_wait_resource_indexed",
      description: "轮询等待 PKB 资源出现在列表中，用于确认索引流程已完成。",
      parameters: Type.Object({
        resourceName: Type.String(),
        timeoutSeconds: Type.Optional(Type.Number({ description: "超时时间，默认 60 秒" })),
        intervalSeconds: Type.Optional(Type.Number({ description: "轮询间隔，默认 2 秒" }))
      }),
      async execute(_id, params) {
        const result = await runBridge(
          {
            ...basePayload(cfg, "wait_resource"),
            resourceName: params.resourceName,
            ...(params.timeoutSeconds !== undefined ? { timeoutSeconds: params.timeoutSeconds } : {}),
            ...(params.intervalSeconds !== undefined ? { intervalSeconds: params.intervalSeconds } : {})
          },
          bridgeEnv
        );
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });

    api.registerTool({
      name: "pkb_delete_resource",
      description: "删除 PKB 中与 Nextcloud 文件对应的索引资源。",
      parameters: Type.Object({
        resourceName: Type.String()
      }),
      async execute(_id, params) {
        const result = await runBridge(
          { ...basePayload(cfg, "delete_resource"), resourceName: params.resourceName },
          bridgeEnv
        );
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });

    api.registerTool({
      name: "pkb_list_resources",
      description: "列出当前 PKB 知识库资源。",
      parameters: Type.Object({
        page: Type.Optional(Type.Number()),
        size: Type.Optional(Type.Number())
      }),
      async execute(_id, params) {
        const result = await runBridge(
          {
            ...basePayload(cfg, "list_resources"),
            ...(params.page !== undefined ? { page: params.page } : {}),
            ...(params.size !== undefined ? { size: params.size } : {})
          },
          bridgeEnv
        );
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });

    api.registerTool({
      name: "pkb_ask",
      description: "对 PKB 知识库提问，返回答案以及带公开链接的溯源信息。",
      parameters: Type.Object({
        question: Type.String(),
        sessionId: Type.Optional(Type.String())
      }),
      async execute(_id, params) {
        const result = await runBridge(
          {
            ...basePayload(cfg, "ask"),
            question: params.question,
            ...(params.sessionId !== undefined ? { sessionId: params.sessionId } : {})
          },
          bridgeEnv
        );
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });
  }
});
