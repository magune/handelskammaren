"""Convert schema.json to OpenAI strict-mode compatible schema_strict.json.

Transformations:
- Resolve all $ref by inlining $defs
- Add type to const fields
- Remove $defs, $schema, $id, title, description, pattern, minimum, maximum,
  minItems, maxItems, minLength, maxLength
- Convert type arrays like ["string", "null"] to anyOf
- Convert enum with null to anyOf [{enum: [non-null values]}, {type: "null"}]
- Ensure additionalProperties: false on all objects
- Ensure all properties are listed in required
"""

import copy
import json
from pathlib import Path

UNSUPPORTED_KEYS = {
    "$schema", "$id", "title", "description",
    "pattern", "minimum", "maximum",
    "minItems", "maxItems", "minLength", "maxLength",
    "minProperties", "maxProperties",
}


def load_schema():
    return json.loads(Path("schema.json").read_text(encoding="utf-8"))


def resolve_ref(ref_path: str, defs: dict) -> dict:
    """Resolve a $ref like '#/$defs/nullableString' to its definition."""
    parts = ref_path.split("/")
    # Expected: ['#', '$defs', 'defName']
    if len(parts) == 3 and parts[0] == "#" and parts[1] == "$defs":
        def_name = parts[2]
        if def_name in defs:
            return copy.deepcopy(defs[def_name])
    raise ValueError(f"Cannot resolve $ref: {ref_path}")


def convert_node(node, defs: dict, visited=None) -> dict:
    """Recursively convert a schema node to strict-mode compatible."""
    if visited is None:
        visited = set()

    if not isinstance(node, dict):
        return node

    # Resolve $ref first
    if "$ref" in node:
        resolved = resolve_ref(node["$ref"], defs)
        return convert_node(resolved, defs, visited)

    result = {}

    # Handle const — add type
    if "const" in node:
        val = node["const"]
        if isinstance(val, str):
            result["type"] = "string"
        elif isinstance(val, bool):
            result["type"] = "boolean"
        elif isinstance(val, int):
            result["type"] = "integer"
        elif isinstance(val, float):
            result["type"] = "number"
        result["enum"] = [val]
        return result

    # Handle type arrays like ["string", "null"]
    if "type" in node and isinstance(node["type"], list):
        types = node["type"]
        non_null = [t for t in types if t != "null"]
        has_null = "null" in types
        if has_null and len(non_null) == 1:
            inner = dict(node)
            inner["type"] = non_null[0]
            del_keys = [k for k in inner if k in UNSUPPORTED_KEYS]
            for k in del_keys:
                del inner[k]
            converted_inner = convert_node(inner, defs, visited)
            return {"anyOf": [converted_inner, {"type": "null"}]}
        elif not has_null:
            node = dict(node)
            node["type"] = non_null[0] if len(non_null) == 1 else non_null[0]

    # Handle enum with null
    if "enum" in node and None in node["enum"]:
        non_null_vals = [v for v in node["enum"] if v is not None]
        if non_null_vals:
            return {"anyOf": [{"type": "string", "enum": non_null_vals}, {"type": "null"}]}
        else:
            return {"type": "null"}

    # Handle enum without null — add type
    if "enum" in node and "type" not in node:
        vals = node["enum"]
        if all(isinstance(v, str) for v in vals):
            result["type"] = "string"
        result["enum"] = vals
        return result

    # Copy over supported keys
    for key, value in node.items():
        if key in UNSUPPORTED_KEYS:
            continue
        if key == "$defs":
            continue

        if key == "type":
            result["type"] = value
        elif key == "properties":
            result["properties"] = {}
            for prop_name, prop_schema in value.items():
                result["properties"][prop_name] = convert_node(prop_schema, defs, visited)
        elif key == "items":
            result["items"] = convert_node(value, defs, visited)
        elif key == "additionalProperties":
            result["additionalProperties"] = value
        elif key == "required":
            result["required"] = value
        elif key == "enum":
            result["enum"] = value
        elif key == "anyOf":
            result["anyOf"] = [convert_node(v, defs, visited) for v in value]
        elif key == "oneOf":
            result["anyOf"] = [convert_node(v, defs, visited) for v in value]
        elif key == "allOf":
            # Merge allOf into single object
            merged = {}
            for sub in value:
                converted = convert_node(sub, defs, visited)
                for k, v in converted.items():
                    if k == "properties" and "properties" in merged:
                        merged["properties"].update(v)
                    elif k == "required" and "required" in merged:
                        merged["required"] = list(set(merged["required"] + v))
                    else:
                        merged[k] = v
            return merged
        else:
            result[key] = value

    # Ensure objects have additionalProperties: false and all props in required
    if result.get("type") == "object" and "properties" in result:
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}).keys())

    return result


def main():
    schema = load_schema()
    defs = schema.get("$defs", {})

    # Pre-convert all defs (handle nested refs within defs)
    converted_defs = {}
    for name, definition in defs.items():
        converted_defs[name] = convert_node(definition, defs)

    # Now convert the full schema using converted defs
    strict = convert_node(schema, converted_defs)

    # Remove top-level metadata
    for key in list(strict.keys()):
        if key in UNSUPPORTED_KEYS or key == "$defs":
            del strict[key]

    output = Path("schema_strict.json")
    output.write_text(json.dumps(strict, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written to {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
