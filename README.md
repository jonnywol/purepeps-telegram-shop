# PurePeps Telegram shop

A Mini App shop for PPA VIP. Customers browse the PurePeps range in Telegram, add items to a cart, then pay on [purepeps.com.au](https://purepeps.com.au).

This page is still a preview until Benji signs off. Every product is marked for research use only. There is no dosing or human-use information here.

## Catalogue

The shop loads a snapshot of the published PurePeps catalogue in `products.json` (119 products when last refreshed). It also tries the public WooCommerce Store API first (`/wp-json/wc/store/v1/products`, 100 per page). That API does not send `Access-Control-Allow-Origin`, so a browser on GitHub Pages is blocked by CORS and the snapshot is used instead.

To refresh the snapshot:

```
python3 scripts/refresh-products.py
```

No login or API keys are required. Prices and stock come from the public store and are not invented. The page shows the snapshot date until live API access is possible.

## Checkout

Payment stays on the PurePeps site.

- One item: Continue to checkout opens `https://purepeps.com.au/?add-to-cart=ID&quantity=N`. This already works.
- More than one item: the first item is added with the same kind of link. The other items are listed with their own add-to-cart links, because WooCommerce needs a small snippet on the site before a full cart can be sent in one go.

The Store API cart endpoints cannot hand a cart from this page to purepeps.com.au while CORS is blocked, and the site session would not be shared anyway.

## Telegram

If this page is opened as a Mini App, external links use `Telegram.WebApp.openLink`. The expected Mini App link is `https://t.me/PPAPromoBot/shop`. Until that URL is pointed at this host, it may still open the earlier five-product demo on w-gas.co.za.

## Files

- `index.html` is the shop.
- `products.json` is the catalogue snapshot.
- `scripts/refresh-products.py` rebuilds the snapshot.
- `images/logo.png` is the PurePeps logo.
