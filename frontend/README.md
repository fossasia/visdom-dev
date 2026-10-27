# Visdom Dev console

The React + Vite single-page app people use to manage their account, workspaces
and team. It talks only to the gateway, under `/api/v1/`, and links into the
visdom server under `/vis/`.

## Running it

```bash
npm install
cp .env.example .env
npm run dev
```

It starts on `http://localhost:5173`. The dev server proxies `/api` to
`VITE_API_URL` (default `http://localhost:8085`, the gateway) and `/vis` to
`VITE_VISDOM_URL` (default `http://localhost:8097`, a visdom server), so
everything is one origin and the session cookies work as they do in production.

| Command | Does |
|---|---|
| `npm run dev` | dev server with hot reload |
| `npm test` | the Vitest suite, once |
| `npm run test:watch` | the suite, again on every change |
| `npm run lint` | ESLint |
| `npm run build` | the production build, into `dist/` |

In the Docker stack the console is not served by Vite: `deploy/proxy.Dockerfile`
builds it and nginx serves `dist/`.

## Where things are

| Path | Holds |
|---|---|
| `src/App.jsx` | the routes: sign-in, register, password reset, legal pages, join links, and the dashboard |
| `src/pages/` | one component per route; `Dashboard.jsx` holds the sidebar and the tabs |
| `src/components/workspace/` | the dashboard tabs (Workspaces, Members, Keys & API, Shared Links, Usage, Billing) and their modals and banners |
| `src/components/` | pieces used across pages: the profile modal, password field, modal frame, toasts |
| `src/context/` | `AuthContext` (the signed-in account, the axios client and token refresh) and `ConfirmContext` (confirm and prompt dialogs) |
| `src/utils/` | plain functions with no React in them, most with tests in `__tests__/` |
| `src/content/legal.js` | the text of the privacy and cookie pages |
| `src/css/` | the console's styles; class names start with `gc-` |

Tests sit next to the code in `__tests__/` folders and use React Testing Library.
