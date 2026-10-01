# Trimen Tractors — website

A modern rebuild of [trimentractors.com](https://www.trimentractors.com/en): a static, mobile-friendly site for A/S Trimen Tractors' used machinery and work-tool stock.

- **Stock browser** — search, filter by category/manufacturer, sort by price/year, grid or list view
- **Listing detail** — photo gallery (arrow keys / thumbnails), specs, net and gross price, direct contact for the responsible manager; deep links like `#id=3065`
- **Categories, new arrivals, about and team** sections

No build step — plain HTML/CSS/JS. Listing photos are loaded from trimentractors.com.

## Run locally

```bash
python -m http.server 8000
```

Then open http://localhost:8000.

## Refresh stock data

`data/stock.json` is generated from the live site:

```bash
python scripts/scrape.py
```
