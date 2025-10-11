# tests/test_aws_secrets.py
import os
import json
import base64
import logging
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

# === 調整這個路徑成實際模組位置 ===
MODULE_PATH = "app.aws_secrets"

# 動態載入目標模組與函式
aws_secrets = __import__(MODULE_PATH, fromlist=["*"])
load_from_secrets_manager = getattr(aws_secrets, "load_from_secrets_manager")


def _make_client_mock(resp_or_exc):
    client = MagicMock()
    if isinstance(resp_or_exc, Exception):
        client.get_secret_value.side_effect = resp_or_exc
    else:
        client.get_secret_value.return_value = resp_or_exc
    return client


@pytest.fixture(autouse=True)
def _clean_env():
    # 測試前後清理可能被寫入的環境變數，避免相互污染
    keys = ["FOO", "HELLO"]
    snapshot = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    yield
    for k, v in snapshot.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_secretstring_success(caplog):
    data = {"FOO": "bar"}
    resp = {"SecretString": json.dumps(data)}

    with patch("boto3.client", return_value=_make_client_mock(resp)):
        caplog.set_level(logging.WARNING)
        out = load_from_secrets_manager("dummy-id")
        assert out == data
        # setdefault 不覆蓋現有變數，但此處應已注入
        assert os.environ["FOO"] == "bar"
        # 不應該在 log 中看到 secret_id（若你採用了安全 logging 修正）
        assert "dummy-id" not in caplog.text


def test_secretbinary_success():
    data = {"HELLO": "world"}
    raw = json.dumps(data).encode("utf-8")
    resp = {"SecretBinary": base64.b64encode(raw)}

    with patch("boto3.client", return_value=_make_client_mock(resp)):
        out = load_from_secrets_manager("dummy-id")
        assert out == data
        assert os.environ["HELLO"] == "world"


def test_invalid_json(caplog):
    # 回傳的是 list/str 等非 object，應觸發 Invalid secret format
    resp = {"SecretString": "[1, 2, 3]"}
    with patch("boto3.client", return_value=_make_client_mock(resp)):
        caplog.set_level(logging.WARNING)
        out = load_from_secrets_manager("dummy-id")
        assert out == {}
        assert "Invalid secret format" in caplog.text
        # 安全起見，也不應包含 secret_id
        assert "dummy-id" not in caplog.text


def test_clienterror(caplog):
    exc = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"},
         "ResponseMetadata": {"RequestId": "req-123"}},
        "GetSecretValue",
    )
    with patch("boto3.client", return_value=_make_client_mock(exc)):
        caplog.set_level(logging.WARNING)
        out = load_from_secrets_manager("dummy-id")
        assert out == {}
        # 驗證有記錄到錯誤但不外洩 secret_id
        assert "AWS Secrets Manager error" in caplog.text
        assert "dummy-id" not in caplog.text
