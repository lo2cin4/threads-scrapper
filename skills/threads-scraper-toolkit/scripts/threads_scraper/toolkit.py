from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlparse

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    PlaywrightTimeoutError = Exception
    sync_playwright = None


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {"User-Agent": USER_AGENT}
THREADS_POST_PATH_RE = re.compile(r"^/@[^/]+/post/([^/?#]+)")
DATE_LABEL_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
RELATIVE_TIME_RE = re.compile(r"^\d+[smhdw]$", re.IGNORECASE)
CONTINUATION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bcontinued\b",
        r"\bto be continued\b",
        r"\bpart\s*\d+\b",
        r"\b\d+\s*/\s*\d+\b",
        r"[（(]\d+\s*/\s*\d+[)）]",
        r"續",
        r"继续",
        r"下篇",
        r"未完",
    )
]
GRAPHQL_PAGE_SIZE = 11
GRAPHQL_MAX_PAGES = 40
DEFAULT_TIMEOUT_MS = 30_000


@dataclass
class ScrapeResult:
    url: str
    title: str
    body_text: str
    html: str
    strategy: str
    username: str
    shortcode: str


@dataclass
class CollectedPost:
    post_url: str
    shortcode: str
    snippet: str
    source: str
    profile_order_hint: int
    collected_at_scroll: int | None
    taken_at: int | None


def normalize_text(text: str) -> str:
    text = text.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    lines = [line.strip() for line in text.split("\n")]
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        if not line:
            blank_run += 1
            if blank_run <= 1:
                cleaned.append("")
            continue
        blank_run = 0
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def infer_title_from_text(text: str) -> str:
    for line in normalize_text(text).splitlines():
        if line and len(line) <= 100:
            return line
    first_sentence = re.split(r"[.!?\n]", normalize_text(text), maxsplit=1)[0].strip()
    return (first_sentence[:80] or "Untitled Threads Post").strip()


def looks_like_token_blob(text: str) -> bool:
    normalized = normalize_text(text)
    if re.search(r"[\u4e00-\u9fff]", normalized):
        return False
    if " " in normalized or "\n" in normalized:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{60,}", normalized))


def is_bad_candidate_text(text: str) -> bool:
    normalized = normalize_text(text)
    lowered = normalized.lower()
    if not normalized:
        return True
    if lowered.startswith("mozilla/5.0"):
        return True
    if lowered.startswith("<!doctype html") or lowered.startswith("<html"):
        return True
    if "applewebkit/" in lowered and "chrome/" in lowered and "safari/" in lowered:
        return True
    return False


def looks_garbled(text: str) -> bool:
    if not text:
        return True
    bad = text.count("\ufffd")
    return bad / max(len(text), 1) > 0.05


def text_quality_ok(text: str, minimum: int) -> bool:
    normalized = normalize_text(text)
    if len(normalized) < minimum:
        return False
    if looks_like_token_blob(normalized):
        return False
    if is_bad_candidate_text(normalized):
        return False
    return not looks_garbled(normalized)


def decode_best_effort(raw: bytes, apparent_encoding: Optional[str]) -> str:
    candidates = ["utf-8", "utf-8-sig", apparent_encoding, "big5", "cp950", "gb18030"]
    decoded_versions: list[tuple[tuple[int, int], str]] = []
    for encoding in candidates:
        if not encoding:
            continue
        try:
            decoded = raw.decode(encoding, errors="replace")
            replacement_penalty = decoded.count("\ufffd") * 10 + decoded.count("\x00") * 20
            cjk_hits = len(re.findall(r"[\u4e00-\u9fff]", decoded))
            decoded_versions.append(((replacement_penalty, -cjk_hits), decoded))
        except Exception:
            continue
    if not decoded_versions:
        return raw.decode("utf-8", errors="replace")
    decoded_versions.sort(key=lambda item: item[0])
    return decoded_versions[0][1]


def is_threads_post_url(url: str) -> bool:
    parsed = urlparse(url)
    return "threads.com" in parsed.netloc and "/post/" in parsed.path


