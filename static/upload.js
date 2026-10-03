const input = document.getElementById('resumeInput');
const dropZone = document.getElementById('dropZone');
const filePreview = document.getElementById('filePreview');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const removeFile = document.getElementById('removeFile');
const parseButton = document.getElementById('parseButton');
const buttonText = document.getElementById('buttonText');
const loader = document.getElementById('loader');
const message = document.getElementById('message');
const emptyProfile = document.getElementById('emptyProfile');
const profileContent = document.getElementById('profileContent');
const downloadButton = document.getElementById('downloadButton');
let selectedFile = null;
let latestProfile = null;
let latestCandidateIndex = null;

const esc = v => String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
const sizeText = n => n < 1024 ? `${n} B` : n < 1048576 ? `${(n/1024).toFixed(1)} KB` : `${(n/1048576).toFixed(2)} MB`;
const showMessage = (t, type='ok') => { message.textContent=t; message.className=`message ${type}`; };

function setProgress(percent){
  const ids=['step1','step2','step3','step4'];
  ids.forEach((id,i)=>document.getElementById(id)?.classList.toggle('done', percent >= (i+1)*25));
  document.getElementById('progressStatus').textContent = percent >= 100 ? 'Completed' : percent ? 'Processing' : 'Waiting';
}
function selectFile(file){
  if(!file) return;
  const ext=file.name.toLowerCase().split('.').pop();
  if(!['pdf','docx'].includes(ext)){showMessage('Only PDF and DOCX files are supported.','err');return;}
  if(file.size>10*1024*1024){showMessage('Maximum file size is 10 MB.','err');return;}
  selectedFile=file; fileName.textContent=file.name; fileSize.textContent=sizeText(file.size);
  filePreview.classList.remove('hidden'); parseButton.disabled=false; setProgress(25); showMessage('Resume selected. Click Parse Resume.');
}
input?.addEventListener('change',()=>selectFile(input.files[0]));
['dragenter','dragover'].forEach(e=>dropZone?.addEventListener(e,x=>{x.preventDefault();dropZone.classList.add('drag');}));
['dragleave','drop'].forEach(e=>dropZone?.addEventListener(e,x=>{x.preventDefault();dropZone.classList.remove('drag');}));
dropZone?.addEventListener('drop',e=>selectFile(e.dataTransfer.files[0]));
removeFile?.addEventListener('click',()=>{selectedFile=null;input.value='';filePreview.classList.add('hidden');parseButton.disabled=true;setProgress(0);message.className='message hidden';});

function list(items, empty='Not detected'){return items?.length ? items.map(x=>`<p>${esc(x)}</p>`).join('') : `<p class="muted">${empty}</p>`;}
function initials(name){return name && name!=='Not detected' ? name.split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase() : 'CN';}
function renderProfile(p){
  latestProfile=p; emptyProfile.classList.add('hidden'); profileContent.classList.remove('hidden'); downloadButton.disabled=false;
  document.getElementById('avatar').textContent=initials(p.name);
  document.getElementById('candidateName').textContent=p.name;
  document.getElementById('candidateLocation').textContent=p.location || 'Not detected';
  document.getElementById('candidateEmail').textContent=p.email || 'Not detected';
  document.getElementById('candidatePhone').textContent=p.phone || 'Not detected';
  document.getElementById('education').innerHTML=list(p.education);
  const exp=p.experience||{};
  const professional = exp.roles?.length
    ? list(exp.roles, 'No professional experience role detected')
    : '<p class="muted">Professional experience not detected</p>';
  const details = (exp.details||[]).filter(x => !(exp.roles||[]).some(r => r.toLowerCase() === x.toLowerCase()));
  const detailHtml = details.length ? list(details) : '';
  const hasProfessional = Boolean(exp.roles?.length || exp.details?.length);
  let experienceHtml = '';
  if (hasProfessional) {
    experienceHtml += `<p><b>${esc(exp.total_experience || 'Experience detected')}</b></p>${professional}${detailHtml}`;
  } else {
    experienceHtml += '<p class="muted">Professional experience not detected</p>';
  }
  if (exp.internships?.length) {
    experienceHtml += '<p><b>Internships</b></p>' + list(exp.internships);
  }
  if (!hasProfessional && !exp.internships?.length) {
    experienceHtml = '<p class="muted">Not detected</p>';
  }
  document.getElementById('experience').innerHTML=experienceHtml;
  document.getElementById('skills').innerHTML=p.skills?.length ? p.skills.map(x=>`<span>${esc(x)}</span>`).join('') : '<span>Not detected</span>';
  document.getElementById('certifications').innerHTML=list(p.certifications);
  document.getElementById('projects').innerHTML=list(p.projects);
  document.getElementById('languages').innerHTML=list(p.languages);
  document.getElementById('rawText').textContent=p.raw_text_preview || 'No text preview available.';
  const fields=[p.name,p.email,p.phone,p.location,p.education?.length,p.skills?.length,exp.roles?.length||exp.internships?.length,p.certifications?.length,p.projects?.length];
  document.getElementById('statFields').textContent=fields.filter(x=>x && x!=='Not detected').length;
  document.getElementById('statSkills').textContent=p.skills?.length||0;
  document.getElementById('statExperience').textContent=exp.total_experience || ((exp.roles?.length || exp.details?.length || exp.internships?.length) ? 'Detected' : '—');
  document.getElementById('statConfidence').textContent=`${p.confidence||0}%`;
}

parseButton?.addEventListener('click',async()=>{
  if(!selectedFile)return;
  parseButton.disabled=true; buttonText.textContent='Parsing resume...'; loader.classList.remove('hidden'); setProgress(50); showMessage('Extracting text and structured information...');
  const form=new FormData(); form.append('resume',selectedFile);
  try{
    const response=await fetch('/api/parse',{method:'POST',body:form});
    const result=await response.json(); if(!response.ok||!result.success) throw new Error(result.error||'Parsing failed.');
    setProgress(100); latestCandidateIndex=result.candidate_index; renderProfile(result.profile); showMessage('Resume parsed successfully.');
    const actions=document.getElementById('profileActions'); if(actions){actions.innerHTML=`<a class="new-job-btn" href="/candidate-dashboard/${result.candidate_index}">Open Candidate Dashboard</a><a class="new-job-btn" href="${result.report_url}">View Analysis Report</a><a class="export-btn" href="${result.report_download_url}">⇩ Download PDF Report</a>`;}
  }catch(err){setProgress(25);showMessage(err.message,'err');}
  finally{parseButton.disabled=false;buttonText.textContent='✦ Parse Resume';loader.classList.add('hidden');}
});

downloadButton?.addEventListener('click',()=>{
  if(!latestProfile)return;
  if(latestCandidateIndex!==null){window.location.href=`/api/profile/${latestCandidateIndex}/report`;return;} const blob=new Blob([JSON.stringify(latestProfile,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download=`${(latestProfile.name||'candidate').replace(/\s+/g,'_')}_profile.json`; a.click(); URL.revokeObjectURL(url);
});
