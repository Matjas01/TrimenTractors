"""Checks the built site: internal links, titles, descriptions, headings, hreflang, JSON-LD, sitemap.

    python scripts/check.py
"""
import collections
import json
import pathlib
import posixpath
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
LANGS = ["en", "de", "ru", "lv"]
problems = []


def page_files():
    for lang in LANGS:
        for f in (ROOT / lang).rglob("index.html"):
            html = f.read_text(encoding="utf-8")
            if 'http-equiv="refresh"' in html:  # redirect from an old URL
                continue
            yield f, html


def resolve(page, href):
    path = urllib.parse.unquote(href.split("#")[0].split("?")[0])
    if not path:
        return True
    base = posixpath.dirname(page.relative_to(ROOT).as_posix())
    target = ROOT / posixpath.normpath(posixpath.join(base, path))
    return (target / "index.html").exists() if path.endswith("/") or target.is_dir() else target.exists()


titles = collections.defaultdict(list)
descs = collections.defaultdict(list)
pages = 0
for f, html in page_files():
    pages += 1
    rel = f.relative_to(ROOT).as_posix()
    for href in re.findall(r'(?:href|src)="([^"]+)"', html):
        if re.match(r"(https?:|mailto:|tel:|#|data:)", href):
            continue
        if not resolve(f, href):
            problems.append(f"{rel}: broken link {href}")
    title = re.search(r"<title>(.*?)</title>", html)
    desc = re.search(r'<meta name="description" content="([^"]*)"', html)
    if not title:
        problems.append(f"{rel}: no <title>")
    else:
        titles[title[1]].append(rel)
    if not desc or not 50 <= len(desc[1]) <= 320:
        problems.append(f"{rel}: description missing or odd length")
    else:
        descs[desc[1]].append(rel)
    if html.count("<h1") != 1:
        problems.append(f"{rel}: {html.count('<h1')} h1 elements")
    if 'rel="canonical"' not in html:
        problems.append(f"{rel}: no canonical")
    langs = re.findall(r'hreflang="([a-z-]+)" href=', html)
    if sorted(set(langs)) != sorted(LANGS + ["x-default"]):
        problems.append(f"{rel}: hreflang set {langs}")
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            json.loads(block)
        except ValueError as e:
            problems.append(f"{rel}: bad JSON-LD ({e})")
    for img in re.findall(r"<img [^>]*>", html):
        if "alt=" not in img:
            problems.append(f"{rel}: image without alt")

for text, where in titles.items():
    if len(where) > 1:
        problems.append(f"duplicate title on {len(where)} pages: {text}")
for text, where in descs.items():
    if len(where) > 1:
        problems.append(f"duplicate description on {len(where)} pages: {text[:60]}")

sitemap = ET.parse(ROOT / "sitemap.xml").getroot()
ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
locs = [u.find("s:loc", ns).text for u in sitemap.findall("s:url", ns)]
if len(locs) != pages:
    problems.append(f"sitemap has {len(locs)} URLs, site has {pages} pages")

print(f"{pages} pages checked, {len(locs)} sitemap URLs")
for p in problems[:60]:
    print(" -", p)
print("OK" if not problems else f"{len(problems)} problems")
sys.exit(1 if problems else 0)
