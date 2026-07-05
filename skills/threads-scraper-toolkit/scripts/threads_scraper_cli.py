from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from threads_scraper.toolkit import attach_post_bodies, collect_profile_posts, filter_posts_by_keyword, scrape_post


SCRIPT_PATH = Path(__file__).resolve()
SCRIPTS_ROOT = SCRIPT_PATH.parent
PACKAGE_ROOT = SCRIPTS_ROOT.parents[2]
DEFAULT_OUTPUT_ROOT = PACKAGE_ROOT / "outputs"
OUTPUT_ROOT_ENV = "THREADS_SCRAPER_OUTPUT_ROOT"
OUTPUT_FORMAT_SUFFIX = {"md": ".md", "json": ".json"}


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def default_output_path(command_name: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return resolve_output_root(None) / command_name / f"{stamp}.json"


def resolve_output_root(output_root: str | None) -> Path:
    if output_root:
        return Path(output_root).expanduser().resolve()
    env_output_root = os.environ.get(OUTPUT_ROOT_ENV, "").strip()
    if env_output_root:
        return Path(env_output_root).expanduser().resolve()
    return DEFAULT_OUTPUT_ROOT


def default_output_file(command_name: str, output_root: str | None, output_format: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    extension = OUTPUT_FORMAT_SUFFIX[output_format]
    return resolve_output_root(output_root) / command_name / f"{stamp}{extension}"


def resolve_output_path(
    output: str | None,
    command_name: str,
    output_root: str | None,
    output_format: str,
) -> Path | None:
    if not output:
        return None
    if output == "auto":
        return default_output_file(command_name, output_root, output_format)

    command_dir = resolve_output_root(output_root) / command_name
    requested = Path(output)
    filename = requested.name or f"{datetime.now().strftime('%Y%m%d_%H%M%S')}{OUTPUT_FORMAT_SUFFIX[output_format]}"
    suffix = Path(filename).suffix.lower()
    if suffix not in OUTPUT_FORMAT_SUFFIX.values():
        filename = f"{filename}{OUTPUT_FORMAT_SUFFIX[output_format]}"
    return command_dir / filename


def normalize_markdown(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def write_utf8_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def emit_text(text: str, *, stream: str = "stdout") -> None:
    target = sys.stdout if stream == "stdout" else sys.stderr
    payload = text if text.endswith("\n") else text + "\n"
    try:
        target.write(payload)
        target.flush()
        return
    except UnicodeEncodeError:
        pass

    buffer = getattr(target, "buffer", None)
    if buffer is not None:
        buffer.write(payload.encode("utf-8"))
        buffer.flush()
        return

    encoded = payload.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    target.write(encoded)
    target.flush()


def post_markdown_block(post: dict[str, object], index: int | None = None) -> str:
    raw_title = str(post.get("title") or post.get("snippet") or "Untitled Threads Post")
    title = normalize_markdown(raw_title).split("\n")[0] or "Untitled Threads Post"
    heading = f"## {index}. {title}" if index is not None else f"## {title}"
    lines = [
        heading,
        "",
        f"- Post URL: {post.get('post_url') or post.get('url') or ''}",
    ]
    if post.get("shortcode"):
        lines.append(f"- Shortcode: `{post['shortcode']}`")
    if post.get("source"):
        lines.append(f"- Source: `{post['source']}`")
    if post.get("scrape_strategy"):
        lines.append(f"- Scrape strategy: `{post['scrape_strategy']}`")
    elif post.get("strategy"):
        lines.append(f"- Scrape strategy: `{post['strategy']}`")
    if post.get("taken_at"):
        lines.append(f"- Taken at: `{post['taken_at']}`")

    body_text = normalize_markdown(str(post.get("body_text") or ""))
    snippet = normalize_markdown(str(post.get("snippet") or ""))
    if body_text:
        lines.extend(["", "### Body", "", body_text])
    elif snippet:
        lines.extend(["", "### Snippet", "", snippet])
    return "\n".join(lines).strip()


def render_markdown(payload: dict[str, object]) -> str:
    command = str(payload.get("command") or "")
    lines = [f"# Threads Toolkit Output: {command}", ""]

    if command == "scrape-post":
        result = dict(payload.get("result") or {})
        lines.append(post_markdown_block(result))
        return "\n".join(lines).strip() + "\n"

    if command == "scrape-user":
        lines.extend(
            [
                f"- Username: `{payload.get('username')}`",
                f"- Profile URL: {payload.get('profile_url')}",
                f"- Collected post count: `{payload.get('collected_post_count')}`",
                "",
            ]
        )
        for index, post in enumerate(payload.get("posts") or [], start=1):
            lines.append(post_markdown_block(dict(post), index=index))
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    if command == "search-keyword":
        lines.extend(
            [
                f"- Username: `{payload.get('username')}`",
                f"- Profile URL: {payload.get('profile_url')}",
                f"- Keyword: `{payload.get('keyword')}`",
                f"- Regex: `{payload.get('regex')}`",
                f"- Searched post count: `{payload.get('searched_post_count')}`",
                f"- Matched post count: `{payload.get('matched_post_count')}`",
                "",
            ]
        )
        matches = payload.get("matches") or []
        if not matches:
            lines.append("No matches found.")
            return "\n".join(lines).strip() + "\n"
        for index, post in enumerate(matches, start=1):
            lines.append(post_markdown_block(dict(post), index=index))
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    lines.append("Unsupported markdown renderer payload.")
    return "\n".join(lines).strip() + "\n"


def write_output_if_requested(
    payload: dict[str, object],
    output: str | None,
    command_name: str,
    output_root: str | None,
    output_format: str,
) -> dict[str, object]:
    output_path = resolve_output_path(output, command_name, output_root, output_format)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_format == "md":
            write_utf8_text(output_path, render_markdown(payload))
        else:
            write_utf8_text(output_path, json.dumps(payload, ensure_ascii=False, indent=2))
        payload["output_path"] = str(output_path)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Portable Threads scraping toolkit with AI-friendly JSON commands.",
    )
    parser.add_argument(
        "--output-root",
        help='Optional base folder for `--output auto`. Defaults to the package outputs folder or env `THREADS_SCRAPER_OUTPUT_ROOT`.',
    )
    parser.add_argument(
        "--format",
        choices=("json", "md"),
        default="json",
        help="Output format for stdout and `--output auto`.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape_post_parser = subparsers.add_parser("scrape-post", help="Scrape one Threads post URL.")
    scrape_post_parser.add_argument("--url", required=True, help="Threads post URL.")
    scrape_post_parser.add_argument("--output", help='Optional output filename. Use "auto" for timestamp naming under the resolved output root.')

    scrape_user_parser = subparsers.add_parser("scrape-user", help="Collect posts from one Threads profile.")
    scrape_user_parser.add_argument("--profile")
    scrape_user_parser.add_argument("--profile-url")
    scrape_user_parser.add_argument("--username")
    scrape_user_parser.add_argument("--max-scrolls", type=int, default=10)
    scrape_user_parser.add_argument("--scroll-pause-ms", type=int, default=1800)
    scrape_user_parser.add_argument("--max-posts", type=int, default=260)
    scrape_user_parser.add_argument("--include-body", action="store_true")
    scrape_user_parser.add_argument("--body-limit", type=int, default=25)
    scrape_user_parser.add_argument("--headful", action="store_true")
    scrape_user_parser.add_argument("--output", help='Optional output filename. Use "auto" for timestamp naming under the resolved output root.')

    keyword_parser = subparsers.add_parser("search-keyword", help="Search one profile for a keyword.")
    keyword_parser.add_argument("--profile")
    keyword_parser.add_argument("--profile-url")
    keyword_parser.add_argument("--username")
    keyword_parser.add_argument("--keyword", required=True)
    keyword_parser.add_argument("--regex", action="store_true")
    keyword_parser.add_argument("--max-scrolls", type=int, default=10)
    keyword_parser.add_argument("--scroll-pause-ms", type=int, default=1800)
    keyword_parser.add_argument("--max-posts", type=int, default=260)
    keyword_parser.add_argument("--include-body", action="store_true")
    keyword_parser.add_argument("--body-limit", type=int, default=25)
    keyword_parser.add_argument("--headful", action="store_true")
    keyword_parser.add_argument("--output", help='Optional output filename. Use "auto" for timestamp naming under the resolved output root.')

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "scrape-post":
            payload = {"status": "ok", "command": args.command, "result": scrape_post(args.url)}
        elif args.command == "scrape-user":
            payload = collect_profile_posts(
                profile=args.profile,
                profile_url=args.profile_url,
                username=args.username,
                max_scrolls=args.max_scrolls,
                scroll_pause_ms=args.scroll_pause_ms,
                max_posts=args.max_posts,
                headful=args.headful,
            )
            payload["command"] = args.command
            if args.include_body:
                payload["posts"] = attach_post_bodies(payload["posts"], args.body_limit)
                payload["body_attached_count"] = min(len(payload["posts"]), args.body_limit)
        else:
            base_payload = collect_profile_posts(
                profile=args.profile,
                profile_url=args.profile_url,
                username=args.username,
                max_scrolls=args.max_scrolls,
                scroll_pause_ms=args.scroll_pause_ms,
                max_posts=args.max_posts,
                headful=args.headful,
            )
            posts = base_payload["posts"]
            matches = filter_posts_by_keyword(posts, args.keyword, use_regex=args.regex)
            if args.include_body and matches:
                matches = attach_post_bodies(matches, min(args.body_limit, len(matches)))
            payload = {
                "status": "ok",
                "command": args.command,
                "profile_url": base_payload["profile_url"],
                "username": base_payload["username"],
                "keyword": args.keyword,
                "regex": args.regex,
                "searched_post_count": len(posts),
                "matched_post_count": len(matches),
                "matches": matches,
                "collection_log": base_payload["collection_log"],
            }

        payload = write_output_if_requested(
            payload,
            getattr(args, "output", None),
            args.command,
            args.output_root,
            args.format,
        )
        if args.format == "md":
            emit_text(render_markdown(payload))
        else:
            emit_text(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        emit_text(
            json.dumps(
                {
                    "status": "failed",
                    "command": args.command,
                    "message": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            ),
            stream="stderr",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
