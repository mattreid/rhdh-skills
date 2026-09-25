# Audit RHDH Jira components

Run from the directory that contains this skill's `SKILL.md`:

```bash
cd skills/release/rhdh-release-component-audit
```

`catalog-diff` finds `/rhdh-jira-api` `references/fields.md` when that skill is
installed or when you run from this monorepo. Override with `RHDH_JIRA_FIELDS_MD`
or `--fields-md` if discovery fails.

Use `--json` on every command. Add `--staging` when `JIRA_STAGING_URL` is set
(same `JIRA_API_TOKEN` as production), or set `JIRA_USE_STAGING=true`.

## 1. Capability check

```bash
uv run scripts/components_audit.py check --json
```

Stop when `access_ok` is false (credentials or project read access). Point to
`/setup-rhdh-skills jira`. Catalog health is `catalog-diff` → `in_sync`, not `check`.

## 2. List live components

```bash
uv run scripts/components_audit.py list --json
uv run scripts/components_audit.py list --json --project RHDHBUGS
```

## 3. Cross-project drift

```bash
uv run scripts/components_audit.py diff --json
```

Report components whose **description** differs between projects. Canonical
description for fixes is RHIDP, then RHDHPLAN.

## 4. Catalog and expectations

```bash
uv run scripts/components_audit.py catalog-diff --json --fields-md "$RHDH_JIRA_FIELDS_MD"
```

Interpret the JSON:

| Field | Meaning |
|---|---|
| `catalog_config_count` | Rows in the Component Catalog in fields.md |
| `live_union_count` | Distinct component names across all four Jira projects (union) |
| `missing_from_catalog_config` | In Jira but not in the Component Catalog in fields.md — often manual Jira adds |
| `missing_from_jira` | In the catalog but absent from every Jira project |
| `expectation_violations` | Wrong project for category (e.g. Program on RHDHBUGS) |
| `drift` | Same name, different descriptions across projects |

Program (non-engineering) components belong on **RHDHPLAN** and **RHIDP** only.
All other catalog categories should exist on all four keys.

## Handoffs

| Request | Skill |
|---|---|
| Create, rename, or delete a component | `/rhdh-release-component-manage` |
| Set component on an issue | `/rhdh-jira-update` |
| Update Rich Filter exclusions | Human Jira UI + `/rhdh-release-status` references |
