import {esc,stamp,minute} from '../utils.js';
import {LABELS,BANDS,SOURCES,CASE_STATES,SUSPENSION_STATES,QUARANTINE_STATES} from '../constants.js';
export const badge=s=>`<span class="badge ${esc(s)}">${esc(LABELS[s]||s)}</span>`;
export const quarantineBadge=s=>`<span class="badge q-${esc(s)}">${esc(QUARANTINE_STATES[s]||s)}</span>`;
export const suspensionBadge=s=>`<span class="badge sus-${esc(s)}">${esc(SUSPENSION_STATES[s]||s)}</span>`;
export const empty=(title,action)=>`<div class="empty"><span>待办 / NEXT</span><h3>${esc(title)}</h3><p>${esc(action)}</p></div>`;
export const caseRibbon=c=>c?`<div class="case-ribbon"><div class="case-id">${esc(c.code)}</div><div><strong>${esc(c.alias)} · ${esc(c.building)}</strong><p>${esc(c.summary)}</p></div><div>${badge(c.status)}<small>监测授权 · ${c.consent?'已取得':'未取得 / 已撤回'}</small></div></div>`:empty('先建立匿名投诉','在收件页填写楼栋、别名和问题，不收集住户真实姓名。');
export const flow=c=>`<div class="flow-strip">${CASE_STATES.map((x,i)=>`<span class="${c?.status===x?'here':''}"><b>0${i+1}</b>${LABELS[x]}</span>`).join('')}</div>`;
export const note=(title,text)=>`<aside class="margin-note"><strong>${esc(title)}</strong><p>${esc(text)}</p></aside>`;
export const agreementRibbon=a=>a?`<div class="agreement-ribbon"><b>协议 QTA-${a.id}</b>${badge(a.state)}<span>${esc(a.party_a)} ↔ ${esc(a.party_b)}</span><span>静音 ${minute(a.quiet_from)} — ${minute(a.quiet_to)}</span><span>能量阈值 ${a.threshold}</span></div>`:empty('尚无调解协议','先在成分归因页登记人工证据，再由主管起草。');
export const bandBars=events=>`<div class="band-profile">${BANDS.map((b,i)=>{const n=events.length?events.reduce((s,e)=>s+e.energies[i],0)/events.length:0;return `<div><label>${b}</label><span style="width:${Math.min(100,n*7)}%"></span><small>${n.toFixed(2)}</small></div>`}).join('')}</div>`;
export const sourceComposition=weights=>`<div class="source-line">${Object.entries(weights).map(([s,n])=>`<span style="flex:${Math.max(.02,n)}" class="source-${s}" title="${SOURCES[s]} ${(n*100).toFixed(1)}%">${SOURCES[s]} ${(n*100).toFixed(0)}%</span>`).join('')}</div>`;
export const suspensionPanel=(suspensions,events)=>{
  if(!suspensions?.length)return empty('暂无停用时段','各测点正常采样的重构误差持续偏离基线时，会从首次异常起自动停用该时段采样。');
  const evById=Object.fromEntries(events.map(e=>[e.id,e]));
  return `<div class="suspension-list">${suspensions.map(s=>`<article class="suspension-card sus-border-${esc(s.state)}">
    <div class="suspension-head"><b>停用 QSS-${s.id} · ${esc(s.position)}</b>${suspensionBadge(s.state)}${s.reopened_from_id?`<small>续接 QSS-${s.reopened_from_id}</small>`:''}</div>
    <p class="subtle">${esc(s.reason)}</p>
    <div class="suspension-meta"><span>停用起 <b>${stamp(s.suspended_from)}</b></span><span>放行 <b>${stamp(s.released_at)}</b></span><span>基线切点 <b>${s.cutoff.toFixed(4)}</b></span></div>
    <div class="suspension-events">${s.events.map(x=>{const e=evById[x.event_id];return `<div class="q-row"><span>#${x.event_id}${e?` · ${stamp(e.measured_at)}`:''}</span>${quarantineBadge(x.state)}<small>重构误差 ${x.reconstruction_error.toFixed(4)}</small></div>`}).join('')}</div>
    ${s.requalifications.length?`<div class="recheck-chain"><b>复测记录</b>${s.requalifications.map(r=>`<div class="q-row"><span>复测 #${r.id} · ${r.passed?'达标':'未达标'}</span><small>${stamp(r.created_at)}</small><span>${r.event_ids.length} 条 / 切点 ${r.cutoff.toFixed(4)}</span></div>`).join('')}</div>`:''}
    ${s.affected_attribution_ids.length?`<p class="inline-warn">受影响归因：${s.affected_attribution_ids.map(i=>`#${i}`).join('、')}（${s.state==='active'?'在途停用，暂停引用':'历史停用链，可追溯'}）</p>`:''}
  </article>`).join('')}</div>`;
};
