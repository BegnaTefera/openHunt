from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable

from app.collectors.url_detection import detect_ats_from_url


def detect_urls(urls: Iterable[str]) -> int:
    exit_code = 0
    for raw_url in urls:
        url = raw_url.strip()
        if not url:
            continue
        result = detect_ats_from_url(url)
        print(
            json.dumps(
                {
                    "url": url,
                    "ats_type": result.ats_type,
                    "ats_slug": result.ats_slug,
                }
            )
        )
        if result.ats_type is None:
            exit_code = 1
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect ATS types and board slugs from pasted application URLs."
    )
    parser.add_argument("urls", nargs="*", help="Application URLs; otherwise read one URL per line from stdin")
    args = parser.parse_args()
    urls = args.urls if args.urls else sys.stdin
    return detect_urls(urls)


if __name__ == "__main__":
    raise SystemExit(main())
