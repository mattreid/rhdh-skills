#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Audit RHDH Jira components across four projects and against the component catalog."""

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
from _catalog import load_catalog, resolve_fields_md  # noqa: E402
from _components_core import (  # noqa: E402
    PROJECTS_ALL,
    catalog_diff_report,
    component_summary,
    cross_project_drift,
    index_by_name,
)

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
        if isinstance(result, list):
            return result
        return []

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


def fetch_all(client: JiraComponentClient) -> dict[str, dict[str, dict[str, Any]]]:
    by_project: dict[str, dict[str, dict[str, Any]]] = {}
    for project in PROJECTS_ALL:
        raw = client.list_components(project)
        by_project[project] = index_by_name(raw)
    return by_project


def cmd_check(client: JiraComponentClient) -> dict[str, Any]:
    return client.check_access()


def cmd_list(
    client: JiraComponentClient,
    *,
    project: str | None,
) -> dict[str, Any]:
    projects = [project] if project else list(PROJECTS_ALL)
    out: dict[str, Any] = {"projects": {}}
    for key in projects:
        raw = client.list_components(key)
        out["projects"][key] = [
            component_summary(c) for c in sorted(raw, key=lambda x: x.get("name", ""))
        ]
    return out


def cmd_catalog_diff(
    client: JiraComponentClient,
    fields_path: Path,
) -> dict[str, Any]:
    catalog = load_catalog(fields_path)
    by_project = fetch_all(client)
    report = catalog_diff_report(catalog, by_project)
    report["fields_md"] = str(fields_path)
    report["drift"] = cross_project_drift(by_project)
    return report


def cmd_diff(client: JiraComponentClient) -> dict[str, Any]:
    by_project = fetch_all(client)
    return {"drift": cross_project_drift(by_project)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit RHDH Jira components.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        help="JSON output (always emitted; flag accepted for parity with fixversions)",
    )
    common.add_argument(
        "--fields-md",
        help="Path to rhdh-jira-api references/fields.md (or set RHDH_JIRA_FIELDS_MD)",
    )
    add_deployment_arguments(common)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", parents=[common], help="Verify auth and project access")
    list_p = sub.add_parser("list", parents=[common], help="List components per project")
    list_p.add_argument("--project", choices=PROJECTS_ALL)
    sub.add_parser("diff", parents=[common], help="Cross-project description drift")
    sub.add_parser(
        "catalog-diff",
        parents=[common],
        help="Compare Jira to fields.md catalog and expectations",
    )
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
        result = cmd_check(client)
    elif args.command == "list":
        result = cmd_list(client, project=args.project)
    elif args.command == "diff":
        result = cmd_diff(client)
    elif args.command == "catalog-diff":
        fields_path = resolve_fields_md(args.fields_md)
        result = cmd_catalog_diff(client, fields_path)
    else:
        return 2

    print(json.dumps(result, indent=2))

    if args.command == "catalog-diff" and not result.get("in_sync", True):
        return 1
    if args.command == "check" and not result.get("access_ok", False):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
