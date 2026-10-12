"""Server-rendered pages for reading the paper: front page, article, archive.

No JavaScript is needed to read; a few lines add the night-edition toggle
and arrow-key paging. Every image is served from this server, so reading
the paper never touches the outside network.
"""

import datetime
import html
import re
import time

from . import PROJECT_URL, boxes, i18n
from . import sections as sec_mod
from .build import tz

E = html.escape

CSS = r"""
:root{
  --paper:#f5f1e8; --paper-2:#ece6d8; --ink:#141311; --ink-2:#3a3631; --muted:#736c60;
  --rule:#141311; --hair:#d3cab8; --accent:#8e1f14; --shade:rgba(20,19,17,.06);
  --grain:.05; --greek:rgba(20,19,17,.13); --lift:rgba(60,42,12,.28);
  --mast:"Big Caslon","Bodoni 72",Didot,"Bodoni MT",Georgia,serif;
  --head:"Iowan Old Style","Charter","Bitstream Charter","Sitka Heading",Cambria,Georgia,"Noto Serif",serif;
  --body:Charter,"Bitstream Charter","Iowan Old Style","Sitka Text",Cambria,Georgia,"Noto Serif",serif;
  --label:"Avenir Next Condensed","Franklin Gothic Medium","Arial Narrow","Roboto Condensed",sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#131210; --paper-2:#1b1916; --ink:#ece5d8; --ink-2:#c9c1b2; --muted:#958c7d;
  --rule:#ece5d8; --hair:#37332c; --accent:#e27a68; --shade:rgba(0,0,0,.25); --grain:.035;
  --greek:rgba(236,229,216,.13); --lift:rgba(0,0,0,.65)}}
:root[data-theme="dark"]{
  --paper:#131210; --paper-2:#1b1916; --ink:#ece5d8; --ink-2:#c9c1b2; --muted:#958c7d;
  --rule:#ece5d8; --hair:#37332c; --accent:#e27a68; --shade:rgba(0,0,0,.25); --grain:.035;
  --greek:rgba(236,229,216,.13); --lift:rgba(0,0,0,.65)}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);
  font-size:17px;line-height:1.5;font-kerning:normal;font-variant-ligatures:common-ligatures;
  -webkit-font-smoothing:antialiased;min-height:100vh}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;opacity:var(--grain);
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 .9 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")}
.page{position:relative;z-index:1;max-width:1200px;margin:0 auto;padding:0 clamp(16px,3.6vw,44px) 72px}
a{color:inherit;text-decoration:none}
a:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.label{font-family:var(--label);font-weight:600;font-size:12px;letter-spacing:.14em;text-transform:uppercase}
img{display:block;max-width:100%;height:auto}

/* strip + masthead */
.strip{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 0 0;color:var(--muted)}
.strip nav{display:flex;gap:18px;align-items:center}
.strip a:hover{color:var(--ink)}
.theme{background:none;border:0;color:inherit;cursor:pointer;padding:4px;font:inherit;line-height:1}
.mast{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,auto) minmax(0,1fr);align-items:end;
  gap:20px;padding:18px 0 14px}
.mast h1{margin:0;text-align:center;font-family:var(--mast);font-weight:700;letter-spacing:-.01em;
  font-size:clamp(30px,9.6vw,80px);line-height:.95;text-wrap:balance}
.ear{font-family:var(--label);font-size:12px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);line-height:1.35;border:1px solid var(--hair);padding:7px 10px;max-width:160px}
.ear b{color:var(--ink);font-weight:700}
.ear.r{justify-self:end;text-align:end}
.dateline{border-top:3px solid var(--rule);border-bottom:1px solid var(--rule);margin-top:2px;
  padding:7px 0;display:flex;justify-content:center;gap:10px 22px;flex-wrap:wrap;position:relative}
.dateline::before{content:"";position:absolute;left:0;right:0;top:2px;border-top:1px solid var(--rule)}
.sections{display:flex;justify-content:center;flex-wrap:wrap;gap:6px 26px;padding:10px 0;
  border-bottom:1px solid var(--hair)}
.sections a{color:var(--ink-2)}
.sections a:hover{color:var(--accent)}

/* shared story bits */
.kicker{color:var(--accent);margin:0 0 8px}
.kicker span{color:var(--muted)}
.hl{font-family:var(--head);font-weight:700;letter-spacing:-.012em;line-height:1.08;margin:0;
  text-wrap:balance}
.hl a{background:linear-gradient(currentColor,currentColor) 0 100%/0 1px no-repeat;
  transition:background-size .25s ease}
.hl a:hover{background-size:100% 1px}
.deck{font-family:var(--body);font-style:italic;color:var(--ink-2);margin:10px 0 0;text-wrap:pretty}
.meta{color:var(--muted);margin-top:10px;font-size:11px}
.pic{margin:0 0 12px;overflow:hidden;background:var(--paper-2)}
.pic img{width:100%;filter:grayscale(.18) contrast(1.04);transition:filter .4s ease}
a:hover .pic img,.pic:hover img{filter:none}

/* front page */
.front{display:grid;grid-template-columns:minmax(0,2.05fr) minmax(0,1fr);gap:0;padding:26px 0 30px;
  border-bottom:3px double var(--rule)}
.lead{padding-inline-end:30px}
.lead .hl{font-size:clamp(32px,4.4vw,56px);line-height:1.02}
.lead .deck{font-size:21px;line-height:1.38;margin-top:14px}
.lead .pic{margin:18px 0 8px}
.lead .pic img{max-height:560px;object-fit:cover}
.lead .text{columns:2 260px;column-gap:28px;column-rule:1px solid var(--hair);margin-top:16px;
  font-size:17px;line-height:1.55;hyphens:auto;-webkit-hyphens:auto}
.lead .text p{margin:0 0 .8em;text-align:justify;text-align-last:start}
.lead .text p:first-child::first-letter{float:left;font-family:var(--head);font-weight:700;
  font-size:3.6em;line-height:.82;padding:6px 8px 0 0;color:var(--ink)}
.more{display:inline-block;margin-top:4px;color:var(--accent)}
.more:hover{text-decoration:underline}
.rail{border-inline-start:1px solid var(--hair);padding-inline-start:26px}
.rail article{padding:0 0 18px;margin:0 0 18px;border-bottom:1px solid var(--hair)}
.rail article:last-child{border-bottom:0;margin-bottom:0}
.rail .hl{font-size:23px}
.rail .deck{font-size:15.5px;line-height:1.42;font-style:normal}

/* sections */
.sec{padding-top:34px}
.sec-h{display:flex;align-items:center;gap:16px;margin:0 0 20px}
.sec-h h2{margin:0;font-family:var(--label);font-weight:700;font-size:15px;letter-spacing:.22em;
  text-transform:uppercase;white-space:nowrap}
.sec-h::before,.sec-h::after{content:"";height:0;border-top:1px solid var(--rule);flex:1}
.sec-h::before{max-width:28px}
.sec-h::after{order:1}
.totop{order:2;color:var(--muted);white-space:nowrap;font-size:11px}
.totop:hover{color:var(--accent)}
.feature{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:26px;
  padding-bottom:22px;margin-bottom:22px;border-bottom:1px solid var(--hair)}
.feature .pic{margin:0}
.feature .pic img{aspect-ratio:3/2;object-fit:cover}
.feature .hl{font-size:clamp(25px,2.6vw,34px)}
.feature .deck{font-size:17px}
/* Grid, not CSS columns: Chrome stacks a handful of cards into one column.
   Each card carries a start-side hairline; the wrapper clips the first column's. */
.cols-wrap{overflow:hidden}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));margin-inline-start:-27px}
.card{border-inline-start:1px solid var(--hair);border-bottom:1px solid var(--hair);padding:0 0 18px;padding-inline-start:26px;margin-bottom:18px}
.card .hl{font-size:19.5px}
.card .deck{font-size:15px;line-height:1.42;font-style:normal}
.card .pic img{aspect-ratio:16/10;object-fit:cover}
.card.strip-art .pic img{aspect-ratio:auto;object-fit:contain;filter:none}
.card.strip-art .pic{background:none}

/* article */
.art-top{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;
  padding:16px 0 12px;border-bottom:3px double var(--rule)}
.art-top .mini{font-family:var(--mast);font-weight:700;font-size:clamp(22px,3.6vw,32px);
  text-align:center;line-height:1;white-space:nowrap}
.art-top .l{color:var(--muted)} .art-top .r{color:var(--muted);text-align:end}
.art-top a:hover{color:var(--ink)}
.story{max-width:690px;margin:0 auto;padding-top:38px}
.story .kicker{text-align:center}
.story h1.hl{font-size:clamp(32px,5vw,52px);text-align:center;line-height:1.05}
.story .deck{text-align:center;font-size:21px;line-height:1.4;margin-top:16px}
.byline{display:flex;justify-content:center;flex-wrap:wrap;gap:4px 18px;color:var(--muted);
  border-top:1px solid var(--hair);border-bottom:1px solid var(--hair);padding:9px 0;margin:24px 0 26px}
.byline b{color:var(--ink);font-weight:700}
.story-fig{max-width:900px;margin:0 auto 30px}
.story-fig img{width:100%;max-height:640px;object-fit:contain;background:var(--paper-2)}
.story-fig figcaption{max-width:690px;margin:12px auto 0;font-style:italic;color:var(--ink-2);text-align:center;font-size:16px}
.body{font-size:19px;line-height:1.66;hyphens:auto;-webkit-hyphens:auto;overflow-wrap:break-word}
.body p{margin:0 0 1.05em}
.body > p:first-of-type::first-letter{float:left;font-family:var(--head);font-weight:700;
  font-size:4.1em;line-height:.8;padding:7px 10px 0 0}
.body > p:last-of-type::after{content:"\25A0";color:var(--accent);font-size:.7em;margin-inline-start:.4em;vertical-align:1px}
.body h2,.body h3,.body h4{font-family:var(--head);line-height:1.2;margin:1.6em 0 .5em}
.body h2{font-size:1.35em} .body h3{font-size:1.18em} .body h4{font-size:1.05em}
.body a{text-decoration:underline;text-decoration-color:var(--hair);text-underline-offset:3px;
  text-decoration-thickness:1px}
.body a:hover{text-decoration-color:var(--accent)}
.body img{margin:1.4em auto;max-height:700px;width:auto}
.body figure{margin:1.6em 0}
.body figcaption{font-family:var(--label);font-size:13px;letter-spacing:.02em;color:var(--muted);margin-top:-.8em}
.body blockquote{margin:1.4em 0;padding:0;padding-inline-start:22px;border-inline-start:3px solid var(--accent);
  font-family:var(--head);font-size:1.12em;font-style:italic;color:var(--ink-2)}
.body ul,.body ol{padding-inline-start:1.3em} .body li{margin:.3em 0}
.body pre{font-family:var(--mono);font-size:14px;background:var(--paper-2);padding:14px;overflow-x:auto;line-height:1.45}
.body code{font-family:var(--mono);font-size:.86em}
.body table{border-collapse:collapse;width:100%;font-size:15px;display:block;overflow-x:auto}
.body th,.body td{border-bottom:1px solid var(--hair);padding:6px 8px;text-align:start;vertical-align:top}
.body hr{border:0;text-align:center;margin:2em 0} .body hr::after{content:"\2042";color:var(--muted)}
.note{border:1px solid var(--hair);background:var(--paper-2);padding:12px 16px;margin:26px 0 0;
  font-size:15px;color:var(--ink-2)}
.source{display:flex;justify-content:center;margin:34px 0 0}
.btn{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--rule);padding:10px 18px;
  font-family:var(--label);font-weight:600;font-size:12.5px;letter-spacing:.14em;text-transform:uppercase;
  background:none;color:var(--ink);cursor:pointer}
.btn:hover{background:var(--ink);color:var(--paper)}
.pager{display:grid;grid-template-columns:1fr 1fr;gap:0;margin:46px auto 0;max-width:900px;
  border-top:3px double var(--rule)}
.pager a{padding:16px 0}
.pager a + a,.pager span + a{border-inline-start:1px solid var(--hair);padding-inline-start:22px;text-align:end}
.pager .hl{font-size:19px;margin-top:6px}
.pager a:hover .hl{color:var(--accent)}

/* archive + empty */
.archive{max-width:760px;margin:30px auto 0}
.archive a.row{display:grid;grid-template-columns:auto 1fr auto;gap:18px;align-items:baseline;
  padding:16px 2px;border-bottom:1px solid var(--hair)}
.archive a.row:hover .hl{color:var(--accent)}
.archive .no{font-family:var(--mast);font-size:30px;font-weight:700;min-width:64px}
.archive .hl{font-size:23px}
.empty{text-align:center;max-width:520px;margin:70px auto 0}
.empty p{color:var(--ink-2);font-size:19px;font-style:italic}
footer.colophon{margin-top:56px;padding-top:12px;border-top:1px solid var(--rule);display:flex;
  justify-content:space-between;flex-wrap:wrap;gap:8px;color:var(--muted)}
footer.colophon a:hover{color:var(--ink)}

/* weather ear, breaking band, boxes */
.ear.wx{display:flex;gap:9px;align-items:center;max-width:210px;text-align:start}
.ear.wx svg{flex:none;color:var(--ink)}
.dl-wx{display:none}
.breaking{display:flex;align-items:stretch;border-bottom:1px solid var(--rule);margin-top:-1px}
.breaking .flag{background:var(--accent);color:var(--paper);padding:10px 14px;display:flex;align-items:center;
  white-space:nowrap;font-weight:700;letter-spacing:.2em}
.breaking ul{list-style:none;margin:0;padding:10px 0 10px 20px;flex:1;display:grid;
  grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:7px 30px;align-content:center}
.breaking li{font-family:var(--head);font-weight:700;font-size:16px;line-height:1.3;padding-inline-start:15px;position:relative}
.breaking li::before{content:"";position:absolute;inset-inline-start:0;top:.5em;width:6px;height:6px;background:var(--accent)}
.breaking a:hover{color:var(--accent)}
.wx-panel{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,2fr);border:1px solid var(--rule);margin-bottom:8px}
.wx-main{padding:20px 22px;border-inline-end:1px solid var(--hair)}
.wx-today{display:flex;gap:18px;align-items:center}
.wx-today svg{color:var(--ink);flex:none}
.wx-desc{margin:0;font-family:var(--head);font-weight:700;font-size:22px}
.wx-temp{margin:2px 0 0;font-family:var(--mast);font-size:52px;line-height:1;font-weight:700}
.wx-temp span{font-size:24px;color:var(--muted);font-weight:400}
.wx-f{margin:6px 0 0;color:var(--muted);font-size:11px}
.wx-facts{display:grid;grid-template-columns:1fr 1fr;gap:10px 18px;margin:18px 0 0;padding-top:14px;border-top:1px solid var(--hair)}
.wx-facts dt{color:var(--muted);font-size:10.5px}
.wx-facts dd{margin:2px 0 0;font-family:var(--body);font-size:15px;letter-spacing:0;text-transform:none;font-weight:400;color:var(--ink)}
.wx-days{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}
.wx-day{padding:20px 18px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:8px}
.wx-day + .wx-day{border-inline-start:1px solid var(--hair)}
.wx-day p{margin:0}
.wx-day svg{color:var(--ink)}
.wx-hl{font-family:var(--head);font-weight:700;font-size:22px}
.wx-hl span{color:var(--muted);font-weight:400;font-size:18px}
.rainbar{width:70%;height:4px;background:var(--hair)}
.rainbar i{display:block;height:100%;background:var(--accent)}
.wx-place{color:var(--muted);font-size:10.5px;margin:0 0 22px}
.otd{border-top:3px double var(--rule);border-bottom:1px solid var(--rule);padding:16px 0 6px;margin-bottom:24px}
.otd-h{margin:0 0 12px;color:var(--accent)}
.otd ol{list-style:none;margin:0;padding:0;columns:2 320px;column-gap:34px;column-rule:1px solid var(--hair)}
.otd li{break-inside:avoid;display:grid;grid-template-columns:62px 1fr;gap:12px;padding:0 0 14px}
.otd .yr{font-family:var(--mast);font-weight:700;font-size:24px;line-height:1.05}
.otd p{margin:0;font-size:15.5px;line-height:1.45;color:var(--ink-2)}
.otd a:hover{color:var(--accent)}
.otd-credit{margin:2px 0 0;font-size:10.5px;color:var(--muted)}
.otd-credit a:hover{color:var(--accent)}

/* editions: each issue as a miniature front page (sized in container units) */
.editions{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:40px 30px;margin-top:34px}
.ed{position:relative}
.ed > a{display:block}
.sheet{position:relative;aspect-ratio:5/7;background:var(--paper);border:1px solid var(--hair);overflow:hidden;
  container-type:inline-size;box-shadow:5px 5px 0 -1px var(--paper),5px 5px 0 0 var(--hair),0 16px 28px -18px var(--lift);
  transition:transform .4s cubic-bezier(.2,.7,.2,1),box-shadow .4s}
.sheet::after{content:"";position:absolute;left:0;right:0;bottom:0;height:16%;background:linear-gradient(transparent,var(--paper))}
.ed > a:hover .sheet,.ed > a:focus-visible .sheet{transform:translateY(-6px) rotate(-.7deg);
  box-shadow:5px 5px 0 -1px var(--paper),5px 5px 0 0 var(--hair),0 26px 36px -18px var(--lift)}
.cv{padding:6cqw 6cqw 0;height:100%;color:var(--ink)}
.c-top{display:flex;justify-content:space-between;align-items:center;font:600 2.7cqw/1 var(--label);letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted)}
.c-top svg{width:4.4cqw;height:4.4cqw;vertical-align:-1.2cqw;margin-inline-end:.8cqw;color:var(--ink)}
.c-mast{font:700 10.4cqw/1 var(--mast);text-align:center;white-space:nowrap;overflow:hidden;margin:3cqw 0 2.4cqw;letter-spacing:-.01em}
.c-rule{height:1.6cqw;border-top:.9cqw solid var(--rule);border-bottom:.35cqw solid var(--rule)}
.c-dl{font:600 2.5cqw/1 var(--label);letter-spacing:.12em;text-transform:uppercase;text-align:center;padding:1.7cqw 0;
  border-bottom:.35cqw solid var(--rule)}
.c-band{display:flex;gap:1.6cqw;align-items:center;border-bottom:.35cqw solid var(--rule);padding:1.3cqw 0;
  font:700 2.6cqw/1.2 var(--head);white-space:nowrap;overflow:hidden}
.c-band b{background:var(--accent);color:var(--paper);font:700 2.2cqw/1 var(--label);letter-spacing:.14em;padding:.9cqw 1.4cqw}
.c-body{display:grid;grid-template-columns:61fr 39fr;gap:3.6cqw;margin-top:3.6cqw}
.c-lead img,.c-lead .ph{width:100%;aspect-ratio:4/3;object-fit:cover;filter:grayscale(.2) contrast(1.03);background:var(--paper-2)}
.c-hl{font:700 5.2cqw/1.06 var(--head);margin:2.2cqw 0 2cqw;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.c-rail{border-inline-start:.35cqw solid var(--hair);padding-inline-start:3.2cqw}
.c-rail .c-hl{font-size:3.3cqw;margin:0 0 1.4cqw}
.c-rail .c-hl ~ .c-hl{margin-top:2.6cqw}
.greek{display:block;height:calc(var(--n,4) * 2.25cqw);background:repeating-linear-gradient(to bottom,var(--greek) 0 1cqw,transparent 1cqw 2.25cqw)}
.c-foot{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:3cqw;margin-top:3.6cqw;padding-top:3cqw;border-top:.35cqw solid var(--rule)}
.c-foot .k{font:600 2.1cqw/1 var(--label);letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
.c-foot .c-hl{font-size:3cqw;margin:1.2cqw 0}
.ed-cap{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-top:16px}
.ed-cap .hl{font-size:19px}
.ed-cap .label{color:var(--muted);font-size:11px;white-space:nowrap}
.ed-tag{position:absolute;top:-10px;inset-inline-start:12px;z-index:2;background:var(--accent);color:var(--paper);padding:4px 9px;
  font-size:10.5px}
.ed-epub{color:var(--muted);font-size:11px}
.ed-epub:hover{color:var(--accent)}

/* motion */
@media (prefers-reduced-motion:no-preference){
  html{scroll-behavior:smooth}
  .rise{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}
  .d1{animation-delay:.06s}.d2{animation-delay:.14s}.d3{animation-delay:.22s}.d4{animation-delay:.3s}
  @keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
}

/* narrow */
@media (max-width:1100px){
  .mast{grid-template-columns:1fr;gap:10px}
  .ear,.ear.wx{display:none}
  .dl-wx{display:inline-flex;gap:6px;align-items:center}
  .dl-wx svg{width:15px;height:15px}
}
@media (max-width:860px){
  .front{grid-template-columns:1fr}
  .lead{padding-inline-end:0}
  .rail{border-inline-start:0;padding-inline-start:0;border-top:1px solid var(--rule);margin-top:26px;padding-top:22px}
  .feature{grid-template-columns:1fr}
  .wx-panel{grid-template-columns:1fr}
  .wx-main{border-inline-end:0;border-bottom:1px solid var(--hair)}
  .breaking{flex-direction:column}
  .breaking .flag{align-self:flex-start}
  .breaking ul{padding:12px 0;grid-template-columns:1fr}
}
@media (max-width:560px){
  body{font-size:16px}
  .strip .date{display:none}
  .dateline{gap:4px 14px}
  .lead .deck,.story .deck{font-size:18px}
  .lead .text p{text-align:start}
  .body{font-size:18px}
  .art-top{grid-template-columns:auto 1fr auto}
  .art-top .r{display:none}
  .pager{grid-template-columns:1fr}
  .pager a + a,.pager span + a{border-inline-start:0;padding-inline-start:0;text-align:start;border-top:1px solid var(--hair)}
  .archive a.row{grid-template-columns:auto 1fr}
  .archive a.row .label:last-child{display:none}
  .editions{grid-template-columns:repeat(2,minmax(0,1fr));gap:30px 18px}
  .ed-cap{flex-direction:column;gap:2px}
  .wx-days{grid-template-columns:repeat(3,minmax(0,1fr))}
  .wx-day{padding:14px 6px}
}
/* Right-to-left papers (Arabic): the layout above uses logical sides, so it mirrors on its own.
   Stories keep their feed's direction, so an English story still reads left to right. */
[dir=rtl] .arw{display:inline-block;transform:scaleX(-1)}
[dir=rtl] .hl,[dir=rtl] .deck,[dir=rtl] .body p,[dir=rtl] .body li,[dir=rtl] .body h2,[dir=rtl] .body h3,
[dir=rtl] .body h4,[dir=rtl] .body blockquote,[dir=rtl] .lead .text p,[dir=rtl] .c-hl{unicode-bidi:plaintext}
:lang(ar) *{letter-spacing:0 !important}
[dir=rtl] .lead .text p:first-child::first-letter,[dir=rtl] .body > p:first-of-type::first-letter,
:lang(zh) .lead .text p:first-child::first-letter,:lang(zh) .body > p:first-of-type::first-letter{
  float:none;font:inherit;line-height:inherit;padding:0;color:inherit}
"""

