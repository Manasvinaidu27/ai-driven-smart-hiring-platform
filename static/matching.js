const jdText = document.getElementById('jdText');
const jdFile = document.getElementById('jdFile');
const jdFileName = document.getElementById('jdFileName');
const jdMessage = document.getElementById('jdMessage');
const jdProfile = document.getElementById('jdProfile');
const analyzeJDButton = document.getElementById('analyzeJD');
let analyzedJDProfile = null;

const jdMsg = (text, type='ok') => {
  if (!jdMessage) return;
  jdMessage.textContent = text;
  jdMessage.className = `message ${type}`;
};

const escJD = v => String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
const jdChips = items => (items || []).map(x => `<span class="match-chip">${escJD(x)}</span>`).join('');

function renderJDProfile(profile){
  analyzedJDProfile = profile;
  if (!jdProfile) return;
  const qualifications = profile.qualifications || [];
  const responsibilities = profile.responsibilities || [];
  jdProfile.classList.remove('hidden');
  jdProfile.innerHTML = `
    <div class="jd-profile-head">
      <div><div class="eyebrow">STRUCTURED JOB REQUIREMENT PROFILE</div><h3>${escJD(profile.title)}</h3><p>Parser confidence: <strong>${Number(profile.confidence || 0)}%</strong> · Source: ${escJD(profile.source_name || 'Pasted text')}</p></div>
      <button type="button" class="jd-use" id="useJDProfile">Use This Profile</button>
    </div>
    <div class="jd-profile-grid">
      <div class="jd-field"><span>Required Skills</span><div class="chips">${jdChips(profile.required_skills)}</div></div>
      <div class="jd-field"><span>Minimum Experience</span><b>${Number(profile.min_experience || 0)} years</b></div>
      <div class="jd-field"><span>Education / Qualifications</span><b>${escJD(profile.education || 'Not detected')}</b></div>
      <div class="jd-field"><span>Location</span><b>${escJD(profile.location || 'Not specified')}</b></div>
      <div class="jd-field full"><span>Qualifications Extracted</span><ul>${qualifications.length ? qualifications.map(x => `<li>${escJD(x)}</li>`).join('') : '<li>No explicit qualification section detected.</li>'}</ul></div>
      <div class="jd-field full"><span>Responsibilities Extracted</span><ul>${responsibilities.length ? responsibilities.map(x => `<li>${escJD(x)}</li>`).join('') : '<li>No explicit responsibilities section detected.</li>'}</ul></div>
    </div>`;
  document.getElementById('useJDProfile')?.addEventListener('click', () => fillJobForm(profile));
}

function fillJobForm(profile){
  const set = (id, value) => { const el = document.getElementById(id); if (el) el.value = value ?? ''; };
  set('jobTitle', profile.title);
  set('jobSkills', (profile.required_skills || []).join(', '));
  set('jobExperience', profile.min_experience || 0);
  set('jobEducation', profile.education || '');
  set('jobLocation', profile.location || '');
  set('jobDescription', profile.description || '');
  document.getElementById('jobForm')?.scrollIntoView({behavior:'smooth', block:'center'});
  showJobMessage('Structured JD profile loaded into Create Job Requirement. Review it and click Create Job & Match Candidates.');
}

jdFile?.addEventListener('change', () => {
  const file = jdFile.files?.[0];
  if (file) {
    jdFileName.textContent = file.name;
    if (jdText) jdText.value = '';
  } else jdFileName.textContent = 'No file selected';
});

analyzeJDButton?.addEventListener('click', async () => {
  const file = jdFile?.files?.[0];
  const text = jdText?.value?.trim() || '';
  if (!file && !text) { jdMsg('Paste a job description or upload a PDF/DOCX file.', 'err'); return; }
  analyzeJDButton.disabled = true;
  analyzeJDButton.textContent = 'Analyzing JD...';
  jdMsg('Extracting job requirements...', 'ok');
  try {
    let response;
    if (file) {
      const form = new FormData(); form.append('file', file);
      response = await fetch('/api/jobs/analyze', {method:'POST', body:form});
    } else {
      response = await fetch('/api/jobs/analyze', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text})});
    }
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || 'Job description analysis failed.');
    renderJDProfile(data.profile);
    jdMsg(`JD analyzed successfully: ${data.profile.required_skills.length} skills, ${data.profile.min_experience || 0} years experience and ${data.profile.qualifications.length} qualification item(s) detected.`);
  } catch (err) {
    jdMsg(err.message, 'err');
  } finally {
    analyzeJDButton.disabled = false;
    analyzeJDButton.textContent = 'Analyze Job Description';
  }
});

const jobForm = document.getElementById('jobForm');
const jobMessage = document.getElementById('jobMessage');
const results = document.getElementById('results');
const resultsEmpty = document.getElementById('resultsEmpty');
const resultsTitle = document.getElementById('resultsTitle');
const gapEmpty = document.getElementById('gapEmpty');
const gapReport = document.getElementById('gapReport');
let currentJob = null;
let currentMatches = [];

