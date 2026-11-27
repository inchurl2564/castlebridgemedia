// Castle Bridge Media: small progressive enhancements. Every page works without this file.
(function () {
  // Mobile menu
  var toggle = document.querySelector('.menu-toggle');
  var nav = document.getElementById('site-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!open));
      document.body.classList.toggle('menu-open', !open);
    });
  }

  // Catalog search + genre dropdown (also reads #genre from the address, e.g. catalog/#horror)
  var q = document.getElementById('q');
  var genre = document.getElementById('genre');
  var cards = document.querySelectorAll('.catalog-grid .book-card');
  if (q && genre && cards.length) {
    var count = document.getElementById('count');
    var empty = document.getElementById('empty');
    var apply = function () {
      var t = q.value.trim().toLowerCase(), f = genre.value, n = 0;
      cards.forEach(function (c) {
        var genres = (c.getAttribute('data-genres') || '').split(' ');
        var hit = c.textContent.toLowerCase().indexOf(t) !== -1 && (f === 'all' || genres.indexOf(f) !== -1);
        c.hidden = !hit;
        if (hit) n++;
      });
      count.textContent = n + (n === 1 ? ' book' : ' books');
      empty.hidden = n !== 0;
    };
    var select = function (f) {
      genre.value = f;
      if (genre.value !== f) genre.value = 'all';
      apply();
    };
    q.addEventListener('input', apply);
    genre.addEventListener('change', function () {
      if (history.replaceState) {
        history.replaceState(null, '', genre.value === 'all' ? location.pathname + location.search : '#' + genre.value);
      }
      apply();
    });
    if (location.hash.length > 1) select(location.hash.slice(1));
    window.addEventListener('hashchange', function () { select(location.hash.slice(1) || 'all'); });
  }

  // Author bios: collapse long ones behind "Read more"
  document.querySelectorAll('.author .bio').forEach(function (bio) {
    if (bio.scrollHeight <= 190) return;
    bio.classList.add('clamped');
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'more';
    btn.textContent = 'Read more';
    btn.setAttribute('aria-expanded', 'false');
    btn.addEventListener('click', function () {
      var open = bio.classList.toggle('clamped') === false;
      btn.textContent = open ? 'Show less' : 'Read more';
      btn.setAttribute('aria-expanded', String(open));
    });
    bio.after(btn);
  });
})();

