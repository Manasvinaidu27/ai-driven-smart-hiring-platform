from pathlib import Path
import json, re, tempfile
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import plotly.express as px

from parser import load_candidates
from matcher import match_candidate_to_job, skills_from_job

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
JOBS_FILE = DATA_DIR / "jobs.json"
VOICE_FILE = DATA_DIR / "voice_screening_results.json"
FEEDBACK_FILE = DATA_DIR / "user_feedback.json"

DEFAULT_JOBS = [
    {"id": 1, "title": "Python Developer", "required_skills": ["Python", "Django", "SQL", "HTML", "CSS", "Git"], "min_experience": 0, "education": "B.Tech / B.E. / equivalent", "location": "Hyderabad, India", "description": "Build Python web applications and REST APIs."},
    {"id": 2, "title": "Data Analyst", "required_skills": ["Python", "SQL", "Power BI", "Excel", "Pandas"], "min_experience": 0, "education": "B.Tech / B.Sc. / equivalent", "location": "Hyderabad, India", "description": "Analyze business data and build dashboards."},
    {"id": 3, "title": "Full Stack Developer", "required_skills": ["Python", "Django", "JavaScript", "HTML", "CSS", "SQL", "Git"], "min_experience": 0, "education": "B.Tech / B.E. / equivalent", "location": "Hyderabad, India", "description": "Develop frontend, backend and database features."},
]

@st.cache_data(ttl=10)
def read_json(path, default):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, type(default)) else default
    except (OSError, json.JSONDecodeError, TypeError):
        return default

@st.cache_data(ttl=10)
def get_jobs():
    data = read_json(JOBS_FILE, [])
    return data if data else DEFAULT_JOBS

@st.cache_data(ttl=10)
def get_candidates():
    return load_candidates()

def save_json(path, rows):
    Path(path).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    st.cache_data.clear()

def candidate_rows(candidates, jobs):
    rows=[]
    for i,c in enumerate(candidates):
        best=None; best_job=None
        for j in jobs:
            result=match_candidate_to_job(c,j)
            if best is None or result["score"] > best["score"]:
                best=result; best_job=j
        if best:
            rows.append({
                "Candidate": c.get("name") or "Unknown",
                "Email": c.get("email") or "Not detected",
                "Best Job": best_job.get("title", "") if best_job else "",
                "Hiring Score": round(float(best.get("score",0))),
                "Status": best.get("recommendation", "Not scored"),
                "Matched Skills": ", ".join(best.get("matched_skills",[])[:8]),
                "Missing Skills": ", ".join(best.get("missing_skills",[])[:8]),
                "Index": i,
            })
    return sorted(rows,key=lambda x:x["Hiring Score"],reverse=True)

def evaluate_answer(question, answer, job):
    answer=str(answer or "").strip()
    if not answer: return 0, "No answer submitted."
    words=re.findall(r"\b[\w+#.-]+\b",answer)
    skills=skills_from_job(job)
    hits=sum(1 for s in skills if str(s).casefold() in answer.casefold())
    structure=sum(1 for x in ["first","then","because","example","result","impact","tested","finally"] if re.search(rf"\b{re.escape(x)}\b",answer.casefold()))
    score=min(100, round(35 + min(len(words),80)*0.45 + min(hits*8,24) + min(structure*4,16)))
    if score>=80: fb="Strong response. Keep the explanation specific and evidence-based."
    elif score>=60: fb="Good start. Add a concrete example, technical detail, or measurable result."
    else: fb="Add more detail and connect your answer directly to the job requirements."
    return score,fb

def speak_text(text):
    try:
        import pyttsx3
        engine=pyttsx3.init()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f: out=f.name
        engine.save_to_file(text,out); engine.runAndWait(); engine.stop()
        return out
    except Exception:
        return None

def transcribe_audio(audio_bytes):
    try:
        import speech_recognition as sr
        recognizer=sr.Recognizer()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes); name=f.name
        with sr.AudioFile(name) as source:
            audio=recognizer.record(source)
        return recognizer.recognize_google(audio), None
    except Exception as e:
        return "", str(e)

st.set_page_config(page_title="Recruitment Copilot Analytics", page_icon="RC", layout="wide")
st.title("Recruitment Copilot")
st.caption("Candidate analytics, hiring scores, skill gaps, interviews and voice screening")

candidates=get_candidates(); jobs=get_jobs(); rows=candidate_rows(candidates,jobs)
voice_rows=read_json(VOICE_FILE,[])
interview_rows=read_json(DATA_DIR/"interview_sessions.json",[])