THEME_JS = """<script>try{var t=localStorage.getItem('pb-theme');if(t)document.documentElement.setAttribute('data-theme',t)}catch(e){}</script>"""

TOGGLE_JS = """<script>
document.querySelectorAll('.theme').forEach(function(b){b.addEventListener('click',function(){
var r=document.documentElement,cur=r.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'),
nx=cur==='dark'?'light':'dark';r.setAttribute('data-theme',nx);try{localStorage.setItem('pb-theme',nx)}catch(e){}})});
document.addEventListener('keydown',function(e){if(e.metaKey||e.ctrlKey||e.altKey||/INPUT|TEXTAREA/.test(e.target.tagName))return;
var a=document.querySelector(e.key==='ArrowLeft'?'a[rel=prev]':e.key==='ArrowRight'?'a[rel=next]':null);if(a)location.href=a.href});
</script>"""

MOON = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">'
        '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/></svg>')


def doc(title, body, desc="", lang="en"):
    return ("<!doctype html><html lang=\"%s\"%s><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">"
            "<meta name=\"color-scheme\" content=\"light dark\">"
            "<title>%s</title>%s<style>%s</style>%s</head><body><div class=\"page\" id=\"top\">%s</div>%s</body></html>"
            % (i18n.lang_of(lang), ' dir="rtl"' if i18n.direction(lang) == "rtl" else "", E(title), "<meta name=\"description\" content=\"%s\">" % E(desc) if desc else "",
               CSS, THEME_JS, body, TOGGLE_JS))


