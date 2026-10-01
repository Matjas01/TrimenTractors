"""Generate the static site from data/stock.json and data/overrides.json.

    python scripts/build.py                 # preview build: every page carries noindex
    python scripts/build.py --production    # live build for www.trimentractors.com

Output goes to the repository root (en/, de/, ru/, lv/, index.html, sitemap.xml ...),
which is what GitHub Pages serves.
"""
import argparse
import datetime
import hashlib
import html
import json
import pathlib
import posixpath
import re
import shutil
import unicodedata
import urllib.parse

from content import (COMPANY, COUNTRY, GROUPS, CATEGORIES, LANG_NAMES, LANGS, OG_LOCALE, PAGE_SLUGS,
                     ROLES, SPEAKS, SPEC_UNITS, SPECS, T, TYPES, UNITS, VALUE_I18N)

ROOT = pathlib.Path(__file__).resolve().parent.parent
GENERATED = LANGS + ["index.html", "404.html", "sitemap.xml", "robots.txt"]
KIND = {0: "machine", 1: "vehicle", 2: "tool"}
NBSP = " "

# Photos from the old site's About page, picked by file name.
HERO_MAIN, HERO_SIDE = "DSC_1049", ["2016-03-04-10-07-46", "20200525_171056"]
TOOLS_PHOTO, YARD_PHOTO, ABOUT_PHOTO = "IMG_2889", "V2lHUK2749_22", "m3kmYpYVIK_23"
ABOUT_GALLERY = ["DSC_1049", "DSC01197", "2016-03-04-10-07-46", "DSC09227", "IMG_2742", "IMG_2889",
                 "20200525_171056", "DSC_0100", "DSC_0295", "DSC_0357", "DSC_1024", "DSC_6982"]

MAKES = {"MANTOVANIBNNE": "Mantovanibenne", "SE Equipment ( Sweden )": "SE Equipment",
         "Atlas Weyhausen GMBH": "Atlas Weyhausen", "ZFE GmbH": "ZFE", "Winkelbauer Maschinenbau": "Winkelbauer",
         "Terastyo T. Salminen Oy": "Terästyö T. Salminen", "RF-System AB": "RF-System"}
NOT_MAKES = {"", "other", "vibrating compaction bucket", "ātrā sakabe", "bale clamp", "ripper tooth", "adapter",
             "bobcat / skid steer"}
KEEP_UPPER = {"JCB", "MAN", "SMP", "PMC", "MST", "MB", "CASE"}
HINGE_LIKE = re.compile(r"\b(NTP\d+|CW\d+|S\d{2}|B\d{2}|SW\d+|BM|GJ\d+|MS\d+|SMP\d|FL\d+)\b", re.I)
CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))


# ---------------------------------------------------------------- helpers

def esc(s):
    return html.escape(str(s), quote=True)


def forms(lang, value, n):
    if isinstance(value, str):
        return value.format(n=n)
    if lang == "ru":
        i = 0 if n % 10 == 1 and n % 100 != 11 else 1 if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 2
    elif lang == "lv":
        i = 0 if n % 10 == 1 and n % 100 != 11 else 1
    else:
        i = 0 if n == 1 else 1
    return value[min(i, len(value) - 1)].format(n=n)


def t(lang, key, **kw):
    value = T[lang][key]
    if "n" in kw and not isinstance(value, str):
        return forms(lang, value, kw["n"])
    return value.format(**kw) if kw else value


def slugify(s):
    s = "".join(CYR.get(ch, ch) for ch in s.lower())
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def cap(s):
    return s[:1].upper() + s[1:] if s else s


def rel(cur, target):
    """Relative link from the page directory `cur` to the site path `target`."""
    base = cur.rstrip("/") or "."
    is_dir = target == "" or target.endswith("/")
    r = posixpath.relpath(target.rstrip("/") or ".", base)
    if is_dir:
        return "./" if r == "." else r + "/"
    return r


def img(url):
    return urllib.parse.quote(url, safe=":/()%")


def medium(url):
    return re.sub(r"/upload/catalog/5", "/upload/catalog/3", url, count=1)


def thumb(url):
    return re.sub(r"/upload/catalog/5", "/upload/catalog/", url, count=1)


def group_digits(int_part, lang):
    sep = {"en": ",", "de": "."}.get(lang, NBSP)
    out = ""
    while len(int_part) > 3:
        out = sep + int_part[-3:] + out
        int_part = int_part[:-3]
    return int_part + out


def fmt_number(s, lang, group_small=False):
    """'1,109' / '0,8' / '4.8' / '1009633' -> localized string."""
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(,\d{3})+", s) or s.count(".") > 1:
        s = re.sub(r"[,.]", "", s)
    s = s.replace(",", ".")
    int_part, _, frac = s.partition(".")
    if len(int_part) > 4 or (group_small and len(int_part) == 4):
        int_part = group_digits(int_part, lang)
    return int_part + (("." if lang == "en" else ",") + frac if frac else "")


def fmt_price(n, lang):
    return group_digits(str(n), lang) + NBSP + "EUR"


def unit(u, lang):
    key = {"m³": "m3", "kw": "kW", "KW": "kW", "T": "t"}.get(u, u)
    return UNITS.get(key, {}).get(lang, key)


def with_unit(number, u, lang):
    if not u:
        return number
    if u == "%":
        return number + ("%" if lang == "en" else NBSP + "%")
    return number + NBSP + unit(u, lang)


NUM_UNIT = re.compile(r"^\s*(\d[\d.,]*)\s*(mm|kg|km|kW|cm3|m3|m³|l|t|T|h|%|m)?\s*$")
RANGE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*(t|T|mm|kg)?\s*$")
FREE_UNIT = re.compile(r"(\d)\s*(mm|kg|m3|m³|l)\b")


def fmt_value(key, raw, lang):
    v = re.sub(r"\s+", " ", raw).strip()
    if key in ("Year", "Stock number", "Model", "Manufacturer"):
        return v
    if v.lower() in VALUE_I18N:
        return VALUE_I18N[v.lower()][lang]
    m = RANGE.match(v)
    if m and key in ("Machine weight", "Capacity", "Weight"):
        return f"{fmt_number(m[1], lang)}–{fmt_number(m[2], lang)}" + NBSP + unit(m[3] or "t", lang)
    m = NUM_UNIT.match(v)
    if m:
        u = m[2] or SPEC_UNITS.get(key, "")
        small = key in ("Motor hours", "KM", "Weight", "Max Load", "Payload", "Engine capacity cm3")
        return with_unit(fmt_number(m[1], lang, small), u, lang)
    v = re.sub(r"(?<=\w) - (?=\w)", "–", v)
    if key == "Hinges":
        v = re.sub(r"\s*/\s*", " / ", v)
    return FREE_UNIT.sub(lambda mm: mm[1] + NBSP + unit(mm[2], lang), v)


