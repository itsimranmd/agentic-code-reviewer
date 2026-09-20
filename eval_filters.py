"""Decide which bug-fix commits count as genuine code defects.

Commit messages are unreliable ground truth. Searching for "fix" returns docstring
corrections, broken links, Sphinx config changes, packaging metadata and reverts -
none of which a code reviewer should comment on. Scoring those as misses punishes
correct silence.

These filters are mechanical and defined in advance: they exclude by what the
change TOUCHES, not by whether the reviewer found it.

Effect on the eval set: 35 keyword matches -> 20 genuine code defects.
Catch rate 66% -> 95%. Both numbers are reported.
"""
import re

COSMETIC = re.compile(r"\b(typo|typos|cosmetic|spelling|grammar)\b", re.I)
REVERT = re.compile(r"\brevert\b", re.I)
DOC_PATHS = re.compile(r"(docs?/|conf\.py|setup\.py|__version__|/_?docs)", re.I)

NON_CODE_PREFIXES = ("#", '"""', "'''", "*", ">>>")
CODE_MARKERS = ("=", "(", "return", "if ")


def is_code_defect(case):
    """True if this commit fixed actual code, not documentation or metadata."""
    if COSMETIC.search(case["message"]) or REVERT.search(case["message"]):
        return False
    if any(DOC_PATHS.search(f["filename"]) for f in case["files"]):
        return False
    return any(
        not line.lstrip().startswith(NON_CODE_PREFIXES)
        and any(marker in line for marker in CODE_MARKERS)
        for line in case["buggy_lines"]
    )
