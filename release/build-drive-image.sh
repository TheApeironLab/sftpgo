#!/usr/bin/env bash
# Overlay only the Drive UI on the released ARM64 SFTPGo 2.7.6 + S256 image.
set -euo pipefail
image=${1:?usage: build-drive-image.sh OUTPUT_IMAGE [LOCAL_BASE_IMAGE]}
base=${2:-ghcr.io/theapeironlab/sftpgo:2.7.6-chentu-pkce.1}
expected=sha256:deba47c921d4f8786ffb532db25689f3633d657e97ea7c4db0e4a414e48a2f33
# Docker Engine reports the config digest. The containerd image store reports the manifest digest.
manifest=sha256:d4aad31acbef0a407dfc60639af90b45a0fef210496501454df087aa285b57ae
actual=$(docker image inspect "$base" --format '{{.Id}} {{.Os}}/{{.Architecture}}')
if [[ "$actual" != "$expected linux/arm64" && "$actual" != "$manifest linux/arm64" ]]; then
  echo "Expected the released ARM64 SFTPGo 2.7.6 + S256 base" >&2
  exit 1
fi
repo=$(git rev-parse --show-toplevel)
stage=$(mktemp -d)
trap 'rm -r -- "$stage"' EXIT
for path in templates/common/{base,baselogin,login}.html templates/webadmin/{adminsetup,base}.html \
            templates/webclient/{base,sharelogin}.html static/locales/{en,zh-CN}/translation.json \
            static/img/apeiron-favicon.png static/css static/img/{apeiron,lucide}; do
  mkdir -p "$stage/assets/$(dirname "$path")"
  cp -R "$repo/$path" "$stage/assets/$path"
done
cat > "$stage/Dockerfile" <<'DOCKER'
ARG BASE=ghcr.io/theapeironlab/sftpgo:2.7.6-chentu-pkce.1
FROM ${BASE}
COPY assets/ /usr/share/sftpgo/
DOCKER
docker build --platform linux/arm64 --build-arg "BASE=$base" -t "$image" "$stage"
