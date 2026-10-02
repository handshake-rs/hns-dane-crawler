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
entry-point, license, README, package-data, and repository identities drift. It
also rejects an automatic, credentialed, long-retention, or topology-deployment
package preflight.

## Routine Wheel Evidence

CI builds a wheel from every pushed commit after the source checks, installs it
into an isolated target, verifies its installed metadata/import version, writes
a SHA-256 sidecar, and retains both files as an exact-commit artifact. The same
cheap smoke check can be reproduced locally without writing into the
repository:

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
tree, an unpushed commit, or a failed CI run is not a release artifact. Routine
CI does not build or inspect the source distribution and is not the package
release preflight.

## Exact-Commit Package Preflight

After routine CI and CodeQL pass for a pushed `main` candidate, manually
dispatch the credential-free package workflow with that exact commit:

```bash
gh workflow run package-release-preflight.yml \
  --ref main \
  -f expected_commit="$(git rev-parse HEAD)"
```

The workflow rejects a non-lowercase SHA, a dispatch ref other than `main`, a
requested commit other than the dispatch commit, or a dirty/read-back mismatch.
It installs the checked-in locked environment, runs the source identity check,
builds the source distribution, verifies its bounded package-only inventory,
then builds the pure-Python wheel from that extracted source distribution. It
checks both archives for safe paths, exact version and project metadata,
dependencies, entry points, README, license, and byte-identical tracked package
payloads. The wheel `RECORD` hashes and sizes are independently verified.

One seven-day Actions artifact contains only:

- `denuo_hns_topology-0.1.0.tar.gz`;
- `denuo_hns_topology-0.1.0-py3-none-any.whl`;
- `SHA256SUMS`; and
- `PROVENANCE.json`, binding the repository, commit, tree, `main` ref, build
  environment, artifact sizes, and SHA-256 values.

`MANIFEST.in` keeps tests, deployment scripts, cloud configuration, generated
topology data, static-site output, and production archives out of the source
distribution. The workflow has read-only repository permission, receives no
credential, and invokes no topology indexing, site generation, data release,
cloud, tag, GitHub Release, or PyPI operation. A newly committed preflight is
not qualified until its exact pushed commit completes routine CI, CodeQL, and
this manual workflow successfully.

## Publication Gate

Before the first publication:

1. Confirm the intended public distribution name and PyPI ownership.
2. Confirm the candidate version in both source files and `CHANGELOG.md`.
3. Push the exact source commit to `main` and wait for CI and security checks.
4. Dispatch the exact-commit package preflight and require its success.
5. Download its candidate artifact and verify `SHA256SUMS`, `PROVENANCE.json`,
   the source commit, and both distribution files independently.
6. Only with explicit release authorization, create the matching version tag,
   publish artifacts, and record the release date and hashes.

Actions artifact upload is not publication. Nothing in the package or
topology-data workflows creates a tag, GitHub Release, PyPI release, production
deployment, or cloud resource automatically.
