# [English](./README_EN.md)

# Threads Scraper Output

本資料夾用於存放專屬的 Threads 爬蟲輸出套件。

## 內容

- `skills/threads-scraper-toolkit/`
- `requirements.txt`
- `HANDOFF.md`
- 預設輸出資料夾：
  - `outputs/scrape-post/`
  - `outputs/scrape-user/`
  - `outputs/search-keyword/`
  - Git 僅保留 `.gitkeep`；實際產生的資料檔案會由 `.gitignore` 忽略

## 基本規則

- 本套件具備可攜性：CLI 會根據 `__file__` 自動定位 package root，複製到其他 repo 後毋須修改硬編碼路徑
- 所有 toolkit 產生的 `md` 與 `json` 檔案均固定採用 UTF-8 編碼
- 所有儲存輸出皆固定遵循以下結構：
  - `{output_root}/{command_name}/{filename}`

主要 CLI：

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit ... --format md --output auto
```

## AI Skill 使用方式與提示詞範例

本套件可由 AI 直接調用，使用者毋須自行修改 Python 程式碼內的帳號、關鍵字或輸出路徑。當 AI 已載入本 skill 後，可直接使用自然語言下達任務。

### 範例一：下載指定文章

使用者需求：

```text
下載 https://www.threads.com/@lo2cin4/post/DWoYX8ZD7hB?hl=zh-hk 這篇文章
```

AI 可使用的提示詞：

```text
請使用 threads-scraper-toolkit 下載這篇 Threads 文章，輸出為 Markdown，並存入預設輸出資料夾：
https://www.threads.com/@lo2cin4/post/DWoYX8ZD7hB?hl=zh-hk
```

### 範例二：下載指定使用者最近 N 篇文章

使用者需求：

```text
下載 https://www.threads.com/@lo2cin4 最近 N 篇文章
```

AI 可使用的提示詞：

```text
請使用 threads-scraper-toolkit 下載 https://www.threads.com/@lo2cin4 最近 10 篇 Threads 文章，輸出為 Markdown，並存入預設輸出資料夾。
```

### 範例三：下載指定使用者含關鍵字的最近 N 篇文章

使用者需求：

```text
下載 https://www.threads.com/@lo2cin4 含關鍵字「量化」的最近 N 篇文章
```

AI 可使用的提示詞：

```text
請使用 threads-scraper-toolkit 搜尋 https://www.threads.com/@lo2cin4 最近 20 篇文章中含有「量化」的內容，輸出為 Markdown，並存入預設輸出資料夾。
```

如需自訂輸出檔名，只需提供檔名即可；toolkit 仍會自動將檔案寫入對應的 command 資料夾：

```powershell
python $toolkit --format md scrape-user --profile-url "https://www.threads.com/@user" --max-posts 10 --output "cat_themove_recent10.md"
```

## 可供使用者執行的操作

1. 提供單一 Threads 文章連結，擷取該篇文章內容。

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit --format md scrape-post --url "https://www.threads.com/@user/post/SHORTCODE" --output auto
```

