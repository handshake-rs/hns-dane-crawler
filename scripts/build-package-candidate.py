#!/usr/bin/env python3
"""Build and inspect the exact Python source and wheel release candidates."""

from __future__ import annotations

import argparse
import base64
import configparser
import csv
import hashlib
import io
import json
import os
import platform
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from contextlib import contextmanager
from email.parser import BytesParser
from email.policy import compat32
from importlib.metadata import version as distribution_version
from pathlib import Path, PurePosixPath

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from setuptools import build_meta

ROOT = Path(__file__).resolve().parents[1]
PROJECT_FILE = ROOT / "pyproject.toml"
LOCK_FILE = ROOT / "requirements-dev.lock"
PACKAGE_ROOT = ROOT / "src" / "hns_topology"
REPOSITORY = "https://github.com/handshake-rs/hns-dane-crawler"
EXPECTED_DISTRIBUTION = "denuo-hns-topology"
EXPECTED_VERSION = "0.1.0"
EXPECTED_REF = "refs/heads/main"
EXPECTED_ROOT_FILES = (
    "CHANGELOG.md",
    "LICENSE",
    "MANIFEST.in",
    "README.md",
    "pyproject.toml",
)
GENERATED_SDIST_FILES = (
    "PKG-INFO",
    "setup.cfg",
    "src/denuo_hns_topology.egg-info/PKG-INFO",
    "src/denuo_hns_topology.egg-info/SOURCES.txt",
    "src/denuo_hns_topology.egg-info/dependency_links.txt",
    "src/denuo_hns_topology.egg-info/entry_points.txt",
    "src/denuo_hns_topology.egg-info/requires.txt",
    "src/denuo_hns_topology.egg-info/top_level.txt",
)
BANNED_SDIST_PREFIXES = (
    ".github/",
    "archives/",
    "configs/",
    "data/",
    "deploy/",
    "docs/",
    "logs/",
    "public/",
    "scripts/",
    "tests/",
)


