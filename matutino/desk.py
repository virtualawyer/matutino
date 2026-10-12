"""The desk: add feeds, edit the list, change settings, print an edition.

One page, rendered in the browser from /api/state. Actions POST JSON and
then re-fetch the state rather than patching the page from responses.
"""

import html

from . import PROJECT_URL, i18n
from .render import CSS, HEAD_ICONS, MOON, THEME_JS, TOGGLE_JS

DESK_CSS = r"""
.desk{max-width:860px;margin:0 auto}
.desk .mast{grid-template-columns:1fr;padding:14px 0 10px}
.desk .mast h1{font-size:clamp(34px,6vw,60px)}
.desk .mast h1 small{display:block;font-family:var(--label);font-size:13px;letter-spacing:.3em;
  text-transform:uppercase;font-weight:600;color:var(--accent);margin-top:10px}
.box{padding:24px 0 26px;border-bottom:1px solid var(--rule)}
.box > h2{font-family:var(--label);font-size:14px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;
  margin:0 0 14px;display:flex;align-items:center;gap:14px}
.box > h2 .tools{margin-left:auto;display:flex;gap:16px}
.box > h2 .tools button{font-size:12px}
.press{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.press .status{flex:1;min-width:240px}
.press .big{font-family:var(--head);font-size:24px;font-weight:700;line-height:1.2}
.press .sub{color:var(--muted);margin-top:4px;font-size:15px}
.btn.primary{background:var(--ink);color:var(--paper)}
.btn.primary:hover{background:var(--accent);border-color:var(--accent)}
.btn[disabled]{opacity:.45;cursor:default;pointer-events:none}
.bar{height:3px;background:var(--hair);margin-top:12px;overflow:hidden}
.bar span{display:block;height:100%;width:0;background:var(--accent);transition:width .3s linear}
.link{background:none;border:0;padding:0;cursor:pointer;color:var(--muted);font:inherit}
.link:hover{color:var(--ink)} .link.danger:hover{color:var(--accent)}
.report{margin-top:16px;font-size:15px;line-height:1.55}
.report summary{cursor:pointer;color:var(--ink-2);list-style:none}
.report summary::-webkit-details-marker{display:none}
.report summary::before{content:"\25B8  "} .report[open] summary::before{content:"\25BE  "}
.report ul{list-style:none;padding:0;margin:10px 0 0;columns:2 280px;column-gap:28px}
.report li{break-inside:avoid;padding:2px 0}
.bad{color:var(--accent)}
textarea,input[type=text],input[type=number],input[type=time]{width:100%;background:transparent;color:var(--ink);
  border:0;border-bottom:1px solid var(--rule);font:inherit;padding:8px 2px;border-radius:0;outline:none}
textarea{font-family:var(--mono);font-size:14px;line-height:1.6;border:1px solid var(--rule);padding:12px 14px;
  min-height:140px;resize:vertical;background:var(--paper-2)}
textarea:focus,input:focus{border-color:var(--accent)}
.row{display:flex;gap:18px;align-items:flex-end;flex-wrap:wrap;margin-top:14px}
.field{flex:1;min-width:160px}
.field > span{display:block;color:var(--muted);margin-bottom:2px}
.check{display:flex;gap:9px;align-items:center;cursor:pointer;color:var(--ink-2);font-size:15px;padding-bottom:8px}
.check input{accent-color:var(--accent);width:16px;height:16px}
.hint{color:var(--muted);font-size:14px;margin:8px 0 0;font-style:italic}
.hint code{font-family:var(--mono);font-style:normal;font-size:12.5px}
.msg{margin-top:12px;font-size:15px;min-height:1px}
.group{margin-top:18px}
.group:first-child{margin-top:0}
.group h3{display:flex;align-items:center;gap:12px;margin:0 0 4px;font-family:var(--label);
  font-size:12.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent)}
.group h3::after{content:"";flex:1;border-top:1px solid var(--hair)}
.feed{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:6px 18px;align-items:center;
  padding:10px 0;border-bottom:1px dotted var(--hair)}
.feed .name{font-family:var(--head);font-weight:700;font-size:17.5px;line-height:1.25;overflow-wrap:anywhere}
.feed .url{font-family:var(--mono);font-size:12px;color:var(--muted);overflow-wrap:anywhere;margin-top:2px}
.feed .st{font-size:13.5px;color:var(--muted);margin-top:2px}
.seg{display:inline-flex;border:1px solid var(--rule)}
.seg button{background:none;border:0;color:var(--muted);cursor:pointer;padding:5px 9px;font-family:var(--label);
  font-size:11px;font-weight:600;letter-spacing:.12em;text-transform:uppercase}
.seg button.on{background:var(--ink);color:var(--paper)}
.x{background:none;border:0;color:var(--muted);cursor:pointer;font-size:20px;line-height:1;padding:4px 2px}
.x:hover{color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:6px 26px}
.issues a{display:flex;gap:14px;align-items:baseline;padding:8px 0;border-bottom:1px dotted var(--hair)}
.issues a:hover .t{color:var(--accent)}
.issues .n{font-family:var(--mast);font-weight:700;font-size:22px;min-width:38px}
.issues .t{font-family:var(--head);font-size:17px;flex:1}
.empty-list{color:var(--muted);font-style:italic}
select{background:transparent;color:var(--ink);border:0;border-bottom:1px solid var(--rule);font:inherit;padding:8px 2px;border-radius:0;width:100%}
select option{background:var(--paper);color:var(--ink)}
.feed select{width:auto;max-width:170px;font-family:var(--label);font-size:11.5px;font-weight:600;letter-spacing:.08em;
  text-transform:uppercase;padding:5px 2px;color:var(--muted)}
.secgrid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr);gap:24px}
.roles p{margin:0 0 10px;font-size:15px;color:var(--ink-2)}
.missing{margin:14px 0 0;font-size:14px;color:var(--muted);font-style:italic}
@media (max-width:700px){.secgrid{grid-template-columns:1fr}}
.feed{grid-template-columns:minmax(0,1fr) auto auto auto}
@media (max-width:560px){.feed{grid-template-columns:minmax(0,1fr) auto}.feed .seg,.feed select{grid-column:1/-1;justify-self:start}}
"""

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>The Desk</title>__ICONS__
<style>__CSS__</style>__THEME__</head><body><div class="page desk">
<div class="strip label"><span>Matutino __VERSION__ &middot; __SOURCE__</span><nav><a href="/">Today</a><a href="/archive">Editions</a>
<button class="theme" type="button" title="Night edition" aria-label="Toggle night edition">__MOON__</button></nav></div>
<header class="mast"><h1 id="paper">The Desk</h1></header>
<div class="dateline label"><span id="dl">&nbsp;</span></div>

