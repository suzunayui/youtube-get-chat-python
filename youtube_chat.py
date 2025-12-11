"""YouTube live chat scraper (Python version of youtubeChat.js)."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

import chat_store

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

_running_lock = threading.Lock()
_stop_event = threading.Event()
_is_running = False


def _utc_offset_minutes() -> int:
    """Return local UTC offset in minutes."""
    try:
        if time.daylight and time.localtime().tm_isdst:
            offset_seconds = -time.altzone
        else:
            offset_seconds = -time.timezone
        return int(offset_seconds / 60)
    except Exception:  # pylint: disable=broad-except
        return 0


def resolve_video_id(input_str: str) -> Optional[str]:
    """Resolve videoId from raw id / @handle / channel id."""
    if len(input_str) == 11 and not input_str.startswith("@"):
        return input_str

    if input_str.startswith("@"):
        url = f"https://www.youtube.com/{input_str}/live"
    else:
        url = f"https://www.youtube.com/channel/{input_str}/live"

    resp = session.get(url, allow_redirects=True)
    if not resp.ok:
        raise RuntimeError(f"failed to fetch /live page: {resp.status_code}")

    html = resp.text
    m = re.search(
        r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([^"]+)">',
        html,
    )
    return m.group(1) if m else None


def get_watch_html(video_id: str) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    resp = session.get(url)
    if not resp.ok:
        raise RuntimeError(f"failed to fetch watch page: {resp.status_code}")
    return resp.text


def extract_options_from_html(html: str) -> Dict[str, str]:
    key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
    ver_match = re.search(r'"clientVersion"\s*:\s*"([\d\.]+)"', html)
    cont_match = re.search(r'"continuation"\s*:\s*"([^"]+)"', html)
    if not key_match:
        raise RuntimeError("INNERTUBE_API_KEY not found")
    if not ver_match:
        raise RuntimeError("clientVersion not found")
    if not cont_match:
        raise RuntimeError("continuation not found")
    return {
        "apiKey": key_match.group(1),
        "clientVersion": ver_match.group(1),
        "continuation": cont_match.group(1),
    }


def extract_continuation_data(cont0: Dict[str, Any]) -> Tuple[str, int]:
    for key in ("timedContinuationData", "invalidationContinuationData"):
        if key in cont0:
            block = cont0[key]
            return block["continuation"], int(block.get("timeoutMs", 2000))
    raise RuntimeError(f"Unknown continuation block type: {list(cont0.keys())}")


def post_live_chat(api_key: str, client_version: str, continuation: str) -> Dict[str, Any]:
    url = f"https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?key={api_key}"
    payload = {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": client_version,
                "hl": "ja",
                "gl": "JP",
                "utcOffsetMinutes": _utc_offset_minutes(),
            }
        },
        "continuation": continuation,
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-YouTube-Client-Name": "1",
        "X-YouTube-Client-Version": client_version,
    }
    resp = session.post(url, headers=headers, data=json.dumps(payload))
    if not resp.ok:
        raise RuntimeError(f"live_chat error: {resp.status_code} {resp.text}")
    return resp.json()


def switch_to_all_chat_continuation(api_key: str, client_version: str, continuation: str) -> str:
    """Switch from Top Chat to Live Chat if available."""
    data = post_live_chat(api_key, client_version, continuation)
    live_cont = data.get("continuationContents", {}).get("liveChatContinuation", {})
    header = live_cont.get("header", {}).get("liveChatHeaderRenderer", {})
    view_selector = header.get("viewSelector", {}).get("sortFilterSubMenuRenderer", {})
    for item in view_selector.get("subMenuItems", []):
        cont = item.get("continuation", {}).get("reloadContinuationData", {}).get("continuation")
        if cont and not item.get("selected"):
            return cont
    return continuation


def runs_to_plain(runs: List[Dict[str, Any]]) -> str:
    return "".join(r.get("text", "") for r in runs or [])


def parse_amount_to_int(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"([\d,]+)", text)
    if not m:
        return None
    digits = m.group(1).replace(",", "")
    try:
        return int(digits)
    except ValueError:
        return None


def parse_message_parts(renderer: Dict[str, Any]) -> List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = []
    runs = renderer.get("message", {}).get("runs", []) or []
    for r in runs:
        if "text" in r:
            parts.append({"type": "text", "text": r.get("text", "")})
        elif "emoji" in r:
            emoji = r["emoji"]
            thumbs = emoji.get("image", {}).get("thumbnails", []) or []
            url = thumbs[-1]["url"] if thumbs else ""
            shortcuts = emoji.get("shortcuts", []) or []
            alt = shortcuts[0] if shortcuts else emoji.get("emojiId", "")
            parts.append({"type": "emoji", "url": url, "alt": alt})
    return parts


def parse_sticker_parts(renderer: Dict[str, Any]) -> List[Dict[str, Any]]:
    sticker = renderer.get("sticker", {}) or {}
    thumbs = sticker.get("thumbnails", []) or []
    url = thumbs[-1]["url"] if thumbs else ""
    alt = sticker.get("accessibility", {}).get("accessibilityData", {}).get("label", "")
    return [{"type": "sticker", "url": url, "alt": alt}]


def to_hex(value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    return f"#{value & 0xFFFFFF:06X}"


def extract_author_photo(renderer: Dict[str, Any], msg_type: str) -> Optional[str]:
    thumbs = renderer.get("authorPhoto", {}).get("thumbnails")
    if thumbs:
        return thumbs[-1].get("url")
    if msg_type == "gift_purchase":
        header = renderer.get("header", {}).get("liveChatSponsorshipsHeaderRenderer", {})
        thumbs = header.get("authorPhoto", {}).get("thumbnails")
        if thumbs:
            return thumbs[-1].get("url")
    return None


def format_datetime(ts_ms: int) -> str:
    dt = datetime.fromtimestamp(ts_ms / 1000)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def fetch_chat_once(
    api_key: str, client_version: str, continuation: str
) -> Tuple[List[Dict[str, Any]], str, int]:
    data = post_live_chat(api_key, client_version, continuation)
    live_cont = data["continuationContents"]["liveChatContinuation"]
    actions = live_cont.get("actions", []) or []
    chat_items: List[Dict[str, Any]] = []

    for idx, action in enumerate(actions):
        item = action.get("addChatItemAction", {}).get("item")
        if not item:
            continue

        renderer: Optional[Dict[str, Any]] = None
        msg_type: Optional[str] = None
        super_colors: Optional[Dict[str, Any]] = None
        amount_value: Optional[int] = None
        amount_text = ""

        if "liveChatTextMessageRenderer" in item:
            renderer = item["liveChatTextMessageRenderer"]
            msg_type = "text"
        elif "liveChatPaidMessageRenderer" in item:
            renderer = item["liveChatPaidMessageRenderer"]
            msg_type = "paid"
        elif "liveChatPaidStickerRenderer" in item:
            renderer = item["liveChatPaidStickerRenderer"]
            msg_type = "sticker"
        elif "liveChatMembershipItemRenderer" in item:
            renderer = item["liveChatMembershipItemRenderer"]
            msg_type = "membership"
        elif "liveChatSponsorshipsGiftPurchaseAnnouncementRenderer" in item:
            renderer = item["liveChatSponsorshipsGiftPurchaseAnnouncementRenderer"]
            msg_type = "gift_purchase"
        elif "liveChatGiftRedemptionAnnouncementRenderer" in item:
            renderer = item["liveChatGiftRedemptionAnnouncementRenderer"]
            msg_type = "gift_redeem"

        if not renderer or not msg_type:
            continue

        author_block = renderer.get("authorName", {}) or {}
        author = author_block.get("simpleText") or runs_to_plain(author_block.get("runs", []))

        timestamp_usec = int(renderer.get("timestampUsec", "0"))
        timestamp_ms = timestamp_usec // 1000
        timestr = format_datetime(timestamp_ms)

        parts: List[Dict[str, Any]] = []
        text_plain = ""

        if msg_type == "text":
            parts = parse_message_parts(renderer)
            text_plain = "".join(p["text"] for p in parts if p["type"] == "text")
        elif msg_type == "paid":
            parts = parse_message_parts(renderer)
            text_plain = "".join(p["text"] for p in parts if p["type"] == "text")
            amount_text = renderer.get("purchaseAmountText", {}).get("simpleText", "") or ""
            amount_value = parse_amount_to_int(amount_text)
            super_colors = {
                "header_bg": to_hex(renderer.get("headerBackgroundColor")),
                "header_text": to_hex(renderer.get("headerTextColor")),
                "body_bg": to_hex(renderer.get("bodyBackgroundColor")),
                "body_text": to_hex(renderer.get("bodyTextColor")),
            }
        elif msg_type == "sticker":
            parts = parse_sticker_parts(renderer)
            text_plain = "[STICKER]"
            amount_text = renderer.get("purchaseAmountText", {}).get("simpleText", "") or ""
            amount_value = parse_amount_to_int(amount_text)
            bg_raw = renderer.get("backgroundColor")
            text_raw = renderer.get("moneyChipTextColor") or renderer.get("authorNameTextColor")
            super_colors = {"body_bg": to_hex(bg_raw), "body_text": to_hex(text_raw)}
        elif msg_type == "membership":
            parts = parse_message_parts(renderer)
            header_primary = runs_to_plain(renderer.get("headerPrimaryText", {}).get("runs", []))
            header_sub = runs_to_plain(renderer.get("headerSubtext", {}).get("runs", []))
            body_text = "".join(p["text"] for p in parts if p["type"] == "text")
            text_plain = " ".join(filter(None, [header_primary, header_sub, body_text])) or "[MEMBERSHIP]"
        elif msg_type == "gift_purchase":
            header = renderer.get("header", {}).get("liveChatSponsorshipsHeaderRenderer", {}) or {}
            header_author = header.get("authorName", {}) or {}
            raw_author = header_author.get("simpleText") or runs_to_plain(header_author.get("runs", []))
            display_name = raw_author.lstrip("@") if raw_author else ""
            author = display_name or author or "Unknown"
            message = f"{author} sent gift memberships" if display_name else "A viewer sent gift memberships"
            parts = [{"type": "text", "text": message}]
            text_plain = message
        elif msg_type == "gift_redeem":
            header_text = runs_to_plain(renderer.get("header", {}).get("runs", []))
            subtext = runs_to_plain(renderer.get("subtext", {}).get("runs", []))
            text_plain = " ".join(filter(None, [header_text, subtext])) or "[GIFT REDEEM]"
            message_runs = renderer.get("message", {}).get("runs", [])
            if message_runs:
                parts = parse_message_parts({"message": {"runs": message_runs}})
            else:
                parts = [{"type": "text", "text": text_plain}]
            if not author:
                author = "Unknown"

        if not author:
            author = "Unknown"

        icon_url = extract_author_photo(renderer, msg_type)
        raw_id = (
            renderer.get("id")
            or renderer.get("messageId")
            or renderer.get("trackingParams")
        )
        msg_id = str(raw_id or f"{timestamp_ms}_{author}_{text_plain}_{idx}")

        chat_items.append(
            {
                "id": msg_id,
                "colors": super_colors,
                "author": author,
                "icon": icon_url,
                "text": text_plain,
                "parts": parts,
                "timestamp_ms": timestamp_ms,
                "timestamp": timestr,
                "kind": msg_type,
                "amount": amount_value,
                "amount_text": amount_text,
            }
        )

    cont0 = live_cont["continuations"][0]
    next_cont, timeout_ms = extract_continuation_data(cont0)
    return chat_items, next_cont, timeout_ms


def start_live_chat(
    input_str: str, store_dir: Optional[str] = None, print_console: bool = False
) -> None:
    """Start fetching live chat in a loop (blocking)."""
    global _is_running
    with _running_lock:
        if _is_running:
            print("start_live_chat: already running")
            return
        _is_running = True
        _stop_event.clear()

    try:
        chat_store.init_chat_store(store_dir)
        video_id = resolve_video_id(input_str)
        if not video_id:
            print("Could not resolve video id")
            return

        print(f"Resolved videoId = {video_id}")
        html = get_watch_html(video_id)
        opts = extract_options_from_html(html)

        api_key = opts["apiKey"]
        client_version = opts["clientVersion"]
        continuation = switch_to_all_chat_continuation(api_key, client_version, opts["continuation"])

        print("Start fetching live chat (Ctrl+C to stop)")
        while not _stop_event.is_set():
            try:
                chat_items, next_cont, timeout_ms = fetch_chat_once(api_key, client_version, continuation)
                continuation = next_cont
                for msg in chat_items:
                    msg["video_id"] = video_id
                    if print_console:
                        preview = (
                            f"{msg['timestamp']} {msg['author']}: {msg['text']} "
                            f"({msg['kind']}) {msg.get('amount_text') or ''}"
                        ).strip()
                        print(preview)
                    chat_store.save_comment(msg)
                time.sleep(max(timeout_ms, 500) / 1000)
            except Exception as exc:  # pylint: disable=broad-except
                if _stop_event.is_set():
                    break
                print(f"live_chat fetch error: {exc}")
                time.sleep(5)
        print("Stopped live chat fetcher")
    finally:
        _is_running = False


def stop_live_chat() -> None:
    if not _is_running:
        return
    print("Setting stop flag...")
    _stop_event.set()


def get_comments(limit: int = chat_store.DEFAULT_LIMIT):
    return chat_store.get_recent_comments(limit)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch YouTube live chat without API key.")
    parser.add_argument("input", help="videoId / channel id / @handle")
    parser.add_argument(
        "--store-dir",
        help="Directory to place comments.db (defaults to current directory)",
        default=None,
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_console",
        help="Also print comments to console as they are saved.",
    )
    args = parser.parse_args()

    try:
        start_live_chat(args.input, store_dir=args.store_dir, print_console=args.print_console)
    except KeyboardInterrupt:
        stop_live_chat()
        print("Interrupted by user")
