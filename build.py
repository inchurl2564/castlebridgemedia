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
    ("Instagram", "https://www.instagram.com/castle_bridge_media_publisher/"),
    ("Threads", "https://www.threads.com/@castle_bridge_media_publisher"),
]
NAV = [
    ("Publishing", "catalog/"),
    ("Podcasts", "podcast-1/"),
    ("Data", "data/"),
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


def write_episode_index(items):
    """Every episode in the feed, for the search box on /podcast-1 (loaded only when someone searches)."""
    rows = []
    for it in items:
        enc = it.find("enclosure")
        img = it.find(ITUNES + "image")
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate"))
            date, iso = dt.strftime("%b %-d, %Y"), dt.strftime("%Y-%m-%d")
        except Exception:
            date, iso = "", ""
        secs = int(it.findtext(ITUNES + "duration") or 0)
        rows.append({
            "t": (it.findtext("title") or "").strip(),
            "d": date, "o": iso,
            "m": round(secs / 60) if secs else 0,
            "s": plain(it.findtext("description")),
            "a": enc.get("url") if enc is not None else "",
            "l": it.findtext("link") or "",
            "i": img.get("href") if img is not None else "",
        })
    os.makedirs(os.path.join(ROOT, "podcast-1"), exist_ok=True)
    with open(os.path.join(ROOT, "podcast-1", "episodes.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))


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
    write_episode_index(ch.findall("item"))
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
            "image": (it.find(ITUNES + "image").get("href") if it.find(ITUNES + "image") is not None else None),
        })
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(show, f, indent=1, ensure_ascii=False)
    return show


# ---------------------------------------------------------------- brand copy
TAGLINE = "Castle Bridge Media connects stories, data and the people who love them."
PILLARS = [
    ("Publishing", "catalog/",
     "We publish horror, mystery, fantasy and thriller fiction for adults and young readers, "
     "working closely with authors to find and grow their audiences.", "Browse the books"),
    ("Podcasts", "podcast-1/",
     "We produce podcasts about entertainment and the people who create it: conversations for fans "
     "who want to go deeper into what they watch, read and play.", "Listen now"),
    ("Data", "data/",
     "We build data-driven websites and tools that help people understand culture and entertainment: "
     "what audiences are discovering, rediscovering and talking about, and why. Our sites gather public "
     "data, turn it into clear, sourced stories, and keep themselves up to date every day.", "See our data sites"),
]
GUIDES = ("We're curious about why stories last. We show our sources, and we make things for readers, "
          "listeners and fans first, and for the writers, journalists and companies who work alongside them.")

YEAR = __import__("datetime").date.today().year
# Genre filters on the Publishing page, in display order. Each book's genres live in data/books.json.
GENRES = ["Horror", "Thrillers", "Mystery", "Fantasy", "Science Fiction", "Anthologies",
          "Literary Fiction", "Film & Pop Culture", "Young Readers"]


def genre_slug(g):
    return re.sub(r"[^a-z0-9]+", "-", g.lower()).strip("-")
NOW_PLAYING = ""  # latest podcast episode title, set in build()


def _asset_version():
    """Short fingerprint of the CSS and JS, so browsers fetch new copies after a change."""
    import hashlib
    h = hashlib.sha1()
    for f in ("css/style.css", "js/site.js"):
        with open(os.path.join(ROOT, f), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:8]


ASSET_VERSION = _asset_version()


# ---------------------------------------------------------------- layout
def page(path, title, body, depth, active="", description="", og_image=None, filename="index.html"):
    # depth=None means root-absolute links (for 404.html, served at any path).
    up = "/" if depth is None else "../" * depth
    nav = "".join(
        '<a href="%s%s"%s>%s</a>' % (up, href, ' aria-current="page"' if label == active else "", label)
        for label, href in NAV
    )
    social = "".join(
        '<li><a href="%s" target="_blank" rel="noopener">%s</a></li>' % (esc(u), esc(n)) for n, u in SOCIAL
    )
    full_title = esc(title + " · " + SITE_NAME if title != SITE_NAME else SITE_NAME + " · Stories, data and the people who love them")
    meta_desc = esc(description or TAGLINE)
    og = '<meta property="og:image" content="%s%s">' % (up, og_image) if og_image else ""
    ticker = ""
    if NOW_PLAYING:
        ticker = ('<div class="ticker"><div class="wrap"><span class="ticker-label">On the air</span>'
                  '<a href="%spodcast-1/">%s</a></div></div>' % (up, esc(NOW_PLAYING)))
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{full_title}</title>
<meta name="description" content="{meta_desc}">
<meta property="og:title" content="{full_title}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:site_name" content="{SITE_NAME}">
{og}
<meta name="theme-color" content="#16130f">
<link rel="icon" href="{up}images/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Gloock&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{up}css/style.css?v={ASSET_VERSION}">
<script src="{up}js/site.js?v={ASSET_VERSION}" defer></script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
{ticker}
<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="{up}">
      <img src="{up}images/logo.png" alt="" width="52" height="49">
      <span>Castle Bridge Media</span>
    </a>
    <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="site-nav">Menu</button>
    <nav class="site-nav" id="site-nav" aria-label="Main">{nav}</nav>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="site-footer">
  <div class="wrap footer-grid">
    <div class="footer-brand">
      <a class="brand" href="{up}"><img src="{up}images/logo.png" alt="" width="52" height="49"><span>Castle Bridge Media</span></a>
      <p>{esc(TAGLINE)}</p>
    </div>
    <div>
      <h2>Publishing</h2>
      <ul>
        <li><a href="{up}catalog/">All books</a></li>
        <li><a href="{up}castling-books/">Castling Books</a></li>
        <li><a href="{up}authors/">Authors</a></li>
        <li><a href="{up}submissions/">Submissions</a></li>
      </ul>
    </div>
    <div>
      <h2>Podcasts &amp; Data</h2>
      <ul>
        <li><a href="{up}podcast-1/">Castle of Horror Podcast</a></li>
        <li><a href="{up}data/">Data sites</a></li>
        <li><a href="{up}about/">About us</a></li>
        <li><a href="mailto:{EMAIL}">{EMAIL}</a></li>
      </ul>
    </div>
    <div>
      <h2>Follow</h2>
      <ul>{social}</ul>
    </div>
  </div>
  <div class="wrap footer-base">
    <span>© {YEAR} Castle Bridge Media · {LOCATION}</span>
  </div>
</footer>
</body>
</html>
"""
    out = os.path.join(ROOT, path, filename)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)


def page_head(eyebrow, title, lede="", extra=""):
    lede_html = '<p class="lede">%s</p>' % lede if lede else ""
    return ('<header class="page-head wrap"><p class="label">%s</p><h1>%s</h1>%s%s</header>'
            % (esc(eyebrow), esc(title), lede_html, extra))


def books_subnav(up, active):
    items = [("All books", "catalog/"), ("Castling Books", "castling-books/"),
             ("Authors", "authors/"), ("Submissions", "submissions/")]
    return '<nav class="subnav" aria-label="Publishing">%s</nav>' % "".join(
        '<a href="%s%s"%s>%s</a>' % (up, h, ' aria-current="page"' if l == active else "", l) for l, h in items)


def badge_text(b):
    """Only pre-order notices are shown as a sticker; "On Sale Now" ribbons from the old site are dropped."""
    r = (b.get("ribbon") or "").strip()
    return r.rstrip("!") if "pre" in r.lower() else ""


def book_card(b, up, eager=False):
    ribbon = '<span class="badge">%s</span>' % esc(badge_text(b)) if badge_text(b) else ""
    return (
        '<li class="book-card" data-genres="%s"><a href="%sproduct-page/%s/">'
        '<span class="cover"><img src="%s%s" alt="" loading="%s" width="400" height="600">%s</span>'
        '<span class="book-title">%s</span><span class="book-author">%s</span></a></li>'
        % (" ".join(genre_slug(g) for g in b.get("genres", [])), up, b["slug"], up, b["cover"],
           "eager" if eager else "lazy", ribbon, esc(b["title"]), esc(b["author"]))
    )


def grid(books, up, extra_class="", eager=0, castling=()):
    cards = "".join(book_card(b, up, i < eager) for i, b in enumerate(books))
    return '<ul class="book-grid %s">%s</ul>' % (extra_class, cards)


def episode_html(e, heading="h3"):
    meta = " · ".join(x for x in (e["date"], e["duration"]) if x)
    audio = ('<audio controls preload="none" src="%s"></audio>' % esc(e["audio"])) if e["audio"] else ""
    more = (' <a href="%s" target="_blank" rel="noopener">Episode page</a>' % esc(e["link"])) if e["link"] else ""
    return ('<%s class="episode-title">%s</%s><p class="meta">%s</p>%s<p class="episode-summary">%s%s</p>'
            % (heading, esc(e["title"]), heading, esc(meta), audio, esc(e["summary"]), more))


def project_card(p, up=""):
    host = re.sub(r"^https?://(www\.)?", "", p["url"]).rstrip("/")
    src = p.get("image") or ""
    if src and not src.startswith("http"):
        src = up + src
    img = ('<img src="%s" alt="" loading="lazy" width="1200" height="630">' % esc(src)) if src else ""
    desc = '<p>%s</p>' % esc(p["description"]) if p.get("description") else ""
    return ('<li class="project-card"><a href="%s" target="_blank" rel="noopener">%s'
            '<span class="project-host">%s</span><h3>%s</h3>%s<span class="arrow">Visit site →</span></a></li>'
            % (esc(p["url"]), img, esc(host), esc(p["name"]), desc))


# ---------------------------------------------------------------- pages
def build():
    site = load("site.json")
    authors = load("authors.json")
    projects = load("projects.json") if os.path.exists(os.path.join(DATA, "projects.json")) else []
    author_slugs = {a["slug"] for a in authors}
    books = [prepare_book(b, author_slugs) for b in load("books.json")]
    by_slug = {b["slug"]: b for b in books}
    castling_slugs = set(site["castling"])
    show = fetch_podcast()
    global NOW_PLAYING
    if show and show["episodes"]:
        NOW_PLAYING = "Castle of Horror Podcast: " + show["episodes"][0]["title"]

    books_by_author = {}
    for b in books:
        for _, slug, _sep in b["authors"]:
            if slug:
                books_by_author.setdefault(slug, []).append(b)

    featured = [by_slug[s] for s in site["featured"] if s in by_slug]
    order = site["catalog"] + [s for s in site["castling"] if s not in site["catalog"]]
    order += sorted(s for s in by_slug if s not in order)
    catalog = [by_slug[s] for s in order if s in by_slug]

    # ---- Home
    # Cover collage: leave out the publishers' own titles.
    def by_publishers(x):
        return bool(re.search(r"In Churl Yo|Henderson", x["author"]))
    wall_books = [x for x in featured + [y for y in catalog if y not in featured] if not by_publishers(x)]
    wall_cols = ["", "", ""]
    for i, wb in enumerate(wall_books[:15]):
        wall_cols[i % 3] += '<a href="product-page/%s/" tabindex="-1"><img src="%s" alt="" width="400" height="600"%s></a>' % (
            wb["slug"], wb["cover"], "" if i < 6 else ' loading="lazy"')
    wall = "".join('<div class="wall-col">%s</div>' % c for c in wall_cols)
    total_eps = show["count"] if show else 0
    stats = [("%d" % len(catalog), "books in print"), ("%d" % len(authors), "authors"),
             ("%s" % format(total_eps, ","), "podcast episodes since 2013"),
             ("Daily", "data updates")]
    stats_html = "".join('<li><strong>%s</strong> %s</li>' % (esc(n), esc(l)) for n, l in stats)
    latest = ""
    if show and show["episodes"]:
        e = show["episodes"][0]
        img = e.get("image") or show.get("image")
        art = ('<img class="show-art" src="%s" alt="" width="220" height="220" loading="lazy">' % esc(img)) if img else ""
        latest = f"""
    <div class="on-air">
      {art}
      <div><p class="label">On the air · {esc(show["title"])}</p>{episode_html(e)}</div>
    </div>"""
    rally = ""
    if projects:
        p0 = projects[0]
        img = ('<img src="%s" alt="" width="1200" height="630" loading="lazy">' % esc(p0["image"])) if p0.get("image") else ""
        rally = f"""
    <a class="feature-project" href="{esc(p0["url"])}" target="_blank" rel="noopener">
      {img}
      <div>
        <p class="label">Now live · {esc(re.sub(r"^https?://(www\.)?", "", p0["url"]).rstrip("/"))}</p>
        <h3>{esc(p0["name"])}</h3>
        <p>{esc(p0.get("description", ""))}</p>
        <span class="arrow">Read today's comebacks →</span>
      </div>
    </a>"""
    body = f"""
<section class="hero">
  <div class="wrap hero-grid">
    <div class="hero-copy">
      <p class="label">An independent media company</p>
      <h1>Stories, data and the people who <em>love</em> them.</h1>
      <p class="lede">{esc(TAGLINE)}</p>
      <p class="actions"><a class="button" href="catalog/">Browse the books</a><a class="button ghost" href="podcast-1/">Hear the podcast</a></p>
    </div>
    <div class="cover-wall" aria-hidden="true">{wall}</div>
  </div>
</section>
<section class="stats"><ul class="wrap">{stats_html}</ul></section>

<section class="band chapter">
  <div class="wrap">
    <div class="chapter-head">
      <p class="chapter-num">I.</p>
      <div><h2>Publishing</h2><p class="lede">{esc(PILLARS[0][2])}</p></div>
    </div>
    {grid(featured, "", "shelf", eager=5, castling=castling_slugs)}
    <p><a class="text-link" href="catalog/">See all {len(catalog)} books →</a> &nbsp; <a class="text-link" href="submissions/">Send us yours →</a></p>
  </div>
</section>

<section class="band chapter dark battlements">
  <div class="wrap">
    <div class="chapter-head">
      <p class="chapter-num">II.</p>
      <div><h2>Podcasts</h2><p class="lede">{esc(PILLARS[1][2])}</p></div>
    </div>
    {latest}
    <p><a class="text-link" href="podcast-1/">All {total_eps:,} episodes →</a></p>
  </div>
</section>

<section class="band chapter pulp">
  <div class="wrap">
    <div class="chapter-head">
      <p class="chapter-num">III.</p>
      <div><h2>Data</h2><p class="lede">{esc(PILLARS[2][2])}</p></div>
    </div>
    {rally}
  </div>
</section>

<section class="band creed">
  <div class="wrap">
    <p class="label">What guides us</p>
    <blockquote>{esc(GUIDES)}</blockquote>
    <a class="text-link" href="about/">More about us →</a>
  </div>
</section>"""
    page("", SITE_NAME, body, 0, "", og_image="images/logo.png")

    # ---- Books (catalog)
    counts = {g: sum(1 for x in catalog if g in x.get("genres", [])) for g in GENRES}
    filters = ('<div class="filters" role="group" aria-label="Filter by genre">'
               '<button type="button" data-filter="all" aria-pressed="true">All <span>%d</span></button>' % len(catalog)
               + "".join('<button type="button" data-filter="%s" aria-pressed="false">%s <span>%d</span></button>'
                         % (genre_slug(g), esc(g), counts[g]) for g in GENRES if counts[g])
               + '</div>')
    body = page_head("Our books", "Publishing", esc(PILLARS[0][2]), books_subnav("../", "All books")) + f"""
<section class="wrap catalog">
  <div class="toolbar">
    <label class="search"><span class="visually-hidden">Search books</span>
      <input id="q" type="search" placeholder="Search by title or author" autocomplete="off"></label>
    {filters}
  </div>
  <p id="count" class="meta" aria-live="polite">{len(catalog)} books</p>
  {grid(catalog, "../", "catalog-grid", eager=8, castling=castling_slugs)}
  <p id="empty" class="empty" hidden>No books match that search.</p>
</section>"""
    page("catalog", "Publishing", body, 1, "Publishing")

    # ---- Castling Books
    castling = [by_slug[s] for s in site["castling"] if s in by_slug]
    body = page_head("Imprint", "Castling Books",
                     "Castling Books is the Castle Bridge Media imprint for juvenile and young adult fiction.",
                     books_subnav("../", "Castling Books")) + f"""
<section class="wrap imprint">
  <img class="imprint-logo" src="../images/castling-logo.png" alt="Castling Books logo" width="509" height="527">
  {grid(castling, "../", eager=6)}
</section>"""
    page("castling-books", "Castling Books", body, 1, "Publishing",
         description="Castling Books is the juvenile and young adult fiction imprint of Castle Bridge Media.")

    # ---- Podcasts
    def ep_item(e):
        img = e.get("image") or (show or {}).get("image")
        thumb = ('<img class="ep-thumb" src="%s" alt="" width="140" height="140" loading="lazy">' % esc(img)) if img else ""
        return '<li class="episode">%s<div>%s</div></li>' % (thumb, episode_html(e))
    eps = "".join(ep_item(e) for e in (show["episodes"] if show else []))
    art = ('<img class="show-art" src="%s" alt="%s artwork" width="240" height="240">'
           % (esc(show["image"]), esc(show["title"]))) if show and show.get("image") else ""
    total = show["count"] if show else 0
    body = page_head("Podcasts", "Podcasts", esc(PILLARS[1][2])) + f"""
<section class="wrap">
  <div class="show" id="show-card">
    {art}
    <div>
      <p class="label">Our show</p>
      <h2>{esc(show["title"]) if show else "Castle of Horror Podcast"}</h2>
      <p>{linkify(esc(show["description"])) if show else ""}</p>
      <p class="actions">
        <a class="button" href="{PODCAST_SHOW_URL}" target="_blank" rel="noopener">Listen on Spreaker</a>
        <a class="button ghost" href="{PODCAST_FEED}" target="_blank" rel="noopener">RSS feed</a>
      </p>
    </div>
  </div>
  <div class="ep-search" id="ep-search">
    <label for="ep-q" class="ep-search-label">Search all {total:,} episodes by movie, show, book, author, director, star or guest</label>
    <input id="ep-q" type="search" placeholder="Try “Hammer”, “John Carpenter” or “Dark Shadows”" autocomplete="off" data-index="episodes.json">
    <p id="ep-status" class="meta" aria-live="polite"></p>
    <ul class="episodes" id="ep-results" hidden></ul>
  </div>
  <div id="ep-latest">
    <div class="section-head"><h2>Latest episodes</h2><span class="meta">{total:,} episodes since 2013</span></div>
    <ul class="episodes">{eps}</ul>
  </div>
  <p class="center"><a class="button ghost" href="{PODCAST_SHOW_URL}" target="_blank" rel="noopener">Browse all {total:,} episodes</a></p>
</section>"""
    page("podcast-1", "Podcasts", body, 1, "Podcasts",
         description="The Castle of Horror Podcast: horror movie panel discussions and author interviews.")

    # ---- Data
    if projects:
        proj = '<ul class="project-grid">%s</ul>' % "".join(project_card(p, "../") for p in projects)
    else:
        proj = '<p class="empty">Our first data sites are on the way.</p>'
    body = page_head("Data", "Data sites", esc(PILLARS[2][2])) + f"""
<section class="wrap">
  <div class="section-head"><h2>Our sites</h2></div>
  {proj}
  <div class="principles">
    <div><h3>Public data</h3><p>Our sites gather publicly available data about what people watch, read, play and talk about.</p></div>
    <div><h3>Sourced stories</h3><p>We turn that data into clear stories and show where every number comes from.</p></div>
    <div><h3>Always current</h3><p>Each site updates itself every day, so what you read reflects what audiences are doing now.</p></div>
  </div>
  <p class="contact-note">Working on something where data could help? <a href="mailto:{EMAIL}">Get in touch</a>.</p>
</section>"""
    page("data", "Data sites", body, 1, "Data", description=PILLARS[2][2][:155])

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
    body = page_head("Publishing", "Submissions", "We're always looking for great genre fiction.",
                     books_subnav("../", "Submissions")) + f"""
<section class="wrap two-col">
  <div class="prose">
    <p>Castle Bridge Media is an independent publisher of predominantly genre books, with particular interest in horror, mystery, fantasy, science fiction and thriller. We also dabble in non-fiction titles. Regardless of the genre, if the work is good, we will consider it. Novels should generally run between 80,000 and 120,000 words.</p>
    <p>We will read your query. We generally respond within 3–6 months. If we like your book, we will ask for the completed manuscript. Do not submit a query without a completed manuscript. We also accept simultaneous submissions; just tell us if you've placed your work somewhere else.</p>
    <p>Thank you so much for your interest in Castle Bridge Media!</p>
    <h2>Frequently asked questions</h2>
    <div class="faq">{faq_html}</div>
  </div>
  <aside class="callout">
    <h2>Ready to submit?</h2>
    <p>We take queries through QueryManager.</p>
    <a class="button" href="{QUERY_URL}" target="_blank" rel="noopener">Submit on QueryManager</a>
    <ul class="checklist">
      <li>Completed manuscript</li>
      <li>80,000–120,000 words for novels</li>
      <li>Simultaneous submissions welcome</li>
      <li>Replies in 3–6 months</li>
    </ul>
  </aside>
</section>"""
    page("submissions", "Submissions", body, 1, "Publishing",
         description="How to submit your manuscript to Castle Bridge Media.")

    # ---- Authors
    cards = []
    for a in authors:
        photo = ('<img src="../%s" alt="" loading="lazy" width="500" height="500">' % a["photo"]) if a["photo"] else ""
        bio = "".join("<p>%s</p>" % esc(p) for p in a["bio"])
        titles = books_by_author.get(a["slug"], [])
        tl = ""
        if titles:
            tl = '<p class="author-books">%s</p>' % " · ".join(
                '<a href="../product-page/%s/">%s</a>' % (b["slug"], esc(b["title"])) for b in titles)
        cards.append('<li class="author" id="%s">%s<div><h2>%s</h2>%s<div class="bio">%s</div></div></li>'
                     % (a["slug"], photo, esc(a["name"]), tl, bio))
    letters = []
    for a in authors:
        L = a["name"].replace(".", " ").split()[-1][0].upper()
        if L not in [x[0] for x in letters]:
            letters.append((L, a["slug"]))
    index = "".join('<a href="#%s">%s</a>' % (slug, L) for L, slug in letters)
    body = page_head("Publishing", "Authors", "The writers, editors and artists who publish with us.",
                     books_subnav("../", "Authors")) + f"""
<section class="wrap">
  <nav class="alpha" aria-label="Authors by surname">{index}</nav>
  <ul class="author-grid">{"".join(cards)}</ul>
</section>"""
    page("authors", "Authors", body, 1, "Publishing", description="The authors of Castle Bridge Media.")

    # ---- About
    press = "".join(
        '<li><a href="%s" target="_blank" rel="noopener">%s</a>%s</li>'
        % (esc(p["href"]), esc(p["title"]), ' <span class="meta">%s</span>' % esc(p["source"]) if p["source"] else "")
        for p in site["press"]
    )
    what = "".join('<div><h3>%s</h3><p>%s</p></div>' % (esc(t), esc(d)) for t, _, d, _ in PILLARS)
    body = page_head("About", "About Castle Bridge Media", esc(TAGLINE)) + f"""
<section class="wrap">
  <div class="principles">{what}</div>
  <div class="guides">
    <p class="label">What guides us</p>
    <blockquote>{esc(GUIDES)}</blockquote>
  </div>
  <div class="two-col">
    <div>
      <h2>Who we are</h2>
      <p>Castle Bridge Media is co-published by <a href="../authors/#jason-henderson">Jason Henderson</a> and
      <a href="../authors/#in-churl-yo">In Churl Yo</a>, and is based in {LOCATION}.</p>
    </div>
    <aside class="callout" id="contact">
      <h2>Contact us</h2>
      <p>Questions, partnerships or press: we'd love to hear from you.</p>
      <a class="button" href="mailto:{EMAIL}">{EMAIL}</a>
    </aside>
  </div>
  <div class="section-head"><h2>In the press</h2><span class="meta">{len(site["press"])} articles, reviews and interviews</span></div>
  <ul class="press">{press}</ul>
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
        badge = '<span class="badge static">%s</span>' % esc(badge_text(b)) if badge_text(b) else ""
        label = "Pre-order on Amazon" if "pre" in b["ribbon"].lower() else "Buy on Amazon"
        buttons = ""
        if b["buy"]:
            buttons += '<a class="button" href="%s" target="_blank" rel="noopener">%s</a>' % (esc(b["buy"]), label)
        if b["sample"]:
            buttons += '<a class="button ghost" href="%s" target="_blank" rel="noopener">Read a sample</a>' % esc(b["sample"])
        note = '<p class="note">%s</p>' % esc(b["note"]) if b["note"] else ""
        imprint = ('<p class="meta">A <a href="%scastling-books/">Castling Books</a> title for young readers</p>' % up
                   if b["slug"] in castling_slugs else "")
        tags = "".join('<a class="tag" href="%scatalog/#%s">%s</a>' % (up, genre_slug(g), esc(g))
                       for g in b.get("genres", []))
        tags = '<p class="tags">%s</p>' % tags if tags else ""
        # related titles: ones sharing the most genres first
        g0 = set(b.get("genres", []))
        ranked = sorted(related_pool, key=lambda r: -len(g0 & set(r.get("genres", []))))
        related = [r for r in ranked if r["slug"] != b["slug"]][:5]
        body = f"""
<article class="wrap product">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="{up}catalog/">Books</a> <span aria-hidden="true">/</span> {esc(b["title"])}</nav>
  <div class="product-grid">
    <div class="product-cover"><img src="{up}{b["cover"]}" alt="Cover of {esc(b["title"])}" width="400" height="600"></div>
    <div class="product-info">
      {badge}
      <h1>{esc(b["title"])}</h1>
      {byline}
      {imprint}
      {tags}
      {note}
      <div class="actions">{buttons}</div>
      <div class="prose">{b["body"]}</div>
    </div>
  </div>
</article>
<section class="band band-alt">
  <div class="wrap">
    <div class="section-head"><h2>More from Castle Bridge Media</h2><a class="text-link" href="{up}catalog/">All books →</a></div>
    {grid(related, up, "shelf")}
  </div>
</section>"""
        plain_desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(b["body"]))).strip()
        page("product-page/" + b["slug"], b["name"], body, 2, "Publishing",
             description=plain_desc[:155], og_image=b["cover"])

    # ---- 404 page (GitHub Pages / Netlify serve /404.html)
    body = page_head("404", "Page not found", "Sorry, we couldn't find that page.") + """
<section class="wrap"><p class="actions"><a class="button" href="/">Go to the home page</a><a class="button ghost" href="/catalog/">Browse books</a></p></section>"""
    page("", "Page not found", body, None, filename="404.html")

    print("Built %d books, %d authors, %d press links, %d data projects." % (len(books), len(authors), len(site["press"]), len(projects)))


if __name__ == "__main__":
    build()
