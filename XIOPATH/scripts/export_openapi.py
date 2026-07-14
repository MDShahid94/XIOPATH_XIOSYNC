#!/usr/bin/env python3
"""
XIOPATH — OpenAPI Spec Export
==============================
Generates the OpenAPI 3.1 JSON spec from the FastAPI app without starting the server.
Usage: python3 scripts/export_openapi.py [output_path]
"""
import json
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Patch heavy dependencies so we don't need them for spec generation
import types

# Stub out imports that require browser/LLM/DB at import time
for mod_name in [
    'playwright', 'playwright.async_api', 'chromadb',
    'google.generativeai', 'google.genai',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else "docs/openapi.json"

    # Import the app to generate the schema
    try:
        from api.main import app
        schema = app.openapi()
    except Exception as e:
        print(f"⚠️  Could not generate full spec: {e}")
        print("Generating minimal spec from metadata...")
        schema = {
            "openapi": "3.1.0",
            "info": {
                "title": "XIOPATH API",
                "version": "5.0.0",
                "description": "Universal Action Intelligence Platform",
            },
            "paths": {},
        }

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2, default=str)

    # Stats
    paths = schema.get("paths", {})
    total_endpoints = sum(len(methods) for methods in paths.values())
    tags = set()
    for path_methods in paths.values():
        for method_info in path_methods.values():
            if isinstance(method_info, dict):
                for tag in method_info.get("tags", []):
                    tags.add(tag)

    print(f"✅ OpenAPI spec exported to: {output_path}")
    print(f"   Version: {schema['info']['version']}")
    print(f"   Paths: {len(paths)}")
    print(f"   Endpoints: {total_endpoints}")
    print(f"   Tags: {len(tags)} ({', '.join(sorted(tags))})")
    print(f"   Size: {os.path.getsize(output_path) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
