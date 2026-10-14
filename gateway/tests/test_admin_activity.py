# Copyright 2017-present, The Visdom Authors
import asyncio
import io
import json
import time

import pytest

from app.admin import activity


def _answering(monkeypatch, payload):
    def urlopen(url, timeout):
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(activity.urllib.request, "urlopen", urlopen)


def test_an_instance_that_answers_properly_is_read(monkeypatch):
    _answering(monkeypatch, {"workspaces": [{"workspace": "vision", "sockets": 2}]})
    assert activity._ask("visdom-1:8097", 1.0) == [{"workspace": "vision", "sockets": 2}]


@pytest.mark.parametrize(
    "payload",
    [["not", "an", "object"], "text", 7, None, {"workspaces": "nope"}, {"other": []}],
)
def test_an_instance_that_answers_in_the_wrong_shape_is_skipped(monkeypatch, payload):
    _answering(monkeypatch, payload)
    assert activity._ask("visdom-1:8097", 1.0) == []


def test_rows_that_are_not_objects_are_dropped(monkeypatch):
    _answering(monkeypatch, {"workspaces": [{"workspace": "vision"}, "junk", 3]})
    assert activity._ask("visdom-1:8097", 1.0) == [{"workspace": "vision"}]


def test_a_slow_instance_does_not_hold_up_other_requests(monkeypatch):
    def slow():
        time.sleep(0.5)
        return {"ws": {"viewers": 1}}

    monkeypatch.setattr(activity, "activity_by_workspace", slow)
    monkeypatch.setattr(activity, "_cache", {"at": 0.0, "value": {}})

    async def run():
        ticks = 0

        async def tick():
            nonlocal ticks
            for _ in range(5):
                await asyncio.sleep(0.05)
                ticks += 1

        await asyncio.gather(activity.refresh_activity(), tick())
        return ticks

    started = time.monotonic()
    assert asyncio.run(run()) == 5
    assert time.monotonic() - started < 0.9
    assert activity.known_activity() == {"ws": {"viewers": 1}}


def test_an_instance_that_keeps_trickling_is_cut_off(monkeypatch):
    class Trickle(io.RawIOBase):
        def read(self, size=-1):
            if size is None or size < 0:
                time.sleep(1.0)
                return b"{}"
            time.sleep(0.05)
            return b" "

    monkeypatch.setattr(activity.urllib.request, "urlopen", lambda url, timeout: Trickle())
    started = time.monotonic()
    assert activity._ask("visdom-1:8097", 0.2) == []
    assert time.monotonic() - started < 0.5


def test_an_answer_that_is_too_large_is_skipped(monkeypatch):
    monkeypatch.setattr(activity, "_MAX_BYTES", 10)
    _answering(monkeypatch, {"workspaces": [{"workspace_id": "vision"}]})
    assert activity._ask("visdom-1:8097", 1.0) == []


def test_rows_with_bad_fields_are_skipped_and_good_rows_kept(monkeypatch):
    rows = [
        {"workspace_id": "vision", "viewers": 2},
        {"workspace_id": "vision", "viewers": "unknown"},
        {"workspace_id": ["vision"], "viewers": 1},
        {"workspace_id": "", "viewers": 1},
        {"workspace_id": "vision", "writers": True},
        {"workspace_id": "vision", "bytes": "lots"},
        {"workspace_id": "audio", "writers": 1, "bytes": 512, "last_active_at": None},
    ]
    monkeypatch.setattr(activity, "instance_addresses", lambda: ["visdom-1:8097"])
    monkeypatch.setattr(activity, "_ask", lambda address, timeout: rows)
    merged = activity.activity_by_workspace(timeout=1.0)
    assert merged["vision"]["viewers"] == 2
    assert merged["audio"]["writers"] == 1
    assert set(merged) == {"vision", "audio"}
