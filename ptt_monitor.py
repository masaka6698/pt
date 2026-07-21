#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BOARD_URL = "https://www.ptt.cc/bbs/PttEarnMoney/index.html"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
STATE_FILE = Path("data/seen_posts.json")
NOTIFY_ON_FIRST_RUN = os.getenv("NOTIFY_ON_FIRST_RUN", "false").lower() == "true"
REQUEST_TIMEOUT = 30
MAX_SEEN_POSTS = 1000


@dataclass(frozen=True)
class Post:
    post_id: str
    title: str
    author: str
    date: str
    push: str
    url: str


def fetch_posts() -> list[Post]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.ptt.cc/",
            "Connection": "close",
        }
    )
    session.cookies.set("over18", "1", domain=".ptt.cc")

    last_error: Exception | None = None

    for attempt in range(1, 6):
        try:
            logging.info("Fetching PTT, attempt %d/5", attempt)
            response = session.get(
                BOARD_URL,
                timeout=(15, REQUEST_TIMEOUT),
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            posts: list[Post] = []

            for entry in soup.select("div.r-ent"):
                title_node = entry.select_one("div.title a")
                if title_node is None:
                    continue

                href = title_node.get("href", "").strip()
                match = re.search(r"/bbs/[^/]+/(M\.[^/]+)\.html$", href)

                if not match:
                    logging.warning("Cannot parse post ID from href: %s", href)
                    continue

                author_node = entry.select_one("div.author")
                date_node = entry.select_one("div.date")
                push_node = entry.select_one("div.nrec")

                posts.append(
                    Post(
                        post_id=match.group(1),
                        title=title_node.get_text(" ", strip=True),
                        author=author_node.get_text(" ", strip=True) if author_node else "",
                        date=date_node.get_text(" ", strip=True) if date_node else "",
                        push=push_node.get_text(" ", strip=True) if push_node else "",
                        url=urljoin(BOARD_URL, href),
                    )
                )

            if not posts:
                raise RuntimeError(
                    "No posts parsed; PTT page structure may have changed."
                )

            return posts

        except (requests.RequestException, RuntimeError) as exc:
            last_error = exc
            logging.warning(
                "PTT fetch failed on attempt %d: %s",
                attempt,
                exc,
            )
            if attempt < 5:
                time.sleep(attempt * 10)

    raise RuntimeError(
        f"PTT could not be fetched after 5 attempts: {last_error}"
    )


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"initialized": False, "seen_ids": []}

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Cannot read state file: {exc}") from exc

    return {
        "initialized": bool(data.get("initialized", False)),
        "seen_ids": [str(item) for item in data.get("seen_ids", [])],
    }


def save_state(post_ids: list[str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "initialized": True,
        "seen_ids": list(dict.fromkeys(post_ids))[-MAX_SEEN_POSTS:],
    }
    STATE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def send_discord(post: Post) -> None:
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError("Missing DISCORD_WEBHOOK_URL environment variable.")

    payload = {
        "username": "PTT 額板通知",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": post.title[:256],
                "url": post.url,
                "description": (
                    f"作者：`{post.author}`　｜　"
                    f"日期：`{post.date}`　｜　"
                    f"推文：`{post.push or '0'}`"
                ),
                "footer": {"text": "PttEarnMoney 新文章"},
            }
        ],
    }

    separator = "&" if "?" in DISCORD_WEBHOOK_URL else "?"
    webhook_url = f"{DISCORD_WEBHOOK_URL}{separator}wait=true"

    response = requests.post(
        webhook_url,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 429:
        retry_after = float(response.json().get("retry_after", 1))
        time.sleep(retry_after)
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

    response.raise_for_status()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    posts = fetch_posts()
    state = load_state()
    seen_ids = set(state["seen_ids"])
    current_ids = [post.post_id for post in posts]

    if not state["initialized"] and not NOTIFY_ON_FIRST_RUN:
        save_state(current_ids)
        logging.info(
            "First run: stored %d current posts without notifications.",
            len(current_ids),
        )
        return 0

    new_posts = [post for post in posts if post.post_id not in seen_ids]
    logging.info("Found %d new post(s).", len(new_posts))

    notified_ids: list[str] = []

    for post in new_posts:
        logging.info("Sending: %s - %s", post.post_id, post.title)
        send_discord(post)
        notified_ids.append(post.post_id)

    save_state(state["seen_ids"] + notified_ids)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logging.exception("Monitor failed.")
        sys.exit(1)