const escM = v => String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
const chipM = items => (items||[]).map(x=>`<span class="match-chip">${escM(x)}</span>`).join('');
const showJobMessage = (text,type='ok') => {jobMessage.textContent=text; jobMessage.className=`message ${type}`;};

function scoreClass(score){ return score >= 80 ? 'score-high' : score >= 65 ? 'score-good' : score >= 50 ? 'score-mid' : 'score-low'; }

function renderResults(data){
  currentMatches=data.matches||[];
  currentJob=data.job;
  resultsTitle.textContent=`${data.job.title} · ${currentMatches.length} candidates`;
  resultsEmpty.classList.add('hidden');
  results.classList.remove('hidden');
  if(!currentMatches.length){ results.innerHTML='<div class="no-results">No candidate profiles are available for matching. Upload resumes first.</div>'; return; }
  results.innerHTML=currentMatches.map((m,i)=>`
    <article class="match-card">
      <div class="match-main">
        <div class="rank">#${i+1}</div>
        <div class="match-avatar">${escM((m.candidate_name||'CN').split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase())}</div>
        <div class="match-person"><h3>${escM(m.candidate_name)}</h3><small>${escM(m.candidate_email)}</small><div class="match-tags">${chipM(m.matched_skills.slice(0,6))}</div></div>
        <div class="score ${scoreClass(m.score)}"><strong>${m.score}%</strong><span>${escM(m.recommendation)}</span></div>
      </div>
      <div class="match-breakdown">
        <span>Skills <b>${m.skill_match_percent}%</b></span>
        <span>Experience <b>${m.experience.score}/25</b></span>
        <span>Education <b>${m.education.score}/10</b></span>
        <span>Location <b>${m.location.score}/5</b></span>
        <button class="gap-btn" data-index="${i}">View Skill Gap</button>
      </div>
    </article>`).join('');
  results.querySelectorAll('.gap-btn').forEach(btn=>btn.addEventListener('click',()=>showGap(Number(btn.dataset.index))));
}

async function showGap(index){
  const match=currentMatches[index];
  if(!match || !currentJob)return;
  gapEmpty.classList.add('hidden'); gapReport.classList.remove('hidden');
  const missing=match.missing_skills||[]; const matched=match.matched_skills||[];
  gapReport.innerHTML=`
    <div class="gap-header"><div><h3>${escM(match.candidate_name)}</h3><p>${escM(currentJob.title)}</p></div><div class="gap-actions"><div class="gap-score">${match.skill_match_percent}% skill coverage</div><button class="gap-download" id="downloadGap">Download Report</button></div></div>
    <p class="gap-summary">${missing.length ? `${missing.length} required skill(s) were not detected in this candidate profile.` : 'All required skills were detected in this candidate profile.'}</p>
    <div class="gap-columns">
      <div class="gap-box"><h4>✓ Matched Skills</h4><div class="match-chips">${matched.length?chipM(matched):'<span class="muted">None detected</span>'}</div></div>
      <div class="gap-box"><h4>! Skill Gaps</h4><div class="gap-chips">${missing.length?missing.map(x=>`<span>${escM(x)}</span>`).join(''):'<span class="complete">No skill gaps detected</span>'}</div></div>
    </div>`;
  document.getElementById('downloadGap')?.addEventListener('click',()=>{
    const report={
      candidate:match.candidate_name,
      email:match.candidate_email,
      job:currentJob.title,
      hiring_score:match.score,
      recommendation:match.recommendation,
      required_skills:currentJob.required_skills,
      matched_skills:match.matched_skills,
      missing_skills:match.missing_skills,
      skill_coverage_percent:match.skill_match_percent,
      score_breakdown:match
    };
    const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob); const a=document.createElement('a');
    a.href=url; a.download=`${(match.candidate_name||'candidate').replace(/\s+/g,'_')}_${(currentJob.title||'job').replace(/\s+/g,'_')}_skill_gap.json`; a.click(); URL.revokeObjectURL(url);
  });
  gapReport.scrollIntoView({behavior:'smooth',block:'nearest'});
}

jobForm?.addEventListener('submit',async e=>{
  e.preventDefault();
  const button=document.getElementById('createJob'); button.disabled=true; button.textContent='Matching candidates...';
  const payload={
    title:document.getElementById('jobTitle').value.trim(),
    required_skills:document.getElementById('jobSkills').value.split(/[,;|\n]+/).map(x=>x.trim()).filter(Boolean),
    min_experience:Number(document.getElementById('jobExperience').value||0),
    education:document.getElementById('jobEducation').value.trim(),
    location:document.getElementById('jobLocation').value.trim(),
    description:document.getElementById('jobDescription').value.trim()
  };
  try{
    const response=await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await response.json();
    if(!response.ok||!data.success) throw new Error(data.error||'Could not create job.');
    renderResults(data); showJobMessage(`Job created and ${data.matches.length} candidates ranked successfully.`);
    gapEmpty.classList.remove('hidden'); gapReport.classList.add('hidden');
  }catch(err){showJobMessage(err.message,'err');}
  finally{button.disabled=false;button.textContent='Create Job & Match Candidates';}
});
