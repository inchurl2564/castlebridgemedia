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

  // Catalog search + imprint filter
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
        var hit = c.textContent.toLowerCase().indexOf(t) !== -1 &&
          (filter === 'all' || c.getAttribute('data-imprint') === filter);
        c.hidden = !hit;
        if (hit) n++;
      });
      count.textContent = n + (n === 1 ? ' book' : ' books');
      empty.hidden = n !== 0;
    };
    q.addEventListener('input', apply);
    buttons.forEach(function (b) {
      b.addEventListener('click', function () {
        filter = b.getAttribute('data-filter');
        buttons.forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        apply();
      });
    });
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
