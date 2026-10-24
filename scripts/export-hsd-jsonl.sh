#!/usr/bin/env bash
set -euo pipefail

INDEXER_MOUNT="${INDEXER_MOUNT:-/mnt/hnscrawler}"
INDEXER_HSD_PREFIX="${INDEXER_HSD_PREFIX:-/mnt/hnscrawler/hsd}"
JSONL_PATH="${JSONL_PATH:-/mnt/hnscrawler/data/extracted_names.jsonl}"
HSD_NETWORK="${HSD_NETWORK:-main}"
CHECK_HSD_READY="${CHECK_HSD_READY:-1}"
EXPORT_LIMIT="${EXPORT_LIMIT:-}"
EXPORT_FORMAT="${EXPORT_FORMAT:-compact}"
STOP_HSD_FOR_EXPORT="${STOP_HSD_FOR_EXPORT:-1}"
RESTART_HSD_AFTER_EXPORT="${RESTART_HSD_AFTER_EXPORT:-0}"
ALLOW_RUNNING_HSD_EXPORT="${ALLOW_RUNNING_HSD_EXPORT:-0}"

if [ -d "$INDEXER_MOUNT" ] && ! mountpoint -q "$INDEXER_MOUNT"; then
  echo "$INDEXER_MOUNT exists but is not mounted; run scripts/setup-indexer-disk.sh first" >&2
  exit 2
fi

if [ "$CHECK_HSD_READY" = "1" ]; then
  scripts/check-hsd-ready.sh
fi

stopped_hsd=0
restart_hsd() {
  if [ "$stopped_hsd" = "1" ] && [ "$RESTART_HSD_AFTER_EXPORT" = "1" ]; then
    sudo systemctl start hsd || true
  fi
}
trap restart_hsd EXIT

if command -v systemctl >/dev/null 2>&1 \
    && [ "$(systemctl show hsd.service --property=LoadState --value 2>/dev/null || true)" = "loaded" ]; then
  hsd_state="$(systemctl show hsd.service --property=ActiveState --value)"
  if [ "$STOP_HSD_FOR_EXPORT" = "1" ]; then
    # Also cancel an auto-restart. is-active is false during that state, but
    # systemd would otherwise race the exporter for the chain database lock.
    sudo systemctl stop hsd
    if [ "$hsd_state" != "inactive" ]; then
      stopped_hsd=1
    fi
  elif [ "$hsd_state" != "inactive" ] && [ "$ALLOW_RUNNING_HSD_EXPORT" != "1" ]; then
    echo "hsd is running; stop it first or set ALLOW_RUNNING_HSD_EXPORT=1" >&2
    exit 2
  fi
fi

args=(--prefix "$INDEXER_HSD_PREFIX" --out "$JSONL_PATH" --network "$HSD_NETWORK")
if [ -n "$EXPORT_LIMIT" ]; then
  args+=(--limit "$EXPORT_LIMIT")
fi
args+=(--format "$EXPORT_FORMAT")

npm_root="$(npm root -g 2>/dev/null || true)"
if [ -n "$npm_root" ]; then
  export NODE_PATH="$npm_root${NODE_PATH:+:$NODE_PATH}"
fi

node scripts/hsd-export-names-jsonl.js "${args[@]}"
