"""Pure component audit logic — no HTTP, no credentials."""

from __future__ import annotations

from typing import Any

from _catalog import CATEGORY_LABELS, CatalogEntry

PROJECTS_ALL = ("RHIDP", "RHDHPLAN", "RHDHBUGS", "RHDHSUPP")
CANONICAL_ORDER = ("RHIDP", "RHDHPLAN", "RHDHBUGS", "RHDHSUPP")
PROGRAM_CATEGORY = "program"
DEFAULT_ASSIGNEE_TYPE = "PROJECT_DEFAULT"
VALID_ASSIGNEE_TYPES = (
    "PROJECT_DEFAULT",
    "PROJECT_LEAD",
    "COMPONENT_LEAD",
    "UNASSIGNED",
)


def projects_for_category(category: str) -> tuple[str, ...]:
    if category == PROGRAM_CATEGORY:
        return ("RHIDP", "RHDHPLAN")
    return PROJECTS_ALL


def category_allowed_on_project(category: str, project: str) -> bool:
    if category == PROGRAM_CATEGORY and project in ("RHDHBUGS", "RHDHSUPP"):
        return False
    return True


def component_summary(component: dict[str, Any]) -> dict[str, Any]:
    lead = component.get("lead") or {}
    lead_id = None
    if isinstance(lead, dict):
        lead_id = lead.get("accountId") or lead.get("name")
    lead_id = lead_id or component.get("leadAccountId") or component.get("leadUserName")
    return {
        "id": component.get("id"),
        "name": component.get("name", ""),
        "description": (component.get("description") or "").strip(),
        "assigneeType": component.get("assigneeType") or DEFAULT_ASSIGNEE_TYPE,
        "lead": lead_id,
    }


def index_by_name(components: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in components if c.get("name")}


def find_projects_with_name(
    by_project: dict[str, dict[str, dict[str, Any]]],
    name: str,
) -> list[str]:
    return [p for p in PROJECTS_ALL if name in by_project.get(p, {})]


EXCLUSION_FLAG_KEYS = ("excl_ff", "excl_cf", "excl_post_cf", "excl_rn")


def flags_from_catalog_entry(entry: CatalogEntry | None) -> dict[str, bool]:
    if entry is None:
        return dict.fromkeys(EXCLUSION_FLAG_KEYS, False)
    return {
        "excl_ff": entry.excl_ff,
        "excl_cf": entry.excl_cf,
        "excl_post_cf": entry.excl_post_cf,
        "excl_rn": entry.excl_rn,
    }


def merge_catalog_flags(
    existing: CatalogEntry | None,
    overrides: dict[str, bool | None],
) -> dict[str, bool]:
    """Apply CLI overrides; None means leave the catalog value unchanged."""
    merged = flags_from_catalog_entry(existing)
    for key in EXCLUSION_FLAG_KEYS:
        value = overrides.get(key)
        if value is not None:
            merged[key] = value
    return merged


def rich_filter_followup(flags: dict[str, bool]) -> bool:
    return any(flags.get(k) for k in EXCLUSION_FLAG_KEYS)


def rich_filter_followup_for_catalog_change(
    existing: CatalogEntry | None,
    new_flags: dict[str, bool],
) -> bool:
    """True when exclusion flags are newly set or any flag was added/removed/changed."""
    old_flags = flags_from_catalog_entry(existing)
    if existing is None:
        return rich_filter_followup(new_flags)
    return any(old_flags[key] != new_flags[key] for key in EXCLUSION_FLAG_KEYS)


def rich_filter_reminder() -> str:
    return (
        "Exclusion flags (Excl FF, CF, Post CF, Excl RN) were set, cleared, or changed "
        "in the component catalog. Update the RHIDP Operational Rich Filter in Jira so "
        "component exclusion clauses match — Feature Freeze, Code Freeze, Post Code "
        "Freeze, and release-note filters use component not in (...). "
        "Rich Filter export setup and coverage are owned by /rhdh-release-status "
        "(references/config.md and references/rich-filter-coverage.md). "
        "Refresh the local Rich Filter export after Jira UI edits if you rely on "
        "release.py rich-filter inventory."
    )


