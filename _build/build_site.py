#!/usr/bin/env python3
"""Fill the generated parts of the website and check its links.

The pages are hand-written HTML. Only these parts come from here, so each
lives in one place:
  <!-- build:nav --> / <!-- build:footer -->       the same menu and footer on every page
  <!-- build:resources -->                         the list on /resources/ (RESOURCES below)
  <!-- build:plans --> / <!-- build:cta -->        pricing cards and hero button, from the app's
  the SoftwareApplication JSON-LD "offers"           plans file (data-platform:
  "<N>-day free trial"                               webhook_receiver/legal/plans.json)
  sitemap.xml                                        every page; <lastmod> today when it changed
Then every internal link (href/src starting with / or #) must point to a page
that exists, and a #fragment to an id on that page.

  python3 _build/build_site.py            write the pages
  python3 _build/build_site.py --check    exit 1 if a page is out of date or a link is broken (CI)
  python3 _build/build_site.py --plans <path to plans.json>

New page: copy one, keep its <!-- build:nav --> and <!-- build:footer --> markers,
add it to RESOURCES if it is a guide or tool, run this script.
Shopify's Managed Pricing plans are set by hand in the Partner Dashboard
(Shopify has no API to write them): keep them equal to plans.json.
Files under _build/ are not published (GitHub Pages skips folders starting with _).
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import posixpath
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
BASE = "https://deltapoint.io"
PLANS = SITE.parent.parent / "data-platform" / "webhook_receiver" / "legal" / "plans.json"
FEATURED = "growth"
SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}
# The app's Shopify App Store page. Empty until the listing is approved: the
# hero then offers early access by email instead of an install button.
SHOPIFY_LISTING = ""
EARLY_ACCESS = "mailto:info@wave-3.com?subject=Delta%20Point%20early%20access"

# Menu: (label, href, shown on phones). Guides and tools go on /resources/, not here.
NAV = [("Features", "/#features", False), ("Pricing", "/#pricing", True),
       ("FAQ", "/#faq", False), ("Resources", "/resources/", True)]
FOOTER = [("Resources", "/resources/"), ("Shopify app", "/shopify/"), ("Privacy", "/privacy.html"),
          ("Terms", "https://webhooks.deltapoint.io/legal/terms"),
          ("Data Processing Agreement", "https://webhooks.deltapoint.io/legal/dpa"),
          ("Sub-processors", "https://webhooks.deltapoint.io/legal/subprocessors")]
# /resources/: (href, kind, title, one-line description), newest first within a kind.
RESOURCES = [
    ("/roas-calculator/", "Free tool", "ROAS & MER calculator",
     "Blended ROAS, break-even ROAS, cost per order and profit after ad spend, and how much more "
     "revenue your ad platforms claim than your store made."),
    ("/guides/multi-store-shopify-reporting/", "Guide", "Reporting across several Shopify stores, countries and currencies",
     "Daily exchange rates, time zones, double counting and blended ROAS per market: one honest number "
     "for a business that sells in many countries."),
]
SITEMAP_PRIORITY = {"/": "1.0", "/shopify/": "0.8", "/roas-calculator/": "0.7", "/resources/": "0.6",
                    "/privacy.html": "0.3"}


def money(n: int, cur: str) -> str:
    return f"{SYMBOLS.get(cur, cur + ' ')}{n:,}"


def nav_html(url: str) -> str:
    links = []
    for label, href, phone in NAV:
        current = ' aria-current="page"' if href == url or (href == "/resources/" and url.startswith(("/guides/", "/roas-calculator/"))) else ""
        links.append(f'        <a{"" if phone else " class=\"wide\""} href="{href}"{current}>{label}</a>')
    links.append('        <a href="https://bi.deltapoint.io" class="login">Client login</a>')
    return ("  <nav>\n    <div class=\"nav-inner\">\n"
            "      <a href=\"/\" class=\"logo\">\n"
            "        <img src=\"/icon.png\" alt=\"\" width=\"32\" height=\"32\">\n"
            "        <span>Delta Point</span>\n      </a>\n"
            "      <div class=\"nav-links\">\n" + "\n".join(links) + "\n      </div>\n    </div>\n  </nav>")


def footer_html() -> str:
    links = "\n".join(f'        <a href="{href}">{html.escape(label)}</a>' for label, href in FOOTER)
    return ("  <footer>\n    <div class=\"footer-inner\">\n"
            "      <address class=\"company\">\n"
            "        <strong>Delta Point by Wave3, d. o. o.</strong><br>\n"
            "        Einspielerjeva ulica 13, 1000 Ljubljana, Slovenia<br>\n"
            "        Reg. no. 9022163000 &middot; VAT ID SI62933671<br>\n"
            "        <a href=\"mailto:info@wave-3.com\">info@wave-3.com</a>\n"
            "      </address>\n"
            "      <div class=\"footer-links\">\n" + links + "\n      </div>\n    </div>\n  </footer>")


def resources_html() -> str:
    cards = "\n".join(
        f'      <a class="card resource" href="{href}">\n'
        f'        <div class="kind">{html.escape(kind)}</div>\n'
        f'        <h2>{html.escape(title)}</h2>\n'
        f'        <p>{html.escape(text)}</p>\n'
        f'      </a>' for href, kind, title, text in RESOURCES)
    return '    <div class="resources">\n' + cards + "\n    </div>"


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


def cta_html(url: str, data: dict) -> str:
    trial = data.get("trial_days")
    if SHOPIFY_LISTING:
        button = f'<a class="btn" href="{html.escape(SHOPIFY_LISTING)}">Install on Shopify</a>'
        soon = "Free plan" + (f", {trial}-day free trial on paid plans." if trial else ".")
    else:
        button = f'<a class="btn" href="{EARLY_ACCESS}">Get early access</a>'
        soon = "Coming soon to the Shopify App Store."
    if url == "/":
        return ('    <div class="actions">\n'
                f'      {button}\n'
                '      <a class="btn btn-ghost" href="#pricing">See pricing</a>\n'
                '    </div>\n'
                f'    <p class="soon">{soon}</p>')
    return f'    {button}\n    <p class="soon">{soon}</p>'


def has_region(src: str, name: str) -> bool:
    return f"<!-- build:{name}" in src


def replace_region(src: str, name: str, body: str, page: str) -> str:
    pat = re.compile(rf"(<!-- build:{name}\b[^>]*-->\n)(.*?)(\n\s*<!-- /build:{name} -->)", re.S)
    if not pat.search(src):
        raise SystemExit(f"{page}: no <!-- build:{name} --> ... <!-- /build:{name} --> region")
    return pat.sub(lambda m: m.group(1) + body + m.group(3), src, count=1)


def offers_jsonld(src: str, data: dict) -> str:
    pat = re.compile(r'(<script type="application/ld\+json">\n)(.*?)(\n</script>)', re.S)
    for m in pat.finditer(src):
        doc = json.loads(m.group(2))
        if doc.get("@type") != "SoftwareApplication":
            continue
        doc["offers"] = [{"@type": "Offer", "name": p["name"], "price": str(p["price_month"]),
                          "priceCurrency": data["currency"], "category": "subscription"}
                         for p in data["plans"]]
        return src[:m.start(2)] + json.dumps(doc, indent=2, ensure_ascii=False) + src[m.end(2):]
    return src


def build_page(src: str, page: str, url: str, data: dict) -> str:
    out = replace_region(src, "nav", nav_html(url), page)
    out = replace_region(out, "footer", footer_html(), page)
    if has_region(out, "resources"):
        out = replace_region(out, "resources", resources_html(), page)
    if has_region(out, "plans"):
        out = replace_region(out, "plans", plans_html(data), page)
    if has_region(out, "cta"):
        out = replace_region(out, "cta", cta_html(url, data), page)
    out = offers_jsonld(out, data)
    if data.get("trial_days"):
        out = re.sub(r"\b\d+-day free trial", f"{data['trial_days']}-day free trial", out)
    return out


def url_of(page: str) -> str:
    if page == "index.html":
        return "/"
    return "/" + (page[:-len("index.html")] if page.endswith("/index.html") else page)


def page_of(url: str) -> str:
    path = url.lstrip("/")
    return path + "index.html" if path == "" or path.endswith("/") else path


def sitemap_xml(old: str, urls: list[str], changed: set[str], today: str) -> str:
    known = dict(re.findall(r"<loc>([^<]*)</loc><lastmod>([^<]*)</lastmod>", old))
    rows = []
    for url in urls:
        loc = BASE + url
        lastmod = today if url in changed or loc not in known else known[loc]
        rows.append(f"  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod>"
                    f"<priority>{SITEMAP_PRIORITY.get(url, '0.6')}</priority></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(rows) + "\n</urlset>\n")


def broken_links(pages: dict[str, str]) -> list[str]:
    ids = {p: set(re.findall(r'\sid="([^"]+)"', s)) for p, s in pages.items()}
    errors = []
    for page, src in pages.items():
        for target in re.findall(r'(?:href|src)="([^"]+)"', src):
            if target.startswith(("http://", "https://", "mailto:", "data:")):
                continue
            path, _, frag = target.partition("#")
            path = path.split("?")[0]
            if path and not path.startswith("/"):  # relative: from the page's own folder
                path = "/" + posixpath.normpath(posixpath.join(posixpath.dirname(page), path)) + ("/" if path.endswith("/") else "")
            dest = page if not path else page_of(path)
            if not (SITE / dest).is_file():
                errors.append(f"{page}: {target} -> no such page")
            elif frag and dest.endswith(".html") and frag not in ids.get(dest, set()):
                errors.append(f"{page}: {target} -> no id=\"{frag}\" on {dest}")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plans", type=Path, default=PLANS)
    ap.add_argument("--check", action="store_true", help="only report, change nothing")
    args = ap.parse_args()
    data = json.loads(args.plans.read_text())

    files = sorted(p for p in SITE.rglob("*.html") if not any(part.startswith(("_", ".")) for part in p.relative_to(SITE).parts))
    pages, changed = {}, set()
    for path in files:
        page = path.relative_to(SITE).as_posix()
        src = path.read_text()
        out = build_page(src, page, url_of(page), data)
        pages[page] = out
        if out != src:
            changed.add(url_of(page))
            print(f"{'out of date' if args.check else 'updated'}: {page}")
            if not args.check:
                path.write_text(out)

    urls = sorted((url_of(p) for p in pages), key=lambda u: (u != "/", u))
    sm = SITE / "sitemap.xml"
    old = sm.read_text() if sm.exists() else ""
    new = sitemap_xml(old, urls, changed, dt.date.today().isoformat())
    if new != old and (changed or set(re.findall(r"<loc>([^<]*)</loc>", old)) != {BASE + u for u in urls}):
        print(f"{'out of date' if args.check else 'updated'}: sitemap.xml")
        changed.add("sitemap")
        if not args.check:
            sm.write_text(new)

    errors = broken_links(pages)
    for e in errors:
        print("BROKEN LINK", e)
    if not changed and not errors:
        print(f"all {len(pages)} pages up to date, links ok")
    if args.check and changed:
        print("run: python3 _build/build_site.py")
    return 1 if errors or (args.check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
