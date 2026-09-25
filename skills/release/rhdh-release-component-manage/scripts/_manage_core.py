"""Plan component creates, updates, renames, and catalog patches."""

from __future__ import annotations

from typing import Any

from _catalog import (
    CATEGORY_LABELS,
    CONFIGURED_CATEGORY_KEYS,
    CatalogEntry,
    normalize_category,
)
from _components_core import (
    DEFAULT_ASSIGNEE_TYPE,
    component_summary,
    find_projects_with_name,
    merge_catalog_flags,
    projects_for_category,
    rich_filter_followup_for_catalog_change,
    rich_filter_reminder,
    team_catalog_publish_for_plan,
)


def build_ensure_plan(
    name: str,
    *,
    category: str,
    description: str | None,
    lead_account_id: str | None,
    assignee_type: str,
    by_project: dict[str, dict[str, dict[str, Any]]],
    fields_md: str,
    existing_catalog: CatalogEntry | None = None,
    excl_ff: bool | None = None,
    excl_cf: bool | None = None,
    excl_post_cf: bool | None = None,
    excl_rn: bool | None = None,
    update_catalog: bool = True,
) -> dict[str, Any]:
    if category not in CONFIGURED_CATEGORY_KEYS:
        raise ValueError(
            f"Invalid category '{category}'. Use one of: {', '.join(CONFIGURED_CATEGORY_KEYS)}"
        )
    if existing_catalog is None and not category:
        raise ValueError("category is required when creating a new catalog component")

    catalog_description = description
    if catalog_description is None and existing_catalog is not None:
        catalog_description = existing_catalog.description
    catalog_description = (catalog_description or "").strip()
    if not catalog_description:
        raise ValueError(
            "description is required for ensure (non-empty). "
            "Prompt the human; do not invent catalog text."
        )

    targets = projects_for_category(category)
    operations: list[dict[str, Any]] = []
    for project in targets:
        existing = by_project.get(project, {}).get(name)
        if existing is None:
            operations.append(
                {
                    "op": "create",
                    "project": project,
                    "name": name,
                    "description": catalog_description,
                    "assigneeType": assignee_type,
                    "leadAccountId": lead_account_id,
                }
            )
        else:
            current = component_summary(existing)
            updates: dict[str, Any] = {"op": "update", "project": project, "id": current["id"]}
            if description is not None and description != current["description"]:
                updates["description"] = description
            if lead_account_id and lead_account_id != current.get("lead"):
                updates["leadAccountId"] = lead_account_id
            if assignee_type != current.get("assigneeType", DEFAULT_ASSIGNEE_TYPE):
                updates["assigneeType"] = assignee_type
            if len(updates) > 3:
                operations.append(updates)

    flags = merge_catalog_flags(
        existing_catalog,
        {
            "excl_ff": excl_ff,
            "excl_cf": excl_cf,
            "excl_post_cf": excl_post_cf,
            "excl_rn": excl_rn,
        },
    )
    if update_catalog:
        operations.append(
            {
                "op": "catalog_upsert",
                "fields_md": fields_md,
                "entry": {
                    "name": name,
                    "description": catalog_description,
                    "category": category,
                    **flags,
                },
            }
        )

    followup = rich_filter_followup_for_catalog_change(existing_catalog, flags)
    plan: dict[str, Any] = {
        "component": name,
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "expected_projects": list(targets),
        "targets": list(targets),
        "operations": operations,
        "catalog_flags": flags,
        "catalog_flags_previous": (
            None
            if existing_catalog is None
            else {
                "excl_ff": existing_catalog.excl_ff,
                "excl_cf": existing_catalog.excl_cf,
                "excl_post_cf": existing_catalog.excl_post_cf,
                "excl_rn": existing_catalog.excl_rn,
            }
        ),
        "rich_filter_followup_required": followup,
        "rich_filter_message": rich_filter_reminder() if followup else None,
    }
    if update_catalog:
        plan["team_catalog_publish"] = team_catalog_publish_for_plan(fields_md)
    return plan


