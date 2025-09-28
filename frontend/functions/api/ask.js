// frontend/functions/api/ask.js
import { proxyToWorker } from "../_proxy";

export async function onRequestPost(context) {
  const { request, env } = context;
  return proxyToWorker(request, env, "/ask", "POST");
}
