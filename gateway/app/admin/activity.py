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

import asyncio
import concurrent.futures
import json
import logging
import os
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request

from app.config import settings
from app.internal_signing import signed_headers

_SERVER_PATTERN = re.compile(r"server\s+([^\s;]+)")


def instance_addresses() -> list[str]:
    """The visdom instances to ask, read from the nginx upstream block.

    `VISDOM_SERVERS` is nginx syntax ("server visdom-1:8097 resolve;") because
    the proxy config is generated from it. Parsing it here keeps one list of
    instances rather than a second one that can drift out of step with the first.
    """
    return _SERVER_PATTERN.findall(settings.VISDOM_SERVERS or "")


_MAX_BYTES = 4 * 1024 * 1024


def _read_within(response, deadline: float) -> bytes:
    body = bytearray()
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("answer took too long")
        chunk = response.read(65536)
        if not chunk:
            return bytes(body)
        body += chunk
        if len(body) > _MAX_BYTES:
            raise ValueError("answer too large")


ACTIVITY_PATH = "/vis/_activity"


_reported: set[str] = set()


def internal_setup_problem() -> str | None:
    if not settings.VISDOM_INTERNAL_READ_KEY:
        return "VISDOM_INTERNAL_READ_KEY is not set"
    if not settings.VISDOM_INTERNAL_CA:
        return "VISDOM_INTERNAL_CA is not set"
    if not os.path.isfile(settings.VISDOM_INTERNAL_CA) or not os.access(settings.VISDOM_INTERNAL_CA, os.R_OK):
        return "VISDOM_INTERNAL_CA cannot be read"
    return None


def _setup_is_complete() -> bool:
    problem = internal_setup_problem()
    if problem is None:
        return True
    if problem not in _reported:
        _reported.add(problem)
        logging.error(
            "not calling the visdom instances: %s (VISDOM_INTERNAL_CA is %r)",
            problem,
            settings.VISDOM_INTERNAL_CA,
        )
    return False


def internal_url(address: str, path: str) -> str:
    host = address.rsplit(":", 1)[0]
    return f"https://{host}:{settings.VISDOM_INTERNAL_PORT}{path}"


def internal_tls() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=settings.VISDOM_INTERNAL_CA)
    context.check_hostname = False
    return context


def certificate_days_left(address: str, timeout: float) -> float | None:
    if not _setup_is_complete():
        return None
    host = address.rsplit(":", 1)[0]
    try:
        with socket.create_connection((host, settings.VISDOM_INTERNAL_PORT), timeout=timeout) as raw:
            with internal_tls().wrap_socket(raw, server_hostname=host) as tls:
                not_after = tls.getpeercert()["notAfter"]
    except (OSError, KeyError, ValueError) as exc:
        logging.warning("could not read the internal certificate of %s: %s", address, exc)
        return None
    return (ssl.cert_time_to_seconds(not_after) - time.time()) / 86400


