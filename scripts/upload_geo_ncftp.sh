#!/usr/bin/env bash
# Resilient overnight uploader for GEO submissions via ncftp.
# Two parallel jobs (bulk + spatial). Each retries on failure (30s cooldown).
# ncftpput -R -z resumes partial files.
#
# Logging:
#  - per-job log at GEO/upload_logs/{label}.log
#  - per-file completion lines (ncftpput -V output, line-buffered via stdbuf)
#  - heartbeat every 30s with current file, byte position, retry count
#
# Usage:
#   bash scripts/upload_geo_ncftp.sh                # both
#   bash scripts/upload_geo_ncftp.sh bulk           # one
#   bash scripts/upload_geo_ncftp.sh spatial
#
# Monitor live:
#   tail -F GEO/upload_logs/*.log

set -u
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  . .env
  set +a
fi

: "${NCFTP_HOST:?Set NCFTP_HOST in .env}"
: "${NCFTP_USER:?Set NCFTP_USER in .env}"
: "${NCFTP_PASS:?Set NCFTP_PASS in .env}"
: "${NCFTP_REMOTE_BASE:?Set NCFTP_REMOTE_BASE in .env}"

command -v ncftpput >/dev/null || { echo "ncftpput missing"; exit 1; }
command -v stdbuf >/dev/null   || { echo "stdbuf missing (coreutils)"; exit 1; }

LOG_DIR="GEO/upload_logs"
mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Emit a heartbeat for one PID: which file it has open + current size.
heartbeat_loop() {
  local label="$1"
  local pid_file="$2"
  local log="$3"
  while true; do
    sleep 30
    local pid
    pid=$(cat "$pid_file" 2>/dev/null || echo "")
    if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
      continue
    fi
    # Find the local file currently being read (fd opened by ncftpput).
    local cur
    cur=$(ls -l /proc/"$pid"/fd 2>/dev/null \
            | grep -oP "[^ ]+\.(fastq\.gz|txt|h5|csv|png|cloupe|svs|json|jpg|html|tsv|gz|prism|xlsx)" \
            | grep -v 'pipe' | head -1)
    if [[ -z "$cur" ]]; then
      echo "[$(ts)] [$label heartbeat] pid=$pid (no open file detected)" >> "$log"
    else
      local name
      name=$(basename "$cur")
      local sz
      sz=$(stat -c %s "$cur" 2>/dev/null)
      echo "[$(ts)] [$label heartbeat] pid=$pid  current=$name  size=$((sz/1000000))MB" >> "$log"
    fi
  done
}

upload_loop_v2() {
  local label="$1"
  local remote_dir="$2"
  local local_src="$3"
  local log="$LOG_DIR/${label}.log"
  local pid_file="$LOG_DIR/${label}.pid"
  local attempt=0

  heartbeat_loop "$label" "$pid_file" "$log" &
  local hb_pid=$!
  trap "kill $hb_pid 2>/dev/null; rm -f $pid_file" RETURN

  while true; do
    attempt=$((attempt + 1))
    echo "[$(ts)] [$label] attempt #$attempt — ncftpput -R -z -V (resume)" >> "$log"

    # Launch ncftpput with line-buffered output, redirected straight to log.
    stdbuf -oL ncftpput -R -z -V \
        -u "$NCFTP_USER" -p "$NCFTP_PASS" \
        "$NCFTP_HOST" "$remote_dir" "$local_src" \
        >>"$log" 2>&1 &
    local nf_pid=$!
    echo "$nf_pid" > "$pid_file"
    wait "$nf_pid"
    rc=$?
    rm -f "$pid_file"

    if [[ $rc -eq 0 ]]; then
      echo "[$(ts)] [$label] ✓ ncftpput exited 0 — done (attempt #$attempt)" >> "$log"
      kill "$hb_pid" 2>/dev/null
      return 0
    else
      echo "[$(ts)] [$label] ✗ ncftpput exited $rc — sleeping 30s" >> "$log"
      sleep 30
    fi
  done
}

# Remote sub-paths under NCFTP_REMOTE_BASE can be overridden via .env:
#   NCFTP_REMOTE_BULK=bulk_rna   (default: bulk_rna)
#   NCFTP_REMOTE_SPATIAL=spatial (default: spatial)
NCFTP_REMOTE_BULK="${NCFTP_REMOTE_BULK:-bulk_rna}"
NCFTP_REMOTE_SPATIAL="${NCFTP_REMOTE_SPATIAL:-spatial}"

JOBS=(${@:-bulk spatial})

PIDS=()
for j in "${JOBS[@]}"; do
  case "$j" in
    bulk)
      upload_loop_v2 bulk "$NCFTP_REMOTE_BASE/$NCFTP_REMOTE_BULK" "GEO/bulk_rna/GEO" &
      PIDS+=($!)
      ;;
    spatial)
      upload_loop_v2 spatial "$NCFTP_REMOTE_BASE/$NCFTP_REMOTE_SPATIAL" "GEO/spatial" &
      PIDS+=($!)
      ;;
    *)
      echo "unknown job: $j (use 'bulk' or 'spatial')"
      exit 1
      ;;
  esac
done

echo "[$(ts)] launched upload_loop PIDs: ${PIDS[*]}  jobs: ${JOBS[*]}"
echo "[$(ts)] logs: $LOG_DIR/{${JOBS[*]// /,}}.log"
echo "[$(ts)] live tail: tail -F $LOG_DIR/*.log"

trap '
  echo "[$(ts)] interrupted — killing children"
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
  pkill -P $$ 2>/dev/null
  pkill -f "ncftpput .* $NCFTP_HOST" 2>/dev/null
  wait
  exit 130
' INT TERM

wait "${PIDS[@]}"
echo "[$(ts)] all upload jobs complete."