def extract_threads_username_shortcode(url: str) -> tuple[str, str]:
    match = re.search(r"/@([^/]+)/post/([^/]+)", urlparse(url).path)
    if not match:
        raise RuntimeError("unable to parse Threads username or shortcode from URL")
    return match.group(1), match.group(2)


def is_threads_date_label(text: str) -> bool:
    normalized = normalize_text(text)
    return bool(
        DATE_LABEL_RE.fullmatch(normalized)
        or RELATIVE_TIME_RE.fullmatch(normalized)
        or normalized.lower() in {"yesterday", "today"}
    )


def contains_continuation_marker(text: str) -> bool:
    normalized = normalize_text(text)
    return any(pattern.search(normalized) for pattern in CONTINUATION_PATTERNS)


def is_static_asset(url: str) -> bool:
    normalized = normalize_text(url).lower()
    if not normalized.startswith(("http://", "https://")):
        return False
    parsed = urlparse(normalized)
    if "cdninstagram.com" in parsed.netloc:
        return True
    return parsed.path.endswith((".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"))


def is_noise_line(line: str) -> bool:
    normalized = normalize_text(line)
    lowered = normalized.lower()
    if not normalized:
        return True
    if normalized in {"Translate", "Log in", "Thread", "Report a problem", "Author"}:
        return True
    if normalized in {"Threads Terms", "Privacy Policy", "Cookies Policy", "Replies", "Related threads"}:
        return True
    if lowered.startswith("log in or sign up for threads"):
        return True
    if lowered.startswith("see what people are talking about"):
        return True
    if lowered.startswith("log in with username instead"):
        return True
    if lowered.startswith("replying to "):
        return True
    if normalized.endswith("views"):
        return True
    if re.fullmatch(r"[\d.,]+[KMB]?", normalized):
        return True
    if is_static_asset(normalized):
        return True
    return False


def extract_meta_content(soup: BeautifulSoup, key: str) -> str:
    attrs = {"property": key} if ":" in key else {"name": key}
    tag = soup.find("meta", attrs=attrs)
    if tag and tag.get("content"):
        return normalize_text(unescape(tag["content"]))
    return ""


def extract_meta_title(soup: BeautifulSoup) -> str:
    for key in ("og:title", "twitter:title", "title"):
        value = extract_meta_content(soup, key)
        if value:
            return value
    if soup.find("h1"):
        return normalize_text(soup.find("h1").get_text(" ", strip=True))
    if soup.title and soup.title.string:
        return normalize_text(soup.title.string)
    return ""


def walk_json_strings(obj: object):
    if isinstance(obj, dict):
        for value in obj.values():
            yield from walk_json_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk_json_strings(value)
    elif isinstance(obj, str):
        yield obj


def score_text_candidate(text: str) -> int:
    normalized = normalize_text(text)
    if not normalized:
        return -1
    cjk_hits = len(re.findall(r"[\u4e00-\u9fff]", normalized))
    lines = len([line for line in normalized.splitlines() if line.strip()])
    continuation_bonus = 400 if contains_continuation_marker(normalized) else 0
    return len(normalized) + cjk_hits * 4 + lines * 12 + continuation_bonus


def extract_post_lines(lines: list[str]) -> list[str]:
    if not lines:
        return []
    start_index = 0
    for index, line in enumerate(lines):
        if is_threads_date_label(line):
            start_index = index + 1
            break
    cleaned: list[str] = []
    for line in lines[start_index:]:
        normalized = normalize_text(line)
        if normalized in {"Related threads", "Suggested for you"}:
            break
        if normalized.startswith("See more in Threads"):
            break
        if is_noise_line(normalized):
            continue
        cleaned.append(normalized)
    return cleaned


def trim_author_segments(lines: list[str], username: str) -> list[str]:
    if not username:
        return lines
    normalized_username = normalize_text(username)
    cleaned: list[str] = []
    index = 0
    while index < len(lines):
        current = normalize_text(lines[index])
        if is_noise_line(current):
            index += 1
            continue
        if current == normalized_username or is_threads_date_label(current):
            index += 1
            continue
        if (
            current != normalized_username
            and index + 1 < len(lines)
            and is_threads_date_label(lines[index + 1])
        ):
            break
        cleaned.append(current)
        index += 1
    return cleaned


