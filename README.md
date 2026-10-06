# Visdom Dev

Visdom Dev is the multi-tenant control plane for [Visdom](https://github.com/fossasia/visdom), the FOSSASIA visualization tool for live, rich experiment data. It adds the pieces a hosted, team-based Visdom deployment needs but the open-source visdom server doesn't provide on its own: user accounts, workspaces, role-based team access, shareable invite links, scoped API keys, and billing — all sitting in front of the existing visdom UI.

The project is split into two services:

- **gateway/** — a FastAPI backend that owns authentication, workspaces, memberships, shared links, API keys, and billing.
- **frontend/** — a React + Vite console where users manage their account, workspaces, and team.

## Status

A live deployment runs at **[visdom.dev](https://visdom.dev)**, with the visdom server behind the same origin at `/vis/`. [TESTER_QUICKSTART.md](TESTER_QUICKSTART.md) walks through registering, making a workspace, and writing plots to it.

This project is under active development. Milestone 1 and Milestone 2 (auth, workspaces, roles, sharing, the console UI, and now automated tests + CI) are complete; Milestone 3 will connect this control plane to a workspace-aware visdom server behind a single reverse-proxied origin.

## Features

- Email/password authentication with short-lived JWT access tokens and rotating HTTP-only refresh cookies
- Workspaces with admin/member/viewer roles
- Two ways to add collaborators: direct email invites (the invitee must accept) and shareable join links (an admin must approve), both requiring explicit consent on both sides
- Invites work even for people who don't have an account yet — they're picked up automatically at registration
- API keys scoped to either an entire account or a hand-picked set of workspaces, with optional expiry
- A billing tab backed by a real plan/usage catalog (Free / Pro / Enterprise), with live plan switching — payment processing is not yet wired up
- A unified toast and confirm/prompt notification system shared visually with the upstream visdom project
- A "Visualizations" link from the console into the visdom server, and a link back, so the two apps can be navigated between today (a fully single-origin, session-sharing integration is planned for Milestone 3)



## Getting started

### Prerequisites

- Python 3.11+
- Node.js 20+
- A running PostgreSQL instance (for local development against SQLite, see Testing below)

### Backend (gateway)

```bash
cd gateway
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

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

The console starts on `http://localhost:5173` and proxies `/api` requests to the gateway.

## Testing

The gateway's test suite runs against an in-memory SQLite database, so no Postgres instance or `.env` file is required to run it:

```bash
cd gateway
pip install -r requirements.txt
pytest tests/ -v
```

The frontend does not yet have an automated test suite; `npm run build` is used as a compile-correctness check.

## Benchmarks

`bench/` measures how much load a single visdom instance can take, against a real deployment rather than a mock — how to run each scenario, the results so far, and what they mean for scaling are all in [bench/README.md](bench/README.md). The headline: one visdom process saturates one core at ~575 line writes/s while three of four cores sit idle, and viewer fan-out is cheap enough that sharding by workspace is the right way past it.

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

Contributions are welcome — see `CONTRIBUTING.md` for guidelines on issues, pull requests, and running tests/linters before you submit one.

## License

This project is part of the FOSSASIA Visdom ecosystem. Licensing will be finalized to match the upstream [visdom](https://github.com/fossasia/visdom) project.
