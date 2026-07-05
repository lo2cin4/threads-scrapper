---
name: threads-scraper-toolkit
description: "Use a dedicated Threads scraping toolkit to scrape one post URL, collect all public posts from one profile, or search that profile by keyword without editing code."
version: 1
status: active
category: workflow
use_when:
  - "User wants all public Threads posts from a specific person."
  - "User wants to scrape one Threads post URL in a structured way."
  - "User wants keyword-based filtering over a Threads profile without touching source code."
  - "AI needs a stable JSON CLI for Threads scraping inside the Obsidian outputs package."
---

# threads-scraper-toolkit

## Purpose

Provide one toolkit package that keeps all active Threads scraping logic in
one place and exposes JSON commands that AI can drive directly.

The skill is self-contained: the CLI locates its own package root from
`__file__`, so it can be copied to another repo without rewriting absolute
paths.

## Scope

Supported commands:

1. `scrape-post`
2. `scrape-user`
3. `search-keyword`

## Runtime

Primary CLI from the package root:

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit --help
```

Scrape one post URL:

```powershell
python $toolkit scrape-post --url "https://www.threads.com/@user/post/SHORTCODE" --format md --output auto
```

Collect one profile:

```powershell
python $toolkit scrape-user --username "user" --include-body --body-limit 10 --format md --output auto
```

Search a profile by keyword:

```powershell
python $toolkit search-keyword --username "user" --keyword "macro" --include-body --body-limit 10 --format md --output auto
```

## Output

- Structured JSON or Markdown to stdout
- Optional saved JSON or Markdown under `{package_root}\outputs\{scrape-post|scrape-user|search-keyword}\` when `--output auto` is used
- Optional saved JSON or Markdown under `{package_root}\outputs\{command_name}\` when `--output <filename>` is used
- Optional custom base folder with:
  - `--output-root "D:\somewhere\threads-output"`
  - env `THREADS_SCRAPER_OUTPUT_ROOT`

## Validation

Run:

```powershell
python -m py_compile .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py .\skills\threads-scraper-toolkit\scripts\threads_scraper\toolkit.py
python $toolkit scrape-post --url "https://www.threads.com/@threads/post/DJrbyamgheB/new-podcast-upcoming-livestream-newsletter-drop-were-rolling-out-another-way-to-" --format md --output auto
python $toolkit scrape-user --username "threads" --max-posts 5 --format md --output auto
python $toolkit search-keyword --username "threads" --keyword "podcast" --max-posts 5 --format md --output auto
```

Pass criteria:

- Each command exits `0`
- Each command returns valid JSON
- `scrape-post` returns non-empty `title`, `body_text`, and `strategy`
- `scrape-user` returns a `posts` array without editing source code
- `search-keyword` returns deterministic keyword-filtered matches without editing source code

Fail action:

- Do not ask the user to edit usernames or keywords in Python files
- Return the runtime error, command attempted, and missing dependency or site-behavior constraint

## Report Requirements

- Owner agent writes the report.
- Include:
  - commands run
  - changed files
  - deleted legacy scripts if any
  - validation results
  - remaining scraping risks
