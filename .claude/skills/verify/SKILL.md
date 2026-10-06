---
name: verify
description: Run BBM's full check suite (Django tests, system check, migrations check, OpenAPI schema validation, frontend tests, lint, typecheck/build) and report results. Use after implementing a change and before telling the user it is ready to commit.
---

# Verify BBM

Run these from the repo root and report each result plainly (pass/fail with
the failing output). Don't claim success for a step you didn't run.

## Backend (Docker)

If `docker compose ps` shows the backend is not up, start it with
`docker compose up -d db redis backend` first. If it errors connecting to
Postgres right after a cold start, `docker compose restart backend`.

```bash
docker compose exec backend python manage.py check
docker compose exec backend python manage.py makemigrations --check --dry-run
docker compose exec backend python manage.py test
docker compose exec backend python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml
```

- `makemigrations --check` failing means a model change has no migration —
  tell the user; don't generate one without saying so.
- To narrow a failure, run one app or module, e.g.
  `docker compose exec backend python manage.py test inventory.tests.test_isolation`.

## Frontend

Only if anything under `frontend/` changed (check `git status`):

```bash
cd frontend && npm test && npm run lint && npm run build
```

## Report

Finish with a short table: step → pass/fail, plus test counts. Then list the
manual checks the user should do for this change (per CLAUDE.md: "tell me
what to test and how before I commit").
