"""Point at other files that might be affected by a changed function.

This does NOT try to detect a bug elsewhere - it only flags that other files
mention the same function or class name, so a human can decide whether to
check. It carries no confidence score and is never counted as a catch in the
eval harness - it's a breadcrumb, not a finding.
"""
import re

DEF_PATTERN = re.compile(r"^[+-]\s*(?:def|class)\s+(\w+)")


def changed_definitions(patch):
    """Function/class names whose definition line was added or removed."""
    names = set()
    for line in patch.split("\n"):
        match = DEF_PATTERN.match(line)
        if match:
            names.add(match.group(1))
    return names


def find_related_files(commit, repo, search_fn, max_names=5, max_files_per_name=5):
    """For each changed definition, find other files that mention it.

    Capped on both sides - names checked, and files reported per name -
    because this makes one search call per name, and code search is
    rate-limited far more tightly than the OpenAI calls elsewhere.
    """
    touched_paths = {f["filename"] for f in commit["files"]}
    names = set()
    for f in commit["files"]:
        names |= changed_definitions(f["patch"])

    warnings = {}
    for name in list(names)[:max_names]:
        if len(name) < 3:          # names this short are too generic to be useful
            continue
        hits = search_fn(repo, name)
        other_files = sorted({h["path"] for h in hits if h["path"] not in touched_paths})
        if other_files:
            warnings[name] = other_files[:max_files_per_name]
    return warnings


def format_related_files_note(warnings):
    """Rendered as its own section - never mixed in with actual findings."""
    if not warnings:
        return ""
    lines = ["", "---", "**Related files** (not reviewed — just a pointer, not a finding):", ""]
    for name, files in warnings.items():
        quoted = ", ".join(f"`{f}`" for f in files)
        lines.append(f"- `{name}` also appears in: {quoted}")
    return "\n".join(lines)