completed=len({str(x.get("session_id")) for x in interview_rows if x.get("session_id") and x.get("completed")})
voice_count=len(voice_rows)
strong=sum(1 for r in rows if r["Hiring Score"]>=80)
# Presentation-friendly KPI: explicitly labeled as demo so it is not confused with a real hiring outcome.
# It remains in the requested 90-100% range while actual candidate scores are shown separately below.
if rows:
    actual_avg = round(sum(r["Hiring Score"] for r in rows) / len(rows))
    demo_hiring_rate = max(90, min(100, actual_avg if actual_avg >= 90 else 95))
else:
    demo_hiring_rate = 95

c1,c2,c3,c4,c5=st.columns(5)
c1.metric("Resumes Processed",len(candidates))
c2.metric("Active Job Postings",len(jobs))
c3.metric("Interviews Completed",completed)
c4.metric("Strong Matches",strong)
c5.metric("Hiring Rate",f"{demo_hiring_rate}%",help="Demo presentation KPI constrained to 90-100%. Use actual hiring outcomes for production reporting.")

st.subheader("Recruitment Analytics Overview")

# Clear presentation charts: candidate score distribution, hiring decision mix, and top skills.
chart1, chart2 = st.columns(2)
with chart1:
    if rows:
        score_bins = {"90-100%":0, "80-89%":0, "70-79%":0, "Below 70%":0}
        for r in rows:
            score=float(r["Hiring Score"])
            if score >= 90: score_bins["90-100%"] += 1
            elif score >= 80: score_bins["80-89%"] += 1
            elif score >= 70: score_bins["70-79%"] += 1
            else: score_bins["Below 70%"] += 1
    else:
        score_bins = {"90-100%":9, "80-89%":3, "70-79%":1, "Below 70%":0}
    score_df=pd.DataFrame({"Score Range":list(score_bins.keys()),"Candidates":list(score_bins.values())})
    fig=px.pie(score_df,names="Score Range",values="Candidates",hole=0.42,title="Candidate Hiring Score Distribution")
    fig.update_traces(textposition="inside",textinfo="percent+label")
    fig.update_layout(height=360,margin=dict(l=20,r=20,t=55,b=20),legend_title_text="Score range")
    st.plotly_chart(fig,use_container_width=True)

with chart2:
    if rows:
        decision_counts=pd.Series([r["Status"] for r in rows]).value_counts().reset_index()
        decision_counts.columns=["Decision","Candidates"]
    else:
        decision_counts=pd.DataFrame({"Decision":["Hire","Shortlist","Review"],"Candidates":[8,4,1]})
    fig=px.pie(decision_counts,names="Decision",values="Candidates",hole=0.42,title="Hiring Decision Mix")
    fig.update_traces(textposition="inside",textinfo="percent+label")
    fig.update_layout(height=360,margin=dict(l=20,r=20,t=55,b=20),legend_title_text="Decision")
    st.plotly_chart(fig,use_container_width=True)

# Ranked job/candidate performance graph
if rows:
    top_df=pd.DataFrame(rows)[["Candidate","Hiring Score"]].head(10).sort_values("Hiring Score")
else:
    top_df=pd.DataFrame({"Candidate":["Candidate A","Candidate B","Candidate C","Candidate D","Candidate E"],"Hiring Score":[98,96,94,92,90]})
fig=px.bar(top_df,x="Hiring Score",y="Candidate",orientation="h",text="Hiring Score",title="Top Candidate Hiring Scores",range_x=[0,100])
fig.update_traces(texttemplate="%{text}%",textposition="outside")
fig.update_layout(height=430,margin=dict(l=20,r=55,t=55,b=30),xaxis_title="Hiring score (%)",yaxis_title="Candidate")
st.plotly_chart(fig,use_container_width=True)

# Skills demand graph from job profiles
skill_counts={}
for job_item in jobs:
    for skill in skills_from_job(job_item):
        key=str(skill).strip()
        if key: skill_counts[key]=skill_counts.get(key,0)+1
if skill_counts:
    skills_df=pd.DataFrame(sorted(skill_counts.items(),key=lambda x:x[1],reverse=True)[:10],columns=["Skill","Job Requirements"])
else:
    skills_df=pd.DataFrame({"Skill":["Python","SQL","Power BI","Django","Excel"],"Job Requirements":[5,4,3,3,2]})
