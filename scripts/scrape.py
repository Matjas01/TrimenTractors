"""Scrape trimentractors.com stock into data/stock.json (English)."""
import json, re, html, pathlib, urllib.request, http.cookiejar
from concurrent.futures import ThreadPoolExecutor

BASE = "https://www.trimentractors.com"
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
op.addheaders = [("User-Agent", "Mozilla/5.0")]
get = lambda p: op.open(BASE + p, timeout=30).read().decode("utf-8", "ignore")
txt = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()

home = get("/en")  # sets English session
cats = []
for img, name in re.findall(r'<a href="/en/for_sale/[^"]+/\d+/\d+/"[^>]*><img src="([^"]+)"[^>]*/><br />([^<]+)</a>', home):
    cats.append({"name": name.strip(), "image": BASE + img})

stock = get("/en/for_sale/1/all")
items = []
for sec in re.split(r"<h4>", stock)[1:]:
    cat = txt(sec[: sec.find("</h4>")])
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", sec, re.S):
        ids = re.findall(r"#id=(\d+)", row)
        if not ids: continue
        cells = [txt(c) for c in re.findall(r"<td>(.*?)</td>", row, re.S)]
        items.append({"id": int(ids[0]), "category": cat, "make": cells[0], "model": cells[1],
                      "year": cells[2], "price": cells[3]})

def detail(it):
    d = get(f"/modules/catalog/ajaxform.php?id={it['id']}")
    it["images"] = [BASE + u for u in re.findall(r'<a href="(/upload/catalog/[^"]+)" rel="lightbox', d)]
    right = d[d.find('class="right"'):]
    specs, extra = [], ""
    tables = re.findall(r"<table>(.*?)</table>", right, re.S)
    if tables:
        for k, v in re.findall(r"<tr><td[^>]*>(.*?)</td>\s*<td>(.*?)</td></tr>", tables[0], re.S):
            if txt(v): specs.append([txt(k), txt(v)])
    if len(tables) > 2: extra = txt(re.sub(r"<th>.*?</th>", "", tables[1]))
    it["specs"], it["extra"] = specs, extra
    c = tables[-1] if tables else ""
    m = re.search(r"<span>(.*?)</span><br />\s*(.*?)<br />\s*(\S+@\S+)", c, re.S)
    it["contact"] = {"name": txt(m[1]), "phone": txt(m[2]), "email": txt(m[3])} if m else None
    return it

newest = [int(i) for i in dict.fromkeys(re.findall(r"#id=(\d+)", get("/en/new/2/")))]

with ThreadPoolExecutor(8) as ex:
    items = list(ex.map(detail, items))

out = pathlib.Path(__file__).resolve().parent.parent / "data" / "stock.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({"categories": cats, "newest": newest, "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(cats), "categories,", len(items), "items")