def number_of(value):
    m = re.search(r"\d[\d.,]*", value or "")
    if not m:
        return None
    s = m[0]
    if re.fullmatch(r"\d{1,3}(,\d{3})+", s):
        s = s.replace(",", "")
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def jsonld(obj):
    return ('<script type="application/ld+json">' +
            json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>")


# ---------------------------------------------------------------- data model

class Site:
    def __init__(self, site_url, production):
        self.url = site_url.rstrip("/")
        self.production = production
        self.data = json.loads((ROOT / "data" / "stock.json").read_text(encoding="utf-8"))
        self.ovr = json.loads((ROOT / "data" / "overrides.json").read_text(encoding="utf-8"))
        self.today = datetime.date.today().isoformat()
        self.year = datetime.date.today().year
        self.team = self.data["team"]
        self.gallery = self.data["gallery"]
        self.cat_group = {c["id"]: c["group"] for c in self.data["categories"]}
        self.cat_scraped = {c["id"]: c for c in self.data["categories"]}
        self.old_pages = self.data["old_pages"]
        self.items = self.build_items()
        self.by_cat = {}
        for it in self.items:
            self.by_cat.setdefault(it["cat"], []).append(it)
        self.cats_with_items = [cid for cid in self.ordered_cats() if cid in self.by_cat]

    # ---- categories

    def ordered_cats(self):
        return [c["id"] for c in self.data["categories"]]

    def cat(self, cid, field, lang):
        c = CATEGORIES.get(cid)
        if c and field in c:
            return c[field][lang]
        name = self.cat_scraped[cid]["name"][lang]
        return {"slug": slugify(name), "name": name, "one": name.lower(), "h1": name}[field]

    def cat_h1(self, cid, lang):
        c = CATEGORIES.get(cid, {})
        return c["h1"][lang] if "h1" in c else self.cat(cid, "name", lang)

    # ---- paths

    def home_path(self, lang):
        return f"{lang}/"

    def group_path(self, g, lang):
        return f"{lang}/{GROUPS[g]['slug'][lang]}/"

    def cat_path(self, cid, lang):
        return f"{lang}/{self.cat(cid, 'slug', lang)}/"

    def page_path(self, page, lang):
        return f"{lang}/{PAGE_SLUGS[page][lang]}/"

    def abs(self, path):
        return f"{self.url}/{path}"

    def photo(self, key):
        return next((g for g in self.gallery if key in g), self.gallery[0])

    # ---- items

    def build_items(self):
        hidden = set(self.ovr.get("hidden", []))
        newest = self.data["newest"]
        max_id = max(i["id"] for i in self.data["items"])
        items = []
        for raw in self.data["items"]:
            if raw["id"] in hidden:
                continue
            it = self.prepare(raw)
            it["rank"] = newest.index(raw["id"]) if raw["id"] in newest else len(newest) + max_id - raw["id"]
            items.append(it)
        # identical titles get the stock number (or listing id) appended
        for lang in LANGS:
            seen = {}
            for it in items:
                seen.setdefault(it["full"][lang], []).append(it)
            for same in seen.values():
                if len(same) > 1:
                    for it in same:
                        tag = re.split(r"[:;,]", it["stock_no"])[0].strip() or f"ID {it['id']}"
                        it["full"][lang] += f" ({tag})"
                        it["card"][lang] += f" ({tag})"
        return items

    def prepare(self, raw):
        o = self.ovr.get("items", {}).get(str(raw["id"]), {})
        cid = raw["category"]
        kind = KIND[self.cat_group[cid]]
        specs = {s["key"]: s["value"] for s in raw["specs"]}
        for k in o.get("drop_specs", []):
            specs.pop(k, None)
        specs.update(o.get("add_specs", {}))
        spec_lang = {k: (v if isinstance(v, dict) else {l: v for l in LANGS}) for k, v in o.get("specs", {}).items()}

        make = o["make"] if "make" in o else self.clean_make(raw["make"])
        hinge = specs.get("Hinges", "").strip()
        model = o["model"] if "model" in o else self.clean_model(raw["model"], hinge, kind)

        def num(key):
            return number_of(specs.get(key, ""))

        price = int(num("Price EUR Netto") or 0) or None
        gross = int(num("Price EUR Brutto (VAT 21%)") or 0) or None
        year = ""
        if kind != "tool":
            m = re.search(r"(19[5-9]\d|20[0-4]\d)", raw["year"])
            year = raw["year"] if m else ""
        width = specs.get(o.get("size_key", "Width"), "") if not o.get("no_size") else ""
        width_mm = number_of(specs.get("Width", ""))
        if width_mm and re.search(r"\d\s*m\b", specs.get("Width", "")):
            width_mm *= 1000

        it = {
            "id": raw["id"], "cat": cid, "group": self.cat_group[cid], "kind": kind,
            "make": make, "model": model, "type": o.get("type"), "specs": specs, "spec_lang": spec_lang,
            "price": price, "gross": gross, "year": year, "hinge": hinge, "stock_no": specs.get("Stock number", ""),
            "width_mm": int(width_mm) if width_mm else None, "size": width,
            "hours": num("Motor hours"), "km": num("KM"),
            "images": raw["images"], "contact": raw["contact"], "condition": o.get("condition"),
            "title_override": o.get("title"),
            "notes": {l: self.note(raw, o, l) for l in LANGS},
            "card": {}, "full": {}, "slug": {}, "path": {},
        }
        for lang in LANGS:
            it["card"][lang], it["full"][lang] = self.titles(it, lang)
            it["slug"][lang] = slugify(it["card"][lang])[:70].strip("-") + f"-{raw['id']}"
            it["path"][lang] = f"{self.cat_path(cid, lang)}{it['slug'][lang]}/"
        return it

    @staticmethod
    def clean_make(make):
        make = make.strip()
        if make.lower() in NOT_MAKES:
            return ""
        if make in MAKES:
            return MAKES[make]
        if make.isupper() and make not in KEEP_UPPER:
            return " ".join(w.capitalize() for w in make.split())
        return "Case" if make == "CASE" else make

    @staticmethod
    def clean_model(model, hinge, kind):
        model = model.strip()
        if kind != "tool" or not model:
            return model
        if re.fullmatch(r"\d+\s*mm", model, re.I) or HINGE_LIKE.search(model):
            return ""
        if hinge and re.sub(r"\W", "", model).lower() == re.sub(r"\W", "", hinge).lower():
            return ""
        return model

    def note(self, raw, o, lang):
        src = raw["extra"].get("en", "")
        if "notes" in o:
            want = o.get("notes_src")
            if not want or want == hashlib.sha1(src.encode()).hexdigest()[:10]:
                return o["notes"][lang]
        val = raw["extra"].get(lang, "")
        if lang == "en":
            return src
        if lang == "lv":
            return val or src
        # The old site often kept Latvian or English text in the German and Russian fields.
        if val and val != raw["extra"].get("lv") and val != src and (lang != "ru" or re.search("[а-яА-Я]", val)):
            return val
        return src

    def type_noun(self, it, lang):
        if it["type"] and it["type"] in TYPES:
            return TYPES[it["type"]][lang]
        return self.cat(it["cat"], "one", lang)

    def hinge_text(self, it, lang):
        if "Hinges" in it["spec_lang"]:
            return it["spec_lang"]["Hinges"][lang]
        return fmt_value("Hinges", it["hinge"], lang) if it["hinge"] else ""

    def hinge_short(self, it, lang):
        hinge = self.hinge_text(it, lang)
        if it["make"] and hinge.lower().startswith(it["make"].lower() + " ") and len(hinge) - len(it["make"]) > 4:
            hinge = hinge[len(it["make"]) + 1:]
        return hinge

    @staticmethod
    def hinge_is_text(it):
        """Mounting given as words ("On Forks") rather than a coupler code ("S70")."""
        return it["hinge"].strip().lower() in VALUE_I18N

    def titles(self, it, lang):
        if it["title_override"]:
            return it["title_override"][lang], it["title_override"][lang]
        noun, make, model = self.type_noun(it, lang), it["make"], it["model"]
        core = " ".join(x for x in ([make, model, noun] if lang == "en" else [cap(noun), make, model]) if x)
        core = cap(core)
        if it["kind"] != "tool":
            card = " ".join(x for x in [make, model] if x) if model else core
            return card, core
        size = fmt_value("Width", it["size"], lang) if it["size"] else ""
        hinge = "" if self.hinge_is_text(it) else self.hinge_short(it, lang)
        card = core + (" " + size if size else (" " + hinge if hinge and not model else ""))
        full = card + (", " + hinge if hinge and hinge not in card else "")
        return card, full

    # ---- text about an item

    def spec_value(self, it, key, lang):
        if key in it["spec_lang"]:
            return it["spec_lang"][key][lang]
        if key == "Power":
            kw, hp = it["specs"].get("KW"), it["specs"].get("HP")
            hp_txt = with_unit(fmt_number(str(number_of(hp)).rstrip("0").rstrip("."), lang), "hp", lang) if hp else ""
            if kw:
                kw_txt = with_unit(fmt_number(kw, lang), "kW", lang)
                return kw_txt + (f" ({hp_txt})" if hp_txt else "")
            return hp_txt
        return fmt_value(key, it["specs"][key], lang)

    def spec_rows(self, it, lang):
        s = it["specs"]
        rows = []
        if it["make"]:
            rows.append((SPECS["Manufacturer"][lang], it["make"]))
        if it["model"]:
            rows.append((SPECS["Model"][lang], it["model"]))
        if it["year"]:
            rows.append((SPECS["Year"][lang], it["year"]))
        order = ["Motor hours", "KM", "Weight", "Power"]
        skip = {"Manufacturer", "Model", "Year", "KW", "HP", "Stock number",
                "Price EUR Netto", "Price EUR Brutto (VAT 21%)"}
        keys = [k for k in order if k in s or (k == "Power" and ("KW" in s or "HP" in s))]
        keys += [k for k in s if k not in skip and k not in order]
        for k in keys:
            label = SPECS.get(k, {}).get(lang, k)
            rows.append((label, self.spec_value(it, k, lang)))
        if it["stock_no"]:
            rows.append((SPECS["Stock number"][lang], it["stock_no"]))
        return rows

    def clause(self, it, key, lang):
        label = SPECS[key][lang]
        if lang != "de":
            label = label[0].lower() + label[1:]
        return f"{label} {self.spec_value(it, key, lang)}"

    def describe(self, it, lang):
        s, out = it["specs"], []
        if it["kind"] != "tool":
            first = [it["full"][lang]]
            if it["year"]:
                first.append({"en": "year {y}", "de": "Baujahr {y}", "ru": "год выпуска {y}",
                              "lv": "izlaiduma gads {y}"}[lang].format(y=it["year"]))
            if it["hours"]:
                h = self.spec_value(it, "Motor hours", lang).rsplit(NBSP, 1)[0]
                n = int(it["hours"])
                first.append({"en": f"{h} operating hours", "de": f"{h} Betriebsstunden",
                              "ru": f"наработка {h} м/ч",
                              "lv": forms("lv", ("nostrādāta {n} motorstunda", "nostrādātas {n} motorstundas"), n)
                              .replace(str(n), h)}[lang])
            if it["km"]:
                first.append({"en": "mileage {v}", "de": "Kilometerstand {v}", "ru": "пробег {v}",
                              "lv": "nobraukums {v}"}[lang].format(v=self.spec_value(it, "KM", lang)))
            out.append(", ".join(first) + ".")
            second = [self.clause(it, k, lang) for k in ("Weight", "Power")
                      if k in s or (k == "Power" and ("KW" in s or "HP" in s))]
            extra = [self.clause(it, k, lang) for k in ("Bucket m3", "Tracks width mm", "Undercarriage", "Tire balance",
                                                        "Max Load", "Payload", "Max., lifting height",
                                                        "Engine capacity cm3") if k in s]
            if second:
                out.append(cap(", ".join(second)) + ".")
            if extra:
                out.append(cap(", ".join(extra)) + ".")
        else:
            hinge = self.hinge_short(it, lang)
            first = it["card"][lang]
            if hinge and self.hinge_is_text(it):
                first += f". {SPECS['Hinges'][lang]}: {hinge[0].lower() + hinge[1:] if lang == 'ru' else hinge}"
            elif hinge and hinge not in first:
                first += " " + {"en": "with {h} mounting", "de": "mit Aufnahme {h}", "ru": "с креплением {h}",
                                "lv": "ar sakabi {h}"}[lang].format(h=hinge)
            out.append(first + ".")
            dims = []
            if "Width" in s and not it["size"].startswith(s["Width"]):
                dims.append(self.clause(it, "Width", lang))
            dims += [self.clause(it, k, lang) for k in ("Pin hole", "Stick", "H.O.H", "Opening ( mm )", "Lenght",
                                                        "Thickness", "Working width") if k in s and k != (
                                                            "Lenght" if it["size"] == s.get("Lenght") else None)]
            if dims:
                out.append(cap(", ".join(dims)) + ".")
            other = [self.clause(it, k, lang) for k in ("Capacity", "Weight", "Fraction") if k in s]
            if other:
                out.append(cap(", ".join(other)) + ".")
            fits = s.get("Machine weight", "")
            if fits:
                v = self.spec_value(it, "Machine weight", lang)
                if RANGE.match(fits):
                    out.append({"en": "For machines of {v}.", "de": "Für Maschinen von {v}.", "ru": "Для машин массой {v}.",
                                "lv": "Tehnikas svara klase: {v}."}[lang].format(v=v))
                else:
                    out.append({"en": "Fits {v}.", "de": "Passend für {v}.", "ru": "Подходит для {v}.",
                                "lv": "Paredzētā tehnika: {v}."}[lang].format(v=v))
            if it["stock_no"]:
                out.append(f"{SPECS['Stock number'][lang]} {it['stock_no']}.")
        return " ".join(out)

    def meta_description(self, it, lang):
        bits = [it["full"][lang]]
        if it["kind"] != "tool":
            if it["year"]:
                bits.append(it["year"])
            if it["hours"]:
                bits.append(self.spec_value(it, "Motor hours", lang))
            if it["km"]:
                bits.append(self.spec_value(it, "KM", lang))
            if "Weight" in it["specs"]:
                bits.append(self.spec_value(it, "Weight", lang))
        else:
            if it["stock_no"]:
                bits.append(it["stock_no"])
        text = ", ".join(bits) + ". "
        text += t(lang, "prod_desc_price", p=fmt_price(it["price"], lang)) if it["price"] else t(lang, "price_request") + "."
        text += f" Trimen Tractors, {COUNTRY[lang]}."
        return text.replace(NBSP, " ")

    def key_facts(self, it, lang):
        s = it["specs"]
        if it["kind"] != "tool":
            keys = [k for k in ("Motor hours", "KM", "Weight", "Power") if k in s or (k == "Power" and ("KW" in s or "HP" in s))]
            facts = [(SPECS["Year"][lang], it["year"])] if it["year"] else []
        else:
            keys = [k for k in ("Hinges", "Width", "Pin hole", "Capacity", "Weight", "Machine weight") if k in s]
            facts = []
        facts += [(SPECS[k][lang], self.spec_value(it, k, lang)) for k in keys]
        return facts[:5]

    def card_meta(self, it, lang):
        if it["kind"] != "tool":
            bits = [it["year"]]
            if it["hours"]:
                bits.append(self.spec_value(it, "Motor hours", lang))
            elif it["km"]:
                bits.append(self.spec_value(it, "KM", lang))
        else:
            hinge = self.hinge_short(it, lang) if it["hinge"] else ""
            bits = [hinge if hinge and hinge not in it["card"][lang] else "", it["stock_no"]]
        return " · ".join(b for b in bits if b)

    def contact(self, it):
        c = it["contact"]
        if c:
            for p in self.team:
                if p["email"] == c["email"] or p["name"] == c["name"]:
                    return p
            return {**c, "role": {}, "photo": "", "speaks": []}
        return None

    def hinge_key(self, hinge):
        h = hinge.upper()
        if "NTP10" in h:
            return "NTP10", "NTP10 / B20 / S1"
        if "NTP20" in h:
            return "NTP20", "NTP20 / B27 / S2"
        if "SKID" in h or "BOBCAT" in h:
            return "SKIDSTEER", None
        key = re.sub(r"[^A-Z0-9]", "", h.replace("HYDRAULIC", ""))
        return key, None


# ---------------------------------------------------------------- rendering

class Renderer:
    def __init__(self, site):
        self.s = site
        self.pages = []  # (lang, path) for the sitemap, grouped by alternates
        self.sitemap = []

    # ---- layout

    def head(self, lang, cur, title, desc, alternates, og_type="website", og_image=None, ld=(), noindex=False):
        s = self.s
        canonical = s.abs(alternates[lang])
        tags = [
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{esc(title)}</title>",
            f'<meta name="description" content="{esc(desc)}">',
        ]
        if noindex or not s.production:
            tags.append('<meta name="robots" content="noindex">')
        tags.append(f'<link rel="canonical" href="{esc(canonical)}">')
        for l in LANGS:
            if l in alternates:
                tags.append(f'<link rel="alternate" hreflang="{l}" href="{esc(s.abs(alternates[l]))}">')
        if "en" in alternates:
            tags.append(f'<link rel="alternate" hreflang="x-default" href="{esc(s.abs(alternates["en"]))}">')
        image = og_image or img(s.photo(HERO_MAIN))
        tags += [
            f'<meta property="og:type" content="{og_type}">',
            f'<meta property="og:site_name" content="Trimen Tractors">',
            f'<meta property="og:title" content="{esc(title.replace(" | Trimen Tractors", ""))}">',
            f'<meta property="og:description" content="{esc(desc)}">',
            f'<meta property="og:url" content="{esc(canonical)}">',
            f'<meta property="og:image" content="{esc(image)}">',
            f'<meta property="og:locale" content="{OG_LOCALE[lang]}">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<link rel="icon" href="{rel(cur, "assets/favicon.ico")}" sizes="16x16">',
            f'<link rel="apple-touch-icon" href="{rel(cur, "assets/apple-touch-icon.png")}">',
            '<link rel="preconnect" href="https://fonts.googleapis.com">',
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fira+Sans+Condensed:wght@500;600&family=Fira+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap">',
            f'<link rel="stylesheet" href="{rel(cur, "assets/site.css")}">',
            "<script>document.documentElement.classList.add('js')</script>",
        ]
        tags += [jsonld(x) for x in ld]
        return "\n".join(tags)

    def header(self, lang, cur, alternates, active):
        s = self.s
        counts = {g: sum(1 for it in s.items if it["group"] == g) for g in GROUPS}
        nav = []
        for g in GROUPS:
            path = s.group_path(g, lang)
            here = ' aria-current="page"' if active == ("group", g) else ""
            nav.append(f'<li><a href="{rel(cur, path)}"{here}>{esc(GROUPS[g]["name"][lang])}'
                       f' <span class="n">{counts[g]}</span></a></li>')
        for page, key in (("stock", "nav_stock"), ("about", "nav_about")):
            here = ' aria-current="page"' if active == page else ""
            nav.append(f'<li><a href="{rel(cur, s.page_path(page, lang))}"{here}>{esc(t(lang, key))}</a></li>')
        langs = "".join(
            f'<a href="{rel(cur, alternates.get(l, s.home_path(l)))}" hreflang="{l}" lang="{l}" title="{LANG_NAMES[l]}"'
            + (' aria-current="true"' if l == lang else "") + f">{l.upper()}</a>" for l in LANGS)
        phone = COMPANY["phone"]
        return f"""<a class="skip" href="#main">{esc(t(lang, "skip"))}</a>
<div class="topbar"><div class="wrap topbar-in">
<span class="where">{esc(t(lang, "address_short"))}</span>
<a class="tel" href="tel:{phone.replace(" ", "")}">{esc(phone)}</a>
<nav class="langs" aria-label="Language">{langs}</nav>
</div></div>
<header class="header"><div class="wrap header-in">
<a class="logo" href="{rel(cur, s.home_path(lang))}"><img src="{rel(cur, "assets/logo.png")}" alt="Trimen Tractors" width="147" height="58"></a>
<button class="menu-btn" type="button" aria-expanded="false" aria-controls="nav">{esc(t(lang, "menu"))}</button>
<nav id="nav" class="nav" aria-label="Main"><ul>{"".join(nav)}</ul></nav>
</div></header>"""

    def footer(self, lang, cur):
        s = self.s
        groups = "".join(f'<li><a href="{rel(cur, s.group_path(g, lang))}">{esc(GROUPS[g]["name"][lang])}</a></li>'
                         for g in GROUPS)
        cats = "".join(f'<li><a href="{rel(cur, s.cat_path(c, lang))}">{esc(s.cat(c, "name", lang))}</a></li>'
                       for c in s.cats_with_items[:8])
        langs = " ".join(f'<a href="{rel(cur, s.home_path(l))}" hreflang="{l}" lang="{l}">{LANG_NAMES[l]}</a>'
                         for l in LANGS)
        phone = COMPANY["phone"]
        return f"""<footer class="footer"><div class="wrap">
<div class="footer-grid">
<div><p class="f-name">{COMPANY["legal"]}</p>
<p>{esc(COMPANY["street"])}<br>{COMPANY["parish"]}, {COMPANY["municipality"]}<br>{COMPANY["postcode"]}, {COUNTRY[lang]}</p>
<p><a href="tel:{phone.replace(" ", "")}">{phone}</a></p></div>
<div><p class="f-head">{esc(t(lang, "categories"))}</p><ul>{groups}{cats}</ul></div>
<div><p class="f-head">Trimen Tractors</p><ul>
<li><a href="{rel(cur, s.page_path("stock", lang))}">{esc(t(lang, "nav_stock"))}</a></li>
<li><a href="{rel(cur, s.page_path("about", lang))}">{esc(t(lang, "nav_about"))}</a></li>
<li><a href="{rel(cur, s.page_path("about", lang))}#contact">{esc(t(lang, "nav_contact"))}</a></li>
<li><a href="{COMPANY["facebook"]}" rel="noopener">Facebook</a></li>
<li><a href="https://www.vuwtc.com" rel="noopener">{esc(t(lang, "verachtert"))}</a></li>
</ul></div>
</div>
<p class="f-langs">{langs}</p>
<p class="f-small">{esc(t(lang, "footer_vat"))} © {s.year} {COMPANY["legal"]}</p>
</div></footer>"""

    def breadcrumbs(self, lang, cur, trail):
        """trail: list of (name, path); last is the current page."""
        s = self.s
        full = [(t(lang, "home"), s.home_path(lang))] + trail
        lis = []
        for i, (name, path) in enumerate(full):
            if i == len(full) - 1:
                lis.append(f'<li aria-current="page">{esc(name)}</li>')
            else:
                lis.append(f'<li><a href="{rel(cur, path)}">{esc(name)}</a></li>')
        ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": s.abs(path)} for i, (name, path) in enumerate(full)]}
        return f'<nav class="crumbs" aria-label="Breadcrumb"><ol>{"".join(lis)}</ol></nav>', ld

    def write(self, lang, path, title, desc, body, alternates, active=None, og_type="website", og_image=None, ld=(),
              sitemap=True, page_class=""):
        cur = path
        doc = f"""<!doctype html>
<html lang="{lang}">
<head>
{self.head(lang, cur, title, desc, alternates, og_type, og_image, ld)}
</head>
<body class="{page_class}">
{self.header(lang, cur, alternates, active)}
<main id="main">
{body}
</main>
{self.footer(lang, cur)}
<script src="{rel(cur, "assets/site.js")}" defer></script>
</body>
</html>
"""
        out = ROOT / path / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(doc, encoding="utf-8")
        if sitemap and lang == "en":
            self.sitemap.append(alternates)

    # ---- pieces

    def card(self, it, lang, cur, level=3, badge=False):
        s = self.s
        photo = it["images"][0] if it["images"] else ""
        im = (f'<img src="{img(medium(photo))}" alt="" width="510" height="383" loading="lazy" decoding="async">'
              if photo else '<span class="noimg"></span>')
        badge_html = f'<span class="badge">{esc(cap(s.type_noun(it, lang)))}</span>' if badge else ""
        count = f'<span class="pics">{esc(t(lang, "photos", n=len(it["images"])))}</span>' if len(it["images"]) > 1 else ""
        price = (f'{fmt_price(it["price"], lang)} <small>{esc(t(lang, "price_net"))}</small>' if it["price"]
                 else f'<span class="req">{esc(t(lang, "price_request"))}</span>')
        hk = s.hinge_key(it["hinge"])[0] if it["hinge"] else ""
        text = " ".join([it["full"][lang], it["make"], it["model"], it["stock_no"], it["hinge"],
                         s.cat(it["cat"], "name", lang), str(it["id"])]).lower()
        data = (f'data-id="{it["id"]}" data-cat="{it["cat"]}" data-make="{esc(it["make"])}" '
                f'data-price="{it["price"] or 0}" data-year="{(re.search(r"\d{4}", it["year"]) or [""])[0]}" '
                f'data-width="{it["width_mm"] or ""}" data-hinge="{esc(hk)}" data-rank="{it["rank"]}" '
                f'data-text="{esc(text)}"')
        meta = s.card_meta(it, lang)
        return (f'<li class="card" {data}><a href="{rel(cur, it["path"][lang])}">'
                f'<span class="card-img">{im}{badge_html}{count}</span>'
                f'<span class="card-body"><h{level} class="card-title">{esc(it["card"][lang])}</h{level}>'
                + (f'<span class="card-meta">{esc(meta)}</span>' if meta else "")
                + f'<span class="card-price">{price}</span></span></a></li>')

    def listing(self, lang, cur, items, cat_filter, level=2, badge=False):
        s = self.s
        items = sorted(items, key=lambda it: it["rank"])
        uid = slugify(cur)
        fields = [f'<div class="f f-q"><label for="q-{uid}">{esc(t(lang, "f_search"))}</label>'
                  f'<input id="q-{uid}" type="search" name="q" autocomplete="off"></div>']
        if cat_filter:
            opts = []
            for g in GROUPS:
                cids = [c for c in s.cats_with_items if s.cat_group[c] == g and any(it["cat"] == c for it in items)]
                if cids:
                    opts.append(f'<optgroup label="{esc(GROUPS[g]["name"][lang])}">' + "".join(
                        f'<option value="{c}">{esc(s.cat(c, "name", lang))}</option>' for c in cids) + "</optgroup>")
            fields.append(f'<div class="f"><label for="c-{uid}">{esc(t(lang, "f_cat"))}</label>'
                          f'<select id="c-{uid}" name="c"><option value="">{esc(t(lang, "f_all"))}</option>{"".join(opts)}</select></div>')
        makes = sorted({it["make"] for it in items if it["make"]}, key=str.lower)
        if len(makes) > 1:
            fields.append(f'<div class="f"><label for="m-{uid}">{esc(t(lang, "f_make"))}</label>'
                          f'<select id="m-{uid}" name="make"><option value="">{esc(t(lang, "f_all"))}</option>'
                          + "".join(f'<option>{esc(m)}</option>' for m in makes) + "</select></div>")
        hinges = {}
        for it in items:
            if it["hinge"]:
                key, label = s.hinge_key(it["hinge"])
                if key == "SKIDSTEER":
                    label = VALUE_I18N["skid steer"][lang]
                hinges.setdefault(key, [label or s.hinge_text(it, lang), 0])[1] += 1
        if len(hinges) > 1:
            opts = sorted(hinges.items(), key=lambda kv: (-kv[1][1], kv[1][0]))
            fields.append(f'<div class="f"><label for="h-{uid}">{esc(t(lang, "f_hinge"))}</label>'
                          f'<select id="h-{uid}" name="hinge"><option value="">{esc(t(lang, "f_all"))}</option>'
                          + "".join(f'<option value="{esc(k)}">{esc(v[0])} ({v[1]})</option>' for k, v in opts)
                          + "</select></div>")
        has_width = sum(1 for it in items if it["width_mm"]) > 3
        if has_width:
            fields.append(f'<fieldset class="f f-range"><legend>{esc(t(lang, "f_width"))}</legend>'
                          f'<input type="number" name="wmin" inputmode="numeric" min="0" step="50" placeholder="{esc(t(lang, "f_from"))}" aria-label="{esc(t(lang, "f_width"))}, {esc(t(lang, "f_from"))}">'
                          f'<input type="number" name="wmax" inputmode="numeric" min="0" step="50" placeholder="{esc(t(lang, "f_to"))}" aria-label="{esc(t(lang, "f_width"))}, {esc(t(lang, "f_to"))}"></fieldset>')
        sorts = [("new", "s_new"), ("price_asc", "s_price_asc"), ("price_desc", "s_price_desc")]
        if any(it["year"] for it in items):
            sorts.append(("year", "s_year"))
        if has_width:
            sorts.append(("width", "s_width"))
        fields.append(f'<div class="f"><label for="s-{uid}">{esc(t(lang, "f_sort"))}</label><select id="s-{uid}" name="sort">'
                      + "".join(f'<option value="{v}">{esc(t(lang, k))}</option>' for v, k in sorts) + "</select></div>")
        fields.append(f'<button type="reset" class="btn-link">{esc(t(lang, "f_reset"))}</button>')
        i18n = {"lang": lang, "results": list(T[lang]["results"])}
        cards = "".join(self.card(it, lang, cur, level, badge) for it in items)
        return f"""<div class="listing" data-listing data-i18n="{esc(json.dumps(i18n, ensure_ascii=False))}">
<form class="filters" role="search">{"".join(fields)}</form>
<p class="result-count" aria-live="polite">{esc(t(lang, "results", n=len(items)))}</p>
<ul class="cards">{cards}</ul>
<p class="no-results" hidden>{esc(t(lang, "no_results"))}</p>
</div>"""

    def business_ld(self):
        s = self.s
        return {
            "@context": "https://schema.org", "@type": "LocalBusiness", "@id": s.abs("#business"),
            "name": COMPANY["name"], "legalName": COMPANY["legal"], "url": s.abs(""),
            "logo": s.abs("assets/logo.png"), "image": [img(s.photo(YARD_PHOTO)), img(s.photo(HERO_MAIN))],
            "telephone": COMPANY["phone"], "vatID": COMPANY["vat"],
            "address": {"@type": "PostalAddress", "streetAddress": COMPANY["street"],
                        "addressLocality": "Babītes pagasts", "addressRegion": "Mārupes novads",
                        "postalCode": COMPANY["postcode"], "addressCountry": "LV"},
            "geo": {"@type": "GeoCoordinates", "latitude": COMPANY["lat"], "longitude": COMPANY["lng"]},
            "sameAs": [COMPANY["facebook"], COMPANY["twitter"]],
            "contactPoint": [{"@type": "ContactPoint", "contactType": "sales", "telephone": p["phone"],
                              "email": p["email"], "name": p["name"], "availableLanguage": p["speaks"]}
                             for p in s.team],
        }

    # ---- pages

    def alts(self, fn):
        return {l: fn(l) for l in LANGS}

    def home(self, lang):
        s = self.s
        cur = s.home_path(lang)
        stock = s.page_path("stock", lang)
        opts = "".join(
            f'<optgroup label="{esc(GROUPS[g]["name"][lang])}">' + "".join(
                f'<option value="{c}">{esc(s.cat(c, "name", lang))}</option>' for c in s.cats_with_items if s.cat_group[c] == g)
            + "</optgroup>" for g in GROUPS if any(s.cat_group[c] == g for c in s.cats_with_items))
        side = "".join(f'<img src="{img(s.photo(k))}" alt="" width="798" height="532" loading="lazy" decoding="async">'
                       for k in HERO_SIDE)
        groups_html = []
        for g in GROUPS:
            cids = [c for c in s.cats_with_items if s.cat_group[c] == g]
            if not cids:
                continue
            tiles = []
            for c in cids:
                rep = sorted(s.by_cat[c], key=lambda it: it["rank"])
                photo = next((it["images"][0] for it in rep if it["images"]), "")
                tiles.append(
                    f'<li><a href="{rel(cur, s.cat_path(c, lang))}"><span class="tile-img">'
                    f'<img src="{img(medium(photo))}" alt="" width="510" height="383" loading="lazy" decoding="async"></span>'
                    f'<span class="tile-name">{esc(s.cat(c, "name", lang))}</span>'
                    f'<span class="tile-n">{esc(t(lang, "count", n=len(s.by_cat[c])))}</span></a></li>')
            n = sum(len(s.by_cat[c]) for c in cids)
            groups_html.append(
                f'<div class="cat-group"><h3><a href="{rel(cur, s.group_path(g, lang))}">{esc(GROUPS[g]["name"][lang])}</a>'
                f' <span>{esc(t(lang, "count", n=n))}</span></h3><ul class="tiles">{"".join(tiles)}</ul></div>')
        recent = sorted(s.items, key=lambda it: it["rank"])[:8]
        tools_n = sum(1 for it in s.items if it["group"] == 2)
        team = "".join(
            f'<li><span class="p-name">{esc(p["name"])}</span> <span class="p-role">{esc(ROLES.get(p["role"]["en"], p["role"])[lang])}</span>'
            f'<a href="tel:{p["phone"].replace(" ", "")}">{esc(p["phone"])}</a></li>' for p in s.team)
        popular = {}
        for it in s.items:
            if it["group"] == 2 and it["hinge"]:
                k, label = s.hinge_key(it["hinge"])
                if k != "SKIDSTEER":
                    popular.setdefault(k, [label or it["hinge"], 0])[1] += 1
        chips = "".join(
            f'<li><a href="{rel(cur, s.group_path(2, lang))}?hinge={urllib.parse.quote(k)}">{esc(v[0])}</a></li>'
            for k, v in sorted(popular.items(), key=lambda kv: -kv[1][1])[:8])
        body = f"""<section class="hero"><div class="wrap hero-grid">
<div class="hero-text">
<h1>{esc(t(lang, "home_h1"))}</h1>
<p class="lead">{esc(t(lang, "home_lead", n=len(s.items)))}</p>
<form class="search" action="{rel(cur, stock)}" method="get" role="search">
<label class="sr-only" for="hero-c">{esc(t(lang, "f_cat"))}</label>
<select id="hero-c" name="c"><option value="">{esc(t(lang, "search_all"))}</option>{opts}</select>
<label class="sr-only" for="hero-q">{esc(t(lang, "search_label"))}</label>
<input id="hero-q" type="search" name="q" placeholder="{esc(t(lang, "search_ph"))}">
<button class="btn" type="submit">{esc(t(lang, "search_btn"))}</button>
</form>
<p class="hero-phone">{esc(t(lang, "office"))}: <a href="tel:{COMPANY["phone"].replace(" ", "")}">{COMPANY["phone"]}</a></p>
</div>
<div class="hero-photos">
<img src="{img(s.photo(HERO_MAIN))}" alt="" width="798" height="531" fetchpriority="high" decoding="async">
<div class="hero-side">{side}</div>
</div>
</div></section>

<section class="section"><div class="wrap">
<h2>{esc(t(lang, "browse"))}</h2>
{"".join(groups_html)}
</div></section>

<section class="section alt"><div class="wrap">
<div class="section-head"><h2>{esc(t(lang, "recent"))}</h2><a href="{rel(cur, stock)}">{esc(t(lang, "see_all"))}</a></div>
<ul class="cards">{"".join(self.card(it, lang, cur, 3, badge=True) for it in recent)}</ul>
</div></section>

<section class="section"><div class="wrap band">
<img src="{img(s.photo(TOOLS_PHOTO))}" alt="" width="798" height="532" loading="lazy" decoding="async">
<div>
<h2>{esc(t(lang, "tools_h2"))}</h2>
<p>{esc(t(lang, "tools_p", n=tools_n))}</p>
<ul class="chips">{chips}</ul>
<p><a class="btn" href="{rel(cur, s.group_path(2, lang))}">{esc(t(lang, "tools_btn"))}</a></p>
</div>
</div></section>

<section class="section alt"><div class="wrap about-band">
<div>
<h2>{esc(t(lang, "about_h2"))}</h2>
<p>{esc(t(lang, "about_p1"))}</p>
<p>{esc(t(lang, "about_p2"))}</p>
<p><a href="{rel(cur, s.page_path("about", lang))}">{esc(t(lang, "about_more"))}</a></p>
</div>
<div class="contact-box">
<h3>{esc(t(lang, "contact_h2"))}</h3>
<p>{esc(t(lang, "office"))}: <a href="tel:{COMPANY["phone"].replace(" ", "")}">{COMPANY["phone"]}</a></p>
<ul class="people">{team}</ul>
</div>
<img class="yard" src="{img(s.photo(YARD_PHOTO))}" alt="" width="798" height="530" loading="lazy" decoding="async">
</div></section>"""
        ld = [self.business_ld(), {"@context": "https://schema.org", "@type": "WebSite", "name": "Trimen Tractors",
                                   "url": s.abs(""), "inLanguage": LANGS}]
        self.write(lang, cur, t(lang, "home_title"), t(lang, "home_desc"), body, self.alts(s.home_path),
                   active="home", ld=ld, page_class="home")

    def group(self, g, lang):
        s = self.s
        cur = s.group_path(g, lang)
        items = [it for it in s.items if it["group"] == g]
        cids = [c for c in s.cats_with_items if s.cat_group[c] == g]
        crumbs, crumb_ld = self.breadcrumbs(lang, cur, [(GROUPS[g]["name"][lang], cur)])
        chips = "".join(f'<li><a href="{rel(cur, s.cat_path(c, lang))}">{esc(s.cat(c, "name", lang))}'
                        f' <span>{len(s.by_cat[c])}</span></a></li>' for c in cids)
        extra = (f'<p class="aside"><a href="https://www.vuwtc.com" rel="noopener">{esc(t(lang, "verachtert"))}</a></p>'
                 if g == 2 else "")
        body = f"""<div class="wrap page">
{crumbs}
<header class="page-head"><h1>{esc(GROUPS[g]["h1"][lang])}</h1><p>{esc(GROUPS[g]["intro"][lang])}</p></header>
<ul class="chips">{chips}</ul>
{self.listing(lang, cur, items, cat_filter=True, level=2, badge=True)}
{extra}
</div>"""
        makes = sorted({it["make"] for it in items if it["make"]}, key=lambda m: -sum(1 for it in items if it["make"] == m))[:3]
        desc = t(lang, "cat_desc", h1=GROUPS[g]["h1"][lang], n=len(items),
                 makes=t(lang, "makes", list=", ".join(makes)) if makes else "")
        self.write(lang, cur, t(lang, "cat_title", h1=GROUPS[g]["h1"][lang]), desc, body,
                   self.alts(lambda l: s.group_path(g, l)), active=("group", g), ld=[crumb_ld])

    def category(self, cid, lang):
        s = self.s
        cur = s.cat_path(cid, lang)
        g = s.cat_group[cid]
        items = s.by_cat[cid]
        h1 = s.cat_h1(cid, lang)
        crumbs, crumb_ld = self.breadcrumbs(lang, cur, [(GROUPS[g]["name"][lang], s.group_path(g, lang)),
                                                         (s.cat(cid, "name", lang), cur)])
        intro = t(lang, "intro_tool" if g == 2 else "intro_machine", h1=h1)
        siblings = "".join(
            f'<li><a href="{rel(cur, s.cat_path(c, lang))}"' + (' aria-current="page"' if c == cid else "")
            + f'>{esc(s.cat(c, "name", lang))} <span>{len(s.by_cat[c])}</span></a></li>'
            for c in s.cats_with_items if s.cat_group[c] == g)
        extra = (f'<p class="aside"><a href="https://www.vuwtc.com" rel="noopener">{esc(t(lang, "verachtert"))}</a></p>'
                 if g == 2 else "")
        body = f"""<div class="wrap page">
{crumbs}
<header class="page-head"><h1>{esc(h1)}</h1><p>{esc(intro)}</p></header>
<ul class="chips">{siblings}</ul>
{self.listing(lang, cur, items, cat_filter=False, level=2)}
{extra}
</div>"""
        makes = sorted({it["make"] for it in items if it["make"]}, key=lambda m: -sum(1 for it in items if it["make"] == m))[:3]
        desc = t(lang, "cat_desc", h1=h1, n=len(items), makes=t(lang, "makes", list=", ".join(makes)) if makes else "")
        self.write(lang, cur, t(lang, "cat_title", h1=h1), desc, body, self.alts(lambda l: s.cat_path(cid, l)),
                   active=("group", g), ld=[crumb_ld])

    def stock(self, lang):
        s = self.s
        cur = s.page_path("stock", lang)
        crumbs, crumb_ld = self.breadcrumbs(lang, cur, [(t(lang, "stock_h1"), cur)])
        body = f"""<div class="wrap page">
{crumbs}
<header class="page-head"><h1>{esc(t(lang, "stock_h1"))}</h1></header>
{self.listing(lang, cur, s.items, cat_filter=True, level=2, badge=True)}
</div>"""
        self.write(lang, cur, t(lang, "stock_title"), t(lang, "stock_desc", n=len(s.items)), body,
                   self.alts(lambda l: s.page_path("stock", l)), active="stock", ld=[crumb_ld], page_class="stock")

    def product(self, it, lang):
        s = self.s
        cur = it["path"][lang]
        cid, g = it["cat"], it["group"]
        title = it["full"][lang]
        crumbs, crumb_ld = self.breadcrumbs(lang, cur, [
            (GROUPS[g]["name"][lang], s.group_path(g, lang)), (s.cat(cid, "name", lang), s.cat_path(cid, lang)),
            (it["card"][lang], cur)])
        imgs = it["images"]
        alt = lambda i: f'{title}, {t(lang, "photo", n=i + 1)}'
        gallery = ""
        if imgs:
            thumbs = "".join(
                f'<li><a href="{img(u)}" data-i="{i}"' + (' aria-current="true"' if i == 0 else "")
                + f'><img src="{img(thumb(u))}" alt="{esc(alt(i))}" width="96" height="72" loading="lazy" decoding="async"></a></li>'
                for i, u in enumerate(imgs)) if len(imgs) > 1 else ""
            gallery = (f'<div class="gallery" data-gallery data-labels="{esc(json.dumps([t(lang, "prev"), t(lang, "next"), t(lang, "close")], ensure_ascii=False))}">'
                       f'<a class="g-main" href="{img(imgs[0])}" data-i="0"><img src="{img(imgs[0])}" alt="{esc(alt(0))}" width="800" height="600" fetchpriority="high"></a>'
                       + (f'<ul class="g-thumbs">{thumbs}</ul>' if thumbs else "") + "</div>")
        price = (f'<p class="price">{fmt_price(it["price"], lang)} <span>{esc(t(lang, "price_net"))}</span></p>'
                 + (f'<p class="gross">{esc(t(lang, "price_gross", p=fmt_price(it["gross"], lang)))}</p>' if it["gross"] else "")
                 if it["price"] else f'<p class="price req">{esc(t(lang, "price_request"))}</p>')
        facts = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in s.key_facts(it, lang))
        person = s.contact(it)
        url = s.abs(cur)
        if person:
            subject = t(lang, "enquiry_subject", title=title, id=it["id"])
            bodytxt = t(lang, "enquiry_body", title=title, url=url)
            mail = f'mailto:{person["email"]}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(bodytxt)}'
            role = ROLES.get(person.get("role", {}).get("en", ""), person.get("role") or {}).get(lang, "")
            speaks = ", ".join(SPEAKS[lang][x] for x in person.get("speaks", []) if x in SPEAKS[lang])
            photo = (f'<img src="{img(person["photo"])}" alt="" width="64" height="83">'
                     if person.get("photo") else "")
            contact = f"""<div class="person">{photo}<div>
<p class="p-label">{esc(t(lang, "contact_person"))}</p>
<p class="p-name">{esc(person["name"])}</p>
<p class="p-role">{esc(role)}{(" · " + esc(t(lang, "speaks")) + ": " + esc(speaks)) if speaks else ""}</p>
<p class="p-links"><a href="tel:{person["phone"].replace(" ", "")}">{esc(person["phone"])}</a><br><a href="mailto:{esc(person["email"])}">{esc(person["email"])}</a></p>
</div></div>
<div class="actions"><a class="btn" href="tel:{person["phone"].replace(" ", "")}">{esc(t(lang, "call"))}</a><a class="btn btn-alt" href="{esc(mail)}">{esc(t(lang, "send_email"))}</a></div>"""
        else:
            contact = (f'<div class="actions"><a class="btn" href="tel:{COMPANY["phone"].replace(" ", "")}">'
                       f'{esc(t(lang, "call"))} {COMPANY["phone"]}</a></div>')
        desc_text = s.describe(it, lang)
        notes = it["notes"][lang]
        notes_html = "".join(f"<p>{'<br>'.join(esc(l) for l in para.splitlines())}</p>"
                             for para in re.split(r"\n\s*\n", notes) if para.strip()) if notes else ""
        rows = "".join(f'<tr><th scope="row">{esc(k)}</th><td>{esc(v)}</td></tr>' for k, v in s.spec_rows(it, lang))
        related = [x for x in sorted(s.by_cat[cid], key=lambda x: x["rank"]) if x["id"] != it["id"]][:4]
        related_html = ""
        if related:
            related_html = (f'<section class="related"><div class="section-head"><h2>{esc(t(lang, "more_in", cat=s.cat(cid, "name", lang)))}</h2>'
                            f'<a href="{rel(cur, s.cat_path(cid, lang))}">{esc(t(lang, "all_in", cat=s.cat(cid, "name", lang)))}</a></div>'
                            f'<ul class="cards">{"".join(self.card(x, lang, cur, 3) for x in related)}</ul></section>')
        sub = s.card_meta(it, lang)
        maps = f'https://www.google.com/maps?q={COMPANY["lat"]},{COMPANY["lng"]}'
        body = f"""<div class="wrap page">
{crumbs}
<article class="product">
<div class="product-top">
{gallery}
<div class="product-info">
<p class="eyebrow"><a href="{rel(cur, s.cat_path(cid, lang))}">{esc(s.cat(cid, "name", lang))}</a></p>
<h1>{esc(title)}</h1>
{f'<p class="sub">{esc(sub)}</p>' if sub else ""}
<div class="price-box">{price}</div>
{f'<dl class="facts">{facts}</dl>' if facts else ""}
<div class="contact-card">{contact}</div>
<p class="listing-id">{esc(t(lang, "listing_id"))}: {it["id"]} · <button type="button" class="btn-link" data-print>{esc(t(lang, "print"))}</button></p>
</div>
</div>
<div class="product-body">
<section class="desc"><h2>{esc(t(lang, "description"))}</h2><p>{esc(desc_text)}</p>{notes_html}</section>
<section class="spec"><h2>{esc(t(lang, "specs"))}</h2><table class="specs">{rows}</table></section>
<section class="seller"><h2>{esc(t(lang, "seller"))}</h2>
<p><strong>{COMPANY["legal"]}</strong><br>{esc(COMPANY["street"])}, {COMPANY["parish"]}, {COMPANY["municipality"]}, {COMPANY["postcode"]}, {COUNTRY[lang]}<br>
<a href="tel:{COMPANY["phone"].replace(" ", "")}">{COMPANY["phone"]}</a> · <a href="{maps}" rel="noopener">{esc(t(lang, "open_map"))}</a></p></section>
</div>
</article>
{related_html}
</div>"""
        ld = {"@context": "https://schema.org", "@type": "Product", "name": title, "sku": str(it["id"]),
              "url": url, "category": s.cat(cid, "name", lang),
              "description": (desc_text + (" " + " ".join(notes.split()) if notes else ""))[:600],
              "image": [img(u) for u in imgs[:6]]}
        if it["make"]:
            ld["brand"] = {"@type": "Brand", "name": it["make"]}
        if it["model"]:
            ld["model"] = it["model"]
        if it["year"]:
            ld["productionDate"] = re.search(r"\d{4}", it["year"])[0]
        if it["price"]:
            offer = {"@type": "Offer", "url": url, "price": str(it["price"]), "priceCurrency": "EUR",
                     "availability": "https://schema.org/InStock", "seller": {"@id": s.abs("#business")},
                     "priceSpecification": {"@type": "UnitPriceSpecification", "price": it["price"],
                                            "priceCurrency": "EUR", "valueAddedTaxIncluded": False}}
            if it["condition"] == "new":
                offer["itemCondition"] = "https://schema.org/NewCondition"
            elif it["kind"] != "tool" and (it["hours"] or it["km"]):
                offer["itemCondition"] = "https://schema.org/UsedCondition"
            ld["offers"] = offer
        self.write(lang, cur, f"{title} | Trimen Tractors", s.meta_description(it, lang), body,
                   self.alts(lambda l: it["path"][l]), active=("group", g), og_type="product",
                   og_image=img(imgs[0]) if imgs else None, ld=[ld, crumb_ld], page_class="product-page")

    def about(self, lang):
        s = self.s
        cur = s.page_path("about", lang)
        crumbs, crumb_ld = self.breadcrumbs(lang, cur, [(t(lang, "nav_about"), cur)])
        paras = "".join(f"<p>{esc(p)}</p>" for p in t(lang, "about_page"))
        people = []
        for p in s.team:
            role = ROLES.get(p["role"]["en"], p["role"])[lang]
            speaks = ", ".join(SPEAKS[lang][x] for x in p["speaks"] if x in SPEAKS[lang])
            people.append(f"""<li class="member">
<img src="{img(p["photo"])}" alt="{esc(p["name"])}" width="100" height="129" loading="lazy">
<div><h3>{esc(p["name"])}</h3><p class="p-role">{esc(role)}</p>
<p><a href="tel:{p["phone"].replace(" ", "")}">{esc(p["phone"])}</a><br><a href="mailto:{esc(p["email"])}">{esc(p["email"])}</a></p>
<p class="p-speaks">{esc(t(lang, "speaks"))}: {esc(speaks)}</p></div></li>""")
        banks = "".join(f"<div><dt>{esc(t(lang, 'bank'))}</dt><dd>{esc(b)}, SWIFT {sw}<br>{iban}</dd></div>"
                        for b, sw, iban in COMPANY["banks"])
        photos = "".join(f'<li><a href="{img(u)}" data-i="{i}"><img src="{img(u)}" alt="" width="798" height="532" loading="lazy" decoding="async"></a></li>'
                         for i, u in enumerate(s.photo(k) for k in ABOUT_GALLERY))
        maps = f'https://www.google.com/maps?q={COMPANY["lat"]},{COMPANY["lng"]}'
        body = f"""<div class="wrap page">
{crumbs}
<div class="about-top">
<div><h1>{esc(t(lang, "about_h1"))}</h1>{paras}</div>
<img src="{img(s.photo(ABOUT_PHOTO))}" alt="" width="798" height="530" decoding="async">
</div>
<section id="contact" class="about-contact">
<div>
<h2>{esc(t(lang, "contact_h2"))}</h2>
<dl class="facts">
<div><dt>{esc(t(lang, "address"))}</dt><dd>{COMPANY["legal"]}<br>{esc(COMPANY["street"])}<br>{COMPANY["parish"]}, {COMPANY["municipality"]}<br>{COMPANY["postcode"]}, {COUNTRY[lang]}</dd></div>
<div><dt>{esc(t(lang, "office"))}</dt><dd><a href="tel:{COMPANY["phone"].replace(" ", "")}">{COMPANY["phone"]}</a></dd></div>
</dl>
<p><a href="{maps}" rel="noopener">{esc(t(lang, "open_map"))}</a></p>
</div>
<iframe class="map" title="Google Maps" loading="lazy" referrerpolicy="no-referrer-when-downgrade"
 src="https://maps.google.com/maps?q={COMPANY["lat"]},{COMPANY["lng"]}&amp;z=12&amp;hl={lang}&amp;output=embed"></iframe>
</section>
<section><h2>{esc(t(lang, "team_h2"))}</h2><ul class="team">{"".join(people)}</ul></section>
<section><h2>{esc(t(lang, "company_h2"))}</h2>
<dl class="facts company">
<div><dt>{esc(t(lang, "company"))}</dt><dd>{COMPANY["legal"]}</dd></div>
<div><dt>{esc(t(lang, "reg_no"))}</dt><dd>{COMPANY["reg"]}</dd></div>
<div><dt>{esc(t(lang, "vat_no"))}</dt><dd>{COMPANY["vat"]}</dd></div>
{banks}
</dl></section>
<section><h2>{esc(t(lang, "gallery_h2"))}</h2><ul class="photos" data-photos data-labels="{esc(json.dumps([t(lang, "prev"), t(lang, "next"), t(lang, "close")], ensure_ascii=False))}">{photos}</ul></section>
</div>"""
        self.write(lang, cur, t(lang, "about_title"), t(lang, "about_desc"), body,
                   self.alts(lambda l: s.page_path("about", l)), active="about", ld=[self.business_ld(), crumb_ld])

    # ---- site-level files

    def redirect_stub(self, old, new, lang):
        target = rel(old.strip("/") + "/", new)
        doc = f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><title>Trimen Tractors</title>
