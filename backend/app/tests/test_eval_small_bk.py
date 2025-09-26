# # app/tests/test_eval_small.py
# """
# 小型資料集自動評測（會真的打 OpenAI API，注意 token 成本）
# """

# import json
# import os
# import re
# import sys
# from pathlib import Path
# import pytest
# import importlib

# # ✅ 在檔案最早就關掉 stub，確保會打 OpenAI
# os.environ["RAG_DISABLE_STUB"] = "1"

# # ---- 參數（可用環境變數覆蓋）----
# DEFAULT_DATASET = Path(__file__).parent / "data" / "eval_small.jsonl"
# DATASET = Path(os.environ.get("EVAL_DATASET", str(DEFAULT_DATASET))).resolve()
# JACCARD_THRESHOLD = float(os.environ.get("EVAL_JACCARD_THRESHOLD", "0.60"))
# PASS_RATE = float(os.environ.get("EVAL_PASS_RATE", "0.60"))
# NGRAM_N = int(os.environ.get("EVAL_NGRAM_N", "2"))

# # 若從 repo 根目錄跑 pytest，補上 backend 到 sys.path
# sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# CLIENT = None
# _IMPORT_ERR = None


# def _ensure_client():
#     """建立 FastAPI TestClient；失敗時 skip"""
#     global CLIENT, _IMPORT_ERR
#     if CLIENT is not None:
#         return CLIENT
#     try:
#         from fastapi.testclient import TestClient
#         from app.main import app
#         CLIENT = TestClient(app)
#         return CLIENT
#     except Exception as e:
#         _IMPORT_ERR = e
#         CLIENT = None
#         return None


# # ---- 字串正規化 + 簡單同義詞替換 ----
# _REPL = {
#     "健康檢查": "/healthz",
#     "指標": "/metrics",
#     "api端點": "api",
#     "端點": "api",
# }


# def _normalize(s: str) -> str:
#     s = (s or "").lower().strip()
#     for k, v in _REPL.items():
#         s = s.replace(k, v)
#     s = re.sub(r"\s+", "", s)
#     s = re.sub(r"[，,。．\.！!？?；;：:\-—_~～/\\()\[\]【】{}<>\"'“”‘’•·・#*@＋+|]", "", s)
#     return s


# def _char_ngrams(s: str, n=2):
#     s = _normalize(s)
#     if len(s) < n:
#         return {s} if s else set()
#     return {s[i:i+n] for i in range(len(s) - n + 1)}


# def _jaccard(a: str, b: str, n=2) -> float:
#     A, B = _char_ngrams(a, n), _char_ngrams(b, n)
#     if not A and not B:
#         return 0.0
#     return len(A & B) / (len(A | B) or 1)


# # ---- 呼叫 API：只取 answer ----
# def _ask_raw(query: str) -> dict:
#     client = _ensure_client()
#     if client is None:
#         pytest.skip(
#             "FastAPI app 未匯入成功；請確認 PYTHONPATH 或 app.main:app 可用。\n"
#             f"ImportError: {_IMPORT_ERR}\n"
#         )
#     r = client.post("/ask", json={"query": query})
#     assert r.status_code == 200, f"/ask failed: {r.status_code} {r.text}"
#     return r.json()


# def _pick_answer_only(resp: dict) -> str:
#     ans = resp.get("answer")
#     return ans.strip() if isinstance(ans, str) else ""


# def _load_dataset(path: Path):
#     rows = []
#     with path.open("r", encoding="utf-8") as f:
#         for line in f:
#             if line.strip():
#                 rows.append(json.loads(line))
#     return rows


# # ---- 測試本體 ----
# @pytest.mark.eval_bk
# def test_eval_on_small_dataset(monkeypatch):
#     # 沒有真金鑰就 skip
#     api_key = os.environ.get("OPENAI_API_KEY")
#     if not api_key or api_key == "sk-test-fake":
#         pytest.skip("需要真實 OPENAI_API_KEY；否則略過 eval 測試。")

#     # 保險：還原 llm 模組，避免之前被 monkeypatch
#     import app.llm as llm_mod
#     importlib.reload(llm_mod)

#     # ✅ 測試時強制模型保守輸出（相容 Pydantic frozen 設定）
#     import app.config as config
#     try:
#         # Pydantic v2：用 model_copy(update=...) 產生新設定，再整體 monkeypatch 回去
#         new_settings = config.settings.model_copy(update={
#             "temperature": 0,
#             "top_p": 1,
#             "answer_max_tokens": (
#                 128 if not getattr(config.settings, "answer_max_tokens", None)
#                 else min(128, getattr(config.settings, "answer_max_tokens"))
#             ),
#         })
#         monkeypatch.setattr(config, "settings", new_settings, raising=True)
#     except Exception:
#         # 後備方案：用環境變數 + 重新載入設定模組
#         monkeypatch.setenv("OPENAI_TEMPERATURE", "0")
#         monkeypatch.setenv("OPENAI_TOP_P", "1")
#         monkeypatch.setenv("ANSWER_MAX_TOKENS", "128")
#         importlib.reload(config)

#     # 重要：確保 llm 模組看到最新 settings（避免舊引用）
#     import app.llm as llm_mod
#     importlib.reload(llm_mod)

#     rows = _load_dataset(DATASET)
#     assert rows, "eval_small.jsonl 為空，請先填 5–20 筆 QA"

#     passed = 0
#     detailed = []

#     for item in rows:
#         q, ref = item["question"], item["answer"]
#         resp = _ask_raw(q)
#         pred = _pick_answer_only(resp)
#         score = _jaccard(ref, pred, NGRAM_N) if pred else 0.0
#         ok = (pred != "") and (score >= JACCARD_THRESHOLD)
#         detailed.append((ok, score, q, ref, pred, resp))
#         if ok:
#             passed += 1

#     acc = passed / len(rows)
#     print(f"\n[eval] accuracy = {acc:.2f} ({passed}/{len(rows)}) | thr={JACCARD_THRESHOLD:.2f}")

#     failures = [d for d in detailed if not d[0]]
#     for _, score, q, ref, pred, resp in failures:
#         meta = resp.get("meta") or {}
#         rid = meta.get("request_id", "N/A")
#         preview = (meta.get("context_preview") or "")[:120]
#         print(
#             "[eval][fail] jaccard={:.2f} | request_id={}\n"
#             "  Q   : {}\n"
#             "  REF : {}\n"
#             "  ANS : {}\n"
#             "  PREV: {}...\n".format(
#                 score, rid, q, ref, (pred if pred else "<EMPTY>"), preview
#             )
#         )

#     assert acc >= PASS_RATE, f"accuracy too low on small dataset: {acc:.2f} < {PASS_RATE}"
