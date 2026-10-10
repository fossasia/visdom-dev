# Copyright 2017-present, The Visdom Authors
import io
import json

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
