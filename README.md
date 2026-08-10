# HNS DANE Crawler

Static topology and DANE-readiness snapshots for the current Handshake namespace.

HNS DANE Crawler builds a compact SQLite database from HSD-derived root state, classifies current on-chain resource summaries, combines them with imported delegated-DNS evidence, derives compliance stages, and publishes a paginated static report. The topology build does not run website liveness checks. A separate `hns-live-directory` service can consume the published snapshot on the web VM without extending the HSD build or deploy cycle.

## Ecosystem Role and Output Boundaries

This repository is the crawler and reporting package in the `handshake-rs`
ecosystem. It produces topology snapshots, DANE-readiness queues, static report
artifacts, stored DNS evidence summaries, and the optional live-directory
output. Those artifacts describe observed or indexed state; they are not an
authoritative namespace classifier and do not make browser trust decisions.

Browser clients and the shared DANE engine resolve and validate the hostname
for each request independently. They do not depend on this crawler being
available at runtime. This package likewise does not operate a Handshake node or
wallet, publish authoritative DNS data, provision certificates, or enforce TLS
policy in a browser. It does not implement HNSA or HNSR service roles, expose
wallet or value-transfer controls, or provide a settlement or P2P marketplace.

The canonical source repository is
[`handshake-rs/hns-dane-crawler`](https://github.com/handshake-rs/hns-dane-crawler).
The organization migration does not change Denuo's package authorship,
copyright, production deployment, publishing, or release-signing identity.

## Package and Release Identity

The repository name, Python distribution name, import package, and installed
commands are intentionally different compatibility identifiers:

| Surface | Identifier |
| --- | --- |
| Source repository | `handshake-rs/hns-dane-crawler` |
| Python distribution | `denuo-hns-topology` |
| Python import package | `hns_topology` |
| Console commands | `hns-topology`, `hns-live-directory` |
| Source candidate version | `0.1.0` |

At this revision, `0.1.0` is an unpublished source candidate: the repository
has no version tag or GitHub Release and the distribution has not been
published to PyPI. Production topology snapshots and website deployments are
data releases with their own manifest provenance; they are not Python package
releases and do not imply that the source candidate was published.

The declared Python contract is Python 3.11 or newer. CI qualifies CPython 3.11
on Ubuntu 24.04. The production wrappers additionally assume Bash, Linux,
systemd, HSD, and the documented GCE environment; other Python/platform
combinations are not currently release-qualified. See
[`docs/PACKAGE_RELEASE.md`](docs/PACKAGE_RELEASE.md) for the package preflight
and [`docs/PRODUCTION_RELEASE.md`](docs/PRODUCTION_RELEASE.md) for the separate
topology-data release gate.

The current analysis answers:

- Which active names publish SYNTH or delegated nameserver bootstrap material?
- Which delegated names have no direct GLUE, and which instead have an indexed HNS nameserver handoff?
- Which active names publish DS records?
- Which roots have an authoritative or authenticated HTTPS TLSA answer in stored DNS evidence?
- Which DS names still lack stored TLSA proof and need verification before generator handoff?
- Which names are parked/default/resolver infrastructure and should stay out of action queues?

## Compliance Stages

- `tlsa_present`: parent DS is present and stored delegated-DNS evidence contains an authoritative or authenticated HTTPS TLSA answer.
- `tlsa_gap`: parent DS is present, but stored DNS evidence does not prove TLSA presence.
- `indirect_ns_handoff`: direct GLUE is absent, but an active HNS root can bootstrap a delegated nameserver host; the handoff still needs authority verification.
- `missing_glue`: delegation has neither direct GLUE nor an indexed HNS nameserver handoff.
- `bootstrap_ready`: SYNTH or delegated GLUE bootstrap exists; the next step is DNSSEC, DS, and TLSA.
- `non_actionable`: expired, parked/default, resolver infrastructure, empty, or unsupported resources.

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --requirement requirements-dev.lock
python -m pip install --no-build-isolation --no-deps --editable .
python -m pip check

hns-topology bootstrap-fixture --fixture tests/fixtures/sample_hsd_names.json --db data/topology.sqlite
hns-topology generate-site --db data/topology.sqlite --out public
hns-topology validate-release --db data/topology.sqlite --public-dir public
```

Open `public/index.html` or serve `public/` with any static web server.

## HSD Indexing

Bootstrap from HSD RPC:

```bash
hns-topology bootstrap --db data/topology.sqlite --rules configs/provider_rules.json
```

Incremental updates:

```bash
hns-topology incremental --db data/topology.sqlite --scan-block-height 337000
hns-topology reorg-check --db data/topology.sqlite --rollback
```

JSONL bootstrap:

```bash
hns-topology bootstrap-jsonl --jsonl data/names.jsonl --db data/topology.sqlite --rules configs/provider_rules.json
```

Provider-rule changes can be applied without rerunning HSD extraction:

```bash
hns-topology reclassify --db data/topology.sqlite --rules configs/provider_rules.json
```

## Evidence Imports

DNS observations remain supported as static evidence sidecars:

```bash
hns-topology import-dns-evidence --db data/topology.sqlite --file dns-evidence.json --source crowd --source-id worker-1
```

Imported DNS observations are exported under `data/dns-evidence/<name>.json` and linked from matching name rows.

TLSA is not part of Handshake's on-chain Resource format. HTTPS TLSA presence is therefore derived only from the latest stored observation per query/server/source identity. A qualifying record must be an exact `_443._tcp.<host>` answer below the indexed root and carry authoritative (`AA`) or authenticated-data (`AD`) evidence. The headline is labeled **TLSA observed** because imports are not an exhaustive live scan; `tlsa_evidence_names` in `summary.json` reports the number of roots with stored TLSA probes.

## Live Website Directory

The independent live scanner has its own database, CLI, static output, runner, and web-VM timer. Its detailed evidence queue checks apex hosts and DNS-evidenced subdomains, while a separate cursor-based broad sweep covers DS and delegated roots without materializing millions of candidates. It separates authenticated HTTPS endpoints from HTTP-only endpoints. See `docs/LIVE_DIRECTORY.md`.

## Published Artifacts

Default production artifacts:

- `index.html`
- `names.html`
- `styles.css`
- `app.js`
- `generator_handoff.js`
- `data/summary.json`
- `data/manifest.json`
- `data/overview-pages.json`
- `data/overview-pages/**`
- `data/names-pages.json`
- `data/names-pages/**`
- `data/hns-handoff-groups.json`
- `data/ip-addresses/**`
- `data/nameservers/index.json`
- `data/nameservers/shards/**`
- `data/dns-evidence/**` when imported DNS evidence exists

Optional downloads with `--include-downloads`:

- `data/names.json`
- `data/names.csv`
- `data/verification.csv`
- `data/topology.sqlite.gz`

## Performance Model

Indexing is O(N) in exported names plus resource records. Export uses one canonical sorted row store and compact posting lists for filters, so publishing is O(E + P + I), where `E` is exported names, `P` is nonzero posting entries, and `I` is resource-IP index rows. The static site only fetches the current page and selected posting list, avoiding full-snapshot browser loads.

## Development

```bash
make test
make lint
make package-check
make fixture-site
```

Production wrappers live under `scripts/`. They start HSD only for update phases, generate the static site, validate the release, optionally archive, and publish generated `public/` artifacts.

## Documentation

- [Architecture and runtime boundaries](docs/ARCHITECTURE.md)
- [Data model and public artifacts](docs/DATA_MODEL.md)
- [Package release preflight](docs/PACKAGE_RELEASE.md)
- [Production topology-data release](docs/PRODUCTION_RELEASE.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Standalone live directory](docs/LIVE_DIRECTORY.md)
