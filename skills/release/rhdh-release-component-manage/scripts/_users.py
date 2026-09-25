"""Resolve Jira users for component lead — strict matching for plans."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from _auth import JiraAuth

API_BASE = "/rest/api/3"


def _request(auth: JiraAuth, headers: dict[str, str], query: str) -> list[dict[str, Any]]:
    url = (
        f"{auth.server}{API_BASE}/user/search?"
        f"{urllib.parse.urlencode({'query': query, 'maxResults': '20'})}"
    )
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, list) else []
    except urllib.error.HTTPError:
        return []


def resolve_lead(
    auth: JiraAuth,
    headers: dict[str, str],
    user_input: str,
) -> dict[str, Any]:
    """
    Resolve lead to accountId. Requires exact match on display name, email, or username.
    """
    needle = user_input.strip()
    if not needle:
        return {"ok": False, "error": "empty lead identifier"}

    users = _request(auth, headers, needle)
    if not users and " " in needle:
        users = _request(auth, headers, needle.split()[0])

    if not users:
        return {"ok": False, "error": f"no Jira user found for '{needle}'"}

    lower = needle.lower()
    for user in users:
        display = (user.get("displayName") or "").lower()
        email = (user.get("emailAddress") or "").lower()
        username = (user.get("name") or "").lower()
        if lower in (display, email, username):
            account_id = user.get("accountId") or user.get("name")
            return {
                "ok": True,
                "lead_input": needle,
                "lead_account_id": account_id,
                "display_name": user.get("displayName"),
            }

    return {
        "ok": False,
        "error": f"ambiguous lead '{needle}' — refine to an exact email or display name",
        "candidates": [
            {
                "displayName": u.get("displayName"),
                "accountId": u.get("accountId"),
            }
            for u in users[:5]
        ],
    }
