"""Parse and patch the Component Catalog in rhdh-jira-api fields.md."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

JIRA_API_SKILL = "rhdh-jira-api"
CATALOG_RELATIVE = Path("references") / "fields.md"
MONOREPO_CATALOG = Path("skills") / "reference" / JIRA_API_SKILL / CATALOG_RELATIVE
HOST_SKILL_LAYOUTS = (
    Path(".agents/skills"),
    Path(".claude/skills"),
    Path(".cursor/skills"),
    Path(".codex/skills"),
)

CATALOG_START = "### Component Catalog"
PRIORITIES_START = "## Priorities"

SECTION_RHDH_CORE = "RHDH Core"
SECTION_BACKSTAGE = "Backstage (upstream)"
SECTION_EXTENSION = "Extension Plugins"
SECTION_PROGRAM = "Program (non-engineering)"

SECTION_TO_CATEGORY: dict[str, str] = {
    SECTION_RHDH_CORE: "rhdh_core",
    SECTION_BACKSTAGE: "backstage",
    SECTION_EXTENSION: "extension_plugin",
    SECTION_PROGRAM: "program",
}

CATEGORY_TO_SECTION: dict[str, str] = {v: k for k, v in SECTION_TO_CATEGORY.items()}

CATEGORY_LABELS: dict[str, str] = {
    "rhdh_core": "RHDH Core",
    "backstage": "Backstage (upstream)",
    "extension_plugin": "Extension Plugins",
    "program": "Program (non-engineering)",
}

CONFIGURED_CATEGORY_KEYS: tuple[str, ...] = tuple(CATEGORY_TO_SECTION.keys())

_CATEGORY_ALIASES: dict[str, str] = {
    "rhdh_core": "rhdh_core",
    "core": "rhdh_core",
    "rhdh core": "rhdh_core",
    "backstage": "backstage",
    "backstage (upstream)": "backstage",
    "extension_plugin": "extension_plugin",
    "extension": "extension_plugin",
    "extension plugin": "extension_plugin",
    "extension plugins": "extension_plugin",
    "program": "program",
    "program (non-engineering)": "program",
}


def configured_categories_message() -> str:
    parts = [f"{key} ({CATEGORY_LABELS[key]})" for key in CONFIGURED_CATEGORY_KEYS]
    return ", ".join(parts)


def normalize_category(value: str) -> str:
    """Map CLI or sheet text to a configured category key."""
    key = _CATEGORY_ALIASES.get(value.strip().lower())
    if key and key in CONFIGURED_CATEGORY_KEYS:
        return key
    raise ValueError(
        f"Unknown category '{value}'. Configured categories: {configured_categories_message()}"
    )


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    description: str
    category: str
    excl_ff: bool
    excl_cf: bool
    excl_post_cf: bool
    excl_rn: bool
    section: str


def _yes(cell: str) -> bool:
    return cell.strip().lower() in ("yes", "y", "true", "1")


def _flag_cell(enabled: bool) -> str:
    return "Yes" if enabled else ""


def _parse_section_header(line: str) -> str | None:
    m = re.match(r"\*\*(.+?):\*\*\s*$", line.strip())
    if not m:
        return None
    title = m.group(1).strip()
    if title in SECTION_TO_CATEGORY:
        return title
    return None


def parse_catalog(text: str) -> list[CatalogEntry]:
    """Parse all component rows under ### Component Catalog."""
    entries: list[CatalogEntry] = []
    in_catalog = False
    current_section: str | None = None
    in_table = False

    for line in text.splitlines():
        if line.startswith(CATALOG_START):
            in_catalog = True
            continue
        if in_catalog and line.startswith("## ") and not line.startswith("### "):
            break
        if not in_catalog:
            continue

        section = _parse_section_header(line)
        if section:
            current_section = section
            in_table = False
            continue

        if line.startswith("|") and "---" in line:
            in_table = True
            continue
        if in_table and line.startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            if len(cells) < 8:
                continue
            name = cells[1]
            if not name or name == "Component":
                continue
            cat_key = SECTION_TO_CATEGORY.get(current_section or "", "")
            entries.append(
                CatalogEntry(
                    name=name,
                    description=cells[2],
                    category=cat_key or "",
                    excl_ff=_yes(cells[3]),
                    excl_cf=_yes(cells[4]),
                    excl_post_cf=_yes(cells[5]),
                    excl_rn=_yes(cells[6]),
                    section=current_section or "",
                )
            )
        elif in_table and not line.startswith("|"):
            in_table = False

    return entries


