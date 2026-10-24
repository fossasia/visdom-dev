# bench/ — capacity measurement for visdom-dev

Answers one question: **does visdom pin one core under concurrent writes, and where does
throughput knee?**

Nothing here deploys a second visdom. The harness is a load *client* plus a measuring
probe; it drives the live stack — real nginx, real auth gate, real Tornado server, real
Postgres — using the visdom python client, which is what a user's training script runs.

**Answer, measured on 4 OCPU ARM:** yes. One visdom process saturates one core at
conc≈25 and throughput plateaus at **~575 line writes/s**, while the host still has
2.9 of 4 cores idle. Viewer fan-out is *not* the second ceiling — 2,000 broadcasts/s
costs 0.24 cores. The scaling axis is therefore more visdom processes sharded by
workspace, not a bigger VM and not a faster framework.

**Sharding by workspace then lifts that ceiling**: three instances behind nginx
consistent hashing reach 1.51 cores as a pool and 743 writes/s, and throughput no longer
plateaus. Numbers in [Results](#results).

**The gateway in front of it is not the binding constraint.** It is the one component that
does not shard, so it was the obvious suspect, but it serves ~12 logins/s (bcrypt-bound, by
design) and stayed at 0.08 cores while cold page loads saturated the host. The auth check
it exists to answer costs 2.4 ms, which is what let the nginx cache window drop from 30 s
to 5 s and close the revocation gap six times faster.

## Layout

| File | Runs where | Purpose |
|---|---|---|
| `sweep.sh` | VM host | orchestrates a concurrency sweep, writes `results/` |
| `lib.sh` | VM host | sampler and result-row plumbing, shared by both runners |
| `cpu_sample.py` | VM host | samples any named process groups plus the host into CSV |
| `writebench.py` | `bench` container | scenario 4 — N writers |
| `viewbench.py` | `bench` container | scenario 5 — N viewers watching one workspace |
| `shardcheck.py` | `bench` container | asserts nginx routes each workspace to one instance |
| `fleet.py` | `bench` container | creates and destroys 4b's throwaway workspaces and keys |
| `Dockerfile`, `requirements.txt` | — | the generator image |
| `k6run.sh` | VM host | runs one k6 scenario with the sampler attached |
| `k6/lib.js` | `k6` container | seeding, sessions, the settle wait and the executor options |
| `k6/login.js` | `k6` container | scenario 1 — login storm |
| `k6/browse.js` | `k6` container | scenario 2 — dashboard browse |
| `k6/coldload.js` | `k6` container | scenario 3 — cold visdom page load |

`cpu_sample.py` runs on the **host**, not in a container: a container has its own PID
namespace and cannot see the visdom server process at all. Standard library only, so
nothing needs installing.

## Running it

On the VM, never from a laptop — otherwise you are measuring a home connection and the
round trip to Oracle.

Once, to build the generator image:

```bash
cd ~/app/visdom-dev
git pull
docker compose --profile bench build bench
```

Then, for every run:

```bash
cd ~/app/visdom-dev
read -rs VISDOM_API_KEY; export VISDOM_API_KEY
export BENCH_WORKSPACE=loadtest

./bench/sweep.sh --smoke                 # 1 writer + 1 viewer, 2 writes: proves the plumbing
```

`--smoke` exercises every driver and takes a few seconds. **Run it first every time** —
it is what catches an expired key, a stale image, a broken fan-out filter or misrouted
sharding before a twenty-minute sweep produces a file full of zeros.

| Scenario | Command |
|---|---|
| **4a** — N writers, one shared workspace | `./bench/sweep.sh` |
| **4a**, image payloads | `BENCH_KIND=image ./bench/sweep.sh` |
| **4b** — N writers, one workspace + key each | `./bench/sweep.sh --fleet` |
| **5** — N viewers watching one writer | `./bench/sweep.sh --viewers` |

4b needs a user session to create its workspaces, so it takes credentials rather than a
key:

```bash
export BENCH_EMAIL=you@example.com
read -rs BENCH_PASSWORD; export BENCH_PASSWORD
./bench/sweep.sh --fleet
```

Any sweep can be narrowed with the level lists, which is how to iterate quickly:

```bash
BENCH_LEVELS="1 10" BENCH_OPS=20 ./bench/sweep.sh
BENCH_VIEWER_LEVELS="1 50 200" BENCH_RATE=20 ./bench/sweep.sh --viewers
```

The gateway scenarios are k6 rather than the python generator, and need no credentials —
they seed their own accounts:

```bash
./bench/k6run.sh login --smoke              # proves the plumbing, a few seconds
./bench/k6run.sh login                      # scenario 1
./bench/k6run.sh browse                     # scenario 2
./bench/k6run.sh coldload                   # scenario 3
BENCH_RATES=1,2,5,10,20 ./bench/k6run.sh coldload
```

Each scenario declares its own CSV columns and the processes worth sampling, so adding one
needs no change to `k6run.sh`. Both wait for the gateway to answer quickly three times
before seeding: a saturated gateway keeps answering slowly for minutes after the load
stops, and a run started too soon measures the previous run's queue rather than its own.

**Never run two scenarios at the same time.** They load the same server, so each becomes
the other's noise and neither result means anything. Run them back to back.

Each sweep writes `results/<stamp>-<scenario>.csv`, one row per level, alongside a
directory of per-second CPU samples. `results/` is git-ignored.

## Results

Measured 2026-08-06 to 2026-08-08 on the test deployment: Oracle `VM.Standard.A1.Flex`,
**4 OCPU / 16 GB ARM**, Caddy → nginx → gateway + visdom + Postgres, generator on the
same box. `visdom_cores` is the server process alone, read from `/proc` on the host;
`host_cores` is all four.

### 4a — concurrent writes, one shared workspace

`line`, `np.random.rand(200)`, 50 writes per writer:

| conc | thr/s | p50 | p95 | p99 | visdom_cores | host_cores |
|---|---|---|---|---|---|---|
| 1 | 225.3 | 3 | 3 | 15 | 0.12 | 1.41 |
| 5 | 536.6 | 8 | 10 | 23 | 0.37 | 2.06 |
| 10 | 577.6 | 14 | 23 | 42 | 0.45 | 2.18 |
| 25 | 573.2 | 37 | 47 | 109 | **0.95** | 2.75 |
| 50 | 564.2 | 78 | 114 | 160 | **0.98** | 2.91 |

**Throughput knees at conc≈10 and plateaus at ~575 writes/s.** Past the knee p50 grows
linearly (14 → 37 → 78 ms) with no throughput gain, which is queueing behind a serialized
resource and nothing else. visdom reaches 0.98 cores while the host sits at 2.91 of 4, so
the ceiling is one process on one core and a bigger VM buys nothing.

`image`, `np.random.rand(3, 256, 256)`:

| conc | thr/s | p50 | p95 | p99 | visdom_cores | bench_cores | host_cores |
|---|---|---|---|---|---|---|---|
| 1 | 45.6 | 20 | 26 | 34 | 0.10 | 0.03 | 1.53 |
| 5 | 153.4 | 26 | 43 | 49 | 0.49 | 2.96 | 3.80 |
| 10 | 169.8 | 55 | 78 | 111 | 0.47 | 3.17 | 3.99 |
| 25 | 173.3 | 138 | 199 | 270 | 0.50 | 3.24 | **4.00** |
| 50 | 168.7 | 283 | 432 | 534 | 0.51 | 3.36 | **4.00** |

**This is not a server capacity number.** visdom never passes 0.51 cores while the
generator uses 3.36 and the host pins at 4.00 — the client saturated the box and starved
the server. The cost is the PNG encode and base64 inside `vis.image()`, which is
client-side and per-call. **Do not quote 169/s as an image ceiling**; measuring it needs
a second machine, or a pre-encoded payload POSTed as raw HTTP.

### 4b — one workspace and one key per writer

Same load, but every writer pays a cold gateway resolve instead of sharing a cached one:

| conc | 4a thr/s | 4b thr/s | Δ | 4a p99 | 4b p99 | 4b visdom_cores |
|---|---|---|---|---|---|---|
| 1 | 225.3 | 227.2 | +0.8% | 15 | 7 | 0.12 |
| 5 | 536.6 | 483.9 | −9.8% | 23 | 21 | 0.34 |
| 10 | 577.6 | 550.2 | −4.7% | 42 | 35 | 0.47 |
| 25 | 573.2 | 548.0 | −4.4% | 109 | 118 | 0.96 |
| 50 | 564.2 | 521.8 | −7.5% | 160 | **244** | 0.96 |

**At this resolve-to-write ratio the auth path is not the bottleneck** — 5–8% throughput,
and visdom still pins one core. It shows up in the tail instead: p99 at conc=50 goes
160 → 244 ms, +52%, which is the blocking resolve stalling the event loop.

That result is bounded by its own ratio: each writer resolves once and then writes 50
times, so only ~2% of requests pay it. Measured directly on raw HTTP, one write to a
brand-new workspace costs **17.19 ms against a warm 1.55 ms — 11×**. Two blocking costs,
both on the event loop: the gateway resolve (~7.2 ms) and `WorkspaceEnvManager`'s
first-touch disk I/O. Space creation is permanent, so only the resolve recurs after the
45 s cache expires. **The impact of the synchronous resolve is set by how many writes follow
each resolve**, and a real workload that opens a client and trains for an hour looks like
4a, not like the cold case.

### Sharding — 4b across three instances (2026-08-09)

Same 4b load, but nginx consistent-hashes each workspace to one of three visdom
instances. `visdom_cores` is now the **sum across all three** processes.

| conc | 1 shard thr/s | 3 shard thr/s | Δ | 1 shard cores | 3 shard cores | host_cores |
|---|---|---|---|---|---|---|
| 1 | 227.2 | 229.5 | +1% | 0.12 | 0.17 | 1.55 |
| 5 | 483.9 | 560.7 | +16% | 0.34 | 0.50 | 2.35 |
| 10 | 550.2 | 715.5 | +30% | 0.47 | 0.54 | 2.49 |
| 25 | 548.0 | 720.4 | +31% | 0.96 | **1.52** | **4.00** |
| 50 | 521.8 | 743.4 | **+42%** | 0.96 | **1.51** | 3.99 |

**The shards do work in parallel, and that is the result.** A single Python process
cannot exceed 1.0 cores, so 1.51 is only reachable by more than one of them serving
simultaneously. Combined with `shardcheck.py` proving each workspace pins to one
instance, the design is confirmed: state stays partitioned *and* the work spreads.

**The shape changed too.** One shard peaked at conc=10 and then declined
(550 → 548 → 522) — queueing behind a serialized resource. Three shards rise all the way
to conc=50 (715 → 720 → 743) and are still climbing. The single-core ceiling is gone.

**+42% and not +200%, because the box is full, not because sharding underdelivers.**
`host_cores` hits 4.00 of 4 at conc=25 while the pool sits at 1.51 of a possible 3.0 —
visdom has headroom and no cores to spend it on. The load generator alone takes 1.76,
and gateway, Postgres and nginx want the rest. **Measuring the real ceiling of three
shards needs load generated from a second machine**; on this VM the generator and the
server are competing for the same four cores (trap 2).

Memory scales as expected: 418 MB resident across three instances against 139 MB for one.

### 5 — viewer fan-out

N subscribers on `main` in one workspace, one writer at 10 writes/s, 50 writes:

| Viewers | Broadcasts/s | Delivered | Drops | p50 | p95 | visdom_cores | bench_cores |
|---|---|---|---|---|---|---|---|
| 1 | 10 | 50 | 0% | 3.0 ms | 3.2 ms | 0.04 | 0.04 |
| 10 | 100 | 500 | 0% | 6.6 ms | 9.7 ms | 0.05 | 0.09 |
| 25 | 250 | 1,250 | 0% | 13.5 ms | 23.8 ms | 0.07 | 0.20 |
| 50 | 500 | 2,500 | 0% | 21.2 ms | 35.9 ms | 0.10 | 0.39 |
| 100 | 1,000 | 5,000 | 0% | 38.9 ms | 68.6 ms | 0.16 | 0.76 |
| 200 | 2,000 | 10,000 | 0% | 185.1 ms | 363.0 ms | **0.24** | **1.19** |

**Fan-out is not the ceiling, and it is not serialize-per-subscriber.** visdom serves
2,000 broadcasts/s at 0.24 cores with zero drops — roughly 5,000–8,000 broadcasts per
core, about 10× cheaper than a write. `register_window` runs `json.dumps` **once per
write** and `broadcast()` writes that same string to every subscriber.

**The latency growth above ~100 viewers is our load generator, not the server.** At 200
viewers the bench container used 1.19 cores against visdom's 0.24: 200 Python receiver
threads contending on the GIL to timestamp arrivals. **Do not quote the 185 ms p50 as a
server figure** — confirming real fan-out latency needs viewers spread across processes
or machines.

### 1 — login storm (2026-08-12)

Every login runs bcrypt at cost factor 12, which is a few hundred milliseconds of CPU by
design. The gateway does not shard and every visdom instance calls it, so if it saturates
first then adding visdom instances buys nothing. Arrival rate is held regardless of how
slow the server gets, so saturation shows as rising latency and dropped iterations rather
than as clients politely waiting.

| Peak rate | Requests | p50 | p95 | p99 | Dropped | gateway_cores_max |
|---|---|---|---|---|---|---|
| 12/s | 848 | 234 ms | 240 ms | 247 ms | 0 | **2.78** |
| 40/s | 1,039 | 238 ms | 3,525 ms | **31,339 ms** | **361** | — |

**The gateway keeps up to about 12 logins/s and falls over well before 40.** At 12/s
nothing is dropped and p99 is a quarter of a second; the p50 of 234 ms is essentially pure
bcrypt, with no queueing on top.

That p50 is also the capacity formula. One core does `1 / 0.235` ≈ **4.25 logins/s**, and
the gateway drew 2.78 cores at 12/s, which is what 12 / 4.25 predicts. Capacity is
therefore cores ÷ 235 ms, and on a box shared with visdom and Postgres that lands near 12.

Past the knee the failure is ugly rather than graceful: at 40/s a third of the attempts are
dropped outright and the unlucky ones wait half a minute. The gateway also stays slow for
minutes after the load stops, which is why the scenarios wait for it to settle.

**This is not a reason to weaken bcrypt.** 12 logins/s is 43,000 an hour, and logins are
bursty in a way that averages out: a thousand-person org all arriving over a ten minute
window is under 2/s. If it ever binds, the fix is more gateway processes, which works here
precisely because the gateway holds no per-request state.

### 2 — dashboard browse (2026-08-15)

What the console does when someone opens it and clicks around: `/auth/me`, the workspace
list, then members, keys and shared links inside one workspace. Five authenticated calls,
all reaching Postgres. Each is timed separately, because the useful answer is which call
to fix rather than "the dashboard is slow".

| Gateway workers | Browses | Throughput | seq p50 | seq p95 | Dropped | gateway_cores_max | host_cores_max |
|---|---|---|---|---|---|---|---|
| 1 | 2,446 | 13.1/s | 26.0 ms | 636 ms | **1,435** | 1.18 | 1.82 |
| 4 | 4,272 | **27.5/s** | 29.0 ms | **283 ms** | **3** | **2.65** | 4.00 |

**The gateway was running as a single uvicorn worker, so it hit exactly the same one-core
wall as visdom.** Nothing else was saturated when it did: at one worker the host was at
1.82 of 4 cores while a third of all browse attempts were dropped. That is the signature
of a single process, not a busy machine.

Four workers doubles throughput, cuts p95 by more than half, and takes dropped iterations
from 1,435 to 3. The pool drawing 2.65 cores is the proof it is real parallelism, since one
Python process cannot exceed 1.0.

**Unlike visdom this needed no sharding**, which is the whole point of the distinction. The
gateway keeps no per-request state, so any worker can answer any request and the kernel can
hand the connection to whichever is free. visdom cannot do that, which is why it needs a
consistent hash on the workspace and the gateway needs one line of config.

At four workers the host is full at 3.99 of 4.00, so 27.5/s is this box's limit rather than
the gateway's. No single endpoint stands out: all five sit between 29 and 54 ms at p95.

### 3 — cold visdom page load (2026-08-12)

A first-time visit with an empty browser cache: the auth check, the page, then all 19
assets it references. Each iteration also pays one uncached `/auth/verify`, which is
exactly the extra cost of shortening the nginx auth cache window.

| Peak rate | Loads | page p50 | page p95 | verify p50 | verify p95 | Dropped | visdom_cores_max | host_cores_max |
|---|---|---|---|---|---|---|---|---|
| 20/s | 854 | 21.5 ms | 27.6 ms | **2.4 ms** | 2.9 ms | 0 | 1.32 | 2.27 |
| 100/s | 3,276 | 164.7 ms | 884.4 ms | 87.8 ms | 5,133 ms | **998** | 2.25 | **4.00** |

**The auth check costs 2.4 ms, so the cache window dropped from 30 s to 5 s.** That window
is also how long a logged-out session keeps working, so shortening it closes the revocation
gap six times faster for a cost that does not register: 2.4 ms against a 21 ms page load,
on a gateway that never rose above 0.08 cores.

**Where it breaks is not the gateway.** At 100 loads/s the gateway sat at 0.08 cores while
the host was pegged at 4.00. The work is visdom serving 19 static files per load, plus the
load generator competing for the same four cores. Static assets are the one thing that
should never reach Tornado at all: they are identical on every instance, so nginx can serve
them directly and take the whole path off the shard.

### What this means in users

Concurrency in the tables above is *simultaneous in-flight writes*, which is not a user
count. A training script writes a plot every T seconds, so supportable runs ≈
throughput × T.

| Write cadence | 1 shard (522/s) | 3 shards (743/s) |
|---|---|---|
| Every 1s — very heavy | ~520 runs | ~740 runs |
| Every 5s — heavy | ~2,600 runs | ~3,700 runs |
| Every 10s — typical | ~5,200 runs | ~7,400 runs |
| Every 60s — per-epoch | ~31,000 runs | ~44,000 runs |

At 7,400 runs writing every 10s the average in-flight concurrency is ~72, which puts p95
around 100 ms — comfortably interactive.

**Viewers barely enter the budget.** 2,000 broadcasts/s costs 0.24 cores, so a few hundred
people watching plots live is noise next to the writes.

Three things this is not:

- **One training run per user.** Someone running ten jobs counts as ten.
- **Valid with the generator on the same box.** These figures assume load comes from
  elsewhere; here it was competing for the same four cores.
- **The whole platform.** Logins cap at ~12/s, dashboard browsing at ~27/s on four gateway
  workers, and cold page loads at ~20/s, all measured separately above.

### What this means for scaling

Sticky routing puts every viewer of a workspace on one instance by design, so fan-out
being cheap is what makes **sharding by workspace** viable: a single busy workspace is
not the constraint it was feared to be. The write path is the thing that pins a core, and
the only way past one core in one Python process is more processes. Swapping Tornado for
another framework does not change that — the multi-process story is the same, and the
state that would have to be split is the same.

### Caveats on all of the above

- Levels ran 0.2 s to 15.7 s, giving 3–19 CPU samples each. The high-concurrency line
  figures (0.95, 0.98) are trustworthy; the low-concurrency ones are diluted by the
  sampler's 2 s lead-in and should be read as "well under one core", not as exact.
- Except where stated, every run is warm-cache. The 4a, 4b and 5 figures were taken while
  the nginx auth gate cached for 30 s; it is 5 s now, which shortens the warm window but
  not the steady-state cost those runs measured.
- Specific to 4 OCPU ARM and to code that still has a synchronous gateway call on the
  event loop.
- The k6 scenarios seed accounts that survive between runs, so a rerun re-registers them
  and takes an expected 400 for each. The `errors` column counts workload failures only,
  which is why it reads 0 on a clean run rather than one per seeded user.

## What each scenario measures

**1** — logins are the most expensive thing the platform does per request, by design:
bcrypt at cost factor 12 is hundreds of milliseconds of CPU that cannot be cached away.
The gateway is also the only component that does not shard, so this asks whether the
front door binds before visdom does. An open load model is the point — arrival rate is
held whatever the server does, so the knee is visible instead of hidden behind clients
that slow down in sympathy.

**2** — the console's own read path, which is the gateway rather than visdom, and the one
component that does not shard. Five authenticated calls per iteration, each timed on its
own so the slow one is identifiable rather than averaged away.

**3** — a first visit with a cold browser cache, which is when the auth gate is felt: every
request under `/vis/` passes it. Each iteration also pays one uncached `/auth/verify`
straight to the gateway, so the run measures what a shorter cache window would cost while
the rest of the load is happening. Assets are read out of the served HTML rather than
hardcoded, so the run tracks whatever the visdom build actually ships, and dot segments are
resolved the way a browser resolves them before the request leaves.

**4a** — every writer shares one workspace and one key. After the first request the auth
caches are warm (nginx 5 s, `WorkspaceManager` 45 s), so the gateway is barely consulted.
That isolates plot serialization CPU, which is what "does visdom pin a core" asks.

**4b** — every writer gets its own workspace and its own key, so each pays a cold gateway
resolve: a synchronous `requests.post` on Tornado's event loop, plus a
first-touch `WorkspaceEnvManager._create_space` that does blocking disk I/O. **4a
throughput − 4b throughput at the same concurrency is the cost of the auth path**, and it
is the number that says whether §1c is worth fixing before anything else.

**5** — every write to a workspace is pushed to each subscribed socket, so one write with
N viewers is one store plus N sends. This is the path that decides whether sharding is the
right axis at all: sticky routing puts every viewer of a workspace on the same instance by
design, so if fan-out were expensive, a busy workspace would be capped by one core no
matter how many instances exist.

N subscribers attach to `main`, one writer sends at a fixed rate, and each subscriber
timestamps arrival. Writer and subscribers share a process, so the difference is real
delivery latency rather than a comparison across clocks. Writes go to `main` because
`broadcast()` only reaches subscribers whose `eid` matches the env being written, and a
freshly opened socket defaults to `main`. A plot broadcast arrives as `command: "window"`,
which is what distinguishes it from the `register`/`layout_update`/`env_update` messages a
socket gets on connect.

## Checking the sharding routes correctly

`shardcheck.py` runs as part of `--smoke`, or on its own:

```bash
docker compose --profile bench run --rm --no-deps -T \
  -e BENCH_SHARDS=3 bench python shardcheck.py
```

visdom keeps a workspace's envs and socket subscribers in one process's memory, so every
request touching a workspace has to reach the same instance. Two things can break that,
and **neither raises an error** — both present as a dashboard that silently never
updates, which is why this is a test rather than something you eyeball:

- **Affinity.** Browser sockets carry the slug in the path (`/vis/w/<slug>/socket`); the
  python client sends it as `X-Visdom-Workspace`. If those hash differently, a viewer
  subscribes on one instance while writes land on another. The check subscribes over the
  browser path, writes over the header path, and asserts the broadcast arrives.
- **Distribution.** If the key resolves empty for everything, every workspace lands on one
  instance — sharding "works" while buying nothing, and the affinity check alone still
  passes. The check probes many slugs and asserts each pins to one instance and that the
  pool is actually spread across.

Distribution reads nginx's `X-Visdom-Upstream` header, so it measures *routing* rather
than access and its slugs don't need to be workspaces that exist — a denied request is
still a routed request. Affinity does need a real workspace, since it has to observe a
broadcast.

| Knob | Default | Meaning |
|---|---|---|
| `BENCH_PROBES` | `24` | synthetic slugs for the distribution check |
| `BENCH_SHARDS` | `0` | instances expected in use; `0` reports without asserting |

`sweep.sh --smoke` derives `BENCH_SHARDS` by counting `server` entries in `.env`'s
`VISDOM_SERVERS`, so the check fails if the running pool and the proxy config have
drifted apart.

## Who creates the workspaces, and who removes them

`sweep.sh --fleet` does both, automatically:

1. **Before the sweep** — `fleet.py setup` logs in with `BENCH_EMAIL`/`BENCH_PASSWORD`,
   creates one workspace and one workspace-scoped key per writer (slugs `bench-0`,
   `bench-1`, …), and writes a manifest to `results/<stamp>-4b-fleet.json`.
2. **After the sweep** — an `EXIT` trap runs `fleet.py teardown`, which revokes every key
   and deletes every workspace. It fires on success, on failure, and on Ctrl-C.

Nothing is left behind in the normal case, and nothing touches your real workspaces —
only slugs starting with `$BENCH_PREFIX` (default `bench-`) are ever created or deleted.

If teardown is ever missed — the VM reboots mid-run, say — clean up by hand. This ignores
the manifest and finds everything by slug prefix:

```bash
cd ~/app/visdom-dev
docker compose --profile bench run --rm -T bench \
  python fleet.py teardown --prefix bench- --discover
```

A partial `setup` still prints its manifest, so a run that dies halfway is recoverable
rather than orphaned.

The client is installed from fossasia/visdom's `dev` branch, not PyPI, because `api_key=`
and `workspace=` are not in a visdom release yet. That also keeps
the client's auth protocol in step with the server it is measuring — **rebuild the bench
image whenever you rebuild visdom.** Pin a different commit with
`--build-arg VISDOM_REF=<sha>`.

It installs with `--no-deps`: `setup.py` declares the *server's* dependencies, and
openTSNE among them has no aarch64 wheel and needs a C++ toolchain the slim image lacks.
The client's hard imports are the four in `requirements.txt`; openTSNE sits behind a
`try/except ImportError` that only raises if `do_tsne()` is called, which the write path
never does. The build asserts the client imports and carries `api_key=`, so a wrong build
fails there rather than mid-benchmark.

Use a throwaway workspace (`loadtest`) so junk environments stay contained.

## Knobs

All environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `VISDOM_API_KEY` | — | required for 4a and 5; export it, never write it to a file |
| `BENCH_EMAIL`, `BENCH_PASSWORD` | — | required for `--fleet`; workspace creation needs a user session |
| `BENCH_WORKSPACE` | `loadtest` | workspace slug for 4a and 5 |
| `BENCH_PREFIX` | `bench-` | slug prefix for the 4b fleet |
| `BENCH_LEVELS` | `1 5 10 25 50` | writer concurrency levels (4a, 4b) |
| `BENCH_OPS` | `50` | writes per writer (4a, 4b) |
| `BENCH_KIND` | `line` | `line` or `image` (4a, 4b) |
| `BENCH_MODE` | `proc` | `proc` or `thread` (4a, 4b) |
| `BENCH_VIEWER_LEVELS` | `1 10 25 50 100 200` | subscriber counts to sweep (5) |
| `BENCH_WRITES` | `50` | writes the single writer sends (5) |
| `BENCH_RATE` | `10` | writes per second (5) |
| `BENCH_SETTLE` | `10` | seconds between levels |
| `BENCH_USERS` | per scenario | accounts the k6 scenarios seed (1: 20, 3: 10) |
| `BENCH_RATES` | per scenario | comma-separated arrival-rate stages (1: `1,2,4,6,8,12`, 3: `5,10,25,50,100`) |
| `BENCH_STAGE` | `30` | seconds per k6 stage |

The k6 defaults are deliberately different per scenario, because the useful range sits
either side of each measured ceiling. Leave them unset unless narrowing a run; the compose
service passes them through empty so each scenario's own defaults apply.

## Reading the output

The columns that answer the question are `visdom_cores_max`, `bench_cores_max` and
`host_cores_max`, next to `throughput` and `p95_ms`. For scenario 5 the equivalents are
`visdom_cores_max` next to `delivered`, `drop_pct` and `p95_ms`; **`drop_pct` above zero
means the server shed broadcasts and that level's latency figures understate the damage.**

- **`visdom_cores_max` ≈ 1.00 at high concurrency** — serialization on one core is the
  ceiling. Serialization is the bottleneck, sharding is the answer, a bigger VM buys nothing.
- **`visdom_cores_max` plateaus well under 1.0 while `p95_ms` climbs** — something else
  binds first, most likely the synchronous gateway call still on Tornado's event loop.
  Fix that before adding instances.
- **`host_cores_max` approaching 4.0** — the *box* saturated, not visdom. The knee is an
  artefact of the generator competing with the server; rerun with fewer levels or accept
  the ceiling as a host limit, and say so in the report.

The knee is the level where `throughput` stops rising while `p95_ms`/`p99_ms` keep
climbing. Below it you are adding parallelism; above it, only queue depth.

## Traps

Each of these has already cost one voided run:

1. **Any non-2xx voids the run.** `writebench.py` preflights for a 200 and aborts on the
   first failed write, so this should now be structurally impossible. A run of cached
   denials once reported 8671 req/s and measured nothing.
2. **Generate load on the VM, not a laptop.**
3. **A generator inside the visdom container inflates that container's `docker stats`.**
   This is why the `bench` container exists and why the sampler reads `/proc` directly.
4. **Caches flatten sustained runs** — nginx auth gate 5 s, `WorkspaceManager` 45 s. This
   measures steady-state serialization, not cold resolve.
5. **Payload type dominates plot count.** `line` is near best case; `image` is base64 and
   orders of magnitude heavier. The gap between the two is the most useful single number
   here.
6. **`docker compose` needs the project directory** — `sweep.sh` cds to the repo root
   itself, but a manual `docker compose` will not.

## Cleanup

**4a** leaves environments behind — one per writer per level (`sw1_0`, `sw5_0`…), 91 in
total for the default levels, all inside `loadtest`. Delete them from that workspace
afterwards and revoke the API key when done. They also accumulate *across* levels, so
conc=50 runs with 41 envs already resident; negligible for `line`, roughly 18 MB for
`image`, and worth a sentence in any report.

**4b** cleans up after itself — see "Who creates the workspaces" above.

**1 and 3** leave seeded accounts (`k6-login-*@example.com`, `k6-cold-*@example.com`) and
one workspace per cold-load session. They are reused on the next run rather than
re-created, so leaving them is the cheaper option; delete them when the deployment is meant
to look clean.

## Not here yet

All five scenarios are measured. The gap now is running the load generator from a separate
machine, so the saturation figures stop being pessimistic.
