"""Decision dashboard: self-contained HTML (big-screen + printable) and CLI text.

build_html(state, live) returns a single standalone .html file: a dark "decision
big-screen" on screen and a clean light printable report via @media print. When
live=True it ships a small script that re-reads /api/state and can trigger runs
through /api/run (used by the server). print_summary(state) is the text/Markdown
fallback for the CLI.
"""

from __future__ import annotations

import json

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>福彩3D 决策大屏</title>
<style>
:root{
  --bg:#0f141b; --panel:#182030; --card:#1e2838; --text:#e6edf3; --muted:#93a1b1;
  --accent:#4ea1ff; --ok:#3fb950; --warn:#d29922; --bad:#f85149; --border:#2a3343;
  --l0:#8b98a8; --l1:#4ea1ff; --l2:#f85149;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.5}
header{padding:18px 24px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
header h1{font-size:20px;margin:0;font-weight:600}
header .meta{color:var(--muted);font-size:12px}
.kpis{display:flex;gap:12px;flex-wrap:wrap;padding:16px 24px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 16px;min-width:150px}
.kpi .label{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.kpi .value{font-size:18px;font-weight:600;margin-top:4px}
nav.tabs{display:flex;gap:4px;padding:0 24px;border-bottom:1px solid var(--border);flex-wrap:wrap}
nav.tabs button{background:transparent;color:var(--muted);border:none;border-bottom:2px solid transparent;padding:10px 14px;cursor:pointer;font-size:14px}
nav.tabs button.active{color:var(--text);border-bottom-color:var(--accent)}
main{padding:20px 24px}
.panel{display:none}
.panel.active{display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px}
.card h3{margin:0 0 6px;font-size:15px}
.card .desc{color:var(--muted);font-size:12px;min-height:34px}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600}
.badge.L0{background:rgba(139,152,168,.18);color:var(--l0)}
.badge.L1{background:rgba(78,161,255,.18);color:var(--l1)}
.badge.L2{background:rgba(248,81,73,.18);color:var(--l2)}
.cat{color:var(--muted);font-size:11px}
button.run{margin-top:10px;background:var(--accent);color:#06121f;border:none;border-radius:8px;padding:6px 12px;cursor:pointer;font-weight:600}
button.run:disabled{opacity:.4;cursor:not-allowed}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--border);font-size:13px}
th{color:var(--muted);font-weight:600;background:rgba(255,255,255,.02)}
.summary{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;color:var(--muted);white-space:pre-wrap}
.acc{background:var(--card);border:1px solid var(--border);border-radius:10px;margin-bottom:8px}
.acc summary{padding:10px 14px;cursor:pointer;font-weight:600}
.acc .body{padding:0 14px 12px;color:var(--muted);font-size:12px;font-family:ui-monospace,monospace;white-space:pre-wrap}
.console{position:fixed;inset:auto 24px 24px 24px;max-height:50vh;overflow:auto;background:#0b0f15;border:1px solid var(--border);border-radius:10px;padding:12px;font-family:ui-monospace,monospace;font-size:12px;display:none;z-index:50}
.console.show{display:block}
.console .close{float:right;cursor:pointer;color:var(--muted)}
.timeline{list-style:none;padding:0;margin:0}
.timeline li{padding:8px 0;border-bottom:1px solid var(--border);font-size:13px}
.timeline .type{display:inline-block;width:74px;color:var(--muted);font-size:11px}
.note{color:var(--muted);font-size:12px;margin:6px 0 14px}
.params{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.params .p{display:flex;flex-direction:column;font-size:11px;color:var(--muted)}
.params .p input{margin-top:3px;width:112px;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:4px 6px;font-size:13px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.scrolltable{max-height:340px;overflow:auto;border:1px solid var(--border);border-radius:10px;margin-bottom:6px}
.scrolltable table{font-size:12px}
.freqgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.freq{width:100%;border-collapse:collapse}
.freq td,.freq th{padding:3px 6px;border-bottom:1px solid var(--border);font-size:12px;text-align:left}
.omit-hot{color:var(--ok);font-weight:600}
.omit-cold{color:var(--bad);font-weight:600}
.catgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.barline{display:flex;align-items:center;gap:6px;font-size:12px;margin:3px 0}
.blabel{width:54px;color:var(--muted);flex:none}
.btrack{flex:1;background:rgba(255,255,255,.04);border-radius:4px;height:12px;overflow:hidden}
.bfill{display:block;height:100%;background:var(--accent);border-radius:4px}
.bval{width:30px;text-align:right;color:var(--muted);flex:none}
.hcgrid{display:flex;flex-wrap:wrap;gap:6px}
.hc{display:inline-block;padding:4px 10px;border-radius:8px;font-family:ui-monospace,monospace;font-size:13px;border:1px solid var(--border)}
.hc.hot{background:rgba(248,81,73,.18);color:#f85149;border-color:rgba(248,81,73,.4)}
.hc.cold{background:rgba(78,161,255,.18);color:#4ea1ff;border-color:rgba(78,161,255,.4)}
.hc.neutral{color:var(--muted)}
.badge.type{padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600}
.badge.type.bz{background:rgba(210,153,34,.2);color:#d29922}
.badge.type.z3{background:rgba(63,185,80,.18);color:#3fb950}
.badge.type.z6{background:rgba(139,152,168,.18);color:#93a1b1}
.chart{width:100%;height:auto;display:block;background:var(--card);border:1px solid var(--border);border-radius:10px;margin-bottom:6px}
.chart text{font-family:ui-monospace,monospace}
.hit-ok{color:var(--ok);font-weight:600}
.hit-no{color:var(--muted)}
.hcell small{color:var(--muted);font-weight:400}
.arena-banner{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin-bottom:14px}
.arena-banner .ab{background:var(--card);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:10px;padding:12px 14px}
.arena-banner .ab .l{color:var(--muted);font-size:11px}
.arena-banner .ab .v{font-size:17px;font-weight:600;margin-top:4px}
.arena-banner .ab.ok .v{color:var(--ok)}
.arena-banner .ab.bad .v{color:var(--bad)}
.arena-banner .ab.warn .v{color:var(--warn)}
.verdict-pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600}
.verdict-pill.nd{background:rgba(139,152,168,.18);color:var(--l0)}
.verdict-pill.better{background:rgba(63,185,80,.18);color:var(--ok)}
.verdict-pill.worse{background:rgba(248,81,73,.18);color:var(--bad)}
.debate-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-top:8px}
.dcard{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:10px 12px}
.dcard .dhead{display:flex;justify-content:space-between;align-items:center;gap:8px}
.dcard .dname{font-weight:600;font-size:13px}
.dcard .dbelief{color:var(--muted);font-size:11px;margin:6px 0}
.dcard .dmetrics{font-size:11px;line-height:1.5}
.dcard .dreason{font-size:11px;color:var(--bad);margin-top:6px;line-height:1.5}
.ledger-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:8px}
.ledger-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 14px;border-left:3px solid var(--accent)}
.ledger-card .ll{color:var(--muted);font-size:11px}
.ledger-card .lv{font-size:18px;font-weight:600;margin-top:4px}
.ledger-card.pro .lv{color:var(--warn)}
.ledger-card.con .lv{color:var(--ok)}
.ledger-card .medal{display:inline-block;margin-top:6px;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600;background:rgba(210,153,34,.2);color:#d29922}
.evo-table{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden;margin-top:8px}
.evo-table th,.evo-table td{padding:7px 9px;border-bottom:1px solid var(--border);font-size:12px;text-align:left}
.evo-table th{color:var(--muted);font-weight:600;background:rgba(255,255,255,.02)}
.tag{display:inline-block;padding:1px 7px;border-radius:999px;font-size:10px;font-weight:600}
.tag.mutate{background:rgba(78,161,255,.18);color:#4ea1ff}
.tag.random{background:rgba(139,152,168,.18);color:#93a1b1}
.tag.comprehensive{background:rgba(210,153,34,.2);color:#d29922}
.tag.base{background:rgba(63,185,80,.15);color:#3fb950}
.badge.L3{background:rgba(248,81,73,.25);color:#f85149}
.badge.iv{font-size:11px;font-weight:600}
.badge.iv.accept{background:rgba(63,185,80,.18);color:#3fb950}
.badge.iv.quarantine{background:rgba(210,153,34,.2);color:#d29922}
.badge.iv.reject{background:rgba(248,81,73,.18);color:#f85149}
.ivgrid{display:flex;gap:18px;flex-wrap:wrap;margin-top:8px}
.ivgrid .p{display:flex;flex-direction:column;font-size:12px;color:var(--muted)}
.ivgrid .p b{color:var(--text);font-size:15px}
@media print{
  .params{display:none!important}
  .scrolltable{max-height:none!important;overflow:visible!important}
  :root{--bg:#fff;--panel:#fff;--card:#fff;--text:#111;--muted:#444;--border:#ccc}
  body{background:#fff;color:#111}
  nav.tabs,.console,button.run{display:none!important}
  .panel{display:block!important;page-break-inside:avoid}
  .kpi,.card,.acc,table{break-inside:avoid}
  header{border-color:#ccc}
}
</style>
</head>
<body>
<header>
  <h1>福彩3D 决策大屏</h1>
  <div class="meta" id="meta"></div>
</header>
<div class="kpis" id="kpis"></div>
<nav class="tabs" id="tabs"></nav>
<main id="content"></main>
<div class="console" id="console"><span class="close" onclick="closeConsole()">✕ 关闭</span><pre id="consolebody"></pre></div>

<script>
const STATE = STATE_JSON_PLACEHOLDER;
const LIVE = LIVE_FLAG_PLACEHOLDER;

function el(html){const d=document.createElement('div');d.innerHTML=html;return d.firstElementChild;}
function riskBadge(r){return `<span class="badge ${r}">${r}</span>`;}

function renderMeta(){
  const p=STATE.project||{};
  const parts=[];
  if(p.draws!=null)parts.push(`样本 ${p.draws} 期`);
  if(p.period_min)parts.push(`期号 ${p.period_min}–${p.period_max}`);
  if(p.last_draw_date)parts.push(`最新 ${p.last_draw_date}`);
  document.getElementById('meta').textContent=`生成 ${STATE.generated_at} · ${parts.join(' · ')}`;
}
function renderKpis(){
  const k=STATE.kpis||{};const items=[
    ['综合研判',k.verdict],['模型闸门',k.gate_decision],['漂移动作',k.drift_action],
    ['泄漏扫描',k.leakage_status],['样本数',STATE.project?.draws],
  ];
  const box=document.getElementById('kpis');
  box.innerHTML=items.map(([l,v])=>`<div class="kpi"><div class="label">${l}</div><div class="value">${v??'—'}</div></div>`).join('');
}
function renderTabs(){
  const tabs=[['overview','总览'],['functions','功能'],['backtest','回测'],['multi_method','多方法对比'],['history','历史分析'],['arena','模型竞技场'],['debate','双阵营辩论擂台'],['evolution','进化擂台'],['interventions','干预治理'],['external','外部耦合'],['near_miss','近失集成'],['decisions','决策审计'],['timeline','回溯时间轴'],['reports','报告']];
  document.getElementById('tabs').innerHTML=tabs.map(([id,t],i)=>`<button data-tab="${id}" class="${i===0?'active':''}">${t}</button>`).join('');
  document.querySelectorAll('nav.tabs button').forEach(b=>b.onclick=()=>{
    document.querySelectorAll('nav.tabs button').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
    showPanel(b.dataset.tab);
  });
}
function showPanel(id){
  const c=document.getElementById('content');
  if(id==='overview')c.innerHTML=overviewHtml();
  else if(id==='functions')c.innerHTML=functionsHtml();
  else if(id==='backtest')c.innerHTML=backtestHtml();
  else if(id==='multi_method')c.innerHTML=multiMethodHtml();
  else if(id==='history')c.innerHTML=historyHtml();
  else if(id==='arena')c.innerHTML=arenaHtml();
  else if(id==='debate')c.innerHTML=debateHtml();
  else if(id==='evolution')c.innerHTML=evolutionHtml();
  else if(id==='interventions')c.innerHTML=interventionsHtml();
  else if(id==='external')c.innerHTML=externalCouplingHtml();
  else if(id==='near_miss')c.innerHTML=nearMissEnsembleHtml();
  else if(id==='decisions')c.innerHTML=decisionsHtml();
  else if(id==='timeline')c.innerHTML=timelineHtml();
  else if(id==='reports')c.innerHTML=reportsHtml();
}
function overviewHtml(){
  const fb=STATE.backtest;
  let extra='';
  if(fb&&fb.frequency_baseline){
    const f=fb.frequency_baseline,u=fb.uniform_random_baseline;
    extra=`<div class="note">回测：测试 ${fb.sample?.tested} 期 · 频率基线命中率 ${(f.exact_top_k_rate*100).toFixed(2)}% · 均匀随机期望 ${(u.expected_exact_top_k_rate*100).toFixed(2)}%</div>`;
  }
  return `<div class="grid">
    <div class="card"><h3>系统健康</h3><div class="desc">宪章治理下，所有变更需经 5 专家审计 ≥4/5 通过。本大屏只读汇总现有报告与决策账本。</div></div>
    <div class="card"><h3>已注册功能</h3><div class="desc">${STATE.functions.length} 个一键操作，覆盖数据/分析/模型/盲评/回测/治理。</div></div>
    <div class="card"><h3>决策记录</h3><div class="desc">${STATE.decisions.length} 份审计/进化提案文件。</div></div>
    <div class="card"><h3>可恢复版本</h3><div class="desc">${STATE.versions.length} 个 git 恢复点（回溯用）。</div></div>
  </div>${extra}`;
}
function functionsHtml(){
  const groups={};
  STATE.functions.forEach(f=>{(groups[f.category]=groups[f.category]||[]).push(f);});
  let html='';
  for(const cat in groups){
    html+=`<div class="note">${cat}</div><div class="grid">`;
    html+=groups[cat].map(f=>{
      let params='';
      if(f.params&&f.params.length){
        params='<div class="params">'+f.params.map(p=>`<label class="p">${p.name}<input type="${p.type==='int'||p.type==='float'?'number':'text'}" data-flag="${p.flag}" data-type="${p.type}" value="${p.default}" title="${p.help||''}"></label>`).join('')+'</div>';
      }
      return `<div class="card">
      <h3>${f.title} ${riskBadge(f.risk)}</h3>
      <div class="desc">${f.desc}</div>
      <div class="cat">${f.id}</div>
      ${params}
      <button class="run" data-id="${f.id}" ${LIVE?'':'disabled'} ${f.confirm?'data-confirm="1"':''}>${LIVE?'运行':'需服务端'}</button>
    </div>`;
    }).join('');
    html+='</div>';
  }
  if(!LIVE)html+='<div class="note">当前为静态/打印视图，运行需启动服务端：<code>python workbench.py serve</code></div>';
  return html;
}
function multiMethodHtml(){
  const mm=STATE.multi_method;
  if(!mm)return '<div class="note">尚未运行「多方法对比」。在“功能”页运行 multi_method 生成对比报告。</div>';
  const lp=mm.last_period_compare||{};
  const actual=mm.actual_last;
  let h=`<div class="note">生成 ${mm.generated_at} · 配置 ${JSON.stringify(mm.config)} · 最近一期 期号 ${mm.last_period}（${lp.date||'未知日期'}）实开 <b>${actual}</b></div>`;
  h+=`<h3>最近一期（期号 ${lp.period||mm.last_period} · ${lp.date||'未知日期'}）：各方法预测 vs 实开 ${actual}</h3>`;
  h+=`<table><thead><tr><th>方法</th><th>Top候选(前10)</th><th>精确命中</th><th>位命中(0-3)</th><th>数字偏差</th><th>log-loss</th></tr></thead><tbody>`;
  (lp.methods||[]).forEach(m=>{
    const met=m.metrics||{};
    const cands=(m.candidates||[]).slice(0,10).join(' ');
    h+=`<tr><td>${m.method_id}</td><td class="mono">${cands}</td><td>${met.exact_hit?'✓':'✗'}</td><td>${met.position_top1_hits??'-'}</td><td>${met.digit_divergence??'-'}</td><td>${met.log_loss!=null?met.log_loss.toFixed(3):'-'}</td></tr>`;
  });
  h+='</tbody></table>';
  const wa=mm.window_aggregate||{};
  h+=`<h3>近 ${wa.window_size||0} 期严格时间顺序聚合（每期仅用更早数据）</h3>`;
  h+=`<table><thead><tr><th>方法</th><th>精确率</th><th>平均位命中率</th><th>平均TopK位命中率</th><th>平均数字偏差</th><th>平均log-loss</th><th>n</th></tr></thead><tbody>`;
  const pm=wa.per_method||{};
  const ids=Object.keys(pm).sort((a,b)=>pm[b].exact_rate-pm[a].exact_rate);
  ids.forEach(mid=>{
    const s=pm[mid];
    h+=`<tr><td>${mid}</td><td>${(s.exact_rate*100).toFixed(1)}%</td><td>${(s.mean_position_top1*100).toFixed(1)}%</td><td>${(s.mean_position_topk*100).toFixed(1)}%</td><td>${s.mean_digit_divergence.toFixed(2)}</td><td>${s.mean_log_loss!=null?s.mean_log_loss.toFixed(3):'-'}</td><td>${s.n}</td></tr>`;
  });
  h+='</tbody></table>';

  // NEW: 下期预测（盲评用，开奖前不可知）
  const np=mm.next_period||{};
  h+=`<h3>下期预测：期号 ${np.period||'-'}（基于截至 ${np.trained_on_periods_up_to||'-'}${np.trained_on_date?'（'+np.trained_on_date+'）':''} 的数据，盲评用途，开奖前不可知）</h3>`;
  h+=`<table><thead><tr><th>方法</th><th>Top候选(前10)</th><th>百位分布Top3</th><th>十位分布Top3</th><th>个位分布Top3</th></tr></thead><tbody>`;
  (np.methods||[]).forEach(m=>{
    const cands=(m.candidates||[]).slice(0,10).join(' ');
    const topd=(arr)=>{ if(!arr) return '-'; return [...arr.keys()].sort((a,b)=>arr[b]-arr[a]).slice(0,3).map(i=>i+':'+(arr[i]*100).toFixed(1)+'%').join(' '); };
    const d=m.distribution;
    h+=`<tr><td>${m.method_id}</td><td class="mono">${cands}</td><td>${d?topd(d[0]):'-'}</td><td>${d?topd(d[1]):'-'}</td><td>${d?topd(d[2]):'-'}</td></tr>`;
  });
  h+='</tbody></table>';

  // NEW: 历史预测 VS 实开
  const hc=mm.historical_compare||{};
  h+=`<h3>历史预测 VS 实开：期号 ${hc.period||'-'}（${hc.date||'未知日期'}）实开 <b>${hc.actual??'-'}</b>（偏移 ${mm.history_offset??'-'} 期，严格时间前训练）</h3>`;
  h+=`<table><thead><tr><th>方法</th><th>Top候选(前10)</th><th>精确命中</th><th>位命中(0-3)</th><th>数字偏差</th><th>log-loss</th></tr></thead><tbody>`;
  (hc.methods||[]).forEach(m=>{
    const met=m.metrics||{};
    const cands=(m.candidates||[]).slice(0,10).join(' ');
    h+=`<tr><td>${m.method_id}</td><td class="mono">${cands}</td><td>${met.exact_hit?'✓':'✗'}</td><td>${met.position_top1_hits??'-'}</td><td>${met.digit_divergence??'-'}</td><td>${met.log_loss!=null?met.log_loss.toFixed(3):'-'}</td></tr>`;
  });
  h+='</tbody></table>';

  h+=`<div class="note">${wa.disclaimer||''} 下期预测为盲评用途，开奖前不可知，不构成任何投注建议。</div>`;
  return h;
}
function svgLine(series, opts){
  const w=680,h=160,pad=24; const n=series.length; if(!n) return '';
  const mn=opts.min!=null?opts.min:Math.min(...series), mx=opts.max!=null?opts.max:Math.max(...series);
  const range=(mx-mn)||1;
  const x=i=> pad + (n===1?0:(i/(n-1))*(w-2*pad));
  const y=v=> h-pad - ((v-mn)/range)*(h-2*pad);
  const pts=series.map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  let s=`<svg class="chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet">`;
  s+=`<line x1="${pad}" y1="${h-pad}" x2="${w-pad}" y2="${h-pad}" stroke="#2a3343"/>`;
  s+=`<line x1="${pad}" y1="${pad}" x2="${pad}" y2="${h-pad}" stroke="#2a3343"/>`;
  if(opts.mean!=null){
    const my=y(opts.mean);
    s+=`<line x1="${pad}" y1="${my.toFixed(1)}" x2="${w-pad}" y2="${my.toFixed(1)}" stroke="${opts.color}" stroke-dasharray="4 4" opacity="0.5"/>`;
    s+=`<text x="${w-pad}" y="${(my-4).toFixed(1)}" fill="${opts.color}" font-size="10" text-anchor="end">均值 ${opts.mean.toFixed(1)}</text>`;
  }
  s+=`<polyline points="${pts}" fill="none" stroke="${opts.color}" stroke-width="2"/>`;
  series.forEach((v,i)=>{ s+=`<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="2" fill="${opts.color}"/>`; });
  s+=`<text x="${pad}" y="${pad-8}" fill="#93a1b1" font-size="10">${mx}</text><text x="${pad}" y="${h-pad+14}" fill="#93a1b1" font-size="10">${mn}</text>`;
  s+='</svg>';
  return s;
}
function svgBars(obj, opts){
  const keys=Object.keys(obj).map(Number).sort((a,b)=>a-b);
  const w=680,h=160,pad=20;
  const maxv=Math.max(1,...keys.map(k=>obj[String(k)]));
  const gap=(w-2*pad)/keys.length;
  const bw=Math.max(3,gap-2);
  let s=`<svg class="chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet">`;
  s+=`<line x1="${pad}" y1="${h-pad}" x2="${w-pad}" y2="${h-pad}" stroke="#2a3343"/>`;
  keys.forEach((k,i)=>{
    const v=obj[String(k)]||0;
    const bh=(v/maxv)*(h-2*pad);
    const x=pad+i*gap+1;
    const y=h-pad-bh;
    s+=`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw}" height="${bh.toFixed(1)}" fill="${opts.color}" opacity="0.85"/>`;
    if(v>0 && i%2===0) s+=`<text x="${(x+bw/2).toFixed(1)}" y="${h-pad+12}" fill="#93a1b1" font-size="9" text-anchor="middle">${k}</text>`;
    if(v>0 && bh>14) s+=`<text x="${(x+bw/2).toFixed(1)}" y="${(y+10).toFixed(1)}" fill="#e6edf3" font-size="9" text-anchor="middle">${v}</text>`;
  });
  s+='</svg>';
  return s;
}
function catBars(obj, title){
  if(!obj) return '';
  const entries=Object.entries(obj).sort((a,b)=>b[1]-a[1]);
  const maxv=Math.max(1,...entries.map(e=>e[1]));
  let s=`<div class="card"><h4>${title}</h4>`;
  entries.forEach(([k,v])=>{
    const pct=(v/maxv*100).toFixed(0);
    s+=`<div class="barline"><span class="blabel">${k}</span><span class="btrack"><span class="bfill" style="width:${pct}%"></span></span><span class="bval">${v}</span></div>`;
  });
  s+='</div>';
  return s;
}
function historyHtml(){
  const hs=STATE.history_stats;
  if(!hs)return '<div class="note">尚未运行「历史与统计」。在“功能”页运行 history_stats 生成报告。</div>';
  let h=`<div class="note">生成 ${hs.generated_at} · 配置 ${JSON.stringify(hs.config)} · 回看 ${hs.count} 期开奖（只读权威库）</div>`;

  const recs=(hs.records||[]).slice().reverse();
  h+=`<h3>历史开奖原始表（近 ${hs.count} 期，最新在上）</h3>`;
  h+=`<div class="scrolltable"><table><thead><tr><th>期号</th><th>日期</th><th>开奖号码</th><th>和值</th><th>跨度</th><th>奇偶</th><th>大小</th><th>类型</th></tr></thead><tbody>`;
  recs.forEach(r=>{
    const tc=r.type==='豹子'?'bz':(r.type==='组三'?'z3':'z6');
    h+=`<tr><td class="mono">${r.period}</td><td>${r.date||'-'}</td><td class="mono">${r.number}</td><td>${r.sum}</td><td>${r.span}</td><td>${r.parity_pattern}</td><td>${r.size_pattern}</td><td><span class="badge type ${tc}">${r.type}</span></td></tr>`;
  });
  h+='</tbody></table></div>';

  const sums=(hs.records||[]).map(r=>r.sum);
  const mean=sums.reduce((a,b)=>a+b,0)/Math.max(1,sums.length);
  h+=`<h3>和值走势（近 ${hs.count} 期）</h3>`;
  h+=svgLine(sums,{min:0,max:27,mean:mean,color:'#4ea1ff'});
  h+=`<h3>和值分布（0–27）</h3>`;
  h+=svgBars(hs.sum_distribution,{color:'#4ea1ff'});
  h+=`<h3>跨度分布（0–9）</h3>`;
  h+=svgBars(hs.span_distribution,{color:'#3fb950'});

  const posName=['百位','十位','个位'];
  h+=`<h3>各位数字频率 &amp; 遗漏（回看 ${hs.count} 期频率 / 全历史遗漏）</h3>`;
  h+=`<div class="freqgrid">`;
  for(let p=0;p<3;p++){
    const freq=hs.position_frequency[String(p)]||{};
    const omit=hs.position_omission[String(p)]||{};
    h+=`<div class="card"><h4>${posName[p]}</h4><table class="freq"><thead><tr><th>数字</th><th>频率</th><th>遗漏</th></tr></thead><tbody>`;
    for(let d=0;d<10;d++){
      const f=freq[String(d)]||0; const o=omit[String(d)];
      const cls=o>=30?'omit-cold':(o<=2?'omit-hot':'');
      h+=`<tr><td class="mono">${d}</td><td>${f}</td><td class="${cls}">${o}</td></tr>`;
    }
    h+='</tbody></table></div>';
  }
  h+='</div>';

  const ps=hs.parity_size||{};
  h+=`<h3>奇偶 / 大小 / 质合 占比（近 ${hs.count} 期）</h3>`;
  h+=`<div class="catgrid">${catBars(ps.parity_ratio,'奇偶比')}${catBars(ps.size_pattern,'大小')}${catBars(ps.zhihe_pattern,'质合')}</div>`;
  h+=`<div class="note">质合总量：质 ${ps.zhi_total??'-'} · 合 ${ps.he_total??'-'}</div>`;

  const ts=hs.type_stats||{};
  const tt=Object.entries(ts).map(([k,v])=>`${k}:${v}`).join(' · ');
  h+=`<h3>组选类型占比（近 ${hs.count} 期）</h3><div class="note">${tt}</div>`;

  const hc=hs.hot_cold||{};
  h+=`<h3>冷热号（近 ${hc.n??0} 期，期望 ${hc.expected??'-'} 次/数字）</h3><div class="hcgrid">`;
  (hc.ranked||[]).forEach(r=>{
    const arrow=r.cls==='hot'?'▲':(r.cls==='cold'?'▼':'');
    h+=`<span class="hc ${r.cls}">${r.digit}:${r.count}${arrow}</span>`;
  });
  h+='</div>';

  const pr=hs.prediction_rolling||{};
  h+=`<h3>历史预测滚动对照（近 ${pr.periods?pr.periods.length:0} 期 × ${pr.methods?pr.methods.length:0} 方法，严格时间前向）</h3>`;
  if(pr.periods&&pr.periods.length){
    h+=`<div class="scrolltable"><table><thead><tr><th>方法 \\ 期号</th>${pr.periods.map(p=>`<th class="hcell mono">${p.period}<br><small>实开 ${p.actual}</small></th>`).join('')}</tr></thead><tbody>`;
    (pr.methods||[]).forEach(m=>{
      h+=`<tr><td>${m.method_id}</td>`;
      (m.cells||[]).forEach(c=>{
        h+=`<td class="${c.exact_hit?'hit-ok':'hit-no'} mono" title="位命中 ${c.pos_hits}">${c.top1}${c.exact_hit?' ✓':' ·'}</td>`;
      });
      h+='</tr>';
    });
    h+='</tbody></table></div>';
  }

  h+=`<div class="note">${hs.disclaimer||''}</div>`;
  return h;
}
function arenaHtml(){
  const a=STATE.predictive_arena;
  if(!a)return '<div class="note">尚未运行「模型竞技场」。在“功能”页运行 predictive_arena 生成诚实回测报告（含 ML 方案，约需 1 分钟）。</div>';
  const hl=a.honesty_layer||{};
  const th=a.theoretical||{};
  let h=`<div class="note">生成 ${a.generated_at} · 配置 ${JSON.stringify(a.config)} · 测试 ${a.schemes_tested} 个方案（严格时间前向，仅用目标期之前数据）</div>`;

  const fdrBetter=(hl.significantly_better_fdr||0)>0;
  const rawBetter=(hl.significantly_better_raw||0)>0;
  const worse=(hl.significantly_worse_raw||0)>0;
  const cls=fdrBetter?'bad':(rawBetter?'warn':'ok');
  h+=`<div class="arena-banner">
    <div class="ab ${cls}"><div class="l">均匀随机基线命中率期望 (top_k)</div><div class="v">${hl.baseline_exact_rate_pct}%</div></div>
    <div class="ab ${cls}"><div class="l">校准 log-loss 理论值</div><div class="v">${hl.theoretical_log_loss}</div></div>
    <div class="ab ${cls}"><div class="l">与随机基线无显著差异</div><div class="v">${hl.no_significant_difference}/${a.schemes_tested}</div></div>
    <div class="ab ${cls}"><div class="l">FDR校正后仍优于基线</div><div class="v">${hl.significantly_better_fdr}</div></div>
  </div>`;
  h+=`<div class="card" style="margin-bottom:14px"><h3>诚实层结论</h3><div class="desc">${hl.conclusion}</div></div>`;
  h+=`<div class="card" style="margin:0 0 14px;border-left:3px solid var(--warn)"><h3>多重比较校正 (Benjamini-Hochberg, FDR=0.05)</h3><div class="desc">${hl.fdr_note||''}</div></div>`;

  h+=`<h3>多元描述性对照：各方案 vs 均匀随机基线</h3>`;
  h+=`<table><thead><tr><th>方案</th><th>结构族</th><th>精确命中率</th><th>基线期望</th><th>双侧 p</th><th>校准 log-loss</th><th>位命中(百/十/个)</th><th>判定</th></tr></thead><tbody>`;
  (a.results||[]).forEach(r=>{
    if(r.error)return;
    const vt=r.verdict==='与随机基线无显著差异'?'nd':(r.verdict==='显著优于随机基线'?'better':'worse');
    const ll=r.mean_log_loss!=null?r.mean_log_loss.toFixed(4):'-';
    const p1=(r.mean_position_top1||[]).map(x=>(x*100).toFixed(1)+'%').join(' / ');
    h+=`<tr><td class="mono">${r.name}</td><td>${r.family||'-'}</td><td>${(r.exact_rate*100).toFixed(2)}%</td><td>${(r.expected_exact_rate*100).toFixed(2)}%</td><td>${r.two_sided_p.toFixed(3)}</td><td>${ll}</td><td>${p1}</td><td><span class="verdict-pill ${vt}">${r.verdict}</span></td></tr>`;
  });
  h+='</tbody></table>';

  const sw=a.improvement_sweep||{};
  h+=`<h3>修偏改进尝试（假设可预测，再用回测检验）</h3>`;
  h+=`<div class="note">${sw.note||''}</div>`;
  const best=sw.best;
  if(best){
    h+=`<div class="note">遍历窗口/混合系数共 ${(sw.trials||[]).length} 组；最优：${best.name} · 命中率 ${(best.exact_rate*100).toFixed(2)}% · 基线期望 ${(sw.baseline_expected_rate*100).toFixed(2)}% · 判定 ${best.verdict} · 是否超越基线：<b>${sw.best_beats_baseline?'是':'否'}</b></div>`;
  }

  h+=`<div class="note">${a.disclaimer||''}</div>`;
  return h;
}
function debateHtml(){
  const a=STATE.debate_arena;
  if(!a)return '<div class="note">尚未运行「双阵营辩论擂台」。在“功能”页运行 debate_arena 生成对抗辩论报告（约需 1–2 分钟）。</div>';
  const sb=a.scoreboard||{}, fv=a.final_verdict||{}, da=a.dual_axis||{}, ar=a.arsenal||{};
  let h=`<div class="note">生成 ${a.generated_at} · 配置 ${JSON.stringify(a.config)} · 正方主张 ${sb.claims_total} 项，反方武器库 ${ar.n_tests||0} 项随机性检验</div>`;

  const proCls = sb.survivors_fdr>0?'bad':'ok';
  h+=`<div class="arena-banner">
    <div class="ab ${proCls}"><div class="l">正方(可预测派) 主张存活率</div><div class="v">${(sb.pro_score*100).toFixed(0)}% (${sb.survivors_fdr}/${sb.claims_total})</div></div>
    <div class="ab ${proCls}"><div class="l">反方(科学随机派) 审核通过率</div><div class="v">${(sb.anti_score*100).toFixed(0)}%</div></div>
    <div class="ab ${proCls}"><div class="l">原始显著 → FDR 后仍存活</div><div class="v">${sb.survivors_fdr}</div></div>
    <div class="ab ${proCls}"><div class="l">最终裁决</div><div class="v" style="font-size:14px">${fv.winner_label||'-'}</div></div>
  </div>`;

  h+=`<div class="card" style="margin-bottom:14px"><h3>可信度 vs 统计强度</h3>${debateGauge(da)}</div>`;

  h+=`<div class="card" style="margin-bottom:14px"><h3>反方武器库 · 随机性检验</h3><div class="desc">${ar.summary||''}</div>`;
  h+='<table><thead><tr><th>位置</th><th>检验</th><th>统计量</th><th>p</th><th>结论</th></tr></thead><tbody>';
  (ar.tests||[]).forEach(t=>{
    const cls=t.rejects?'bad':'ok';
    h+=`<tr><td>${t.position}</td><td>${t.name}</td><td>${t.stat}</td><td>${t.p}</td><td><span class="verdict-pill ${t.rejects?'worse':'nd'}">${t.rejects?'偏离均匀':'未拒绝'}</span></td></tr>`;
  });
  h+='</tbody></table></div>';

  h+=`<h3>证据卡片 · 正方主张 vs 反方审计</h3><div class="debate-cards">`;
  (a.evidence||[]).forEach(e=>{
    const vt=e.rejected?'nd':(e.fdr_survivor?'better':'worse');
    const pill = e.rejected? '已驳回' : (e.fdr_survivor?'FDR存活':'原始显著');
    const ts = e.two_sided_p!=null ? (e.two_sided_p.toFixed? e.two_sided_p.toFixed(3) : e.two_sided_p) : '-';
    const hv = e.effect_size_h!=null ? (e.effect_size_h.toFixed? e.effect_size_h.toFixed(3) : e.effect_size_h) : '-';
    const bf = e.bayes_factor!=null ? (e.bayes_factor.toFixed? e.bayes_factor.toFixed(2) : e.bayes_factor) : '-';
    let extra='';
    if(e.placebo_exceed_p!=null) extra+=` · 安慰剂p=${e.placebo_exceed_p.toFixed(3)}`;
    if(e.split_half_consistent!=null) extra+=` · 可复现=${e.split_half_consistent?'是':'否'}`;
    h+=`<div class="dcard">
      <div class="dhead"><span class="dname">${e.name}</span><span class="verdict-pill ${vt}">${pill}</span></div>
      <div class="dbelief">${e.belief}</div>
      <div class="dmetrics">命中率 ${(e.exact_rate*100).toFixed(2)}% / 基线 ${(e.expected_exact_rate*100).toFixed(2)}% · 双侧p ${ts} · 效应量h ${hv} · BF ${bf}</div>
      <div class="dreason">反方：${e.reject_reason||''}${extra}</div>
    </div>`;
  });
  h+='</div>';

  h+=`<div class="card" style="margin-top:14px"><h3>对抗轮次时间线</h3>${debateTimeline(a.rounds)}</div>`;

  h+=`<div class="card" style="margin-top:14px;border-left:3px solid var(--accent)"><h3>最终结论</h3><div class="desc">${fv.conclusion||''}</div><div class="desc" style="margin-top:8px">${fv.fdr_note||''}</div>`;
  if(fv.profit_per_bet!=null){
    const ppb=fv.profit_per_bet;
    h+=`<div class="desc" style="margin-top:8px">每注期望收益（扣除成本后）：<b style="color:${ppb>0?'var(--ok)':'var(--bad)'}">¥${ppb.toFixed(2)}</b>（直选奖金¥${a.config.prize}，每注¥${a.config.cost_per_number}，候选${a.config.top_k}注/期）</div>`;
  }
  h+=`<div class="desc" style="margin-top:8px;color:var(--muted)">${fv.disclaimer||''}</div></div>`;
  return h;
}
function debateGauge(da){
  const bel=(da.believability||0)*100, str=(da.statistical_strength||0)*100;
  let s=`<svg class="chart" viewBox="0 0 680 64">`;
  s+=`<text x="20" y="18" font-size="12" fill="var(--text)">人类可信度（正方说服力）</text>`;
  s+=`<rect x="20" y="22" width="640" height="12" rx="6" fill="var(--border)"/>`;
  s+=`<rect x="20" y="22" width="${640*bel/100}" height="12" rx="6" fill="var(--warn)"/>`;
  s+=`<text x="664" y="33" font-size="11" fill="var(--warn)" text-anchor="end">${bel.toFixed(0)}%</text>`;
  s+=`<text x="20" y="50" font-size="12" fill="var(--text)">统计强度（反方证据力）</text>`;
  s+=`<rect x="20" y="54" width="640" height="12" rx="6" fill="var(--border)"/>`;
  s+=`<rect x="20" y="54" width="${640*str/100}" height="12" rx="6" fill="var(--ok)"/>`;
  s+=`<text x="664" y="65" font-size="11" fill="var(--ok)" text-anchor="end">${str.toFixed(0)}%</text>`;
  s+=`</svg>`;
  const r=da.radar||{};
  const dims=[['命中率边缘',r.命中率边缘],['FDR存活',r.FDR存活],['可盈利性',r.可盈利性],['可复现',r.可复现],['安慰剂稳健',r.安慰剂稳健]];
  const cx=170,cy=90,R=70,n=dims.length;
  let pts='';
  const coords=dims.map((d,i)=>{const ang=-Math.PI/2+2*Math.PI*i/n;const v=Math.max(0,Math.min(1,d[1]||0));const x=cx+R*v*Math.cos(ang);const y=cy+R*v*Math.sin(ang);pts+=x.toFixed(1)+','+y.toFixed(1)+' ';return {x,y,ang,d};});
  s+=`<svg class="chart" viewBox="0 0 340 180" style="display:inline-block;vertical-align:top">`;
  for(let g=1;g<=4;g++){let gp='';for(let i=0;i<n;i++){const ang=-Math.PI/2+2*Math.PI*i/n;const x=cx+R*g/4*Math.cos(ang);const y=cy+R*g/4*Math.sin(ang);gp+=x.toFixed(1)+','+y.toFixed(1)+' ';}s+=`<polygon points="${gp}" fill="none" stroke="var(--border)" stroke-width="1"/>`;}
  for(let i=0;i<n;i++){const ang=-Math.PI/2+2*Math.PI*i/n;const x=cx+R*Math.cos(ang);const y=cy+R*Math.sin(ang);s+=`<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--border)" stroke-width="1"/>`;}
  s+=`<polygon points="${pts}" fill="rgba(210,153,34,.25)" stroke="var(--warn)" stroke-width="2"/>`;
  coords.forEach(c=>{s+=`<text x="${(cx+(R+16)*Math.cos(c.ang)).toFixed(1)}" y="${(cy+(R+16)*Math.sin(c.ang)).toFixed(1)}" font-size="10" fill="var(--muted)">${c.d[0]}</text>`;});
  s+=`<text x="${cx}" y="174" font-size="11" fill="var(--muted)" text-anchor="middle">五维评估雷达</text>`;
  s+=`</svg>`;
  return s;
}
function debateTimeline(rounds){
  if(!rounds||!rounds.length)return '<div class="note">无轮次数据</div>';
  const W=680,H=92,n=rounds.length,gap=W/n;
  let s=`<svg class="chart" viewBox="0 0 ${W} ${H}">`;
  rounds.forEach((r,i)=>{
    const x=gap*i+gap/2;
    s+=`<line x1="${x}" y1="28" x2="${x}" y2="${H-18}" stroke="var(--border)"/>`;
    s+=`<circle cx="${x}" cy="28" r="11" fill="var(--accent)"/>`;
    s+=`<text x="${x}" y="32" font-size="11" fill="#fff" text-anchor="middle">${r.round}</text>`;
    s+=`<text x="${x}" y="54" font-size="11" fill="var(--text)" text-anchor="middle">${r.n_claims}项</text>`;
    s+=`<text x="${x}" y="70" font-size="11" fill="var(--ok)" text-anchor="middle">存活${r.n_survivors}</text>`;
    s+=`<text x="${x}" y="84" font-size="9" fill="var(--muted)" text-anchor="middle">第${r.round}轮</text>`;
  });
  s+=`</svg>`;
  return s;
}
function evolutionHtml(){
  const r=STATE.evolution_arena;
  if(!r)return '<div class="note">尚未运行「自进化辩论擂台」。在“功能”页运行 evolution_arena 生成闭环报告（约需 1–2 分钟）。</div>';
  const cfg=r.config||{}, lg=r.ledger||{}, camps=(lg.camps)||{}, pro=camps.pro||{}, con=camps.con||{}, badges=lg.badges||{};
  const dir=r.directional||{}, fv=r.final_verdict||{}, ar=r.arsenal||{}, oos=r.oos||{};
  const es=r.engine_state||{};
  const esNote = es.runs ? ` · 引擎累计运行 ${es.runs} 次（跨运行累积账本+近失种子）` : '';
  let h=`<div class="note">生成 ${r.generated_at} · 配置 ${JSON.stringify(cfg)} · 累计主张 ${(r.lineage||[]).length} 项，反方武器库 ${ar.n_tests||0} 项随机性检验${esNote}</div>`;
  h+=evolutionLedgerHtml(pro,con,badges);
  h+=evolutionGauge(dir,fv);
  h+=evolutionConvergence(r.generations||[], cfg.oos_n);
  h+=evolutionLineage(r.lineage||[], r.evidence||[]);
  h+=evolutionOpenHypotheses(r);
  h+=evolutionArsenal(ar);
  h+=evolutionOOS(oos,cfg);
  h+=evolutionFinal(fv,cfg);
  return h;
}
function evolutionLedgerHtml(pro,con,badges){
  const badgePro=badges.pro?'<span class="medal">'+badges.pro+'</span>':'';
  const badgeCon=badges.con?'<span class="medal">'+badges.con+'</span>':'';
  return `<div class="card" style="margin-bottom:14px"><h3>① 激励账本（双阵营积分 + 独立 Reputation + 徽章）</h3>
    <div class="ledger-grid">
      <div class="ledger-card pro"><div class="ll">正方 主张积分 AP</div><div class="lv">${pro.ap!=null?pro.ap.toFixed(1):'—'}</div>${badgePro}</div>
      <div class="ledger-card pro"><div class="ll">正方 声望 Rep</div><div class="lv">${pro.rep!=null?pro.rep.toFixed(1):'—'}</div></div>
      <div class="ledger-card pro"><div class="ll">提交/存活/撤回</div><div class="lv">${pro.submitted||0} / ${pro.survived||0} / ${pro.retracted||0}</div></div>
      <div class="ledger-card con"><div class="ll">反方 纠错积分 RP</div><div class="lv">${con.rp!=null?con.rp.toFixed(1):'—'}</div>${badgeCon}</div>
      <div class="ledger-card con"><div class="ll">反方 声望 Rep</div><div class="lv">${con.rep!=null?con.rep.toFixed(1):'—'}</div></div>
      <div class="ledger-card con"><div class="ll">挑战/正确/误驳</div><div class="lv">${con.challenges||0} / ${con.correct||0} / ${con.wrongful||0}</div></div>
    </div>
    <div class="desc" style="margin-top:6px">规则：提交冻结押金(C_SUB=5)；经 FDR+安慰剂+复现+盈利闸全过 → 退还押金并按 merit_w 奖励 50×merit_w AP、Rep+4；被驳回没收押金、Rep-3；诚实撤回退押金+20AP、Rep+2。反方正确驳回得 30+10×decisiveness RP、Rep+3；误驳 Rep-5。Rep 与积分分离，科学权重优先。徽章：Bronze→Silver→Gold→Platinum 由 Rep 与战绩阈值决定。</div>
  </div>`;
}
function evolutionGauge(dir,fv){
  const score=dir.score||0, ci=dir.score_ci||[-1,1];
  const W=680,H=120,pad=40;
  const x=v=> pad + (Math.max(-1,Math.min(1,v))+1)/2*(W-2*pad);
  const nullP975=(dir.null_calibration&&dir.null_calibration.score_null_p975)||1.0;
  const nb0=x(-nullP975), nb1=x(nullP975);
  const c0=x(ci[0]), c1=x(ci[1]);
  const sx=x(score);
  const verdictLabel=fv.winner_label||'-';
  let s=`<svg class="chart" viewBox="0 0 ${W} ${H}">`;
  s+=`<rect x="${x(-1)}" y="40" width="${(W-2*pad).toFixed(1)}" height="16" rx="8" fill="var(--border)"/>`;
  s+=`<rect x="${nb0.toFixed(1)}" y="40" width="${(nb1-nb0).toFixed(1)}" height="16" fill="rgba(139,152,168,.35)"/>`;
  s+=`<rect x="${c0.toFixed(1)}" y="34" width="${(c1-c0).toFixed(1)}" height="28" fill="rgba(78,161,255,.35)"/>`;
  s+=`<line x1="${x(0)}" y1="28" x2="${x(0)}" y2="68" stroke="#93a1b1" stroke-dasharray="3 3"/>`;
  s+=`<line x1="${sx.toFixed(1)}" y1="26" x2="${sx.toFixed(1)}" y2="70" stroke="var(--warn)" stroke-width="3"/>`;
  s+=`<circle cx="${sx.toFixed(1)}" cy="48" r="6" fill="var(--warn)"/>`;
  s+=`<text x="${x(-1)}" y="88" font-size="11" fill="#93a1b1">随机(H₀) -1</text>`;
  s+=`<text x="${x(0)}" y="88" font-size="11" fill="#93a1b1" text-anchor="middle">0</text>`;
  s+=`<text x="${x(1)}" y="88" font-size="11" fill="#93a1b1" text-anchor="end">可预测(H⁺) +1</text>`;
  s+=`<text x="${sx.toFixed(1)}" y="106" font-size="12" fill="var(--warn)" text-anchor="middle">score=${score.toFixed(3)}</text>`;
  s+='</svg>';
  const cls=fv.winner==='random'?'ok':(fv.winner==='weak_signal'?'warn':'nd');
  let h=`<div class="card" style="margin-bottom:14px"><h3>③ 决策方向科学评价（单一方向标量 score=tanh(Z)∈(−1,+1)）</h3>
    ${s}
    <div class="desc">灰带=零分布 97.5% 区间(±${nullP975.toFixed(2)}，落入即"与随机不可区分")；蓝带=score 的 95% CI=${JSON.stringify(ci)}。信心(可预测)=${dir.confidence_predictable!=null?dir.confidence_predictable.toFixed(3):'-'} · 等价随机信心=${dir.confidence_random_equiv!=null?dir.confidence_random_equiv.toFixed(3):'-'} · Fisher p=${dir.fisher_p!=null?dir.fisher_p.toFixed(4):'-'} · Stouffer Z=${dir.stouffer_z!=null?dir.stouffer_z.toFixed(3):'-'} · 组合BF=${dir.bayes_factor_portfolio!=null?dir.bayes_factor_portfolio.toFixed(3):'-'} · 最大效应量h=${dir.max_effect_h!=null?dir.max_effect_h.toFixed(3):'-'} · 结论 ${dir.conclusion}</div>
    <div class="arena-banner" style="margin-top:10px"><div class="ab ${cls}"><div class="l">最终裁决</div><div class="v" style="font-size:14px">${verdictLabel}</div></div></div>
  </div>`;
  return h;
}
function evolutionConvergence(gens, oosN){
  if(!gens.length)return '<div class="card" style="margin-bottom:14px"><h3>② 自进化元循环 · 谱系收敛</h3><div class="note">无代际数据</div></div>';
  const scores=gens.map(g=>g.score||0);
  let h=`<div class="card" style="margin-bottom:14px"><h3>② 自进化元循环 · 谱系收敛</h3>`;
  h+=`<table class="evo-table"><thead><tr><th>代 gen</th><th>候选数</th><th>FDR 存活</th><th>方向得分 score</th><th>CI</th><th>Fisher p</th></tr></thead><tbody>`;
  gens.forEach(g=>{
    h+=`<tr><td>${g.generation}</td><td>${g.n_claims}</td><td>${g.n_survivors}</td><td>${g.score!=null?g.score.toFixed(3):'-'}</td><td>${JSON.stringify(g.score_ci||[])}</td><td>${g.fisher_p!=null?g.fisher_p.toFixed(4):'-'}</td></tr>`;
  });
  h+='</tbody></table>';
  h+=`<div class="note">各代方向得分（−1 随机 … +1 可预测）：</div>`;
  h+=svgLine(scores,{min:-1,max:1,color:'#d29922'});
  h+=`<div class="desc">开放探索姿态：引擎<b>不以"未检出信号"为由停止生成</b>，仅在达到 max_gens 上限时结束本轮；跨运行还会推进随机种子并回流近失假设继续探索。生成越多假设，全局 FDR 阈值越严（q_eff=q0×m0/m，防数据淘金）；OOS 盲窗训练严格限定在末 ${oosN||''} 期之前。</div>`;
  return h+'</div>';
}
function evolutionLineage(lineage, evidence){
  void evidence;
  let h=`<div class="card" style="margin-bottom:14px"><h3>谱系与适应度（parent→child 自进化树）</h3>`;
  if(!lineage.length){h+='<div class="note">无谱系数据</div>';return h+'</div>';}
  const tagMap={mutate:'突变',random:'随机',comprehensive:'综合','':'基'};
  const tagCls={mutate:'mutate',random:'random',comprehensive:'comprehensive','':'base'};
  h+=`<div class="scrolltable"><table class="evo-table"><thead><tr><th>主张</th><th>代</th><th>来源</th><th>族</th><th>命中率/基线</th><th>双侧p</th><th>h</th><th>BF</th><th>FDR存活</th><th>状态</th></tr></thead><tbody>`;
  lineage.forEach(l=>{
    const f=l.fitness||{}, origin=l.origin||'';
    const ot=tagMap[origin]||'基'; const oc=tagCls[origin]||'base';
    const surv=f.fdr_survivor?'✓':'✗';
    const survCls=f.fdr_survivor?'hit-ok':'hit-no';
    h+=`<tr><td class="mono" title="${l.claim_id}">${(l.claim_id||'').slice(0,22)}</td><td>${l.generation}</td><td><span class="tag ${oc}">${ot}</span></td><td>${l.family||'-'}</td><td>${(f.exact_rate*100).toFixed(2)}% / ${(f.expected_exact_rate*100).toFixed(2)}%</td><td>${f.two_sided_p!=null?f.two_sided_p.toFixed(3):'-'}</td><td>${f.effect_size_h!=null?f.effect_size_h.toFixed(3):'-'}</td><td>${f.bayes_factor!=null?f.bayes_factor.toFixed(2):'-'}</td><td class="${survCls}">${surv}</td><td>${l.status}</td></tr>`;
  });
  h+='</tbody></table></div>';
  return h+'</div>';
}
function evolutionOpenHypotheses(r){
  const oh=(r.open_hypotheses||[]);
  let h=`<div class="card" style="margin-bottom:14px"><h3>开放假设 · 持续探索中的弱信号（不视为失败）</h3>`;
  if(!oh.length){
    h+='<div class="note">本轮无"近失"主张（p&lt;0.2 但未过 FDR）。它们会在后续运行以近失种子形式回流重验；当前特征空间下暂无可标定的微妙联结。</div>';
    return h+'</div>';
  }
  h+=`<div class="desc">这些主张当前未通过 FDR 严格闸门，但 p 值已逼近临界（&lt;0.2），属"微妙联结的蛛丝马迹"。本引擎把它们作为<b>开放假设</b>持续追踪，而非"已被证伪"——下一轮会以近失种子回流，换角度/换数据窗口继续检验。</div>`;
  h+=`<div class="scrolltable"><table class="evo-table"><thead><tr><th>主张</th><th>来源</th><th>族 / 特征</th><th>命中率/基线</th><th>双侧p</th><th>h</th><th>BF</th><th>状态</th></tr></thead><tbody>`;
  oh.forEach(l=>{
    const f=l.fitness||{};
    h+=`<tr><td class="mono" title="${l.claim_id}">${(l.claim_id||'').slice(0,28)}</td><td>${l.origin||'-'}</td><td>${l.family||'-'}${l.feats?(' / '+l.feats.join(',')):''}</td><td>${(f.exact_rate*100).toFixed(2)}% / ${(f.expected_exact_rate*100).toFixed(2)}%</td><td>${f.two_sided_p!=null?f.two_sided_p.toFixed(3):'-'}</td><td>${f.effect_size_h!=null?f.effect_size_h.toFixed(3):'-'}</td><td>${f.bayes_factor!=null?f.bayes_factor.toFixed(2):'-'}</td><td><span class="tag open">开放</span></td></tr>`;
  });
  h+='</tbody></table></div></div>';
  return h;
}
function evolutionArsenal(ar){
  let h=`<div class="card" style="margin-bottom:14px"><h3>反方武器库 · 随机性检验（${ar.n_tests||0} 项）</h3><div class="desc">${ar.summary||''}</div>`;
  if(ar.tests&&ar.tests.length){
    h+='<div class="scrolltable"><table class="evo-table"><thead><tr><th>位置</th><th>检验</th><th>统计量</th><th>p</th><th>结论</th></tr></thead><tbody>';
    ar.tests.forEach(t=>{
      h+=`<tr><td>${t.position}</td><td>${t.name}</td><td>${t.stat}</td><td>${t.p}</td><td><span class="verdict-pill ${t.rejects?'worse':'nd'}">${t.rejects?'偏离均匀':'未拒绝'}</span></td></tr>`;
    });
    h+='</tbody></table></div>';
  }
  h+='</div>';
  return h;
}
function evolutionOOS(oos,cfg){
  const oosSurv=(oos.survivors||[]);
  let h=`<div class="card" style="margin-bottom:14px"><h3>末 ${cfg.oos_n||0} 期 OOS 盲评（训练严格限定在盲窗之前，防数据淘金）</h3><div class="desc">${oos.note||''}</div>`;
  if(oosSurv.length){
    h+='<table class="evo-table"><thead><tr><th>主张</th><th>样本n</th><th>命中率</th><th>盲评超基线p</th><th>盲评判定</th></tr></thead><tbody>';
    oosSurv.forEach(r=>{
      h+=`<tr><td class="mono">${r.claim}</td><td>${r.n}</td><td>${(r.exact_rate*100).toFixed(2)}%</td><td>${r.oos_exceeds_p!=null?r.oos_exceeds_p.toFixed(4):'-'}</td><td>${r.oos_verdict}</td></tr>`;
    });
    h+='</tbody></table>';
  }else{
    h+='<div class="note">无 FDR 存活主张进入盲评（符合纯随机预期）。</div>';
  }
  h+='</div>';
  return h;
}
function evolutionFinal(fv,cfg){
  let h=`<div class="card" style="margin-bottom:14px;border-left:3px solid var(--accent)"><h3>最终结论</h3><div class="desc">${fv.conclusion||''}</div>`;
  if(fv.profit_per_bet!=null){
    const ppb=fv.profit_per_bet;
    h+=`<div class="desc" style="margin-top:8px">每注期望收益（扣除成本后）：<b style="color:${ppb>0?'var(--ok)':'var(--bad)'}">¥${ppb.toFixed(2)}</b>（直选奖金¥${cfg.prize}，每注¥${cfg.cost_per_number}，候选${cfg.top_k}注/期）</div>`;
  }
  h+=`<div class="desc" style="margin-top:8px;color:var(--muted)">${fv.disclaimer||''}</div></div>`;
  return h;
}
function interventionsHtml(){
  const iv=STATE.interventions;
  if(!iv)return '<div class="note">尚未有任何人机干预记录。</div>';
  const c=iv.counts||{};
  let h=`<div class="note">人类干预治理层（「自主神经稳态」入口）：人类只能以受控、可审计、带自保护的干预请求影响系统——调参 / 加因子 / 推翻裁决 / 重置均按风险分级 L0→L3，并经泄漏检测 / 显著性膨胀 / 重置滥用 / 无证据推翻 / cherry-pick 等稳态检查，决定 accept(应用) / quarantine(待复核) / reject(拒绝)。全部 append-only 记录，不可篡改。</div>`;

  h+=`<div class="arena-banner">
    <div class="ab"><div class="l">累计干预</div><div class="v">${c.total||0}</div></div>
    <div class="ab ok"><div class="l">接受(应用)</div><div class="v">${c.accept||0}</div></div>
    <div class="ab warn"><div class="l">隔离(待复核)</div><div class="v">${c.quarantine||0}</div></div>
    <div class="ab bad"><div class="l">拒绝(自保护)</div><div class="v">${c.reject||0}</div></div>
  </div>`;

  const ov=iv.overrides||{};
  const ovKeys=Object.keys(ov);
  h+=`<div class="card" style="margin-bottom:14px"><h3>生效中的参数覆盖（仅 accept 者，引擎每次运行加载）</h3>`;
  if(ovKeys.length){
    h+='<div class="ivgrid">'+ovKeys.map(k=>`<div class="p"><span>${k}</span><b>${ov[k]}</b></div>`).join('')+'</div>';
    h+='<div class="desc" style="margin-top:8px">这些参数覆盖正被自进化引擎在每次运行时加载（见「进化擂台」配置里的 overrides_applied）。</div>';
  }else{
    h+='<div class="note">无生效参数覆盖。</div>';
  }
  h+='</div>';

  const reg=iv.factor_registry||[];
  h+=`<div class="card" style="margin-bottom:14px"><h3>人类注册影响因子（已接入引擎，每代参与评估）</h3>`;
  if(reg.length){
    h+='<div class="scrolltable"><table class="evo-table"><thead><tr><th>因子 spec</th><th>注册者</th><th>注册时间</th></tr></thead><tbody>';
    reg.forEach(s=>{
      const spec=s.spec||s; const by=s.by||'-'; const ts=s.created_at||'-';
      h+=`<tr><td class="mono">${JSON.stringify(spec)}</td><td>${by}</td><td>${ts}</td></tr>`;
    });
    h+='</tbody></table></div>';
  }else{
    h+='<div class="note">无注册因子。</div>';
  }
  h+='</div>';

  const log=iv.log||[];
  h+=`<h3>干预账本（append-only，最近 50 条倒序）</h3>`;
  if(log.length){
    h+='<div class="scrolltable"><table class="evo-table"><thead><tr><th>时间</th><th>类型</th><th>分级</th><th>决定</th><th>操作者</th><th>理由/复核</th></tr></thead><tbody>';
    log.forEach(r=>{
      const tier=r.tier||'-';
      const st=r.status||'-';
      const stCls=st==='accept'?'accept':(st==='quarantine'?'quarantine':'reject');
      const reasons=(r.reasons&&r.reasons.length)?r.reasons.join('；'):(r.rationale||'-');
      h+=`<tr><td>${r.decided_at||r.created_at||'-'}</td><td>${r.type||'-'}</td><td>${riskBadge(tier)}</td><td><span class="badge iv ${stCls}">${st}</span></td><td>${r.by||'-'}</td><td class="desc">${reasons}</td></tr>`;
    });
    h+='</tbody></table></div>';
  }else{
    h+='<div class="note">暂无干预记录。</div>';
  }
  h+=`<div class="note">调用方式（服务端）：<code>python -m workbench.interventions param_change --by user --set top_k=12 --why "..."</code> · <code>add_factor --spec '{"kind":"pos_parity_eq","a":0,"b":1}'</code> · <code>override_verdict --claim &lt;id&gt; --why "..."</code> · <code>reset</code></div>`;
  return h;
}

function externalCouplingHtml(){
  const r=STATE.external_coupling;
  if(!r)return '<div class="note">尚未运行外部/日历耦合探针。可在「功能」选项卡运行 external_coupling。</div>';
  const tests=r.tests||[];
  let h=`<div class="note">外部/跨域耦合探针（"蝴蝶效应 / 微妙联结"的域外延伸）：从每期开奖日期派生星期 / 周末 / 月份 / 月初月末，用卡方独立性 + 均值置换检验探测"外部状态→开奖"耦合，全部 BH-FDR(q=0.05) 校正。外部特征仅由已发生日期派生，构造上零泄漏。样本 n=${r.n} · 置换 M=${r.m_perm}。</div>`;
  h+=`<div class="arena-banner">
    <div class="ab"><div class="l">检验总数</div><div class="v">${tests.length}</div></div>
    <div class="ab warn"><div class="l">原始 p&lt;0.05</div><div class="v">${r.n_rejected_raw||0}</div></div>
    <div class="ab ok"><div class="l">FDR 存活</div><div class="v">${(r.fdr_survivors||[]).length}</div></div>
  </div>`;
  h+=`<div class="card" style="margin-bottom:14px"><h3>结论</h3><div class="desc">${r.summary||''}</div></div>`;
  h+=`<h3>检验明细（按 p 升序）</h3><div class="scrolltable"><table class="evo-table"><thead><tr><th>检验</th><th>类型</th><th>统计量</th><th>p</th><th>FDR</th></tr></thead><tbody>`;
  tests.slice().sort((a,b)=>a.p-b.p).forEach(t=>{
    const fdr=t.fdr_survivor?'<span class="badge iv accept">存活</span>':'<span class="badge iv reject">否</span>';
    h+=`<tr><td>${t.name}</td><td>${t.type||'-'}</td><td>${t.stat}</td><td>${t.p}</td><td>${fdr}</td></tr>`;
  });
  h+='</tbody></table></div>';
  h+=`<div class="note">${r.disclaimer||''}</div>`;
  return h;
}

function nearMissEnsembleHtml(){
  const r=STATE.near_miss_ensemble;
  if(!r)return '<div class="note">尚未运行近失集成/元学习。可在「功能」选项卡运行 near_miss_ensemble。</div>';
  if(r.error)return `<div class="note">${r.error}</div>`;
  const har=r.harvested||{};
  const ens=r.ensembles||[];
  const fdr=r.fdr_results||[];
  const pf=r.portfolio||{};
  let h=`<div class="note">近失假设集成 / 元学习：收割近失候选（基桩族 ${har.report||0} · 跨运行种子 ${har.state||0} · 确定性合成补足 ${har.synthetic||0} → 池大小 ${r.pool_size}），投票/堆叠集成，严格 OOS 盲窗评估 vs 均匀随机基线 + BH-FDR + Fisher/Stouffer 组合 p。</div>`;
  h+=`<div class="arena-banner">
    <div class="ab"><div class="l">池大小</div><div class="v">${r.pool_size}</div></div>
    <div class="ab"><div class="l">Fisher p</div><div class="v">${pf.fisher_p??'-'}</div></div>
    <div class="ab"><div class="l">Stouffer Z</div><div class="v">${pf.stouffer_z??'-'}</div></div>
    <div class="ab ${(((r.best_ensemble_oos||{}).beats_baseline)?'ok':'warn')}"><div class="l">最佳 OOS 胜基线</div><div class="v">${(((r.best_ensemble_oos||{}).beats_baseline)?'是':'否')}</div></div>
  </div>`;
  h+=`<h3>集成器（min_votes 扫描，左训练窗参考 / 右 OOS 盲窗）</h3><div class="scrolltable"><table class="evo-table"><thead><tr><th>min_votes</th><th>训练命中率</th><th>训练 p</th><th>OOS 命中率</th><th>OOS p</th><th>OOS 95%CI</th></tr></thead><tbody>`;
  ens.forEach(e=>{
    const tr=e.train||{}, oo=e.oos||{};
    const ci=(oo.ci95&&oo.ci95.length)?`[${oo.ci95[0].toFixed(4)}, ${oo.ci95[1].toFixed(4)}]`:'-';
    h+=`<tr><td>${e.min_votes}/${e.m}</td><td>${tr.exact_rate!=null?tr.exact_rate.toFixed(4):'-'}</td><td>${tr.exceeds_baseline_p!=null?tr.exceeds_baseline_p.toFixed(3):'-'}</td><td>${oo.exact_rate!=null?oo.exact_rate.toFixed(4):'-'}</td><td>${oo.exceeds_baseline_p!=null?oo.exceeds_baseline_p.toFixed(3):'-'}</td><td class="mono">${ci}</td></tr>`;
  });
  h+='</tbody></table></div>';
  h+=`<h3>FDR 校正（成员 + 集成器的 OOS 右尾 p）</h3><div class="scrolltable"><table class="evo-table"><thead><tr><th>对象</th><th>OOS 右尾 p</th><th>FDR 存活</th></tr></thead><tbody>`;
  fdr.forEach(f=>{
    const s=f.fdr_survivor?'<span class="badge iv accept">存活</span>':'<span class="badge iv reject">否</span>';
    h+=`<tr><td>${f.name}</td><td>${f.oos_exceeds_p}</td><td>${s}</td></tr>`;
  });
  h+='</tbody></table></div>';
  const fv=r.final_verdict||{};
  h+=`<div class="card" style="margin-bottom:14px"><h3>裁决：${fv.winner_label||'-'}</h3><div class="desc">${fv.fdr_note||''}</div><div class="desc">${fv.conclusion||''}</div></div>`;
  h+=`<div class="note">${r.disclaimer||''}</div>`;
  return h;
}

function backtestHtml(){
  const fb=STATE.backtest;
  if(!fb)return '<div class="note">尚未运行回测。在“功能”页运行 backtest。</div>';
  const f=fb.frequency_baseline,u=fb.uniform_random_baseline;
  return `<div class="card"><h3>严格时间顺序回测</h3>
    <div class="desc">${fb.disclaimer||''}</div>
    <div class="summary">配置：${JSON.stringify(fb.config)}
样本：${JSON.stringify(fb.sample)}
频率基线 命中率=${(f.exact_top_k_rate*100).toFixed(3)}%  期望(均匀)=${(u.expected_exact_top_k_rate*100).toFixed(3)}%
百位命中=${(f.position_top1_rates[0]*100).toFixed(2)}% 十位=${(f.position_top1_rates[1]*100).toFixed(2)}% 个位=${(f.position_top1_rates[2]*100).toFixed(2)}% (期望各 10%)</div>
  </div>`;
}
function decisionsHtml(){
  if(!STATE.decisions.length)return '<div class="note">暂无决策记录。</div>';
  return `<table><thead><tr><th>标题</th><th>状态</th><th>提案ID</th><th>更新</th><th>文件</th></tr></thead><tbody>
    ${STATE.decisions.map(d=>`<tr><td>${d.title}</td><td>${riskBadge2(d.status)}</td><td>${d.proposal_id}</td><td>${d.mtime}</td><td>${d.file}</td></tr>`).join('')}
  </tbody></table>`;
}
function riskBadge2(s){const c=s==='APPROVED'?'ok':(s==='REJECTED'?'bad':'warn');return `<span class="badge ${c}" style="background:rgba(255,255,255,.06)">${s}</span>`;}
function timelineHtml(){
  if(!STATE.timeline.length)return '<div class="note">暂无时间轴。</div>';
  return `<ul class="timeline">${STATE.timeline.map(t=>`<li><span class="type">${t.type}</span>${t.date} · ${t.text}</li>`).join('')}</ul>`;
}
function reportsHtml(){
  if(!STATE.reports.length)return '<div class="note">暂无报告。</div>';
  return STATE.reports.map(r=>`<div class="acc"><summary>${r.name} <span class="cat">(${r.mtime})</span></summary><div class="body">${r.summary.join('\n')}</div></div>`).join('');
}

let consoleLines=[];
function openConsole(){document.getElementById('console').classList.add('show');}
function closeConsole(){document.getElementById('console').classList.remove('show');consoleLines=[];document.getElementById('consolebody').textContent='';}
function appendLine(s){consoleLines.push(s);document.getElementById('consolebody').textContent=consoleLines.join('\n');}

async function runCmd(id,confirm,card){
  if(!LIVE)return;
  if(confirm && !window.confirm('该操作属于高风险(L2)，确认执行？'))return;
  const args=[];
  if(card){
    card.querySelectorAll('input[data-flag]').forEach(inp=>{
      const v=inp.value;
      if(v!=='' && v!=null)args.push(inp.dataset.flag, v);
    });
  }
  openConsole();appendLine(`▶ ${id}${args.length?(' ('+args.join(' ')+')'):''} ...`);
  try{
    const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,args})});
    const j=await r.json();
    if(j.error){appendLine('ERROR: '+j.error);return;}
    const tid=j.task_id;
    while(true){
      await new Promise(r=>setTimeout(r,800));
      const t=await fetch('/api/task?id='+encodeURIComponent(tid));
      const s=await t.json();
      consoleLines=s.log.slice();document.getElementById('consolebody').textContent=consoleLines.join('\n');
      if(s.status!=='running'){appendLine(s.status==='done'?(s.returncode===0?'✓ 完成 (exit 0)':'✗ 失败 (exit '+s.returncode+')'):s.status);break;}
    }
  }catch(e){appendLine('NETWORK ERROR: '+e);}
}
document.addEventListener('click',e=>{const b=e.target.closest('button.run');if(b)runCmd(b.dataset.id,b.dataset.confirm,b.closest('.card'));});

renderMeta();renderKpis();renderTabs();showPanel('overview');
</script>
</body>
</html>
"""


def build_html(state: dict, live: bool = False) -> str:
    safe = json.dumps(state, ensure_ascii=False)
    safe = safe.replace("</", "<\\/")
    html = TEMPLATE.replace("STATE_JSON_PLACEHOLDER", safe)
    html = html.replace("LIVE_FLAG_PLACEHOLDER", "true" if live else "false")
    return html


def print_summary(state: dict) -> str:
    p = state.get("project", {})
    k = state.get("kpis", {})
    lines = []
    lines.append("# 福彩3D 决策摘要")
    lines.append("")
    lines.append(f"生成时间: {state.get('generated_at')}")
    lines.append(f"样本: {p.get('draws')} 期 | 期号 {p.get('period_min')}–{p.get('period_max')} | 最新 {p.get('last_draw_date')}")
    lines.append("")
    lines.append("## 关键指标 (KPI)")
    lines.append(f"- 综合研判 verdict: {k.get('verdict')}")
    lines.append(f"- 模型闸门 gate: {k.get('gate_decision')}")
    lines.append(f"- 漂移动作 drift: {k.get('drift_action')}")
    lines.append(f"- 泄漏扫描 leakage: {k.get('leakage_status')} (scanned={k.get('leakage_scanned')})")
    lines.append("")
    lines.append("## 回测")
    fb = state.get("backtest")
    if fb and fb.get("frequency_baseline"):
        f = fb["frequency_baseline"]
        u = fb["uniform_random_baseline"]
        lines.append(f"- 测试 {fb['sample']['tested']} 期")
        lines.append(f"- 频率基线命中率 {f['exact_top_k_rate']*100:.3f}% | 均匀随机期望 {u['expected_exact_top_k_rate']*100:.3f}%")
    else:
        lines.append("- 尚未运行回测")
    lines.append("")
    lines.append("## 决策/审计记录")
    for d in state.get("decisions", []):
        lines.append(f"- [{d['status']}] {d['title']} ({d['file']}, {d['mtime']})")
    lines.append("")
    lines.append("## 多方法对比（多种预测方式共存）")
    mm = state.get("multi_method")
    if mm:
        lp = mm.get("last_period_compare") or {}
        lines.append(f"- 最近一期 期号 {mm.get('last_period')} 实开 {mm.get('actual_last')}（配置 {mm.get('config')}）")
        for m in lp.get("methods", []):
            met = m.get("metrics") or {}
            lines.append(f"  - {m['method_id']}: 精确={met.get('exact_hit')} 位命中={met.get('position_top1_hits')} 偏差={met.get('digit_divergence')}")
        wa = mm.get("window_aggregate") or {}
        for mid, s in (wa.get("per_method") or {}).items():
            lines.append(f"  - 近{wa.get('window_size')}期 {mid}: 精确率={s['exact_rate']*100:.1f}% 均偏差={s['mean_digit_divergence']:.2f}")
    else:
        lines.append("- 尚未运行（功能页运行 multi_method）")
    lines.append("")
    lines.append("## 一键功能列表")
    for f in state.get("functions", []):
        lines.append(f"- [{f['risk']}] {f['title']} — {f['desc']}")
    lines.append("")
    lines.append("## 最近报告")
    for r in state.get("reports", []):
        lines.append(f"- {r['name']} ({r['mtime']}): {'; '.join(r['summary'][:4])}")
    return "\n".join(lines)