class CandidateError(RuntimeError):
    """Release candidate validation failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateError(message)


def git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def project_configuration() -> dict:
    return tomllib.loads(PROJECT_FILE.read_text(encoding="utf-8"))["project"]


def locked_tool_version(distribution: str) -> str:
    prefix = f"{distribution}==".lower()
    matches = [
        line.strip().split("==", 1)[1]
        for line in LOCK_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip().lower().startswith(prefix)
    ]
    require(len(matches) == 1, f"lockfile must pin exactly one {distribution} version")
    return matches[0]


def validate_build_environment() -> None:
    for distribution in ("packaging", "setuptools", "wheel"):
        actual = distribution_version(distribution)
        expected = locked_tool_version(distribution)
        require(actual == expected, f"{distribution} {actual} differs from lockfile {expected}")


def expected_requirements(project: dict) -> set[Requirement]:
    requirements = {Requirement(value) for value in project.get("dependencies", [])}
    for extra, values in project.get("optional-dependencies", {}).items():
        requirements.update(Requirement(f'{value}; extra == "{extra}"') for value in values)
    return requirements


def validate_metadata(data: bytes, project: dict, location: str) -> None:
    metadata = BytesParser(policy=compat32).parsebytes(data)
    require(
        canonicalize_name(metadata.get("Name", ""))
        == canonicalize_name(EXPECTED_DISTRIBUTION),
        f"{location}: distribution name differs",
    )
    require(metadata.get("Version") == EXPECTED_VERSION, f"{location}: version differs")
    require(
        metadata.get("Summary") == project["description"],
        f"{location}: summary differs",
    )
    require(
        metadata.get("Author") == project["authors"][0]["name"],
        f"{location}: author differs",
    )
    require(
        metadata.get("Requires-Python") == project["requires-python"],
        f"{location}: Python requirement differs",
    )
    require(metadata.get("License") == "MIT", f"{location}: license differs")
    require(
        metadata.get("Description-Content-Type") == "text/markdown",
        f"{location}: README content type differs",
    )
    require(
        metadata.get_all("Classifier", []) == project.get("classifiers", []),
        f"{location}: classifiers differ",
    )
    require(
        metadata.get_all("License-File", []) == ["LICENSE"],
        f"{location}: license-file metadata differs",
    )
    actual_requirements = {
        Requirement(value) for value in metadata.get_all("Requires-Dist", [])
    }
    require(
        actual_requirements == expected_requirements(project),
        f"{location}: dependency metadata differs",
    )
    require(
        set(metadata.get_all("Provides-Extra", []))
        == set(project.get("optional-dependencies", {})),
        f"{location}: optional dependency metadata differs",
    )
    project_urls: dict[str, str] = {}
    for value in metadata.get_all("Project-URL", []):
        label, separator, url = value.partition(",")
        require(bool(separator), f"{location}: malformed Project-URL")
        project_urls[label.strip()] = url.strip()
    require(project_urls == project.get("urls", {}), f"{location}: project URLs differ")
    description = metadata.get_payload()
    require(
        isinstance(description, str)
        and description.rstrip() == (ROOT / "README.md").read_text(encoding="utf-8").rstrip(),
        f"{location}: packaged README differs",
    )


def validate_archive_name(name: str, location: str) -> PurePosixPath:
    require("\\" not in name, f"{location}: archive member uses a backslash: {name}")
    path = PurePosixPath(name)
    require(not path.is_absolute(), f"{location}: archive member is absolute: {name}")
    require(".." not in path.parts, f"{location}: archive member escapes root: {name}")
    require(bool(path.parts), f"{location}: archive member has an empty name")
    return path


def tracked_package_payload() -> dict[str, bytes]:
    output = subprocess.run(
        ["git", "ls-files", "-z", "--", "src/hns_topology"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    payload: dict[str, bytes] = {}
    for raw_path in output.split(b"\0"):
        if not raw_path:
            continue
        source_path = ROOT / os.fsdecode(raw_path)
        require(source_path.is_file(), f"tracked package file is missing: {source_path}")
        relative = source_path.relative_to(PACKAGE_ROOT).as_posix()
        payload[f"hns_topology/{relative}"] = source_path.read_bytes()
    require(bool(payload), "no tracked hns_topology package files found")
    return payload


def validate_sdist(path: Path, project: dict, package_payload: dict[str, bytes]) -> Path:
    expected_slug = canonicalize_name(EXPECTED_DISTRIBUTION).replace("-", "_")
    expected_filename = f"{expected_slug}-{EXPECTED_VERSION}.tar.gz"
    require(path.name == expected_filename, f"unexpected sdist filename: {path.name}")
    expected_root = f"{expected_slug}-{EXPECTED_VERSION}"
    file_data: dict[str, bytes] = {}

    with tarfile.open(path, mode="r:gz") as archive:
        names: set[str] = set()
        for member in archive.getmembers():
            validate_archive_name(member.name, path.name)
            require(member.name not in names, f"{path.name}: duplicate member {member.name}")
            names.add(member.name)
            require(
                member.isdir() or member.isfile(),
                f"{path.name}: links and special files are forbidden: {member.name}",
            )
            if member.isfile():
                extracted = archive.extractfile(member)
                require(extracted is not None, f"{path.name}: cannot read {member.name}")
                file_data[member.name] = extracted.read()

    prefix = f"{expected_root}/"
    require(file_data, f"{path.name}: source archive is empty")
    require(
        all(name.startswith(prefix) for name in file_data),
        f"{path.name}: files do not share the expected source root",
    )
    relative_files = {name.removeprefix(prefix): data for name, data in file_data.items()}
    for banned in BANNED_SDIST_PREFIXES:
        require(
            not any(name.startswith(banned) for name in relative_files),
            f"{path.name}: operational tree {banned} must not enter the source package",
        )

    for relative in EXPECTED_ROOT_FILES:
        require(relative in relative_files, f"{path.name}: missing {relative}")
        require(
            relative_files[relative] == (ROOT / relative).read_bytes(),
            f"{path.name}: {relative} differs from the exact source",
        )

    expected_package_names = {f"src/{name}" for name in package_payload}
    actual_package_names = {
        name for name in relative_files if name.startswith("src/hns_topology/")
    }
    require(
        actual_package_names == expected_package_names,
        f"{path.name}: package source inventory differs",
    )
    for wheel_name, expected_data in package_payload.items():
        source_name = f"src/{wheel_name}"
        require(
            relative_files[source_name] == expected_data,
            f"{path.name}: {source_name} differs from the exact source",
        )

    allowed = (
        set(EXPECTED_ROOT_FILES)
        | set(GENERATED_SDIST_FILES)
        | expected_package_names
    )
    unexpected = set(relative_files) - allowed
    require(not unexpected, f"{path.name}: unexpected files: {sorted(unexpected)}")
    missing_generated = set(GENERATED_SDIST_FILES) - set(relative_files)
    require(
        not missing_generated,
        f"{path.name}: missing generated metadata: {sorted(missing_generated)}",
    )
    validate_metadata(relative_files["PKG-INFO"], project, f"{path.name}/PKG-INFO")
    validate_metadata(
        relative_files["src/denuo_hns_topology.egg-info/PKG-INFO"],
        project,
        f"{path.name}/src/denuo_hns_topology.egg-info/PKG-INFO",
    )
    return PurePosixPath(expected_root)


def expected_entry_points(project: dict) -> dict[str, str]:
    return dict(project.get("scripts", {}))


def validate_record(
    members: dict[str, bytes],
    record_name: str,
    wheel_name: str,
) -> None:
    rows = list(csv.reader(io.StringIO(members[record_name].decode("utf-8"))))
    require(all(len(row) == 3 for row in rows), f"{wheel_name}: malformed RECORD row")
    records = {row[0]: (row[1], row[2]) for row in rows}
    require(len(records) == len(rows), f"{wheel_name}: duplicate RECORD path")
    require(set(records) == set(members), f"{wheel_name}: RECORD inventory differs")
    for name, data in members.items():
        digest, size = records[name]
        if name == record_name:
            require(not digest and not size, f"{wheel_name}: RECORD must not hash itself")
            continue
        encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        require(digest == f"sha256={encoded}", f"{wheel_name}: bad RECORD hash for {name}")
        require(size == str(len(data)), f"{wheel_name}: bad RECORD size for {name}")


def validate_wheel(path: Path, project: dict, package_payload: dict[str, bytes]) -> None:
    expected_slug = canonicalize_name(EXPECTED_DISTRIBUTION).replace("-", "_")
    expected_filename = f"{expected_slug}-{EXPECTED_VERSION}-py3-none-any.whl"
    require(path.name == expected_filename, f"unexpected wheel filename: {path.name}")
    dist_info = f"{expected_slug}-{EXPECTED_VERSION}.dist-info"

    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        require(len(names) == len(set(names)), f"{path.name}: duplicate archive member")
        members: dict[str, bytes] = {}
        for info in infos:
            validate_archive_name(info.filename, path.name)
            require(not info.is_dir(), f"{path.name}: directory member is unnecessary")
            require(not info.flag_bits & 0x1, f"{path.name}: encrypted member is forbidden")
            mode = (info.external_attr >> 16) & 0xFFFF
            require(not stat.S_ISLNK(mode), f"{path.name}: symlink member is forbidden")
            members[info.filename] = archive.read(info)

        actual_package_names = {name for name in members if name.startswith("hns_topology/")}
        require(
            actual_package_names == set(package_payload),
            f"{path.name}: installed package inventory differs",
        )
        for name, expected_data in package_payload.items():
            require(members[name] == expected_data, f"{path.name}: {name} differs from source")

        metadata_name = f"{dist_info}/METADATA"
        wheel_metadata_name = f"{dist_info}/WHEEL"
        entry_points_name = f"{dist_info}/entry_points.txt"
        record_name = f"{dist_info}/RECORD"
        top_level_name = f"{dist_info}/top_level.txt"
        license_name = f"{dist_info}/licenses/LICENSE"
        expected_dist_info = {
            metadata_name,
            wheel_metadata_name,
            entry_points_name,
            record_name,
            top_level_name,
            license_name,
        }
        actual_dist_info = {name for name in members if name.startswith(f"{dist_info}/")}
        require(
            actual_dist_info == expected_dist_info,
            f"{path.name}: wheel metadata inventory differs",
        )
        require(
            set(members) == set(package_payload) | expected_dist_info,
            f"{path.name}: unexpected top-level wheel content",
        )
        require(members[license_name] == (ROOT / "LICENSE").read_bytes(), "wheel license differs")
        require(members[top_level_name] == b"hns_topology\n", "wheel top-level metadata differs")
        validate_metadata(members[metadata_name], project, metadata_name)

        wheel_metadata = BytesParser(policy=compat32).parsebytes(members[wheel_metadata_name])
        require(wheel_metadata.get("Wheel-Version") == "1.0", "wheel version differs")
        require(wheel_metadata.get("Root-Is-Purelib") == "true", "wheel is not pure Python")
        require(wheel_metadata.get_all("Tag", []) == ["py3-none-any"], "wheel tag differs")

        entry_points = configparser.ConfigParser(interpolation=None)
        entry_points.optionxform = str
        entry_points.read_string(members[entry_points_name].decode("utf-8"))
        require(entry_points.sections() == ["console_scripts"], "wheel entry-point groups differ")
        require(
            dict(entry_points["console_scripts"]) == expected_entry_points(project),
            "wheel console entry points differ",
        )
        validate_record(members, record_name, path.name)


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def extract_sdist(path: Path, destination: Path, root: PurePosixPath) -> Path:
    with tarfile.open(path, mode="r:gz") as archive:
        for member in archive.getmembers():
            validate_archive_name(member.name, path.name)
            require(
                member.isdir() or member.isfile(),
                f"{path.name}: refusing to extract special member {member.name}",
            )
        archive.extractall(destination)
    extracted = destination / Path(*root.parts)
    require(extracted.is_dir(), f"{path.name}: extracted source root is missing")
    return extracted


def build_candidates(output_dir: Path, commit: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    require(not any(output_dir.iterdir()), f"output directory is not empty: {output_dir}")
    source_epoch = git("show", "-s", "--format=%ct", commit)
    require(source_epoch.isdigit(), "Git commit timestamp is invalid")
    os.environ["SOURCE_DATE_EPOCH"] = source_epoch

    sdist_filename = build_meta.build_sdist(str(output_dir))
    sdist_path = output_dir / sdist_filename
    require(sdist_path.is_file(), "setuptools did not create the source distribution")
    project = project_configuration()
    package_payload = tracked_package_payload()
    source_root = validate_sdist(sdist_path, project, package_payload)

    with tempfile.TemporaryDirectory(prefix="hns-crawler-sdist-") as temporary:
        extracted = extract_sdist(sdist_path, Path(temporary), source_root)
        with working_directory(extracted):
            wheel_filename = build_meta.build_wheel(str(output_dir))
    wheel_path = output_dir / wheel_filename
    require(wheel_path.is_file(), "setuptools did not create the wheel")
    validate_wheel(wheel_path, project, package_payload)
    return sdist_path, wheel_path


def write_provenance(
    output_dir: Path,
    artifacts: tuple[Path, Path],
    commit: str,
    source_ref: str,
) -> None:
    artifact_records = [
        {
            "filename": path.name,
            "sha256": sha256(path.read_bytes()),
            "size": path.stat().st_size,
        }
        for path in sorted(artifacts)
    ]
    sums = "".join(
        f"{record['sha256']}  {record['filename']}\n" for record in artifact_records
    )
    (output_dir / "SHA256SUMS").write_text(sums, encoding="utf-8")

    actions = {
        key.removeprefix("GITHUB_").lower(): os.environ[key]
        for key in (
            "GITHUB_REPOSITORY",
            "GITHUB_RUN_ATTEMPT",
            "GITHUB_RUN_ID",
            "GITHUB_WORKFLOW_REF",
        )
        if os.environ.get(key)
    }
    provenance = {
        "schema_version": 1,
        "candidate": {
            "distribution": EXPECTED_DISTRIBUTION,
            "import_package": "hns_topology",
            "version": EXPECTED_VERSION,
        },
        "source": {
            "commit": commit,
            "commit_time": git("show", "-s", "--format=%cI", commit),
            "ref": source_ref,
            "repository": REPOSITORY,
            "tree": git("rev-parse", f"{commit}^{{tree}}"),
        },
        "build": {
            "backend": "setuptools.build_meta",
            "packaging_version": distribution_version("packaging"),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "setuptools_version": distribution_version("setuptools"),
            "source_date_epoch": os.environ["SOURCE_DATE_EPOCH"],
            "wheel_version": distribution_version("wheel"),
        },
        "artifacts": artifact_records,
    }
    if actions:
        provenance["github_actions"] = actions
    (output_dir / "PROVENANCE.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-ref", default=EXPECTED_REF)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require(
        re.fullmatch(r"[0-9a-f]{40}", args.expected_commit) is not None,
        "expected commit must be one lowercase 40-character Git commit",
    )
    require(args.expected_ref == EXPECTED_REF, f"release ref must be {EXPECTED_REF}")
    require(git("rev-parse", "HEAD") == args.expected_commit, "HEAD differs from expected commit")
    require(not git("status", "--porcelain", "--untracked-files=all"), "source tree is not clean")
    project = project_configuration()
    require(project.get("name") == EXPECTED_DISTRIBUTION, "distribution identity differs")
    require(project.get("version") == EXPECTED_VERSION, "candidate version differs")
    validate_build_environment()

    artifacts = build_candidates(args.output_dir.resolve(), args.expected_commit)
    require(not git("diff", "--name-only", "HEAD"), "package build changed tracked source")
    write_provenance(
        args.output_dir.resolve(), artifacts, args.expected_commit, args.expected_ref
    )
    expected_outputs = {
        artifacts[0].name,
        artifacts[1].name,
        "PROVENANCE.json",
        "SHA256SUMS",
    }
    actual_outputs = {path.name for path in args.output_dir.iterdir()}
    require(actual_outputs == expected_outputs, "candidate output inventory differs")
    print(
        f"package candidate valid: {EXPECTED_DISTRIBUTION} {EXPECTED_VERSION} "
        f"at {args.expected_commit}; sdist, wheel, hashes, and provenance recorded"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        CandidateError,
        KeyError,
        OSError,
        ValueError,
        configparser.Error,
        subprocess.SubprocessError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as error:
        print(f"package candidate check: {error}", file=sys.stderr)
        raise SystemExit(1) from error