def extract_same_author_segments(lines: list[str], username: str) -> list[str]:
    if not lines or not username:
        return []
    normalized_username = normalize_text(username)
    cleaned_lines = [normalize_text(line) for line in lines if normalize_text(line)]
    segments: list[str] = []
    current: list[str] = []
    in_author_block = False
    index = 0

    while index < len(cleaned_lines):
        line = cleaned_lines[index]
        next_line = cleaned_lines[index + 1] if index + 1 < len(cleaned_lines) else ""

        if line in {"Related threads", "Suggested for you"}:
            break

        if line == normalized_username and next_line and is_threads_date_label(next_line):
            if current:
                segments.append(normalize_text("\n".join(current)))
                current = []
            in_author_block = True
            index += 2
            while index < len(cleaned_lines) and cleaned_lines[index] == "Author":
                index += 1
            continue

        if in_author_block and line == "Translate":
            if current:
                segments.append(normalize_text("\n".join(current)))
                current = []
            in_author_block = False
            index += 1
            continue

        if in_author_block and line != normalized_username and next_line and is_threads_date_label(next_line):
            if current:
                segments.append(normalize_text("\n".join(current)))
            break

        if in_author_block and not is_noise_line(line):
            current.append(line)
        index += 1

    if current:
        segments.append(normalize_text("\n".join(current)))
    return [segment for segment in segments if text_quality_ok(segment, 40)]


def extract_json_text_candidates(soup: BeautifulSoup) -> list[str]:
    candidates: list[str] = []
    for block in soup.find_all("script", attrs={"data-sjs": True}):
        try:
            data = json.loads(block.get_text())
        except Exception:
            continue
        for value in walk_json_strings(data):
            normalized = normalize_text(value)
            if len(normalized) < 80:
                continue
            if normalized.startswith("{") or normalized.startswith("["):
                continue
            if is_bad_candidate_text(normalized):
                continue
            if is_static_asset(normalized):
                continue
            if looks_like_token_blob(normalized):
                continue
            if not any(ch.isalpha() for ch in normalized) and not re.search(r"[\u4e00-\u9fff]", normalized):
                continue
            candidates.append(normalized)
    deduped = list(dict.fromkeys(candidates))
    deduped.sort(key=score_text_candidate, reverse=True)
    return deduped


def browser_extract_render(url: str, username: str = "") -> dict[str, object]:
    if sync_playwright is None:
        return {}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 2200})
            page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
            page.wait_for_timeout(3000)
            html = page.content()
            title = normalize_text(page.title())
            body_text = normalize_text(page.locator("body").inner_text(timeout=10_000))
            lines = [line.strip() for line in body_text.splitlines() if line.strip()]
            post_lines = extract_post_lines(lines)
            author_segments = extract_same_author_segments(lines, username)
            browser.close()
            return {
                "title": title,
                "html": html,
                "body_text": body_text,
                "lines": lines,
                "post_lines": post_lines,
                "author_segments": author_segments,
            }
    except Exception:
        return {}


def build_article_carrier_text(lines: list[str], meta_description: str) -> Optional[tuple[str, str]]:
    url_candidate = ""
    title_candidate = ""
    domain_candidate = ""

    for index, line in enumerate(lines):
        if line.startswith(("http://", "https://")) and not is_static_asset(line):
            url_candidate = line
            for candidate in lines[index + 1 :]:
                if re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s]*)?", candidate):
                    domain_candidate = candidate
                    continue
                title_candidate = candidate
                break
            break

    if not url_candidate and meta_description.startswith(("http://", "https://")) and not is_static_asset(meta_description):
        url_candidate = meta_description

    if not url_candidate:
        return None

    article_title = title_candidate or (f"Shared article from {domain_candidate}" if domain_candidate else "Threads shared link")
    lines_out = [article_title, "", f"Shared URL: {url_candidate}"]
    if domain_candidate:
        lines_out.append(f"Article domain: {domain_candidate}")
    if title_candidate:
        lines_out.append(f"Article title: {title_candidate}")
    return article_title, "\n".join(lines_out).strip()


