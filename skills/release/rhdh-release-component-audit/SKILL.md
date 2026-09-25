---
name: rhdh-release-component-audit
description: >-
  Audits RHDH Jira components across RHDHPLAN, RHIDP, RHDHBUGS, and RHDHSUPP —
  lists live components, compares them to the component catalog in
  rhdh-jira-api fields.md, flags program components on bugs or support projects,
  and reports cross-project description drift. Use for "audit jira components",
  "component drift", "list components in RHIDP", "catalog out of sync with
  Jira", or "what was added manually in Jira". Read-only — creating or
  renaming components is /rhdh-release-component-manage.
compatibility: >-
  Python 3.9+ and uv; Jira REST via the invoker's API token (same as
  /rhdh-release-fixversions). Read access to all four project keys; fields.md
  catalog path via --fields-md, RHDH_JIRA_FIELDS_MD, or auto-discovery of
  installed /rhdh-jira-api. Compose with /rhdh-jira-api for field semantics.
---

# RHDH release component audit

Read-only inventory and drift detection for Jira components. Supersedes the old
Google Sheet + `jira_component_manager.py` audit flows for day-to-day release
management inside this skill pack.

Run from this skill's directory:

```bash
cd skills/release/rhdh-release-component-audit
uv run scripts/components_audit.py check --json
```

## Route

Load `workflows/audit-components.md` and `references/component-expectations.md`.

| Intent | CLI |
|---|---|
| Verify auth and project access | `uv run scripts/components_audit.py check --json` |
| List components | `uv run scripts/components_audit.py list --json` |
| List one project | add `--project RHIDP` |
| Cross-project description drift | `uv run scripts/components_audit.py diff --json` |
| Catalog + expectation violations | `uv run scripts/components_audit.py catalog-diff --json` |

For `catalog-diff`, the CLI resolves `references/fields.md` from `/rhdh-jira-api`
when that skill is installed (same host layouts as `/setup-rhdh-skills`), or from
this monorepo checkout. Override with `--fields-md` or `RHDH_JIRA_FIELDS_MD`.

Add **`--staging`** (or `JIRA_USE_STAGING=true`) with **`JIRA_STAGING_URL`** set;
use the same `JIRA_API_TOKEN` as production before running against production.
`check` JSON uses **`access_ok`** (and per-project **`accessible`**) for credentials
and list-components API access only — not catalog sync; use **`in_sync`** from
`catalog-diff`. Reports `deployment`: `staging` or `production`.

## Boundaries

- Mutations (create, rename, delete, catalog patch) are
  `/rhdh-release-component-manage` through `/mutation-gate`.
- Issue-level component fields are `/rhdh-jira-update`; field semantics and the
  catalog table live in `/rhdh-jira-api`.
- Rich Filter export setup is `/rhdh-release-status`; this skill does not edit
  filters.

## Completion

Complete when every named project was read for the requested command, the CLI
subcommand is cited, and catalog-diff reports `in_sync` or lists every violation
(missing catalog row, missing Jira component, forbidden program component on
RHDHBUGS/RHDHSUPP, cross-project description drift). A failed `check` names the
project and points to `/setup-rhdh-skills jira`.
