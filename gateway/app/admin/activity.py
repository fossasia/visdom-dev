# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Asks the visdom instances who is connected to each workspace right now.

A workspace is "active" when someone is reading from or writing to it, which is
socket state living in the visdom processes rather than anything in this
database. The proxy hashes each workspace onto exactly one instance, so no
instance sees the whole picture and the answer is the concatenation of all of
them. Instances are asked directly over the internal network rather than through
the proxy, which would hash the request onto a single one.
"""

import concurrent.futures
import json
import logging
import re
import time
import urllib.error
import urllib.request

from app.config import settings

_SERVER_PATTERN = re.compile(r"server\s+([^\s;]+)")


def instance_addresses() -> list[str]:
    """The visdom instances to ask, read from the nginx upstream block.

    `VISDOM_SERVERS` is nginx syntax ("server visdom-1:8097 resolve;") because
    the proxy config is generated from it. Parsing it here keeps one list of
    instances rather than a second one that can drift out of step with the first.
    """
    return _SERVER_PATTERN.findall(settings.VISDOM_SERVERS or "")


def _ask(address: str, timeout: float) -> list[dict]:
    url = f"http://{address}/vis/_activity"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logging.warning("could not read activity from %s: %s", address, exc)
        return []
    return payload.get("workspaces", [])


_CACHE_TTL = 2.0
_cache: dict = {"at": 0.0, "value": {}}


def cached_activity() -> dict[str, dict]:
    """`activity_by_workspace` behind a short cache.

    One list page renders many rows and each wants the same answer, so without
    this a fifty row page would fan out fifty times. The window is short enough
    that a page still shows what is happening now.
    """
    now = time.monotonic()
    if now - _cache["at"] < _CACHE_TTL:
        return _cache["value"]
    value = activity_by_workspace()
    _cache["at"] = now
    _cache["value"] = value
    return value


def _combine(merged: dict[str, dict], workspace_id: str, entry: dict) -> None:
    """Fold one instance's answer for a workspace into the running total.

    Every instance shares the env volume, so all of them report every workspace
    that has a directory, while only the one serving it has any sockets. Letting
    the last answer win would therefore overwrite real viewer counts with the
    zeroes reported by the instances that merely see the files.

    Counts add up, since a workspace is served by one instance and the others
    contribute nothing. Everything else takes the most informative answer: the
    latest write, the largest size, and a slug from whichever instance has
    actually bound the workspace and knows it.
    """
    current = merged.get(workspace_id)
    if current is None:
        merged[workspace_id] = dict(entry)
        return

    current["viewers"] = current.get("viewers", 0) + entry.get("viewers", 0)
    current["writers"] = current.get("writers", 0) + entry.get("writers", 0)
    current["slug"] = current.get("slug") or entry.get("slug")
    for key in ("last_active_at", "bytes"):
        mine, theirs = current.get(key), entry.get(key)
        if theirs is not None and (mine is None or theirs > mine):
            current[key] = theirs


def activity_by_workspace(timeout: float | None = None) -> dict[str, dict]:
    """Live viewer/writer counts keyed by workspace id, across all instances.

    An instance that does not answer is skipped rather than failing the whole
    call, so one sick instance costs its workspaces' counts instead of the page.
    """
    addresses = instance_addresses()
    if not addresses:
        return {}
    if timeout is None:
        timeout = settings.VISDOM_ACTIVITY_TIMEOUT

    merged: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(addresses)) as pool:
        for entries in pool.map(lambda a: _ask(a, timeout), addresses):
            for entry in entries:
                workspace_id = entry.get("workspace_id")
                if workspace_id:
                    _combine(merged, workspace_id, entry)
    return merged
