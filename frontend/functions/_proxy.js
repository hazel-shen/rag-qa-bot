// frontend/functions/_proxy.js
export async function proxyToWorker(request, env, path, method = "GET") {
  // 清理標頭，避免 hop-by-hop header
  const headers = new Headers(request.headers);
  headers.delete("Host");
  headers.delete("Content-Length");

  // ✅ Pages → Worker 來源驗證
  headers.set("x-from-pages", env.PAGES_SECRET);

  // ✅ Access Service Token（Worker 被 Access 保護時）
  if (env.CF_ACCESS_CLIENT_ID && env.CF_ACCESS_CLIENT_SECRET) {
    headers.set("CF-Access-Client-Id", env.CF_ACCESS_CLIENT_ID);
    headers.set("CF-Access-Client-Secret", env.CF_ACCESS_CLIENT_SECRET);
  }

  // （可選）往下傳 Access JWT
  const jwt = request.headers.get("Cf-Access-Jwt-Assertion");
  if (jwt) headers.set("Cf-Access-Jwt-Assertion", jwt);

  // 🔑 轉發到 Worker
  return fetch(`${env.WORKER_URL}${path}`, {
    method,
    headers,
    body: ["GET", "HEAD"].includes(method) ? undefined : await request.text(),
    cf: { cacheTtl: 0, cacheEverything: false },
  });
}
