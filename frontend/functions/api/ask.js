// frontend/functions/api/ask.js
export async function onRequestPost(context) {
  const { request, env } = context;

  const body = await request.text();

  // 準備轉發用標頭（避免帶入 hop-by-hop）
  const headers = new Headers(request.headers);
  headers.delete("Host");
  headers.delete("Content-Length");

  // ✅ Pages → Worker 來源驗證（與 Worker 的 PAGES_SECRET 對上）
  headers.set("x-from-pages", env.PAGES_SECRET);

  // ✅ Worker 受 Cloudflare Access 保護時必帶的 Service Token 標頭
  headers.set("CF-Access-Client-Id", env.CF_ACCESS_CLIENT_ID);
  headers.set("CF-Access-Client-Secret", env.CF_ACCESS_CLIENT_SECRET);

  // （可選）把最終使用者的 Access JWT 往下傳，方便審計/每使用者限流
  const jwt = request.headers.get("Cf-Access-Jwt-Assertion");
  if (jwt) headers.set("Cf-Access-Jwt-Assertion", jwt);

  const upstream = await fetch(`${env.BACKEND_URL}/ask`, {
    method: "POST",
    headers,
    body,
    cf: { cacheTtl: 0, cacheEverything: false }
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: upstream.headers
  });
}