fig=px.bar(skills_df,x="Skill",y="Job Requirements",text="Job Requirements",title="Most Requested Skills")
fig.update_layout(height=380,margin=dict(l=20,r=20,t=55,b=70),xaxis_title="Skill",yaxis_title="Number of job profiles")
st.plotly_chart(fig,use_container_width=True)

st.info("Charts use live project data when available. When the project has no candidate/job records yet, the dashboard displays clearly illustrative demo values so the analytics page is still presentation-ready.")

st.subheader("Candidate Ranking")
if rows:
    df=pd.DataFrame(rows).drop(columns=["Index"])
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.download_button("Download Candidate Ranking",df.to_csv(index=False),"candidate_ranking.csv","text/csv")
else:
    st.info("Upload resumes to populate candidate analytics.")

st.subheader("Skill-Gap Analysis")
if rows:
    selected=st.selectbox("Candidate",[r["Candidate"] for r in rows])
    row=next(r for r in rows if r["Candidate"]==selected)
    st.write(f"**Best matched role:** {row['Best Job']}  |  **Hiring score:** {row['Hiring Score']}%")
    a,b=st.columns(2); a.success(row["Matched Skills"] or "No matched skills detected"); b.warning(row["Missing Skills"] or "No missing required skills detected")

st.subheader("Interview Status")
st.write(f"Completed interviews: **{completed}**")
st.write(f"Voice screening responses saved: **{voice_count}**")

st.divider()
st.header("Voice Screening")
job=st.selectbox("Screening job",jobs,key="voice_job",format_func=lambda x:x.get("title","Job"))
candidate=st.selectbox("Candidate",candidates,key="voice_candidate",format_func=lambda x:x.get("name","Candidate"))
questions=[
    f"Briefly explain your experience relevant to the {job.get('title','role')} role.",
    f"How would you apply {', '.join(skills_from_job(job)[:3])} in this role?",
    "Describe a project or problem you solved and the result you achieved.",
]
qnum=st.number_input("Question",1,len(questions),1,key="voice_q")
question=questions[qnum-1]
st.info(question)

speech_audio=st.audio_input("Record your answer")
typed=st.text_area("Or enter your answer",height=140)
if speech_audio:
    transcript,error=transcribe_audio(speech_audio.getvalue())
    if transcript:
        st.session_state["voice_transcript"]=transcript
        st.success("Speech converted to text.")
    elif error:
        st.warning("Speech-to-text could not process this recording. You can use the text box instead.")
answer=st.text_area("Answer",value=st.session_state.get("voice_transcript",typed),height=160,key="voice_answer")
if st.button("Save Screening Answer",type="primary"):
    if not answer.strip(): st.error("Please provide an answer.")
    else:
        score,feedback=evaluate_answer(question,answer,job)
        record={"timestamp":datetime.now(timezone.utc).isoformat(),"candidate":candidate.get("name"),"job":job.get("title"),"question":question,"answer":answer,"score":score,"feedback":feedback,"input_source":"voice" if speech_audio else "typed"}
        voice_rows.append(record); save_json(VOICE_FILE,voice_rows[-500:]); st.success(f"Answer saved. Score: {score}% — {feedback}")

st.divider()
st.subheader("AI Interviewer Voice")
tts=st.text_input("Text for interviewer voice",value=question)
if st.button("Generate Interviewer Voice"):
    path=speak_text(tts)
    if path: st.audio(path,format="audio/wav")
    else: st.warning("Text-to-speech is unavailable in this environment. Browser voice screening remains available in the recruiter portal.")

st.divider()
st.subheader("User Feedback")
with st.form("feedback_form"):
    rating=st.slider("How satisfied are you with the recruitment workflow?",1,5,5)
    submitted=st.form_submit_button("Submit Feedback")
    if submitted:
        feedback_rows=read_json(FEEDBACK_FILE,[])
        feedback_rows.append({"timestamp":datetime.now(timezone.utc).isoformat(),"rating":rating})
        save_json(FEEDBACK_FILE,feedback_rows)
        st.success("Feedback saved.")
feedback_rows=read_json(FEEDBACK_FILE,[])
if feedback_rows:
    positive=sum(1 for x in feedback_rows if int(x.get("rating",0))>=4)
    satisfaction=round(positive/len(feedback_rows)*100,1)
    st.metric("Observed satisfaction",f"{satisfaction}%",help="Calculated from submitted ratings of 4 or 5 out of 5. It is only meaningful after actual user feedback is collected.")

st.caption("This analytics app uses the same local candidate/job data as the Flask recruitment application. It does not replace the existing recruiter dashboard.")
