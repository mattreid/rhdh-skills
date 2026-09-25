#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Plan and apply RHDH Jira component changes and catalog updates."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from _auth import JiraAuth, add_deployment_arguments, resolve_jira_auth  # noqa: E402
from _catalog import (  # noqa: E402
    CONFIGURED_CATEGORY_KEYS,
    CatalogEntry,
    catalog_by_name,
    load_catalog,
    remove_catalog_row,
    resolve_fields_md,
    upsert_catalog_row,
)
from _components_core import (  # noqa: E402
    CATALOG_OPERATION_KINDS,
    DEFAULT_ASSIGNEE_TYPE,
    PROJECTS_ALL,
    VALID_ASSIGNEE_TYPES,
    compose_apply_reminder,
    enrich_plan_response,
    index_by_name,
    team_catalog_publish_after_apply,
)
from _manage_core import (  # noqa: E402
    EnsureValidationError,
    build_delete_plan,
    build_ensure_plan,
    build_rename_plan,
    ensure_validation_failure_payload,
    resolve_ensure_inputs,
)
from _manage_core import catalog_entry_from_dict as entry_from_plan  # noqa: E402
from _users import resolve_lead  # noqa: E402

API_BASE = "/rest/api/3"


class JiraComponentClient:
    def __init__(self, auth: JiraAuth) -> None:
        self.auth = auth
        credentials = f"{auth.login}:{auth.token}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        self._headers = {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> Any:
        url = f"{self.auth.server}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
                if not body:
                    return None
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Jira HTTP {exc.code} {method} {path}: {detail}") from exc

    def list_components(self, project_key: str) -> list[dict[str, Any]]:
        result = self._request("GET", f"{API_BASE}/project/{project_key}/components")
        return result if isinstance(result, list) else []

    def check_access(self) -> dict[str, Any]:
        projects: dict[str, Any] = {}
        access_ok = True
        for key in PROJECTS_ALL:
            try:
                components = self.list_components(key)
                projects[key] = {"accessible": True, "count": len(components)}
            except RuntimeError as exc:
                access_ok = False
                projects[key] = {"accessible": False, "error": str(exc)}
        return {
            "access_ok": access_ok,
            "server": self.auth.server,
            "deployment": self.auth.deployment,
            "auth_source": self.auth.auth_source,
            "projects": projects,
        }

    def create_component(
        self,
        project: str,
        name: str,
        description: str,
        assignee_type: str,
        lead_account_id: str | None,
    ) -> dict[str, Any]:
        if not (description or "").strip():
            raise ValueError("description is required when creating a component")
        payload: dict[str, Any] = {
            "name": name,
            "project": project,
            "description": description.strip(),
        }
        if assignee_type:
            payload["assigneeType"] = assignee_type
        if lead_account_id:
            payload["leadAccountId"] = lead_account_id
        return self._request("POST", f"{API_BASE}/component", payload)

    def update_component(
        self,
        component_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        assignee_type: str | None = None,
        lead_account_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if assignee_type is not None:
            payload["assigneeType"] = assignee_type
        if lead_account_id is not None:
            payload["leadAccountId"] = lead_account_id
        return self._request("PUT", f"{API_BASE}/component/{component_id}", payload)

    def delete_component(self, component_id: str) -> None:
        self._request("DELETE", f"{API_BASE}/component/{component_id}")

    def issue_count(self, project: str, component_name: str) -> int:
        jql = f'project = {project} AND component = "{component_name}"'
        result = self._request(
            "POST",
            f"{API_BASE}/search/approximate-count",
            payload={"jql": jql},
        )
        if isinstance(result, dict):
            return int(result.get("count", 0))
        return 0


def fetch_all(client: JiraComponentClient) -> dict[str, dict[str, dict[str, Any]]]:
    by_project: dict[str, dict[str, dict[str, Any]]] = {}
    for project in PROJECTS_ALL:
        by_project[project] = index_by_name(client.list_components(project))
    return by_project


def apply_catalog_op(op: dict[str, Any]) -> dict[str, Any]:
    path = Path(op["fields_md"])
    text = path.read_text(encoding="utf-8")
    if op["op"] == "catalog_upsert":
        entry = entry_from_plan(op["entry"])
        new_text = upsert_catalog_row(text, entry)
    elif op["op"] == "catalog_rename":
        old = op["old_name"]
        new = op["new_name"]
        entries = load_catalog(text)
        by_name = catalog_by_name(entries)
        if old not in by_name:
            return {"ok": False, "error": f"{old} not in catalog"}
        entry = by_name[old]
        entry = CatalogEntry(
            name=new,
            description=entry.description,
            category=entry.category,
            excl_ff=entry.excl_ff,
            excl_cf=entry.excl_cf,
            excl_post_cf=entry.excl_post_cf,
            excl_rn=entry.excl_rn,
            section=entry.section,
        )
        text = remove_catalog_row(text, old)
        new_text = upsert_catalog_row(text, entry)
    elif op["op"] == "catalog_remove":
        new_text = remove_catalog_row(text, op["name"])
    else:
        return {"ok": False, "error": f"unknown catalog op {op['op']}"}
    path.write_text(new_text, encoding="utf-8")
    return {"ok": True, "path": str(path)}


def apply_plan(client: JiraComponentClient, plan: dict[str, Any]) -> dict[str, Any]:
    outcomes: list[dict[str, Any]] = []
    for op in plan.get("operations", []):
        kind = op.get("op")
        try:
            if kind == "create":
                created = client.create_component(
                    op["project"],
                    op["name"],
                    op["description"],
                    op.get("assigneeType") or DEFAULT_ASSIGNEE_TYPE,
                    op.get("leadAccountId"),
                )
                outcomes.append(
                    {"op": kind, "ok": True, "project": op["project"], "id": created.get("id")}
                )
            elif kind == "update":
                updated = client.update_component(
                    op["id"],
                    description=op.get("description"),
                    assignee_type=op.get("assigneeType"),
                    lead_account_id=op.get("leadAccountId"),
                )
                outcomes.append(
                    {"op": kind, "ok": True, "project": op["project"], "id": updated.get("id")}
                )
            elif kind == "rename":
                client.update_component(op["id"], name=op["new_name"])
                outcomes.append({"op": kind, "ok": True, "project": op["project"]})
            elif kind == "delete":
                client.delete_component(op["id"])
                outcomes.append({"op": kind, "ok": True, "project": op["project"]})
            elif kind in CATALOG_OPERATION_KINDS:
                outcomes.append({"op": kind, **apply_catalog_op(op)})
            else:
                outcomes.append({"op": kind, "ok": False, "error": "unknown op"})
        except RuntimeError as exc:
            outcomes.append({"op": kind, "ok": False, "error": str(exc)})
    ok = all(o.get("ok") for o in outcomes)
    result: dict[str, Any] = {"ok": ok, "outcomes": outcomes}
    catalog_paths = sorted(
        {
            o["path"]
            for o in outcomes
            if o.get("op") in CATALOG_OPERATION_KINDS and o.get("ok") and o.get("path")
        }
    )
    if catalog_paths:
        result["team_catalog_publish"] = team_catalog_publish_after_apply(catalog_paths)
        apply_reminder = compose_apply_reminder(True)
        if apply_reminder:
            result["reminder"] = apply_reminder
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage RHDH Jira components.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        help="JSON output (always emitted; flag accepted for parity with fixversions)",
    )
    common.add_argument("--fields-md", help="Path to fields.md catalog")
    add_deployment_arguments(common)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", parents=[common], help="Verify auth (same as audit skill)")

    ensure_p = sub.add_parser("ensure", parents=[common], help="Plan create/sync for one component")
    ensure_p.add_argument("name")
    ensure_p.add_argument(
        "--category",
        help=(
            "Required for new components. One of: "
            + ", ".join(CONFIGURED_CATEGORY_KEYS)
            + ". Determines expected Jira projects."
        ),
    )
    ensure_p.add_argument(
        "--description",
        default="",
        help=(
            "Non-empty catalog/Jira description. Required for new components; "
            "for existing rows omit to keep current text. Never invent — ask the human."
        ),
    )
    ensure_p.add_argument("--lead", help="Lead email, display name, or username")
    ensure_p.add_argument(
        "--assignee-type",
        default=DEFAULT_ASSIGNEE_TYPE,
        choices=VALID_ASSIGNEE_TYPES,
    )
    ensure_p.add_argument("--excl-ff", action=argparse.BooleanOptionalAction, default=None)
    ensure_p.add_argument("--excl-cf", action=argparse.BooleanOptionalAction, default=None)
    ensure_p.add_argument("--excl-post-cf", action=argparse.BooleanOptionalAction, default=None)
    ensure_p.add_argument("--excl-rn", action=argparse.BooleanOptionalAction, default=None)
    ensure_p.add_argument("--no-catalog", action="store_true")
    ensure_p.add_argument(
        "--plan-out",
        metavar="PATH",
        help="Write the plan JSON to PATH (same file apply --plan reads)",
    )

    rename_p = sub.add_parser(
        "rename", parents=[common], help="Plan rename across projects where present"
    )
    rename_p.add_argument("old_name")
    rename_p.add_argument("new_name")
    rename_p.add_argument("--plan-out", metavar="PATH", help="Write plan JSON for apply")

    delete_p = sub.add_parser(
        "delete", parents=[common], help="Plan delete when no issues reference component"
    )
    delete_p.add_argument("name")
    delete_p.add_argument("--plan-out", metavar="PATH", help="Write plan JSON for apply")

    apply_p = sub.add_parser("apply", parents=[common], help="Execute an approved plan file")
    apply_p.add_argument("--plan", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        auth = resolve_jira_auth(staging=args.staging)
    except RuntimeError as exc:
        print(json.dumps({"access_ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    client = JiraComponentClient(auth)

    if args.command == "check":
        result = client.check_access()
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "apply":
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        result = apply_plan(client, plan)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    fields_path = resolve_fields_md(getattr(args, "fields_md", None))
    fields_str = str(fields_path)
    by_project = fetch_all(client)

    if args.command == "ensure":
        catalog_entries = catalog_by_name(load_catalog(fields_path))
        existing_catalog = catalog_entries.get(args.name)
        try:
            category, description = resolve_ensure_inputs(
                args.category, args.description, existing_catalog
            )
        except EnsureValidationError as exc:
            print(json.dumps(ensure_validation_failure_payload(exc.errors)), file=sys.stderr)
            return 2
        lead_id = None
        if args.lead:
            resolved = resolve_lead(auth, client._headers, args.lead)
            if not resolved.get("ok"):
                print(json.dumps(resolved, indent=2))
                return 1
            lead_id = resolved["lead_account_id"]
        result = build_ensure_plan(
            args.name,
            category=category,
            description=description,
            lead_account_id=lead_id,
            assignee_type=args.assignee_type,
            by_project=by_project,
            fields_md=fields_str,
            existing_catalog=existing_catalog,
            excl_ff=args.excl_ff,
            excl_cf=args.excl_cf,
            excl_post_cf=args.excl_post_cf,
            excl_rn=args.excl_rn,
            update_catalog=not args.no_catalog,
        )
    elif args.command == "rename":
        result = build_rename_plan(
            args.old_name,
            args.new_name,
            by_project,
            fields_str,
        )
    elif args.command == "delete":
        projects = [p for p in PROJECTS_ALL if args.name in by_project.get(p, {})]
        counts = {p: client.issue_count(p, args.name) for p in projects}
        result = build_delete_plan(args.name, by_project, fields_str, counts)
        if not result.get("ok"):
            print(json.dumps(result, indent=2))
            return 1
    else:
        return 2

    result = enrich_plan_response(args.command, result)
    plan_out = getattr(args, "plan_out", None)
    if plan_out:
        out_path = Path(plan_out).expanduser()
        out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        result["plan_file"] = str(out_path.resolve())
        if result.get("has_changes"):
            result["next_steps"]["apply"] = (
                f"uv run scripts/components_manage.py apply --plan {result['plan_file']}"
            )

    print(json.dumps(result, indent=2))
    return 0 if result.get("has_changes", True) else 1


if __name__ == "__main__":
    sys.exit(main())