<section class="box"><h2>The press</h2>
  <div class="press"><div class="status"><div class="big" id="big">&nbsp;</div><div class="sub" id="sub"></div></div>
  <button class="btn primary" id="print">Print now</button></div>
  <div class="bar" id="bar" hidden><span></span></div>
  <div id="report"></div>
</section>

<section class="box"><h2>Add feeds</h2>
  <textarea id="paste" spellcheck="false" placeholder="Paste one feed or many, one per line. A website address works too.

# World
https://feeds.bbci.co.uk/news/world/rss.xml
# Comics
xkcd | https://xkcd.com/rss.xml | headlines"></textarea>
  <div class="row">
    <label class="field"><span class="label">Section</span><select id="section"></select></label>
    <label class="check"><input type="checkbox" id="headlines"> Headlines only (no page fetch)</label>
    <button class="btn" id="add">Add</button>
  </div>
  <p class="hint">Lines starting with <code># Name</code> file the feeds below them in that section (<code># World</code>, <code># Comics</code> and <code># Sports</code> find their sections). Add <code>headlines</code> after an address to print only what the feed carries, which suits comics and link lists. Longer <code>#</code> lines are comments, and a <code>#</code> in front of a feed switches it off.</p>
  <div class="msg" id="addmsg"></div>
</section>

<section class="box"><h2>Feeds <span class="tools"><button class="link label" id="astext">Edit as text</button></span></h2>
  <div id="feeds"></div>
  <div id="textedit" hidden>
    <textarea id="alltext" spellcheck="false" style="min-height:280px"></textarea>
    <div class="row"><button class="btn primary" id="savetext">Save list</button><button class="link label" id="canceltext">Cancel</button></div>
    <p class="hint">Reorder, rename, regroup or delete lines, then save. New addresses are checked before they are added.</p>
  </div>
  <div class="msg" id="textmsg"></div>
