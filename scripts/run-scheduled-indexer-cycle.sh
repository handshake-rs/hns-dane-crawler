#!/usr/bin/env bash
set -euo pipefail

INDEXER_MOUNT="${INDEXER_MOUNT:-/mnt/hnscrawler}"
INDEXER_REPO_DIR="${INDEXER_REPO_DIR:-$INDEXER_MOUNT/HNScrawler}"
GCP_PROJECT="${GCP_PROJECT:-denuo-web-site}"
GCP_ZONE="${GCP_ZONE:-us-west1-b}"
INDEXER_VM="${INDEXER_VM:-hns-topology-indexer}"

# The VM also serves manually started auction tasks. Only the weekly wake starts
# this cycle; Cloud Scheduler wakes it on Monday at 03:05 UTC.
if [[ "$(date -u +%u%H)" != "103" ]]; then
  echo "[scheduled-indexer] outside Monday 03:00 UTC window; skipping"
  exit 0
fi

mountpoint -q "$INDEXER_MOUNT" || { echo "$INDEXER_MOUNT is not mounted" >&2; exit 2; }
mkdir -p "$INDEXER_MOUNT/logs"
exec >>"$INDEXER_MOUNT/logs/scheduled-indexer-cycle.log" 2>&1

finish() {
  local status=$?
  trap - EXIT
  echo "[scheduled-indexer] $(date -u +%Y-%m-%dT%H:%M:%SZ) exit_status=$status; stopping VM"
  gcloud compute instances stop "$INDEXER_VM" \
    --project "$GCP_PROJECT" --zone "$GCP_ZONE" --async --quiet || true
  exit "$status"
}
trap finish EXIT

echo "[scheduled-indexer] $(date -u +%Y-%m-%dT%H:%M:%SZ) starting weekly cycle"
cd "$INDEXER_REPO_DIR"
git pull --ff-only
sudo systemctl start hsd

tip=""
for attempt in $(seq 1 720); do
  if ready_output="$(scripts/check-hsd-ready.sh 2>&1)"; then
    tip="$(printf '%s\n' "$ready_output" | sed -n 's/^\[ok\] blocks_reported: \([0-9][0-9]*\)$/\1/p' | head -n1)"
    [[ "$tip" =~ ^[0-9]+$ ]] || { echo "Cannot read the ready HSD block height" >&2; exit 2; }
    break
  fi
  echo "[scheduled-indexer] HSD not ready attempt=$attempt/720"
  sleep 30
done
[[ -n "$tip" ]] || { echo "HSD did not sync within six hours" >&2; exit 1; }
echo "[scheduled-indexer] HSD ready at block $tip"

export TOPOLOGY_DB="$INDEXER_MOUNT/data/topology.sqlite"
export PUBLIC_DIR="$INDEXER_MOUNT/public"
export PIPELINE_MODE=incremental
export INCREMENTAL_MAX_BLOCKS=10000
export MIN_INDEXED_HEIGHT="$tip"
export HSD_START_READY_ATTEMPTS=3
export HSD_START_READY_INTERVAL_SECONDS=10
export RUN_PUBLISH_FROM_INDEXER=1
export INDEXER_GIT_PULL=0

scripts/run-indexer-pipeline-local.sh
echo "[scheduled-indexer] $(date -u +%Y-%m-%dT%H:%M:%SZ) published block $tip or newer"