def strip(left="", lang="en"):
    L = i18n.strings(lang)
    return ('<div class="strip label"><span class="date">%s</span><nav><a href="/">%s</a>'
            '<a href="/archive">%s</a><a href="/desk">%s</a>'
            '<button class="theme" type="button" title="%s" aria-label="%s">%s</button>'
            '</nav></div>' % (E(left), L["today"], L["editions"], L["desk"], L["night"], L["night"], MOON))


def _when(ts, zone):
    return datetime.datetime.fromtimestamp(ts, tz(zone))


def clock(ts, zone, lang="en"):
    return i18n.stamp(_when(ts, zone), lang) if ts else ""


def hour(ts, zone, lang="en"):
    d = _when(ts, zone)
    return i18n.hm(d.hour, d.minute, lang)


def _src(markup, date):
    return markup.replace('src="img/', 'src="/issue/%s/img/' % date)


def _img(st, date, cls="pic"):
    if not st["image"]:
        return ""
    return '<figure class="%s"><img src="/issue/%s/%s" alt="" loading="lazy"></figure>' % (cls, date, E(st["image"]))


def _url(issue, st):
    return "/issue/%s/%s" % (issue["date"], st["id"])


def _kicker(st, with_section=True, names=None):
    sec = E((names or {}).get(st["section"], st["section"])) if with_section else ""
    src = E(st["source"])
    if sec and src:
        return '<p class="kicker label">%s <span>&middot; %s</span></p>' % (sec, src)
    return '<p class="kicker label">%s</p>' % (sec or src)