// Podcast archive search: loads podcast-1/episodes.json on first use and searches titles + descriptions.
(function () {
  var input = document.getElementById('ep-q');
  if (!input) return;
  var status = document.getElementById('ep-status');
  var results = document.getElementById('ep-results');
  var latest = document.getElementById('ep-latest');
  var data = null, loading = null, timer = null;

  var norm = function (s) {
    return (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  };
  var escapeHtml = function (s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var escapeRe = function (s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); };
  var mark = function (text, terms) {
    var html = escapeHtml(text);
    if (!terms.length) return html;
    var re = new RegExp('(' + terms.map(escapeRe).join('|') + ')', 'gi');
    return html.replace(re, '<mark>$1</mark>');
  };
  var snippet = function (text, terms) {
    var n = norm(text), at = -1;
    terms.forEach(function (t) { var i = n.indexOf(t); if (i !== -1 && (at === -1 || i < at)) at = i; });
    if (at < 0 || text.length <= 260) return text.length > 260 ? text.slice(0, 260) + '…' : text;
    var start = Math.max(0, at - 90);
    var out = text.slice(start, start + 260);
    return (start > 0 ? '…' : '') + out + (start + 260 < text.length ? '…' : '');
  };

  var load = function () {
    if (!loading) {
      status.textContent = 'Loading the episode archive…';
      loading = fetch(input.getAttribute('data-index'))
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (rows) {
          rows.forEach(function (r) { r._t = norm(r.t); r._s = norm(r.s); });
          data = rows;
          status.textContent = '';
        })
        .catch(function () { status.textContent = 'Sorry, the episode archive could not be loaded.'; });
    }
    return loading;
  };

  var render = function () {
    var q = input.value.trim();
    var terms = norm(q).split(/\s+/).filter(function (t) { return t.length > 1; });
    if (!terms.length) {
      results.hidden = true; latest.hidden = false; status.textContent = '';
      if (history.replaceState) history.replaceState(null, '', location.pathname);
      return;
    }
    if (!data) { load().then(render); return; }
    var hits = [];
    data.forEach(function (r) {
      var score = 0;
      for (var k = 0; k < terms.length; k++) {
        var inT = r._t.indexOf(terms[k]) !== -1, inS = r._s.indexOf(terms[k]) !== -1;
        if (!inT && !inS) return;
        score += inT ? 3 : 1;
      }
      hits.push({ r: r, score: score });
    });
    hits.sort(function (a, b) { return b.score - a.score || (b.r.o > a.r.o ? 1 : b.r.o < a.r.o ? -1 : 0); });
    var shown = hits.slice(0, 60);
    status.textContent = hits.length === 0 ? 'No episodes match “' + q + '”.' :
      hits.length + (hits.length === 1 ? ' episode matches' : ' episodes match') + ' “' + q + '”' +
      (hits.length > shown.length ? ' (showing the best ' + shown.length + ')' : '') + '.';
    var rawTerms = q.split(/\s+/).filter(function (t) { return t.length > 1; });
    results.innerHTML = shown.map(function (h) {
      var r = h.r;
      var meta = [r.d, r.m ? r.m + ' min' : ''].filter(Boolean).join(' · ');
      return '<li class="episode">' +
        (r.i ? '<img class="ep-thumb" src="' + escapeHtml(r.i) + '" alt="" width="140" height="140" loading="lazy">' : '<span></span>') +
        '<div><h3 class="episode-title">' + mark(r.t, rawTerms) + '</h3>' +
        '<p class="meta">' + escapeHtml(meta) + '</p>' +
        (r.a ? '<audio controls preload="none" src="' + escapeHtml(r.a) + '"></audio>' : '') +
        '<p class="episode-summary">' + mark(snippet(r.s, terms), rawTerms) +
        (r.l ? ' <a href="' + escapeHtml(r.l) + '" target="_blank" rel="noopener">Episode page</a>' : '') +
        '</p></div></li>';
    }).join('');
    results.hidden = false; latest.hidden = true;
    if (history.replaceState) history.replaceState(null, '', '?q=' + encodeURIComponent(q));
  };

  input.addEventListener('focus', load, { once: true });
  input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(render, 150); });
  var initial = new URLSearchParams(location.search).get('q');
  if (initial) { input.value = initial; render(); }
})();

// "Read a sample": phones go to the Amazon book page (its sample button works there); computers open the Kindle reader.
(function () {
  var phone = window.matchMedia && window.matchMedia('(pointer: coarse)').matches ||
    /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
  if (!phone) return;
  document.querySelectorAll('a.sample-link[data-mobile-href]').forEach(function (a) {
    a.href = a.getAttribute('data-mobile-href');
    a.textContent = 'Read a sample on Amazon';
  });
})();

// Back-to-top arrow: appears after scrolling down (shown on phones via CSS)
(function () {
  var btn = document.querySelector('.to-top');
  if (!btn) return;
  var onScroll = function () { btn.classList.toggle('is-visible', window.scrollY > 600); };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
  btn.addEventListener('click', function (e) { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
})();

// Contact form: posts into the Google Form through a hidden frame, then shows a thank-you note.
(function () {
  var form = document.getElementById('contact-form');
  if (!form) return;
  var thanks = document.getElementById('contact-thanks');
  var status = form.querySelector('.form-status');
  var sink = document.querySelector('iframe[name="contact-sink"]');
  var sent = false;
  form.addEventListener('submit', function () {
    // the Google Form also collects the responder's email separately; send the same address there
    form.querySelector('input[name="emailAddress"]').value = form.querySelector('input[type="email"]').value;
    sent = true;
    form.querySelector('button[type="submit"]').disabled = true;
    status.textContent = 'Sending…';
  });
  sink.addEventListener('load', function () {
    if (!sent) return;
    sent = false;
    form.reset();
    form.querySelector('button[type="submit"]').disabled = false;
    status.textContent = '';
    form.hidden = true;
    thanks.hidden = false;
    thanks.focus();
  });
  document.getElementById('contact-again').addEventListener('click', function () {
    thanks.hidden = true;
    form.hidden = false;
    form.querySelector('input').focus();
  });
})();
