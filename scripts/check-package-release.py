#!/usr/bin/env python3
"""Validate the stable identity and version of the Python release candidate."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
PROJECT_FILE = ROOT / "pyproject.toml"
INIT_FILE = ROOT / "src" / "hns_topology" / "__init__.py"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"
MANIFEST_FILE = ROOT / "MANIFEST.in"
PREFLIGHT_FILE = ROOT / ".github" / "workflows" / "package-release-preflight.yml"
EXPECTED_VERSION = "0.1.0"


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
    _require(project_version == EXPECTED_VERSION, "first candidate version changed", errors)
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
    _require(MANIFEST_FILE.is_file(), "MANIFEST.in is missing", errors)
    _require(
        (ROOT / "scripts" / "build-package-candidate.py").is_file(),
        "package candidate builder is missing",
        errors,
    )
    manifest = MANIFEST_FILE.read_text(encoding="utf-8") if MANIFEST_FILE.is_file() else ""
    for required in (
        "include CHANGELOG.md",
        "include LICENSE",
        "include README.md",
        "include pyproject.toml",
        "prune tests",
    ):
        _require(required in manifest, f"MANIFEST.in omits {required!r}", errors)
    changelog = CHANGELOG_FILE.read_text(encoding="utf-8")
    _require(
        f"## {project_version} " in changelog,
        "candidate version is missing from CHANGELOG.md",
        errors,
    )

    if PREFLIGHT_FILE.is_file():
        preflight = PREFLIGHT_FILE.read_text(encoding="utf-8")
        _require(
            re.search(r"^on:\n  workflow_dispatch:\s*$", preflight, re.MULTILINE) is not None,
            "package preflight must be manually dispatchable",
            errors,
        )
        for automatic_event in ("push", "pull_request", "schedule"):
            _require(
                re.search(rf"^  {automatic_event}:\s*", preflight, re.MULTILINE) is None,
                f"package preflight must not run on {automatic_event}",
                errors,
            )
        required_preflight_text = (
            "expected_commit:",
            "permissions:\n  contents: read",
            "persist-credentials: false",
            "test \"$GITHUB_REF\" = \"refs/heads/main\"",
            "test \"$GITHUB_SHA\" = \"$EXPECTED_COMMIT\"",
            "python scripts/build-package-candidate.py",
            f"name: denuo-hns-topology-{EXPECTED_VERSION}-${{{{ inputs.expected_commit }}}}",
            "retention-days: 7",
            "compression-level: 0",
        )
        for required in required_preflight_text:
            _require(required in preflight, f"package preflight omits {required!r}", errors)
        _require(
            preflight.count("actions/upload-artifact@") == 1,
            "package preflight must upload exactly one candidate artifact",
            errors,
        )
        _require(
            re.findall(r"^\s+retention-days:\s*(\d+)\s*$", preflight, re.MULTILINE)
            == ["7"],
            "package preflight must use one seven-day retention setting",
            errors,
        )
        for forbidden in (
            "contents: write",
            "id-token: write",
            "packages: write",
            "secrets.",
            "gcloud-",
            "publish-site",
            "TOPOLOGY_DB",
            "public/",
        ):
            _require(
                forbidden not in preflight,
                f"package preflight crosses the package-only boundary with {forbidden!r}",
                errors,
            )
    else:
        errors.append("package release preflight workflow is missing")

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
