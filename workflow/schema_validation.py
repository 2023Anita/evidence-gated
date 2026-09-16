"""项目内置的受限 JSON Schema 校验器。

只实现仓库内三个 Schema 用到的关键词。遇到未知关键词会拒绝，避免静默忽略规则。
"""

from __future__ import annotations

import json
import re

from .common import GateError

SUPPORTED = {
    "$schema", "type", "properties", "required", "additionalProperties", "const", "enum",
    "pattern", "minLength", "maxLength", "minItems", "maxItems", "uniqueItems", "items",
}


def _kind(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def validate(value, schema: dict, path: str = "$"):
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise GateError(20, f"INFRA_ERROR：Schema 使用未实现关键词 {sorted(unknown)}")
    if "const" in schema and value != schema["const"]:
        raise GateError(2, f"INVALID_CONTRACT：{path} 必须等于 {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise GateError(2, f"INVALID_CONTRACT：{path} 不是允许值")
    expected = schema.get("type")
    if expected and _kind(value) != expected:
        raise GateError(2, f"INVALID_CONTRACT：{path} 必须是 {expected}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1 << 60):
            raise GateError(2, f"INVALID_CONTRACT：{path} 长度不符合约束")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise GateError(2, f"INVALID_CONTRACT：{path} 格式不符合约束")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 1 << 60):
            raise GateError(2, f"INVALID_CONTRACT：{path} 项目数不符合约束")
        if schema.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            raise GateError(2, f"INVALID_CONTRACT：{path} 含重复项目")
        if "items" in schema:
            for index, item in enumerate(value):
                validate(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        if missing:
            raise GateError(2, f"INVALID_CONTRACT：{path} 缺少字段 {sorted(missing)}")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            if extra:
                raise GateError(2, f"INVALID_CONTRACT：{path} 含未知字段 {sorted(extra)}")
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key], f"{path}.{key}")
