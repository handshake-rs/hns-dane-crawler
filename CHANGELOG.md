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
- Expose the `denuo-hns-topology` package, `hns_topology` module,
  `hns-topology` CLI, and independent `hns-live-directory` CLI.
- Add a credential-free, manual exact-`main` package preflight that builds the
  0.1.0 source distribution and then its pure-Python wheel, validates archive
  metadata, content, version, entry points, and wheel `RECORD`, and retains only
  the two distributions, SHA-256 sums, and build provenance for seven days.
- Keep deployment scripts, cloud configuration, generated topology/site data,
  production archives, and tests outside the source-distribution inventory;
  package preflight does not run or publish any topology-data release path.


Keep the source candidate at `0.1.0` until publication of the exact qualified
artifacts is authorized.