def _norm(s):
    return re.sub(r"\W+", "", (s or "").lower())


def _deck_needed(st):
    lead_text = _norm(re.sub(r"<[^>]+>", " ", st["html"]))[:400]
    d = _norm(st["summary"])[:80]
    return bool(d) and d not in lead_text


def _lead_text(st, words=170):
    paras, n = [], 0
    for p in re.findall(r"<p>.*?</p>", st["html"], re.S):
        if "<img" in p:
            continue
        paras.append(p)
        n += len(re.sub(r"<[^>]+>", " ", p).split())
        if n >= words:
            break
    return "".join(paras) or "<p>%s</p>" % E(st["summary"])


BAND_MAX = 6


def _deg(c):
    return "%d&deg;" % int(round(c)) if c is not None else "&ndash;"


def _hm(hhmm, lang="en"):
    try:
        h, m = [int(x) for x in hhmm.split(":")]
    except ValueError:
        return ""
    return i18n.hm(h, m, lang)


def _pct(v):
    return v if v is not None else "&ndash;"


def _desc(d, lang):
    return i18n.weather(d.get("code"), d.get("desc") or "", lang)


def weather_ear(w, lang="en"):
    d, L = w["days"][0], i18n.strings(lang)
    return ('<div class="ear r wx">%s<div><b>%s</b><br>%s / %sC &middot; %s</div></div>'
            % (boxes.icon(d["icon"], 30), E(_desc(d, lang) or w["place"]), _deg(d["hi"]), _deg(d["lo"]),
               L["rain_pct"] % _pct(d["rain_pct"])))


