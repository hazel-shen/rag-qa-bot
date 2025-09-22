import re
from fastapi import HTTPException

def validate_query(query: str):
    if re.search(r"(127\.0\.0\.1|localhost|0\.0\.0\.0)", query):
        raise HTTPException(status_code=403, detail="Blocked internal URL access")

    if re.search(r"(DROP\s+TABLE|UNION\s+SELECT|INSERT\s+INTO)", query, re.IGNORECASE):
        raise HTTPException(status_code=403, detail="Blocked injection attempt")

    return query
