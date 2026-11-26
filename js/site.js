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

  // Catalog search + genre filter (also reads #genre from the address, e.g. catalog/#horror)
  var q = document.getElementById('q');
  var cards = document.querySelectorAll('.catalog-grid .book-card');
  if (q && cards.length) {
    var count = document.getElementById('count');
    var empty = document.getElementById('empty');
    var buttons = document.querySelectorAll('.filters button');
    var filter = 'all';
    var apply = function () {
      var t = q.value.trim().toLowerCase(), n = 0;
      cards.forEach(function (c) {
        var genres = (c.getAttribute('data-genres') || '').split(' ');
        var hit = c.textContent.toLowerCase().indexOf(t) !== -1 &&
          (filter === 'all' || genres.indexOf(filter) !== -1);
        c.hidden = !hit;
        if (hit) n++;
      });
      count.textContent = n + (n === 1 ? ' book' : ' books');
      empty.hidden = n !== 0;
    };
    var select = function (f, updateHash) {
      var found = false;
      buttons.forEach(function (x) {
        var on = x.getAttribute('data-filter') === f;
        if (on) found = true;
        x.setAttribute('aria-pressed', String(on));
      });
      if (!found) { f = 'all'; buttons[0].setAttribute('aria-pressed', 'true'); }
      filter = f;
      if (updateHash && history.replaceState) {
        history.replaceState(null, '', f === 'all' ? location.pathname + location.search : '#' + f);
      }
      apply();
    };
    q.addEventListener('input', apply);
    buttons.forEach(function (b) {
      b.addEventListener('click', function () { select(b.getAttribute('data-filter'), true); });
    });
    if (location.hash.length > 1) select(location.hash.slice(1), false);
    window.addEventListener('hashchange', function () { select(location.hash.slice(1) || 'all', false); });
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
