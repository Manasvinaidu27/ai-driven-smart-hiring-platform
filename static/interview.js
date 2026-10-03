(() => {
'use strict';
const $ = id => document.getElementById(id);
const candidates = Array.isArray(window.INTERVIEW_CANDIDATES) ? window.INTERVIEW_CANDIDATES : [];
const jobs = Array.isArray(window.INTERVIEW_JOBS) ? window.INTERVIEW_JOBS : [];
let questions=[]; let simulationQuestions=[]; let current=0; let job=null; let sessionId=''; let started=false; let sending=false; let scores=[]; let simulationType='descriptive'; let simulationAnswers=[];
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
function msg(t,ok=false){const e=$('interviewSetupMsg');if(!e)return;e.className='message '+(ok?'ok':'err');e.textContent=t;e.classList.remove('hidden');}
function candidate(){const i=Number($('interviewCandidate')?.value);return Number.isInteger(i)&&candidates[i]?candidates[i]:{name:'Demo Candidate',email:'demo@example.com'};}
function selectedJob(){const id=String($('interviewJob')?.value||'');return jobs.find(j=>String(j.id)===id)||{id,title:$('interviewJob')?.selectedOptions?.[0]?.text||'Selected Role',required_skills:[]};}
function filter(){return String($('questionTypeSelect')?.value||'all');}
const T={
 technical:[
  'How would you apply {skill} in a real {role} project?','What are the key implementation considerations for {skill} in a {role} role?','How would you test and validate a solution involving {skill}?','What common issue can occur with {skill}, and how would you troubleshoot it?','How would you improve performance, reliability, or maintainability when using {skill}?','Explain an important trade-off when using {skill} in a {role} project.','How would you review another developer’s implementation of {skill}?','How would you secure a solution that uses {skill}?','How would you debug a production issue involving {skill}?','How would you document a technical decision involving {skill}?','What metrics would you monitor for a {skill}-based solution?','How would you handle errors when working with {skill}?'
 ],
 behavioral:[
  'Tell me about a project where you used {skill}. What did you contribute?','Describe a challenge you faced while learning or using {skill} and how you handled it.','How would you explain your work with {skill} to a non-technical stakeholder?','Tell me about a time you received feedback on work involving {skill}. What changed afterward?','Describe how you collaborated with others on a task involving {skill}.','What did you learn from a project where you used {skill}?','Describe a time you had to learn a new tool quickly for a project.','Tell me about a time you made a mistake in a project and what you learned.','How do you prioritize competing tasks in a {role} position?','Describe a time you disagreed with a teammate and how you resolved it.'
 ],
 situational:[
  'A production issue involves {skill}. What steps would you take to diagnose and resolve it?','A stakeholder reports an unexpected result involving {skill}. How would you investigate?','A deadline is approaching and a task involving {skill} is incomplete. What would you do?','A requirement changes after you implement {skill}. How would you respond?','You discover a quality problem involving {skill} before release. What is your approach?','Two team members disagree about how to use {skill}. How would you handle the situation?','A critical defect is reported immediately before release. What would you do first?','You receive incomplete requirements for a {role} task. How would you proceed?','A solution using {skill} is slower than expected in production. How would you respond?','A stakeholder rejects your proposed solution. How would you handle the discussion?'
 ]
};
async function makeQuestions(){
 const id=job?.id; if(!id) throw new Error('Select a job role first.');
 const response=await fetch(`/api/interview/questions/${encodeURIComponent(id)}?type=all&v=40`,{cache:'no-store',headers:{'Accept':'application/json'}});
 const data=await response.json();
 if(!response.ok||!data.success) throw new Error(data.error||'Unable to generate the 40 questions.');
 if(!Array.isArray(data.questions)||data.questions.length!==40) throw new Error(`Expected 40 questions, received ${data.questions?.length||0}.`);
 if(data.questions.filter(q=>q.type==='descriptive').length!==20||data.questions.filter(q=>q.type==='mcq').length!==20) throw new Error('The recruiter exam must contain exactly 20 descriptive questions and 20 MCQs.');
 return data.questions;
}
function makeSimulationQuestions(type){
 const bank=questions.filter(q=>type==='mcq' ? q.type==='mcq' : q.type==='descriptive');
 return bank.slice(0,20).map((q,i)=>({...q,id:i+1}));
}

function renderSimulationMode(){
 const isMcq=simulationType==='mcq';
 const textComposer=$('simulationTextComposer');
 const mcqOptions=$('simulationMcqOptions');
 if(textComposer) textComposer.classList.toggle('hidden',isMcq);
 if(mcqOptions) mcqOptions.classList.toggle('hidden',!isMcq);
}

function render(){const list=$('generatorList');if(!list)return;if(!questions.length){list.innerHTML='<div class="question-placeholder"><div class="placeholder-icon">?</div><b>Click Generate Questions</b><span>Questions will be tailored to the selected job role and question type.</span></div>';}else{list.innerHTML=questions.map((q,i)=>`<article class="generated-question ${i===current?'selected-question':''}" data-i="${i}"><span class="q-number">${i+1}</span><div><p>${esc(q.question)}</p><small>${esc(q.type)} · Recruiter assessment question</small>${q.type==='mcq'?`<div class="generated-mcq-options">${(q.options||[]).map((o,j)=>`<span>${String.fromCharCode(65+j)}. ${esc(o)}</span>`).join('')}</div>`:''}</div></article>`).join('');list.querySelectorAll('.generated-question').forEach(el=>el.onclick=()=>{if(!started)start( Number(el.dataset.i));});} if($('questionCount'))$('questionCount').textContent=questions.length+' questions';}
function bubble(text,kind='ai'){const box=$('chatWindow');if(!box)return;const d=document.createElement('div');d.className='chat-bubble '+(kind==='user'?'user-bubble':'ai-bubble');d.textContent=text;box.appendChild(d);box.scrollTop=box.scrollHeight;}
function setQ(i){
 if(!simulationQuestions.length)return;
 current=Math.max(0,Math.min(i,simulationQuestions.length-1));
 render();
 const q=simulationQuestions[current];
 $('questionProgress').textContent=`Question ${current+1} of ${simulationQuestions.length}`;
 bubble(`Question ${current+1} of ${simulationQuestions.length}: ${q.question}`);
 renderSimulationMode();
 const inp=$('answerInput'),btn=$('sendAnswer'),opts=$('simulationMcqOptions');
 if(simulationType==='mcq'){
   if(opts){
     opts.innerHTML=(q.options||[]).map((o,j)=>`<label class="simulation-mcq-option"><input type="radio" name="simulationMcq" value="${esc(o)}"><span><b>${String.fromCharCode(65+j)}.</b> ${esc(o)}</span></label>`).join('');
     opts.querySelectorAll('input').forEach(r=>r.addEventListener('change',async()=>{
       if(sending) return;
       simulationAnswers[current]=r.value;
       // In MCQ mode, selecting an option is the submission action.
       // This keeps the simulation sequential and avoids requiring a separate Send click.
       await sendAnswer();
     }));
   }
 } else if(inp){inp.disabled=false;inp.value=simulationAnswers[current]||'';inp.focus();}
 if(btn){btn.disabled=false;btn.innerHTML='➤ <span>Send</span>';}
}

function start(i=0){if(!simulationQuestions.length){msg('Select Descriptive or MCQ Interview, then click Generate Questions.');return;}started=true;const c=candidate();const box=$('chatWindow');if(box)box.innerHTML='';bubble(`Candidate interview — ${c.name||'Candidate'} — ${job?.title||'Selected role'} — ${simulationType==='mcq'?'MCQ':'Descriptive'}.`);$('sessionStatus').textContent='Active Session';$('sessionStatus').classList.add('active');setQ(i);}
async function generateQuestions(){
 const btn=$('startInterview'); if(btn){btn.disabled=true;btn.textContent='Generating…';}
 try{
   job=selectedJob();
   questions=await makeQuestions();
   simulationQuestions=makeSimulationQuestions(simulationType);
   if(simulationQuestions.length!==20) throw new Error(`Expected 20 ${simulationType} simulation questions, received ${simulationQuestions.length}.`);
   current=0;scores=[];simulationAnswers=new Array(20).fill('');started=false;sessionId='session-'+Date.now();
   $('simulationTitle').textContent=(job.title||'Selected Role')+' interview';$('simulationFeedback')?.classList.add('hidden');
   const box=$('chatWindow');if(box)box.innerHTML=`<div class="chat-bubble ai-bubble">${simulationType==='mcq'?'20 MCQ':'20 descriptive'} questions loaded. The AI simulation will begin with Question 1.</div>`;
   render();msg(`20 ${simulationType==='mcq'?'MCQ':'descriptive'} simulation questions generated for ${job.title}.`,true);start(0);
 }catch(e){console.error(e);msg('Could not generate questions: '+e.message);}finally{if(btn){btn.disabled=false;btn.textContent='Generate Questions';}}
}

function localEval(answer,q){const words=answer.split(/\s+/).filter(Boolean).length;const qWords=new Set(q.question.toLowerCase().match(/[a-z0-9+#.-]+/g)||[]);const aWords=new Set(answer.toLowerCase().match(/[a-z0-9+#.-]+/g)||[]);let overlap=0;qWords.forEach(w=>{if(aWords.has(w))overlap++;});const relevance=Math.min(100,45+overlap*5);const communication=Math.min(100,40+Math.min(words,80));const structure=Math.min(100,45+(answer.includes('.')?15:0)+(words>35?20:0));const score=Math.round(relevance*.4+communication*.3+structure*.3);const feedback=score>=75?'Strong response. Add a concrete example or measurable result to make it stronger.':score>=60?'Good start. Add more role-specific technical detail and a clear example.':'Add more detail, explain your reasoning step by step, and connect the answer directly to the question.';return {score,feedback,metrics:{technical_relevance:relevance,communication,structure}};}
async function sendAnswer(){
 if(sending)return;if(!started||!simulationQuestions.length){msg('Click Generate Questions first.');return;}
 const q=simulationQuestions[current];let answer='';
 if(simulationType==='mcq'){
   answer=simulationAnswers[current]||'';
   if(!answer){msg('Please select an MCQ option before clicking Send.');return;}
 }else{
   const inp=$('answerInput');answer=(inp?.value||'').trim();
   if(!answer){msg('Please type an answer before clicking Send.');return;}
   simulationAnswers[current]=answer;
 }
 sending=true;const btn=$('sendAnswer');if(btn){btn.disabled=true;btn.innerHTML='Saving…';}
 if(simulationType==='mcq'){
   const selected=q.options?.indexOf(answer);
   const score=selected===Number(q.answer_index)?100:0;
   const feedback=score===100?'Correct answer.':'Incorrect answer. Review the concept and try similar questions.';
   scores.push(score);bubble(`${String.fromCharCode(65+(selected??0))}. ${answer}`,'user');
   const fb=$('simulationFeedback');if(fb){fb.classList.remove('hidden');fb.innerHTML=`<b>MCQ submitted</b><span>${feedback}</span>`;}
 }else{
   bubble(answer,'user');let ev=localEval(answer,q);
   try{const r=await fetch('/api/interview/evaluate',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({answer,question:q.question,skills:job?.required_skills||[],role:job?.title||''}),cache:'no-store'});if(r.ok){const d=await r.json();if(d.success)ev={score:Number(d.score)||ev.score,feedback:(d.feedback||[]).join(' '),metrics:d.metrics||ev.metrics};}}catch(_){}
   scores.push(Number(ev.score)||0);
   const fb=$('simulationFeedback');if(fb){fb.classList.remove('hidden');fb.innerHTML=`<b>Answer recorded</b><span>Score is included in the final interview result.</span>`;}
 }
 // Persist the answer without blocking the UI. A slow/unavailable save endpoint must not
 // prevent the interview from advancing to the next question.
 try{
   const controller=new AbortController();
   const timer=setTimeout(()=>controller.abort(),2000);
   fetch('/api/interview/save-answer',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({session_id:sessionId,candidate:candidate(),job,question_id:q.id,question:q.question,answer,score:scores[scores.length-1],feedback:[],metrics:{type:simulationType}}),signal:controller.signal})
     .catch(()=>{}).finally(()=>clearTimeout(timer));
 }catch(_){}
 if(current<simulationQuestions.length-1){setTimeout(()=>{current++;if($('simulationFeedback'))$('simulationFeedback').classList.add('hidden');sending=false;setQ(current);},450);}
 else{const final=Math.round(scores.reduce((a,b)=>a+b,0)/scores.length);const strong=scores.filter(x=>x>=75).length;const improve=scores.filter(x=>x<60).length;$('sessionStatus').textContent='Completed';$('sessionStatus').classList.remove('active');if($('answerInput'))$('answerInput').disabled=true;if(btn){btn.disabled=true;btn.innerHTML='Interview Complete';}if($('simulationMcqOptions'))$('simulationMcqOptions').classList.add('hidden');bubble(`Interview completed. Overall score: ${final}% (${scores.length}/20 questions answered).`);msg(`${simulationType==='mcq'?'MCQ':'Descriptive'} interview completed for ${job.title}. Overall score: ${final}%.`,true);const fb=$('simulationFeedback');if(fb){fb.classList.remove('hidden');fb.innerHTML=`<div class="final-interview-summary"><strong>Overall ${simulationType==='mcq'?'MCQ':'Descriptive'} Interview Score: ${final}%</strong><span>Questions answered: ${scores.length}/20 · Strong responses: ${strong} · Needs improvement: ${improve}</span><p>${final>=75?'Strong overall performance. Review the detailed feedback to refine your answers.':final>=60?'Good overall performance. Focus on questions with lower scores.':'More practice is recommended. Review the questions and strengthen role-specific preparation.'}</p></div>`;}sending=false;}
}

function bind(){
 window.generateQuestions=generateQuestions;window.sendAnswer=sendAnswer;
 document.querySelectorAll('.simulation-mode-btn').forEach(btn=>btn.addEventListener('click',()=>{
   document.querySelectorAll('.simulation-mode-btn').forEach(x=>x.classList.remove('active'));btn.classList.add('active');
   simulationType=btn.dataset.simType||'descriptive';questions=[];simulationQuestions=[];started=false;renderSimulationMode();render();
 }));
 $('startInterview')?.addEventListener('click',generateQuestions);$('sendAnswer')?.addEventListener('click',sendAnswer);
 $('answerInput')?.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendAnswer();}});
 $('interviewJob')?.addEventListener('change',()=>{questions=[];simulationQuestions=[];started=false;render();});
 $('questionTypeSelect')?.addEventListener('change',()=>{questions=[];started=false;render();});
 renderSimulationMode();render();
}

if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
})();
