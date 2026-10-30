"""Load the JSON Schemas in schema/ into a registry so cross-file $refs resolve."""

import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from scg.paths import SCHEMA_DIR


@cache
def registry(schema_dir: Path = SCHEMA_DIR) -> Registry:
    resources = []
    for path in sorted(schema_dir.glob("*.schema.json")):
        contents = json.loads(path.read_text())
        resources.append((contents["$id"], Resource.from_contents(contents)))
    return Registry().with_resources(resources)


@cache
def validator(name: str, schema_dir: Path = SCHEMA_DIR) -> Draft202012Validator:
    """Validator for urn:scg:<name>, e.g. validator("edge")."""
    reg = registry(schema_dir)
    schema = reg.contents(f"urn:scg:{name}")
    return Draft202012Validator(schema, registry=reg, format_checker=FormatChecker())
