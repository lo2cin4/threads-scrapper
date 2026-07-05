# Threads Scraper Handoff

## What This Package Is

This is a portable Threads scraping package. It contains:

- `skills/threads-scraper-toolkit/SKILL.md`
- `skills/threads-scraper-toolkit/scripts/threads_scraper_cli.py`
- `skills/threads-scraper-toolkit/scripts/threads_scraper/`
- `requirements.txt`

It can be copied into another repo without editing hardcoded project paths.

## Setup

From the package root:

```powershell
python -m pip install -r .\requirements.txt
python -m playwright install chromium
```

## Runtime

From the package root:

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit --help
```

## Commands

Scrape one post:

```powershell
python $toolkit scrape-post --url "https://www.threads.com/@user/post/SHORTCODE" --format md --output auto
```

Collect one profile:

```powershell
python $toolkit scrape-user --username "user" --include-body --body-limit 10 --format md --output auto
```

Search one profile by keyword:

```powershell
python $toolkit search-keyword --username "user" --keyword "keyword" --include-body --body-limit 20 --format md --output auto
```

## Output Routing

- `--output auto` writes under `.\outputs\{command}\`
- `--output-root "D:\somewhere\threads-output"` overrides that base folder
- env `THREADS_SCRAPER_OUTPUT_ROOT` also overrides the base folder

## Integration Boundary

- The toolkit package is portable and self-contained.
- `D:\Company\.agent\workspace\Obsidian\scripts\intake_source_to_obsidian.py` is only a local wrapper for this repo.
- If another repo needs Threads scraping, copy this package instead of copying the Obsidian wrapper.
