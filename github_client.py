"""Fetch commits and diffs from the GitHub API."""
import requests

API = "https://api.github.com"

# Add a language by adding its file extensions here. Nothing else in this
# file, or in diff_parser.py, is language-specific - diffs look the same
# regardless of what language they're written in.
LANGUAGE_EXTENSIONS = {
    "python": (".py",),
    "javascript": (".js", ".jsx", ".mjs", ".cjs"),
    "typescript": (".ts", ".tsx"),
}


class GitHubClient:
    """Read-only client for pulling commit diffs.

    Without a token you get 60 requests per hour, which one run exhausts. With
    one, 5,000. No scopes are needed for public repositories.
    """

    def __init__(self, token=None):
        self.headers = {"Accept": "application/vnd.github+json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path, **params):
        response = requests.get(f"{API}{path}", headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def list_commits(self, repo, per_page=60, page=1):
        return self._get(f"/repos/{repo}/commits", per_page=per_page, page=page)

    def get_commit(self, repo, sha):
        return self._get(f"/repos/{repo}/commits/{sha}")

    def code_commits(self, repo, limit=12, max_files=3, extensions=LANGUAGE_EXTENSIONS["python"]):
        """Commits touching a small number of files in the given language(s).

        Pass extensions=LANGUAGE_EXTENSIONS["javascript"] for JS, or a custom
        tuple for a language not yet listed. Large refactors are excluded here
        rather than handled, because a commit touching 40 files is a different
        review problem - see chunk_by_file.
        """
        out = []
        for entry in self.list_commits(repo):
            detail = self.get_commit(repo, entry["sha"])
            files = [f for f in detail.get("files", [])
                     if f["filename"].endswith(extensions) and f.get("patch")]
            if 0 < len(files) <= max_files:
                out.append({
                    "sha": detail["sha"][:8],
                    "message": detail["commit"]["message"].split("\n")[0][:70],
                    "files": files[:max_files],
                    "lines": sum(f["changes"] for f in files[:max_files]),
                })
            if len(out) >= limit:
                break
        return out


    def python_commits(self, repo, limit=12, max_files=3):
        """Deprecated alias for code_commits(..., extensions=(".py",))."""
        return self.code_commits(repo, limit, max_files, LANGUAGE_EXTENSIONS["python"])