def build_rename_plan(
    old_name: str,
    new_name: str,
    by_project: dict[str, dict[str, dict[str, Any]]],
    fields_md: str,
    *,
    update_catalog: bool = True,
) -> dict[str, Any]:
    projects = find_projects_with_name(by_project, old_name)
    operations: list[dict[str, Any]] = []
    for project in projects:
        comp = by_project[project][old_name]
        operations.append(
            {
                "op": "rename",
                "project": project,
                "id": comp.get("id"),
                "old_name": old_name,
                "new_name": new_name,
            }
        )
    if update_catalog:
        operations.append(
            {
                "op": "catalog_rename",
                "fields_md": fields_md,
                "old_name": old_name,
                "new_name": new_name,
            }
        )
    plan: dict[str, Any] = {
        "old_name": old_name,
        "new_name": new_name,
        "projects": projects,
        "operations": operations,
        "rich_filter_followup_required": True,
        "rich_filter_message": (
            "Component renamed — update Rich Filter JQL that references the old name "
            "in component not in (...) / component in (...) clauses. "
            "See /rhdh-release-status rich-filter references."
        ),
    }
    if update_catalog:
        plan["team_catalog_publish"] = team_catalog_publish_for_plan(fields_md)
    return plan


def build_delete_plan(
    name: str,
    by_project: dict[str, dict[str, dict[str, Any]]],
    fields_md: str,
    issue_counts: dict[str, int],
    *,
    update_catalog: bool = True,
) -> dict[str, Any]:
    projects = find_projects_with_name(by_project, name)
    blockers = [p for p in projects if issue_counts.get(p, 0) > 0]
    if blockers:
        return {
            "ok": False,
            "error": "component has open issues",
            "component": name,
            "issue_counts": issue_counts,
            "blocked_projects": blockers,
        }
    operations: list[dict[str, Any]] = []
    for project in projects:
        comp = by_project[project][name]
        operations.append(
            {
                "op": "delete",
                "project": project,
                "id": comp.get("id"),
                "name": name,
            }
        )
    if update_catalog:
        operations.append(
            {"op": "catalog_remove", "fields_md": fields_md, "name": name},
        )
    plan: dict[str, Any] = {
        "ok": True,
        "component": name,
        "projects": projects,
        "operations": operations,
    }
    if update_catalog:
        plan["team_catalog_publish"] = team_catalog_publish_for_plan(fields_md)
    return plan


class EnsureValidationError(Exception):
    """One or more ensure argument errors (report all at once)."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def collect_ensure_validation_errors(
    cli_category: str | None,
    cli_description: str,
    existing_catalog: CatalogEntry | None,
) -> list[str]:
    errors: list[str] = []
    stripped_description = (cli_description or "").strip()

    if existing_catalog is None:
        if not cli_category:
            errors.append("--category is required for new components (not in fields.md).")
        else:
            try:
                normalize_category(cli_category)
            except ValueError as exc:
                errors.append(str(exc))
        if not stripped_description:
            errors.append(
                "--description is required for new components (not in fields.md). "
                "Ask the human for the catalog text; do not invent it."
            )
        return errors

    if cli_category:
        try:
            normalize_category(cli_category)
        except ValueError as exc:
            errors.append(str(exc))
    elif existing_catalog.category not in CONFIGURED_CATEGORY_KEYS:
        errors.append("pass --category; existing catalog row has no valid category.")
    return errors


def ensure_validation_failure_payload(errors: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "errors": errors}
    if any("category" in item.lower() for item in errors):
        payload["configured_categories"] = list(CONFIGURED_CATEGORY_KEYS)
    return payload


def resolve_ensure_inputs(
    cli_category: str | None,
    cli_description: str,
    existing_catalog: CatalogEntry | None,
) -> tuple[str, str | None]:
    errors = collect_ensure_validation_errors(cli_category, cli_description, existing_catalog)
    if errors:
        raise EnsureValidationError(errors)

    stripped_description = (cli_description or "").strip()
    if existing_catalog is None:
        assert cli_category is not None
        return normalize_category(cli_category), stripped_description

    category = normalize_category(cli_category) if cli_category else existing_catalog.category
    description = stripped_description if stripped_description else None
    return category, description


def catalog_entry_from_dict(data: dict[str, Any]) -> CatalogEntry:
    from _catalog import CATEGORY_TO_SECTION

    category = data["category"]
    return CatalogEntry(
        name=data["name"],
        description=data.get("description") or "",
        category=category,
        excl_ff=bool(data.get("excl_ff")),
        excl_cf=bool(data.get("excl_cf")),
        excl_post_cf=bool(data.get("excl_post_cf")),
        excl_rn=bool(data.get("excl_rn")),
        section=CATEGORY_TO_SECTION[category],
    )
