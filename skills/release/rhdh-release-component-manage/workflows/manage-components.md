# Manage RHDH Jira components

```bash
cd skills/release/rhdh-release-component-manage
```

Ensure, rename, and delete resolve the catalog from installed `/rhdh-jira-api` or
this monorepo. Override with `RHDH_JIRA_FIELDS_MD` or `--fields-md` when needed.
`apply` needs no catalog path when the plan has only Jira REST operations.

Use `--staging` on every command (including `apply`) to target staging Jira.
`--staging` does **not** redirect catalog writes: `fields.md` on disk still
updates unless you pass **`--no-catalog`**. Prefer `--no-catalog` for
staging-only practice, or discard the catalog diff before any commit.

## 1. Plan create or sync

**Prompt for `--description` first** when the name is not in `fields.md`. Do not
invent catalog text. `--category` is also required for new names.

```bash
uv run scripts/components_manage.py ensure "New Capability" \
  --category rhdh_core \
  --description "Short catalog description from the human" \
  --excl-ff \
  --plan-out /tmp/component-plan.json \
  --json
```

Staging-only (no `fields.md` touch):

```bash
uv run scripts/components_manage.py ensure "New Capability" \
  --staging \
  --no-catalog \
  --category rhdh_core \
  --description "Short catalog description from the human" \
  --plan-out /tmp/component-plan.json \
  --json
```

`ensure`, `rename`, and `delete` only print a **plan**. Jira and `fields.md` stay
unchanged until `apply`. Every plan JSON includes **`reminder`**, **`has_changes`**, and
when non-empty **`next_steps`** (gate → save file → `apply --plan`). Prefer
**`--plan-out`** so `plan_file` and `next_steps.apply` name the real path.

Optional: `--lead user@redhat.com` (exact match required in plan JSON).

Program category creates on **RHDHPLAN** and **RHIDP** only. Other categories
target all four projects.

When `rich_filter_followup_required` is true — new or changed exclusion flags,
cleared flags (`--no-excl-ff`, etc.), or a rename — tell the human to update
Rich Filter `component not in (...)` clauses before trusting freeze dashboards.

**`team_catalog_publish`** (`fields_md`, `pending_apply`) flags catalog writes; the
single **`reminder`** covers gate/apply and the PR step when catalog ops are present.

## 2. Plan rename

Renames every project that currently has the component:

```bash
uv run scripts/components_manage.py rename "Old Label" "New Label" \
  --fields-md "$RHDH_JIRA_FIELDS_MD" --json
```

Remind about Rich Filter JQL that still references the old name.

## 3. Plan delete

```bash
uv run scripts/components_manage.py delete "Retired Thing" \
  --fields-md "$RHDH_JIRA_FIELDS_MD" --json
```

Blocked when any project still has issues with that component.

## 4. Gate and apply

Present the plan table through `/mutation-gate`. **Copy targets from the plan** —
use `expected_projects` and every `operations[]` entry as shown in the JSON
(or the `--plan-out` file). Do not invent, drop, or add projects. Gate the whole
document — not just `operations`.

```bash
uv run scripts/components_manage.py apply --plan /tmp/component-plan.json --json
```

Add `--staging` on `apply` when the plan was built with `--staging`.

## 5. Verify

```bash
cd ../rhdh-release-component-audit
uv run scripts/components_audit.py catalog-diff --json --fields-md "$RHDH_JIRA_FIELDS_MD"
```

## 6. Publish catalog for the team

When the approved plan included catalog operations (`catalog_upsert`, `catalog_rename`,
or `catalog_remove`), `apply` updated **`fields.md` on disk only**. Jira is live for
everyone; the shared catalog in git is not until it is merged.

If the catalog file on disk changed (see `team_catalog_publish.fields_md` in the apply
output), tell the operator to:

1. Review `git diff` on that file in their **rhdh-skills** clone.
2. Commit and **open a PR** to [redhat-developer/rhdh-skills](https://github.com/redhat-developer/rhdh-skills) so installs, agents, and `/rhdh-jira-api` stay aligned with Jira.

If `apply` patched a catalog file outside the clone they will commit (for example an
install-only copy), re-run `ensure` with `--plan-out` pointing at the clone, gate, and
`apply` again — or copy the catalog diff into the clone before the PR.

Skip this step when the plan used `--no-catalog` or had no catalog operations.

Successful `apply` JSON sets **`reminder`** (PR step only) when catalog ops ran, plus
**`team_catalog_publish`** with the `fields_md` path(s) written.
