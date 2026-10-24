"""Portable interactive audit report. No network, dependencies, or web server."""

import json
from pathlib import Path


def render_report(path, results, summary):
    payload = json.dumps({"results": results, "summary": summary}, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = '''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GhostTrace · Deletion audit</title>
<style>
:root{color-scheme:dark;--bg:#0c111b;--panel:#141d2b;--line:#29374c;--text:#e8eef7;--muted:#a6b6ca;--cyan:#5eead4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,sans-serif}
header,main{max-width:1360px;margin:auto;padding:28px}header{border-bottom:1px solid var(--line)}
.brand{font-size:25px;font-weight:750;letter-spacing:-1px}.brand span{color:var(--cyan)}.eyebrow{color:var(--cyan);font:12px monospace;letter-spacing:2px}
h1{font-size:36px;letter-spacing:-1.5px;margin:16px 0 6px}p{color:var(--muted);margin:6px 0 16px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:22px 0}
.card,article,aside{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px}.number{font-size:32px;font-weight:700}
.label{font-size:12px;color:var(--muted);letter-spacing:1px}input,select,button{font:inherit;padding:10px 14px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--text)}input{flex:1;min-width:120px}button{cursor:pointer}button:hover{border-color:var(--cyan)}
.tools{display:flex;gap:12px;margin:18px 0}.layout{display:grid;grid-template-columns:340px 1fr;gap:18px}aside{padding:8px;max-height:720px;overflow:auto}.case{display:block;width:100%;border:0;text-align:left;margin:3px 0;padding:12px}.case.active{background:#21394a;outline:1px solid var(--cyan)}
.badge{display:inline-block;font:11px/1.5 monospace;letter-spacing:.5px;border-radius:5px;padding:4px 7px;background:#29374c}.COMPLETE{color:#67e8b3}.INCOMPLETE{color:#ff9d9d}.REVIEW_REQUIRED{color:#fcd47e}.NOT_APPLICABLE{color:#a5b4fc}
h2{font-size:22px;margin:0 0 10px}h3{font-size:15px;margin:24px 0 10px;color:var(--cyan)}ul,ol{padding-left:22px}li{margin:8px 0}.ref{font:12px monospace;color:var(--muted)}.row{border-bottom:1px solid var(--line);padding:10px 0}.small{font-size:12px}.empty{padding:14px;background:#101825;border-radius:8px;color:var(--muted)}.notice{border-left:3px solid #fcd47e;padding:12px 16px;background:#25241e;border-radius:6px;color:#ffe3a3}
@media(max-width:800px){.layout{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,1fr)}aside{max-height:250px}header,main{padding:18px}h1{font-size:28px}.tools{flex-wrap:wrap}}
</style>
<header><div class="brand">◈ Ghost<span>Trace</span></div><h1>Deletion claims. Verified.</h1><p>An evidence trail from request to resolution.</p></header>
<main><div class="eyebrow">AUDIT WORKSPACE</div><div id="notice" class="notice"></div><div id="cards" class="cards"></div>
<div class="tools"><input id="search" aria-label="Search case ID" placeholder="Search a case ID…"><select id="filter" aria-label="Filter status"><option value="">All verdicts</option><option>INCOMPLETE</option><option>COMPLETE</option><option>NOT_APPLICABLE</option><option>REVIEW_REQUIRED</option></select><button id="download">Download audit JSON</button></div>
<p class="small" id="count"></p><div class="layout"><aside id="cases" aria-label="Cases"></aside><article id="detail" aria-live="polite"></article></div>
<p class="small">GhostTrace · Internal audit format. REVIEW_REQUIRED is an abstention, not an official competition label. Reported dashboard status is never proof.</p></main>
<script id="data" type="application/json">__PAYLOAD__</script>
<script>
const data=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id);
let selected=data.results[0]?.case_id;
function el(tag,text,cls){const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x}
function section(title,items,format){$('detail').append(el('h3',title));if(!items.length){$('detail').append(el('div','No items recorded.','empty'));return}const list=el('ul');for(const item of items){const li=el('li');li.append(el('div',format(item)));if(item.source)li.append(el('div',item.source+(item.policy?' · '+item.policy:''),'ref'));list.append(li)}$('detail').append(list)}
function detail(r){$('detail').replaceChildren();if(!r){$('detail').append(el('p','No matching requests.'));return}$('detail').append(el('h2',r.case_id),el('span',r.status,'badge '+r.status),el('p','Reported status: '+r.reported_status+' · Intent: '+r.intent));
section('Evidence gaps',r.gaps,x=>x);section('Resolved identifiers',r.identifiers,x=>x.type+': '+x.value);section('Remaining exposures / policy failures',r.findings,x=>x.description+(x.record_id?' '+x.system+'/'+x.record_id:''));section('Recreation paths',r.recreation_paths,x=>x.process_id+': '+x.from+' → '+x.to);section('Ordered remediation',r.remediation,x=>x.step+'. '+x.action);section('Required retained records',r.retained_records,x=>x);section('Proof checks',r.proof,x=>x.description);section('Observed timeline',r.timeline,x=>x.at+' · '+x.description);if(r.ai_review){section('AI review · advisory only',r.ai_review.checks,x=>x.observation)}}
function draw(){const q=$('search').value.toLowerCase(),s=$('filter').value,rows=data.results.filter(r=>r.case_id.toLowerCase().includes(q)&&(!s||r.status===s));if(!rows.some(r=>r.case_id===selected))selected=rows[0]?.case_id;$('cases').replaceChildren();for(const r of rows){const b=el('button',undefined,'case'+(r.case_id===selected?' active':''));b.append(el('div',r.case_id),el('span',r.status,'badge '+r.status));b.onclick=()=>{selected=r.case_id;draw()};$('cases').append(b)}$('count').textContent=rows.length+' of '+data.results.length+' requests';detail(rows.find(r=>r.case_id===selected))}
for(const status of ['COMPLETE','INCOMPLETE','NOT_APPLICABLE','REVIEW_REQUIRED']){const c=el('div',undefined,'card');c.append(el('div',String(data.summary.counts[status]||0),'number '+status),el('div',status.replaceAll('_',' '),'label'));$('cards').append(c)}
$('notice').textContent=data.summary.demo?'SYNTHETIC DEMO — these findings are generated from example evidence, not the organizer dataset.':'Evidence-backed results. Missing policy or system evidence causes review abstention. This report uses a provisional internal schema.';
$('search').oninput=draw;$('filter').onchange=draw;$('download').onclick=()=>{const a=el('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.download='audit.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};draw();
</script></html>'''
    Path(path).write_text(template.replace("__PAYLOAD__", payload), encoding="utf-8")