</section>

<section class="box"><h2>Sections</h2>
  <div class="secgrid">
    <textarea id="secs" spellcheck="false" style="min-height:300px" aria-label="Sections, one per line, in printing order"></textarea>
    <div class="roles">
      <p><b>Front Page</b> feeds supply the lead story and the right-hand column. With none, the top story of each news section is used.</p>
      <p><b>Breaking News</b> prints as a red band under the masthead.</p>
      <p><b>Local Weather</b> carries the forecast; <b>Variety News</b> carries <i>On this day</i>. Both print even without feeds.</p>
      <p><b>Funnies</b> and <b>Opinion</b> never lead the paper.</p>
      <p class="hint">One section per line, in printing order. Those jobs follow the names, so &ldquo;Comics&rdquo; works like Funnies, and so do Spanish names such as Portada, Clima or Tiras c&oacute;micas.</p>
      <p class="hint">To print a section under another name, add it after an equals sign: <code>World News = Mundo</code>. Its feeds and its job stay the same. On a Spanish paper (language <code>es</code>) the usual sections already print in Spanish.</p>
    </div>
  </div>
  <div class="row"><button class="btn" id="savesecs">Save sections</button><span class="msg" id="secmsg" style="margin:0"></span></div>
</section>

<section class="box"><h2>Settings</h2>
  <div class="grid">
    <label class="field"><span class="label">Paper name</span><input type="text" id="s_paper_name"></label>
    <label class="field"><span class="label">Edition line</span><input type="text" id="s_edition"></label>
    <label class="field"><span class="label">Print at</span><input type="time" id="s_build_time"></label>
    <label class="field"><span class="label">Time zone</span><input type="text" id="s_timezone" list="zones"></label>
    <label class="field"><span class="label">Stories per feed</span><input type="number" min="1" max="30" id="s_per_feed"></label>
    <label class="field"><span class="label">Look back (hours)</span><input type="number" min="6" max="336" id="s_lookback_hours"></label>
    <label class="field"><span class="label">Keep issues (days)</span><input type="number" min="1" max="365" id="s_keep_days"></label>
    <label class="field"><span class="label">Language</span><select id="s_language">__LANGS__</select></label>
  </div>
  <div class="grid" style="margin-top:14px">
    <label class="field" style="grid-column:1/-1"><span class="label">Weather for</span><input type="text" id="s_weather_place" placeholder="Town, Country (e.g. Lisbon, Portugal)"></label>
  </div>
  <div class="row"><label class="check"><input type="checkbox" id="s_weather_on"> Weather box</label>
    <label class="check"><input type="checkbox" id="s_onthisday_on"> On this day</label>
    <label class="check" title="Some news sites refuse feed readers. With this on, Matutino presents itself as a desktop browser to every site it reads."><input type="checkbox" id="s_browser_ua"> Identify as a web browser</label></div>
  <div class="row"><label class="check"><input type="checkbox" id="s_schedule_on"> Print automatically every day</label>
    <span style="flex:1"></span><button class="btn" id="saveset">Save settings</button></div>
  <p class="hint" id="kavita"></p>
  <p class="hint" id="opds"></p>
  <div class="msg" id="setmsg"></div>
  <datalist id="zones"><option>UTC</option><option>Europe/London</option><option>Europe/Madrid</option>
  <option>America/New_York</option><option>America/Chicago</option><option>America/Los_Angeles</option>
  <option>America/Mexico_City</option><option>America/Bogota</option><option>America/Buenos_Aires</option>
  <option>America/Costa_Rica</option><option>America/Puerto_Rico</option></datalist>
  <p class="hint">Language sets the paper's own words (dates, labels, weather, section names) and On this day. Stories print in their feeds' language. To add a language, drop a pack into <code>languages/</code> in the data folder (see the README).</p>
</section>

<section class="box" style="border-bottom:0"><h2>Recent editions <span class="tools"><a class="link label" href="/archive">All editions &rarr;</a></span></h2><div class="issues" id="issues"></div></section>
</div>
__TOGGLE__
<script>
var S=null, editing=false, timer=null;
function $(id){return document.getElementById(id)}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
$('opds').innerHTML='Reading apps (Librera, Readest, KOReader) can subscribe to the paper: add <code>'+esc(location.origin+'/opds')+
  '</code> as an OPDS catalog and every new issue appears there as an EPUB.';
