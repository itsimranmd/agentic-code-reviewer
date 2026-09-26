"""Tests for diff_parser.py — the foundation everything else depends on."""
from diff_parser import added_lines, review_scope, chunk_by_file, touches_tests


def test_added_lines_basic():
    patch = "@@ -1,2 +1,3 @@\n line one\n+new line\n line two"
    result = added_lines(patch)
    assert result == [(2, "new line")]


def test_added_lines_ignores_removed():
    patch = "@@ -1,2 +1,2 @@\n-old line\n+new line\n line two"
    result = added_lines(patch)
    assert result == [(1, "new line")]


def test_added_lines_line_numbers_after_multiple_hunks():
    patch = "@@ -1,1 +1,2 @@\n line one\n+added a\n@@ -10,1 +11,2 @@\n line ten\n+added b"
    result = added_lines(patch)
    assert result == [(2, "added a"), (12, "added b")]


def test_review_scope_only_includes_added_lines():
    commit = {"files": [{"filename": "a.py", "patch": "@@ -1,1 +1,2 @@\n line one\n+new line"}]}
    diff, scope = review_scope(commit)
    assert "a.py:2: new line" in scope
    assert "line one" not in "\n".join(scope)   # unchanged context isn't in scope


def test_touches_tests_true_for_test_file():
    commit = {"files": [{"filename": "test_models.py"}, {"filename": "models.py"}]}
    assert touches_tests(commit) is True


def test_touches_tests_false_when_no_test_file():
    commit = {"files": [{"filename": "models.py"}, {"filename": "utils.py"}]}
    assert touches_tests(commit) is False


def test_chunk_by_file_splits_large_patches():
    big_patch = "x" * 20000
    commit = {"files": [{"filename": "big.py", "patch": big_patch}]}
    chunks = chunk_by_file(commit, max_chars=5000)
    assert len(chunks) > 1
    assert all(chunk.get("truncated") for chunk in chunks)
