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
};

function bridgeScriptPath(): string {
  return path.join(__dirname, "scripts", "openclaw_bridge.py");
}

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
      if (code !== 0) {
        reject(new Error(stderr || `python exited with code ${code}`));
        return;
      }
      try {
        const parsed = JSON.parse(trimmed) as { ok?: boolean; error?: string; result?: unknown };
        if (parsed?.ok === false) {
          reject(new Error(parsed.error || "bridge error"));
          return;
        }
        resolve("result" in parsed && parsed.result !== undefined ? parsed.result : parsed);
      } catch (e) {
        reject(
          new Error(
            `invalid JSON from bridge: ${e instanceof Error ? e.message : String(e)}; stdout=${trimmed.slice(0, 500)}`
          )
        );
      }
    });
  });
}

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
    const cfg = api.config as PKBConfig;

    api.registerTool({
      name: "pkb_upload_file",
      description: "上传本地文件到 PKB 建索引；可附带 Nextcloud 公共链接用于问答溯源。",
      parameters: Type.Object({
        localPath: Type.String({ description: "本地文件路径" }),
        resourceName: Type.String({ description: "知识库资源名，建议使用与 Nextcloud 一致的逻辑路径" }),
        sourceUrl: Type.Optional(Type.String({ description: "Nextcloud 公共访问链接" }))
      }),
      async execute(_id, params) {
        const result = await runBridge({
          ...basePayload(cfg, "upload_file"),
          localPath: params.localPath,
          resourceName: params.resourceName,
          ...(params.sourceUrl !== undefined ? { sourceUrl: params.sourceUrl } : {})
        });
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
        const result = await runBridge({
          ...basePayload(cfg, "upload_text"),
          text: params.text,
          resourceName: params.resourceName,
          ...(params.sourceUrl !== undefined ? { sourceUrl: params.sourceUrl } : {}),
          ...(params.suffix !== undefined ? { suffix: params.suffix } : {})
        });
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
        const result = await runBridge({
          ...basePayload(cfg, "wait_resource"),
          resourceName: params.resourceName,
          ...(params.timeoutSeconds !== undefined ? { timeoutSeconds: params.timeoutSeconds } : {}),
          ...(params.intervalSeconds !== undefined ? { intervalSeconds: params.intervalSeconds } : {})
        });
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
        const result = await runBridge({
          ...basePayload(cfg, "delete_resource"),
          resourceName: params.resourceName
        });
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
        const result = await runBridge({
          ...basePayload(cfg, "list_resources"),
          ...(params.page !== undefined ? { page: params.page } : {}),
          ...(params.size !== undefined ? { size: params.size } : {})
        });
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
        const result = await runBridge({
          ...basePayload(cfg, "ask"),
          question: params.question,
          ...(params.sessionId !== undefined ? { sessionId: params.sessionId } : {})
        });
        return {
          content: [{ type: "text", text: JSON.stringify(result) }]
        };
      }
    });
  }
});