def weather_panel(w, lang="en"):
    t, L = w["days"][0], i18n.strings(lang)
    f_hi, f_lo = boxes.c_to_f(t["hi"]), boxes.c_to_f(t["lo"])
    facts = [(L["rain"], "%s%% &middot; %s mm" % (_pct(t["rain_pct"]),
                                                   "%.1f" % t["rain_mm"] if t["rain_mm"] is not None else "&ndash;")),
             (L["wind"], "%s km/h" % ("%d" % round(t["wind"]) if t["wind"] is not None else "&ndash;")),
             (L["uv"], "%.0f" % t["uv"] if t["uv"] is not None else "&ndash;"),
             (L["sun"], "%s &ndash; %s" % (_hm(t["sunrise"], lang), _hm(t["sunset"], lang)))]
    main = ('<div class="wx-main"><div class="wx-today">%s<div><p class="wx-desc">%s</p>'
            '<p class="wx-temp">%s<span> / %sC</span></p><p class="wx-f label">%s / %sF</p></div></div>'
            '<dl class="wx-facts label">%s</dl></div>'
            % (boxes.icon(t["icon"], 64), E(_desc(t, lang)), _deg(t["hi"]), _deg(t["lo"]), _deg(f_hi), _deg(f_lo),
               "".join("<div><dt>%s</dt><dd>%s</dd></div>" % f for f in facts)))
    days = "".join(
        '<div class="wx-day"><p class="label">%s</p>%s<p class="wx-hl">%s <span>%s</span></p>'
        '<div class="rainbar" title="%s"><i style="width:%d%%"></i></div><p class="label meta">%s</p></div>'
        % (i18n.weekday(d["date"], lang), boxes.icon(d["icon"], 34), _deg(d["hi"]), _deg(d["lo"]),
           L["chance_rain"], d["rain_pct"] or 0, L["rain_pct"] % _pct(d["rain_pct"]))
        for d in w["days"][1:4])
    return ('<div class="wx-panel">%s<div class="wx-days">%s</div></div>'
            '<p class="wx-place label">%s</p>' % (main, days, L["forecast"] % E(w["place"])))


