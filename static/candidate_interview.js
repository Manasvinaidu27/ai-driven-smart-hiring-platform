const $c = id => document.getElementById(id);
let practiceQuestions = [];
let practiceAnswers = [];
let practiceIndex = 0;
let practiceJob = null;

function practiceMessage(text, type = 'err') {
  const box = $c('practiceSetupMsg');
  if (!box) return;
  box.className = `message ${type}`;
  box.textContent = text;
  box.classList.remove('hidden');
}
function updateWordCount() {
  const value = $c('practiceAnswer')?.value || '';
  const n = (value.trim().match(/\S+/g) || []).length;
  if ($c('practiceWordCount')) $c('practiceWordCount').textContent = `${n} words`;
}
$c('practiceAnswer')?.addEventListener('input', updateWordCount);

$c('startPractice')?.addEventListener('click', async () => {
  const id = $c('candidateJob')?.value;
  if (!id) return practiceMessage('Select a job role first.');
  const button = $c('startPractice'); button.disabled = true; button.textContent = 'Loading 40 Questions…';
  try {
    const response = await fetch(`/api/candidate-interview/questions/${encodeURIComponent(id)}?v=40`, {cache:'no-store',headers:{'Accept':'application/json'}});
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || 'Unable to load the 40 questions.');
    if (!Array.isArray(data.questions) || data.questions.length !== 40) throw new Error(`Expected 40 questions, received ${data.questions?.length || 0}.`);
    if (data.questions.filter(q => q.type === 'descriptive').length !== 20 || data.questions.filter(q => q.type === 'mcq').length !== 20) throw new Error('The exam must contain exactly 20 descriptive questions and 20 MCQs.');
    practiceQuestions=data.questions; practiceAnswers=new Array(40).fill(''); practiceIndex=0; practiceJob=data.job;
    $c('practiceTitle').textContent=`${practiceJob.title} · 40 Questions`;
    $c('practiceSub').textContent='20 descriptive questions + 20 MCQs. These are the same questions used in the Recruiter Portal.';
    $c('practiceEmpty').classList.add('hidden'); $c('practiceResult').classList.add('hidden'); $c('practiceArea').classList.remove('hidden'); $c('practiceSetupMsg')?.classList.add('hidden');
    renderPracticeQuestion();
  } catch(e){ console.error(e); practiceMessage(e.message || 'Could not load questions.'); }
  finally { button.disabled=false; button.textContent='Load 40 Questions →'; }
});

function renderPracticeQuestion(){
  const q=practiceQuestions[practiceIndex]; if(!q)return;
  $c('practiceCount').textContent=`${practiceIndex+1} / ${practiceQuestions.length}`;
  $c('practiceType').textContent=String(q.type||'DESCRIPTIVE').toUpperCase();
  $c('practiceQuestion').textContent=q.question||'';
  const textarea=$c('practiceAnswer'), mcq=$c('practiceMcqOptions');
  if(q.type==='mcq'){
    textarea.classList.add('hidden'); mcq.classList.remove('hidden');
    mcq.innerHTML=(q.options||[]).map((opt,i)=>`<label class="mcq-option"><input type="radio" name="candidateMcq" value="${escapeHtml(opt)}" ${practiceAnswers[practiceIndex]===opt?'checked':''}><span>${String.fromCharCode(65+i)}. ${escapeHtml(opt)}</span></label>`).join('');
    mcq.querySelectorAll('input').forEach(r=>r.addEventListener('change',()=>{practiceAnswers[practiceIndex]=r.value;}));
  } else {
    mcq.classList.add('hidden'); mcq.innerHTML=''; textarea.classList.remove('hidden'); textarea.value=practiceAnswers[practiceIndex]||''; updateWordCount();
  }
  $c('practiceNext').textContent=practiceIndex===practiceQuestions.length-1?'Submit 40 Questions ✓':'Next Question →';
}

$c('practiceNext')?.addEventListener('click', async()=>{
  const q=practiceQuestions[practiceIndex];
  if(q?.type==='descriptive') practiceAnswers[practiceIndex]=$c('practiceAnswer').value.trim();
  if(!practiceAnswers[practiceIndex]) return practiceMessage('Please answer/select an answer before continuing.');
  if(practiceIndex<practiceQuestions.length-1){practiceIndex++;practiceMessage('', 'ok');$c('practiceSetupMsg')?.classList.add('hidden');renderPracticeQuestion();return;}
  const button=$c('practiceNext');button.disabled=true;button.textContent='Calculating Final Score…';
  try{
    const response=await fetch('/api/candidate-interview/submit',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({job_id:practiceJob.id,answers:practiceAnswers})});
    const data=await response.json(); if(!response.ok||!data.success)throw new Error(data.error||'Unable to calculate score.'); showPracticeResult(data);
  }catch(e){practiceMessage(e.message||'Could not submit exam.');}finally{button.disabled=false;button.textContent='Submit 40 Questions ✓';}
});
function showPracticeResult(data){
  $c('practiceArea').classList.add('hidden');$c('practiceEmpty').classList.add('hidden');$c('practiceResult').classList.remove('hidden');
  $c('practiceTitle').textContent=`${data.job.title} · Final Result`; $c('practiceSub').textContent=`${data.answered} of ${data.total_questions} questions answered.`;$c('practiceCount').textContent=`${data.total_questions} / ${data.total_questions}`;
  const rows=(data.results||[]).map((r,i)=>`<div class="practice-result-row"><div><b>Question ${i+1}</b><span>${r.answered?'Answered':'Not answered'}</span></div><strong>${r.score}/100</strong><p>${(r.feedback||[]).map(escapeHtml).join(' ')}</p></div>`).join('');
  const strengths=(data.strengths||[]).map(x=>`<li>${escapeHtml(x)}</li>`).join(''), improvements=(data.improvements||[]).map(x=>`<li>${escapeHtml(x)}</li>`).join('');
  $c('practiceResult').innerHTML=`<div class="practice-score-card"><div class="eyebrow">FINAL SCORE · ${escapeHtml(String(data.evaluation_mode||'AI evaluation'))}</div><div class="practice-big-score">${data.overall_score}<small>/100</small></div><p>20 descriptive questions + 20 MCQs completed.</p><button class="interview-start" id="restartPractice">Try Again →</button></div><div class="analysis-grid" style="margin-top:16px"><div class="analysis-panel"><h3>Strengths</h3><ul>${strengths||'<li>Keep practising complete answers.</li>'}</ul></div><div class="analysis-panel"><h3>Improvements</h3><ul>${improvements||'<li>Continue practising role-specific questions.</li>'}</ul></div></div><div class="practice-results-list">${rows}</div>`;
  $c('restartPractice').addEventListener('click',()=>{$c('practiceResult').classList.add('hidden');$c('practiceArea').classList.remove('hidden');practiceAnswers=new Array(40).fill('');practiceIndex=0;renderPracticeQuestion();});
}
function escapeHtml(value){return String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');}
