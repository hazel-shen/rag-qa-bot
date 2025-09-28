// frontend/functions/api/healthz.js
export async function onRequestGet(context) {
  const { request, env } = context;

  const headers = new Headers();

  // ✅ Pages → Worker 來源驗證
  headers.set("x-from-pages", env.PAGES_SECRET);

  // ✅ Access Service Token（Worker 被 Access 保護）
  headers.set("CF-Access-Client-Id", env.CF_ACCESS_CLIENT_ID);
  headers.set("CF-Access-Client-Secret", env.CF_ACCESS_CLIENT_SECRET);

  // （可選）往下帶 Access JWT
  const jwt = request.headers.get("Cf-Access-Jwt-Assertion");
  if (jwt) headers.set("Cf-Access-Jwt-Assertion", jwt);

  const upstream = await fetch(`${env.BACKEND_URL}/healthz`, {
    method: "GET",
    headers,
    cf: { cacheTtl: 0, cacheEverything: false }
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: upstream.headers
  });
}
