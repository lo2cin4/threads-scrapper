# [中文](./README.md)

# Threads Scraper Output

This folder stores the dedicated Threads scraping output package.

Contents:

- `skills/threads-scraper-toolkit/`
- `requirements.txt`
- `HANDOFF.md`
- default command output folders:
  - `outputs/scrape-post/`
  - `outputs/scrape-user/`
  - `outputs/search-keyword/`
  - each folder is kept in git only with `.gitkeep`; generated data stays ignored

The package is portable. The CLI resolves its package root from `__file__`,
so it can be copied to another repo without rewriting hardcoded paths.
All toolkit-generated `md` and `json` outputs are written as UTF-8, including on Windows.
Saved outputs always follow the default order: `{output_root}/{command_name}/{filename}`.

Primary CLI from this folder:

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit ... --format md --output auto
```

If a custom saved filename is needed, pass a filename only. The toolkit still writes it under the command folder:

```powershell
python $toolkit --format md scrape-user --profile-url "https://www.threads.com/@user" --max-posts 10 --output "cat_themove_recent10.md"
```

## User Examples

Users can drive the toolkit by giving links or keywords. No code edit is needed.

1. Scrape one specific Threads post from a direct post link.

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit --format md scrape-post --url "https://www.threads.com/@user/post/SHORTCODE" --output auto
```

2. Scrape the most recent `N` posts from a specific Threads profile link.

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit --format md scrape-user --profile-url "https://www.threads.com/@user" --max-posts 10 --output auto
```

If full body is needed for the collected posts:

```powershell
python $toolkit --format md scrape-user --profile-url "https://www.threads.com/@user" --max-posts 10 --include-body --body-limit 10 --output auto
```

3. Search one profile link for posts that match a keyword.

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit --format md search-keyword --profile-url "https://www.threads.com/@user" --keyword "隨手筆記" --output auto
```

If matched posts should include full body text:

```powershell
python $toolkit --format md search-keyword --profile-url "https://www.threads.com/@user" --keyword "隨手筆記" --include-body --body-limit 10 --output auto
```

Regex search is also supported:

```powershell
python $toolkit --format json search-keyword --profile-url "https://www.threads.com/@user" --keyword "LGBTQ|吃瓜" --regex --output auto
```

## Capability Matrix

| Content type | Current support | Primary detection | Primary strategy | Fallback |
| --- | --- | --- | --- | --- |
| Single text post | Good | `threads.com/@user/post/...` URL | rendered DOM + HTML/meta extraction | profile snippet fallback |
| Shared article / link card | Good | post body or meta looks like external URL | article-carrier extraction | rendered DOM text |
| Continuation chain / multi-post thread | Partial-good | post text contains continuation markers | scrape first post, then merge adjacent profile posts | stop at single post if continuation cannot be proven |
| Profile-wide post collection | Good | profile URL or username input | DOM profile crawl | GraphQL page capture when available |
| Profile keyword search | Good | keyword over collected profile posts | filter collected snippets first | optional body attach for matched posts only |

## Strategy Flow

The scraper does not blindly run every method for every post.

It uses this order:

1. Detect whether the target is a post URL or a profile crawl/search task.
2. For a post URL, fetch rendered DOM and raw HTML.
3. Classify the post as:
   - ordinary text post
   - shared article / link card
   - possible continuation chain
4. Use the best-fit extractor first.
5. If the result is weak, fall back to another source such as profile snippet text.
6. Only if continuation markers are found will the scraper try to merge adjacent posts into one chain.

## Supported Functions

The three functions you listed are all supported now:

1. A user can give one specific post link and scrape that single post with `scrape-post`.
2. A user can give another user's profile link and scrape the recent `N` posts with `scrape-user --profile-url ... --max-posts N`.
3. A user can give another user's profile link plus a keyword and scrape matched posts with `search-keyword --profile-url ... --keyword ...`.

## Other Supported Features Not Previously Written Clearly

- Accept profile input as `--profile`, `--profile-url`, or `--username`.
- Return either `json` or `md` with `--format`.
- Save outputs automatically under this package with `--output auto`.
- Save outputs to another base folder with `--output-root` or env `THREADS_SCRAPER_OUTPUT_ROOT`.
- Keep all saved files under the fixed command order `{output_root}/{command_name}/...`.
- Add full post body to profile collection or keyword results with `--include-body`.
- Limit how many matched posts get body expansion with `--body-limit`.
- Use regex instead of plain keyword matching with `search-keyword --regex`.
- Tune crawl depth and pacing with `--max-scrolls` and `--scroll-pause-ms`.
- Run a visible browser with `--headful` for cases where headless behavior differs from a normal session.

## Current Limits

- Continuation chains depend on detectable continuation markers. If the author does not signal continuation clearly, chain merge may not trigger.
- Profile history depth depends on what Threads exposes to the browser session. Some older posts may not be available from the public page.
- GraphQL capture is opportunistic, not guaranteed. When unavailable, the scraper falls back to DOM collection only.
- Newest posts may sometimes lag behind what a logged-in human session can see. Public profile feed and browser-visible feed can be stale or inconsistent.
- If Threads changes DOM structure or response behavior, one or more strategies may degrade until updated.
