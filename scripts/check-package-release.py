#!/usr/bin/env python3
"""Validate the stable identity and version of the Python release candidate."""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
PROJECT_FILE = ROOT / "pyproject.toml"
INIT_FILE = ROOT / "src" / "hns_topology" / "__init__.py"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"


def _import_version() -> str:
    tree = ast.parse(INIT_FILE.read_text(encoding="utf-8"), filename=str(INIT_FILE))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "__version__" for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    raise ValueError(f"{INIT_FILE.relative_to(ROOT)} must define a literal __version__")


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    root_config = tomllib.loads(PROJECT_FILE.read_text(encoding="utf-8"))
    project = root_config["project"]
    project_version = str(project.get("version", ""))
    import_version = _import_version()
    errors: list[str] = []

    try:
        parsed_version = Version(project_version)
        _require(str(parsed_version) == project_version, "project version must be normalized", errors)
    except InvalidVersion:
        errors.append(f"invalid project version: {project_version!r}")

    _require(project_version == import_version, "project and import versions differ", errors)
    _require(
        project.get("name") == "denuo-hns-topology",
        "distribution identity changed",
        errors,
    )
    _require(
        project.get("requires-python") == ">=3.11",
        "Python compatibility contract changed",
        errors,
    )
    _require(project.get("readme") == "README.md", "README package metadata changed", errors)
    _require(project.get("license") == {"text": "MIT"}, "MIT license metadata changed", errors)

    scripts = project.get("scripts", {})
    _require(
        scripts.get("hns-topology") == "hns_topology.cli:main",
        "hns-topology entry point changed",
        errors,
    )
    _require(
        scripts.get("hns-live-directory") == "hns_topology.live_cli:main",
        "hns-live-directory entry point changed",
        errors,
    )

    urls = project.get("urls", {})
    canonical = "https://github.com/handshake-rs/hns-dane-crawler"
    _require(urls.get("Homepage") == canonical, "canonical homepage changed", errors)
    _require(urls.get("Repository") == f"{canonical}.git", "canonical repository changed", errors)

    package_data = root_config.get("tool", {}).get("setuptools", {}).get("package-data", {})
    _require(
        package_data.get("hns_topology") == ["site_assets/*", "live_site_assets/*"],
        "static package-data contract changed",
        errors,
    )
    _require((ROOT / "LICENSE").is_file(), "LICENSE is missing", errors)
    _require((ROOT / "README.md").is_file(), "README.md is missing", errors)
    changelog = CHANGELOG_FILE.read_text(encoding="utf-8")
    _require(
        f"## {project_version} " in changelog,
        "candidate version is missing from CHANGELOG.md",
        errors,
    )

    if errors:
        for error in errors:
            print(f"package release check: {error}", file=sys.stderr)
        return 1

    print(
        "package release check: "
        f"denuo-hns-topology {project_version}; import hns_topology {import_version}; "
        "metadata and compatibility identifiers match"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
