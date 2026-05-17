#!/usr/bin/env python3
"""Validate Feed the Shield OPML files.

Checks:
- OPML XML parses cleanly
- feed xmlUrl values are unique across the checked files
- each feed URL returns HTTP 200
- responses look like RSS or Atom XML
- feeds contain items/entries
- feeds have at least one item within the configured recency window when dates
  are available
"""

from __future__ import annotations

import argparse
import email.utils
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable


DEFAULT_OPML_FILES = ("nfl-freshrss-flat.opml", "nfl-freshrss.opml")
USER_AGENT = "feed-the-shield-validator/1.0"


@dataclass(frozen=True)
class FeedRef:
    source_file: Path
    title: str
    xml_url: str


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_opml(path: Path) -> list[FeedRef]:
    root = ET.parse(path).getroot()
    if local_name(root.tag) != "opml":
        raise ValueError(f"{path}: root element is not opml")

    refs: list[FeedRef] = []
    for node in root.iter():
        if local_name(node.tag) != "outline":
            continue
        xml_url = node.attrib.get("xmlUrl")
        if not xml_url:
            continue
        title = node.attrib.get("title") or node.attrib.get("text") or xml_url
        refs.append(FeedRef(path, title, xml_url))
    return refs


def unique_feed_refs(refs: Iterable[FeedRef]) -> list[FeedRef]:
    seen: set[str] = set()
    unique: list[FeedRef] = []
    for ref in refs:
        if ref.xml_url in seen:
            continue
        seen.add(ref.xml_url)
        unique.append(ref)
    return unique


def find_dates(node: ET.Element) -> list[datetime]:
    dates: list[datetime] = []
    for child in node.iter():
        name = local_name(child.tag)
        if name not in {"pubdate", "published", "updated", "date"}:
            continue
        if not child.text:
            continue
        parsed = parse_datetime(child.text.strip())
        if parsed is None:
            continue
        dates.append(parsed)
    return dates


def parse_datetime(value: str) -> datetime | None:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = None

    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_feed(content: bytes) -> tuple[str, int, datetime | None]:
    root = ET.fromstring(content)
    root_name = local_name(root.tag)

    if root_name == "rss":
        items = [node for node in root.iter() if local_name(node.tag) == "item"]
        feed_type = "rss"
    elif root_name == "feed":
        items = [node for node in root if local_name(node.tag) == "entry"]
        feed_type = "atom"
    else:
        raise ValueError(f"root element is {root.tag!r}, not RSS or Atom")

    newest_dates: list[datetime] = []
    for item in items:
        newest_dates.extend(find_dates(item))

    return feed_type, len(items), max(newest_dates) if newest_dates else None


def fetch_feed(ref: FeedRef, timeout: int) -> tuple[int, str, bytes]:
    request = urllib.request.Request(
        ref.xml_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        content_type = response.headers.get("content-type", "")
        content = response.read()
    return status, content_type, content


def validate_one_feed(
    ref: FeedRef, timeout: int, retries: int, cutoff: datetime, max_age_days: int
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    label = f"{ref.title} <{ref.xml_url}>"
    for attempt in range(1, retries + 2):
        try:
            status, content_type, content = fetch_feed(ref, timeout)
            if status != 200:
                errors = [f"{label}: HTTP {status}"]
                continue
            feed_type, item_count, newest = parse_feed(content)
            if item_count == 0:
                return [f"{label}: {feed_type} feed has no items"], warnings
            if newest is None:
                warnings.append(f"{label}: {feed_type} feed has {item_count} items but no parseable item dates")
            elif newest < cutoff:
                errors.append(f"{label}: newest item is {newest.date().isoformat()}, older than {max_age_days} days")
            if "xml" not in content_type.lower() and "rss" not in content_type.lower() and "atom" not in content_type.lower():
                warnings.append(f"{label}: content-type is {content_type!r}, but XML parsed as {feed_type}")
            return errors, warnings
        except urllib.error.HTTPError as exc:
            errors = [f"{label}: HTTP {exc.code}"]
        except urllib.error.URLError as exc:
            errors = [f"{label}: URL error: {exc.reason}"]
        except TimeoutError:
            errors = [f"{label}: timed out"]
        except ET.ParseError as exc:
            errors = [f"{label}: XML parse error: {exc}"]
            break
        except Exception as exc:
            errors = [f"{label}: {type(exc).__name__}: {exc}"]

        if attempt <= retries:
            continue

    return errors, warnings


def validate_network(
    refs: Iterable[FeedRef], timeout: int, retries: int, max_age_days: int, workers: int
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(validate_one_feed, ref, timeout, retries, cutoff, max_age_days) for ref in refs]
        for future in as_completed(futures):
            feed_errors, feed_warnings = future.result()
            errors.extend(feed_errors)
            warnings.extend(feed_warnings)

    return sorted(errors), sorted(warnings)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Feed the Shield OPML files.")
    parser.add_argument("files", nargs="*", default=DEFAULT_OPML_FILES, help="OPML files to validate")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout per feed in seconds")
    parser.add_argument("--retries", type=int, default=1, help="Retry count for transient network failures")
    parser.add_argument("--max-age-days", type=int, default=120, help="Fail feeds whose newest dated item is older than this")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent network checks")
    parser.add_argument("--no-network", action="store_true", help="Only validate XML structure and duplicate xmlUrls")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    refs: list[FeedRef] = []
    refs_by_file: dict[Path, list[FeedRef]] = {}

    for file_name in args.files:
        path = Path(file_name)
        try:
            file_refs = parse_opml(path)
            refs.extend(file_refs)
            refs_by_file[path] = file_refs
            print(f"{path}: XML valid, {len(file_refs)} feed URLs")
        except Exception as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")

    for path, file_refs in refs_by_file.items():
        url_counts = Counter(ref.xml_url for ref in file_refs)
        duplicates = [url for url, count in url_counts.items() if count > 1]
        for url in duplicates:
            errors.append(f"{path}: duplicate xmlUrl: {url}")

    if not args.no_network and not errors:
        network_errors, network_warnings = validate_network(
            unique_feed_refs(refs), args.timeout, args.retries, args.max_age_days, args.workers
        )
        errors.extend(network_errors)
        warnings.extend(network_warnings)

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if errors:
        print(f"validation failed: {len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1

    print(f"validation passed: {len(unique_feed_refs(refs))} unique feeds, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