function post(url,body){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})
  .then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.error||('HTTP '+r.status));return j})})}
function ago(ts){if(!ts)return'';var s=Math.max(0,S.now-ts);if(s<90)return'just now';if(s<5400)return Math.round(s/60)+' min ago';
  if(s<129600)return Math.round(s/3600)+' h ago';return Math.round(s/86400)+' days ago'}
function load(){fetch('/api/state').then(function(r){return r.json()}).then(function(j){S=j;render();schedule()}).catch(function(){schedule()})}
function schedule(){clearTimeout(timer);timer=setTimeout(load,S&&S.building?1200:20000)}
function render(){
  $('paper').innerHTML=esc(S.settings.paper_name)+'<small>The Desk</small>';
  document.title=S.settings.paper_name+' — The Desk';
  $('dl').textContent=S.today_long+(S.issues.length?' · '+S.issues.length+(S.issues.length===1?' issue':' issues')+' on file':'');
  var p=S.progress, r=S.last_report;
  $('print').disabled=S.building||!S.feeds.length;
  $('print').textContent=S.building?'Printing…':'Print now';
  if(S.building){
    $('big').textContent=p.phase||'Printing';
    $('sub').textContent=[p.total?p.done+' of '+p.total:'',p.detail||''].filter(Boolean).join(' · ');
    $('bar').hidden=false; $('bar').firstChild.style.width=(p.total?Math.round(100*p.done/p.total):4)+'%';
  } else {
    $('bar').hidden=true;
    if(!S.feeds.length){$('big').textContent='No feeds yet';$('sub').textContent='Paste some below, then print the first edition.'}
    else if(r&&!r.ok){$('big').innerHTML='<span class="bad">The last run failed</span>';$('sub').textContent=r.error||''}
    else if(r){$('big').textContent=r.message||'';$('sub').textContent='Finished '+ago(r.finished)+(S.next_build?' · next edition '+S.next_build:'')}
    else{$('big').textContent='Ready to print';$('sub').textContent=S.next_build?'Next edition '+S.next_build:'Automatic printing is off'}
  }
  var rep='';
  if(r&&r.ok&&r.sections&&!S.building){
    var items=[];r.sections.forEach(function(sec){sec.feeds.forEach(function(f){
      items.push('<li>'+(f.error?'<span class="bad">FAILED</span> ':'')+esc(sec.name)+' / <b>'+esc(f.name)+'</b>: '+(f.error?'<span class="bad">'+esc(f.error)+'</span>':f.new+' new')+'</li>')})});
    var k=r.kavita||{}, kl=k.path?'<li>EPUB filed in Kavita: <code>'+esc(k.path)+'</code></li>':k.error?'<li class="bad">EPUB not filed: '+esc(k.error)+'</li>':'';
    var ex=r.excerpts?'<li>'+r.excerpts+' stories printed as feed excerpts (page could not be read)</li>':'';
    rep='<details class="report"'+(r.failed||k.error?' open':'')+'><summary>Report'+(r.failed?' · <span class="bad">'+r.failed+' feed'+(r.failed>1?'s':'')+' failed</span>':'')+
      (r.number?' · <a href="/issue/'+r.date+'/">Read No. '+r.number+' &rarr;</a>':'')+'</summary><ul>'+items.join('')+ex+kl+'</ul></details>';
  }
  $('report').innerHTML=rep;
  var list=S.settings.sections.slice(), secs=[];
  S.feeds.forEach(function(f){if(list.indexOf(f.section)<0&&secs.indexOf(f.section)<0)secs.push(f.section)});
  var all=list.concat(secs); secs=all.filter(function(n){return S.feeds.some(function(f){return f.section===n})});
  var opts=function(sel){return all.map(function(n){return '<option'+(n===sel?' selected':'')+'>'+esc(n)+'</option>'}).join('')};
  var cur=$('section').value||(list.indexOf('Local News')>=0?'Local News':list[0]);
  if(document.activeElement!==$('section'))$('section').innerHTML=opts(cur);
  var labels=S.settings.section_labels||{};
  if(document.activeElement!==$('secs'))$('secs').value=list.map(function(n){return labels[n]?n+' = '+labels[n]:n}).join('\\n');
  if(!editing){
    if(!S.feeds.length){$('feeds').innerHTML='<p class="empty-list">No feeds on the list.</p>'}
    else $('feeds').innerHTML=secs.map(function(sec){return '<div class="group"><h3>'+esc(sec)+'</h3>'+
      S.feeds.filter(function(f){return f.section===sec}).map(function(f){
        var st=f.last_status==='failed'?'<span class="bad">Failed: '+esc(f.last_error)+'</span>':
          f.last_status==='ok'?f.last_count+' in the last issue · checked '+ago(f.last_checked):'Not printed yet';
        return '<div class="feed"><div><div class="name">'+esc(f.name||f.url)+'</div><div class="url">'+esc(f.url)+'</div><div class="st">'+st+'</div></div>'+
          '<select data-sec="'+f.id+'" aria-label="Section for '+esc(f.name||f.url)+'">'+opts(f.section)+'</select>'+
          '<div class="seg" role="group" aria-label="Story depth"><button data-mode="full" data-id="'+f.id+'" class="'+(f.mode==='full'?'on':'')+'">Full text</button>'+
          '<button data-mode="feed" data-id="'+f.id+'" class="'+(f.mode==='feed'?'on':'')+'">Headlines</button></div>'+
          '<button class="x" title="Remove" aria-label="Remove '+esc(f.name||f.url)+'" data-del="'+f.id+'">&times;</button></div>'}).join('')+'</div>'}).join('');
    var empty=list.filter(function(n){var r=S.roles[n];return secs.indexOf(n)<0&&r!=='weather'&&r!=='variety'});
    if(empty.length)$('feeds').innerHTML+='<p class="missing">No feeds yet in: '+empty.map(esc).join(', ')+'.</p>';
  }
  if(!document.activeElement||!/^s_/.test(document.activeElement.id||'')){
    Object.keys(S.settings).forEach(function(k){var el=$('s_'+k);if(!el)return;if(el.type==='checkbox')el.checked=!!S.settings[k];else{
      if(el.tagName==='SELECT'&&![].some.call(el.options,function(o){return o.value===String(S.settings[k])})){
        var o=document.createElement('option');o.value=o.textContent=S.settings[k];el.appendChild(o)}
      el.value=S.settings[k]}})}
  $('kavita').innerHTML=S.epub_dir?(S.epub_ok?'EPUBs are filed in <code>'+esc(S.epub_dir+(S.kavita_folder?'/'+S.kavita_folder:''))+'</code> for Kavita'+
    (S.kavita_folder?' (this folder stays put if you rename the paper)':'')+'.':
    '<span class="bad">The Kavita folder <code>'+esc(S.epub_dir)+'</code> is not reachable; EPUBs stay on this server only.</span>'):
    'No Kavita folder is set, so each EPUB is only offered for download from its issue.';
  var gb=function(mb){return (mb/1024).toFixed(1)+' GB'};
  $('kavita').innerHTML+='<br>'+(S.disk_free_mb<1024?'<span class="bad">':'')+'Issue library <code>'+esc(S.library)+'</code>: '+gb(S.disk_free_mb)+' free'+
    (S.disk_free_mb<1024?' \u2014 below 300 MB the paper prints without pictures.</span>':'')+
    (S.kavita_free_mb!=null?' \u00b7 Kavita drive: '+gb(S.kavita_free_mb)+' free':'')+
    (S.shrinker?'':' \u00b7 <span class="bad">pictures are stored full size (Pillow missing)</span>');
  $('issues').innerHTML=S.issues.length?S.issues.slice(0,10).map(function(i){return '<a href="/issue/'+i.date+'/"><span class="n">'+i.number+'</span><span class="t">'+esc(i.long)+'</span><span class="label meta">'+i.stories+' stories</span></a>'}).join(''):'<p class="empty-list">Nothing printed yet.</p>';
}
$('feeds').addEventListener('change',function(e){var t=e.target;if(t.dataset&&t.dataset.sec)post('/api/feeds/'+t.dataset.sec,{section:t.value}).then(load)});
$('savesecs').addEventListener('click',function(){post('/api/settings',{sections:$('secs').value}).then(function(){
  $('secmsg').textContent='Saved.';setTimeout(function(){$('secmsg').textContent=''},2500);$('secs').blur();load()})
  .catch(function(e){$('secmsg').innerHTML='<span class="bad">'+esc(e.message)+'</span>'})});
