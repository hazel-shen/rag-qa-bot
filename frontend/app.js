// web/app.js
(function () {
  const cfg = window.APP_CONFIG || {};
  const BASE = (cfg.BACKEND_URL || "").replace(/\/+$/,"");
  const ASK_URL = BASE + (cfg.ASK_PATH || "/ask");
  const HEALTH_URL = BASE + (cfg.HEALTHZ_PATH || "/healthz");

  const $ = (sel) => document.querySelector(sel);
  const btnAsk = $("#btnAsk");
  const btnHealth = $("#btnHealth");
  const txt = $("#query");
  const keep = $("#chkKeep");
  const hint = $("#hint");

  const card = $("#result");
  const badgeCached = $("#badgeCached");
  const badge429 = $("#badge429");
  const retryCountdown = $("#retryCountdown");
  const answer = $("#answer");
  const ulSources = $("#sources");
  const ulStats = $("#stats");

  let retryTimer = null;

  function setLoading(on) {
    btnAsk.disabled = on;
    btnAsk.textContent = on ? "查詢中…" : "送出";
    hint.textContent = on ? "正在向伺服器發送請求…" : "";
  }

  function renderSources(sources = []) {
    ulSources.innerHTML = "";
    for (const s of sources) {
      const li = document.createElement("li");
      const title = s.title || s.source || s.id || "來源";
      const score = typeof s.score === "number" ? s.score.toFixed(3) : String(s.score ?? "");
      const rerank = typeof s.reranker_score === "number" ? s.reranker_score.toFixed(3) : "";
      li.textContent = `${title}  (score=${score}${rerank ? `, rerank=${rerank}` : ""})`;
      ulSources.appendChild(li);
    }
  }

  function renderStats(meta = {}) {
    ulStats.innerHTML = "";
    const add = (k, v) => {
      const li = document.createElement("li");
      li.textContent = `${k}: ${v}`;
      ulStats.appendChild(li);
    };
    if (meta.cached != null) add("cached", meta.cached ? "yes" : "no");
    if (meta.cost_usd != null) add("cost_usd", `$${meta.cost_usd.toFixed ? meta.cost_usd.toFixed(6) : meta.cost_usd}`);
    if (meta.rerank_model) add("rerank_model", meta.rerank_model);
    if (meta.top_k != null) add("top_k", meta.top_k);
    if (meta.policy_version) add("policy_version", meta.policy_version);
    if (meta.request_id) add("request_id", meta.request_id);
    if (meta.usage) {
      const u = meta.usage;
      add("input_tokens", u.input_tokens ?? "-");
      add("output_tokens", u.output_tokens ?? "-");
      add("total_tokens", u.total_tokens ?? "-");
    }
  }

  function show429(retryAfter) {
    badge429.classList.remove("hidden");
    let remain = parseInt(retryAfter, 10);
    if (!Number.isFinite(remain) || remain <= 0) remain = 5;
    retryCountdown.textContent = remain;
    clearInterval(retryTimer);
    retryTimer = setInterval(() => {
      remain -= 1;
      retryCountdown.textContent = remain;
      if (remain <= 0) {
        clearInterval(retryTimer);
        badge429.classList.add("hidden");
        hint.textContent = "可以再試一次囉。";
      }
    }, 1000);
  }

  async function ask() {
    const q = (txt.value || "").trim();
    if (!q) {
      hint.textContent = "請先輸入問題。";
      return;
    }
    setLoading(true);
    badge429.classList.add("hidden");
    clearInterval(retryTimer);

    try {
      const resp = await fetch(ASK_URL, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ query: q })
      });

      if (resp.status === 429) {
        const retryAfter = resp.headers.get("Retry-After") || "5";
        show429(retryAfter);
        setLoading(false);
        return;
      }

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        hint.textContent = `錯誤（${resp.status}）：${err.message || "請稍後再試"}`;
        setLoading(false);
        return;
      }

      const data = await resp.json();
      card.classList.remove("hidden");
      badgeCached.classList.toggle("hidden", !data?.meta?.cached);
      answer.textContent = (data.answer || "").replace(/\n{2,}/g, "\n\n"); // 避免奇怪 \n 堆疊
      renderSources(data?.meta?.sources || []);
      renderStats(data?.meta || {});
      hint.textContent = "完成。";
      if (!keep.checked) txt.value = "";

    } catch (e) {
      hint.textContent = "網路異常或伺服器無回應。";
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function healthz() {
    try {
      const resp = await fetch(HEALTH_URL);
      if (resp.ok) {
        hint.textContent = "後端健康 OK。";
      } else {
        hint.textContent = `健康檢查失敗（${resp.status}）`;
      }
    } catch {
      hint.textContent = "無法連線到後端。";
    }
  }

  btnAsk.addEventListener("click", ask);
  btnHealth.addEventListener("click", healthz);
  txt.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
  });
})();
