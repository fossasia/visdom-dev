# Visdom Dev: tester quickstart

A hosted, multi-tenant visdom for live experiment visualization. Your training
code runs on **your** machine and streams plots to a shared server; you view them
in the browser. Everything is isolated per **workspace**.

## 1. Make an account + workspace
1. Open **https://visdom.dev** and **Register** (or log in).
2. Create a **workspace** and note its **slug** (e.g. `team-alpha`).

## 2. Get an API key
- In the console, open the **Keys & API** tab → **Generate**.
- Copy or download it now: it is shown only once. (Org-scoped works for any of
  your workspaces; workspace-scoped is bound to one.)

## 3. Install the client
The hosted server needs the client that sends your key + workspace. It is on the
`dev` branch of fossasia/visdom and not in a release yet. Install it into a fresh
virtualenv so it cannot clash with anything already on your machine:
```bash
python3 -m venv ~/.venvs/visdom-client
source ~/.venvs/visdom-client/bin/activate
python -m pip install "git+https://github.com/fossasia/visdom.git@dev"
```
> Plain `pip install visdom` will **not** work here: the released client has no
> key/workspace support.

> **Installed it before, from another branch or fork?** Activate the virtualenv first,
> as above, then reinstall into it:
> `python -m pip install --force-reinstall "git+https://github.com/fossasia/visdom.git@dev"`

Activate the virtualenv in every new terminal before running your training script,
otherwise `import visdom` finds whatever is installed system-wide instead.

## 4. Send some plots: this is how an "environment" is created
An **environment** is created automatically the first time you write to it. There
is no "new env" button and no server terminal: you just pass `env="<name>"` from
your own code.
```python
import visdom

vis = visdom.Visdom(
    server="https://visdom.dev", port=443, base_url="/vis",
    api_key="visdom_live_...",   # your key from step 2
    workspace="team-alpha",      # your workspace slug (required when a key is set)
)

# The env "experiment-1" is created in your workspace and plotted into:
for step, loss in enumerate([0.9, 0.6, 0.4, 0.25]):
    vis.line(X=[step], Y=[loss], win="loss", update="append",
             env="experiment-1", opts={"title": "training loss"})

vis.text("hello from my first run", env="experiment-1")
```

## 5. View them
Back in the console, pick your workspace and click **Visualizations**. You land in the
visdom UI at `/vis/w/team-alpha/`, and **experiment-1** appears in the environment
list, updating live. You only ever see your own workspace's environments.

## Troubleshooting
- **401 / "invalid key"**: key typo or it was revoked. Regenerate in the
  **Keys & API** tab.
- **402**: the workspace owner's plan is out of storage. Delete old environments,
  or move to a bigger plan in the **Billing** tab.
- **403**: you are not an active member of that workspace, the key is not scoped to
  it, or the workspace has been suspended.
- **"workspace is required"**: you set `api_key` but not `workspace`; add the slug.
- **Nothing shows in the UI**: confirm you opened *your* workspace's link
  (`/vis/w/<your-slug>/`) and that the script printed no errors.
- **Env in the wrong place**: the `workspace=` in your script must match the
  workspace you are viewing.

## Notes
- Use throwaway data and accounts during testing.
- One key can drive many environments: just write to different `env=` names.
- Environments older than your plan's retention period can be removed. The **History** section of the
  **Workspaces** tab says how long yours keeps them, and warns before anything goes.
