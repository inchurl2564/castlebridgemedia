#!/usr/bin/env python3
"""Static site generator for castlebridgemedia.com.

Reads data/*.json and writes plain HTML pages into this folder, using the
same URL paths as the old Wix site (/catalog, /product-page/<slug>, ...) so
existing links keep working. Standard library only:

    python3 build.py
"""
import html
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

SITE_NAME = "Castle Bridge Media"
EMAIL = "castlebridgemedia@gmail.com"
LOCATION = "Denver, Colorado"
QUERY_URL = "https://querymanager.com/query/castlebridgemedia"
SOCIAL = [
    ("Amazon", "https://www.amazon.com/s?k=Castle+Bridge+Media&i=digital-text&ref=nb_sb_noss_2"),
    ("Facebook", "https://www.facebook.com/castlebridgemedia/"),
    ("Twitter / X", "https://twitter.com/castlebridgemed"),
]
NAV = [
    ("Home", ""),
    ("Our Catalog", "catalog/"),
    ("Castling Books", "castling-books/"),
    ("Podcast", "podcast-1/"),
    ("Submissions", "submissions/"),
    ("Authors", "authors/"),
    ("About", "about/"),
]
PODCAST_FEED = "https://www.spreaker.com/show/4268760/episodes/feed"
PODCAST_SHOW_URL = "https://www.spreaker.com/podcast/castle-of-horror-podcast--4268760"
PODCAST_EPISODES = 30  # how many recent episodes to list on the page


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


esc = html.escape


# ---------------------------------------------------------------- HTML cleanup
class Sanitizer(HTMLParser):
    """Keep simple semantic markup from the Wix rich text, drop inline styling."""

    KEEP = {"p", "br", "strong", "b", "em", "i", "a", "ul", "ol", "li", "h3", "h4", "blockquote"}
    VOID = {"br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.KEEP:
            return
        if tag == "a":
            href = dict(attrs).get("href", "")
            ext = href.startswith("http")
            self.out.append('<a href="%s"%s>' % (esc(href), ' target="_blank" rel="noopener"' if ext else ""))
        elif tag in self.VOID:
            self.out.append("<%s>" % tag)
        else:
            self.out.append("<%s>" % tag)

    def handle_endtag(self, tag):
        if tag in self.KEEP and tag not in self.VOID:
            self.out.append("</%s>" % tag)

    def handle_data(self, data):
        self.out.append(esc(data.replace("\xa0", " "), quote=False))


def clean_html(raw):
    s = Sanitizer()
    s.feed(raw)
    s.close()
    out = "".join(s.out)
    out = re.sub(r"<p>(\s|<br>)*</p>", "", out)
    out = re.sub(r"(<br>\s*){3,}", "<br><br>", out)
    out = re.sub(r"<p>(\s|<br>)+", "<p>", out)
    out = re.sub(r"(\s|<br>)+</p>", "</p>", out)
    return out.strip()


def split_title(name):
    """'Kudzu by Artemis Fey Collins' -> ('Kudzu', 'Artemis Fey Collins')."""
    m = re.match(r"^(.*?)\s+by\s+(.+)$", name)
    if m:
        return m.group(1), m.group(2)
    return name, ""


BUY_PHRASE = re.compile(
    r"(?i)^\W*(on sale|order|pre-?order|available|get your copy|link to buy|click here|buy|read sample|now)\b")
# Short names used in book titles -> author page slugs.
AUTHOR_ALIASES = {
    "Henderson": "jason-henderson",
    "Yo": "in-churl-yo",
    "Josh Speero": "josh-spero",
    "Bruce Wright": "bruce-lanier-wright",
}


def strip_empty(h):
    prev = None
    while prev != h:
        prev = h
        h = re.sub(r"<(strong|b|em|i|u|span)\b[^>]*>(\s|&nbsp;)*</\1>", "", h)
    return h


def prepare_book(b, author_slugs):
    """Pull the store links out of the description into proper buttons."""
    desc = b["description_html"]
    note = None

    def drop_buy_link(m):
        nonlocal note
        text = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).replace("\xa0", " ").strip()
        if not BUY_PHRASE.match(text):
            return m.group(0)
        d = re.search(r"((?:Releases|Coming)[^.<]*\d{4})", text)
        if d:
            note = d.group(1)
        return ""

    desc = re.sub(r"<a\b([^>]*)>(.*?)</a>", drop_buy_link, desc, flags=re.S)
    desc = strip_empty(desc)
    body = clean_html(desc)
    # Leftover lead-in such as "On Sale October 13, 2020." or "On Sale NOW!"
    body = re.sub(r"^<p>\s*(<strong>)?\s*(On Sale|Available)[^<]{0,40}(</strong>)?\s*(<br>\s*)*", "<p>", body)
    body = strip_empty(body)
    body = re.sub(r"^<p>(\s|<br>)*", "<p>", body)
    body = re.sub(r"<p>(\s|<br>)*</p>", "", body).strip()
    # A short first paragraph that is only a call to buy (split across tags on the old site).
    m = re.match(r"<p>(.*?)</p>", body, re.S)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if len(t) < 60 and re.search(r"(?i)\b(order|on sale|get your copy|available now)\b", t):
            body = body[m.end():].strip()

    buy, sample = None, None
    for link in b["links"]:
        if "read.amazon.com" in link["href"] or "SAMPLE" in link["text"].upper():
            sample = sample or link["href"]
        else:
            buy = buy or link["href"]
    title, author = split_title(b["name"])
    authors = []
    for part in re.split(r"(\s*&\s*|\s+and\s+|,\s*)", author) if author else []:
        if re.fullmatch(r"\s*&\s*|\s+and\s+|,\s*", part):
            authors.append((part, None, True))
            continue
        slug = AUTHOR_ALIASES.get(part) or re.sub(r"[^a-z0-9]+", "-", part.lower()).strip("-")
        authors.append((part, slug if slug in author_slugs else None, False))
    return dict(b, title=title, author=author, authors=authors, body=body,
                buy=buy, sample=sample, note=note)



