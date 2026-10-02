# Bootstrap performance

The production bootstrap should read HSD's name tree directly, not JSON-RPC.

Relevant HSD structures:

- `ChainDB` owns an Urkel `Tree` and exposes the current transaction as `chain.db.txn`.
- `getnames` iterates `txn.iterator()`, decodes every `NameState`, calls `ns.getJSON(height, network)`, appends each object to an array, then returns the full array through RPC.
- `NameState` stores the name, renewal height, serialized resource data, owner/value fields, and status fields. For this report we only need name, name hash, state, renewal, current expiration, and resource data.
- `Resource.decode(ns.data)` exposes only the records this report summarizes: `DS`, `NS`, `GLUE4`, `GLUE6`, `SYNTH4`, `SYNTH6`, and `TXT`.

The fast path is:

1. Stop `hsd` so the datadir is stable.
2. Run `scripts/export-hsd-jsonl.sh` with `EXPORT_FORMAT=compact`.
3. The Node exporter iterates `chain.db.txn` and writes one `compact_name` JSONL row per `NameState`.
4. Python `bootstrap-jsonl` batches compact rows into SQLite with precomputed resource summaries.

This avoids:

- HSD's unpaginated `getnames` RPC array.
- full `NameState.getJSON()` output for fields the site never uses.
- Python decoding and summarizing every resource from full JSON.
- repeated regex/CIDR compilation during provider classification.
- per-name SQLite insert calls.
- per-row dataclass construction on compact imports.
- repeated JSON encoding of empty resource-summary arrays.

Tuning knobs:

- `EXPORT_FORMAT=compact` for production, `full` only for debugging.
- `JSONL_BOOTSTRAP_BATCH_SIZE=5000` by default. Increase on a larger indexer VM if memory is comfortable.
- `EXPORT_LIMIT=<n>` for smoke runs.

Benchmark the exact source with a representative export and record rows per
second, peak memory, database size, and disk I/O. Include empty and populated
resources, and compare the resulting row counts and summaries with the source.

Headers are not enough for this report. Block headers prove chain order and work, but HNS name resources are current state in the name tree. The report needs the current resource bytes to classify NS, GLUE, DS, SYNTH, TXT, DANE candidacy, and provider patterns.

## Full-node synchronization

Stopped-state export requires a synchronized HSD name tree. HSD validates
transactions and updates both UTXOs and names in canonical block order. More
peers can improve download throughput, but they do not parallelize ordered
state transitions. Measure replay, tree I/O, export, import, and site generation
separately before changing resource allocation.

## Experimental name-only export

`scripts/export-hsd-nameonly-jsonl.sh` and
`scripts/hsd-nameonly-replay-jsonl.js` read accepted blocks through local HSD RPC,
apply name-covenant transitions, reuse HSD `NameState` for expiration math, and
write compact JSONL for `bootstrap-jsonl`. The export is explicitly labeled
`hsd_nameonly_rpc_compact_experimental`.

This experiment is not a validating full node. Before using its output for a
production snapshot, compare every resulting name and resource at the same
height with a stopped authoritative HSD tree export. Compare interval roots
where available, reject decode errors, and measure peak memory at mainnet
scale. Keep the authoritative tree export as the production path until the
complete comparison and resource budgets pass.

A full node must keep ordinary UTXO and consensus validation. Any modification
to ordered covenant mutation or authenticated-tree writes requires exact root
and state equality against the pinned HSD implementation.
