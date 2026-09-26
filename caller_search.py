"""Point at other files that might be affected by a changed function.

This does NOT try to detect a bug elsewhere - it only flags that other files
mention the same function or class name, so a human can decide whether to
check. It carries no confidence score and is never counted as a catch in the
eval harness - it's a breadcrumb, not a finding.

Searches the local checkout directly rather than GitHub's code-search API.
GitHub's search index lags badly on low-traffic repos - a fresh push can sit
unindexed for hours, which made the API-based version silently find nothing
on a real test. Grepping files already on disk has no such lag: pull_request_target
checks out the full repo before this script runs, so the files are already there.
"""
import os
import re

DEF_PATTERN = re.compile(r"^[+-]\s*(?:def|class)\s+(\w+)")
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".github"}


def changed_definitions(patch):
    """Function/class names whose definition line was added or removed."""
    names = set()
    for line in patch.split("\n"):
        match = DEF_PATTERN.match(line)
        if match:
            names.add(match.group(1))
    return names


def _iter_repo_files(root, extensions):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name.endswith(extensions):
                yield os.path.join(dirpath, name)


def find_related_files(commit, repo_root, extensions=(".py",), max_names=5, max_files_per_name=5):
    """For each changed definition, find other files in the checkout that mention it.

    Word-boundary matching avoids matching a name that's a substring of another
    (e.g. "review" inside "review_pr" as one token, not "reviewer").
    """
    touched_paths = {f["filename"] for f in commit["files"]}
    names = set()
    for f in commit["files"]:
        names |= changed_definitions(f["patch"])

    warnings = {}
    for name in list(names)[:max_names]:
        if len(name) < 3:
            continue
        pattern = re.compile(r"\b" + re.escape(name) + r"\b")
        hits = []
        for path in _iter_repo_files(repo_root, extensions):
            rel = os.path.relpath(path, repo_root)
            if rel in touched_paths:
                continue
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    if pattern.search(fh.read()):
                        hits.append(rel)
            except OSError:
                continue
        if hits:
            warnings[name] = sorted(hits)[:max_files_per_name]
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
