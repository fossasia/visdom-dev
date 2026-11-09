# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""The machine the deployment runs on, read from inside the gateway container.

A container shares the host's kernel, so the load average, `/proc/meminfo` and
`/proc/uptime` describe the whole machine rather than the container, and the
root filesystem is the host disk the container's layers live on. Checked
against the host on the live box, where the two agree.

Nothing here uses the Docker socket. Mounting it into the gateway to read
per-container figures would amount to giving the gateway root on the host.

Every reading degrades to `None` where the platform does not offer it, so the
page still renders on a development machine.
"""

import os


def _memory():
    try:
        values = {}
        with open("/proc/meminfo") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    values[key] = int(rest.split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    if "MemTotal" not in values or "MemAvailable" not in values:
        return None
    return {"total": values["MemTotal"], "used": values["MemTotal"] - values["MemAvailable"]}


def _disk(path="/"):
    try:
        stat = os.statvfs(path)
    except OSError:
        return None
    total = stat.f_blocks * stat.f_frsize
    return {"total": total, "used": total - stat.f_bavail * stat.f_frsize}


def _load():
    try:
        return os.getloadavg()[0]
    except (OSError, AttributeError):
        return None


def _uptime():
    try:
        with open("/proc/uptime") as handle:
            return float(handle.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def snapshot() -> dict:
    return {
        "cpus": os.cpu_count() or 1,
        "load": _load(),
        "memory": _memory(),
        "disk": _disk("/"),
        "uptime_seconds": _uptime(),
    }
