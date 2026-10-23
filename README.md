# Delta Point
Delta Point — Shopify analytics integration. The website at https://deltapoint.io (GitHub Pages).

The pages are hand-written HTML. `_build/build_site.py` fills in the parts that must be the same
everywhere: the menu and footer (every page), the list on /resources/, and prices, trial length and the
hero button from the app's plans file (data-platform repo: `webhook_receiver/legal/plans.json`). It also
writes sitemap.xml and checks every internal link:

```
python3 _build/build_site.py           # after any change: menu, footer, prices, sitemap
python3 _build/build_site.py --check   # exit 1 if a page is out of date or a link is broken
```

It reads `~/data-platform` (two folders up from this repo), or pass `--plans <path>`.
Set `SHOPIFY_LISTING` in the script once the App Store listing is live: the hero then shows "Install on Shopify".
Shopify's Managed Pricing plans are set by hand in the Partner Dashboard: keep them equal to plans.json.

New guide or tool: copy an existing page (keep its `<!-- build:nav -->` and `<!-- build:footer -->` markers),
add it to `RESOURCES` in the script, run it. The top menu stays as it is: guides go on /resources/.
