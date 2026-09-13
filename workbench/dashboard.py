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
  const tabs=[['overview','总览'],['functions','功能'],['backtest','回测'],['multi_method','多方法对比'],['history','历史分析'],['arena','模型竞技场'],['decisions','决策审计'],['timeline','回溯时间轴'],['reports','报告']];
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
