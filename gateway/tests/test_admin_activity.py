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