def extract_post_from_html(url: str, html: str, rendered: Optional[dict[str, object]] = None) -> tuple[str, str, str]:
    if BeautifulSoup is None:
        raise RuntimeError("BeautifulSoup is required for Threads extraction")

    soup = BeautifulSoup(html, "html.parser")
    meta_title = extract_meta_title(soup)
    meta_description = extract_meta_content(soup, "og:description") or extract_meta_content(soup, "description")

    parsed_username = ""
    if is_threads_post_url(url):
        parsed_username, _ = extract_threads_username_shortcode(url)

    rendered = rendered or {}
    post_lines = [normalize_text(str(line)) for line in rendered.get("post_lines", [])]
    author_segments = [normalize_text(str(segment)) for segment in rendered.get("author_segments", [])]
    if parsed_username:
        post_lines = trim_author_segments(post_lines, parsed_username)

    article_carrier = build_article_carrier_text(post_lines, meta_description)
    if article_carrier is not None:
        title, body_text = article_carrier
        return title, body_text, "threads_article_carrier"

    rendered_post_text = normalize_text("\n".join(post_lines))
    rendered_author_text = normalize_text("\n\n---\n\n".join(author_segments))

    candidates: list[tuple[str, str]] = []
    if meta_description and not meta_description.startswith("http") and not looks_like_token_blob(meta_description):
        candidates.append(("threads_meta_description", meta_description))
    if text_quality_ok(rendered_author_text, 40):
        candidates.append(("threads_rendered_dom_author_replies", rendered_author_text))
    if text_quality_ok(rendered_post_text, 40):
        candidates.append(("threads_rendered_dom", rendered_post_text))
    for candidate in extract_json_text_candidates(soup):
        candidates.append(("threads_meta_dom", candidate))

    if not candidates:
        raise RuntimeError("Threads extractor could not find readable post text")

    best_strategy, best_text = max(candidates, key=lambda item: score_text_candidate(item[1]))
    if contains_continuation_marker(best_text):
        best_strategy = f"{best_strategy}_continuation"

    title = meta_title if meta_title and not meta_title.lower().endswith(" on threads") else infer_title_from_text(best_text)
    if not title or looks_garbled(title) or title.lower() in {"threads", parsed_username.lower() if parsed_username else ""}:
        title = infer_title_from_text(best_text)
    return title, best_text, best_strategy


def scrape_single_post(url: str) -> ScrapeResult:
    username = ""
    shortcode = ""
    if is_threads_post_url(url):
        username, shortcode = extract_threads_username_shortcode(url)
    rendered = browser_extract_render(url, username)

    html = str(rendered.get("html", ""))
    request_error = ""
    if requests is not None:
        try:
            response = requests.get(url, timeout=20, headers=REQUEST_HEADERS)
            response.raise_for_status()
            html = decode_best_effort(response.content, response.apparent_encoding)
        except Exception as exc:
            request_error = str(exc)
    if not html:
        raise RuntimeError(request_error or "Threads extractor could not load page html")

    title, body_text, strategy = extract_post_from_html(url, html, rendered)
    return ScrapeResult(
        url=url,
        title=title,
        body_text=body_text,
        html=html,
        strategy=strategy,
        username=username,
        shortcode=shortcode,
    )


def extract_shortcode(post_url: str) -> str:
    match = THREADS_POST_PATH_RE.search(urlparse(post_url).path)
    return match.group(1) if match else ""


def parse_graphql_edges(payload: dict[str, Any], username: str) -> list[CollectedPost]:
    results: list[CollectedPost] = []
    edges = payload.get("data", {}).get("mediaData", {}).get("edges", [])
    for index, edge in enumerate(edges, start=1):
        node = ((edge or {}).get("node") or {})
        thread_items = node.get("thread_items") or [{}]
        post = (thread_items[0] or {}).get("post") or {}
        code = post.get("code") or post.get("text_post_app_shortcode") or ""
        caption = normalize_text(((post.get("caption") or {}).get("text")) or "")
        if not code or not caption:
            continue
        results.append(
            CollectedPost(
                post_url=f"https://www.threads.com/@{username}/post/{code}",
                shortcode=code,
                snippet=caption,
                source="graphql",
                profile_order_hint=index,
                collected_at_scroll=None,
                taken_at=post.get("taken_at"),
            )
        )
    return results


