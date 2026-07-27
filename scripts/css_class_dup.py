# -*- coding: utf-8 -*-
"""theme.css vs components+tokens class-name intersection (S7 / 2.6.9).

Analysis helper under scripts/ (not product src/). Shared by inventory CLI
and tests/test_css_no_dup_classes.py.

Class name = ``.name`` after start/combinator/whitespace/comma/brace/pipe
(not chained ``.foo.bar`` or ``button.foo``).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
THEME_CSS = ROOT / "static" / "css" / "theme.css"
COMPONENTS_DIR = ROOT / "frontend" / "src" / "styles" / "components"
TOKENS_CSS = ROOT / "frontend" / "src" / "styles" / "tokens.css"

COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
CLASS_RE = re.compile(r"(?:^|[\s,{>+~|])\.([A-Za-z_][A-Za-z0-9_-]*)")
RULE_RE = re.compile(r"([^{}@]+)\{([^{}]*)\}")


def strip_comments(text: str) -> str:
    return COMMENT_RE.sub("", text)


def extract_class_names(text: str) -> set[str]:
    return set(CLASS_RE.findall(strip_comments(text)))


def extract_class_names_from_path(path: Path) -> set[str]:
    return extract_class_names(path.read_text(encoding="utf-8"))


def spa_style_paths() -> list[Path]:
    paths = sorted(COMPONENTS_DIR.glob("*.css"))
    if TOKENS_CSS.is_file():
        paths.append(TOKENS_CSS)
    return paths


def theme_classes() -> set[str]:
    return extract_class_names_from_path(THEME_CSS)


def spa_classes() -> set[str]:
    out: set[str] = set()
    for p in spa_style_paths():
        out |= extract_class_names_from_path(p)
    return out


def intersection_classes() -> set[str]:
    return theme_classes() & spa_classes()


def _match_brace_block(text: str, open_idx: int) -> int:
    """Return index just past matching ``}`` for ``{`` at open_idx; or len(text)."""
    depth = 0
    j = open_idx
    n = len(text)
    while j < n:
        ch = text[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def _iter_rules(text: str) -> Iterable[tuple[str, str, str]]:
    """Yield (context, selector, body). context is '' or truncated @media head."""
    text = strip_comments(text)
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        if text.startswith("@", i):
            brace = text.find("{", i)
            if brace < 0:
                break
            at_head = text[i:brace].strip()
            end = _match_brace_block(text, brace)
            block = text[brace + 1 : end - 1]
            if at_head.startswith("@media") or at_head.startswith("@supports"):
                for sel, body in RULE_RE.findall(block):
                    yield (at_head[:48], sel.strip(), body.strip())
            i = end
            continue
        brace = text.find("{", i)
        if brace < 0:
            break
        sel = text[i:brace].strip()
        end = _match_brace_block(text, brace)
        body = text[brace + 1 : end - 1].strip()
        if "{" not in body:
            yield ("", sel, body)
        i = end


def rules_for_class(text: str, cls: str) -> list[tuple[str, str, str]]:
    pat = re.compile(rf"\.{re.escape(cls)}(?![A-Za-z0-9_-])")
    return [
        (ctx, sel, body)
        for ctx, sel, body in _iter_rules(text)
        if pat.search(sel)
    ]


def parse_decls(body: str) -> dict[str, str]:
    decls: dict[str, str] = {}
    for part in body.split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        prop, _, val = part.partition(":")
        decls[prop.strip().lower()] = re.sub(r"\s+", " ", val.strip())
    return decls


def bare_class_decls(text: str, cls: str) -> dict[str, str]:
    """Merge decls from selectors that are exactly ``.cls`` (comma-list of pure .cls)."""
    merged: dict[str, str] = {}
    for ctx, sel, body in rules_for_class(text, cls):
        if ctx:
            continue
        parts = [p.strip() for p in sel.split(",")]
        if all(re.fullmatch(rf"\.{re.escape(cls)}", p) for p in parts):
            merged.update(parse_decls(body))
    return merged


def _equivalence(t_bare: dict, s_bare: dict, diffs: list) -> str:
    if t_bare and s_bare and not diffs:
        return "equivalent_bare"
    if t_bare and s_bare:
        return "not_equivalent_bare"
    if t_bare and not s_bare:
        return "theme_bare_only_spa_compound_or_other"
    if s_bare and not t_bare:
        return "spa_bare_only_theme_compound_or_media"
    return "no_bare_on_either_compound_only"


def compare_class(cls: str) -> dict:
    theme_text = THEME_CSS.read_text(encoding="utf-8")
    spa_by_file: dict[str, str] = {}
    for p in spa_style_paths():
        spa_by_file[p.name] = p.read_text(encoding="utf-8")
    spa_all = "\n".join(spa_by_file.values())

    theme_rules = rules_for_class(theme_text, cls)
    spa_rules = []
    spa_sources: set[str] = set()
    for name, t in spa_by_file.items():
        for item in rules_for_class(t, cls):
            spa_rules.append((name, *item))
            spa_sources.add(name)

    t_bare = bare_class_decls(theme_text, cls)
    s_bare = bare_class_decls(spa_all, cls)
    diffs = []
    for prop in sorted(set(t_bare) | set(s_bare)):
        tv, sv = t_bare.get(prop), s_bare.get(prop)
        if tv != sv:
            diffs.append({"prop": prop, "theme": tv, "spa": sv})

    return {
        "class": cls,
        "spa_sources": sorted(spa_sources),
        "equivalence": _equivalence(t_bare, s_bare, diffs),
        "bare_diffs": diffs,
        "theme_rule_count": len(theme_rules),
        "spa_rule_count": len(spa_rules),
        "theme_rules": [
            {"ctx": c, "sel": s[:120], "body": b[:200]} for c, s, b in theme_rules
        ],
        "spa_rules": [
            {"file": f, "ctx": c, "sel": s[:120], "body": b[:200]}
            for f, c, s, b in spa_rules
        ],
    }


def build_inventory_text() -> str:
    inter = sorted(intersection_classes())
    lines = [
        "# CSS dual-source same-name class inventory (S7 / stage_2_6_9_s7)",
        f"# theme: {THEME_CSS.relative_to(ROOT)}",
        "# spa: frontend/src/styles/components/*.css + tokens.css",
        (
            f"# theme_class_count={len(theme_classes())} "
            f"spa_class_count={len(spa_classes())} intersection={len(inter)}"
        ),
        (
            "# known_pre_fix_set includes: bu-nav, bu-nav-a, bu-nav-label, "
            "bu-nav-links, ledger-scroll, rc-bud-bar, rc-bud-h (+ more found below)"
        ),
        "",
    ]
    if not inter:
        lines.append("(empty intersection — post-fix clean)")
        return "\n".join(lines) + "\n"

    for cls in inter:
        info = compare_class(cls)
        lines.append(f"## .{cls}")
        lines.append(f"spa_sources: {', '.join(info['spa_sources'])}")
        lines.append(f"equivalence: {info['equivalence']}")
        lines.append(
            f"rule_counts: theme={info['theme_rule_count']} spa={info['spa_rule_count']}"
        )
        if info["bare_diffs"]:
            lines.append("bare_property_diffs:")
            for d in info["bare_diffs"]:
                lines.append(
                    f"  - {d['prop']}: theme={d['theme']!r} | spa={d['spa']!r}"
                )
        else:
            lines.append("bare_property_diffs: (none or N/A)")
        lines.append("theme_rules:")
        for r in info["theme_rules"]:
            ctx = f" [{r['ctx']}]" if r["ctx"] else ""
            lines.append(f"  -{ctx} {r['sel']}")
            lines.append(f"    {{{r['body']}}}")
        lines.append("spa_rules:")
        for r in info["spa_rules"]:
            ctx = f" [{r['ctx']}]" if r["ctx"] else ""
            lines.append(f"  - [{r['file']}]{ctx} {r['sel']}")
            lines.append(f"    {{{r['body']}}}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_inventory_text())
