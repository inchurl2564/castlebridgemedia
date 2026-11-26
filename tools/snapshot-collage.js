// Renders the home-page cover collage, tilted and faded as on phones, into one small image
// (images/hero-collage.jpg). Phones use it as the hero background instead of loading 15 covers.
// Re-run after changing the featured books:  python3 build.py && python3 -m http.server 8765 &  node tools/snapshot-collage.js
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  await p.goto('http://localhost:8765/');
  await p.addStyleTag({ content: `
    .ticker, .site-header, .hero-copy { visibility: hidden !important; }
    .hero { position: relative !important; padding: 0 !important; height: 640px !important; overflow: hidden !important;
            background: #f4efe6 !important; margin: 0 !important; }
    .hero::after { content: "" !important; position: absolute !important; inset: 0 !important; z-index: 1 !important; height: auto !important;
      background: linear-gradient(180deg, rgba(244,239,230,.55), rgba(244,239,230,.15) 40%, rgba(244,239,230,.6)) !important; }
    .hero-grid { display: block !important; }
    .cover-wall { display: grid !important; position: absolute !important; inset: 0 !important; height: auto !important; margin: 0 !important;
      transform: rotate(4deg) scale(1.25) !important; opacity: .16 !important; -webkit-mask-image: none !important; mask-image: none !important; }
    .cover-wall img { content-visibility: visible; }` });
  await p.evaluate(() => document.querySelectorAll('.cover-wall img').forEach(i => { i.loading = 'eager'; }));
  await p.waitForFunction(() => [...document.querySelectorAll('.cover-wall img')].every(i => i.complete && i.naturalWidth));
  const box = await (await p.$('.hero')).boundingBox();
  await p.screenshot({ path: 'images/hero-collage.png', clip: box, fullPage: true });
  await b.close();
})();
