# Jira component fields

| Field | Default | Notes |
|---|---|---|
| `name` | required | Must be unique per project |
| `description` | *(none — must be supplied)* | **Required on create** (new catalog row). Prompt the human; never invent or leave empty. Optional on update — omit to keep the current text. Same string for Jira and fields.md |
| `assigneeType` | `PROJECT_DEFAULT` | Override with `--assignee-type` when needed |
| `leadAccountId` | unset | Set via `--lead` resolved through user search |

Valid assignee types: `PROJECT_DEFAULT`, `PROJECT_LEAD`, `COMPONENT_LEAD`,
`UNASSIGNED`.

Lead resolution requires an **exact** match on display name, email, or username.
Ambiguous search results fail the plan so the gate never applies a wrong lead.

Catalog-only columns (not in Jira): **category** (required on create; one of
`rhdh_core`, `backstage`, `extension_plugin`, `program`), Excl FF, CF, Post CF,
Excl RN. Category drives which Jira projects the plan targets. Those columns are
written to fields.md in the same plan as Jira operations.

`apply` does not push to GitHub. After a successful catalog write, the release
manager should commit that `fields.md` and open a PR on rhdh-skills so the team
shares the table with Jira.