# ---------------------------------------------------------------- podcast feed
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def plain(text):
    text = re.sub(r"<br\s*/?>|</p>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text))).strip()


def linkify(escaped):
    return re.sub(r"(https?://[^\s,<]+)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', escaped)


def fetch_podcast():
    """Read the Spreaker RSS feed and cache the newest episodes in data/podcast.json.

    If the feed can't be reached, the last cached copy is used, so the build never fails on it.
    """
    cache = os.path.join(DATA, "podcast.json")
    try:
        req = urllib.request.Request(PODCAST_FEED, headers={"User-Agent": "castlebridgemedia-site-build"})
        with urllib.request.urlopen(req, timeout=60) as r:
            ch = ET.fromstring(r.read()).find("channel")
    except Exception as e:  # network down, feed moved, bad XML...
        print("Podcast feed unavailable (%s); using cached data/podcast.json" % e)
        return load("podcast.json") if os.path.exists(cache) else None

    img = ch.find(ITUNES + "image")
    show = {
        "title": ch.findtext("title"),
        "description": plain((ch.findtext("description") or "").split("Become a supporter")[0]),
        "image": img.get("href") if img is not None else ch.findtext("image/url"),
        "count": len(ch.findall("item")),
        "episodes": [],
    }
    for it in ch.findall("item")[:PODCAST_EPISODES]:
        enc = it.find("enclosure")
        try:
            date = parsedate_to_datetime(it.findtext("pubDate")).strftime("%B %-d, %Y")
        except Exception:
            date = ""
        secs = int(it.findtext(ITUNES + "duration") or 0)
        summary = plain(it.findtext("description"))
        if len(summary) > 320:
            summary = summary[:320].rsplit(" ", 1)[0] + "…"
        show["episodes"].append({
            "title": (it.findtext("title") or "").strip(),
            "date": date,
            "duration": "%d min" % round(secs / 60) if secs else "",
            "summary": summary,
            "audio": enc.get("url") if enc is not None else None,
            "link": it.findtext("link"),
        })
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(show, f, indent=1, ensure_ascii=False)
    return show


# ---------------------------------------------------------------- layout
def page(path, title, body, depth, active="", description="", og_image=None, filename="index.html"):
    # depth=None means root-absolute links (for 404.html, served at any path).
    up = "/" if depth is None else "../" * depth
    nav = "".join(
        '<a href="%s%s"%s>%s</a>' % (up, href, ' aria-current="page"' if label == active else "", label)
        for label, href in NAV
    )
    social = "".join(
        '<a href="%s" target="_blank" rel="noopener">%s</a>' % (esc(u), esc(n)) for n, u in SOCIAL
    )
    full_title = esc(title + " | " + SITE_NAME if title != SITE_NAME else SITE_NAME)
    meta_desc = esc(description or "Castle Bridge Media is an independent publisher of genre books: horror, science fiction, thriller, and fantasy.")
    og = '<meta property="og:image" content="%s%s">' % (up, og_image) if og_image else ""
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{full_title}</title>
<meta name="description" content="{meta_desc}">
<meta property="og:title" content="{full_title}">
<meta property="og:description" content="{meta_desc}">
{og}
<link rel="icon" href="{up}images/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@300;400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{up}css/style.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <a class="brand" href="{up}">
    <img src="{up}images/logo.png" alt="" width="85" height="80">
    <span class="wordmark">CASTLE BRIDGE MEDIA</span>
  </a>
  <nav class="site-nav" aria-label="Main">{nav}</nav>
</header>
<main id="main">
{body}
</main>
<footer class="site-footer">
  <div class="footer-mark">CASTLE BRIDGE MEDIA</div>
  <nav class="social" aria-label="Social">{social}</nav>
  <p class="contact-line"><a href="mailto:{EMAIL}">{EMAIL}</a> · {LOCATION}</p>
  <p class="copyright">© 2020 by Castle Bridge Media.</p>
</footer>
</body>
</html>
"""
    out = os.path.join(ROOT, path, filename)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)


def book_card(b, up, eager=False):
    ribbon = '<span class="ribbon">%s</span>' % esc(b["ribbon"]) if b["ribbon"] else ""
    return (
        '<li class="book-card"><a href="%sproduct-page/%s/">'
        '<span class="cover">%s<img src="%s%s" alt="Cover of %s" loading="%s" width="400" height="600"></span>'
        '<span class="book-title">%s</span><span class="book-author">%s</span></a></li>'
        % (up, b["slug"], ribbon, up, b["cover"], esc(b["title"]), "eager" if eager else "lazy",
           esc(b["title"]), esc(b["author"]))
    )


def grid(books, up, extra_class="", eager=0):
    cards = "".join(book_card(b, up, i < eager) for i, b in enumerate(books))
    return '<ul class="book-grid %s">%s</ul>' % (extra_class, cards)


# ---------------------------------------------------------------- pages
def build():
    site = load("site.json")
    authors = load("authors.json")
    author_slugs = {a["slug"] for a in authors}
    books = [prepare_book(b, author_slugs) for b in load("books.json")]
    by_slug = {b["slug"]: b for b in books}

    # Books by each author, for the authors page.
    books_by_author = {}
    for b in books:
        for _, slug, _sep in b["authors"]:
            if slug:
                books_by_author.setdefault(slug, []).append(b)

    # ---- Home
    featured = [by_slug[s] for s in site["featured"] if s in by_slug]
    body = f"""
<section class="hero" aria-label="Castle Bridge Media">
  <img src="images/hero.jpg" alt="" width="2400" height="479">
</section>
<section class="section">
  <h1 class="section-title">Featured Titles</h1>
  {grid(featured, "", "featured", eager=4)}
  <p class="center"><a class="button" href="catalog/">See All</a></p>
</section>"""
    page("", SITE_NAME, body, 0, "Home", og_image="images/logo.png")

    # ---- Catalog (everything; Castling titles listed last as on the old site)
    order = site["catalog"] + [s for s in site["castling"] if s not in site["catalog"]]
    order += sorted(s for s in by_slug if s not in order)
    catalog = [by_slug[s] for s in order if s in by_slug]
    body = f"""
<section class="section">
  <h1 class="section-title">Our Catalog</h1>
  <div class="search">
    <label for="q" class="visually-hidden">Search the catalog</label>
    <input id="q" type="search" placeholder="Search by title or author" autocomplete="off">
    <p id="count" class="count" aria-live="polite">{len(catalog)} titles</p>
  </div>
  {grid(catalog, "../", "catalog-grid", eager=8)}
  <p id="empty" class="center muted" hidden>No titles match that search.</p>
</section>
<script>
(function () {{
  var q = document.getElementById('q'), cards = document.querySelectorAll('.catalog-grid .book-card');
  var count = document.getElementById('count'), empty = document.getElementById('empty');
  q.addEventListener('input', function () {{
    var t = q.value.trim().toLowerCase(), n = 0;
    cards.forEach(function (c) {{ var hit = c.textContent.toLowerCase().indexOf(t) !== -1; c.hidden = !hit; if (hit) n++; }});
    count.textContent = n + (n === 1 ? ' title' : ' titles');
    empty.hidden = n !== 0;
  }});
}})();
</script>"""
    page("catalog", "Our Catalog", body, 1, "Our Catalog")

    # ---- Castling Books
    castling = [by_slug[s] for s in site["castling"] if s in by_slug]
    body = f"""
<section class="section">
  <img class="imprint-logo" src="../images/castling-logo.jpg" alt="Castling Books" width="400" height="280">
  <p class="lede center">Castling Books is an Imprint of Castle Bridge Media that focuses on juvenile and young adult fiction.</p>
  {grid(castling, "../", eager=4)}
</section>"""
    page("castling-books", "Castling Books", body, 1, "Castling Books",
         description="Castling Books is the juvenile and young adult fiction imprint of Castle Bridge Media.")

    # ---- Podcast (episodes come from the Spreaker RSS feed at build time)
    show = fetch_podcast()
    eps = ""
    if show:
        for e in show["episodes"]:
            meta = " · ".join(x for x in (e["date"], e["duration"]) if x)
            audio = ('<audio controls preload="none" src="%s"></audio>' % esc(e["audio"])) if e["audio"] else ""
            more = (' <a href="%s" target="_blank" rel="noopener">Episode page</a>' % esc(e["link"])) if e["link"] else ""
            eps += ('<li class="episode"><h3>%s</h3><p class="episode-meta">%s</p>%s<p>%s%s</p></li>'
                    % (esc(e["title"]), esc(meta), audio, esc(e["summary"]), more))
    art = ('<img class="show-art" src="%s" alt="%s artwork" width="280" height="280">'
           % (esc(show["image"]), esc(show["title"]))) if show and show.get("image") else ""
    total = show["count"] if show else 0
    body = f"""
<section class="section narrow">
  <h1 class="section-title">Podcast</h1>
  <div class="show">
    {art}
    <div>
      <h2 class="show-title">{esc(show["title"]) if show else "Castle of Horror Podcast"}</h2>
      <p>{linkify(esc(show["description"])) if show else ""}</p>
      <p class="actions">
        <a class="button" href="{PODCAST_SHOW_URL}" target="_blank" rel="noopener">Listen on Spreaker</a>
        <a class="button ghost" href="{PODCAST_FEED}" target="_blank" rel="noopener">RSS feed</a>
      </p>
    </div>
  </div>
  <h2 class="sub-title">Latest episodes</h2>
  <ul class="episodes">{eps}</ul>
  <p class="center"><a class="button ghost" href="{PODCAST_SHOW_URL}" target="_blank" rel="noopener">Browse all {total:,} episodes</a></p>
</section>"""
    page("podcast-1", "Podcast", body, 1, "Podcast",
         description="The Castle of Horror Podcast: horror movie panel discussions and author interviews.")

    # ---- Submissions
    faq = [
        ("It's been six months. Why haven't I heard anything?",
         "<p>We try to respond to every query we receive, but as a small independent publisher, sometimes things unfortunately get pushed. If it's been more than 6 months, feel free to send us a follow-up email.</p><p>If you still do not receive a response, then we have likely passed on your work.</p>"),
        ("Can I mail my query and sample chapters to you?",
         "<p>Castle Bridge Media only accepts electronic submissions at this time.</p>"),
        ("I have a great non-fiction book I'd like to submit. Would you look at it?",
         "<p>Maybe? It depends on the subject matter. Send us a query.</p>"),
        ("Do you give notes or feedback on submissions?",
         "<p>Unfortunately, we usually don't respond with individual feedback on the submissions we receive.</p>"),
        ("Do you accept submissions for the Castle of Horror Anthology series?",
         "<p>The Castle of Horror Anthology series is submission by invitation only at this time.</p>"),
    ]
    faq_html = "".join('<details><summary>%s</summary>%s</details>' % (esc(q), a) for q, a in faq)
    body = f"""
<section class="section narrow prose">
  <h1 class="section-title">Submissions</h1>
  <p>Castle Bridge Media is an independent publisher of predominantly genre books, with particular interest in horror, science fiction, thriller, and fantasy. We also dabble in non-fiction titles as well. However, regardless of the genre, if the work is good, we will consider it. Novels should generally run between 80,000 and 120,000 words.</p>
  <p>We will read your query. We generally respond within 3-6 months. If we like your book, we will ask for the completed manuscript. Do not submit a query without a completed manuscript. We also accept simultaneous submissions, just tell us if you've placed your work somewhere else.</p>
  <p>Please submit your work using our <a href="{QUERY_URL}" target="_blank" rel="noopener">QueryManager page</a>.</p>
  <p class="center"><a class="button" href="{QUERY_URL}" target="_blank" rel="noopener">Submit on QueryManager</a></p>
  <p>Thank you so much for your interest in Castle Bridge Media!</p>
  <h2 class="sub-title">Frequently asked questions</h2>
  <div class="faq">{faq_html}</div>
</section>"""
    page("submissions", "Submissions", body, 1, "Submissions",
         description="How to submit your manuscript to Castle Bridge Media.")

    # ---- Authors
    cards = []
    for a in authors:
        photo = ('<img src="../%s" alt="%s" loading="lazy" width="500" height="500">' % (a["photo"], esc(a["name"]))
                 if a["photo"] else "")
        bio = "".join("<p>%s</p>" % esc(p) for p in a["bio"])
        titles = books_by_author.get(a["slug"], [])
        tl = ""
        if titles:
            tl = '<p class="author-books"><span>Books:</span> %s</p>' % ", ".join(
                '<a href="../product-page/%s/">%s</a>' % (b["slug"], esc(b["title"])) for b in titles)
        cards.append('<li class="author" id="%s">%s<h2>%s</h2>%s%s</li>' % (a["slug"], photo, esc(a["name"]), bio, tl))
    index = "".join('<a href="#%s">%s</a>' % (a["slug"], esc(a["name"])) for a in authors)
    body = f"""
<section class="section">
  <h1 class="section-title">Authors</h1>
  <details class="author-index"><summary>Jump to an author ({len(authors)})</summary><nav>{index}</nav></details>
  <ul class="author-grid">{"".join(cards)}</ul>
</section>"""
    page("authors", "Authors", body, 1, "Authors", description="The authors of Castle Bridge Media.")

    # ---- About
    press = "".join(
        '<li><a href="%s" target="_blank" rel="noopener">%s</a>%s</li>'
        % (esc(p["href"]), esc(p["title"]), ' <span class="source">%s</span>' % esc(p["source"]) if p["source"] else "")
        for p in site["press"]
    )
    body = f"""
<section class="section narrow">
  <h1 class="section-title">About Us</h1>
  <p class="lede center">Castle Bridge Media is an independent publisher of predominantly genre books, with particular interest in horror, science fiction, thriller, and fantasy.</p>
  <h2 class="sub-title">In the Press</h2>
  <ul class="press">{press}</ul>
  <h2 class="sub-title" id="contact">Contact Us</h2>
  <div class="contact">
    <p><strong>Castle Bridge Media</strong><br>{LOCATION}<br><a href="mailto:{EMAIL}">{EMAIL}</a></p>
    <p class="center"><a class="button" href="mailto:{EMAIL}">Send us a message</a></p>
  </div>
</section>"""
    page("about", "About", body, 1, "About")

    # ---- Product pages
    related_pool = featured + [b for b in catalog if b not in featured]
    for b in books:
        up = "../../"
        names = []
        for name, slug, sep in b["authors"]:
            names.append('<a href="%sauthors/#%s">%s</a>' % (up, slug, esc(name)) if slug else esc(name))
        byline = '<p class="byline">by %s</p>' % "".join(names) if b["author"] else ""
        ribbon = '<span class="ribbon static">%s</span>' % esc(b["ribbon"]) if b["ribbon"] else ""
        label = "Pre-order on Amazon" if "pre" in b["ribbon"].lower() else "Buy on Amazon"
        buttons = ""
        if b["buy"]:
            buttons += '<a class="button" href="%s" target="_blank" rel="noopener">%s</a>' % (esc(b["buy"]), label)
        if b["sample"]:
            buttons += '<a class="button ghost" href="%s" target="_blank" rel="noopener">Read a sample</a>' % esc(b["sample"])
        note = '<p class="note">%s</p>' % esc(b["note"]) if b["note"] else ""
        related = [r for r in related_pool if r["slug"] != b["slug"]][:4]
        body = f"""
<article class="section product">
  <p class="crumbs"><a href="{up}catalog/">Our Catalog</a> / {esc(b["title"])}</p>
  <div class="product-grid">
    <div class="product-cover">{ribbon}<img src="{up}{b["cover"]}" alt="Cover of {esc(b["title"])}" width="400" height="600"></div>
    <div class="product-info">
      <h1>{esc(b["title"])}</h1>
      {byline}
      {note}
      <div class="actions">{buttons}</div>
      <div class="prose">{b["body"]}</div>
    </div>
  </div>
</article>
<section class="section related">
  <h2 class="sub-title">More from Castle Bridge Media</h2>
  {grid(related, up)}
</section>"""
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(b["body"]))).strip()
        page("product-page/" + b["slug"], b["name"], body, 2, "Our Catalog",
             description=plain[:155], og_image=b["cover"])

    # ---- 404 page (GitHub Pages / Netlify serve /404.html)
    body = """
<section class="section narrow center">
  <h1 class="section-title">Page not found</h1>
  <p>Sorry, we couldn't find that page.</p>
  <p><a class="button" href="/catalog/">Browse the catalog</a></p>
</section>"""
    page("", "Page not found", body, None, filename="404.html")

    print("Built %d books, %d authors, %d press links." % (len(books), len(authors), len(site["press"])))


if __name__ == "__main__":
    build()
