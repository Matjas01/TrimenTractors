# SEO review: trimentractors.com and the new site

Checked on 1 October 2026. Sources: the live site's HTML and headers, a rendered page in a browser, and a Google `site:` search. There was no Search Console or analytics access, and the PageSpeed Insights API was over its daily quota, so page weight was measured by downloading the page and its files.

## Summary

The old site's biggest problem is that **individual machines cannot appear in Google at all**. Every listing opens in a JavaScript pop-up at an address like `/en/for_sale/1/all#id=3065`. Google ignores everything after `#`, so the 147 listings have no pages of their own. A `site:trimentractors.com` search returns only category pages and the About page. Searches for the company name are led by directories (Lursoft, Firmas.lv, D&B, Autoline, Machinetrack) instead of the company's own site.

On top of that, the site is not mobile-friendly, no page has an H1 or a meta description, and the four language versions are not linked to each other for search engines.

The rebuild in this repository fixes these problems in the code. A few remaining steps can only be done when the new site goes live on the real domain (see "Launch checklist").

**Top issues on the old site**

1. Machines and work tools have no indexable pages (pop-ups behind `#id=`).
2. Not mobile-friendly: no viewport tag, fixed-width layout.
3. No H1, no meta descriptions, and duplicate titles such as "Trimen Tractors - For sale".
4. Language versions are not connected with hreflang, and the German and Russian pages contain Latvian text and misspelled category names.
5. The same pages are served on `www.` and without `www.`, and Google has indexed both, plus some `http://` addresses.

## Technical findings (old site)

| Issue | Impact | Evidence | Fix in the rebuild |
|---|---|---|---|
| Listings exist only as pop-ups at `#id=NNNN`, loaded from `/modules/catalog/ajaxform.php` | High | Stock list links are `href="#id=3065"`; a `site:` search shows no machine pages | Every listing has its own page in each language, e.g. `/en/dozers/caterpillar-d3-lgp-3065/` |
| No XML sitemap | High | `/sitemap.xml` returns 404; robots.txt has no `Sitemap:` line | `sitemap.xml` with all 692 pages and their language alternates; robots.txt points to it |
| `www` and non-`www` both return 200 | Medium | `https://trimentractors.com/` and `https://www.trimentractors.com/` both serve the site; Google lists both variants | Canonical tags point to `https://www.trimentractors.com/...`. Add a server 301 from the bare domain at launch |
| No canonical tags | Medium | Not present on any page checked | Self-referencing canonical on every page |
| No mobile viewport, fixed 880 px layout | High | No `<meta name="viewport">`; checked in a rendered browser | Responsive layout, tested at 375 px and 960 px with no sideways scrolling |
| Slow, script-heavy pages | Medium | Homepage: 52 requests, about 926 KB, a 515 KB background photo, 7 scripts loaded before the content (jQuery and plugins). Stock list HTML is 227 KB, mostly a dropdown of every model ever listed | No jQuery; one small CSS and one small JS file, deferred. Listing photos load lazily |
| HTML not cacheable, session cookie on every page | Low | `Cache-Control: no-store`, `Set-Cookie: PHPSESSID` on every response | Static files; GitHub Pages and most hosts cache them |
| Item language depends on a server session, not the URL | Medium | Opening a pop-up without first visiting `/en` returned German text | Each language has its own URLs and fully translated pages |

## On-page findings (old site)

| Issue | Impact | Evidence | Fix in the rebuild |
|---|---|---|---|
| No H1 on any page | Medium | 0 H1 on the 10 pages checked; headings start at H3/H4 | One H1 per page (checked on all 692 pages) |
| No meta descriptions | Medium | None on the 10 pages checked | Unique description on every page, built from the listing's specs and price |
| Duplicate, brand-first titles | Medium | Home and stock list are both "Trimen Tractors - For sale" | Unique titles starting with the product or category, e.g. "Caterpillar D3 LGP dozer \| Trimen Tractors" |
| No `lang` attribute, no hreflang | High for DE/RU/LV | `<html>` has no `lang`; no `hreflang` links | `lang` on every page; hreflang for en, de, ru, lv and x-default on every page and in the sitemap |
| Mixed-language and misspelled text | Medium | German and Russian item notes contain Latvian text (e.g. "Iegādāts jauns 01/2026" on the German page). Russian category names use Latin look-alike letters ("Mинипогрузчики", "Kатки", "Tелескопическиe Погрузчики"), so they don't match what people type. German misspellings: "Gabelstabler", "Tieflöffels", "Asfalt fertiger" | Category names, labels and the dealer notes rewritten in each language |
| Images without alt text | Low | 33 of 37 images on the homepage have empty alt | Listing photos carry the product name and photo number |
| No structured data | Medium | No JSON-LD or microdata, checked in a rendered browser | `Product` + `Offer` (price, EUR, VAT excluded) on listings, `BreadcrumbList` on inner pages, `LocalBusiness` with address, coordinates, phone and sales contacts |
| Category icons are 72×72 px images | Low | `/upload/catalog/top_2.1.jpg` etc. are 72×72 | Replaced with photos of current stock |

