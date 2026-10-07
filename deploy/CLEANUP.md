# Weekly build cleanup

Every deploy rebuilds the images, and docker keeps the pieces of each build
so the next one is faster. Nothing ever throws them away, and on this box
they once filled the disk.

Once a week, on Sunday within ten minutes after 04:30 UTC, an hour after the
nightly backup:

| Step | What goes | What stays |
|---|---|---|
| `docker builder prune --all --filter until=168h` | every build file not used for a week, not only the dangling ones | anything the last week of deploys used, so the next build is still quick |
| `docker builder prune --max-used-space 3gb` | the oldest build files, until at most 3 GB are left. Needs Docker Engine 28 or newer; an older one skips this step and carries on | the newest 3 GB, for a week with many deploys |
| `docker image prune` | images no container uses and no tag points at | every image a container is running |
| `df -h /` | nothing | prints disk use into the log, so the effect can be read back |

Volumes are never touched. The database and every plot live in volumes.

## Install, once

```bash
ssh <user>@<server>
cd ~/app/visdom-dev && git pull
sudo install -m 644 deploy/visdom-prune.service deploy/visdom-prune.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now visdom-prune.timer
systemctl list-timers visdom-prune.timer
```

## Run it now, and read what it did

```bash
sudo systemctl start visdom-prune.service
journalctl -u visdom-prune -n 20 --no-pager
```

The log shows how much space each step reclaimed, then the disk use after.

## Turn it off

```bash
sudo systemctl disable --now visdom-prune.timer
```
