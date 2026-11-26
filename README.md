# Castle Bridge Media website

The Castle Bridge Media website: publishing, podcasts and data. Originally rebuilt from the Wix site. It is plain HTML and CSS with no
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
| `data/projects.json` | Data sites shown on /data and the home page: `name`, `url`, `description`, optional `image` |
| `data/podcast.json` | Latest podcast episodes, refreshed from the Spreaker RSS feed on every build |

Images are in `images/covers/` and `images/authors/`. Brand copy (tagline, the Publishing / Podcasts / Data descriptions, "What guides us") is at the top of
the page section in `build.py`, along with page text for Submissions and About. Styles are in
`css/style.css`; the menu, catalog filters and author "Read more" are in `js/site.js`.

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
- **Podcast page** lists the latest episodes from the Spreaker feed; a daily GitHub Action keeps it current.
- **New Data section** (`/data/`) for data sites.
- **Catalog search** was added.

## Publishing on GitHub Pages

Settings → Pages → Build and deployment → Deploy from a branch → `main` / root. To use
castlebridgemedia.com, add it under Custom domain and update the domain's DNS records as GitHub
describes.
