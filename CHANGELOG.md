# Changelog

This changelog tracks the Python source package. Generated topology snapshots,
static sites, and archive manifests have independent data-release provenance.

## 0.1.0 (unreleased source candidate)

- Build current Handshake name topology from HSD RPC, compact JSONL, or fixture
  input and publish validated, paginated static artifacts.
- Classify resource bootstrap, delegation, DNSSEC, and stored TLSA evidence into
  explicit DANE-readiness stages.
- Maintain the independent `hns-live-directory` scanner and compact public
  endpoint directory without making it a browser trust dependency.
- Guard production indexing, archive, publish, and cloud lifecycle operations
  with explicit validation and confirmation boundaries.
- Move canonical source to `handshake-rs/hns-dane-crawler` while preserving the
  `denuo-hns-topology`, `hns_topology`, `hns-topology`, and
  `hns-live-directory` compatibility identifiers.

There is no earlier package release or tag to supersede. Keep the candidate at
`0.1.0` until the first package publication is deliberately authorized; record
the release date here only when the exact tagged artifacts are published.
