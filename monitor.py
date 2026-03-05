#!/usr/bin/env python3
"""
API Monitor for KamberLaw MCP Connectors

Checks Clio, Lawmatics, CourtListener, and GovInfo API documentation
for changes (new endpoints, version bumps, changelog entries).

Run manually or via GitHub Actions on a monthly cron schedule.
When changes are detected, creates a GitHub Issue (if GH_TOKEN is set)
or prints a report to stdout.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASELINES_DIR = Path(__file__).parent / "baselines"
BASELINES_DIR.mkdir(exist_ok=True)

GITHUB_REPO = "ilawyer2000/api-monitor"


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def fetch(url: str, timeout: int = 30) -> str:
    """Fetch a URL and return its text content."""
    headers = {"User-Agent": "KamberLaw-API-Monitor/1.0"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def text_of(html: str) -> str:
    """Strip HTML tags and return cleaned text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def content_hash(text: str) -> str:
    """SHA-256 of normalized text (lowercased, whitespace-collapsed)."""
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    return hashlib.sha256(normalized.encode()).hexdigest()


def load_baseline(name: str) -> dict:
    """Load a baseline JSON file, or return empty dict."""
    path = BASELINES_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_baseline(name: str, data: dict):
    """Save baseline data to JSON."""
    path = BASELINES_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# Per-API monitors
# ---------------------------------------------------------------------------

