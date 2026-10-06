#!/usr/bin/env bash

# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

set -euo pipefail

STACK_DIR="${STACK_DIR:-/home/ubuntu/app/visdom-dev}"
LOCAL_DIR="${LOCAL_DIR:-/home/ubuntu/backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
VISDOM_VOLUME="${VISDOM_VOLUME:-visdom-dev_visdom_data}"
PING_URL="${PING_URL:-}"

ping_failure() {
    if [ -n "$PING_URL" ]; then
        curl -fsS -m 10 --retry 3 "${PING_URL}/fail" >/dev/null 2>&1 || true
    fi
}

fail() {
    echo "backup: $*" >&2
    ping_failure
    exit 1
}

trap 'fail "failed at line $LINENO"' ERR

[ -n "${BACKUP_BUCKET:-}" ] || fail "BACKUP_BUCKET is not set. See deploy/BACKUPS.md"
command -v aws >/dev/null 2>&1 || fail "the aws cli is not installed. See deploy/BACKUPS.md"
cd "$STACK_DIR" 2>/dev/null || fail "no stack at $STACK_DIR"

postgres_user=$(grep -E '^POSTGRES_USER=' .env | head -1 | cut -d= -f2-)
postgres_db=$(grep -E '^POSTGRES_DB=' .env | head -1 | cut -d= -f2-)
[ -n "$postgres_user" ] && [ -n "$postgres_db" ] || fail "POSTGRES_USER or POSTGRES_DB missing from $STACK_DIR/.env"

stamp=$(date -u +%Y%m%d-%H%M%S)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

docker compose exec -T db pg_dump -U "$postgres_user" -Fc "$postgres_db" </dev/null >"$work/db.dump"
[ -s "$work/db.dump" ] || fail "the database dump came out empty"

docker run --rm -v "$VISDOM_VOLUME:/envs:ro" busybox tar -cf - -C /envs . >"$work/envs.tar"
[ -s "$work/envs.tar" ] || fail "the plot data archive came out empty"

cp .env "$work/env"

mkdir -p "$LOCAL_DIR"
archive="$LOCAL_DIR/visdom-dev-$stamp.tar.gz"
tar -czf "$archive" -C "$work" db.dump envs.tar env
sha256sum "$archive" | cut -d' ' -f1 >"$archive.sha256"

key="visdom-dev/$(date -u +%Y/%m)/$(basename "$archive")"
region_flag=()
[ -n "${AWS_REGION:-}" ] && region_flag=(--region "$AWS_REGION")
aws s3api put-object --bucket "$BACKUP_BUCKET" --key "$key" --body "$archive" "${region_flag[@]}" >/dev/null
aws s3api put-object --bucket "$BACKUP_BUCKET" --key "$key.sha256" --body "$archive.sha256" "${region_flag[@]}" >/dev/null

find "$LOCAL_DIR" -name 'visdom-dev-*.tar.gz*' -mtime +"$KEEP_DAYS" -delete

if [ -n "$PING_URL" ]; then
    curl -fsS -m 10 --retry 3 "$PING_URL" >/dev/null 2>&1 || true
fi

echo "backup: $(du -h "$archive" | cut -f1) to s3://$BACKUP_BUCKET/$key"