$('feeds').addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;
  if(b.dataset.mode){post('/api/feeds/'+b.dataset.id,{mode:b.dataset.mode}).then(load)}
  else if(b.dataset.del){var f=S.feeds.filter(function(x){return x.id==b.dataset.del})[0];
    if(confirm('Remove '+(f.name||f.url)+' from the paper?'))post('/api/feeds/'+b.dataset.del+'/delete').then(load)}});
$('add').addEventListener('click',function(){var t=$('paste').value.trim();if(!t)return;
  $('add').disabled=true;$('addmsg').textContent='Checking feeds…';
  post('/api/feeds',{text:t,section:$('section').value.trim(),mode:$('headlines').checked?'feed':'full'}).then(function(j){
    var m=[];if(j.added.length)m.push('Added '+j.added.map(esc).join(', ')+'.');
    if(j.existing.length)m.push(j.existing.length+' already on the list.');
    j.failed.forEach(function(f){m.push('<span class="bad">'+esc(f.url)+': '+esc(f.error)+'</span>')});
    if(!j.added.length&&!j.existing.length&&!j.failed.length)m.push('No addresses found in that text.');
    $('addmsg').innerHTML=m.join('<br>');if(!j.failed.length)$('paste').value='';load()
  }).catch(function(e){$('addmsg').innerHTML='<span class="bad">'+esc(e.message)+'</span>'}).then(function(){$('add').disabled=false})});
