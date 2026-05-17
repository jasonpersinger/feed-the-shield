# Feed the Shield

Public OPML files for importing NFL-focused RSS, Atom, and podcast feeds into FreshRSS or another feed reader.

The goal is broad NFL coverage without turning the reader into an all-sports firehose. The feed list favors public, legal, reachable feed endpoints for official team news, national NFL news, transactions, injuries, fantasy football, draft coverage, analysis, local beat coverage, and podcasts.

## Recommended File

Use the flat OPML if you want everything imported under a single `NFL` category:

```text
https://raw.githubusercontent.com/jasonpersinger/feed-the-shield/main/nfl-freshrss-flat.opml
```

This is the best default for FreshRSS.

## Alternate File

Use the categorized OPML if you want FreshRSS to create separate categories such as `Official`, `Team News`, `Podcasts`, `Fantasy`, `Draft`, and `Analysis`:

```text
https://raw.githubusercontent.com/jasonpersinger/feed-the-shield/main/nfl-freshrss.opml
```

## FreshRSS Import

1. Open FreshRSS.
2. Go to **Subscription management**.
3. Open **Import / Export**.
4. Import from one of the raw OPML URLs above, or download the OPML file and upload it manually.
5. After import, refresh feeds and remove any sources you do not want.

FreshRSS may ignore non-feed OPML notes. The categorized file includes a small manual-follow section for reporters who did not have a verified public RSS or Atom feed.

## Files

- `nfl-freshrss-flat.opml`: recommended import file. All feeds are directly under one `NFL` category.
- `nfl-freshrss.opml`: categorized import file with nested OPML folders.

## Source Policy

Included feeds should be:

- Publicly reachable
- Legal to subscribe to with a feed reader
- RSS, Atom, XML, or podcast RSS endpoints
- Focused on NFL content

Excluded sources include:

- Social media profile URLs without a verified public feed
- Login-only or private feeds
- Paywalled article pages without a usable feed endpoint
- Dead feeds, placeholder feeds, and article pages pretending to be feeds
- Broad all-sports feeds that would overwhelm the import with unrelated content
- Gambling pick spam and low-quality feed farms

## Maintenance

Feeds can break or go empty over time. If you notice a dead, empty, noisy, or duplicated feed, open an issue or submit a pull request.

Before committing changes, validate the OPML and check for duplicate feed URLs:

```bash
python3 - <<'PY'
import xml.etree.ElementTree as ET
from collections import Counter

for path in ["nfl-freshrss-flat.opml", "nfl-freshrss.opml"]:
    root = ET.parse(path).getroot()
    urls = [node.attrib["xmlUrl"] for node in root.iter("outline") if "xmlUrl" in node.attrib]
    duplicates = [url for url, count in Counter(urls).items() if count > 1]
    print(f"{path}: {len(urls)} feeds, {len(duplicates)} duplicate URLs")
    if duplicates:
        for url in duplicates:
            print(f"  duplicate: {url}")
PY
```

## Current Notes

The list intentionally avoids Twitter/X-only NFL insiders unless a stable, legal, public feed endpoint exists. Some reporters are covered indirectly through verified outlet feeds or podcast feeds instead of personal RSS feeds.

