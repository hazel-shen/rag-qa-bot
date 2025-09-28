// frontend/functions/_middleware.js
//
// Cloudflare Access 版本（分層）：
// - 檢查 Cf-Access-Jwt-Assertion（保險）
// - 以「使用者身分」做 KV 限流（預設 100 次/小時）
// - /api/healthz 預設放行（可用 RL_HEALTHZ="true" 開）
// - 只對「重」的路徑做限流：POST /api/ask
//
// 需要在 Pages 專案設定：RATELIMIT_KV 綁定；環境變數（選）：RL_LIMIT, RL_WINDOW, RL_HEALTHZ

function identifyUser(req) {
  return (
    req.headers.get("Cf-Access-Authenticated-User-Email") ||
    req.headers.get("Cf-Access-Authenticated-User-Id") ||
    req.headers.get("CF-Connecting-IP") ||
    "unknown"
  );
}

function buildCorsHeaders(req) {
  const origin = req.headers.get("Origin") || "*";
  return {
    "Access-Control-Allow-Origin": origin,
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}

async function applyRateLimit(env, key) {
  const limit = parseInt(env.RL_LIMIT || "100", 10);
  const windowSec = parseInt(env.RL_WINDOW || "3600", 10);
  const now = Date.now();

  let rec;
  const raw = await env.RATELIMIT_KV.get(key);
  if (raw) { try { rec = JSON.parse(raw); } catch { rec = null; } }

  if (!rec || typeof rec.reset !== "number" || now >= rec.reset) {
    const reset = now + windowSec * 1000;
    rec = { n: 1, reset };
    await env.RATELIMIT_KV.put(key, JSON.stringify(rec), { expirationTtl: windowSec + 5 });
    return { allowed: true, retryAfterSec: 0, limit, remaining: limit - 1, resetAt: Math.ceil(reset / 1000) };
  }

  if (rec.n >= limit) {
    const retryAfterSec = Math.max(1, Math.ceil((rec.reset - now) / 1000));
    return { allowed: false, retryAfterSec, limit, remaining: 0, resetAt: Math.ceil(rec.reset / 1000) };
  }

  rec.n += 1;
  const remainSec = Math.max(1, Math.ceil((rec.reset - now) / 1000));
  await env.RATELIMIT_KV.put(key, JSON.stringify(rec), { expirationTtl: remainSec + 5 });
  return { allowed: true, retryAfterSec: 0, limit, remaining: limit - rec.n, resetAt: Math.ceil(rec.reset / 1000) };
}

export async function onRequest(context) {
  const { request, env, next } = context;
  const url = new URL(request.url);
  const path = url.pathname;

  // 只處理 /api/*；其他交給靜態資源
  if (!path.startsWith("/api/")) return next();

  const cors = buildCorsHeaders(request);

  // Preflight
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: cors });
  }

  // Access（保險檢查）
  const accessJwt = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!accessJwt) {
    return new Response("Unauthorized", { status: 401, headers: cors });
  }

  // healthz 預設不做限流；設 RL_HEALTHZ="true" 可開啟
  const isHealthz = path === "/api/healthz";
  const limitHealthz = String(env.RL_HEALTHZ || "false").toLowerCase() === "true";

  // 只對「重」的路徑限流：POST /api/ask（你也可擴成清單）
  const shouldRateLimit =
    (path === "/api/ask" && request.method === "POST") ||
    (isHealthz && limitHealthz);

  if (shouldRateLimit) {
    try {
      const user = identifyUser(request);
      const key = `rl:${user}`;
      const { allowed, retryAfterSec, limit, remaining, resetAt } = await applyRateLimit(env, key);
      if (!allowed) {
        const headers = new Headers(cors);
        headers.set("Retry-After", String(retryAfterSec));
        headers.set("X-RateLimit-Limit", String(limit));
        headers.set("X-RateLimit-Remaining", "0");
        headers.set("X-RateLimit-Reset", String(resetAt));
        return new Response("Too Many Requests", { status: 429, headers });
      }
      // 成功也附上限流資訊（方便觀測）
      context.rateLimitInfo = { limit, remaining: Math.max(0, remaining), resetAt };
    } catch (e) {
      // 限流出錯：為了可用性放行（你可改為 fail-closed）
      console.error("[ratelimit error]", e);
    }
  }

  const resp = await next();

  // 統一補上 CORS & 限流觀測標頭（若有）
  const h = new Headers(resp.headers);
  Object.entries(cors).forEach(([k, v]) => h.set(k, v));
  if (context.rateLimitInfo) {
    const { limit, remaining, resetAt } = context.rateLimitInfo;
    h.set("X-RateLimit-Limit", String(limit));
    h.set("X-RateLimit-Remaining", String(remaining));
    h.set("X-RateLimit-Reset", String(resetAt));
  }
  return new Response(resp.body, { status: resp.status, headers: h });
}
