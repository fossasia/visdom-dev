# Contributing to Visdom Dev

We want to make contributing to this project as easy and transparent as possible.

Visdom Dev is the hosted control plane for [visdom](https://github.com/fossasia/visdom) — a FastAPI backend (`gateway/`) plus a React console (`frontend/`). Please keep in mind that, like visdom itself, this is a project maintained in contributors' spare time, so response times may vary.

## Guidelines for Contributors

### First-Time Contributors

If you are a first-time contributor, we highly recommend starting with beginner-friendly issues. Please avoid taking up tasks that involve large-scale file changes or major refactoring until you're familiar with the codebase — keeping your initial contributions focused and scoped will make the review process smoother.

### AI Usage Guidelines

We welcome the use of AI tools to assist in writing, debugging, or understanding code. However, you should only submit a pull request if:

1. You fully understand what your code changes do.
2. You understand and can explain every single line of the code changes you make.

Blindly copy-pasting AI-generated code that you cannot explain or debug is not permitted. As the contributor, you are responsible for the correctness and maintenance of the code you submit.

## Setup

See the [README](README.md#getting-started) for full instructions on setting up the gateway and frontend locally.

## Pull Requests

We actively welcome your pull requests.

1. Fork the repo and create your branch from `master`.
2. If you've added code that should be tested, add tests — new gateway endpoints and business logic should have pytest coverage under `gateway/tests/`.
3. If you've changed an API, update the relevant schema/docs.
4. Make sure your code lints and your tests pass (see below). CI runs the same checks automatically on every pull request and must be green before merging.
5. If you haven't already, complete the Contributor License Agreement ("CLA"), if one is required for this repository.

## Running Tests

The gateway's test suite runs against an in-memory SQLite database, so no PostgreSQL instance or `.env` file is needed:

```bash
cd gateway
pip install -r requirements.txt -c constraints.txt
pytest tests/ -v
```

The frontend does not yet have an automated test suite. For frontend changes, run a production build as a compile-correctness check:

```bash
cd frontend
npm install
npm run build
```

## Running the Linter

For Python files in `gateway/`, we use [ruff](https://docs.astral.sh/ruff/):

```bash
cd gateway
ruff check .
```

Some issues can be fixed automatically:

```bash
ruff check . --fix
```

For JavaScript/JSX files in `frontend/`, we use ESLint:

```bash
cd frontend
npm run lint
```

Both linters run automatically in CI (`.github/workflows/ci.yml`) on every pull request — running them locally first will save you a review round-trip.

## Coding Style

- Follow PEP 8 for Python; line length is capped at 120 characters (enforced by ruff, see `gateway/pyproject.toml`).
- Follow the existing ESLint configuration for JavaScript/JSX (`frontend/eslint.config.js`).
- Keep new code comment-free unless a comment explains a genuinely non-obvious constraint or workaround — well-named functions and variables should do most of the explaining.

## Issues

We use GitHub issues to track public bugs. Please ensure your description is clear and has sufficient instructions to reproduce the issue, including:

1. The error message produced by the gateway or frontend dev server (if any).
2. The error message produced by the browser's JavaScript console (if any).
3. The platform you're running on (OS, browser, Python/Node versions).

## License

By contributing to Visdom Dev, you agree that your contributions will be licensed under the same terms as the rest of this project.
