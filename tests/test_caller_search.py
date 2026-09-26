"""Tests for caller_search.py — the related-files pointer feature."""
import os
import tempfile
from caller_search import changed_definitions, find_related_files


def test_changed_definitions_finds_function():
    patch = "+def review(text):\n+    return text"
    assert changed_definitions(patch) == {"review"}


def test_changed_definitions_finds_class():
    patch = "+class Reviewer:\n+    pass"
    assert changed_definitions(patch) == {"Reviewer"}


def test_changed_definitions_ignores_unrelated_lines():
    patch = "+x = 1\n+y = 2"
    assert changed_definitions(patch) == set()


def test_find_related_files_finds_matching_file():
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "caller.py"), "w").write("from x import review\nreview('hi')")
        open(os.path.join(tmp, "changed.py"), "w").write("def review(text):\n    return text")

        commit = {"files": [{"filename": "changed.py", "patch": "+def review(text):\n+    return text"}]}
        result = find_related_files(commit, repo_root=tmp)

        assert "review" in result
        assert "caller.py" in result["review"]


def test_find_related_files_excludes_the_changed_file_itself():
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "changed.py"), "w").write("def review(text):\n    return text")
        commit = {"files": [{"filename": "changed.py", "patch": "+def review(text):\n+    return text"}]}
        result = find_related_files(commit, repo_root=tmp)
        assert result == {}   # only file mentioning it is the one that changed


def test_find_related_files_no_match_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "unrelated.py"), "w").write("x = 1")
        commit = {"files": [{"filename": "changed.py",
                             "patch": "+def totally_unique_name_xyz(): pass"}]}
        result = find_related_files(commit, repo_root=tmp)
        assert result == {}
