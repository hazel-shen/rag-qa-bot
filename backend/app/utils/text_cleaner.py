# app/utils/text_cleaner.py
import re

def clean_answer(text: str, *, single_line: bool = False) -> str:
    """清掉冗語、來源尾註、過多換行；可選擇壓成單行。"""
    if not text:
        return text

    t = text.strip()

    # 移除模型常見的尾註或來源括號
    t = re.sub(r'\s*\(source:.*?\)\s*$', '', t, flags=re.I | re.S)

    # 統一空白與換行
    t = t.replace('\r\n', '\n')
    t = re.sub(r'[ \t]+', ' ', t)          # 多個空白 → 1 個
    t = re.sub(r'\n{3,}', '\n\n', t)       # 3 個以上換行 → 2 個

    # 去掉開場贅詞（可依喜好擴充）
    t = re.sub(r'^\s*答[:：]\s*', '', t, flags=re.I)
    t = re.sub(r'(?i)^(以下|如下)[^：:]*[:：]\s*', '', t)

    # 統一項目符號（1. / 1) / - / * → •）
    t = re.sub(r'^\s*[-*•]\s*', '• ', t, flags=re.M)
    t = re.sub(r'^\s*\d+[.)]\s*', '• ', t, flags=re.M)

    if single_line:
        # 完全移除換行，避免 JSON 看到一堆 \n
        t = re.sub(r'\s*\n\s*', ' ', t)
        t = re.sub(r'\s{2,}', ' ', t).strip()

    return t


def squash_whitespace(text: str) -> str:
    """用在 preview：把所有空白壓成單一空白。"""
    return re.sub(r'\s+', ' ', (text or '')).strip()
