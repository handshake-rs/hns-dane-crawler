# Python Package Release

This document covers the installable Python source package. It is separate from
the topology snapshot, static website, and archive workflow in
[`PRODUCTION_RELEASE.md`](PRODUCTION_RELEASE.md).

## Current Candidate

| Property | Value |
| --- | --- |
| Distribution | `denuo-hns-topology` |
| Import package | `hns_topology` |
| Commands | `hns-topology`, `hns-live-directory` |
| Candidate version | `0.1.0` |
| Python contract | `>=3.11` |
| CI-qualified runtime | CPython 3.11 on Ubuntu 24.04 |
| Publication state | source only; no tag, GitHub Release, or PyPI project |

The distribution name and import/command names predate the repository rename
and remain compatibility identifiers. Do not rename them as documentation
cleanup.

All repository history currently belongs to the first `0.1.0` candidate. With
no prior package tag or publication, a bump to `0.1.1` would imply a released
`0.1.0` that does not exist. Keep `pyproject.toml`,
`src/hns_topology/__init__.py`, and this changelog at `0.1.0` until the release
owner intentionally chooses and authorizes the first published version.

## Compatibility Boundary

The Python code declares Python 3.11 or newer. CI currently proves only CPython
3.11 on Ubuntu 24.04. The topology library and fixture pipeline may work on
other supported Python versions, but they are not release-qualified until CI
covers them. Production scripts additionally depend on Bash/Linux tools,
systemd, HSD, and the documented GCE layout; the wheel does not make those
operator workflows portable to Windows or macOS.

The package produces observational/indexed topology and DANE-readiness data. It
does not operate a Handshake node or wallet, make browser trust decisions,
implement HNSA or HNSR service roles, transfer value, or provide a settlement
or P2P marketplace.

## Source Preflight

Run these inexpensive checks from a clean checkout after installing the locked
development environment:

```bash
python -m pip install --requirement requirements-dev.lock
python -m pip install --no-build-isolation --no-deps --editable .
python -m pip check
python scripts/check-package-release.py
ruff check .
pytest
bash -n scripts/*.sh
node --check scripts/hsd-export-names-jsonl.js
```

The package check fails if the project and import-package versions diverge, if
the version is not represented in the changelog, or if the stable distribution,
entry-point, license, README, package-data, and repository identities drift.

## Wheel Preflight

CI builds a wheel from every pushed commit after the source checks, installs it
into an isolated target, verifies its installed metadata/import version, writes
a SHA-256 sidecar, and retains both files as an exact-commit artifact. The same
cheap check can be reproduced locally without writing into the repository:

```bash
PACKAGE_TMP="$(mktemp -d)"
python -m pip wheel --no-build-isolation --no-deps \
  --wheel-dir "$PACKAGE_TMP/dist" .
python -m pip install --no-deps --target "$PACKAGE_TMP/site" \
  "$PACKAGE_TMP"/dist/*.whl
PYTHONPATH="$PACKAGE_TMP/site" python -c \
  'import hns_topology; print(hns_topology.__version__)'
sha256sum "$PACKAGE_TMP"/dist/*.whl
```

Remove the temporary directory after inspection. A wheel built from a dirty
tree, an unpushed commit, or a failed CI run is not a release artifact.

## Publication Gate

Before the first publication:

1. Confirm the intended public distribution name and PyPI ownership.
2. Confirm the candidate version in both source files and `CHANGELOG.md`.
3. Push the exact source commit to `main` and wait for CI and security checks.
4. Download the exact-commit wheel artifact and verify its SHA-256 sidecar.
5. Build and inspect any additional source distribution required by the chosen
   publishing channel from the same clean commit.
6. Only with explicit release authorization, create the matching version tag,
   publish artifacts, and record the release date and hashes.

CI artifact upload is not publication. Nothing in the package or topology-data
workflows creates a tag, GitHub Release, PyPI release, production deployment, or
cloud resource automatically.
