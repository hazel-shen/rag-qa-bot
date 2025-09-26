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
from typing import Mapping


def load_from_secrets_manager(
    secret_id: str,
    region: str = os.getenv("AWS_REGION", "ap-northeast-1"),
    export_to_env: bool = True,
) -> Mapping[str, str]:
    """
    從 AWS Secrets Manager 讀取 secret 並回傳 dict。
    預期 secret 內容是一個 JSON 字串，例如：
    {
      "OPENAI_API_KEY": "sk-xxx",
      "REDIS_URL": "redis://..."
    }

    Args:
        secret_id: Secrets Manager 的名稱 (例: "ragqa/prod/app")
        region: 預設 ap-northeast-1，可透過環境變數 AWS_REGION 覆寫
        export_to_env: 是否自動把 key/value 注入 os.environ
                       （使用 setdefault，不會覆蓋既有變數）

    Returns:
        dict: secret 的 key/value
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except Exception:
        # 沒裝 boto3 或本地測試環境，不做任何事
        return {}

    try:
        client = boto3.client("secretsmanager", region_name=region)
        resp = client.get_secret_value(SecretId=secret_id)

        # SecretString 存 JSON，SecretBinary 少見
        raw = resp.get("SecretString") or (resp.get("SecretBinary") or b"").decode()
        data = json.loads(raw)

        if export_to_env:
            for k, v in data.items():
                # setdefault -> 保留本地 .env，Secrets 只補充沒有的
                os.environ.setdefault(k, v)

        return data

    except (BotoCoreError, ClientError, ValueError, json.JSONDecodeError):
        return {}
