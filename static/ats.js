(function(){
"use strict";
const msg=(id,text,ok=true)=>{const e=document.getElementById(id);if(!e)return;e.className=`message ${ok?'ok':'err'}`;e.textContent=text};
const esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
const chip=items=>(items||[]).map(x=>`<span class="match-chip">${esc(x)}</span>`).join('');
const scoreClass=s=>s>=80?'score-high':s>=65?'score-good':s>=50?'score-mid':'score-low';
let currentMatches=[];let currentJob=null;let selectedIndexes=new Set();

function renderResults(data){
 currentMatches=data.matches||[]; currentJob=data.job; selectedIndexes=new Set();
 document.getElementById('atsResultsTitle').textContent=`${data.job.title} · ${currentMatches.length} candidates`;
 document.getElementById('atsResultsSubtitle').textContent='ATS Score and Match Score are calculated independently.';
 document.getElementById('screeningCount').textContent=`${currentMatches.length} candidates`;
 const box=document.getElementById('atsResults');
 if(!currentMatches.length){box.innerHTML='<div class="interview-empty"><h3>No candidate profiles yet</h3><p>Upload resumes first.</p></div>';return;}
 box.innerHTML=currentMatches.map((m,i)=>{const a=m.ats||{};return `
 <article class="ats-candidate-row">
  <div class="select-cell"><input type="checkbox" class="screen-check" data-index="${m.candidate_index}" aria-label="Select ${esc(m.candidate_name)}"></div>
  <div class="candidate-rank">#${i+1}</div>
  <div class="ats-avatar">${esc((m.candidate_name||'CN').split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase())}</div>
  <div class="ats-candidate-main"><h3>${esc(m.candidate_name)}</h3><small>${esc(m.candidate_email)}</small><div class="match-tags">${chip(m.matched_skills.slice(0,5))}</div></div>
  <div class="dual-score"><div class="mini-score ${scoreClass(a.score)}"><span>ATS SCORE</span><strong>${a.score}%</strong><em>${esc(a.status||'')}</em></div><div class="mini-score ${scoreClass(m.score)}"><span>MATCH SCORE</span><strong>${m.score}%</strong><em>${esc(m.recommendation||'')}</em></div></div>
  <button class="view-score-btn" data-index="${i}">View Analysis</button>
 </article>`}).join('');
 box.querySelectorAll('.screen-check').forEach(c=>c.addEventListener('change',()=>{const i=Number(c.dataset.index);if(c.checked)selectedIndexes.add(i);else selectedIndexes.delete(i)}));
 box.querySelectorAll('.view-score-btn').forEach(b=>b.addEventListener('click',()=>showAnalysis(Number(b.dataset.index))));
 showAnalysis(0);
}

function showAnalysis(i){
 const m=currentMatches[i]; if(!m)return; const a=m.ats||{}; const d=document.getElementById('atsDetail');
 const sectionRows=Object.entries(a.section_checks||{}).map(([k,v])=>`<div class="check-row"><span>${esc(k)}</span><b class="${v?'pass':'miss'}">${v?'Detected':'Missing'}</b></div>`).join('');
 d.innerHTML=`<div class="analysis-head"><div><div class="eyebrow">CANDIDATE ANALYSIS</div><h2>${esc(m.candidate_name)}</h2><p>${esc(currentJob.title)} · ${esc(m.candidate_email)}</p></div><div class="analysis-score-pair"><div><span>ATS</span><strong class="${scoreClass(a.score)}">${a.score}%</strong></div><div><span>MATCH</span><strong class="${scoreClass(m.score)}">${m.score}%</strong></div></div></div>
 <div class="analysis-grid">
  <div class="analysis-panel"><h3>ATS Score Breakdown</h3><div class="metric-line"><span>Job keywords</span><b>${a.keyword_score||0}/50</b></div><div class="metric-line"><span>Resume structure</span><b>${a.resume_structure_score||0}/20</b></div><div class="metric-line"><span>Parser confidence</span><b>${a.parser_score||0}/15</b></div><div class="metric-line"><span>Resume completeness</span><b>${Math.max(0,(a.score-(a.keyword_score||0)-(a.resume_structure_score||0)-(a.parser_score||0))).toFixed(1)}/15</b></div></div>
  <div class="analysis-panel"><h3>Match Score Breakdown</h3><div class="metric-line"><span>Skills</span><b>${m.skill_match_percent}%</b></div><div class="metric-line"><span>Experience</span><b>${m.experience.score}/25</b></div><div class="metric-line"><span>Education</span><b>${m.education.score}/10</b></div><div class="metric-line"><span>Location</span><b>${m.location.score}/5</b></div></div>
  <div class="analysis-panel"><h3>ATS Resume Checks</h3>${sectionRows}</div>
  <div class="analysis-panel"><h3>Skills & Gaps</h3><p class="label-sm">Matched</p><div class="match-chips">${chip(m.matched_skills)}</div><p class="label-sm gap-label">Missing</p><div class="gap-chips">${(m.missing_skills||[]).length?m.missing_skills.map(x=>`<span>${esc(x)}</span>`).join(''):'<span class="complete">No required skill gaps</span>'}</div></div>
 </div>`;
 d.scrollIntoView({behavior:'smooth',block:'nearest'});
}

async function loadScreening(){
 const id=document.getElementById('atsJobSelect').value;if(!id)return;
 const box=document.getElementById('atsResults');box.innerHTML='<div class="interview-empty"><h3>Calculating scores…</h3><p>Parsing candidate profiles against the selected role.</p></div>';
 try{const r=await fetch(`/api/jobs/${id}/matches`);const j=await r.json();if(!r.ok||!j.success)throw Error(j.error||'Unable to calculate scores');renderResults(j);}catch(e){box.innerHTML=`<div class="interview-empty"><h3>Unable to screen candidates</h3><p>${esc(e.message)}</p></div>`;}
}

document.getElementById('atsJobSelect')?.addEventListener('change',loadScreening);
if(document.getElementById('atsJobSelect')?.value)loadScreening();

document.getElementById('saveAts')?.addEventListener('click',async()=>{const payload={provider:document.getElementById('atsProvider').value,base_url:document.getElementById('atsBaseUrl').value,api_key:document.getElementById('atsApiKey').value};try{const r=await fetch('/api/ats/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const j=await r.json();msg('atsMsg',j.success?'ATS connection settings saved.':j.error||'Unable to save.',j.success)}catch(e){msg('atsMsg',e.message,false)}});
document.getElementById('testAts')?.addEventListener('click',async()=>{try{const r=await fetch('/api/ats/test',{method:'POST'});const j=await r.json();msg('atsMsg',j.status||'Test failed.',j.success)}catch(e){msg('atsMsg',e.message,false)}});
document.getElementById('syncAts')?.addEventListener('click',async()=>{const ids=[...selectedIndexes];if(!ids.length){msg('syncMsg','Select at least one candidate from the screening list.',false);return}try{const r=await fetch('/api/ats/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate_indexes:ids,job_title:currentJob?.title||''})});const j=await r.json();msg('syncMsg',j.status||j.error||'Sync failed.',j.success)}catch(e){msg('syncMsg',e.message,false)}});


// Refresh the built-in Demo ATS status after a successful sync.
document.getElementById('syncAts')?.addEventListener('click',async()=>{
  setTimeout(async()=>{
    try{
      const r=await fetch('/api/ats/demo/candidates');
      const j=await r.json();
      const el=document.getElementById('demoCount');
      if(el && j.success) el.textContent=`${(j.candidates||[]).length} stored in Demo ATS`;
    }catch(_e){}
  },300);
});

// Full ATS candidate-management workflow: retrieve, sync, de-duplicate and update status.
const ATS_STATUSES=['New','Screening','Interview Scheduled','Interviewed','Shortlisted','Rejected','Hired','On Hold'];
function atsManagementMsg(text,ok=true){msg('atsManagementMsg',text,ok)}
function renderAtsManagement(rows,mode='demo'){
  const body=document.getElementById('atsManagementBody');
  const summary=document.getElementById('atsManagementSummary');
  const badge=document.getElementById('atsProviderBadge');
  if(badge){badge.textContent=mode==='external'?'External ATS':'Demo ATS';badge.className=`ats-provider-badge ${mode==='external'?'external':''}`}
  if(summary) summary.textContent=`${rows.length} candidate(s) currently stored in ${mode==='external'?'External ATS':'Demo ATS'}`;
  if(!rows.length){body.innerHTML='<tr><td colspan="5">No candidates have been synced to the ATS yet.</td></tr>';return;}
  body.innerHTML=rows.map((c,i)=>{const status=ATS_STATUSES.includes(c.status)?c.status:'New';return `<tr>
    <td><b>${esc(c.name||'Candidate')}</b></td><td>${esc(c.email||'')}</td><td>${esc(c.job_applied||'—')}</td>
    <td><select class="ats-status-select" data-email="${esc(c.email||'')}" data-old="${esc(status)}">${ATS_STATUSES.map(x=>`<option ${x===status?'selected':''}>${x}</option>`).join('')}</select><span class="ats-status-saved" data-saved="${esc(c.email||'')}"></span></td>
    <td>${esc(c.updated_at||c.synced_at||c.created_at||'—')}</td></tr>`}).join('');
  body.querySelectorAll('.ats-status-select').forEach(sel=>sel.addEventListener('change',async()=>{
    const email=sel.dataset.email, status=sel.value, old=sel.dataset.old;
    sel.disabled=true;
    try{const r=await fetch(`/api/ats/candidates/${encodeURIComponent(email)}/status`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});const j=await r.json();if(!r.ok||!j.success)throw Error(j.error||'Status update failed');sel.dataset.old=status;const saved=body.querySelector(`[data-saved="${CSS.escape(email)}"]`);if(saved){saved.textContent='Saved';setTimeout(()=>saved.textContent='',1200)}
    }catch(e){sel.value=old;atsManagementMsg(e.message,false)}finally{sel.disabled=false}
  }));
}
async function refreshAtsManagement(){
  try{
    const r=await fetch('/api/ats/candidates',{headers:{'Accept':'application/json'},cache:'no-store'});
    const j=await r.json();
    if(!r.ok||!j.success)throw Error(j.error||'Unable to retrieve ATS candidates');
    let rows=Array.isArray(j.candidates)?j.candidates:[];
    const mode=j.mode||'demo';
    if(mode==='demo' && rows.length===0){
      const dr=await fetch('/api/ats/demo/candidates',{headers:{'Accept':'application/json'},cache:'no-store'});
      const dj=await dr.json();
      if(dr.ok && dj.success && Array.isArray(dj.candidates)) rows=dj.candidates;
    }
    renderAtsManagement(rows,mode);
    atsManagementMsg('ATS candidate records loaded.',true);
  }catch(e){
    document.getElementById('atsManagementSummary').textContent='ATS connection unavailable';
    atsManagementMsg(e.message,false);
  }
}
async function loadAtsManagementConfig(){
  try{const r=await fetch('/api/ats/config');const j=await r.json();document.getElementById('managementProvider').value=j.provider||'Demo ATS';document.getElementById('managementBaseUrl').value=j.base_url||'';document.getElementById('managementApiKey').value='';}catch(_e){}
}
document.getElementById('refreshAtsCandidates')?.addEventListener('click',refreshAtsManagement);
document.getElementById('saveManagementConfig')?.addEventListener('click',async()=>{
 const payload={provider:document.getElementById('managementProvider').value,base_url:document.getElementById('managementBaseUrl').value,api_key:document.getElementById('managementApiKey').value};
 try{const r=await fetch('/api/ats/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const j=await r.json();if(!r.ok||!j.success)throw Error(j.error||'Unable to save ATS configuration');atsManagementMsg('ATS API configuration saved successfully.',true);await refreshAtsManagement();}catch(e){atsManagementMsg(e.message,false)}
});
document.getElementById('syncAllAts')?.addEventListener('click',async()=>{
 const checked=[...document.querySelectorAll('.mini-ats-check:checked')];
 if(!checked.length){atsManagementMsg('Select candidate(s) in the Candidate Management section above before syncing.',false);return;}
 try{const r=await fetch('/api/ats/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate_indexes:checked.map(x=>Number(x.value)),candidate_ids:checked.map(x=>x.dataset.candidateId).filter(Boolean),candidate_emails:checked.map(x=>x.dataset.email).filter(Boolean),job_title:document.getElementById('interviewJob')?.selectedOptions?.[0]?.text||'Interview Candidate'})});const j=await r.json();if(!r.ok||!j.success)throw Error(j.error||'ATS sync failed');atsManagementMsg(j.status||'Candidates synchronized successfully.',true);await refreshAtsManagement();}catch(e){atsManagementMsg(e.message,false)}
});
// Interview-page mini ATS controls. These handlers are kept in this file so ATS behavior
// is isolated from the interview simulator and cannot be blocked by duplicate global names.
async function miniAtsHealth(){
  const status=document.getElementById('atsConnectionStatus');
  const count=document.getElementById('demoAtsCount');
  const r=await fetch('/api/ats/demo/health',{headers:{'Accept':'application/json'},cache:'no-store'});
  const j=await r.json();
  if(!r.ok||!j.success) throw new Error(j.error||`Demo ATS unavailable (HTTP ${r.status})`);
  if(status){status.textContent='Connected';status.parentElement?.classList.remove('error');}
  if(count) count.textContent=`Demo ATS: ${j.count} candidate${j.count===1?'':'s'} stored`;
  return j;
}
async function miniAtsRefresh(){
  const r=await fetch('/api/ats/demo/candidates',{headers:{'Accept':'application/json'},cache:'no-store'});
  const j=await r.json();
  if(!r.ok||!j.success) throw new Error(j.error||`Unable to load Demo ATS (HTTP ${r.status})`);
  const rows=Array.isArray(j.candidates)?j.candidates:[];
  const byEmail=new Map(rows.map(x=>[String(x.email||'').trim().toLowerCase(),x]));
  document.querySelectorAll('.ats-mini-candidate').forEach(card=>{
    const email=(card.dataset.email || card.querySelector('.mini-candidate-info small')?.textContent || '').trim().toLowerCase();
    const info=byEmail.get(email);
    let state=card.querySelector('.ats-mini-status');
    if(!state){state=document.createElement('em');state.className='ats-mini-status';card.querySelector('.mini-candidate-info')?.appendChild(state);}
    state.textContent=info?.status||'Ready for ATS';
    state.classList.toggle('synced-status',!!info); card.classList.toggle('synced',!!info);
  });
  const count=document.getElementById('demoAtsCount');
  if(count) count.textContent=`Demo ATS: ${rows.length} candidate${rows.length===1?'':'s'} stored`;
  return rows;
}
async function miniAtsSync(){
  const checks=[...document.querySelectorAll('.mini-ats-check:checked')];
  if(!checks.length) throw new Error('Select at least one candidate to sync.');
  const selectedJob=document.getElementById('interviewJob')?.selectedOptions?.[0]?.text || 'Interview Candidate';
  const payload={
    candidate_indexes:checks.map(x=>Number(x.value)),
    candidate_emails:checks.map(x=>x.dataset.email||'').filter(Boolean),
    candidate_ids:checks.map(x=>x.dataset.candidateId||'').filter(Boolean),
    job_title:selectedJob
  };
  const r=await fetch('/api/ats/sync',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},cache:'no-store',body:JSON.stringify(payload)});
  const j=await r.json();
  if(!r.ok||!j.success) throw new Error(j.error||`ATS synchronization failed (HTTP ${r.status})`);
  checks.forEach(x=>{x.checked=false;const card=x.closest('.ats-mini-candidate');if(card){card.classList.add('synced');let state=card.querySelector('.ats-mini-status');if(!state){state=document.createElement('em');state.className='ats-mini-status';card.querySelector('.mini-candidate-info')?.appendChild(state);}state.textContent='Synced to ATS';state.classList.add('synced-status');}});
  await miniAtsRefresh();
  return j;
}
function bindMiniAts(){
  const refresh=document.getElementById('refreshMiniAts');
  const test=document.getElementById('testMiniAts');
  const sync=document.getElementById('syncMiniAts');
  refresh?.addEventListener('click',async()=>{
    refresh.disabled=true; refresh.textContent='Refreshing…';
    try{await miniAtsRefresh();await miniAtsHealth();msg('miniAtsMsg','ATS candidates refreshed successfully.',true);}
    catch(e){msg('miniAtsMsg',e.message,false);}
    finally{refresh.disabled=false;refresh.textContent='Refresh';}
  });
  test?.addEventListener('click',async()=>{
    test.disabled=true;test.textContent='Testing…';
    try{const j=await miniAtsHealth();msg('miniAtsMsg',j.status||'Demo ATS connection successful.',true);}
    catch(e){msg('miniAtsMsg',e.message,false);}
    finally{test.disabled=false;test.textContent='Test Connection';}
  });
  sync?.addEventListener('click',async()=>{
    sync.disabled=true;sync.textContent='Syncing…';
    try{const j=await miniAtsSync();msg('miniAtsMsg',j.status||'Candidates synchronized successfully.',true);}
    catch(e){msg('miniAtsMsg',e.message,false);}
    finally{sync.disabled=false;sync.textContent='Sync Selected Candidates';}
  });
  // Show a real connection state immediately instead of leaving "Checking…" indefinitely.
  miniAtsHealth().catch(e=>{const status=document.getElementById('atsConnectionStatus');if(status)status.textContent='Connection error';const count=document.getElementById('demoAtsCount');if(count)count.textContent='Demo ATS: connection error';});
  miniAtsRefresh().catch(()=>{});
}
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',bindMiniAts,{once:true}); else bindMiniAts();

loadAtsManagementConfig();refreshAtsManagement();

})();
