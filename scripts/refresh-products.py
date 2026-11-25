#!/usr/bin/env python3
"""Refresh products.json from the public PurePeps WooCommerce Store API.

No login or API keys are used. Safe to rerun any time:

    python3 scripts/refresh-products.py

Writes products.json in the shop folder (parent of scripts/).
Used as a snapshot because the Store API does not send
Access-Control-Allow-Origin, so a browser on GitHub Pages cannot
load the live catalogue directly.
"""
from __future__ import annotations

import html
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = "https://purepeps.com.au/wp-json/wc/store/v1/products"
STORE = "https://purepeps.com.au"
PER_PAGE = 100
UA = "PurePepsTelegramShopRefresh/1.0 (catalogue snapshot; research-use shop demo)"
OUT = Path(__file__).resolve().parent.parent / "products.json"
SYDNEY = timezone(timedelta(hours=11))


def clean_text(value: str) -> str:
    text = html.unescape(value or "")
    for ch in ("\u2014", "\u2013", "\u2212", "–", "—"):
        text = text.replace(ch, "-")
    return " ".join(text.split())


def parse_price(prices: dict | None) -> float | None:
    if not prices:
        return None
    raw = prices.get("price")
    if raw is None or raw == "":
        return None
    try:
        amount = float(raw)
    except (TypeError, ValueError):
        return None
    minor = prices.get("currency_minor_unit")
    try:
        minor_i = int(minor) if minor is not None else 0
    except (TypeError, ValueError):
        minor_i = 0
    if minor_i > 0:
        amount = amount / (10 ** minor_i)
    return amount


def first_image(item: dict) -> str | None:
    images = item.get("images") or []
    if not images:
        return None
    return images[0].get("src") or images[0].get("thumbnail") or None


def fetch_json(url: str, retries: int = 6) -> tuple[object, dict]:
    last_err = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                body = json.loads(resp.read().decode("utf-8"))
                return body, headers
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            last_err = err
            time.sleep(min(2 * attempt, 8))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def fetch_pages(extra_query: str = "") -> list[dict]:
    items: list[dict] = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        q = f"{BASE}?per_page={PER_PAGE}&page={page}"
        if extra_query:
            q += "&" + extra_query
        body, headers = fetch_json(q)
        if not isinstance(body, list):
            raise RuntimeError(f"Unexpected response on page {page}: {type(body)}")
        items.extend(body)
        try:
            total_pages = max(1, int(headers.get("x-wp-totalpages") or 1))
        except ValueError:
            total_pages = 1
        if not body:
            break
        page += 1
        time.sleep(0.25)
    return items


def variation_label(parent: dict, var: dict) -> str | None:
    for entry in parent.get("variations") or []:
        if entry.get("id") == var.get("id"):
            attrs = entry.get("attributes") or []
            labels = [clean_text(a.get("value") or a.get("name") or "") for a in attrs]
            labels = [x for x in labels if x]
            if labels:
                return " / ".join(labels)
    raw = var.get("variation") or ""
    if ":" in raw:
        return clean_text(raw.split(":", 1)[1].strip())
    if raw:
        return clean_text(raw)
    return None


def main() -> int:
    print("Fetching products...", file=sys.stderr)
    products = fetch_pages()
    print(f"  {len(products)} products", file=sys.stderr)
    print("Fetching variations...", file=sys.stderr)
    variations = fetch_pages("type=variation")
    print(f"  {len(variations)} variations", file=sys.stderr)

    vars_by_parent: dict[int, list[dict]] = {}
    vars_by_id: dict[int, dict] = {}
    for var in variations:
        vars_by_id[var["id"]] = var
        vars_by_parent.setdefault(var.get("parent") or 0, []).append(var)

    catalogue = []
    for p in products:
        if p.get("type") == "variation":
            continue
        prices = p.get("prices") or {}
        cats = [clean_text(c.get("name") or "") for c in (p.get("categories") or [])]
        cats = [c for c in cats if c]
        entry = {
            "id": p["id"],
            "name": clean_text(p.get("name") or ""),
            "officialName": clean_text(p.get("name") or ""),
            "slug": p.get("slug"),
            "type": p.get("type") or "simple",
            "permalink": p.get("permalink") or f"{STORE}/?p={p['id']}",
            "inStock": bool(p.get("is_in_stock")),
            "purchasable": bool(p.get("is_purchasable")),
            "image": first_image(p),
            "categories": cats,
            "price": parse_price(prices),
            "currency": prices.get("currency_code") or "AUD",
        }
        if p.get("type") == "variable" or p.get("has_options"):
            parent_vars = []
            # Prefer parent-declared variation ids so labels stay aligned
            declared = p.get("variations") or []
            declared_ids = [d.get("id") for d in declared if d.get("id")]
            source = []
            if declared_ids:
                for vid in declared_ids:
                    if vid in vars_by_id:
                        source.append(vars_by_id[vid])
                # include any extras under this parent
                for var in vars_by_parent.get(p["id"], []):
                    if var["id"] not in declared_ids:
                        source.append(var)
            else:
                source = vars_by_parent.get(p["id"], [])

            for var in source:
                vp = var.get("prices") or {}
                parent_vars.append({
                    "id": var["id"],
                    "label": variation_label(p, var),
                    "price": parse_price(vp),
                    "image": first_image(var) or entry["image"],
                    "inStock": bool(var.get("is_in_stock")),
                    "purchasable": bool(var.get("is_purchasable")),
                    "permalink": var.get("permalink") or entry["permalink"],
                })
            entry["variations"] = parent_vars
            instock_prices = [v["price"] for v in parent_vars if v["price"] is not None]
            all_prices = [v["price"] for v in parent_vars if v["price"] is not None]
            use_prices = instock_prices or all_prices
            if use_prices:
                entry["price"] = min(use_prices)
                entry["maxPrice"] = max(use_prices)
            if parent_vars:
                entry["inStock"] = any(v["inStock"] for v in parent_vars)
        catalogue.append(entry)

    # Stable order: in-stock first, then name
    catalogue.sort(key=lambda x: (0 if x["inStock"] else 1, x["name"].lower(), x["id"]))

    payload = {
        "source": BASE,
        "store": STORE,
        "fetched": datetime.now(SYDNEY).isoformat(timespec="seconds"),
        "currency": "AUD",
        "liveApiBlockedByCors": True,
        "note": (
            "Snapshot of published products from the public WooCommerce Store API. "
            "The API does not send Access-Control-Allow-Origin, so the shop page "
            "cannot read it live from GitHub Pages. Rerun this script to refresh. "
            "Prices were not invented."
        ),
        "count": len(catalogue),
        "products": catalogue,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    in_stock = sum(1 for p in catalogue if p["inStock"])
    print(f"Wrote {OUT} ({len(catalogue)} products, {in_stock} in stock)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
