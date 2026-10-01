"""Scrape the live trimentractors.com site (EN/DE/RU/LV) into data/stock.json.

Run:  python scripts/scrape.py
Then: python scripts/build.py
"""
import datetime
import html
import http.cookiejar
import json
import pathlib
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://www.trimentractors.com"
LANGS = ["en", "de", "ru", "lv"]
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "stock.json"


def session(lang):
    """Each language needs its own PHP session: the item pop-ups follow the session language."""
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (site rebuild scraper)")]
    get = lambda path: op.open(BASE + urllib.parse.quote(path, safe="/?=&%"), timeout=60).read().decode("utf-8", "ignore")
    get(f"/{lang}")
    return get


def text(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in s.split("\n")]
    return "\n".join(l for l in lines if l)


def scrape_lang(lang):
    get = session(lang)
    home = get(f"/{lang}")

    nav = re.findall(r'<li[^>]*><span><a href="([^"]+)"', re.search(r'<div class="nav">(.*?)</div>', home, re.S)[1])
    pages = {"new": nav[0], "stock": nav[1], "about": nav[2]}

    block = home[home.find('<div class="categories">'):home.find('<div class="clear">')]
    cats = []
    for group, part in enumerate(block.split('<div class="line"></div>')):
        for href, cid, name in re.findall(r'<a href="(/[^"]+/1/(\d+)/)"[^>]*><img[^>]*/><br />([^<]+)</a>', part):
            cats.append({"id": int(cid), "group": group, "name": text(name), "old": href})
    by_name = {c["name"]: c["id"] for c in cats}

    stock = get(pages["stock"] + "all")
    items = []
    for sec in re.split(r"<h4>", stock)[1:]:
        cid = by_name[text(sec[:sec.find("</h4>")])]
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", sec, re.S):
            ids = re.findall(r"#id=(\d+)", row)
            if ids:
                cells = [text(c) for c in re.findall(r"<td>(.*?)</td>", row, re.S)]
                items.append({"id": int(ids[0]), "category": cid, "make": cells[0], "model": cells[1],
                              "year": cells[2], "price": cells[3]})

    newest = list(dict.fromkeys(int(i) for i in re.findall(r"#id=(\d+)", get(pages["new"]))))

    about = get(pages["about"])
    team = []
    for p in re.findall(r'<div class="person">(.*?)</div>\s*(?=<div class="person">|</div>)', about, re.S):
        photo = re.search(r'<img src="(/upload/team/[^"]+)"', p)
        lines = text(re.sub(r"<img[^>]*>", "", p)).split("\n")
        user = re.search(r'title="com trimentractors ([^"]+)"', p)
        team.append({
            "name": lines[0], "role": lines[1], "phone": lines[2] if len(lines) > 2 else "",
            "email": f"{user[1]}@trimentractors.com" if user else "",
            "photo": BASE + photo[1] if photo else "",
            "speaks": re.findall(r'/img/(\w\w)\.gif', p),
        })
    gallery = [BASE + u for u in re.findall(r'<a href="(/upload/[^"/]+\.(?:jpe?g|JPE?G))"[^>]*rel="gallery"', about)]

    def detail(it):
        d = get(f"/modules/catalog/ajaxform.php?id={it['id']}")
        right = d[d.find('class="right"'):]
        tables = re.findall(r"<table>(.*?)</table>", right, re.S)
        rows = re.findall(r"<tr><td[^>]*>(.*?)</td>\s*<td>(.*?)</td></tr>", tables[0], re.S) if tables else []
        extra = ""
        if len(tables) > 2:
            extra = text(re.sub(r"<th>.*?</th>", "", tables[1], flags=re.S))
        contact = re.search(r'<span>(.*?)</span><br />\s*(.*?)<br />\s*(\S+@\S+)', tables[-1] if tables else "", re.S)
        video = re.search(r'<iframe[^>]+src="([^"]+)"', d)
        return {
            "id": it["id"],
            "images": [BASE + u for u in re.findall(r'<a href="(/upload/catalog/[^"]+)" rel="lightbox', d)],
            "rows": [[text(k), text(v)] for k, v in rows],
            "extra": extra,
            "contact": {"name": text(contact[1]), "phone": text(contact[2]), "email": text(contact[3])} if contact else None,
            "video": video[1] if video else "",
        }

    with ThreadPoolExecutor(6) as ex:
        details = {d["id"]: d for d in ex.map(detail, items)}
    return {"pages": pages, "cats": cats, "items": items, "newest": newest, "team": team,
            "gallery": gallery, "details": details}


def main():
    with ThreadPoolExecutor(len(LANGS)) as ex:
        raw = dict(zip(LANGS, ex.map(scrape_lang, LANGS)))
    en = raw["en"]

    categories = []
    for c in en["cats"]:
        loc = {l: next(x for x in raw[l]["cats"] if x["id"] == c["id"]) for l in LANGS}
        categories.append({"id": c["id"], "group": c["group"],
                           "name": {l: loc[l]["name"] for l in LANGS},
                           "old": {l: loc[l]["old"] for l in LANGS}})

    items = []
    for it in en["items"]:
        d = {l: raw[l]["details"][it["id"]] for l in LANGS}
        specs = []
        for i, (key, value) in enumerate(d["en"]["rows"]):
            labels = {l: (d[l]["rows"][i][0] if i < len(d[l]["rows"]) else key) for l in LANGS}
            if value:
                specs.append({"key": key, "value": value, "label": labels})
        items.append({**it, "images": d["en"]["images"], "specs": specs,
                      "extra": {l: d[l]["extra"] for l in LANGS},
                      "contact": d["en"]["contact"], "video": d["en"]["video"]})

    team = en["team"]
    for i, person in enumerate(team):
        person["role"] = {l: raw[l]["team"][i]["role"] if i < len(raw[l]["team"]) else person["role"] for l in LANGS}

    data = {
        "scraped": datetime.date.today().isoformat(),
        "old_pages": {l: raw[l]["pages"] for l in LANGS},
        "categories": categories,
        "newest": en["newest"],
        "team": team,
        "gallery": en["gallery"],
        "items": items,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(categories)} categories, {len(items)} items, {len(team)} people, {len(data['gallery'])} gallery photos")


if __name__ == "__main__":
    main()
