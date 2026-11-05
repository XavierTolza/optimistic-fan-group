"""Validate the HACS structure of the integration (used by CI)."""

import json
import pathlib
import sys

DOMAIN = "optimistic_fan_group"
ROOT = pathlib.Path("custom_components") / DOMAIN

REQUIRED_MANIFEST_KEYS = (
    "domain",
    "name",
    "codeowners",
    "version",
    "documentation",
    "iot_class",
    "config_flow",
)
REQUIRED_FILES = (
    "__init__.py",
    "fan.py",
    "config_flow.py",
    "const.py",
    "strings.json",
    "translations/fr.json",
)


def main() -> int:
    """Check the repository layout needed by HACS and Home Assistant."""
    errors: list[str] = []

    paths = {"manifest": ROOT / "manifest.json"}
    manifest: dict = {}

    hacs_path = pathlib.Path("hacs.json")
    if not hacs_path.is_file():
        errors.append("missing hacs.json")
    else:
        try:
            json.loads(hacs_path.read_text())
        except ValueError as err:
            errors.append(f"invalid JSON in hacs.json - {err}")

    if not paths["manifest"].is_file():
        errors.append("missing " + str(paths["manifest"]))
    else:
        try:
            manifest = json.loads(paths["manifest"].read_text())
        except ValueError as err:
            errors.append(f"invalid JSON in manifest.json - {err}")

    for key in REQUIRED_MANIFEST_KEYS:
        if key not in manifest:
            errors.append(f"manifest missing '{key}'")
    if manifest.get("domain") != DOMAIN:
        errors.append(f"manifest domain must be '{DOMAIN}'")
    if not manifest.get("version"):
        errors.append("manifest version is required for HACS")

    for name in REQUIRED_FILES:
        if not (ROOT / name).is_file():
            errors.append("missing " + str(ROOT / name))

    if errors:
        print("\n".join(errors))
        return 1

    print("HACS structure OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
