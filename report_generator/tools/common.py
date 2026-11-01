import json


def to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