## Content findings

* **Thin pages.** Category pages on the old site are tables of make, model, year and price. The new category pages have an intro, filters, and cards linking to full listing pages.
* **Listing descriptions.** The old pop-ups had a spec table and, for 30 of 149 items, a short note. Each new listing page has a written description in all four languages, built from its specifications, plus the dealer's note translated by hand.
* **Messy source data.** On the old site the manufacturer field sometimes holds a product type ("Bale Clamp", "RIPPER TOOTH") and the year field holds stock numbers for work tools. Listings with unclear data were checked against their photos; 70 listings are corrected in `data/overrides.json` and 2 (a duplicate and an empty placeholder) are hidden.
* **Trust signals.** Company details (registration and VAT numbers, bank accounts), named salespeople with photos and languages spoken, and photos of the yard are all on the About page.

## What the new site does for search

* 147 listing pages × 4 languages, 20 category pages, 3 group pages (Machinery, Trucks, Work tools), stock search and About page: 692 pages in total.
* URL structure: `/{language}/{category}/{product}-{id}/`. Russian slugs are transliterated so links stay readable when shared.
* Redirect pages for the old addresses, including the ones Google already has indexed, e.g. `/de/zu_verkaufen/agrarfahrzeuge_/1/16/` → `/de/landmaschinen/` and `/ru/торговля/бульдозеры/1/2/` → `/ru/buldozery/`. Old links to a pop-up (`/en/for_sale/1/all#id=3065`) land on the new listing page.
* `scripts/check.py` checks every built page for broken internal links, missing or duplicate titles and descriptions, H1 count, canonical, hreflang, JSON-LD validity and sitemap coverage. The current build passes.

## Launch checklist

The GitHub Pages preview is built with `noindex` on purpose, so Google does not index a copy that later competes with the real domain.

**Critical (when switching the domain)**

1. Build without `noindex`: `python scripts/build.py --production`.
2. Point `www.trimentractors.com` at the new site, and 301-redirect `trimentractors.com` and all `http://` addresses to `https://www.trimentractors.com/`.
3. If the host supports real redirects (Netlify, Cloudflare, Apache, nginx), add 301s for the old URL patterns. The redirect pages in the repository are a fallback for hosts like GitHub Pages that cannot send 301s.
4. Add the site to Google Search Console and Bing Webmaster Tools, submit `sitemap.xml`, and check the Pages report and a few URLs with URL Inspection in the first weeks to confirm the language versions are indexed.

**High impact**

5. Host the photos on the new site's domain. They are currently loaded from `trimentractors.com/upload/...`, which stops working if the old server is switched off.
6. Keep stock current. Sold machines should disappear from the site (a 404 is fine for sold items) and new ones should appear within a day. Today that means re-running `scripts/scrape.py` and `scripts/build.py`; long term, an admin tool or CMS that writes `data/stock.json`.
7. Set up or update the Google Business Profile with the same name, address and phone as the site (AS Trimen Tractors, "Valodzes", Klīves, LV-2107, +371 67247977), and add opening hours to both.

**Quick wins**

8. Link each marketplace listing (Mascus, Autoline, Machinetrack and others) to the matching page on the new site.
9. Send a vector version of the logo (SVG, AI, EPS or PDF). The current one is a 147×58 PNG and looks soft on high-resolution screens.
10. Re-add analytics (the old site used Google Tag Manager, container GTM-55N5C5) and track phone and email clicks on listing pages.

**Long term**

11. Write short buying guides that match how people search for work tools, e.g. an explanation of coupler systems (S40 to S80, NTP10/NTP20, CW20 to CW40) with links to matching buckets.
12. Serve photos in WebP at several sizes; the largest listing photos are 800 px wide, which limits how big they can be shown.

## Keywords to target

No search volume data was available (no Search Console, Ahrefs or Semrush access). These are the terms each page type is written around; check them against real query data once Search Console has a few weeks of data.

| Page | English | German | Russian | Latvian |
|---|---|---|---|---|
| Home | used construction machinery Latvia | gebrauchte Baumaschinen Lettland | б/у спецтехника Латвия | lietota būvtehnika |
| Machinery | used construction and farm machinery | gebrauchte Bau- und Landmaschinen | б/у строительная техника | lietota tehnika pārdošanā |
| Work tools | excavator buckets for sale, quick couplers | Tieflöffel gebraucht, Schnellwechsler | ковши для экскаватора б/у, квик-каплер | ekskavatora kausi, ātrā sakabe |
| Category | used wheel loaders, ditch cleaning buckets | gebrauchte Radlader, Grabenräumlöffel | б/у фронтальные погрузчики, планировочный ковш | lietoti frontālie iekrāvēji, planējamais kauss |
| Listing | make + model + type, e.g. "Caterpillar D3 LGP dozer" | "Planierraupe Caterpillar D3 LGP" | "Бульдозер Caterpillar D3 LGP" | "Buldozers Caterpillar D3 LGP" |

Listing pages target the long tail: make + model searches have little competition, and buyers using them are close to a decision.