def otd_box(o, date, lang="en"):
    L = i18n.strings(lang)
    items = "".join('<li><span class="yr">%d</span><p>%s</p></li>' % (
        e["year"], '<a href="%s" rel="noopener noreferrer" target="_blank">%s</a>' % (E(e["link"]), E(e["text"]))
        if e["link"] else E(e["text"])) for e in o["events"])
    return ('<div class="otd"><h3 class="otd-h label">%s</h3><ol>%s</ol>'
            '<p class="otd-credit label"><a href="https://creativecommons.org/licenses/by-sa/4.0/" '
            'rel="noopener noreferrer license" target="_blank">%s</a></p></div>'
            % (L["otd"] % E(i18n.month_day(date, lang)), items, L["otd_credit"]))


def _role(sec):
    return sec.get("role") if "role" in sec else sec_mod.role(sec["name"])


def section_names(issue):
    """What each section of an issue prints as: the desk's names, else the language's usual ones."""
    lang, custom = issue.get("language") or "en", issue.get("section_labels")
    return {sec["name"]: i18n.section_name(sec["name"], lang, custom) for sec in issue["sections"]}


def layout(issue):
    """Everything the front page and the cover thumbnail share."""
    stories = {st["id"]: st for sec in issue["sections"] for st in sec["stories"]}
    lead = stories.get(issue["front"]["lead"])
    rail = [stories[i] for i in issue["front"]["rail"] if i in stories]
    breaking = [st for sec in issue["sections"] if _role(sec) == "breaking" for st in sec["stories"]][:BAND_MAX]
    used = set(st["id"] for st in rail + breaking) | set([lead["id"]] if lead else [])
    shown = []
    for sec in issue["sections"]:
        rest = [st for st in sec["stories"] if st["id"] not in used]
        if rest or sec.get("box"):
            shown.append((sec, rest))
    return stories, lead, rail, breaking, shown


def _source_link(L):
    return ('<a href="%s" rel="noopener noreferrer">%s &middot; %s</a>' % (E(PROJECT_URL), L["free_software"], L["source"])
            if PROJECT_URL else L["free_software"])


