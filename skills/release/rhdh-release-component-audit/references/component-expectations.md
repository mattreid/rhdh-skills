# Component expectations by project

The component catalog in `/rhdh-jira-api` `references/fields.md` groups rows under
these section titles:

| Section in fields.md | Category key |
|---|---|
| RHDH Core | `rhdh_core` |
| Backstage (upstream) | `backstage` |
| Extension Plugins | `extension_plugin` |
| Program (non-engineering) | `program` |

## Project membership

| Category | RHDHPLAN | RHIDP | RHDHBUGS | RHDHSUPP |
|---|---|---|---|---|
| RHDH Core, Backstage, Extension Plugins | required | required | required | required |
| Program (non-engineering) | required | required | must be absent | must be absent |

Freeze columns (Excl FF, CF, Post CF, Excl RN) exist only in fields.md and in
Rich Filter JQL — not in Jira component records. When those flags are true,
release managers must update Rich Filter static filters; see
`/rhdh-release-status` `references/rich-filter-coverage.md`.
