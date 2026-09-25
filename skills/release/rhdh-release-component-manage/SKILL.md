---
name: rhdh-release-component-manage
description: >-
  Creates, updates, renames, and deletes RHDH Jira components across
  RHDHPLAN, RHIDP, RHDHBUGS, and RHDHSUPP using the invoker's Jira credentials,
  and patches the component catalog in rhdh-jira-api fields.md (category and
  freeze exclusion columns). Use for "create jira component", "add component to
  RHIDP and RHDHPLAN", "rename component", "delete unused component", or
  "sync component catalog". Program components stay off RHDHBUGS and RHDHSUPP;
  renames apply on every project where the name exists. Requires Administer
  Projects; invoke /mutation-gate before apply.
compatibility: >-
  Python 3.9+ and uv; Jira REST via JIRA_EMAIL and JIRA_API_TOKEN (same as
  /rhdh-release-fixversions). Catalog path via --fields-md,
  RHDH_JIRA_FIELDS_MD, or auto-discovery of installed /rhdh-jira-api. Compose
  with /rhdh-jira-api for the canonical Component Catalog.
---

# RHDH release component manage

Plan-then-apply component changes for release managers. Replaces the local
`jira_component_manager.py` + Google Sheet workflow for mutations.

```bash
cd skills/release/rhdh-release-component-manage
uv run scripts/components_manage.py ensure "My Plugin" \
  --category rhdh_core \
  --description "One-line catalog text from the human" \
  --json
```

## Description (required on create)

**Never invent a component description.** Before `ensure` for a name that is not
yet in `fields.md`, **prompt the human** for a non-empty description and wait.
Pass it as `--description`. The same text lands in Jira and in the catalog row.
Empty creates are rejected. For an existing catalog row, omit `--description` to
keep the current text, or pass a new string the human supplied when updating.

## Route

Load `workflows/manage-components.md` and `references/component-jira-fields.md`.

| Intent | CLI |
|---|---|
| Plan create or align | `uv run scripts/components_manage.py ensure NAME --category C --description "…" --plan-out /tmp/component-plan.json` |
| Plan rename (all projects with the old name) | `uv run scripts/components_manage.py rename OLD NEW --plan-out /tmp/component-plan.json` |
| Plan delete (blocked if issues exist) | `uv run scripts/components_manage.py delete NAME --plan-out /tmp/component-plan.json` |
| Apply after `/mutation-gate` | `uv run scripts/components_manage.py apply --plan /tmp/component-plan.json` |

Plan commands do **not** mutate anything. JSON includes `reminder`, `has_changes`, and
`next_steps` (gate → save → `apply --plan`). Use **`--plan-out`** so `plan_file` points
at the file `apply` reads.

Category is **required** when the component is not yet in fields.md (`--category`).
Use a configured key: `rhdh_core`, `backstage`, `extension_plugin`, or `program`
(aliases such as `RHDH Core` or `extension plugins` are accepted). The category
sets `expected_projects` on the plan (all four keys, or RHIDP+RHDHPLAN only for
`program`). For an existing catalog row, omit `--category` to keep the current
section unless you are moving it.

Optional catalog flags on `ensure`: `--excl-ff`, `--no-excl-ff`, and the same
pattern for CF, Post CF, and Excl RN. Omitted flags keep the current catalog
values. The plan sets `rich_filter_followup_required` when any exclusion flag is
newly set, cleared, or changed (including edits to an existing row), and on
rename — then remind the human to update Rich Filter JQL (`/rhdh-release-status`).

## Jira field defaults

**`--description` is required** when the component is not in `fields.md` yet (same
rule as `--category`). Ask the human; do not draft one unprompted. For an existing
catalog row, omit it to keep the current text. Default assignee type is
`PROJECT_DEFAULT` (project default / effectively unassigned). Pass `--lead` with
an exact email or display name when a component lead is required; the plan
resolves to `leadAccountId`.

Use **`--staging`** on every command (including `apply`) when practicing against
staging Jira: set **`JIRA_STAGING_URL`** and reuse production
`JIRA_EMAIL`/`JIRA_API_TOKEN`. `JIRA_USE_STAGING=true` selects staging without
the flag.

**Staging does not isolate the catalog.** `--staging` only retargets Jira.
`ensure`/`apply` still patch the local `fields.md` unless you pass
**`--no-catalog`**. For staging-only drills use `--no-catalog`, or discard the
catalog diff afterward so it is never committed as a production change.

## Every mutation is an external write

Build a plan with `ensure`, `rename`, or `delete`. Pass the JSON through
`/mutation-gate`. **Build the gate table from the plan JSON** —
`expected_projects` and each entry in `operations` — never invent or trim the
project set. Write the approved plan to a temp file, then `apply`. Catalog
patches in the same plan are a second class of write — include them in the same
gate approval when the human accepts catalog updates.

Plan JSON includes one **`reminder`** (gate, apply, and PR when catalog ops exist)
and **`team_catalog_publish`** metadata (`fields_md`, `pending_apply`). Surface
`reminder` in the gate preview. After apply, `reminder` is only the PR step when
the catalog was patched.

Prefer planning against the **monorepo** `fields.md` path so `apply` edits the file
you will commit. After catalog writes, **nudge the operator** to open a PR on
rhdh-skills with that diff — local and installed copies are not team-visible until
merged.

## Boundaries

- Read-only audit and drift are `/rhdh-release-component-audit`.
- Fix versions are `/rhdh-release-fixversions`.
- Setting components on issues is `/rhdh-jira-update`.

## Completion

Complete when every operation in the approved plan has a reported outcome, any
`rich_filter_followup_required` flag was shown to the human, catalog-diff
(from the audit skill) is re-run when the user asked for end-to-end sync, and —
when the plan touched the catalog — the operator was reminded to **commit
`fields.md` and open a PR** for the team (see workflow step 6).