2. 提供 Threads 個人頁面連結，擷取指定使用者最近 `N` 篇文章。

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit --format md scrape-user --profile-url "https://www.threads.com/@user" --max-posts 10 --output auto
```

如需一併補上文章 body：

```powershell
python $toolkit --format md scrape-user --profile-url "https://www.threads.com/@user" --max-posts 10 --include-body --body-limit 10 --output auto
```

3. 提供個人頁面連結與關鍵字，搜尋該使用者的命中文章。

```powershell
$toolkit = Resolve-Path .\skills\threads-scraper-toolkit\scripts\threads_scraper_cli.py
python $toolkit --format md search-keyword --profile-url "https://www.threads.com/@user" --keyword "隨手筆記" --output auto
```

如需一併補上命中文章的 body：

```powershell
python $toolkit --format md search-keyword --profile-url "https://www.threads.com/@user" --keyword "隨手筆記" --include-body --body-limit 10 --output auto
```

亦支援 Regex 搜尋：

```powershell
python $toolkit --format json search-keyword --profile-url "https://www.threads.com/@user" --keyword "LGBTQ|吃瓜" --regex --output auto
```

## 功能矩陣

| 內容類型 | 目前支援 | 主要判斷方式 | 主要策略 | 備援 |
| --- | --- | --- | --- | --- |
| 單篇文字文章 | 良好 | `threads.com/@user/post/...` URL | rendered DOM + HTML/meta extraction | profile snippet fallback |
| 分享文章 / link card | 良好 | body 或 meta 呈現外部連結特徵 | article-carrier extraction | rendered DOM text |
| 連續串文 / 多篇 thread | 中上 | 文字包含 continuation markers | 先擷取第一篇，再合併相鄰 profile posts | 如無法證明為串文，則停留於單篇 |
| 整體個人頁面收集 | 良好 | profile URL / username | DOM profile crawl | GraphQL page capture（可用時） |
| 個人頁面關鍵字搜尋 | 良好 | 對 collected posts 執行 keyword filter | 先 filter snippet | 命中後可選擇補 body |

## 策略流程

爬蟲並非對每篇文章一律執行所有方法，而是依以下順序處理：

1. 先判斷目標為文章 URL，或為 profile crawl / search 任務
2. 若為文章 URL，則先抓取 rendered DOM 與 raw HTML
3. 再進一步分類為：
   - 一般文字文章
   - 分享文章 / link card
   - 疑似 continuation chain
4. 優先使用最適合該類型的 extractor
5. 若結果偏弱，則退回其他來源，例如 profile snippet
6. 僅於偵測到 continuation marker 時，才會嘗試將相鄰 posts 合併為同一串內容

## 目前已支援的主要功能

以下三項功能均已支援：

1. 使用特定文章連結擷取單篇內容：`scrape-post`
2. 使用特定 profile 連結擷取最近 `N` 篇文章：`scrape-user --profile-url ... --max-posts N`
3. 使用特定 profile 連結搭配關鍵字搜尋命中文章：`search-keyword --profile-url ... --keyword ...`

## 其他已支援但先前未清楚列示的功能

- profile 輸入可使用 `--profile`、`--profile-url` 或 `--username`
- 輸出格式可選 `json` / `md`
- `--output auto` 可自動存檔
- `--output-root` 或環境變數 `THREADS_SCRAPER_OUTPUT_ROOT` 可切換輸出根目錄
- 所有儲存檔案均固定寫入 `{output_root}/{command_name}/...`
- `--include-body` 可補抓文章 body
- `--body-limit` 可限制補抓 body 的數量
- `search-keyword --regex` 支援 Regex 搜尋
- `--max-scrolls` 與 `--scroll-pause-ms` 可調整 crawl 深度與節奏
- `--headful` 可開啟可見瀏覽器，用於處理 headless 與一般 session 表現不一致的情況

## 目前限制

- 串文判斷依賴 continuation markers；若作者未清楚標示，未必能自動合併
- profile 可見歷史深度取決於 Threads 對當前 browser session 開放的資料量
- GraphQL capture 屬 opportunistic，無法保證每次皆可取得
- 最新文章有時會晚於登入狀態下的人眼可見 timeline；公開 feed 與可見畫面可能不一致
- 若 Threads 調整 DOM 或 response 行為，部分策略可能退化，需另行更新

## 風險說明

- 若目前工具以「未登入狀態」抓取公開內容，通常不存在直接導致帳號被封鎖的風險，因為並未綁定特定使用者帳號
- 但即使未登入，仍然存在被限流、封鎖 IP、回傳舊快取資料、要求驗證或暫時拒絕存取的風險
- 若未來改為登入態抓取，或以過高頻率大量請求，帳號風險與平台風控風險都會顯著提高
- 因此，現階段較實際的主要風險不是「封帳號」，而是「被偵測為自動化流量後遭限流或封鎖來源」