def _ask(address: str, timeout: float) -> tuple[bool, list[dict]]:
    if not _setup_is_complete():
        return False, []
    request = urllib.request.Request(
        internal_url(address, ACTIVITY_PATH),
        headers=signed_headers(settings.VISDOM_INTERNAL_READ_KEY, "GET", ACTIVITY_PATH),
    )
    deadline = time.monotonic() + timeout
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=internal_tls()) as response:
            payload = json.loads(_read_within(response, deadline) or b"{}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logging.warning("could not read activity from %s: %s", address, exc)
        return False, []
    rows = payload.get("workspaces") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        logging.warning("activity from %s was not in the expected shape", address)
        return False, []
    return True, [row for row in rows if isinstance(row, dict)]


_CACHE_TTL = 2.0
_cache: dict = {"at": 0.0, "value": {"answered": False, "workspaces": {}}}
_cache_lock = threading.Lock()


def cached_snapshot() -> dict:
    """`activity_snapshot` behind a short cache.

    One list page renders many rows and each wants the same answer, so without
    this a fifty row page would fan out fifty times. The window is short enough
    that a page still shows what is happening now.
    """
    with _cache_lock:
        if time.monotonic() - _cache["at"] < _CACHE_TTL:
            return _cache["value"]
        value = activity_snapshot()
        _cache["at"] = time.monotonic()
        _cache["value"] = value
        return value


def cached_activity() -> dict[str, dict]:
    """Just the per-workspace part of the cached snapshot."""
    return cached_snapshot()["workspaces"]


async def refresh_activity() -> None:
    """Fill the cache from a worker thread so a slow instance does not hold up other requests."""
    await asyncio.to_thread(cached_activity)


def known_activity() -> dict[str, dict]:
    """The last answer fetched, without asking the instances again."""
    return _cache["value"]["workspaces"]


_OPTIONAL_COUNTS = ("writes", "broadcasts", "broadcast_bytes", "active_hour", "active_minutes_mask")


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _usable(entry: dict) -> bool:
    if not isinstance(entry.get("workspace_id"), str) or not entry["workspace_id"]:
        return False
    if not all(_is_count(entry.get(key, 0)) for key in ("viewers", "writers")):
        return False
    if not all(entry.get(key) is None or _is_count(entry[key]) for key in _OPTIONAL_COUNTS):
        return False
    return all(entry.get(key) is None or _is_number(entry[key]) for key in ("last_active_at", "bytes"))


def _union_active_minutes(current: dict, entry: dict) -> None:
    """Combine two instances' active-minute masks for the same workspace.

    A union rather than a sum: three instances that each served a write in the
    same minute did one minute of work between them. Masks belong to an hour, so
    only answers about the same hour combine, and a later hour replaces an
    earlier one outright rather than folding two hours into one number.
    """
    mine_hour, theirs_hour = current.get("active_hour"), entry.get("active_hour")
    if theirs_hour is None:
        return
    if mine_hour is None or theirs_hour > mine_hour:
        current["active_hour"] = theirs_hour
        current["active_minutes_mask"] = entry.get("active_minutes_mask") or 0
        return
    if theirs_hour == mine_hour:
        current["active_minutes_mask"] = (current.get("active_minutes_mask") or 0) | (
            entry.get("active_minutes_mask") or 0
        )


def _combine(merged: dict[str, dict], workspace_id: str, entry: dict) -> None:
    """Fold one instance's answer for a workspace into the running total.

    Every instance shares the env volume, so all of them report every workspace
    that has a directory, while only the one serving it has any sockets. Letting
    the last answer win would therefore overwrite real viewer counts with the
    zeroes reported by the instances that merely see the files.

    Counts add up, since a workspace is served by one instance and the others
    contribute nothing. That holds for the running totals as well as the live
    counts: a workspace moves between instances when one restarts, and the work
    each did is a share of the same total rather than a rival answer to it.
    Everything else takes the most informative answer: the latest write, the
    largest size, and a slug from whichever instance has actually bound the
    workspace and knows it.

    A counter absent from every instance stays absent, so a deployment running a
    visdom that predates them reports nothing rather than a fabricated zero.
    """
    current = merged.get(workspace_id)
    if current is None:
        merged[workspace_id] = dict(entry)
        return

    for key in ("viewers", "writers", "writes", "broadcasts", "broadcast_bytes"):
        mine, theirs = current.get(key), entry.get(key)
        if mine is None and theirs is None:
            continue
        current[key] = (mine or 0) + (theirs or 0)
    _union_active_minutes(current, entry)
    current["slug"] = current.get("slug") or entry.get("slug")
    for key in ("last_active_at", "bytes"):
        mine, theirs = current.get(key), entry.get(key)
        if theirs is not None and (mine is None or theirs > mine):
            current[key] = theirs


def activity_snapshot(timeout: float | None = None) -> dict:
    """What the instances collectively know, and whether any of them answered.

    An instance that does not answer is skipped rather than failing the whole
    call, so one sick instance costs its workspaces' counts instead of the page.
    `answered` is true once any instance has replied, which is what lets a
    caller read a missing workspace as one nobody has written to. Every instance
    shares the env volume, so any one of them reports every workspace that has a
    directory, and a workspace missing from an answer really has none.
    """
    addresses = instance_addresses()
    if not addresses:
        return {"answered": False, "workspaces": {}}
    if timeout is None:
        timeout = settings.VISDOM_ACTIVITY_TIMEOUT

    answered = False
    merged: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(addresses)) as pool:
        for ok, entries in pool.map(lambda a: _ask(a, timeout), addresses):
            answered = answered or ok
            for entry in entries:
                workspace_id = entry.get("workspace_id")
                if workspace_id and _usable(entry):
                    _combine(merged, workspace_id, entry)
    return {"answered": answered, "workspaces": merged}


def activity_per_instance(timeout: float | None = None) -> list[tuple]:
    """Each instance's own answer, unmerged, as (address, answered, entries).

    The merged snapshot sums counters across instances, which is right for a
    page showing what is happening and wrong for working out what is new: a
    restart is only visible in the one instance that had it.
    """
    addresses = instance_addresses()
    if not addresses:
        return []
    if timeout is None:
        timeout = settings.VISDOM_ACTIVITY_TIMEOUT
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(addresses)) as pool:
        answers = list(pool.map(lambda a: _ask(a, timeout), addresses))
    return [(address, ok, entries) for address, (ok, entries) in zip(addresses, answers, strict=True)]


def activity_by_workspace(timeout: float | None = None) -> dict[str, dict]:
    """Live viewer/writer counts keyed by workspace id, across all instances."""
    return activity_snapshot(timeout)["workspaces"]
