# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import hashlib
import hmac
import time


def signature(key: str, method: str, uri: str, timestamp: int, body: bytes) -> str:
    message = "\n".join([method.upper(), uri, str(timestamp), hashlib.sha256(body or b"").hexdigest()])
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def signed_headers(key: str, method: str, uri: str, body: bytes = b"", now: float | None = None) -> dict[str, str]:
    timestamp = int(time.time() if now is None else now)
    return {
        "X-Visdom-Timestamp": str(timestamp),
        "X-Visdom-Signature": signature(key, method, uri, timestamp, body),
    }