def front_page(issue, zone):
    date, lang = issue["date"], issue.get("language") or "en"
    L = i18n.strings(lang)
    stories, lead, rail, breaking, shown = layout(issue)
    names = section_names(issue)
    total = len(stories)
    w = issue.get("weather")
    day = i18n.long_date(date, lang)

    out = [strip(day, lang)]
    right = weather_ear(w, lang) if w else ('<div class="ear r"><b>%s</b><br>%s</div>'
                                            % (E(issue.get("edition") or ""), L["printed"] % hour(issue["built_at"], zone, lang)))
    out.append('<header class="mast rise"><div class="ear"><b>%s</b><br>%s</div>'
               '<h1><a href="/issue/%s/">%s</a></h1>%s</header>'
               % (L["no"] % issue["number"], L["stories_sources"] % (total, issue.get("sources", 0)), date,
                  E(issue["paper"]), right))
    dl = [L["no"] % issue["number"], E(day)]
    if issue.get("edition"):
        dl.append(E(issue["edition"]))
    dl.append(L["printed"] % hour(issue["built_at"], zone, lang))
    wx_dl = ('<span class="dl-wx">%s%s / %s</span>' % (boxes.icon(w["days"][0]["icon"], 15), _deg(w["days"][0]["hi"]),
                                                        _deg(w["days"][0]["lo"]))) if w else ""
    out.append('<div class="dateline label rise d1">%s%s</div>' % ("".join("<span>%s</span>" % x for x in dl), wx_dl))
    nav = [(i, sec) for i, (sec, _) in enumerate(shown) if _role(sec) != "front"]
    if len(nav) > 1:
        out.append('<nav class="sections label rise d1">%s</nav>' % "".join(
            '<a href="#s%d">%s</a>' % (i, E(names[sec["name"]])) for i, sec in nav))
    if breaking:
        out.append('<div class="breaking rise d1"><span class="flag label">%s</span><ul>%s</ul></div>' % (
            L["breaking"], "".join('<li><a href="%s">%s</a></li>' % (_url(issue, st), E(st["title"])) for st in breaking)))

    if lead:
        deck = '<p class="deck">%s</p>' % E(lead["summary"]) if _deck_needed(lead) else ""
        out.append('<section class="front"><article class="lead rise d2">%s<h2 class="hl"><a href="%s">%s</a></h2>%s'
                   '<p class="meta label">%s%s</p>%s'
                   '<div class="text">%s</div><a class="more label" href="%s">%s <span class="arw">&rarr;</span></a></article>'
                   % (_kicker(lead, names=names), _url(issue, lead), E(lead["title"]), deck,
                      (L["by"] % E(lead["author"]) + " &middot; ") if lead["author"] else "",
                      L["min_read"] % lead["minutes"],
                      '<a href="%s">%s</a>' % (_url(issue, lead), _img(lead, date)) if lead["image"] else "",
                      _src(_lead_text(lead), date), _url(issue, lead), L["continue"]))
        if rail:
            out.append('<aside class="rail rise d3">')
            for i, st in enumerate(rail):
                pic = '<a href="%s">%s</a>' % (_url(issue, st), _img(st, date)) if i == 0 and st["image"] else ""
                out.append('<article>%s%s<h3 class="hl"><a href="%s">%s</a></h3><p class="deck">%s</p>'
                           '<p class="meta label">%s</p></article>'
                           % (pic, _kicker(st, names=names), _url(issue, st), E(st["title"]), E(st["summary"][:180]),
                              L["min_read"] % st["minutes"]))
            out.append("</aside>")
        out.append("</section>")

    for i, (sec, rest) in enumerate(shown):
        title = L["more_top"] if _role(sec) == "front" else names[sec["name"]]
        out.append('<section class="sec rise d4" id="s%d"><div class="sec-h"><h2>%s</h2>'
                   '<a class="totop label" href="#top">%s &uarr;</a></div>' % (i, E(title), L["back_top"]))
        if sec.get("box") == "weather" and w:
            out.append(weather_panel(w, lang))
        elif sec.get("box") == "onthisday" and issue.get("onthisday"):
            out.append(otd_box(issue["onthisday"], date, lang))
        feat = rest[0] if rest and rest[0]["image"] and rest[0]["mode"] == "full" else None
        if feat:
            deck = '<p class="deck">%s</p>' % E(feat["summary"]) if feat["summary"] else ""
            out.append('<article class="feature"><a href="%s">%s</a><div>%s<h3 class="hl"><a href="%s">%s</a></h3>%s'
                       '<p class="meta label">%s</p></div></article>'
                       % (_url(issue, feat), _img(feat, date), _kicker(feat, False), _url(issue, feat),
                          E(feat["title"]), deck, L["min_read"] % feat["minutes"]))
            rest = rest[1:]
        if rest:
            out.append('<div class="cols-wrap"><div class="cols">')
            for st in rest:
                art = st["mode"] == "feed" and st["image"]
                pic = '<a href="%s">%s</a>' % (_url(issue, st), _img(st, date)) if st["image"] else ""
                summ = ('<p class="deck"><em>%s</em></p>' % E(st["caption"][:200]) if st.get("caption") else "") \
                    if art else '<p class="deck">%s</p>' % E(st["summary"][:200])
                out.append('<article class="card%s">%s%s<h3 class="hl"><a href="%s">%s</a></h3>%s'
                           '<p class="meta label">%s</p></article>'
                           % (" strip-art" if art else "", pic, _kicker(st, False), _url(issue, st),
                              E(st["title"]), summ,
                              clock(st["published"], zone, lang) if art else L["min_read"] % st["minutes"]))
            out.append("</div></div>")
        out.append("</section>")

    out.append('<footer class="colophon label"><span>%s &middot; %s</span>'
               '<span><a href="#top">%s &uarr;</a> &middot; <a href="/issue/%s/epub">%s</a> &middot; '
               '<a href="/archive">%s</a></span></footer>'
               % (L["printed_by"] % hour(issue["built_at"], zone, lang), _source_link(L), L["back_top"], date,
                  L["download_epub"], L["all_editions"]))
    return doc("%s — %s" % (issue["paper"], day), "".join(out),
               "%s, %s" % (re.sub("<[^>]+>", "", L["no"] % issue["number"]), L["n_stories"] % total), lang)


def cover(issue):
    """A miniature of the issue's front page, drawn in container units."""
    date, lang = issue["date"], issue.get("language") or "en"
    L = i18n.strings(lang)
    stories, lead, rail, breaking, shown = layout(issue)
    names = section_names(issue)
    w = issue.get("weather")
    top_r = ("%s%s / %s" % (boxes.icon(w["days"][0]["icon"], 12), _deg(w["days"][0]["hi"]), _deg(w["days"][0]["lo"]))
             if w else L["n_stories"] % len(stories))
    out = ['<div class="cv"><div class="c-top"><span>%s</span><span>%s</span></div>'
           % (i18n.weekday(date, lang), top_r),
           '<div class="c-mast">%s</div><div class="c-rule"></div>' % E(issue["paper"]),
           '<div class="c-dl">%s &middot; %s</div>' % (L["no"] % issue["number"], E(i18n.long_date(date, lang)))]
    if breaking:
        out.append('<div class="c-band"><b>%s</b>%s</div>' % (L["breaking"], E(breaking[0]["title"])))
    if lead:
        pic = ('<img src="/issue/%s/%s" alt="" loading="lazy">' % (date, E(lead["image"])) if lead["image"]
               else '<span class="ph" style="display:block"></span>')
        side = "".join('<p class="c-hl">%s</p><i class="greek" style="--n:%d"></i>' % (E(st["title"]), 3 if j else 5)
                       for j, st in enumerate(rail[:3]))
        out.append('<div class="c-body"><div class="c-lead">%s<p class="c-hl">%s</p><i class="greek" style="--n:7"></i></div>'
                   '<div class="c-rail">%s</div></div>' % (pic, E(lead["title"]), side))
    foot = []
    for sec, rest in shown:
        if rest and _role(sec) not in ("front", "breaking") and len(foot) < 3:
            foot.append('<div><span class="k">%s</span><p class="c-hl">%s</p><i class="greek" style="--n:4"></i></div>'
                        % (E(names[sec["name"]]), E(rest[0]["title"])))
    if foot:
        out.append('<div class="c-foot">%s</div>' % "".join(foot))
    out.append("</div>")
    return "".join(out)


