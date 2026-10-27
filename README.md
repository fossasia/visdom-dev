# Visdom Dev

Visdom Dev is the multi-tenant control plane for [Visdom](https://github.com/fossasia/visdom), the FOSSASIA visualization tool for live, rich experiment data. It adds the pieces a hosted, team-based Visdom deployment needs but the open-source visdom server doesn't provide on its own: user accounts, workspaces, role-based team access, shareable invite links, scoped API keys, plans and billing, all sitting in front of the existing visdom UI.

| Directory | What it is |
|---|---|
| `gateway/` | FastAPI backend. Accounts, workspaces, memberships, shared links, API keys, plans and limits, usage metering, retention, account deletion, and the staff console at `/admin/`. It also answers visdom's "who is this and which workspace" question. |
| `frontend/` | React + Vite console where people manage their account, workspaces and team. See [frontend/README.md](frontend/README.md). |
| `nginx/` | A reverse proxy config for running the pieces by hand on one machine. See [nginx/README.md](nginx/README.md). |
| `deploy/` | Everything the Docker stack needs beyond the compose file: the proxy image, its nginx template, the internal certificate script, backups, build cleanup and monitoring. |
| `bench/` | Load and capacity measurements. See [bench/README.md](bench/README.md). |

The visdom server itself lives in [fossasia/visdom](https://github.com/fossasia/visdom). Its `dev` branch has the workspace support this project relies on.

## Status

A test deployment runs at **[visdom.dev](https://visdom.dev)**, with the visdom server behind the same origin at `/vis/`. [TESTER_QUICKSTART.md](TESTER_QUICKSTART.md) walks through registering, making a workspace, and writing plots to it.

The project is under active development.

## Features

- Email/password accounts with short-lived JWT access tokens and rotating HTTP-only refresh cookies
- Password reset by emailed single-use link, password change, and a profile with plan, join date and last sign-in
- Workspaces with admin/member/viewer roles
- Two ways to add collaborators: direct email invites (the invitee must accept) and shareable join links (an admin must approve), both requiring explicit consent on both sides
- Invites work even for people who don't have an account yet: they're picked up automatically at registration
- API keys scoped to either an entire account or a hand-picked set of workspaces, with optional expiry
- Plans (Free, Pro, Enterprise) stored in the database, with limits on workspaces, members, API keys, storage and how long plot data is kept, enforced by the gateway
- Paid plans through Stripe, switched on by setting the Stripe keys; see [deploy/BILLING.md](deploy/BILLING.md)
- A Usage tab with active time and storage per workspace, from an hourly rollup of what the visdom instances report
- Old environments removed once they pass the plan's retention window, with a warning first (off until `RETENTION_ENFORCE` is set)
- People can delete their own account, with a 30 day waiting period that signing in cancels
- A staff console at `/admin/` with its own sign-in and roles: look up accounts and workspaces, suspend a workspace, manage memberships and staff, and read the audit trail
- Privacy and cookie policy pages
- A "Visualizations" link from the console into the visdom server, and a link back, with both on one origin and sharing the sign-in session



## Getting started

### Prerequisites

- Python 3.12 and Node.js 22, the versions in `.python-version` and `.nvmrc`
- A running PostgreSQL instance (for local development against SQLite, see Testing below)

### Backend (gateway)

```bash
cd gateway
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -c constraints.txt

cp .env.example .env
# edit .env: set DATABASE_URL to your local Postgres instance and a real JWT_SECRET

python run.py
```

The gateway starts on `http://localhost:8085` by default (configurable via `PORT` in `.env`). Apply the schema first with `alembic upgrade head`, and again after pulling changes that add a migration. The Docker image runs this on container start, so only local runs need it by hand.

### Frontend

```bash
cd frontend
npm install

cp .env.example .env
# edit .env if your gateway isn't running on the default port

npm run dev
```

The console starts on `http://localhost:5173` and proxies `/api` to the gateway and `/vis` to a visdom server on `http://localhost:8097`.

To run the console, gateway and visdom together on one origin by hand, see [nginx/README.md](nginx/README.md).

### The whole stack with Docker

`docker-compose.yml` runs Postgres, the gateway, three visdom instances and an nginx proxy that serves the built console. The visdom image is built from a checkout of [fossasia/visdom](https://github.com/fossasia/visdom) on its `dev` branch, by default one directory up (`VISDOM_CONTEXT=../visdom`).

```bash
git clone -b dev https://github.com/fossasia/visdom.git ../visdom
cp .env.docker.example .env
# edit .env: the Postgres password, JWT_SECRET, and the two VISDOM_INTERNAL_*_KEY values
deploy/internal-cert.sh new
docker compose up -d --build
```

Then open `http://localhost:8080`. Migrations run when the gateway starts.

The proxy speaks plain HTTP. On a public server put something that terminates HTTPS in front of it (the test deployment uses Caddy) and set `COOKIE_SECURE=True`.

More on running it:

| Doc | About |
|---|---|
| [deploy/INTERNAL.md](deploy/INTERNAL.md) | the port the gateway uses to talk to each visdom instance, its keys and certificate |
| [deploy/BILLING.md](deploy/BILLING.md) | setting up Stripe for paid plans |
| [deploy/BACKUPS.md](deploy/BACKUPS.md) | nightly backups to S3, and restoring |
| [deploy/CLEANUP.md](deploy/CLEANUP.md) | the weekly Docker build cleanup |
| [deploy/MONITORING.md](deploy/MONITORING.md) | health checks and what to do when one fails |

Optional settings in `.env`: `SMTP_*` and `MAIL_FROM` for sending email (without them nothing is sent: invites are only logged, and the forgot-password form says email is unavailable), `SUPPORT_CONTACT` for the contact button, and the `RETENTION_*` settings described in `.env.docker.example`.

### The staff console

The staff console at `/admin/` is off until `ADMIN_ENABLED=True` and `ADMIN_SECRET` is set. Staff accounts are separate from user accounts. Make the first one from inside the gateway container:

```bash
docker compose exec gateway python -m app.admin.bootstrap you@example.org superadmin
```

It asks for a password of at least 12 characters. The roles are `viewer`, `support`, `admin` and `superadmin`; a superadmin can add the rest from the console.

## Testing

The gateway's test suite runs against an in-memory SQLite database, so no Postgres instance or `.env` file is required to run it:

```bash
cd gateway
pip install -r requirements.txt -c constraints.txt
pytest tests/ -v
```

The frontend includes an automated test suite using Vitest and React Testing Library.

To run the frontend tests:

```bash
cd frontend
npm install
npm test
```

Use `npm run build` to check that the frontend builds successfully.

## Benchmarks

`bench/` measures how much load a single visdom instance can take, against a real deployment rather than a mock. How to run each scenario, the results so far, and what they mean for scaling are all in [bench/README.md](bench/README.md). The headline: one visdom process saturates one core at ~575 line writes/s while three of four cores sit idle, and viewer fan-out is cheap enough that sharding by workspace is the right way past it.

## Linting

```bash
# Backend
cd gateway
ruff check .

# Frontend
cd frontend
npm run lint
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on issues, pull requests, and running tests/linters before you submit one.

## License

This project is part of the FOSSASIA Visdom ecosystem. Licensing will be finalized to match the upstream [visdom](https://github.com/fossasia/visdom) project.