def check_clio() -> dict:
    """
    Monitor Clio API changelog for new entries.
    Source: https://docs.developers.clio.com/api-docs/clio-manage/api-changelog/
    """
    url = "https://docs.developers.clio.com/api-docs/clio-manage/api-changelog/"
    try:
        html = fetch(url)
        text = text_of(html)
        current_hash = content_hash(text)

        # Extract version numbers (pattern: 4.0.XX) — sort numerically
        raw = set(re.findall(r"4\.0\.(\d+)", text))
        versions = sorted([f"4.0.{n}" for n in raw], key=lambda v: int(v.split(".")[-1]), reverse=True)
        latest_version = versions[0] if versions else "unknown"

        return {
            "service": "Clio",
            "url": url,
            "latest_version": latest_version,
            "versions_found": versions,
            "content_hash": current_hash,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
        }
    except Exception as e:
        return {
            "service": "Clio",
            "url": url,
            "status": "error",
            "error": str(e),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


def check_lawmatics() -> dict:
    """
    Monitor Lawmatics API docs for version changes.
    Source: https://docs.lawmatics.com/
    """
    url = "https://docs.lawmatics.com/"
    try:
        html = fetch(url)
        text = text_of(html)
        current_hash = content_hash(text)

        # Extract version from page title/header (pattern: v1.XX.X)
        version_match = re.search(r"v(\d+\.\d+\.\d+)", text, re.IGNORECASE)
        latest_version = version_match.group(1) if version_match else "unknown"

        # Look for endpoint-related keywords to detect new endpoints
        endpoint_patterns = re.findall(
            r"(?:GET|POST|PUT|DELETE|PATCH)\s+/\S+", text
        )

        return {
            "service": "Lawmatics",
            "url": url,
            "latest_version": latest_version,
            "endpoints_found": len(endpoint_patterns),
            "content_hash": current_hash,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
        }
    except Exception as e:
        return {
            "service": "Lawmatics",
            "url": url,
            "status": "error",
            "error": str(e),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


def check_courtlistener() -> dict:
    """
    Monitor CourtListener REST API root for new endpoints.
    Source: https://www.courtlistener.com/api/rest/v4/
    """
    url = "https://www.courtlistener.com/api/rest/v4/"
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "KamberLaw-API-Monitor/1.0",
                "Accept": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()

        # The API root returns a JSON object with endpoint names as keys
        try:
            data = resp.json()
            endpoints = sorted(data.keys()) if isinstance(data, dict) else []
        except ValueError:
            text = text_of(resp.text)
            endpoints = re.findall(r'"(\w[\w-]+)":\s*"https?://', text)

        return {
            "service": "CourtListener",
            "url": url,
            "endpoint_count": len(endpoints),
            "endpoints": endpoints,
            "content_hash": content_hash(json.dumps(endpoints)),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
        }
    except Exception as e:
        return {
            "service": "CourtListener",
            "url": url,
            "status": "error",
            "error": str(e),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


def check_govinfo() -> dict:
    """
    Monitor GovInfo API docs and release notes for changes.
    Sources:
      - https://github.com/usgpo/api (README)
      - https://www.govinfo.gov/developers
    """
    readme_url = "https://raw.githubusercontent.com/usgpo/api/main/README.md"
    dev_url = "https://www.govinfo.gov/developers"

    try:
        readme_text = fetch(readme_url)
        readme_hash = content_hash(readme_text)

        try:
            dev_html = fetch(dev_url)
            dev_text = text_of(dev_html)
            dev_hash = content_hash(dev_text)
        except Exception:
            dev_text = ""
            dev_hash = "unavailable"

        # Extract endpoint paths from README
        endpoints = sorted(set(re.findall(r"`(/[a-z]+(?:/[{}\w]+)*)`", readme_text)))

        return {
            "service": "GovInfo",
            "urls": [readme_url, dev_url],
            "endpoint_count": len(endpoints),
            "endpoints": endpoints,
            "readme_hash": readme_hash,
            "devpage_hash": dev_hash,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
        }
    except Exception as e:
        return {
            "service": "GovInfo",
            "urls": [readme_url, dev_url],
            "status": "error",
            "error": str(e),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Diff / change detection
# ---------------------------------------------------------------------------

def detect_changes(service_name: str, current: dict, baseline: dict) -> list[str]:
    """Compare current scan to baseline and return list of change descriptions."""
    changes = []

    if not baseline:
        changes.append(f"First scan — baseline created.")
        return changes

    if current.get("status") == "error":
        changes.append(f"Error fetching docs: {current.get('error', 'unknown')}")
        return changes

    # Version bump
    old_ver = baseline.get("latest_version", "")
    new_ver = current.get("latest_version", "")
    if old_ver and new_ver and old_ver != new_ver:
        changes.append(f"Version changed: {old_ver} -> {new_ver}")

    # Content hash change (general page change)
    old_hash = baseline.get("content_hash", "")
    new_hash = current.get("content_hash", "")
    if old_hash and new_hash and old_hash != new_hash:
        changes.append("Documentation page content changed (hash mismatch).")

    # README hash (GovInfo)
    old_rh = baseline.get("readme_hash", "")
    new_rh = current.get("readme_hash", "")
    if old_rh and new_rh and old_rh != new_rh:
        changes.append("GitHub README content changed.")

    # Dev page hash (GovInfo)
    old_dh = baseline.get("devpage_hash", "")
    new_dh = current.get("devpage_hash", "")
    if old_dh and new_dh and old_dh != "unavailable" and new_dh != "unavailable" and old_dh != new_dh:
        changes.append("Developer page content changed.")

    # New endpoints (CourtListener, GovInfo)
    old_eps = set(baseline.get("endpoints", []))
    new_eps = set(current.get("endpoints", []))
    added = new_eps - old_eps
    removed = old_eps - new_eps
    if added:
        changes.append(f"New endpoints added: {', '.join(sorted(added))}")
    if removed:
        changes.append(f"Endpoints removed: {', '.join(sorted(removed))}")

    # Endpoint count change
    old_count = baseline.get("endpoint_count")
    new_count = current.get("endpoint_count")
    if old_count is not None and new_count is not None and old_count != new_count:
        changes.append(f"Endpoint count changed: {old_count} -> {new_count}")

    # New Clio versions
    old_versions = set(baseline.get("versions_found", []))
    new_versions = set(current.get("versions_found", []))
    added_versions = new_versions - old_versions
    if added_versions:
        changes.append(f"New changelog versions: {', '.join(sorted(added_versions, reverse=True))}")

    return changes


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def build_report(all_results: dict[str, list[str]]) -> str:
    """Build a markdown report from change detection results."""
    lines = [
        "# API Monitor Report",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    has_changes = any(changes for changes in all_results.values())

    if not has_changes:
        lines.append("No changes detected across any monitored API.")
        return "\n".join(lines)

    for service, changes in all_results.items():
        if changes:
            lines.append(f"## {service}")
            for change in changes:
                lines.append(f"- {change}")
            lines.append("")

    lines.extend([
        "---",
        "**Action Required:** Review the changes above and determine if any MCP",
        "connector updates are needed. Check the relevant API documentation for details.",
        "",
        "| Service | Documentation |",
        "|---------|-------------|",
        "| Clio | https://docs.developers.clio.com/api-docs/clio-manage/api-changelog/ |",
        "| Lawmatics | https://docs.lawmatics.com/ |",
        "| CourtListener | https://www.courtlistener.com/api/rest-info/ |",
        "| GovInfo | https://github.com/usgpo/api |",
    ])

    return "\n".join(lines)


def create_github_issue(title: str, body: str):
    """Create a GitHub issue using the gh CLI."""
    try:
        subprocess.run(
            ["gh", "issue", "create",
             "--repo", GITHUB_REPO,
             "--title", title,
             "--body", body],
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"GitHub issue created: {title}")
    except FileNotFoundError:
        print("gh CLI not found — printing report to stdout instead.")
        print(body)
    except subprocess.CalledProcessError as e:
        print(f"Failed to create GitHub issue: {e.stderr}")
        print(body)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"API Monitor — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # Run all checks
    checkers = {
        "Clio": ("clio", check_clio),
        "Lawmatics": ("lawmatics", check_lawmatics),
        "CourtListener": ("courtlistener", check_courtlistener),
        "GovInfo": ("govinfo", check_govinfo),
    }

    all_changes: dict[str, list[str]] = {}

    for display_name, (baseline_name, checker_fn) in checkers.items():
        print(f"\nChecking {display_name}...", end=" ")
        baseline = load_baseline(baseline_name)
        current = checker_fn()

        changes = detect_changes(display_name, current, baseline)
        all_changes[display_name] = changes

        # Always save current as new baseline
        save_baseline(baseline_name, current)

        if changes:
            print(f"CHANGES DETECTED:")
            for c in changes:
                print(f"  - {c}")
        else:
            print("No changes.")

    # Build report
    report = build_report(all_changes)
    has_real_changes = any(
        changes and not all("First scan" in c for c in changes)
        for changes in all_changes.values()
    )

    if has_real_changes:
        title = f"API Changes Detected — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

        # If running in GitHub Actions with a token, create an issue
        if os.environ.get("GITHUB_ACTIONS") and os.environ.get("GH_TOKEN"):
            create_github_issue(title, report)
        else:
            print("\n" + "=" * 60)
            print(report)
    else:
        print("\n" + "=" * 60)
        print("All APIs unchanged (or first run — baselines saved).")

    print("\nBaselines saved to:", BASELINES_DIR)


if __name__ == "__main__":
    main()