def collect_dom_posts(page: Any, username: str, max_scrolls: int, scroll_pause_ms: int, max_posts: int) -> tuple[list[CollectedPost], list[str]]:
    logs: list[str] = []
    posts_by_url: dict[str, CollectedPost] = {}
    stalled_rounds = 0
    last_count = 0

    for scroll_round in range(max_scrolls + 1):
        page.wait_for_timeout(800)
        batch = page.evaluate(
            """
            ({ username, scrollRound }) => {
              const anchors = Array.from(document.querySelectorAll(`a[href*="/@${username}/post/"]`));
              const seen = new Set();
              const results = [];

              function cleanText(text) {
                return (text || "")
                  .replace(/\\u00a0/g, " ")
                  .replace(/\\r/g, "")
                  .split("\\n")
                  .map((line) => line.trim())
                  .filter((line, index, arr) => line || (index > 0 && arr[index - 1]))
                  .join("\\n")
                  .trim();
              }

              function findContainer(anchor) {
                const preferred = anchor.closest('[data-pressable-container="true"]') || anchor.closest("article");
                if (preferred) {
                  const preferredText = cleanText(preferred.innerText || "");
                  if (preferredText) {
                    return preferredText;
                  }
                }

                let bestText = cleanText(anchor.innerText || anchor.textContent || "");
                let node = anchor.parentElement;
                for (let depth = 0; depth < 12 && node; depth += 1) {
                  const text = cleanText(node.innerText || "");
                  if (text.length > bestText.length && text.length <= 3000) {
                    bestText = text;
                  }
                  node = node.parentElement;
                }
                return bestText;
              }

              for (let index = 0; index < anchors.length; index += 1) {
                const anchor = anchors[index];
                const href = anchor.getAttribute("href") || "";
                if (!href.includes(`/@${username}/post/`) || href.endsWith("/media")) {
                  continue;
                }
                const absoluteUrl = href.startsWith("http") ? href : `https://www.threads.com${href}`;
                if (seen.has(absoluteUrl)) {
                  continue;
                }
                seen.add(absoluteUrl);
                results.push({
                  post_url: absoluteUrl,
                  snippet: findContainer(anchor),
                  profile_order_hint: index,
                  collected_at_scroll: scrollRound,
                });
              }
              return results;
            }
            """,
            {"username": username, "scrollRound": scroll_round},
        )

        for item in batch:
            post_url = str(item.get("post_url") or "")
            snippet = normalize_text(str(item.get("snippet") or ""))
            if not post_url or not snippet:
                continue
            candidate = CollectedPost(
                post_url=post_url,
                shortcode=extract_shortcode(post_url),
                snippet=snippet,
                source="dom",
                profile_order_hint=int(item.get("profile_order_hint") or 0),
                collected_at_scroll=int(item.get("collected_at_scroll") or 0),
                taken_at=None,
            )
            existing = posts_by_url.get(post_url)
            if existing is None or len(candidate.snippet) > len(existing.snippet):
                posts_by_url[post_url] = candidate

        current_count = len(posts_by_url)
        logs.append(f"dom_scroll_round={scroll_round} collected={current_count}")
        if current_count >= max_posts:
            logs.append(f"dom_stopped_at_max_posts={max_posts}")
            break

        if current_count == last_count:
            stalled_rounds += 1
        else:
            stalled_rounds = 0
            last_count = current_count

        if stalled_rounds >= 3:
            logs.append("dom_stopped_after_stall=3")
            break

        page.mouse.wheel(0, 2600)
        page.wait_for_timeout(scroll_pause_ms)

    ordered = sorted(posts_by_url.values(), key=lambda item: (item.profile_order_hint, item.post_url))
    return ordered, logs


