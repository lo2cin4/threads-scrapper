# Threads Scraper Output 中文版

[English](./README.md)

呢個資料夾係專屬嘅 Threads 爬蟲輸出 package。

## 內容

- `skills/threads-scraper-toolkit/`
- `requirements.txt`
- `HANDOFF.md`
- 預設輸出資料夾：
  - `outputs/scrape-post/`
  - `outputs/scrape-user/`
  - `outputs/search-keyword/`
  - Git 只保留 `.gitkeep`，實際產生出嚟嘅資料會被 `.gitignore` 忽略

## 基本規則

- package 可攜式：CLI 會由 `__file__` 自動定位 package root，搬去其他 repo 都唔使改死路徑
- 所有 toolkit 產生嘅 `md` / `json` 都固定用 UTF-8
- 所有 saved output 都固定跟呢個結構：
  - `{output_root}/{command_name}/{filename}`

主 CLI：

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit ... --format md --output auto
```

如果想自訂檔名，只需要俾 filename，toolkit 仍然會自動放返喺對應 command folder：

```powershell
python $toolkit --format md scrape-user --profile-url "https://www.threads.com/@user" --max-posts 10 --output "cat_themove_recent10.md"
```

## 用戶可以做乜

1. 用一條 Threads 文章 link，爬單篇文章。

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit --format md scrape-post --url "https://www.threads.com/@user/post/SHORTCODE" --output auto
```

2. 用一條 Threads profile link，爬該用戶最近 `N` 篇文章。

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit --format md scrape-user --profile-url "https://www.threads.com/@user" --max-posts 10 --output auto
```

如果想連 body 一齊補：

```powershell
python $toolkit --format md scrape-user --profile-url "https://www.threads.com/@user" --max-posts 10 --include-body --body-limit 10 --output auto
```

3. 用 profile link + 關鍵字，搜尋命中文章。

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit --format md search-keyword --profile-url "https://www.threads.com/@user" --keyword "隨手筆記" --output auto
```

如果想連命中文章嘅 body 一齊補：

```powershell
python $toolkit --format md search-keyword --profile-url "https://www.threads.com/@user" --keyword "隨手筆記" --include-body --body-limit 10 --output auto
```

Regex 搜尋亦支援：

```powershell
python $toolkit --format json search-keyword --profile-url "https://www.threads.com/@user" --keyword "LGBTQ|吃瓜" --regex --output auto
```

## 功能矩陣

| 內容類型 | 目前支援 | 主要判斷 | 主要策略 | 備援 |
| --- | --- | --- | --- | --- |
| 單篇文字文章 | 好 | `threads.com/@user/post/...` URL | rendered DOM + HTML/meta extraction | profile snippet fallback |
| 分享文章 / link card | 好 | body 或 meta 像外部連結 | article-carrier extraction | rendered DOM text |
| 連續串文 / 多篇 thread | 中上 | 文字包含 continuation markers | 先爬第一篇，再合併相鄰 profile posts | 如果無法證明係串文，就停喺單篇 |
| 整個 profile 收集 | 好 | profile URL / username | DOM profile crawl | GraphQL page capture（有就用） |
| profile 關鍵字搜尋 | 好 | 對 collected posts 做 keyword filter | 先 filter snippet | 命中後可選擇補 body |

## 策略流程

爬蟲唔係每篇文都硬跑所有方法，而係照以下順序：

1. 先判斷目標係文章 URL，定係 profile crawl / search 任務
2. 如果係文章 URL，就先抓 rendered DOM 同 raw HTML
3. 再分類：
   - 普通文字文
   - 分享文章 / link card
   - 疑似 continuation chain
4. 先用最合適嘅 extractor
5. 如果結果偏弱，再 fallback 去其他來源，例如 profile snippet
6. 只有偵測到 continuation marker，先會嘗試將相鄰 posts 合併為同一串

## 目前已支援嘅主要功能

以下三個功能都已支援：

1. 用特定文章 link 爬單篇文：`scrape-post`
2. 用特定 profile link 爬最近 `N` 篇：`scrape-user --profile-url ... --max-posts N`
3. 用特定 profile link + keyword 搜尋命中文章：`search-keyword --profile-url ... --keyword ...`

## 其他已支援但之前未寫清楚嘅功能

- profile 可用 `--profile`、`--profile-url` 或 `--username`
- 輸出格式可選 `json` / `md`
- `--output auto` 會自動存檔
- `--output-root` 或 env `THREADS_SCRAPER_OUTPUT_ROOT` 可以換 output root
- 所有 saved files 都固定落 `{output_root}/{command_name}/...`
- `--include-body` 可以補文章 body
- `--body-limit` 可以限制補 body 嘅數量
- `search-keyword --regex` 支援 regex 搜尋
- `--max-scrolls`、`--scroll-pause-ms` 可以調整 crawl 深度同節奏
- `--headful` 可以開可見 browser，處理 headless 同正常 session 表現不一致嘅情況

## 目前限制

- 串文判斷依賴 continuation markers。如果作者冇清楚標示，未必會自動合併
- profile 可見歷史深度取決於 Threads 對當前 browser session 開放幾多資料
- GraphQL capture 係 opportunistic，唔保證一定有
- 最新文章有時會比登入後人眼見到嘅 timeline 慢，公開 feed 同可見畫面可能唔一致
- 如果 Threads 改 DOM 或 response 行為，某啲策略可能會退化，需要更新
