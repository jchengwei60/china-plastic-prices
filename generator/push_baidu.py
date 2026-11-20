"""Push the day's core URLs to Baidu's 普通收录 API (best-effort).

Requires the repo secret BAIDU_PUSH_TOKEN (the token from the
site's 普通收录 API page on ziyuan.baidu.com). Without it this is a
no-op. Never fails the daily run: all errors are printed and the
exit code stays 0.

Run from the repo root (after the daily build):
    BAIDU_PUSH_TOKEN=... python generator/push_baidu.py
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date

SITE = "https://pla365.com"
MAINS = ["pp", "lldpe", "hdpe", "ldpe", "pvc", "abs", "ps", "pet"]


def url_list(today):
    urls = [f"{SITE}/", f"{SITE}/news/"]
    urls += [f"{SITE}/{s}/" for s in MAINS]
    urls += [f"{SITE}/{p}/" for p in
             ("pinzhong", "rank", "wendu", "basis", "alerts", "today")]
    urls += [f"{SITE}/history/{today}/",
             f"{SITE}/history/{today[:7]}/",
             f"{SITE}/history/"]
    return urls


def main():
    token = os.environ.get("BAIDU_PUSH_TOKEN", "").strip()
    if not token:
        print("[baidu] no BAIDU_PUSH_TOKEN set; skipping push")
        return 0
    today = date.today().isoformat()
    urls = url_list(today)
    api = (f"http://data.zz.baidu.com/urls?site={SITE}&token={token}")
    req = urllib.request.Request(
        api, data="\n".join(urls).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "text/plain")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        print(f"[baidu] pushed {len(urls)} urls: "
              f"success={out.get('success')} remain={out.get('remain')}")
        if out.get("not_same_site"):
            print(f"[baidu] rejected as not_same_site: "
                  f"{out['not_same_site']}")
    except Exception as exc:
        print(f"[baidu] push failed (continuing): {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
