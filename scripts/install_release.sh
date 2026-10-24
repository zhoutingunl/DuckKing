#!/usr/bin/env bash
# Install ONLY DuckKing. Never changes ai_gateway, system Python, or Nginx.
set -euo pipefail
umask 022
[[ $EUID -eq 0 ]] || { echo "Run as root on the deployment target" >&2; exit 1; }
[[ $# -eq 4 ]] || { echo "Usage: $0 archive sha256 version commit" >&2; exit 1; }
archive=$1 checksum=$2 version=$3 commit=$4
[[ $checksum =~ ^[0-9a-f]{64}$ && $commit =~ ^[0-9a-f]{40}$ && $version =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] || exit 2
base=/opt/duckking
release=$base/releases/$version
python=/usr/local/bin/python3.12
uv_binary=${DUCKKING_UV:-/root/.local/bin/uv}
[[ -x $python && -x $uv_binary ]] || { echo "Python 3.12 and uv are required" >&2; exit 1; }
mkdir -p "$base/releases"
exec 9>"$base/deploy.lock"
flock -n 9 || { echo "Another DuckKing release is running" >&2; exit 1; }
[[ ! -e $release ]] || { echo "Immutable release already exists" >&2; exit 1; }
printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check --status
# systemd owns the transient UID and moves StateDirectory below /var/lib/private.
# Do not edit the target's protected passwd/group databases.
install -d -m 700 /var/lib/duckking /var/lib/duckking/verification /etc/duckking
previous=$(readlink -f "$base/current" || true)
switched=0
unit_changed=0
unit_backup=$base/previous-duckking.service
if [[ -e /etc/systemd/system/duckking.service ]]; then
  cp /etc/systemd/system/duckking.service "$unit_backup"
elif [[ -e $unit_backup ]]; then
  rm "$unit_backup"
fi

record() {
  "$python" - "$release/release.json" "$1" "$2" "$3" <<'PY'
import json,sys
from datetime import UTC,datetime
from pathlib import Path
metadata=Path(sys.argv[1])
if metadata.is_file():
    row=json.loads(metadata.read_text())
    row.update(ts=datetime.now(UTC).isoformat(),status=sys.argv[2],selftest=sys.argv[3],rollback=sys.argv[4])
    with Path('/var/lib/duckking/deployments.jsonl').open('a') as stream:
        stream.write(json.dumps(row,ensure_ascii=False)+'\n')
PY
  chown --reference=/var/lib/duckking /var/lib/duckking/deployments.jsonl
  chmod 600 /var/lib/duckking/deployments.jsonl
}

failed() {
  status=$?
  trap - ERR
  rollback=unchanged
  if [[ $unit_changed == 1 && -f $unit_backup ]]; then
    cp "$unit_backup" /etc/systemd/system/duckking.service
    systemctl daemon-reload || true
  fi
  if [[ $switched == 1 ]]; then
    if [[ -n $previous && -d $previous ]]; then
      ln -sfn "$previous" "$base/current.next"
      mv -Tf "$base/current.next" "$base/current"
      rollback=failed
      if systemctl restart duckking; then
        for attempt in {1..20}; do
          if "$python" - "$previous/release.json" <<'PY'
import json,sys,urllib.request
expected=json.load(open(sys.argv[1]))['commit']
with urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=2) as response:
    assert json.load(response)['release']['commit']==expected
PY
          then rollback=restored; break; fi
          sleep 1
        done
      fi
    else
      systemctl stop duckking || true
      systemctl disable duckking || true
      rollback=not_available
    fi
  fi
  record failed failed "$rollback" || true
  echo "DuckKing install failed; rollback=$rollback" >&2
  exit "$status"
}
trap failed ERR

mkdir "$release"
"$python" - "$archive" "$release" "$version" "$commit" <<'PY'
import json,sys,tarfile
from pathlib import Path
with tarfile.open(sys.argv[1]) as archive:
    archive.extractall(sys.argv[2],filter='data')
metadata=json.loads((Path(sys.argv[2])/'release.json').read_text())
assert metadata['version']==sys.argv[3] and metadata['commit']==sys.argv[4]
PY
export UV_CACHE_DIR=$base/cache UV_CONCURRENT_DOWNLOADS=2 UV_CONCURRENT_INSTALLS=2
export DUCKKING_SIM_DIR=$release/external OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
"$uv_binary" sync --project "$release" --frozen --no-dev --extra simulation --python "$python" --no-managed-python
"$python" - "$release" <<'PY'
import hashlib,json,runpy,sys
from pathlib import Path
release=Path(sys.argv[1])
upstream=runpy.run_path(str(release/'scripts/fetch_scene_assets.py'))
sources=json.loads((release/'external/sources.json').read_text())
assert sources=={'model_commit':upstream['REVISION'],'policy_commit':upstream['POLICIES']}
for name,expected in upstream['CHECKSUMS'].items():
    assert hashlib.sha256((release/'external/policies'/name).read_bytes()).hexdigest()==expected
PY
nice -n 10 "$release/.venv/bin/python" "$release/scripts/verify_scenarios.py" --output "/var/lib/duckking/verification/physics-$version.json"
chown --reference=/var/lib/duckking "/var/lib/duckking/verification/physics-$version.json"
if [[ ! -e /etc/duckking/runtime.env ]]; then
  printf 'DUCKKING_BIND_HOST=127.0.0.1\n' > /etc/duckking/runtime.env
  chmod 600 /etc/duckking/runtime.env
fi
install -m 644 "$release/deploy/duckking.service" /etc/systemd/system/duckking.service
unit_changed=1
ln -sfn "$release" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
switched=1
systemctl daemon-reload
systemctl enable duckking
systemctl restart duckking
ready=0
for attempt in {1..30}; do
  if curl -fsS http://127.0.0.1:8765/api/health >/dev/null; then ready=1; break; fi
  sleep 1
done
[[ $ready == 1 ]]
"$release/.venv/bin/python" "$release/scripts/release_smoke.py" --url http://127.0.0.1:8765/ --commit "$commit"
record staged backend_passed not_needed
trap - ERR
echo "DuckKing staged on loopback. HTTPS routing and real cloud voice still require verification."