<meta name="robots" content="noindex"><link rel="canonical" href="{esc(self.s.abs(new))}">
<meta http-equiv="refresh" content="0; url={esc(target)}">
<script>location.replace({json.dumps(target)} + location.search + location.hash)</script>
</head><body><p><a href="{esc(target)}">{esc(self.s.abs(new))}</a></p></body></html>
"""
        out = ROOT / old.strip("/") / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(doc, encoding="utf-8")

    def legacy(self):
        """Old URLs (/en/for_sale/dozers_/1/2/ ...) forward to the new pages. Item pop-ups (#id=123) are
        resolved by site.js on the stock page."""
        s = self.s
        n = 0
        for lang in LANGS:
            pages = s.old_pages[lang]
            stock = s.page_path("stock", lang)
            for old, new in ((pages["stock"], stock), (pages["stock"] + "all/", stock), (pages["new"], stock),
                             (pages["about"], s.page_path("about", lang))):
                self.redirect_stub(old, new, lang)
                n += 1
            for c in s.data["categories"]:
                cid = c["id"]
                new = s.cat_path(cid, lang) if cid in s.by_cat else s.group_path(c["group"], lang)
                self.redirect_stub(c["old"][lang], new, lang)
                n += 1
        return n

    def root_files(self):
        s = self.s
        (ROOT / "index.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trimen Tractors</title>
<link rel="canonical" href="{s.abs("en/")}">
{"".join(f'<link rel="alternate" hreflang="{l}" href="{s.abs(l + "/")}">' for l in LANGS)}
<link rel="alternate" hreflang="x-default" href="{s.abs("en/")}">
<script>
var l = (navigator.languages || [navigator.language || "en"]).map(function (x) {{ return x.slice(0, 2).toLowerCase(); }})
  .filter(function (x) {{ return ["en", "de", "ru", "lv"].indexOf(x) > -1; }})[0] || "en";
location.replace(l + "/" + location.hash);
</script>
<noscript><meta http-equiv="refresh" content="0; url=en/"></noscript>
</head><body>
<p>{"".join(f'<a href="{l}/" hreflang="{l}">{LANG_NAMES[l]}</a> ' for l in LANGS)}</p>
</body></html>
""", encoding="utf-8")
        links = "".join(f'<li><a data-home="{l}/" href="/{l}/" hreflang="{l}" lang="{l}"><b>{esc(T[l]["nf_title"])}</b> {esc(T[l]["nf_text"])} <u>{LANG_NAMES[l]}</u></a></li>'
                        for l in LANGS)
        (ROOT / "404.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>404 | Trimen Tractors</title><meta name="robots" content="noindex">
<style>body{{font:16px/1.5 system-ui,sans-serif;color:#1f262b;max-width:40rem;margin:4rem auto;padding:0 1rem}}
ul{{list-style:none;padding:0}}li{{margin:0 0 1rem}}a{{color:#1f262b;text-decoration:none}}b{{display:block}}u{{color:#c42800}}</style>
</head><body><h1>404</h1><ul>{links}</ul>
<script>
var base = location.pathname.indexOf("/TrimenTractors/") === 0 ? "/TrimenTractors/" : "/";
document.querySelectorAll("[data-home]").forEach(function (a) {{ a.href = base + a.dataset.home; }});
</script></body></html>
""", encoding="utf-8")
        (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {s.abs('sitemap.xml')}\n", encoding="utf-8")
        urls = []
        for alternates in self.sitemap:
            links = "".join(f'<xhtml:link rel="alternate" hreflang="{l}" href="{esc(s.abs(p))}"/>' for l, p in alternates.items())
            links += f'<xhtml:link rel="alternate" hreflang="x-default" href="{esc(s.abs(alternates["en"]))}"/>'
            for l, p in alternates.items():
                urls.append(f"<url><loc>{esc(s.abs(p))}</loc><lastmod>{s.data['scraped']}</lastmod>{links}</url>")
        (ROOT / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
            + "\n".join(urls) + "\n</urlset>\n", encoding="utf-8")
        return len(urls)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-url", default="https://www.trimentractors.com")
    ap.add_argument("--production", action="store_true", help="omit the noindex tag")
    args = ap.parse_args()

    site = Site(args.site_url, args.production)
    for name in GENERATED:
        p = ROOT / name
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()

    r = Renderer(site)
    pages = 0
    for lang in LANGS:
        r.home(lang)
        r.stock(lang)
        r.about(lang)
        for g in GROUPS:
            r.group(g, lang)
        for cid in site.cats_with_items:
            r.category(cid, lang)
        for it in site.items:
            r.product(it, lang)
        pages += 3 + len(GROUPS) + len(site.cats_with_items) + len(site.items)
    stubs = r.legacy()
    urls = r.root_files()
    print(f"{len(site.items)} items, {pages} pages, {stubs} redirects from old URLs, {urls} sitemap URLs"
          + ("" if args.production else " (preview build: noindex)"))


if __name__ == "__main__":
    main()
