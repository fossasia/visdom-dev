# Gateway dependencies

Two files, on purpose.

- `requirements.txt` says what the gateway needs, as ranges.
- `constraints.txt` says exactly which version of everything gets installed,
  including what those packages pull in.

The image and CI both install with `pip install -r requirements.txt -c
constraints.txt`, so a rebuild installs the same versions every time. Before
this, a rebuild took whatever was newest, and two releases broke the gateway
without any change on our side (SQLAlchemy 2.1 and anyio 4.15).

## Moving to newer versions

Do it deliberately, in its own pull request.

```bash
cd gateway
python3.12 -m venv /tmp/fresh && /tmp/fresh/bin/pip install -r requirements.txt
/tmp/fresh/bin/pip freeze > constraints.txt
```

That takes the newest versions the ranges in `requirements.txt` allow. Read
the diff, let CI run, and deploy it like any other change. To move one package
only, edit its line in `constraints.txt`.

## Adding a package

Add it to `requirements.txt`, install it, and add its line (and the lines of
anything new it pulled in) to `constraints.txt`. A package that is in
`requirements.txt` but not in `constraints.txt` still installs, at whatever
version is newest, which is the thing this file exists to stop.

## Python and Node versions

`.python-version` and `.nvmrc` at the top of the repository say which Python
and Node every CI job runs. The Dockerfiles cannot read those files, so their
`FROM` lines name the same versions. Change them together.
