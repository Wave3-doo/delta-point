#!/usr/bin/env python3
"""Fill the generated parts of the website from the app's plans file.

The pages are hand-written HTML. Only these parts come from here, so prices
live in one place (data-platform: webhook_receiver/legal/plans.json):
  <!-- build:plans --> ... <!-- /build:plans -->   the pricing cards
  <!-- build:cta --> ... <!-- /build:cta -->       hero button: early access or install
  the SoftwareApplication JSON-LD "offers"           prices for search engines
  "<N>-day free trial"                               from trial_days
  sitemap.xml <lastmod>                              today, for pages that changed

  python3 _build/build_site.py            write the pages
  python3 _build/build_site.py --check    exit 1 if a page is out of date (CI)
  python3 _build/build_site.py --plans <path to plans.json>

Shopify's Managed Pricing plans are set by hand in the Partner Dashboard
(Shopify has no API to write them): keep them equal to plans.json.
Files under _build/ are not published (GitHub Pages skips folders starting with _).
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
PLANS = SITE.parent.parent / "data-platform" / "webhook_receiver" / "legal" / "plans.json"
PAGES = {"index.html": "https://deltapoint.io/", "shopify/index.html": "https://deltapoint.io/shopify/"}
FEATURED = "growth"
SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}
# The app's Shopify App Store page. Empty until the listing is approved: the
# hero then offers early access by email instead of an install button.
SHOPIFY_LISTING = ""
EARLY_ACCESS = "mailto:info@wave-3.com?subject=Delta%20Point%20early%20access"


def money(n: int, cur: str) -> str:
    return f"{SYMBOLS.get(cur, cur + ' ')}{n:,}"


def plans_html(data: dict) -> str:
    cur = data["currency"]
    cards = []
    for p in data["plans"]:
        if p.get("price_year"):
            free_months = round(12 - p["price_year"] / p["price_month"])
            yearly = (f"or {money(p['price_year'], cur)}/year"
                      + (f" ({free_months} month{'s' if free_months > 1 else ''} free)" if free_months > 0 else ""))
        else:
            yearly = "No charge" if p["price_month"] == 0 else ""
        items = "".join(f"<li>{html.escape(f)}</li>" for f in p["features"])
        cards.append(
            f'        <div class="card plan{" featured" if p["id"] == FEATURED else ""}">\n'
            f'          <h3>{html.escape(p["name"])}</h3>\n'
            f'          <div class="summary">{html.escape(p["summary"])}</div>\n'
            f'          <div class="price">{money(p["price_month"], cur)}<small> / month</small></div>\n'
            f'          <div class="yearly">{yearly}</div>\n'
            f'          <ul>{items}</ul>\n'
            f'        </div>')
    return '    <div class="plans">\n' + "\n".join(cards) + "\n    </div>"


def cta_html(page: str, data: dict) -> str:
    trial = data.get("trial_days")
    if SHOPIFY_LISTING:
        button = f'<a class="btn" href="{html.escape(SHOPIFY_LISTING)}">Install on Shopify</a>'
        soon = "Free plan" + (f", {trial}-day free trial on paid plans." if trial else ".")
    else:
        button = f'<a class="btn" href="{EARLY_ACCESS}">Get early access</a>'
        soon = "Coming soon to the Shopify App Store."
    if page == "index.html":
        return ('    <div class="actions">\n'
                f'      {button}\n'
                '      <a class="btn btn-ghost" href="#pricing">See pricing</a>\n'
                '    </div>\n'
                f'    <p class="soon">{soon}</p>')
    return f'    {button}\n    <p class="soon">{soon}</p>'


def replace_region(src: str, name: str, body: str, page: str) -> str:
    pat = re.compile(rf"(<!-- build:{name}\b[^>]*-->\n)(.*?)(\n\s*<!-- /build:{name} -->)", re.S)
    if not pat.search(src):
        raise SystemExit(f"{page}: no <!-- build:{name} --> region")
    return pat.sub(lambda m: m.group(1) + body + m.group(3), src, count=1)


def offers_jsonld(src: str, data: dict, page: str) -> str:
    pat = re.compile(r'(<script type="application/ld\+json">\n)(.*?)(\n</script>)', re.S)
    for m in pat.finditer(src):
        doc = json.loads(m.group(2))
        if doc.get("@type") != "SoftwareApplication":
            continue
        doc["offers"] = [{"@type": "Offer", "name": p["name"], "price": str(p["price_month"]),
                          "priceCurrency": data["currency"], "category": "subscription"}
                         for p in data["plans"]]
        new = json.dumps(doc, indent=2, ensure_ascii=False)
        return src[:m.start(2)] + new + src[m.end(2):]
    raise SystemExit(f"{page}: no SoftwareApplication JSON-LD")


def build_page(src: str, page: str, data: dict) -> str:
    out = replace_region(src, "plans", plans_html(data), page)
    out = replace_region(out, "cta", cta_html(page, data), page)
    out = offers_jsonld(out, data, page)
    if data.get("trial_days"):
        out = re.sub(r"\b\d+-day free trial", f"{data['trial_days']}-day free trial", out)
    return out


def touch_sitemap(src: str, urls: list[str], today: str) -> str:
    for url in urls:
        src = re.sub(rf"(<loc>{re.escape(url)}</loc><lastmod>)[^<]*(</lastmod>)", rf"\g<1>{today}\2", src)
    return src


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plans", type=Path, default=PLANS)
    ap.add_argument("--check", action="store_true", help="only report pages that are out of date")
    args = ap.parse_args()
    data = json.loads(args.plans.read_text())

    changed = []
    for page, url in PAGES.items():
        path = SITE / page
        src = path.read_text()
        out = build_page(src, page, data)
        if out != src:
            changed.append(url)
            if args.check:
                print(f"out of date: {page}")
            else:
                path.write_text(out)
                print(f"updated: {page}")
    if args.check:
        print("run: python3 _build/build_site.py" if changed else "all pages up to date")
        return 1 if changed else 0
    if changed:
        sm = SITE / "sitemap.xml"
        sm.write_text(touch_sitemap(sm.read_text(), changed, dt.date.today().isoformat()))
    else:
        print("all pages up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
