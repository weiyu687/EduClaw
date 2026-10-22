"""Deliberately bounded JSON Schema subset used for local tool contracts."""
import math

KEYS = {"type", "properties", "required", "additionalProperties", "items", "enum",
        "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems",
        "description", "title", "default"}
TYPES = {"object": dict, "array": list, "string": str, "integer": int,
         "number": (int, float), "boolean": bool, "null": type(None)}


def check_schema(schema):
    if not isinstance(schema, dict) or set(schema) - KEYS or schema.get("type") not in TYPES:
        raise ValueError("Tool schema uses unsupported keywords or lacks a supported type.")
    if schema["type"] == "object":
        if not isinstance(schema.get("properties", {}), dict) or type(schema.get("additionalProperties", False)) is not bool:
            raise ValueError("Invalid object schema.")
        required = schema.get("required", [])
        if not isinstance(required, list) or any(not isinstance(x, str) for x in required) or set(required) - set(schema.get("properties", {})):
            raise ValueError("Invalid required properties.")
        for value in schema.get("properties", {}).values():
            check_schema(value)
    if schema["type"] == "array":
        check_schema(schema.get("items"))


def validate(value, schema):
    kind = schema["type"]
    if not isinstance(value, TYPES[kind]) or (kind in ("number", "integer") and isinstance(value, bool)):
        raise ValueError(f"Tool argument must be {kind}.")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("Tool argument outside enum.")
    if kind == "object":
        props = schema.get("properties", {})
        if set(schema.get("required", [])) - set(value):
            raise ValueError("Missing tool argument.")
        if not schema.get("additionalProperties", False) and set(value) - set(props):
            raise ValueError("Unexpected tool argument.")
        for key, item in value.items():
            if key in props:
                validate(item, props[key])
    if kind == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10000):
            raise ValueError("Tool array size outside bounds.")
        for item in value:
            validate(item, schema["items"])
    if kind == "string" and not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 64000):
        raise ValueError("Tool string size outside bounds.")
    if kind in ("integer", "number"):
        if not math.isfinite(value) or not schema.get("minimum", -math.inf) <= value <= schema.get("maximum", math.inf):
            raise ValueError("Tool number outside bounds.")
