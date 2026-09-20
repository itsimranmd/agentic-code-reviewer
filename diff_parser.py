"""Parse unified diffs into reviewable line numbers.

A diff shows what changed, not the file it changed in. This module extracts the
added lines and their real position in the new file, which is what lets a finding
be posted to a specific line on GitHub.
"""
import re

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def added_lines(patch):
    """Return [(line_number_in_new_file, text)] for added lines only.

    The hunk header "@@ -42,7 +156,9 @@" says the new file's block starts at line
    156. Count forward from there, skipping removed lines - they do not exist in
    the new file, so counting them would shift every subsequent line number.
    """
    out, lineno = [], 0
    for raw in patch.split("\n"):
        match = HUNK.match(raw)
        if match:
            lineno = int(match.group(1))
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            out.append((lineno, raw[1:]))
            lineno += 1
        elif raw.startswith("-"):
            continue
        else:
            lineno += 1
    return out


def review_scope(commit):
    """Return (full_diff, in_scope_lines).

    Scope is added lines only. Reviewing code the author never touched is the
    fastest way to get an automated reviewer muted.
    """
    parts, scope = [], []
    for f in commit["files"]:
        parts.append(f"--- {f['filename']} ---\n{f['patch']}")
        for lineno, text in added_lines(f["patch"]):
            if text.strip():
                scope.append(f"{f['filename']}:{lineno}: {text}")
    return "\n\n".join(parts), scope


def chunk_by_file(commit, max_chars=12000):
    """Split an oversized commit so each piece fits the context window.

    Files are a natural boundary - a finding rarely spans two of them. The cost is
    that cross-file issues become invisible: if a signature changes in one file and
    a caller in another is not updated, per-file review cannot see it.
    """
    chunks = []
    for f in commit["files"]:
        patch = f["patch"]
        if len(patch) <= max_chars:
            chunks.append({"files": [f]})
        else:
            for i in range(0, len(patch), max_chars):
                chunks.append({"files": [dict(f, patch=patch[i:i + max_chars])],
                               "truncated": True})
    return chunks or [commit]


def touches_tests(commit):
    """Commit-wide test detection.

    This must be checked against the whole commit, not a chunk. Chunking splits by
    file, so a chunk containing only models.py cannot see that the commit also adds
    a test - which produced four false "untested behaviour" findings before this
    existed.
    """
    return any("test" in f["filename"].lower() or "spec" in f["filename"].lower()
               for f in commit["files"])