def reading_order(issue):
    return [st for sec in issue["sections"] for st in sec["stories"]]


def article_page(issue, st, zone):
    date, lang = issue["date"], issue.get("language") or "en"
    L = i18n.strings(lang)
    order = reading_order(issue)
    i = next(n for n, s in enumerate(order) if s["id"] == st["id"])
    prev = order[i - 1] if i > 0 else None
    nxt = order[i + 1] if i + 1 < len(order) else None

    out = ['<div class="art-top label"><a class="l" href="/issue/%s/"><span class="arw">&larr;</span> %s</a>'
           '<a class="mini" href="/issue/%s/">%s</a><span class="r">%s &middot; %s</span></div>'
           % (date, L["front_page"], date, E(issue["paper"]), L["no"] % issue["number"],
              E(i18n.long_date(date, lang)))]
    out.append('<article class="story rise">%s<h1 class="hl">%s</h1>' % (_kicker(st, names=section_names(issue)), E(st["title"])))
    if _deck_needed(st) and st["mode"] == "full":
        out.append('<p class="deck">%s</p>' % E(st["summary"]))
    bits = []
    if st["author"]:
        bits.append(L["by"] % ("<b>%s</b>" % E(st["author"])))
    if st["published"]:
        bits.append(clock(st["published"], zone, lang))
    bits.append(L["min_read"] % st["minutes"])
    out.append('<div class="byline label">%s</div></article>' % "".join("<span>%s</span>" % b for b in bits))
    if st["image"]:
        cap = '<figcaption>%s</figcaption>' % E(st["caption"]) if st.get("caption") else ""
        out.append('<figure class="story-fig rise d1"><img src="/issue/%s/%s" alt="">%s</figure>'
                   % (date, E(st["image"]), cap))
    out.append('<div class="story rise d2" style="padding-top:0"><div class="body">%s</div>'
               % (_src(st["html"], date) if st["html"] else "<p>%s</p>" % E(st["summary"])))
    if st["excerpt_only"]:
        out.append('<p class="note">%s</p>' % (L["excerpt"] % E(st["host"])))
    if st["link"]:
        out.append('<p class="source"><a class="btn" href="%s" rel="noopener noreferrer" target="_blank">%s &nearr;</a></p>'
                   % (E(st["link"]), L["read_at"] % E(st["host"] or L["the_source"])))
    out.append("</div>")
    out.append('<nav class="pager">')
    out.append('<a rel="prev" href="%s"><span class="label"><span class="arw">&larr;</span> %s</span><div class="hl">%s</div></a>'
               % (_url(issue, prev), L["previous"], E(prev["title"])) if prev else
               '<a rel="prev" href="/issue/%s/"><span class="label"><span class="arw">&larr;</span> %s</span><div class="hl">%s</div></a>'
               % (date, L["front_page"], E(issue["paper"])))
    out.append('<a rel="next" href="%s"><span class="label">%s <span class="arw">&rarr;</span></span><div class="hl">%s</div></a>'
               % (_url(issue, nxt), L["next"], E(nxt["title"])) if nxt else
               '<a rel="next" href="/issue/%s/"><span class="label">%s <span class="arw">&rarr;</span></span><div class="hl">%s</div></a>'
               % (date, L["back_front"], L["end_paper"]))
    out.append("</nav>")
    return doc("%s — %s" % (st["title"], issue["paper"]), "".join(out), st["summary"], lang)


def archive_page(editions, paper, lang="en"):
    """Every edition on file as a miniature front page. `editions` = [(row, issue)]."""
    L = i18n.strings(lang)
    out = [strip("", lang), '<header class="mast"><span></span><h1><a href="/">%s</a></h1><span></span></header>' % E(paper),
           '<div class="dateline label"><span>%s</span><span>%s</span></div>'
           % (L["editions"], L["on_file"] % len(editions))]
    if not editions:
        out.append('<div class="empty"><p>%s</p><p><a class="btn" href="/desk">%s</a></p></div>'
                   % (L["no_editions"], L["go_desk"]))
    else:
        out.append('<div class="editions">')
        for i, (row, issue) in enumerate(editions):
            il = issue.get("language") or lang
            out.append('<div class="ed rise">%s<a href="/issue/%s/" aria-label="%s, %s"><div class="sheet">%s</div>'
                       '<div class="ed-cap"><span class="hl">%s</span><span class="label">%s &middot; %s</span></div></a>'
                       '<a class="ed-epub label" href="/issue/%s/epub">EPUB &darr;</a></div>'
                       % ('<span class="ed-tag label">%s</span>' % L["latest"] if i == 0 else "", row["date"],
                          E(i18n.long_date(row["date"], il)), L["no"] % row["number"], cover(issue),
                          E(i18n.day_month(row["date"], il)), L["no"] % row["number"],
                          L["n_stories"] % row["stories"], row["date"]))
        out.append("</div>")
    return doc("%s — %s" % (paper, L["editions"]), "".join(out), "", lang)


def empty_page(paper, building=False, lang="en"):
    L = i18n.strings(lang)
    out = [strip(i18n.long_date(time.strftime("%Y-%m-%d"), lang), lang),
           '<header class="mast"><span></span><h1>%s</h1><span></span></header>' % E(paper),
           '<div class="dateline label"><span>%s</span></div>' % L["awaiting"],
           '<div class="empty"><p>%s</p><p><a class="btn" href="/desk">%s</a></p></div>'
           % (L["running"] if building else L["no_issue"], L["go_desk"])]
    return doc(paper, "".join(out), "", lang)


def not_found_page(lang="en"):
    L = i18n.strings(lang)
    return doc("404", strip("", lang) + '<div class="empty"><p>%s</p><p><a class="btn" href="/">%s</a></p></div>'
               % (L["not_found"], L["todays_paper"]), "", lang)