def load_catalog(path: Path) -> list[CatalogEntry]:
    return parse_catalog(path.read_text(encoding="utf-8"))


def catalog_by_name(entries: list[CatalogEntry]) -> dict[str, CatalogEntry]:
    return {e.name: e for e in entries}


def format_catalog_row(entry: CatalogEntry) -> str:
    return (
        f"| {entry.name} | {entry.description} | "
        f"{_flag_cell(entry.excl_ff)} | {_flag_cell(entry.excl_cf)} | "
        f"{_flag_cell(entry.excl_post_cf)} | {_flag_cell(entry.excl_rn)} |"
    )


def upsert_catalog_row(
    text: str,
    entry: CatalogEntry,
) -> str:
    """Insert or replace a component row in the correct category section."""
    lines = text.splitlines()
    section_header = f"**{CATEGORY_TO_SECTION[entry.category]}:**"
    row_line = format_catalog_row(entry)

    # Replace existing row anywhere in catalog
    name_pattern = re.compile(rf"^\|\s*{re.escape(entry.name)}\s*\|")
    out: list[str] = []
    replaced = False
    in_catalog = False
    for line in lines:
        if line.startswith(CATALOG_START):
            in_catalog = True
        if in_catalog and line.startswith("## ") and not line.startswith("### "):
            in_catalog = False
        if in_catalog and name_pattern.match(line):
            out.append(row_line)
            replaced = True
            continue
        out.append(line)

    if replaced:
        return "\n".join(out) + ("\n" if text.endswith("\n") else "")

    working = lines[:]
    for i, line in enumerate(working):
        if line.strip() != section_header:
            continue
        j = i + 1
        while j < len(working) and not working[j].startswith("|"):
            j += 1
        while j < len(working) and "---" not in working[j]:
            j += 1
        if j < len(working):
            working.insert(j + 1, row_line)
            return "\n".join(working) + ("\n" if text.endswith("\n") else "")

    raise ValueError(f"Could not find section {section_header} in catalog")


def remove_catalog_row(text: str, component_name: str) -> str:
    pattern = re.compile(rf"^\|\s*{re.escape(component_name)}\s*\|")
    lines = [ln for ln in text.splitlines() if not pattern.match(ln)]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def iter_catalog_names(entries: list[CatalogEntry]) -> Iterator[str]:
    for entry in entries:
        yield entry.name


def discover_fields_md(
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> Path | None:
    """Locate rhdh-jira-api references/fields.md (monorepo checkout or installed skill)."""
    cwd = cwd or Path.cwd()
    home = home or Path.home()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / MONOREPO_CATALOG
        if candidate.is_file():
            return candidate.resolve()
    for base in (cwd, home):
        for layout in HOST_SKILL_LAYOUTS:
            for skill_root in (
                base / layout / JIRA_API_SKILL,
                base / layout / "reference" / JIRA_API_SKILL,
            ):
                candidate = skill_root / CATALOG_RELATIVE
                if candidate.is_file():
                    return candidate.resolve()
    return None


def resolve_fields_md(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise SystemExit(f"fields.md not found: {path}")
        return path
    env = os.environ.get("RHDH_JIRA_FIELDS_MD", "").strip()
    if env:
        path = Path(env).expanduser()
        if path.is_file():
            return path
    discovered = discover_fields_md()
    if discovered:
        return discovered
    raise SystemExit(
        "Component catalog path required. Pass --fields-md PATH, set RHDH_JIRA_FIELDS_MD, "
        "or install /rhdh-jira-api so references/fields.md can be discovered."
    )
