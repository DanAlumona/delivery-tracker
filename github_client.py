"""Read-only GitHub REST API client with a local file cache.

Only GET requests are made, only to api.github.com. Every response is cached
under cache/ so repeat runs (and offline runs) don't spend the rate limit:
unauthenticated requests get 60 calls an hour, a token gets 5,000.
"""

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"


def find_token(use_gh_cli):
    """A token from GITHUB_TOKEN, or from `gh auth token` if asked. None means unauthenticated."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    if use_gh_cli:
        try:
            out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
            return out.stdout.strip() or None
        except (OSError, subprocess.CalledProcessError):
            print("warning: `gh auth token` failed; continuing unauthenticated")
    return None


class GitHubClient:
    def __init__(self, cache_dir, token=None, max_age_hours=12, offline=False):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.token = token
        self.max_age = max_age_hours * 3600
        self.offline = offline
        self.calls = 0  # live API calls made this run

    def _cache_path(self, url):
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")

    def get(self, url):
        """GET one URL. Returns (json_body, next_page_url or None)."""
        path = self._cache_path(url)
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            if self.offline or time.time() - cached["fetched_at"] < self.max_age:
                return cached["body"], cached["next"]
        if self.offline:
            raise RuntimeError(f"--offline but not cached: {url}")

        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "delivery-tracker"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
                link = response.headers.get("Link", "")
        except urllib.error.HTTPError as err:
            if err.code == 403 and err.headers.get("X-RateLimit-Remaining") == "0":
                raise RuntimeError("GitHub rate limit reached. Wait an hour, use --offline, "
                                   "or pass a token (GITHUB_TOKEN or --gh-token).") from err
            raise
        self.calls += 1
        match = re.search(r'<([^>]+)>;\s*rel="next"', link)
        next_url = match.group(1) if match else None
        path.write_text(json.dumps({"url": url, "fetched_at": time.time(), "next": next_url,
                                    "body": body}), encoding="utf-8")
        return body, next_url

    def get_all(self, path, max_pages=30):
        """Follow pagination for a list endpoint, e.g. /repos/o/r/issues?state=open."""
        url = API + path
        sep = "&" if "?" in url else "?"
        url += f"{sep}per_page=100"
        items = []
        for _ in range(max_pages):
            body, url = self.get(url)
            items.extend(body)
            if not url:
                break
        return items
