import re

READ_ONLY_QUERY_PATTERN = re.compile(
    r"^\s*(SELECT|SHOW|EXPLAIN|DESCRIBE|DESC|WITH)\b",
    re.IGNORECASE,
)


def is_read_only_query(query: str) -> bool:
    if not isinstance(query, str):
        return False
    return bool(READ_ONLY_QUERY_PATTERN.match(query))