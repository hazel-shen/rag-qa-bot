// frontend/functions/api/healthz.js
import { proxyToWorker } from "../_proxy";

export async function onRequestGet(context) {
  const { request, env } = context;
  return proxyToWorker(request, env, "/healthz", "GET");
}
