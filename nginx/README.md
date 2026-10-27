# Nginx reverse proxy for local development

Collapses the three dev services behind a single origin so the console and visdom
share one session cookie: no CORS, no token hand-off.

This config is for running the pieces by hand on one machine. The Docker stack
uses its own, `deploy/nginx.conf.template`, which serves the built console and
spreads workspaces across several visdom instances.

| Path            | Upstream         | Port  |
| --------------- | ---------------- | ----- |
| `/`             | console frontend | 5173  |
| `/api/v1/*`     | console gateway  | 8085  |
| `/admin/*`      | staff console, in the gateway | 8085 |
| `/vis/w/<slug>/*` | visdom server, for that workspace | 8097 |
| `/vis/*`        | visdom server    | 8097  |

Unified origin: **http://localhost:8080**

`/vis/*` is gated by an nginx `auth_request` subrequest to
`GET /api/v1/auth/verify`, which checks the `session_token` cookie the gateway
sets at login and refresh, or an API key. Unauthenticated browser requests are
redirected to `/login`; API clients get a 401.

The visdom server needs `VISDOM_GATEWAY_URL=http://localhost:8085` in its
environment so it can ask the gateway which workspace a request belongs to.

## Run the stack

Four processes, in order:

```sh
# 1. gateway
cd gateway && .venv/bin/python run.py

# 2. visdom server, mounted under the /vis prefix so its routes line up
python -m visdom.server --port 8097 --base_url /vis

# 3. console frontend
cd frontend && npm run dev

# 4. nginx (install first: `brew install nginx`)
nginx -c "$(pwd)/nginx/visdom-dev.conf"
```

Validate the config before starting: `nginx -t -c "$(pwd)/nginx/visdom-dev.conf"`.
Reload after edits: `nginx -s reload`. Stop: `nginx -s stop`.

Then open http://localhost:8080.
