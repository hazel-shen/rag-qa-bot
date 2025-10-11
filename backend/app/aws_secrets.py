"""
aws_secrets.py

專門負責 AWS Secrets Manager 整合：
- 在 APP_ENV=prod 時才會去讀取 Secrets Manager
- 在 APP_ENV=dev 或未指定時，只用本地 .env

好處：
- 本地開發簡單，直接 .env
- 產線自動從 Secrets Manager 撈設定
"""
import os
import json
import logging
import base64
from typing import Mapping, Dict

logger = logging.getLogger(__name__)

def load_from_secrets_manager(
    secret_id: str,
    region: str = os.getenv("AWS_REGION", "ap-northeast-1"),
    export_to_env: bool = True,
) -> Mapping[str, str]:
    """ 從 AWS Secrets Manager 讀取 secret 並回傳 dict。
        預期 secret 內容是一個 JSON 字串，
        例如： { "OPENAI_API_KEY": "sk-xxx", "REDIS_URL": "redis://..." } 
        Args: 
            secret_id: Secrets Manager 的名稱 (例: "ragqa/prod/app") 
            region: 預設 ap-northeast-1，可透過環境變數 AWS_REGION 覆寫 
            export_to_env: 是否自動把 key/value 注入 os.environ （使用 setdefault，不會覆蓋既有變數）
            Returns: dict: secret 的 key/value 
    """
    # 允許本地/測試環境沒有 boto3 也不報錯
    try:
        import boto3
        from botocore.config import Config as BotoConfig
        from botocore.exceptions import BotoCoreError, ClientError
    except Exception as e:
        logger.debug("boto3 not available (dev/local?): %s", e)
        return {}

    try:
        client = boto3.client(
            "secretsmanager",
            region_name=region,
            config=BotoConfig(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=3,
                read_timeout=3,
            ),
        )
        resp: Dict = client.get_secret_value(SecretId=secret_id)

        if "SecretString" in resp and resp["SecretString"] is not None:
            raw = resp["SecretString"]
        elif "SecretBinary" in resp and resp["SecretBinary"] is not None:
            # SecretBinary 是 base64 編碼
            raw_bytes = base64.b64decode(resp["SecretBinary"])
            raw = raw_bytes.decode("utf-8")
        else:
            raise ValueError("Secret has no SecretString or SecretBinary")

        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Secret JSON must be an object (key/value)")

        if export_to_env:
            for k, v in data.items():
                # setdefault: 不覆寫既有環境變數（保留 .env）
                os.environ.setdefault(str(k), str(v))

        return data

    except (BotoCoreError, ClientError) as e:
        err = getattr(e, "response", {}).get("Error", {})
        code = err.get("Code", e.__class__.__name__)
        req_id = getattr(e, "response", {}).get("ResponseMetadata", {}).get("RequestId")
        logger.warning(
            "AWS Secrets Manager error",
            extra={"err_code": code, "aws_request_id": req_id, "region": region},
        )
        return {}

    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(
            "Invalid secret format",
            extra={"err_type": e.__class__.__name__},
        )
        return {}