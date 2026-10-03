const jobSelect=document.getElementById('jobSelect');
const gapResult=document.getElementById('gapResult');
const esc2=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
jobSelect?.addEventListener('change',async()=>{
 const id=jobSelect.value;if(!id){gapResult.innerHTML='<div class="empty"><div>◎</div><h3>Choose a job posting</h3><p>Your skill gap bar graph will appear here.</p></div>';return;}
 gapResult.innerHTML='<div class="loading-box">Analysing job requirements…</div>';
 try{const r=await fetch(`/api/jobs/${id}/skill-gap/${window.CANDIDATE_INDEX}`);const j=await r.json();if(!r.ok||!j.success)throw Error(j.error||'Unable to analyse');const x=j.report;
 const matched=x.matched_skills.length, missing=x.missing_skills.length, total=Math.max(matched+missing,1), m=Math.round(matched/total*100), g=Math.round(missing/total*100);
 gapResult.innerHTML=`<div class="gap-dashboard"><div class="gap-metric"><span>Skill coverage</span><strong>${x.skill_coverage}%</strong><i><em style="width:${x.skill_coverage}%"></em></i></div><div class="bar-chart"><div class="bar-group"><span>Matched</span><div class="bar"><i style="height:${m}%"></i></div><b>${matched}</b></div><div class="bar-group"><span>Missing</span><div class="bar"><i style="height:${g}%"></i></div><b>${missing}</b></div></div><div class="gap-columns"><div class="gap-box"><h4>✓ Matched skills</h4><div class="gap-chips">${x.matched_skills.length?x.matched_skills.map(s=>`<span class="complete">${esc2(s)}</span>`).join(''):'<span class="complete">None detected</span>'}</div></div><div class="gap-box"><h4>! Missing skills</h4><div class="gap-chips">${x.missing_skills.length?x.missing_skills.map(s=>`<span>${esc2(s)}</span>`).join(''):'<span class="complete">No gaps detected</span>'}</div></div></div></div>`;
 }catch(e){gapResult.innerHTML=`<div class="empty"><h3>Analysis unavailable</h3><p>${esc2(e.message)}</p></div>`;}
});