def collect_profile_posts(
    profile: str | None = None,
    *,
    profile_url: str | None = None,
    username: str | None = None,
    max_scrolls: int = 10,
    scroll_pause_ms: int = 1800,
    max_posts: int = 260,
    headful: bool = False,
) -> dict[str, object]:
    if sync_playwright is None:
        raise RuntimeError("playwright is not available")

    target_url, target_username = build_profile_url(profile, profile_url, username)
    logs: list[str] = []
    posts_by_url: dict[str, CollectedPost] = {}

    with sync_playwright() as playwright:
        browser = None
        launch_errors: list[str] = []
        for launch_kwargs in ({"headless": not headful, "channel": "chrome"}, {"headless": not headful}):
            try:
                browser = playwright.chromium.launch(**launch_kwargs)
                logs.append(f"browser_launch={launch_kwargs}")
                break
            except Exception as exc:
                launch_errors.append(f"{launch_kwargs}: {exc}")
        if browser is None:
            raise RuntimeError("unable to launch Playwright browser: " + " | ".join(launch_errors))

        context = browser.new_context(
            viewport={"width": 1440, "height": 2200},
            user_agent=USER_AGENT,
            locale="zh-TW",
        )
        page = context.new_page()

        graphql_request_form: dict[str, str] | None = None
        graphql_request_headers: dict[str, str] | None = None
        graphql_request_url: str | None = None
        initial_graphql_payload: dict[str, Any] | None = None

        def capture_graphql_response(response: Any) -> None:
            nonlocal graphql_request_form, graphql_request_headers, graphql_request_url, initial_graphql_payload
            if graphql_request_form is not None and initial_graphql_payload is not None:
                return
            if "/graphql/query" not in response.url:
                return
            try:
                text = response.text()
                if "mediaData" not in text:
                    return
                graphql_request_url = response.url
                graphql_request_headers = dict(response.request.headers)
                graphql_request_form = dict(parse_qsl(response.request.post_data or "", keep_blank_values=True))
                initial_graphql_payload = json.loads(text)
                logs.append("graphql_initial_response_captured=true")
            except Exception:
                return

        page.on("response", capture_graphql_response)

        try:
            page.goto(target_url, wait_until="commit", timeout=DEFAULT_TIMEOUT_MS)
            page.wait_for_timeout(5000)
        except PlaywrightTimeoutError:
            page.goto(target_url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
            page.wait_for_timeout(5000)

        dom_posts, dom_logs = collect_dom_posts(page, target_username, max_scrolls, scroll_pause_ms, max_posts)
        logs.extend(dom_logs)
        for post in dom_posts:
            posts_by_url[post.post_url] = post

        if graphql_request_form and graphql_request_url and initial_graphql_payload is not None:
            for post in parse_graphql_edges(initial_graphql_payload, target_username):
                existing = posts_by_url.get(post.post_url)
                if existing is None or len(post.snippet) > len(existing.snippet):
                    posts_by_url[post.post_url] = post

            page_info = initial_graphql_payload.get("data", {}).get("mediaData", {}).get("page_info", {})
            page_count = 1
            safe_headers = dict(graphql_request_headers or {})
            safe_headers.pop("content-length", None)

            while page_info.get("has_next_page") and page_info.get("end_cursor") and page_count < GRAPHQL_MAX_PAGES:
                variables = json.loads(graphql_request_form["variables"])
                variables["after"] = page_info["end_cursor"]
                variables["before"] = None
                variables["first"] = GRAPHQL_PAGE_SIZE
                variables["last"] = None
                next_form = dict(graphql_request_form)
                next_form["variables"] = json.dumps(variables, ensure_ascii=False, separators=(",", ":"))

                response = page.request.post(graphql_request_url, headers=safe_headers, form=next_form)
                payload = response.json()
                for post in parse_graphql_edges(payload, target_username):
                    existing = posts_by_url.get(post.post_url)
                    if existing is None or len(post.snippet) > len(existing.snippet):
                        posts_by_url[post.post_url] = post
                page_info = payload.get("data", {}).get("mediaData", {}).get("page_info", {})
                page_count += 1
            logs.append(f"graphql_pages_fetched={page_count}")
        else:
            logs.append("graphql_initial_response_captured=false")

        context.close()
        browser.close()

    ordered = sorted(
        posts_by_url.values(),
        key=lambda item: (item.taken_at is None, -(item.taken_at or 0), item.profile_order_hint, item.post_url),
    )
    ordered = ordered[:max_posts]
    return {
        "status": "ok",
        "profile_url": target_url,
        "username": target_username,
        "collected_post_count": len(ordered),
        "collection_log": logs,
        "posts": [asdict(item) for item in ordered],
    }


def build_profile_url(profile: str | None, profile_url: str | None, username: str | None) -> tuple[str, str]:
    raw = profile_url or username or profile
    if not raw:
        raise ValueError("provide a profile URL or username")

    candidate = raw.strip()
    if candidate.startswith("http://") or candidate.startswith("https://"):
        parsed = urlparse(candidate)
        match = re.search(r"/@([^/?#]+)", parsed.path)
        if not match:
            raise ValueError("unable to parse username from profile URL")
        normalized_username = match.group(1)
    else:
        normalized_username = candidate.lstrip("@")
        if "/" in normalized_username:
            raise ValueError("username should not contain path separators")

    return f"https://www.threads.com/@{normalized_username}", normalized_username


def filter_posts_by_keyword(
    posts: list[dict[str, Any]],
    keyword: str,
    *,
    use_regex: bool = False,
) -> list[dict[str, Any]]:
    if use_regex:
        pattern = re.compile(keyword, re.IGNORECASE)
        matcher = lambda text: bool(pattern.search(text))
    else:
        lowered = keyword.lower()
        matcher = lambda text: lowered in text.lower()

    matches: list[dict[str, Any]] = []
    for post in posts:
        haystacks = [normalize_text(str(post.get("snippet") or ""))]
        if post.get("body_text"):
            haystacks.append(normalize_text(str(post["body_text"])))
        if any(matcher(haystack) for haystack in haystacks if haystack):
            matches.append(post)
    return matches


def scrape_post(url: str) -> dict[str, object]:
    base_result = scrape_single_post(url)
    if is_bad_candidate_text(base_result.body_text) or not text_quality_ok(base_result.body_text, 20):
        if base_result.username and base_result.shortcode:
            profile_payload = collect_profile_posts(username=base_result.username, max_scrolls=6, max_posts=450)
            matched = next(
                (item for item in profile_payload["posts"] if item.get("shortcode") == base_result.shortcode),
                None,
            )
            if matched and text_quality_ok(str(matched.get("snippet") or ""), 20):
                base_result.body_text = normalize_text(str(matched["snippet"]))
                base_result.title = infer_title_from_text(base_result.body_text)
                base_result.strategy = "threads_profile_snippet_fallback"
    if not contains_continuation_marker(base_result.body_text):
        return asdict(base_result)

    profile_payload = collect_profile_posts(username=base_result.username, max_scrolls=6, max_posts=80)
    posts = profile_payload["posts"]
    start_index = next(
        (index for index, item in enumerate(posts) if item.get("shortcode") == base_result.shortcode),
        None,
    )
    if start_index is None:
        return asdict(base_result)

    segments = [base_result.body_text]
    seed_date = posts[start_index].get("date_label", "")
    for item in posts[start_index + 1 : start_index + 8]:
        date_label = item.get("date_label", "")
        if seed_date and date_label and date_label != seed_date:
            break
        next_text = normalize_text(str(item.get("snippet") or ""))
        if not next_text:
            break
        segments.append(next_text)
        if not contains_continuation_marker(next_text):
            break

    combined = "\n\n---\n\n".join(segment.rstrip() for segment in segments if segment.strip())
    result = asdict(base_result)
    result["body_text"] = combined
    result["strategy"] = "threads_profile_chain"
    return result


def attach_post_bodies(posts: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for index, post in enumerate(posts):
        enriched_post = dict(post)
        if index < limit:
            try:
                scraped = scrape_post(str(post["post_url"]))
                enriched_post["body_text"] = scraped["body_text"]
                enriched_post["title"] = scraped["title"]
                enriched_post["scrape_strategy"] = scraped["strategy"]
            except Exception as exc:
                enriched_post["body_error"] = str(exc)
        enriched.append(enriched_post)
    return enriched
