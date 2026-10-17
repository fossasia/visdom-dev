#!/usr/bin/env bash

# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

set -euo pipefail

DIR="${INTERNAL_TLS_DIR:-$(dirname "$0")/internal-tls}"
DAYS="${INTERNAL_TLS_DAYS:-730}"

bundle() {
    cat "$DIR/internal.crt" > "$DIR/internal-ca.pem"
    if [ -f "$DIR/internal.previous.crt" ]; then
        cat "$DIR/internal.previous.crt" >> "$DIR/internal-ca.pem"
    fi
}

case "${1:-}" in
new)
    mkdir -p "$DIR"
    if [ -f "$DIR/internal.crt" ]; then
        mv "$DIR/internal.crt" "$DIR/internal.previous.crt"
    fi
    ( umask 077 && openssl req -x509 -newkey rsa:3072 -nodes -days "$DAYS" \
        -subj "/CN=visdom-internal" \
        -keyout "$DIR/internal.key" -out "$DIR/internal.crt" 2>/dev/null )
    chmod 644 "$DIR/internal.crt"
    bundle
    openssl x509 -enddate -noout -in "$DIR/internal.crt"
    ;;
drop-previous)
    rm -f "$DIR/internal.previous.crt"
    bundle
    ;;
*)
    echo "usage: $0 new|drop-previous" >&2
    exit 2
    ;;
esac
