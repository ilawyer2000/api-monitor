# API Monitor

Automated monitoring for KamberLaw's MCP connector APIs. Checks twice monthly for new endpoints, version changes, and documentation updates across all four connected services.

## What It Monitors

| Service | What's Checked | Source |
|---------|---------------|--------|
| **Clio** | API changelog versions (4.0.x), page content changes | [Clio API Changelog](https://docs.developers.clio.com/api-docs/clio-manage/api-changelog/) |
| **Lawmatics** | API version number (currently v1.21.0), endpoint count | [Lawmatics API Docs](https://docs.lawmatics.com/) |
| **CourtListener** | REST API endpoint list (v4), new/removed endpoints | [CourtListener API v4](https://www.courtlistener.com/api/rest/v4/) |
| **GovInfo** | GitHub README changes, developer page updates, endpoint list | [GovInfo GitHub](https://github.com/usgpo/api) |

## How It Works

1. Fetches each API's documentation page
2. Extracts version numbers, endpoint lists, and content hashes
3. Compares against stored baselines (in `baselines/`)
4. If changes detected: creates a GitHub Issue with details
5. Saves updated baselines for next run

## Setup (GitHub)

1. Create a new repo: `ilawyer2000/api-monitor`
2. Push this directory to it:
   ```bash
   cd api-monitor
   git init
   git add .
   git commit -m "Initial commit — API monitor"
   git remote add origin https://github.com/ilawyer2000/api-monitor.git
   git push -u origin main
   ```
3. The GitHub Action runs automatically on the **1st and 15th of each month** at 9am CT
4. You can also trigger it manually from the Actions tab

No secrets needed — the workflow uses the built-in `GITHUB_TOKEN` for creating issues.

## Run Locally

```bash
pip install -r requirements.txt
python monitor.py
```

First run creates baselines. Subsequent runs detect changes.

## What Happens When Changes Are Found

- **In GitHub Actions**: Creates an Issue titled "API Changes Detected — YYYY-MM-DD" with a detailed report listing what changed and links to the relevant documentation
- **Locally**: Prints the report to stdout

## Adjusting Schedule

Edit `.github/workflows/api-check.yml` — the cron expression `0 14 1,15 * *` runs at 14:00 UTC (9am CT) on the 1st and 15th. Change to `0 14 1 * *` for monthly only.
