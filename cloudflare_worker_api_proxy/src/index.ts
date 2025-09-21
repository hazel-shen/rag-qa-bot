export interface Env {
  TARGET_BASE_URL: string;
  WORKER_SHARED_SECRET?: string; // Worker → 後端的密鑰 (給 EC2 用)
  PAGES_SECRET: string;          // Pages → Worker 的密鑰 (只允許 Pages 呼叫)
}

const ALLOWED_ORIGIN = "https://rag-qa-bot.pages.dev"; // 你的 Pages 網域

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // --- 健康檢查端點，不經過上游 ---
    if (url.pathname === "/ping") {
      return new Response(JSON.stringify({
        ok: true,
        time: new Date().toISOString(),
        worker: true,
      }), {
        status: 200,
        headers: {
          "content-type": "application/json",
          "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        },
      });
    }

    // --- CORS Preflight ---
    if (req.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
          "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
          "Access-Control-Allow-Headers": "authorization,content-type,x-request-id,x-from-pages",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    // --- 驗證 Pages Secret ---
    const pagesToken = req.headers.get("x-from-pages");
    if (!pagesToken || pagesToken !== env.PAGES_SECRET) {
      return new Response("Forbidden: invalid caller", { status: 403 });
    }

    // --- 重寫目標 URL ---
    const upstream = new URL(env.TARGET_BASE_URL);
    upstream.pathname = url.pathname;
    upstream.search = url.search;

    // --- 標頭處理 ---
    const headers = new Headers(req.headers);
    if (env.WORKER_SHARED_SECRET) {
      headers.set("X-From-Worker", env.WORKER_SHARED_SECRET);
    }
    headers.delete("cookie");

    // --- 轉發 ---
    const resp = await fetch(upstream.toString(), {
      method: req.method,
      headers,
      body: ["GET", "HEAD"].includes(req.method) ? undefined : req.body,
      redirect: "follow",
    });

    // --- 回傳 + CORS ---
    const outHeaders = new Headers(resp.headers);
    outHeaders.set("Access-Control-Allow-Origin", ALLOWED_ORIGIN);
    outHeaders.set("Access-Control-Expose-Headers", "*");

    return new Response(resp.body, {
      status: resp.status,
      statusText: resp.statusText,
      headers: outHeaders,
    });
  },
};
