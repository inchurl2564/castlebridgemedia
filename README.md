# Castle Bridge Media website

A static rebuild of castlebridgemedia.com (previously on Wix). It is plain HTML and CSS with no
server or framework, so it can be hosted on GitHub Pages, Netlify, Cloudflare Pages or any web host.

Page URLs match the old Wix site (`/catalog`, `/product-page/<slug>`, `/podcast-1`, ...), so
existing links to books keep working after you point the domain here.

## Editing content

All content lives in `data/`:

| File | What it holds |
| --- | --- |
| `data/books.json` | Every title: name, ribbon ("On Sale Now!"), cover path, description (HTML), store links |
| `data/authors.json` | Author names, photos and bios (shown alphabetically by surname) |
| `data/site.json` | Home-page featured titles, catalog order, Castling Books titles, press links on About |

Images are in `images/covers/` and `images/authors/`. Page text for Submissions, Podcast and About
is in `build.py`.

After editing, regenerate the HTML:

```bash
python3 build.py
```

Preview locally:

```bash
python3 -m http.server 8000
```

then open http://localhost:8000.

## Differences from the Wix site

- **No shop checkout.** Wix sold e-book downloads directly. Each book page now has a
  "Buy on Amazon" button using the Amazon link from that book's description. Prices are kept in
  `data/books.json` but not shown.
- **Mailing-list signup** was a Wix form; it's not included. Add a form from a service such as
  Buttondown or Mailchimp to the footer in `build.py` if you want it back.
- **Contact form** is replaced by a mailto link to castlebridgemedia@gmail.com.
- **Podcast page**: the Wix podcast widget had no feed connected (the live page was blank), so
  the page has a short description and a `TODO` where a player embed or listening links go.
- **Catalog search** was added.

## Publishing on GitHub Pages

Settings → Pages → Build and deployment → Deploy from a branch → `main` / root. To use
castlebridgemedia.com, add it under Custom domain and update the domain's DNS records as GitHub
describes.