$('astext').addEventListener('click',function(){editing=true;$('alltext').value=S.feeds_text;$('feeds').hidden=true;$('textedit').hidden=false;$('alltext').focus()});
$('canceltext').addEventListener('click',function(){editing=false;$('feeds').hidden=false;$('textedit').hidden=true;$('textmsg').textContent='';render()});
$('savetext').addEventListener('click',function(){$('savetext').disabled=true;$('textmsg').textContent='Checking new addresses…';
  post('/api/feeds/text',{text:$('alltext').value}).then(function(j){
    var m=['Saved: '+j.total+' feeds'+(j.added?', '+j.added+' new':'')+(j.removed?', '+j.removed+' removed':'')+'.'];
    j.failed.forEach(function(f){m.push('<span class="bad">Not added, '+esc(f.url)+': '+esc(f.error)+'</span>')});
    $('textmsg').innerHTML=m.join('<br>');editing=false;$('feeds').hidden=false;$('textedit').hidden=true;load()
  }).catch(function(e){$('textmsg').innerHTML='<span class="bad">'+esc(e.message)+'</span>'}).then(function(){$('savetext').disabled=false})});
$('print').addEventListener('click',function(){post('/api/build').then(load)});
$('saveset').addEventListener('click',function(){var v={};Object.keys(S.settings).forEach(function(k){var el=$('s_'+k);if(!el)return;
  v[k]=el.type==='checkbox'?el.checked:el.type==='number'?Number(el.value):el.value.trim()});
  post('/api/settings',v).then(function(j){$('setmsg').textContent='Saved.'+(j.settings&&j.settings.weather_on?' Weather for '+j.settings.weather_place+'.':'');
    setTimeout(function(){$('setmsg').textContent=''},4000);document.activeElement.blur();load()})
  .catch(function(e){$('setmsg').innerHTML='<span class="bad">'+esc(e.message)+'</span>'})});
load();
</script></body></html>"""


def page(version):
    source = ('<a href="%s" rel="noopener noreferrer">free software (AGPL) &middot; source</a>' % PROJECT_URL
              if PROJECT_URL else "free software (AGPL)")
    return (PAGE.replace("__CSS__", CSS + DESK_CSS).replace("__THEME__", THEME_JS).replace("__ICONS__", HEAD_ICONS)
            .replace("__TOGGLE__", TOGGLE_JS).replace("__MOON__", MOON).replace("__VERSION__", version)
            .replace("__SOURCE__", source).replace("__LANGS__", "".join(
                '<option value="%s">%s (%s)</option>' % (html.escape(c), html.escape(n), html.escape(c))
                for c, n in i18n.languages())))