def catalog_diff_report(
    catalog: list[CatalogEntry],
    by_project: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    documented = {e.name for e in catalog}
    live_union: set[str] = set()
    per_project: dict[str, set[str]] = {}
    for project in PROJECTS_ALL:
        names = set(by_project.get(project, {}))
        per_project[project] = names
        live_union |= names

    missing_from_catalog_config = sorted(live_union - documented)
    missing_from_jira = sorted(documented - live_union)

    expectation_violations: list[dict[str, str]] = []
    for entry in catalog:
        targets = projects_for_category(entry.category)
        for project in PROJECTS_ALL:
            present = entry.name in per_project.get(project, set())
            if project in targets and not present:
                expectation_violations.append(
                    {
                        "component": entry.name,
                        "project": project,
                        "issue": "missing_expected",
                        "category": entry.category,
                    }
                )
            if not category_allowed_on_project(entry.category, project) and present:
                expectation_violations.append(
                    {
                        "component": entry.name,
                        "project": project,
                        "issue": "forbidden_category",
                        "category": entry.category,
                    }
                )

    not_in_catalog_config: list[dict[str, Any]] = []
    for name in missing_from_catalog_config:
        not_in_catalog_config.append(
            {
                "name": name,
                "projects": sorted(find_projects_with_name(by_project, name)),
            }
        )

    return {
        "catalog_config_count": len(documented),
        "live_union_count": len(live_union),
        "per_project_counts": {p: len(per_project[p]) for p in PROJECTS_ALL},
        "missing_from_catalog_config": not_in_catalog_config,
        "missing_from_jira": missing_from_jira,
        "expectation_violations": expectation_violations,
        "in_sync": not (missing_from_catalog_config or missing_from_jira or expectation_violations),
    }


def cross_project_drift(
    by_project: dict[str, dict[str, dict[str, Any]]],
    *,
    names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Flag same component name with differing description across projects."""
    if names is None:
        names = set()
        for project in PROJECTS_ALL:
            names |= set(by_project.get(project, {}))

    drifts: list[dict[str, Any]] = []
    for name in sorted(names):
        projects = find_projects_with_name(by_project, name)
        if len(projects) < 2:
            continue
        descriptions: dict[str, str] = {}
        for project in projects:
            raw = by_project[project][name]
            descriptions[project] = component_summary(raw)["description"]
        unique = set(descriptions.values())
        if len(unique) > 1:
            drifts.append(
                {
                    "name": name,
                    "projects": projects,
                    "descriptions": descriptions,
                    "canonical_project": CANONICAL_ORDER[0]
                    if CANONICAL_ORDER[0] in projects
                    else projects[0],
                }
            )
    return drifts


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category)


CATALOG_OPERATION_KINDS = frozenset(
    {
        "catalog_upsert",
        "catalog_rename",
        "catalog_remove",
    }
)

PR_PUBLISH_SUFFIX = (
    "After apply, commit fields.md and open a PR on redhat-developer/rhdh-skills "
    "so the team shares the catalog with Jira."
)

PLAN_COMMANDS = frozenset({"ensure", "rename", "delete"})

PLAN_NO_OPERATIONS_REMINDER = (
    "This plan has no operations. Nothing would change in Jira or fields.md; "
    "there is nothing to gate or apply."
)


def team_catalog_publish_for_plan(fields_md: str) -> dict[str, Any]:
    return {
        "fields_md": fields_md,
        "pending_apply": True,
    }


def team_catalog_publish_after_apply(paths: list[str]) -> dict[str, Any]:
    return {
        "fields_md": paths,
        "pending_apply": False,
    }


def plan_includes_catalog_write(operations: list[dict[str, Any]]) -> bool:
    return any(op.get("op") in CATALOG_OPERATION_KINDS for op in operations)


def compose_plan_reminder(has_changes: bool, includes_catalog: bool) -> str:
    if not has_changes:
        return PLAN_NO_OPERATIONS_REMINDER
    text = (
        "Plan only: Jira and fields.md are unchanged until /mutation-gate approval "
        "and apply --plan PATH."
    )
    if includes_catalog:
        text += f" {PR_PUBLISH_SUFFIX}"
    return text


def compose_apply_reminder(includes_catalog: bool) -> str | None:
    if not includes_catalog:
        return None
    return PR_PUBLISH_SUFFIX


def enrich_plan_response(command: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Attach apply workflow hints to ensure/rename/delete JSON (stdout only)."""
    if command not in PLAN_COMMANDS:
        return plan
    if plan.get("ok") is False:
        blocked = dict(plan)
        blocked["applied"] = False
        blocked["has_changes"] = False
        blocked["reminder"] = "No changes were made."
        return blocked

    operations = plan.get("operations", [])
    has_changes = len(operations) > 0
    enriched: dict[str, Any] = {
        "plan_kind": command,
        "applied": False,
        "has_changes": has_changes,
        "operation_count": len(operations),
        **plan,
    }
    if has_changes:
        enriched["reminder"] = compose_plan_reminder(True, plan_includes_catalog_write(operations))
        enriched["next_steps"] = {
            "mutation_gate": "Present operations through /mutation-gate and get approval.",
            "save_plan": (
                "Write this entire JSON document to a file, for example "
                "/tmp/component-plan.json (or pass --plan-out on the CLI)."
            ),
            "apply": ("uv run scripts/components_manage.py apply --plan /tmp/component-plan.json"),
        }
    else:
        enriched["reminder"] = PLAN_NO_OPERATIONS_REMINDER
    return enriched
