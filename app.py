from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file, redirect, url_for, session
from parser import load_candidates, process_resume, profile_to_dataframe, get_candidate, init_candidate_db, DB_FILE
from matcher import rank_candidates, build_skill_gap_report, match_candidate_to_job, skills_from_job, norm
from jd_parser import analyze_job_description, analyze_job_file
import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from collections import Counter
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

app = Flask(__name__)
app.secret_key = 'ai-smart-hiring-demo-secret-key-change-in-production'
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
BASE_DIR = Path(__file__).resolve().parent

# Vercel allows temporary runtime storage in /tmp.
RUNTIME_DIR = Path("/tmp/ai-smart-hiring")

UPLOAD_DIR = RUNTIME_DIR / "uploads"
DATA_DIR = RUNTIME_DIR / "data"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED = {".pdf", ".docx"}
AI_API_URL = os.getenv("AI_API_URL", "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini").strip()


@app.before_request
def require_login():
    public = {"login", "recruiter_login", "candidate_login", "static"}
    if request.endpoint in public:
        return None
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    # Recruiter-only routes
    recruiter_endpoints = {"dashboard", "upload_page", "candidates", "candidate_insights", "ats_page",
                           "ats_config", "save_ats_config", "ats_test", "ats_sync", "api_candidates",
                           "api_jobs", "create_job", "analyze_job_description_api", "job_matches", "skill_gap",
                           "interview_page", "interview_questions", "voice_screening_page", "save_voice_screening", "demo_ats_candidates", "mock_ats_add_candidate", "mock_ats_list_candidates", "mock_ats_update_status"}
    if request.endpoint in recruiter_endpoints and session.get("role") != "recruiter":
        return redirect(url_for("candidate_dashboard"))
    candidate_endpoints = {"candidate_interview_page", "candidate_interview_questions", "submit_candidate_interview"}
    if request.endpoint in candidate_endpoints and session.get("role") != "candidate":
        return redirect(url_for("recruiter_login"))


@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/recruiter-login", methods=["GET", "POST"])
def recruiter_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username == "admin" and password == "admin123":
            session.clear(); session["logged_in"] = True; session["role"] = "recruiter"; session["username"] = username
            return redirect(url_for("dashboard"))
        return render_template("recruiter_login.html", error="Invalid recruiter username or password.")
    return render_template("recruiter_login.html")

DEMO_CANDIDATE = {
    "name": "Demo Candidate",
    "email": "demo.candidate@smart-hiring.local",
    "phone": "Not available (demo)",
    "location": "Hyderabad, India",
    "skills": ["Python", "Django", "SQL", "HTML", "CSS", "JavaScript", "Power BI", "Excel", "Git"],
    "education": ["B.Tech – Computer Science Engineering (AI & ML)"],
    "projects": ["AI Smart Hiring Platform", "Power BI Analytics Dashboard"],
    "certifications": ["Advanced Data Analytics"],
    "experience": {"roles": [], "details": [], "internships": [], "total_experience": "Fresher / Demo profile"},
    "confidence": 90,
}

@app.route("/candidate-login", methods=["GET", "POST"])
def candidate_login():
    candidates = load_candidates()
    if request.method == "POST":
        # One-click demo sign-in for presentations/testing.
        if request.form.get("demo_login") == "1":
            session.clear(); session["logged_in"] = True; session["role"] = "candidate"; session["demo_candidate"] = True
            return redirect(url_for("candidate_dashboard"))

        email = request.form.get("email", "").strip().casefold()
        idx = next((i for i,c in enumerate(candidates) if str(c.get("email","")).casefold() == email), None)
        # Demo-friendly fallback: allow selecting a candidate even when email extraction is missing.
        if idx is None and request.form.get("candidate_index", "").isdigit():
            j=int(request.form["candidate_index"]); idx=j if 0 <= j < len(candidates) else None
        if idx is not None:
            session.clear(); session["logged_in"] = True; session["role"] = "candidate"; session["candidate_index"] = idx
            return redirect(url_for("candidate_dashboard"))
        return render_template("candidate_login.html", candidates=candidates, error="Candidate not found. Select your profile, use the registered email, or choose Demo Sign In.")
    return render_template("candidate_login.html", candidates=candidates)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
def home():
    return redirect(url_for("dashboard"))


def skill_categories(skills):
    groups = {
        "Programming": {"python", "java", "javascript", "c++", "c#", "r", "sql"},
        "Web": {"html", "html5", "css", "css3", "django", "flask", "react", "node.js", "nodejs", "rest api"},
        "Data & BI": {"power bi", "excel", "pandas", "numpy", "data analysis", "data visualization", "machine learning", "pyspark"},
        "Cloud & DevOps": {"aws", "azure", "docker", "git", "github", "ci/cd"},
        "Other": set(),
    }
    counts = Counter()
    for skill in skills or []:
        key = str(skill).casefold().strip()
        found = next((name for name, vals in groups.items() if key in vals), "Other")
        counts[found] += 1
    return [{"name": k, "count": counts[k]} for k in groups if counts[k]]

def profile_summary(candidate):
    skills=len(candidate.get("skills",[]) or [])
    projects=len(candidate.get("projects",[]) or [])
    certs=len(candidate.get("certifications",[]) or [])
    exp=candidate.get("experience",{}) or {}
    exp_present=bool(exp.get("roles") or exp.get("details") or exp.get("internships"))
    parts=[f"The resume parser detected {skills} skill(s), {projects} project(s), and {certs} certification(s)."]
    parts.append("Professional experience information was detected." if exp_present else "No professional experience duration or role was clearly detected.")
    return " ".join(parts)

def next_steps(candidate):
    steps=[]
    if not candidate.get("phone") or candidate.get("phone")=="Not detected": steps.append("Add a clearly formatted phone number to the resume.")
    if not candidate.get("location") or candidate.get("location")=="Not detected": steps.append("Add a current location or preferred work location.")
    if not candidate.get("certifications"): steps.append("Add relevant certifications or training credentials if applicable.")
    if not candidate.get("projects"): steps.append("Add 1–3 measurable projects with tools, responsibilities and outcomes.")
    if not candidate.get("experience",{}).get("roles") and not candidate.get("experience",{}).get("internships"): steps.append("Clarify experience or internship titles and dates where applicable.")
    return steps[:5] or ["Keep the resume sections clearly labelled and tailor skills to each target job description."]

def completeness_metrics(c):
    exp=c.get("experience",{}) or {}
    return {
        "contact": 100 if c.get("email") not in (None,"","Not detected") and c.get("phone") not in (None,"","Not detected") else 50 if c.get("email") not in (None,"","Not detected") else 0,
        "education": 100 if c.get("education") else 0,
        "skills": 100 if c.get("skills") else 0,
        "experience": 100 if exp.get("roles") or exp.get("details") or exp.get("internships") else 0,
        "projects": 100 if c.get("projects") or c.get("certifications") else 0,
    }

def _read_json_file(path, default):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def _dashboard_candidate_rows(candidates, jobs):
    rows = []
    for index, candidate in enumerate(candidates):
        best = None
        best_job = None
        for job in jobs:
            result = match_candidate_to_job(candidate, job)
            if best is None or result.get("score", 0) > best.get("score", 0):
                best, best_job = result, job
        if best is None:
            best = {"score": 0, "recommendation": "Not scored", "missing_skills": [], "matched_skills": []}
        rows.append({
            "index": index,
            "name": candidate.get("name") or "Unknown Candidate",
            "email": candidate.get("email") or "Not detected",
            "job": (best_job or {}).get("title", "No job selected"),
            "score": round(float(best.get("score", 0))),
            "recommendation": best.get("recommendation", "Not scored"),
            "missing_skills": best.get("missing_skills", [])[:5],
            "matched_skills": best.get("matched_skills", [])[:5],
        })
    return sorted(rows, key=lambda x: x["score"], reverse=True)


def _dashboard_interview_stats():
    sessions = _read_json_file(DATA_DIR / "interview_sessions.json", [])
    if not isinstance(sessions, list):
        sessions = []
    grouped = {}
    for row in sessions:
        sid = str(row.get("session_id") or "")
        if not sid:
            continue
        grouped.setdefault(sid, []).append(row)
    completed = 0
    scores = []
    for answers in grouped.values():
        if len(answers) >= 20:
            completed += 1
            vals = [int(x.get("score") or 0) for x in answers[:20]]
            if vals:
                scores.append(round(sum(vals) / len(vals)))
    return completed, (round(sum(scores) / len(scores)) if scores else 0)


@app.get("/dashboard")
def dashboard():
    candidates = load_candidates()
    jobs = load_jobs()
    candidate_rows = _dashboard_candidate_rows(candidates, jobs)
    strong_matches = sum(1 for row in candidate_rows if row["score"] >= 80)
    internship_count = sum(1 for c in candidates if (c.get("experience", {}) or {}).get("internships"))
    resume_count = len(candidates)
    readiness = 100 if resume_count else 0
    success_rate = round((strong_matches / resume_count) * 100) if resume_count else 0
    interview_count, average_interview_score = _dashboard_interview_stats()
    voice_results = _read_json_file(DATA_DIR / "voice_screening_results.json", [])
    voice_count = len(voice_results) if isinstance(voice_results, list) else 0
    return render_template("dashboard.html", resume_count=resume_count, job_count=len(jobs),
                           interview_count=interview_count, success_rate=success_rate,
                           strong_matches=strong_matches, internship_count=internship_count,
                           readiness=readiness, jobs=jobs, candidate_rows=candidate_rows[:8],
                           average_interview_score=average_interview_score, voice_count=voice_count)


@app.get("/upload")
def upload_page():
    return render_template("upload.html", candidates=load_candidates())



JOBS_FILE = DATA_DIR / "jobs.json"

DEFAULT_JOBS = [
    {"id": "python-api-developer", "title": "Python API Developer"},
    {"id": "data-analyst", "title": "Data Analyst"},
    {"id": "full-stack-developer", "title": "Full Stack Developer"},
    {"id": "backend-engineer", "title": "Backend Engineer"},
    {"id": "qa-automation-engineer", "title": "QA Automation Engineer"},
    {"id": "machine-learning-engineer", "title": "Machine Learning Engineer"},
    {"id": "ai-engineer", "title": "AI Engineer"},
    {"id": "power-bi-developer", "title": "Power BI Developer"},
    {"id": "cloud-devops-engineer", "title": "Cloud DevOps Engineer"},
    {"id": "business-analyst", "title": "Business Analyst"},
    {"id": "frontend-developer", "title": "Frontend Developer"},
    {"id": "database-sql-developer", "title": "Database SQL Developer"},
    {"id": "cybersecurity-analyst", "title": "Cybersecurity Analyst"},
    {"id": "product-manager", "title": "Product Manager"},
    {"id": "data-scientist", "title": "Data Scientist"}
]

def load_jobs():
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        pass
    # Keep the interview demo usable even when the local job file is empty/missing.
    return DEFAULT_JOBS.copy()


def save_jobs(jobs):
    JOBS_FILE.write_text(json.dumps(jobs[:100], indent=2, ensure_ascii=False), encoding="utf-8")


@app.get("/jobs")
def jobs_page():
    if session.get("role") == "candidate":
        candidates=load_candidates(); idx=session.get("candidate_index",0); c=candidates[idx] if isinstance(idx,int) and 0 <= idx < len(candidates) else {}
        cs={norm(x) for x in (c.get("skills",[]) or [])}
        cards=[]
        for job in load_jobs():
            req={norm(x) for x in skills_from_job(job)}; matched=len(cs & req); fit=round(matched/max(len(req),1)*100) if req else 0
            cards.append({"job":job,"fit":fit})
        cards.sort(key=lambda x:-x["fit"])
        return render_template("candidate_jobs.html", candidate=c, job_cards=cards)
    return render_template("job_postings.html", jobs=load_jobs())


@app.get("/api/jobs")
def api_jobs():
    return jsonify(load_jobs())


@app.post("/api/jobs/analyze")
def analyze_job_description_api():
    """Analyze pasted text or an uploaded PDF/DOCX job description."""
    try:
        if "file" in request.files and request.files["file"].filename:
            uploaded = request.files["file"]
            filename = uploaded.filename or "job_description"
            suffix = Path(filename).suffix.lower()
            if suffix not in {".pdf", ".docx"}:
                return jsonify(success=False, error="Upload a PDF or DOCX job description."), 400
            safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
            path = UPLOAD_DIR / f"jd_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
            uploaded.save(path)
            try:
                profile = analyze_job_file(path)
            finally:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        else:
            text = str((request.get_json(silent=True) or {}).get("text", "")).strip()
            if not text:
                return jsonify(success=False, error="Paste a job description or upload a PDF/DOCX file."), 400
            profile = analyze_job_description(text, "pasted_job_description.txt")

        if not profile.get("required_skills"):
            return jsonify(success=False, error="No required skills were detected. Add a skills/requirements section and analyze again.", profile=profile), 422
        return jsonify(success=True, profile=profile)
    except Exception as exc:
        return jsonify(success=False, error=f"Could not analyze the job description: {exc}"), 400


@app.post("/api/jobs")
def create_job():
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()
    required_skills = payload.get("required_skills", [])
    if isinstance(required_skills, str):
        required_skills = [x.strip() for x in required_skills.replace(";", ",").split(",") if x.strip()]
    required_skills = [str(x).strip() for x in required_skills if str(x).strip()]
    if not title:
        return jsonify(success=False, error="Job title is required."), 400
    if not required_skills:
        return jsonify(success=False, error="Add at least one required skill."), 400

    try:
        min_experience = max(float(payload.get("min_experience", 0) or 0), 0)
    except (TypeError, ValueError):
        min_experience = 0

    jobs = load_jobs()
    job = {
        "id": max([int(j.get("id", 0)) for j in jobs if str(j.get("id", "")).isdigit()] or [0]) + 1,
        "title": title,
        "required_skills": required_skills,
        "min_experience": min_experience,
        "education": str(payload.get("education", "")).strip(),
        "location": str(payload.get("location", "")).strip(),
        "description": str(payload.get("description", "")).strip(),
    }
    jobs.insert(0, job)
    save_jobs(jobs)
    matches = rank_candidates(load_candidates(), job)
    return jsonify(success=True, job=job, matches=matches)


@app.get("/api/jobs/<int:job_id>/matches")
def job_matches(job_id):
    job = next((j for j in load_jobs() if int(j.get("id", -1)) == job_id), None)
    if not job:
        return jsonify(success=False, error="Job not found."), 404
    return jsonify(success=True, job=job, matches=rank_candidates(load_candidates(), job))


@app.get("/api/jobs/<int:job_id>/skill-gap/<int:candidate_index>")
def skill_gap(job_id, candidate_index):
    job = next((j for j in load_jobs() if int(j.get("id", -1)) == job_id), None)
    candidates = load_candidates()
    if not job:
        return jsonify(success=False, error="Job not found."), 404
    if not 0 <= candidate_index < len(candidates):
        return jsonify(success=False, error="Candidate not found."), 404
    return jsonify(success=True, report=build_skill_gap_report(candidates[candidate_index], job))


@app.get("/candidate-insights")
def candidate_insights():
    candidates = load_candidates()
    skill_counter = Counter()
    category_counter = Counter()
    candidate_rows = []
    for idx, candidate in enumerate(candidates):
        skills = candidate.get("skills", []) or []
        clean_skills = []
        seen = set()
        for skill in skills:
            value = str(skill).strip()
            key = value.casefold()
            if value and key not in seen:
                clean_skills.append(value); seen.add(key)
                skill_counter[key] += 1
        for item in skill_categories(clean_skills):
            category_counter[item["name"]] += item["count"]
        candidate_rows.append({
            "index": idx,
            "name": candidate.get("name") or f"Candidate {idx + 1}",
            "email": candidate.get("email") or "Not detected",
            "skill_count": len(clean_skills),
            "skills": clean_skills,
            "projects": len(candidate.get("projects", []) or []),
            "certifications": len(candidate.get("certifications", []) or [])
        })
    top_skills = sorted(skill_counter.items(), key=lambda x: (-x[1], x[0]))[:15]
    top_skills = [{"name": k, "count": v} for k, v in top_skills]
    categories = [{"name": k, "count": category_counter[k]} for k in ["Programming", "Web", "Data & BI", "Cloud & DevOps", "Other"] if category_counter[k]]
    max_skill_count = max([x["count"] for x in top_skills], default=1)
    return render_template("candidate_insights.html", candidates=candidate_rows, total_candidates=len(candidates), total_skills=sum(skill_counter.values()), unique_skills=len(skill_counter), top_skills=top_skills, categories=categories, max_skill_count=max_skill_count)

@app.get("/api/candidate-insights")
def api_candidate_insights():
    candidates = load_candidates()
    counter = Counter()
    for c in candidates:
        for skill in set(str(x).strip().casefold() for x in (c.get("skills", []) or []) if str(x).strip()):
            counter[skill] += 1
    return jsonify({"total_candidates": len(candidates), "unique_skills": len(counter), "skills": [{"name": k, "count": v} for k,v in sorted(counter.items(), key=lambda x:(-x[1],x[0]))]})

@app.get("/candidate-dashboard")
def candidate_dashboard():
    try:
        candidates = load_candidates()

        # Demo candidate login
        if session.get("demo_candidate"):
            candidate = DEMO_CANDIDATE.copy()
            index = -1

        else:
            index = session.get("candidate_index")

            if (
                index is None
                or not isinstance(index, int)
                or not 0 <= index < len(candidates)
            ):
                return redirect(url_for("candidate_login"))

            candidate = candidates[index]

        # Make sure candidate data is always safe
        if not isinstance(candidate, dict):
            candidate = DEMO_CANDIDATE.copy()

        skills = candidate.get("skills", [])
        if not isinstance(skills, list):
            skills = [str(skills)] if skills else []

        candidate["skills"] = skills

        candidate_skills = {
            norm(skill)
            for skill in skills
            if str(skill).strip()
        }

        # Load jobs safely
        jobs = load_jobs()

        if not isinstance(jobs, list):
            jobs = []

        job_cards = []

        for job in jobs:
            if not isinstance(job, dict):
                continue

            required = {
                norm(skill)
                for skill in (skills_from_job(job) or [])
                if str(skill).strip()
            }

            matched = len(candidate_skills & required)

            fit = (
                round(matched / len(required) * 100)
                if required
                else 0
            )

            # Make sure template fields always exist
            safe_job = {
                "id": job.get("id", ""),
                "title": job.get("title", "Untitled Job"),
                "location": job.get("location", ""),
                "min_experience": job.get("min_experience", 0),
                "description": job.get("description", ""),
                "required_skills": job.get("required_skills", []),
            }

            if not isinstance(safe_job["required_skills"], list):
                safe_job["required_skills"] = [
                    str(x).strip()
                    for x in str(safe_job["required_skills"]).split(",")
                    if str(x).strip()
                ]

            job_cards.append({
                "job": safe_job,
                "fit": fit,
                "matched": matched,
                "total": len(required),
            })

        job_cards.sort(
            key=lambda x: (
                -x["fit"],
                str(x["job"].get("title", "")).casefold()
            )
        )

        return render_template(
            "candidate_portal.html",
            candidate=candidate,
            index=index,
            job_cards=job_cards[:8]
        )

    except Exception as exc:
        app.logger.exception("Candidate dashboard error")

        # Do not show a blank 500 page.
        # Send the user back to candidate login.
        return redirect(url_for("candidate_login"))

@app.get("/candidate-dashboard/<int:index>")
def candidate_dashboard_legacy(index):
    if session.get("role") == "candidate":
        session["candidate_index"] = index
        return redirect(url_for("candidate_dashboard"))
    return redirect(url_for("candidates"))

@app.get("/report/<int:index>")
def analysis_report(index):
    candidates=load_candidates()
    if not 0 <= index < len(candidates): return redirect(url_for("candidates"))
    candidate=candidates[index]
    return render_template("report.html", candidate=candidate, index=index, summary=profile_summary(candidate), next_steps=next_steps(candidate))

def create_analysis_pdf(candidate, output):
    styles=getSampleStyleSheet()
    title=ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=20, leading=24, textColor=colors.HexColor("#10264a"), alignment=TA_CENTER)
    h=ParagraphStyle("H", parent=styles["Heading2"], fontSize=12, leading=15, textColor=colors.HexColor("#2459ad"))
    body=ParagraphStyle("B", parent=styles["BodyText"], fontSize=9, leading=13, textColor=colors.HexColor("#43546d"))
    doc=SimpleDocTemplate(str(output), pagesize=A4, rightMargin=38,leftMargin=38,topMargin=38,bottomMargin=38)
    story=[Paragraph("AI Resume Analysis Report",title), Spacer(1,10), Paragraph(f"<b>Candidate:</b> {candidate.get('name','Not detected')}",body), Paragraph(f"<b>Email:</b> {candidate.get('email','Not detected')} &nbsp;&nbsp; <b>Location:</b> {candidate.get('location','Not detected')}",body), Spacer(1,12), Paragraph("Executive Summary",h), Paragraph(profile_summary(candidate),body), Spacer(1,10)]
    data=[["Metric","Detected"] ,["Profile completeness",f"{candidate.get('confidence',0)}%"],["Skills",str(len(candidate.get('skills',[]) or []))],["Projects",str(len(candidate.get('projects',[]) or []))],["Certifications",str(len(candidate.get('certifications',[]) or []))]]
    t=Table(data,colWidths=[250,120]); t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eaf2ff")),("TEXTCOLOR",(0,0),(-1,0),colors.HexColor("#2459ad")),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#dce6f2")),("FONTNAME",(0,0),(-1,-1),"Helvetica"),("FONTSIZE",(0,0),(-1,-1),9),("VALIGN",(0,0),(-1,-1),"TOP"),("BOTTOMPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),7)])); story += [t,Spacer(1,14),Paragraph("Detected Skills",h),Paragraph(", ".join(candidate.get("skills",[]) or []) or "Not detected",body),Spacer(1,10),Paragraph("Education",h)]
    for x in candidate.get("education",[]) or []: story.append(Paragraph(x,body))
    story += [Spacer(1,8),Paragraph("Experience",h)]
    exp=candidate.get("experience",{}) or {}
    story.append(Paragraph(exp.get("total_experience") or "No duration detected",body))
    for x in exp.get("roles",[]) or []: story.append(Paragraph(x,body))
    story += [Spacer(1,8),Paragraph("Projects & Certifications",h)]
    for x in candidate.get("projects",[]) or []: story.append(Paragraph("Project: "+x,body))
    for x in candidate.get("certifications",[]) or []: story.append(Paragraph("Certification: "+x,body))
    story += [Spacer(1,8),Paragraph("Improvement Suggestions",h)]
    for x in next_steps(candidate): story.append(Paragraph("• "+x,body))
    doc.build(story)

@app.get("/api/profile/<int:index>/report")
def download_analysis_report(index):
    candidates=load_candidates()
    if not 0 <= index < len(candidates): return jsonify(error="Candidate not found."),404
    output=DATA_DIR / f"candidate_{index+1}_resume_analysis.pdf"
    create_analysis_pdf(candidates[index],output)
    return send_file(output, as_attachment=True, download_name=f"{(candidates[index].get('name') or 'candidate').replace(' ','_')}_resume_analysis.pdf", mimetype="application/pdf")

@app.get("/candidates")
def candidates():
    return render_template("candidates.html", candidates=load_candidates())


@app.get("/candidate-database")
def candidate_database():
    """Recruiter-facing view of the persistent SQLite candidate store."""
    candidates = load_candidates()
    return render_template("candidate_database.html", candidates=candidates, db_file=DB_FILE.name, database_path=str(DB_FILE))


@app.get("/api/candidates/<int:candidate_id>")
def api_candidate(candidate_id):
    candidate = get_candidate(candidate_id)
    if not candidate:
        return jsonify(success=False, error="Candidate not found."), 404
    return jsonify(success=True, candidate=candidate)


@app.post("/api/parse")
def parse_resume():
    uploaded = request.files.get("resume")
    if not uploaded or not uploaded.filename:
        return jsonify(success=False, error="Please select a resume."), 400

    suffix = Path(uploaded.filename).suffix.lower()
    if suffix not in ALLOWED:
        return jsonify(success=False, error="Only PDF and DOCX files are supported."), 400

    # Werkzeug/Flask already strips dangerous paths in most cases; Path.name is an extra guard.
    safe_name = Path(uploaded.filename).name
    destination = UPLOAD_DIR / safe_name
    uploaded.save(destination)

    try:
        profile = process_resume(destination)
        candidates = load_candidates()
        profile_index = next((i for i, c in enumerate(candidates) if c.get("email") == profile.get("email") and profile.get("email") != "Not detected"), 0)
        if not candidates:
            profile_index = 0
        return jsonify(success=True, profile=profile, candidate_index=profile_index, candidate_id=profile.get("candidate_id"), storage="SQLite candidate database", report_url=url_for("analysis_report", index=profile_index), report_download_url=url_for("download_analysis_report", index=profile_index))
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 500


@app.get("/api/candidates")
def api_candidates():
    return jsonify(load_candidates())


@app.get("/api/candidates/export")
def export_candidates():
    candidates = load_candidates()

    if not candidates:
        return jsonify(error="No candidate profiles available for export."), 404

    output = DATA_DIR / "all_candidates.csv"
    profile_to_dataframe(candidates).to_csv(output, index=False)

    return send_file(
        output,
        as_attachment=True,
        download_name="all_candidates.csv",
        mimetype="text/csv"
    )


@app.get("/api/profile/<int:index>/download")
def download_profile(index):
    candidates = load_candidates()
    if not 0 <= index < len(candidates):
        return jsonify(error="Candidate not found."), 404

    output = DATA_DIR / f"candidate_{index + 1}_profile.csv"
    profile_to_dataframe([candidates[index]]).to_csv(output, index=False)
    return send_file(output, as_attachment=True, download_name="candidate_profile.csv", mimetype="text/csv")



# Interview question architecture:
# - Recruiter interview: 10 assessment questions per role.
# - Candidate practice exam: 10 questions per role.
# - Exactly 5/10 (50%) of candidate questions test the same competencies as
#   recruiter questions, but are worded differently. The other 5 are practice-only.
ROLE_QUESTION_PROFILES = {
    "python api developer": {
        "skills": ["Python", "REST APIs", "Django", "SQL"],
        "recruiter": [
            ("technical", "How would you design a versioned REST API in Python for a resource with create, read, update and delete operations?"),
            ("technical", "How would you handle exceptions, logging and validation in a Python API running in production?"),
            ("technical", "How would you investigate and improve a slow SQL query used by an API endpoint?"),
            ("technical", "How would you secure an API against unauthorized access, invalid input and common web vulnerabilities?"),
            ("situational", "An API suddenly starts returning 500 errors after a deployment. What would you check first and how would you communicate the incident?"),
            ("technical", "How would you structure automated unit and API tests for a Python service?"),
            ("technical", "When would you use synchronous versus asynchronous processing in an API?"),
            ("technical", "How would you design pagination, filtering and error responses for a REST endpoint used by many clients?"),
            ("situational", "A new endpoint works locally but is slow in production. Walk through your diagnosis and remediation plan."),
            ("behavioral", "Tell me about a backend problem you solved and how you measured that your solution worked.")
        ],
        "candidate_shared": [
            ("technical", "For practice: explain how you would build a Python REST API with CRUD operations and keep its API versions compatible."),
            ("technical", "For practice: what would you include in Python API error handling, logging and input validation for a production service?"),
            ("technical", "For practice: list the steps you would take to find the cause of a slow SQL query behind an API."),
            ("technical", "For practice: describe practical ways to protect a REST API from unauthorized requests and bad input."),
            ("situational", "For practice: a Python API begins returning 500 errors after release. Describe your troubleshooting sequence.")
        ],
        "candidate_unique": [
            ("technical", "Practice: what is the difference between PUT and PATCH, and when would you use each?"),
            ("technical", "Practice: how would you use Git branches and pull requests while developing an API feature?"),
            ("technical", "Practice: explain how authentication and authorization are different."),
            ("technical", "Practice: how would you return useful HTTP status codes from a REST API?"),
            ("behavioral", "Practice: describe a project where you learned a backend technology quickly.")
        ]
    },
    "backend engineer": {
        "skills": ["Python", "APIs", "SQL", "Git"],
        "recruiter": [
            ("technical", "How would you design a maintainable backend service with clear modules, validation and error handling?"),
            ("technical", "How would you diagnose a backend endpoint whose response time has increased significantly?"),
            ("technical", "How would you design database transactions so partial updates do not leave inconsistent data?"),
            ("technical", "How would you secure authentication, authorization and sensitive data in a backend application?"),
            ("situational", "A production backend is failing for only some users. How would you isolate the issue?"),
            ("technical", "How would you test service logic and database interactions before deployment?"),
            ("technical", "When would you introduce caching, and what consistency problems would you consider?"),
            ("technical", "How would you design an API contract so frontend and backend teams can work independently?"),
            ("situational", "A dependency update breaks an existing service. What would you do before and after rolling back?"),
            ("behavioral", "Describe a backend design decision you made and how you evaluated its trade-offs.")
        ],
        "candidate_shared": [
            ("technical", "Practice: outline how you would organize a backend service so that validation, business logic and errors stay manageable."),
            ("technical", "Practice: what would you inspect when one backend endpoint becomes slow?"),
            ("technical", "Practice: explain how transactions can protect a database from partial updates."),
            ("technical", "Practice: how would you protect users and data with authentication and authorization?"),
            ("situational", "Practice: some users report a backend failure while others are unaffected. How would you investigate?")
        ],
        "candidate_unique": [
            ("technical", "Practice: what is an API endpoint and what makes an API easy for another developer to consume?"),
            ("technical", "Practice: explain indexing in a relational database in simple terms."),
            ("technical", "Practice: when might caching make an application faster?"),
            ("technical", "Practice: what information should a useful application log contain?"),
            ("behavioral", "Practice: tell me about a time you debugged a difficult programming issue.")
        ]
    },
    "data analyst": {
        "skills": ["SQL", "Python", "Pandas", "Power BI", "Excel"],
        "recruiter": [
            ("technical", "How would you clean and validate a new dataset before using it for analysis?"),
            ("technical", "How would you write SQL to find top-performing categories while avoiding duplicate records?"),
            ("technical", "How would you design a Power BI dashboard for a business stakeholder and choose its first KPIs?"),
            ("technical", "What is the difference between a Power BI calculated column and a measure?"),
            ("situational", "A stakeholder's report contains numbers that conflict with the source system. How would you investigate and communicate the issue?"),
            ("technical", "How would you use Pandas to identify missing values, duplicates and unusual records?"),
            ("technical", "How would you check whether an observed change in a KPI is meaningful rather than caused by a data-quality issue?"),
            ("technical", "How would you structure an Excel analysis so another analyst can audit your calculations?"),
            ("situational", "A manager asks for a dashboard by tomorrow but the data is incomplete. What would you deliver and how would you communicate limitations?"),
            ("behavioral", "Tell me about an analysis or dashboard where your findings changed a decision.")
        ],
        "candidate_shared": [
            ("technical", "Practice: describe your checklist for cleaning and validating a dataset before analysis."),
            ("technical", "Practice: explain how you would find top categories in SQL without double-counting rows."),
            ("technical", "Practice: if you were building a Power BI dashboard, how would you select useful KPIs and organize the page?"),
            ("technical", "Practice: explain calculated columns and measures in Power BI with a simple example."),
            ("situational", "Practice: two reports show different numbers for the same KPI. How would you find the reason?")
        ],
        "candidate_unique": [
            ("technical", "Practice: what is the difference between WHERE and HAVING in SQL?"),
            ("technical", "Practice: how would you handle missing values in Pandas?"),
            ("technical", "Practice: which chart would you use to show a monthly trend and why?"),
            ("technical", "Practice: what makes an Excel formula or workbook easy to audit?"),
            ("behavioral", "Practice: explain one data project you completed and the insight you found.")
        ]
    },
    "full stack developer": {
        "skills": ["Python", "Django", "JavaScript", "HTML", "CSS", "SQL"],
        "recruiter": [
            ("technical", "How would you structure a full-stack application from browser to API, business logic and database?"),
            ("technical", "How would you make a web page responsive across desktop, tablet and mobile?"),
            ("technical", "How do HTML, CSS and JavaScript work together when a user submits a form?"),
            ("technical", "How would you design and consume a REST API from a frontend, including error handling?"),
            ("situational", "A full-stack feature works locally but fails after deployment. How would you isolate the layer causing the problem?"),
            ("technical", "How would you protect a web application from common input and authentication risks?"),
            ("technical", "How would you improve a page that loads slowly?"),
            ("technical", "How would you manage database schema changes safely in a Django project?"),
            ("situational", "A requested feature changes the database and frontend. How would you plan testing before release?"),
            ("behavioral", "Describe a full-stack project and the most difficult integration issue you solved.")
        ],
        "candidate_shared": [
            ("technical", "Practice: explain the flow of data through a full-stack web application from the browser to the database."),
            ("technical", "Practice: list the main techniques you would use to make a website responsive."),
            ("technical", "Practice: describe what happens between clicking a form submit button and saving data."),
            ("technical", "Practice: how would a frontend call a REST API and handle success and error responses?"),
            ("situational", "Practice: a web feature works on your laptop but not after deployment. How would you troubleshoot it?")
        ],
        "candidate_unique": [
            ("technical", "Practice: what is the purpose of HTML semantic elements?"),
            ("technical", "Practice: explain the difference between frontend and backend validation."),
            ("technical", "Practice: what is a database migration?"),
            ("technical", "Practice: how would you use browser developer tools to debug a web page?"),
            ("behavioral", "Practice: describe a web project you built and one improvement you would make now.")
        ]
    },
    "qa automation engineer": {
        "skills": ["Testing", "Automation", "Python", "Selenium", "API Testing"],
        "recruiter": [
            ("technical", "How would you create a test plan when requirements are incomplete?"),
            ("technical", "What is the difference between functional, regression, integration and end-to-end testing?"),
            ("technical", "How would you decide which test cases should be automated?"),
            ("technical", "How would you report a defect so a developer can reproduce it quickly?"),
            ("situational", "A critical defect is found just before release. How would you assess risk and communicate it?"),
            ("technical", "How would you design a maintainable UI automation framework?"),
            ("technical", "How would you validate a REST API response during API testing?"),
            ("technical", "How would you reduce flaky automated tests?"),
            ("situational", "Automation passes locally but fails in CI. What would you investigate?"),
            ("behavioral", "Tell me about a defect you found and how you helped the team prevent a recurrence.")
        ],
        "candidate_shared": [
            ("technical", "Practice: how would you plan testing for a feature when some requirements are unclear?"),
            ("technical", "Practice: compare functional, regression, integration and end-to-end tests."),
            ("technical", "Practice: what makes a test case a good candidate for automation?"),
            ("technical", "Practice: what information should be included in a high-quality defect report?"),
            ("situational", "Practice: a serious defect is found before release. What factors would you consider before recommending a release?")
        ],
        "candidate_unique": [
            ("technical", "Practice: what is a flaky test and how can you reduce it?"),
            ("technical", "Practice: how would you test a login page?"),
            ("technical", "Practice: what is the purpose of assertions in automated tests?"),
            ("technical", "Practice: how would you test a REST API without a browser?"),
            ("behavioral", "Practice: describe a time you found an issue others had missed.")
        ]
    },
    "machine learning engineer": {
        "skills": ["Python", "Machine Learning", "Pandas", "NumPy", "Scikit-learn"],
        "recruiter": [
            ("technical", "How would you prepare a dataset for machine learning, including missing values, outliers and categorical features?"),
            ("technical", "How would you choose an evaluation metric for a classification model, and why can accuracy be insufficient?"),
            ("technical", "What is overfitting and what techniques would you use to reduce it?"),
            ("technical", "How would you compare two candidate models and decide which one to deploy?"),
            ("situational", "A model performs well during development but poorly on new production data. How would you investigate?"),
            ("technical", "How would you prevent data leakage during model training?"),
            ("technical", "How would you create a reproducible machine-learning training pipeline?"),
            ("technical", "How would you monitor a deployed model for data drift and performance changes?"),
            ("situational", "A model's precision improves while recall falls. How would you discuss the trade-off with stakeholders?"),
            ("behavioral", "Describe an ML project where you changed your approach after evaluating the first model.")
        ],
        "candidate_shared": [
            ("technical", "Practice: walk through your preprocessing steps before training an ML model."),
            ("technical", "Practice: when might accuracy give a misleading picture of a classification model?"),
            ("technical", "Practice: explain overfitting and give two ways to control it."),
            ("technical", "Practice: what evidence would you use to choose between two trained models?"),
            ("situational", "Practice: a model works well on training or validation data but poorly on new data. What would you check?")
        ],
        "candidate_unique": [
            ("technical", "Practice: explain the difference between classification and regression."),
            ("technical", "Practice: why do we split data into training and testing sets?"),
            ("technical", "Practice: what is feature scaling and when can it matter?"),
            ("technical", "Practice: what is a confusion matrix?"),
            ("behavioral", "Practice: describe an ML project you built and the result you achieved.")
        ]
    },
    "ai engineer": {
        "skills": ["Python", "Artificial Intelligence", "Machine Learning", "NLP", "APIs"],
        "recruiter": [
            ("technical", "How would you design an AI feature from data preparation through model evaluation and API integration?"),
            ("technical", "How would you evaluate whether an AI system is producing useful and reliable outputs?"),
            ("technical", "How would you handle incomplete, noisy or biased training data?"),
            ("technical", "How would you expose an AI model through a production API safely?"),
            ("situational", "An AI feature performs well in testing but produces inconsistent outputs for real users. How would you investigate?"),
            ("technical", "How would you reduce latency and cost in an AI inference pipeline?"),
            ("technical", "How would you log and monitor AI predictions after deployment?"),
            ("technical", "How would you design fallback behavior when an AI service is unavailable?"),
            ("situational", "A model's output is technically valid but does not meet the business requirement. What would you change?"),
            ("behavioral", "Tell me about an AI project where evaluation changed your implementation.")
        ],
        "candidate_shared": [
            ("technical", "Practice: outline the steps for taking an AI idea from data preparation to a working API feature."),
            ("technical", "Practice: what measures would you use to decide whether an AI feature is reliable and useful?"),
            ("technical", "Practice: how would you prepare noisy or incomplete data before using it for AI?"),
            ("technical", "Practice: what should you consider when exposing an AI model through an API?"),
            ("situational", "Practice: an AI feature gives inconsistent results to users although testing looked good. What would you inspect?")
        ],
        "candidate_unique": [
            ("technical", "Practice: what is NLP and give one practical application."),
            ("technical", "Practice: what is inference in a machine-learning system?"),
            ("technical", "Practice: why is monitoring important after deploying an AI model?"),
            ("technical", "Practice: what is the difference between training and inference?"),
            ("behavioral", "Practice: explain an AI project you built in simple terms.")
        ]
    },
    "power bi developer": {
        "skills": ["Power BI", "DAX", "SQL", "Data Modeling", "Excel"],
        "recruiter": [
            ("technical", "How would you design a Power BI data model for multiple business entities and avoid ambiguous relationships?"),
            ("technical", "What is the difference between a DAX measure and calculated column, and how does filter context affect them?"),
            ("technical", "How would you optimize a slow Power BI report?"),
            ("technical", "How would you validate dashboard numbers against the source data?"),
            ("situational", "A stakeholder says a KPI is wrong while the underlying SQL data appears correct. How would you investigate?"),
            ("technical", "How would you choose visuals for trends, comparisons and composition?"),
            ("technical", "How would you implement row-level security for different users?"),
            ("technical", "How would you manage refresh failures and communicate stale-data risk?"),
            ("situational", "A dashboard has too many visuals and users cannot find the important KPIs. How would you improve it?"),
            ("behavioral", "Describe a dashboard you built and how you measured whether stakeholders found it useful.")
        ],
        "candidate_shared": [
            ("technical", "Practice: explain how you would model related business tables in Power BI."),
            ("technical", "Practice: explain measures versus calculated columns and give a situation for each."),
            ("technical", "Practice: list steps you would take when a Power BI report is slow."),
            ("technical", "Practice: how would you verify that a dashboard KPI matches the source system?"),
            ("situational", "Practice: the source data looks correct but a Power BI KPI looks wrong. How would you trace the issue?")
        ],
        "candidate_unique": [
            ("technical", "Practice: what is DAX used for?"),
            ("technical", "Practice: what is a slicer in Power BI?"),
            ("technical", "Practice: what is row-level security?"),
            ("technical", "Practice: which visual would you use for a monthly trend?"),
            ("behavioral", "Practice: describe one Power BI dashboard you have created.")
        ]
    },
    "cloud devops engineer": {
        "skills": ["AWS", "Docker", "CI/CD", "Linux", "Git"],
        "recruiter": [
            ("technical", "How would you deploy an application to the cloud with separate development, testing and production environments?"),
            ("technical", "What would you monitor after deployment and how would you investigate a sudden increase in errors?"),
            ("technical", "How would you design cloud identity, network and data-access controls securely?"),
            ("technical", "How does CI/CD reduce deployment risk and where would you add automated tests?"),
            ("situational", "An application works locally but fails after deployment. What would you check first?"),
            ("technical", "How would you containerize an application and manage configuration separately from the image?"),
            ("technical", "How would you design backups and recovery for a production database?"),
            ("technical", "How would you control infrastructure changes so they are reviewable and repeatable?"),
            ("situational", "A service becomes unavailable during peak traffic. How would you restore it safely and then investigate the root cause?"),
            ("behavioral", "Describe a deployment or automation problem you solved.")
        ],
        "candidate_shared": [
            ("technical", "Practice: describe how you would separate cloud environments for development, testing and production."),
            ("technical", "Practice: which logs and metrics would you inspect when a deployed service starts returning errors?"),
            ("technical", "Practice: what cloud security controls would you consider for identities, networks and data?"),
            ("technical", "Practice: explain how a CI/CD pipeline can reduce deployment mistakes."),
            ("situational", "Practice: software works locally but fails in the cloud. Give a troubleshooting sequence.")
        ],
        "candidate_unique": [
            ("technical", "Practice: what problem does Docker solve?"),
            ("technical", "Practice: why should secrets not be hard-coded in source code?"),
            ("technical", "Practice: what is a CI/CD pipeline?"),
            ("technical", "Practice: what is the purpose of a production backup?"),
            ("behavioral", "Practice: describe a time you automated a repetitive technical task.")
        ]
    },
    "business analyst": {
        "skills": ["SQL", "Excel", "Power BI", "Requirements Analysis", "Communication"],
        "recruiter": [
            ("situational", "How would you gather and validate requirements when different stakeholders want different outcomes?"),
            ("technical", "How would you turn a business problem into measurable KPIs and an analysis plan?"),
            ("technical", "How would you use SQL or Excel to validate a business report?"),
            ("technical", "How would you present an analytical finding to a non-technical stakeholder?"),
            ("situational", "A stakeholder changes requirements near the deadline. How would you assess the impact and respond?"),
            ("technical", "How would you document a process or requirement so developers can implement it accurately?"),
            ("technical", "How would you identify whether a proposed KPI is actually measurable from available data?"),
            ("situational", "Two teams provide conflicting definitions for the same metric. How would you resolve it?"),
            ("behavioral", "Tell me about a time you handled competing priorities."),
            ("behavioral", "Describe a recommendation you made using data or structured analysis.")
        ],
        "candidate_shared": [
            ("situational", "Practice: several stakeholders want different results. How would you gather and reconcile their requirements?"),
            ("technical", "Practice: explain how you would convert a business problem into KPIs and analysis steps."),
            ("technical", "Practice: how could SQL or Excel help you validate a business report?"),
            ("technical", "Practice: how would you explain a data finding to someone without a technical background?"),
            ("situational", "Practice: a stakeholder changes the requirement close to a deadline. What would you do?")
        ],
        "candidate_unique": [
            ("technical", "Practice: what is a business requirement?"),
            ("technical", "Practice: what is the purpose of a process flow?"),
            ("technical", "Practice: how would you prioritize requirements?"),
            ("technical", "Practice: what makes a KPI useful?"),
            ("behavioral", "Practice: describe a situation where you communicated a difficult point clearly.")
        ]
    },
    "frontend developer": {
        "skills": ["HTML", "CSS", "JavaScript", "Responsive Design", "Git"],
        "recruiter": [
            ("technical", "How would you build a responsive page that works consistently across common screen sizes?"),
            ("technical", "How would you structure HTML, CSS and JavaScript so the code remains maintainable?"),
            ("technical", "How would you debug a frontend feature that works in one browser but fails in another?"),
            ("technical", "How would you handle API loading, success, empty and error states in a frontend application?"),
            ("situational", "A page is visually correct but slow. How would you identify the bottleneck?"),
            ("technical", "How would you make a form accessible and validate user input?"),
            ("technical", "How would you reduce unnecessary browser requests and improve page performance?"),
            ("technical", "How would you manage frontend changes with Git in a team?"),
            ("situational", "A new UI change breaks an existing page. How would you isolate and fix the regression?"),
            ("behavioral", "Describe a frontend problem you solved and how you verified the fix.")
        ],
        "candidate_shared": [
            ("technical", "Practice: describe the main techniques you would use to make a page responsive."),
            ("technical", "Practice: how would you organize HTML, CSS and JavaScript for maintainability?"),
            ("technical", "Practice: what would you check if a feature works in Chrome but not another browser?"),
            ("technical", "Practice: how should a frontend handle API loading, success and error states?"),
            ("situational", "Practice: a page looks correct but loads slowly. How would you investigate it?")
        ],
        "candidate_unique": [
            ("technical", "Practice: what are semantic HTML elements?"),
            ("technical", "Practice: what is the CSS box model?"),
            ("technical", "Practice: what is event handling in JavaScript?"),
            ("technical", "Practice: how can browser developer tools help debug CSS?"),
            ("behavioral", "Practice: describe a frontend project you built.")
        ]
    },
    "database sql developer": {
        "skills": ["SQL", "MySQL", "PostgreSQL", "Database Design", "Indexing"],
        "recruiter": [
            ("technical", "How would you design relational tables for a transactional application and choose appropriate keys?"),
            ("technical", "How would you diagnose and optimize a slow SQL query?"),
            ("technical", "When would you normalize tables and when might denormalization be useful?"),
            ("technical", "How would you use transactions to preserve data consistency?"),
            ("situational", "A production query suddenly becomes slow after data volume increases. What would you inspect?"),
            ("technical", "How do indexes improve reads, and what trade-offs do they introduce?"),
            ("technical", "How would you prevent SQL injection in an application?"),
            ("technical", "How would you validate a database migration before applying it to production?"),
            ("situational", "A migration fails halfway through deployment. What would you do to protect data integrity?"),
            ("behavioral", "Describe a database issue you investigated and the result.")
        ],
        "candidate_shared": [
            ("technical", "Practice: explain how you would design relational tables for an application with related entities."),
            ("technical", "Practice: list the steps you would take to optimize a slow SQL query."),
            ("technical", "Practice: explain normalization and one situation where denormalization may be considered."),
            ("technical", "Practice: what does a database transaction protect you from?"),
            ("situational", "Practice: a query becomes slow as the database grows. What would you check?")
        ],
        "candidate_unique": [
            ("technical", "Practice: what is a primary key?"),
            ("technical", "Practice: what is an index?"),
            ("technical", "Practice: explain INNER JOIN versus LEFT JOIN."),
            ("technical", "Practice: what is SQL injection and how can applications prevent it?"),
            ("behavioral", "Practice: describe a database query or project you worked on.")
        ]
    },
    "cybersecurity analyst": {
        "skills": ["Cybersecurity", "Networking", "Linux", "Risk Analysis", "SIEM"],
        "recruiter": [
            ("technical", "How would you investigate an alert that may indicate unauthorized access?"),
            ("technical", "How would you assess risk when a vulnerability is discovered in a business system?"),
            ("technical", "How would you use logs to build a timeline of a security incident?"),
            ("technical", "How would you reduce the impact of compromised credentials?"),
            ("situational", "A suspicious login is detected from an unusual location. What would you investigate before escalating?"),
            ("technical", "How would you explain the difference between vulnerability, threat and risk?"),
            ("technical", "How would you prioritize security findings for remediation?"),
            ("technical", "What information would you expect a SIEM to help correlate?"),
            ("situational", "A phishing incident affects several employees. What immediate steps would you recommend to the response team?"),
            ("behavioral", "Describe a security-learning or lab project and what you learned.")
        ],
        "candidate_shared": [
            ("technical", "Practice: outline how you would investigate a security alert for possible unauthorized access."),
            ("technical", "Practice: how would you assess the risk of a newly discovered vulnerability?"),
            ("technical", "Practice: how can logs help reconstruct a security incident?"),
            ("technical", "Practice: what steps can reduce damage after credentials are compromised?"),
            ("situational", "Practice: a login appears suspicious because of its location. What evidence would you check?")
        ],
        "candidate_unique": [
            ("technical", "Practice: define threat, vulnerability and risk."),
            ("technical", "Practice: what is a SIEM used for?"),
            ("technical", "Practice: what is phishing?"),
            ("technical", "Practice: why is least privilege important?"),
            ("behavioral", "Practice: describe a cybersecurity lab or project you completed.")
        ]
    },
    "product manager": {
        "skills": ["Product Management", "Requirements", "Analytics", "Communication", "Prioritization"],
        "recruiter": [
            ("situational", "How would you prioritize competing product requests when engineering capacity is limited?"),
            ("technical", "How would you define success metrics for a new product feature?"),
            ("situational", "How would you handle conflicting feedback from customers, sales and engineering?"),
            ("technical", "How would you turn a customer problem into a clear product requirement?"),
            ("situational", "A feature has shipped but adoption is low. How would you investigate and decide what to do next?"),
            ("technical", "How would you use product data to identify a meaningful user problem?"),
            ("technical", "How would you write acceptance criteria for a feature?"),
            ("situational", "A high-priority request appears just before a committed release. How would you evaluate it?"),
            ("behavioral", "Tell me about a time you influenced a decision without direct authority."),
            ("behavioral", "Describe a product or project decision that you changed after receiving new evidence.")
        ],
        "candidate_shared": [
            ("situational", "Practice: several important features compete for limited development time. How would you prioritize them?"),
            ("technical", "Practice: what metrics would you choose to tell whether a new feature is successful?"),
            ("situational", "Practice: customers, sales and engineers disagree about a feature. How would you move the discussion forward?"),
            ("technical", "Practice: how would you turn a customer complaint into a clear requirement?"),
            ("situational", "Practice: a released feature has low adoption. What data and feedback would you examine?")
        ],
        "candidate_unique": [
            ("technical", "Practice: what is an acceptance criterion?"),
            ("technical", "Practice: what is an MVP?"),
            ("technical", "Practice: how would you write a simple product requirement?"),
            ("behavioral", "Practice: describe a time you had to prioritize several tasks."),
            ("behavioral", "Practice: explain a project where you coordinated with different people.")
        ]
    },
    "data scientist": {
        "skills": ["Python", "Statistics", "Machine Learning", "SQL", "Pandas"],
        "recruiter": [
            ("technical", "How would you explore a new dataset and identify the variables most relevant to a business question?"),
            ("technical", "How would you choose between different statistical or machine-learning approaches for a problem?"),
            ("technical", "How would you evaluate a predictive model and check for overfitting?"),
            ("technical", "How would you communicate uncertainty in an analysis to a business stakeholder?"),
            ("situational", "A model's offline metrics improve but business outcomes do not. How would you investigate?"),
            ("technical", "How would you use SQL and Pandas together in an analysis workflow?"),
            ("technical", "How would you detect data leakage or sampling bias?"),
            ("technical", "How would you explain a model result to a non-technical audience?"),
            ("situational", "The dataset is small and noisy but a model is still requested. What would you do?"),
            ("behavioral", "Describe an analysis where your initial hypothesis changed after examining the data.")
        ],
        "candidate_shared": [
            ("technical", "Practice: how would you explore a new dataset before choosing a modeling approach?"),
            ("technical", "Practice: what factors would guide your choice of a statistical or ML method?"),
            ("technical", "Practice: how would you evaluate a predictive model and check whether it overfits?"),
            ("technical", "Practice: how would you explain uncertainty in your findings to a business person?"),
            ("situational", "Practice: model metrics improve but the business result does not. What would you investigate?")
        ],
        "candidate_unique": [
            ("technical", "Practice: what is exploratory data analysis?"),
            ("technical", "Practice: explain mean, median and standard deviation."),
            ("technical", "Practice: why can correlation not by itself prove causation?"),
            ("technical", "Practice: what is a train-test split?"),
            ("behavioral", "Practice: describe a data science project and its outcome.")
        ]
    }
}

def _role_key(title):
    key = norm(title)
    aliases = [
        ("python api developer", ["python", "api"]),
        ("backend engineer", ["backend", "back end"]),
        ("data analyst", ["data analyst", "analytics"]),
        ("full stack developer", ["full stack", "fullstack"]),
        ("qa automation engineer", ["qa", "quality", "test", "automation"]),
        ("machine learning engineer", ["machine learning", "ml engineer"]),
        ("ai engineer", ["ai engineer", "artificial intelligence"]),
        ("power bi developer", ["power bi", "bi developer"]),
        ("cloud devops engineer", ["cloud", "devops", "sre", "infrastructure"]),
        ("business analyst", ["business analyst"]),
        ("frontend developer", ["frontend", "front end", "ui developer", "react"]),
        ("database sql developer", ["database", "sql developer", "dba"]),
        ("cybersecurity analyst", ["cybersecurity", "security analyst"]),
        ("product manager", ["product manager"]),
        ("data scientist", ["data scientist"])
    ]
    for canonical, terms in aliases:
        if any(t in key for t in terms):
            return canonical
    return None

def recruiter_questions_for_job(job):
    """Return 40 recruiter questions tailored to the selected role.
    The first questions come from the role profile; the rest are generated from
    the role's required skills and assessment categories so every role has a full set.
    """
    title = (job.get("title") or "this role").strip()
    key = _role_key(title)
    profile = ROLE_QUESTION_PROFILES.get(key)
    base = list(profile["recruiter"]) if profile else []
    skills = skills_from_job(job)
    if not skills and profile:
        skills = profile.get("skills", [])

    # Add role/skill-specific questions with varied wording.
    templates = [
        ("technical", "How would you apply {skill} in a real {title} project?"),
        ("technical", "What are the main implementation considerations when using {skill} for this role?"),
        ("technical", "How would you test or validate work involving {skill}?"),
        ("technical", "What common problem can occur with {skill}, and how would you troubleshoot it?"),
        ("technical", "How would you improve performance or reliability when using {skill}?"),
        ("situational", "A production issue involves {skill}. What steps would you take to diagnose and resolve it?"),
        ("situational", "A stakeholder reports an unexpected result involving {skill}. How would you investigate?"),
        ("behavioral", "Tell me about a project where you used {skill}. What did you contribute and what was the outcome?"),
        ("behavioral", "Describe a challenge you faced while learning or using {skill} and how you handled it."),
        ("behavioral", "How would you explain your work with {skill} to a non-technical stakeholder?"),
    ]
    generated=[]
    for skill in skills[:10]:
        for typ, tmpl in templates:
            generated.append((typ, tmpl.format(skill=skill, title=title)))

    # Role-level questions provide variety beyond individual skills.
    role_templates=[
        ("technical", f"What technical approach would you take when starting a new {title} project?"),
        ("technical", f"How would you review the quality of another person's work in a {title} role?"),
        ("technical", f"How would you troubleshoot a defect that you cannot reproduce consistently in a {title} project?"),
        ("technical", f"How would you document an important technical decision in a {title} project?"),
        ("situational", f"A critical issue appears just before a {title} project deadline. How would you prioritize your response?"),
        ("situational", f"Requirements change after you have started a {title} task. How would you handle the change?"),
        ("situational", f"You receive incomplete information for a {title} assignment. What would you do first?"),
        ("behavioral", f"Tell me about a project that best demonstrates your preparation for a {title} position."),
        ("behavioral", f"Describe a time you received difficult feedback on your work and how you responded."),
        ("behavioral", f"How do you prioritize multiple tasks when working as a {title}?"),
    ]
    generated.extend(role_templates)

    # Deduplicate while preserving order, then fill from base/profile and generated.
    items=[]; seen=set()
    for typ,q in base + generated:
        k=(typ.lower(),q.strip().lower())
        if k not in seen:
            seen.add(k); items.append((typ,q))
        if len(items)>=40: break
    # Absolute fallback if an unusual role has insufficient skills.
    while len(items)<40:
        n=len(items)+1
        typ=("technical" if n%3 else "behavioral")
        items.append((typ, f"Question {n}: How would you demonstrate effective performance in the {title} role?"))
    return [{"id": i+1, "type": typ, "question": q} for i,(typ,q) in enumerate(items[:40])]

def _mcq_bank_for_role(job):
    """Return exactly 20 role-specific MCQs shared by recruiter and candidate portals."""
    title = (job.get("title") or "this role").strip()
    key = _role_key(title) or ""
    banks = {
        "python api developer": [
            ("Which HTTP method is normally used to retrieve a resource?", ["GET","POST","PATCH","DELETE"], 0),
            ("Which status code normally indicates a successful resource creation?", ["200","201","301","404"], 1),
            ("What is the main purpose of request validation in an API?", ["Accept every value","Reject invalid input before processing","Disable authentication","Increase page size"], 1),
            ("Which format is commonly used for REST API request and response bodies?", ["JSON","BMP","EXE","WAV"], 0),
            ("What should an API do when a requested resource does not exist?", ["Return an appropriate 4xx response","Return 200 with random data","Restart the server","Delete the database"], 0),
            ("Which practice helps protect an API from unauthorized access?", ["Authentication and authorization","Removing validation","Using hard-coded passwords","Disabling logs"], 0),
            ("What is a useful reason to version a public API?", ["To support controlled changes without breaking clients","To remove all endpoints","To avoid testing","To hide errors"], 0),
            ("Which Python structure is best suited to store key-value pairs?", ["List","Tuple","Dictionary","Set"], 2),
            ("What is a good way to handle unexpected API failures?", ["Log the error and return a safe response","Expose stack traces to users","Ignore every error","Delete the request"], 0),
            ("Why are automated API tests useful?", ["They verify behavior consistently after changes","They remove the need for code","They guarantee zero bugs","They replace requirements"], 0),
        ],
        "data analyst": [
            ("Which SQL clause groups rows for aggregate calculations?", ["GROUP BY","ORDER BY","WHERE","LIMIT"], 0),
            ("Which function calculates an average in SQL?", ["SUM","AVG","COUNT","MAX"], 1),
            ("What is the main purpose of data cleaning?", ["Improve data quality and consistency","Increase file size","Remove all columns","Hide missing values"], 0),
            ("Which Power BI feature is commonly used to create calculated measures?", ["DAX","HTML","CSS","SMTP"], 0),
            ("What does a primary key identify?", ["A unique row/entity","Every duplicate row","A chart color","A file extension"], 0),
            ("Which visualization is generally suitable for showing a trend over time?", ["Line chart","Pie chart only","Scatterless text","Single KPI only"], 0),
            ("Why should analysts validate source data before reporting?", ["To reduce incorrect conclusions","To make dashboards slower","To remove business context","To avoid documentation"], 0),
            ("Which Pandas operation combines rows from two DataFrames using matching keys?", ["merge","print","sort_index only","describe only"], 0),
            ("What is a KPI?", ["A key performance indicator","A Python package","A database password","A file format"], 0),
            ("Which SQL clause filters rows before grouping?", ["WHERE","ORDER BY","GROUP BY","HAVING only"], 0),
        ],
        "full stack developer": [
            ("Which technology is used to structure content on a web page?", ["HTML","SQL","SMTP","JSON only"], 0),
            ("Which technology is primarily used to style web pages?", ["CSS","SQL","FTP","DAX"], 0),
            ("What does JavaScript commonly add to a web application?", ["Client-side behavior and interactivity","Database backups only","DNS records","Hardware drivers"], 0),
            ("Which HTTP status code represents a successful request?", ["200","404","500","301"], 0),
            ("What is the purpose of a backend API?", ["Provide application data and operations to clients","Only change font colors","Replace the operating system","Format images"], 0),
            ("Why use server-side validation as well as client-side validation?", ["Client checks can be bypassed","It makes HTML invalid","It removes security","It prevents all API calls"], 0),
            ("Which database is relational?", ["MySQL","Redis only","HTML","CSS"], 0),
            ("What does responsive design aim to provide?", ["Usable layouts across screen sizes","Only desktop pages","Only printed pages","Database replication"], 0),
            ("What is version control used for?", ["Tracking code changes","Compressing images only","Hosting DNS","Replacing testing"], 0),
            ("Why separate frontend and backend concerns?", ["To organize responsibilities and maintainability","To remove APIs","To prevent testing","To duplicate every file"], 0),
        ],
        "backend engineer": [
            ("What is a backend service responsible for?", ["Business logic and data operations","Only page colors","Only browser tabs","Monitor brightness"], 0),
            ("Which HTTP method is commonly used to update part of a resource?", ["PATCH","GET","OPTIONS only","TRACE"], 0),
            ("Why use database transactions?", ["To keep related changes consistent","To make queries random","To remove constraints","To disable recovery"], 0),
            ("What is input validation used for?", ["Checking data before processing","Increasing CPU speed","Replacing authentication","Deleting logs"], 0),
            ("What is logging useful for in production?", ["Diagnosing behavior and failures","Storing passwords in plain text","Replacing backups","Hiding incidents"], 0),
            ("What does caching commonly improve?", ["Response time for repeatable data","Password strength","Source-code formatting","Database schema correctness"], 0),
            ("What is a database index designed to improve?", ["Lookup/query performance","Image resolution","HTTP encryption","HTML semantics"], 0),
            ("What is authorization?", ["Checking what an authenticated user is allowed to do","Creating a password","Compressing JSON","Starting a server"], 0),
            ("Why handle exceptions explicitly?", ["To fail safely and provide useful diagnostics","To ignore all errors","To expose secrets","To stop all requests"], 0),
            ("What is an idempotent operation?", ["Repeating it has the same intended effect","It always fails","It requires a browser","It changes every record"], 0),
        ],
        "qa automation engineer": [
            ("What is the purpose of an automated regression test?", ["Check that existing behavior still works","Replace requirements","Create production data","Disable releases"], 0),
            ("Why are explicit waits useful in UI automation?", ["They wait for required conditions","They make tests random","They skip assertions","They delete cookies"], 0),
            ("What is a test assertion?", ["A check that actual behavior matches expected behavior","A deployment script","A password","A browser extension"], 0),
            ("What should a good automated test be?", ["Repeatable and isolated where practical","Random and stateful","Dependent on manual clicks","Without expected results"], 0),
            ("What is smoke testing?", ["A quick check that critical functions work","Testing every edge case","Load testing only","Security scanning only"], 0),
            ("Why use test data management?", ["To make tests predictable and maintainable","To hide defects","To remove assertions","To disable CI"], 0),
            ("What does CI commonly do?", ["Automatically build and test changes","Only create UI designs","Replace source control","Delete test reports"], 0),
            ("What is a flaky test?", ["A test that passes and fails inconsistently without intended code changes","A permanently failing test","A security test","A unit test with no assertions"], 0),
            ("Why test negative scenarios?", ["To verify safe behavior for invalid inputs and failures","To reduce coverage","To avoid validation","To increase defects"], 0),
            ("What is regression testing focused on?", ["Detecting unintended effects of changes","Designing logos","Creating resumes","Managing payroll"], 0),
        ],
        "machine learning engineer": [
            ("Why split data into training and test sets?", ["To evaluate generalization on unseen data","To increase labels","To remove features","To avoid metrics"], 0),
            ("What is overfitting?", ["A model learns training data too closely and generalizes poorly","A model has no features","A database error","A UI defect"], 0),
            ("Which metric is commonly used for regression?", ["Mean squared error","Accuracy only","Precision only","Recall only"], 0),
            ("What does feature scaling help with?", ["Putting numeric features on comparable scales for suitable algorithms","Deleting labels","Creating APIs","Encrypting models"], 0),
            ("What is cross-validation used for?", ["Estimating model performance across different data splits","Deploying servers","Parsing PDFs","Creating SQL tables"], 0),
            ("Why keep a test set untouched until evaluation?", ["To reduce leakage into final evaluation","To train twice","To increase bias","To remove predictions"], 0),
            ("What is a hyperparameter?", ["A setting chosen outside the learned model parameters","A target label","A database row","An HTML element"], 0),
            ("What is data leakage?", ["Information from outside the training process improperly influences learning/evaluation","Missing CSS","Slow APIs","A broken dashboard"], 0),
            ("Why monitor a deployed ML model?", ["Data and model performance can change over time","Models never change","Monitoring replaces testing","It removes the need for data"], 0),
            ("What is precision measuring?", ["The fraction of predicted positives that are correct","All actual positives","Training time","CPU usage"], 0),
        ],
        "ai engineer": [
            ("What is an embedding?", ["A numeric representation capturing useful semantic relationships","A database password","A CSS class","A network cable"], 0),
            ("Why evaluate an AI model on representative examples?", ["To measure behavior on relevant inputs","To increase file size","To avoid validation","To remove prompts"], 0),
            ("What is prompt engineering?", ["Designing instructions and context to guide a model","Training a CPU","Creating database indexes","Styling a page"], 0),
            ("What is hallucination in generative AI?", ["A confident but unsupported or incorrect generated response","A faster API","A database backup","A UI animation"], 0),
            ("Why use retrieval-augmented generation?", ["To provide relevant external knowledge to generation","To remove all context","To disable search","To replace evaluation"], 0),
            ("What is a model evaluation set?", ["Data used to assess model behavior","A production password","A CSS file","A network port"], 0),
            ("Why protect sensitive prompts and outputs?", ["They may contain confidential information","They improve font size","They reduce latency automatically","They replace authentication"], 0),
            ("What is temperature commonly used for in text generation?", ["Controlling randomness of sampling","Changing screen color","Changing database schema","Encrypting requests"], 0),
            ("Why log model inputs and outputs carefully?", ["For debugging and evaluation while respecting privacy","To expose secrets","To disable monitoring","To avoid testing"], 0),
            ("What is grounding an AI response?", ["Connecting the response to trusted, relevant evidence or context","Removing context","Randomizing answers","Disabling retrieval"], 0),
        ],
        "power bi developer": [
            ("Which language is used for Power BI measures?", ["DAX","Python only","HTML","CSS"], 0),
            ("What is a Power BI measure?", ["A calculation evaluated in filter context","A database server","A CSS rule","A PDF parser"], 0),
            ("What does a slicer do?", ["Lets users filter report data interactively","Creates a database","Writes Python code","Deploys a server"], 0),
            ("Why model relationships between tables?", ["To connect related data for analysis","To change colors","To remove all keys","To create passwords"], 0),
            ("What is a dashboard KPI useful for?", ["Quickly communicating an important performance measure","Replacing all reports","Storing raw PDFs","Running APIs"], 0),
            ("Why avoid unnecessary columns in a model?", ["To reduce model complexity and improve performance","To hide all data","To disable filters","To prevent refresh"], 0),
            ("What is Power Query mainly used for?", ["Data extraction and transformation","Browser automation","CSS styling","API authentication only"], 0),
            ("Why validate a dashboard against source data?", ["To ensure reported values are accurate","To make charts decorative","To remove relationships","To avoid testing"], 0),
            ("What does filter context affect?", ["How DAX calculations are evaluated","Only page colors","File names","User passwords"], 0),
            ("What is a report visual?", ["A chart or visual element used to communicate data","A server process","A Python package","A database key"], 0),
        ],
        "cloud devops engineer": [
            ("What is CI primarily intended to automate?", ["Building and testing code changes","Writing resumes","Changing monitor brightness","Deleting repositories"], 0),
            ("What is CD commonly associated with?", ["Automated delivery or deployment of software","Manual database typing","UI design only","Resume parsing"], 0),
            ("Why use infrastructure as code?", ["To define infrastructure in repeatable, versioned configuration","To remove automation","To avoid documentation","To hide resources"], 0),
            ("What is containerization useful for?", ["Packaging applications with consistent runtime dependencies","Creating spreadsheets","Writing CSS","Replacing monitoring"], 0),
            ("What is monitoring used for?", ["Observing system health and performance","Changing source code automatically","Removing logs","Creating resumes"], 0),
            ("Why use health checks?", ["To determine whether a service is functioning as expected","To change passwords","To create HTML","To replace backups"], 0),
            ("What is a deployment rollback?", ["Returning to a previous known-good version","Deleting all versions","Changing a logo","Removing tests"], 0),
            ("Why store secrets outside source code?", ["To reduce accidental exposure of credentials","To make code longer","To disable authentication","To avoid environment variables"], 0),
            ("What is autoscaling?", ["Adjusting resources based on demand or policy","Changing source code style","Creating database keys","Removing monitoring"], 0),
            ("Why automate repetitive operational tasks?", ["To improve consistency and reduce manual errors","To prevent logging","To remove tests","To increase duplication"], 0),
        ],
        "business analyst": [
            ("What is a requirement?", ["A documented need or expectation the solution should address","A server password","A CSS property","A test log"], 0),
            ("What are acceptance criteria?", ["Conditions used to determine whether a requirement is satisfied","A database backup","A deployment server","A chart color"], 0),
            ("Why clarify ambiguous requirements?", ["To reduce misunderstandings and rework","To avoid stakeholders","To remove testing","To delay every task"], 0),
            ("What is stakeholder analysis used for?", ["Understanding affected parties and their needs","Creating source code","Encrypting files","Changing UI colors"], 0),
            ("What is a process map?", ["A visual representation of workflow steps","A database index","A Python object","A network cable"], 0),
            ("Why validate requirements with stakeholders?", ["To confirm they reflect actual business needs","To remove acceptance criteria","To avoid feedback","To increase ambiguity"], 0),
            ("What is prioritization used for?", ["Deciding which requirements or work should be addressed first","Deleting requirements","Changing passwords","Testing only UI colors"], 0),
            ("What is a user story commonly used to describe?", ["A user need from a user's perspective","A database schema only","A server log","A CSS rule"], 0),
            ("Why document assumptions?", ["To make dependencies and decisions visible","To hide risks","To remove requirements","To prevent communication"], 0),
            ("What is traceability useful for?", ["Linking requirements to implementation and testing","Changing file names","Replacing stakeholders","Removing documentation"], 0),
        ],
        "frontend developer": [
            ("What does the DOM represent?", ["The structured document tree of a web page","A database server","A network protocol","A Python package"], 0),
            ("Which technology primarily styles web pages?", ["CSS","SQL","DAX","SMTP"], 0),
            ("Which technology adds browser-side logic?", ["JavaScript","SQL","Docker","PostgreSQL"], 0),
            ("What is responsive design?", ["Design that adapts to different screen sizes","Only desktop design","Database scaling","API versioning"], 0),
            ("Why use semantic HTML?", ["To improve structure, accessibility, and meaning","To encrypt content","To speed databases","To replace CSS"], 0),
            ("What is client-side validation useful for?", ["Giving immediate feedback before submission","Replacing server validation completely","Disabling APIs","Deleting data"], 0),
            ("What is an event handler?", ["Code that responds to an event such as a click","A database table","A server certificate","A CSS file"], 0),
            ("Why optimize frontend assets?", ["To improve loading and user experience","To remove accessibility","To disable caching","To prevent testing"], 0),
            ("What is accessibility testing concerned with?", ["Ensuring people with different abilities can use the interface","Only database speed","Only API security","Only image size"], 0),
            ("Why test a UI across browsers?", ["To detect browser-specific behavior differences","To remove JavaScript","To avoid responsive design","To change SQL"], 0),
        ],
        "database sql developer": [
            ("Which SQL command retrieves rows?", ["SELECT","INSERT","DROP","GRANT"], 0),
            ("Which SQL operation combines related rows from tables?", ["JOIN","DELETE","TRUNCATE","RENAME"], 0),
            ("What is a primary key?", ["A unique identifier for rows","A chart title","A password","A view color"], 0),
            ("Why use indexes?", ["To speed suitable lookups and queries","To encrypt tables","To replace backups","To remove constraints"], 0),
            ("Which clause filters grouped results?", ["HAVING","WHERE only","ORDER BY","SELECT"], 0),
            ("What does normalization aim to reduce?", ["Unnecessary data redundancy and update anomalies","All indexes","All queries","Security"], 0),
            ("What is a foreign key?", ["A column that references a key in another table","A password","A chart","A Python list"], 0),
            ("Why use transactions?", ["To keep related database changes consistent","To delete indexes","To avoid backups","To remove constraints"], 0),
            ("What does ORDER BY do?", ["Sorts query results","Groups rows","Creates a table","Deletes rows"], 0),
            ("What is a database constraint?", ["A rule that enforces data integrity","A UI color","An API route","A PDF page"], 0),
        ],
        "cybersecurity analyst": [
            ("What does least privilege mean?", ["Give users only the access they need","Give everyone admin access","Disable passwords","Allow every network port"], 0),
            ("What is phishing?", ["A social-engineering attempt to obtain information or access","A database index","A backup method","A UI framework"], 0),
            ("Why use multi-factor authentication?", ["It adds an additional verification factor","It removes passwords","It disables logging","It exposes credentials"], 0),
            ("What is encryption used for?", ["Protecting information by transforming it into an unreadable form without the key","Deleting logs","Creating UI styles","Replacing backups"], 0),
            ("What is a vulnerability?", ["A weakness that could be exploited","A successful backup","A dashboard chart","A normal login"], 0),
            ("Why patch systems?", ["To address known bugs and security weaknesses","To remove authentication","To disable monitoring","To create users"], 0),
            ("What is a security log useful for?", ["Investigating events and detecting suspicious activity","Changing CSS","Creating resumes","Removing audit trails"], 0),
            ("What is input sanitization intended to reduce?", ["Risk from unsafe or unexpected input","Network speed","Screen size","Database storage"], 0),
            ("Why segment networks?", ["To limit the spread and reach of threats","To remove encryption","To avoid access control","To disable monitoring"], 0),
            ("What is incident response?", ["A structured process for handling security incidents","A frontend framework","A database query","A resume parser"], 0),
        ],
        "product manager": [
            ("What is a product requirement?", ["A defined need or capability the product should address","A server password","A CSS class","A database index"], 0),
            ("What are acceptance criteria?", ["Conditions that define when work is acceptable","A design color","A deployment key","A database backup"], 0),
            ("Why prioritize product work?", ["To focus limited resources on the most important needs","To avoid stakeholders","To remove feedback","To build everything at once"], 0),
            ("What is a user story?", ["A concise description of a user need","A server log","A SQL index","A CSS rule"], 0),
            ("Why use product metrics?", ["To measure outcomes and inform decisions","To replace user research","To remove testing","To hide failures"], 0),
            ("What is an MVP?", ["A minimum viable product used to test a core value proposition","A maximum feature product","A database","A security protocol"], 0),
            ("Why gather user feedback?", ["To understand needs and validate product decisions","To remove requirements","To avoid iteration","To disable analytics"], 0),
            ("What is a product roadmap?", ["A high-level view of planned product direction and work","A database schema","A server password","A test script"], 0),
            ("How should conflicting stakeholder requests be handled?", ["Clarify goals, constraints, evidence, and priorities","Accept all without discussion","Ignore everyone","Delete requirements"], 0),
            ("Why define success metrics before launch?", ["To make outcomes measurable","To avoid data","To remove accountability","To prevent testing"], 0),
        ],
        "data scientist": [
            ("Why split data into training and test sets?", ["To evaluate performance on unseen data","To remove features","To avoid metrics","To duplicate labels"], 0),
            ("What is a classification problem?", ["Predicting categories or classes","Only predicting continuous numbers","Only sorting rows","Only storing text"], 0),
            ("Which metric is common for regression?", ["Mean absolute error","Accuracy only","Recall only","F1 only"], 0),
            ("What is feature engineering?", ["Creating or transforming useful model inputs","Deleting all columns","Deploying servers","Writing CSS"], 0),
            ("Why inspect missing values?", ["They can affect analysis and model behavior","They always improve models","They are never relevant","They replace labels"], 0),
            ("What is a baseline model?", ["A simple reference used for comparison","A production server","A database backup","A UI component"], 0),
            ("What is correlation?", ["A measure of association between variables","Proof of causation","A deployment tool","A file format"], 0),
            ("Why use cross-validation?", ["To estimate model performance across multiple splits","To encrypt data","To create dashboards","To replace cleaning"], 0),
            ("What is data leakage?", ["Using information that should not be available during training/evaluation","A missing value","A slow query","A broken chart"], 0),
            ("Why communicate uncertainty in analysis?", ["To make conclusions and limitations clear","To hide assumptions","To remove evidence","To avoid stakeholders"], 0),
        ],
    }
    rows = banks.get(key, [])
    if len(rows) < 20:
        skills = skills_from_job(job) or [title]
        fallback = [
            ("What is a good practice when working with {skill}?", ["Validate, test, document, and monitor the work","Skip validation","Ignore requirements","Disable logging"], 0),
            ("Why should {skill} work be tested before release?", ["To detect defects before users are affected","To avoid feedback","To remove documentation","To guarantee no future changes"], 0),
        ]
        i=0
        while len(rows)<20:
            skill=skills[i%len(skills)]
            q,opts,idx=fallback[i%len(fallback)]
            rows.append((q.format(skill=skill), opts, idx)); i+=1
    out=[]
    for i,(q,opts,idx) in enumerate(rows[:20]):
        out.append({"id": i+21, "type":"mcq", "question":q, "options":opts, "answer_index":idx, "correct_answer":opts[idx]})
    return out


def shared_40_questions_for_job(job):
    """Single canonical 40-question bank used by recruiter and candidate portals."""
    descriptive = recruiter_questions_for_job(job)[:20]
    descriptive = [{**q, "id": i+1, "type":"descriptive"} for i,q in enumerate(descriptive)]
    mcqs = _mcq_bank_for_role(job)
    return descriptive + [{**q, "id": i+21} for i,q in enumerate(mcqs)]


def candidate_practice_questions_for_job(job):
    return shared_40_questions_for_job(job)


@app.get("/interview", endpoint="interview_page")
def interview_page():
    jobs = load_jobs()
    candidates = load_candidates()
    return render_template("interview.html", jobs=jobs, candidates=candidates)


@app.get("/api/candidate-interview/questions/<job_id>")
def candidate_interview_questions(job_id):
    try:
        job = next(
            (
                j for j in load_jobs()
                if str(j.get("id", "")).strip() == str(job_id).strip()
            ),
            None
        )

        if not job:
            return jsonify(
                success=False,
                error=f"Job not found: {job_id}"
            ), 404

        questions = candidate_practice_questions_for_job(job)

        if not isinstance(questions, list):
            return jsonify(
                success=False,
                error="Question generator did not return a list."
            ), 500

        if len(questions) != 40:
            return jsonify(
                success=False,
                error=f"Expected 40 questions, but generated {len(questions)}."
            ), 500

        return jsonify(
            success=True,
            audience="candidate",
            job=job,
            questions=questions,
            question_count=40,
            total_questions=40,
            overlap_percentage=100,
            note="Exactly the same 40 questions are used in the Recruiter Portal and Candidate Portal."
        )

    except Exception as exc:
        app.logger.exception("Candidate interview question generation failed")

        return jsonify(
            success=False,
            error=f"Candidate interview question generation failed: {type(exc).__name__}: {exc}"
        ), 500
        

@app.get("/api/voice-screening/questions/<job_id>")
def voice_screening_questions(job_id):
    job = next((j for j in load_jobs() if str(j.get("id", "")) == str(job_id)), None)
    if not job:
        return jsonify(success=False, error="Job not found."), 404
    # Voice screening uses the descriptive half of the canonical bank.
    questions = shared_40_questions_for_job(job)[:20]
    return jsonify(success=True, job=job, questions=questions, question_count=20)


@app.get("/voice-screening")
def voice_screening_page():
    return render_template("voice_screening.html", jobs=load_jobs(), candidates=load_candidates())


@app.post("/api/voice-screening/save")
def save_voice_screening():
    payload = request.get_json(silent=True) or {}
    answer = str(payload.get("answer") or "").strip()
    question = str(payload.get("question") or "").strip()
    candidate = str(payload.get("candidate") or "Unknown Candidate").strip()
    job = str(payload.get("job") or "Unknown Job").strip()
    if not answer:
        return jsonify(success=False, error="Please provide an answer before saving."), 400
    words = re.findall(r"\b[\w+#.-]+\b", answer)
    score = min(100, 40 + min(len(words), 60))
    feedback = "Good response. Add a concrete example and measurable outcome where possible." if len(words) >= 25 else "Add more detail, explain your steps clearly, and include a concrete example."
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candidate": candidate, "job": job, "question": question, "answer": answer,
        "score": score, "feedback": feedback, "input_source": payload.get("input_source", "voice"),
    }
    path = DATA_DIR / "voice_screening_results.json"
    rows = _read_json_file(path, [])
    rows.append(row)
    path.write_text(json.dumps(rows[-500:], indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify(success=True, result=row)


@app.get("/candidate-interview")
def candidate_interview_page():
    jobs = load_jobs()
    return render_template("candidate_interview.html", jobs=jobs)





def _local_ai_evaluate(job, questions, answers):
    """Dependency-free AI-style interview evaluator used for the demo.

    It evaluates every answer against the role skills and question vocabulary,
    then produces structured feedback. If an external LLM is configured,
    ``ai_evaluate_interview`` can replace this result with a real LLM result.
    """
    skills = [str(x).strip() for x in (job.get("required_skills") or []) if str(x).strip()]
    role_words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", str(job.get("title", "" )).casefold()))
    results = []
    total = 0
    strengths = []
    improvements = []
    for i, q in enumerate(questions):
        answer = str(answers[i] if i < len(answers) else "").strip()
        if not answer:
            results.append({"id": q["id"], "score": 0, "feedback": ["No answer submitted. Answer every question to get a meaningful practice score."], "technical_relevance": 0, "communication": 0, "structure": 0, "answered": False})
            improvements.append(f"Question {q['id']}: provide an answer instead of leaving it blank.")
            continue

        if q.get("type") == "mcq":
            correct = str(q.get("correct_answer") or "").strip()
            is_correct = answer.strip() == correct
            score = 100 if is_correct else 0
            results.append({"id": q["id"], "score": score,
                            "feedback": ["Correct answer." if is_correct else f"Incorrect. Correct answer: {correct}"],
                            "technical_relevance": score, "communication": score, "structure": score,
                            "specificity": score, "answered": True})
            if is_correct:
                strengths.append(f"Question {q['id']}: correct MCQ response.")
            else:
                improvements.append(f"Question {q['id']}: review the concept tested by this MCQ.")
            total += score
            continue

        answer_norm = norm(answer)
        question_norm = norm(q.get("question", ""))
        answer_tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", answer_norm))
        question_tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", question_norm))
        skill_hits = [skill for skill in skills if norm(skill) in answer_norm]
        vocab_overlap = len(answer_tokens & question_tokens)
        word_count = len(re.findall(r"\b[\w+#.-]+\b", answer))
        structure_terms = ["because", "therefore", "first", "then", "finally", "result", "impact", "example", "implemented", "tested", "measured", "learned"]
        structure_hits = sum(1 for term in structure_terms if re.search(rf"\b{re.escape(term)}\b", answer_norm))

        relevance = min(100, 35 + len(skill_hits) * 15 + min(vocab_overlap * 4, 30))
        communication = min(100, 35 + min(word_count, 120) // 2)
        structure = min(100, 35 + structure_hits * 9 + (10 if word_count >= 45 else 0))
        specificity = min(100, 30 + (20 if word_count >= 40 else 0) + (15 if any(x in answer_norm for x in ["project", "example", "system", "result"]) else 0))
        score = round(relevance * 0.35 + communication * 0.20 + structure * 0.25 + specificity * 0.20)

        feedback = []
        if relevance < 60:
            feedback.append("Connect your answer more directly to the role, question, or required skills.")
        if communication < 65:
            feedback.append("Add enough detail to explain your reasoning clearly.")
        if structure < 65:
            feedback.append("Use a clear Situation → Action → Result or step-by-step structure.")
        if specificity < 65:
            feedback.append("Include a concrete example, action, tool, or measurable result.")
        if not feedback:
            feedback.append("Strong practice response. Keep it specific and support your explanation with evidence.")

        if score >= 75:
            strengths.append(f"Question {q['id']}: clear and relevant response.")
        elif score < 60:
            improvements.append(f"Question {q['id']}: improve relevance, structure, and specificity.")

        results.append({"id": q["id"], "score": score, "feedback": feedback,
                        "technical_relevance": relevance, "communication": communication,
                        "structure": structure, "specificity": specificity, "answered": True})
        total += score

    overall = round(total / max(len(questions), 1))
    if not strengths:
        strengths.append("Keep practising complete answers and use concrete examples.")
    if not improvements:
        improvements.append("Continue practising concise, role-specific answers.")
    return {"overall_score": overall, "strengths": strengths[:5], "improvements": improvements[:5], "per_question": results}


def _extract_llm_json(raw):
    """Extract structured JSON from common OpenAI-compatible responses."""
    content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in content)
    content = str(content).strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I | re.S).strip()
    result = json.loads(content)
    if not isinstance(result, dict) or "overall_score" not in result or "per_question" not in result:
        raise ValueError("AI response did not contain the required evaluation JSON")
    return result


def ai_evaluate_interview(job, questions, answers):
    """Use a configured OpenAI-compatible LLM; otherwise use the built-in evaluator.

    The built-in evaluator means the demo remains fully functional without an API key.
    When AI_API_URL and AI_API_KEY are supplied, the returned mode is ``ai-llm``.
    """
    if not (AI_API_URL and AI_API_KEY and AI_API_KEY.lower() not in {"your_api_key_here", "changeme"}):
        return _local_ai_evaluate(job, questions, answers), "ai-local"
    prompt = {
        "role": job.get("title", "Unknown role"),
        "required_skills": job.get("required_skills", []),
        "instructions": "Evaluate objectively. Return JSON only with overall_score (0-100), strengths (array), improvements (array), and per_question (array of objects containing id, score, feedback, technical_relevance, communication, structure, specificity).",
        "questions_and_answers": [
            {"id": q["id"], "question": q["question"], "answer": answers[i] if i < len(answers) else ""}
            for i, q in enumerate(questions)
        ]
    }
    body = json.dumps({
        "model": AI_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "You are an interview evaluator. Return valid JSON only."},
            {"role": "user", "content": json.dumps(prompt)}
        ],
        "response_format": {"type": "json_object"}
    }).encode()
    try:
        req=urllib.request.Request(AI_API_URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json", "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw=json.loads(resp.read().decode("utf-8"))
        return _extract_llm_json(raw), "ai-llm"
    except Exception:
        # Never break the interview because an optional external AI service failed.
        return _local_ai_evaluate(job, questions, answers), "ai-local-fallback"

@app.post("/api/candidate-interview/submit")
def submit_candidate_interview():
    payload = request.get_json(silent=True) or {}

    job_id = str(payload.get("job_id") or "").strip()
    answers = payload.get("answers") or []

    if not job_id:
        return jsonify(
            success=False,
            error="Invalid job selection."
        ), 400

    job = next(
        (j for j in load_jobs()
         if str(j.get("id", "")).strip() == job_id),
        None
    )

    if not job:
        return jsonify(
            success=False,
            error="Job not found."
        ), 404
    if not job:
        return jsonify(success=False, error="Job not found."), 404
    questions = candidate_practice_questions_for_job(job)
    if not isinstance(answers, list):
        return jsonify(success=False, error="Answers must be a list."), 400

    ai_result, evaluation_mode = ai_evaluate_interview(job, questions, answers)
    return jsonify(success=True, job=job, overall_score=int(ai_result.get("overall_score", 0)),
                   answered=sum(1 for a in answers if str(a).strip()), total_questions=len(questions),
                   results=ai_result.get("per_question", []), strengths=ai_result.get("strengths", []),
                   improvements=ai_result.get("improvements", []), evaluation_mode=evaluation_mode)



INTERVIEW_SESSIONS_FILE = DATA_DIR / "interview_sessions.json"

def _load_interview_sessions():
    try:
        if INTERVIEW_SESSIONS_FILE.exists():
            data=json.loads(INTERVIEW_SESSIONS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []

def _save_interview_sessions(rows):
    INTERVIEW_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    INTERVIEW_SESSIONS_FILE.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

@app.post("/api/interview/save-answer")
def save_interview_answer():
    payload=request.get_json(silent=True) or {}
    session_id=str(payload.get("session_id") or "").strip()
    if not session_id:
        session_id=f"recruiter-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    row={
        "session_id":session_id,
        "candidate":payload.get("candidate") or {},
        "job":payload.get("job") or {},
        "question_id":payload.get("question_id"),
        "question":str(payload.get("question") or ""),
        "answer":str(payload.get("answer") or ""),
        "score":int(payload.get("score") or 0),
        "feedback":payload.get("feedback") or [],
        "metrics":payload.get("metrics") or {},
        "saved_at":datetime.now(timezone.utc).isoformat(),
    }
    sessions=_load_interview_sessions()
    sessions.append(row)
    _save_interview_sessions(sessions)
    return jsonify(success=True, session_id=session_id, saved=True, saved_at=row["saved_at"])

@app.post("/api/interview/evaluate")
def evaluate_interview():
    payload = request.get_json(silent=True) or {}
    answer = str(payload.get("answer", "")).strip()
    question = str(payload.get("question", "")).strip()
    skills = [str(x).strip() for x in (payload.get("skills") or []) if str(x).strip()]
    role = str(payload.get("role") or "Interview role").strip()
    if not answer:
        return jsonify(success=False, error="Please enter an answer before evaluating."), 400
    q = {"id": 1, "type": "interview", "question": question or "Explain your approach."}
    result, mode = ai_evaluate_interview({"title": role, "required_skills": skills}, [q], [answer])
    item = (result.get("per_question") or [{}])[0]
    return jsonify(success=True, score=int(item.get("score", result.get("overall_score", 0))),
                   feedback=item.get("feedback", []),
                   metrics={"technical_relevance": int(item.get("technical_relevance", 0)),
                            "communication": int(item.get("communication", 0)),
                            "structure": int(item.get("structure", 0))},
                   evaluation_mode=mode)


# Milestone 3 mock ATS API endpoints. These mirror the FastAPI example in the project brief
# while keeping the main application on Flask. A standalone FastAPI mock is also provided
# in mock_ats_api.py for integration demos.
MOCK_ATS_FILE = DATA_DIR / "mock_ats_candidates.json"

DEMO_JOB_TITLES = [
    "Python API Developer", "Data Analyst", "Full Stack Developer",
    "Backend Engineer", "QA Automation Engineer", "Machine Learning Engineer",
    "AI Engineer", "Power BI Developer", "Cloud DevOps Engineer",
    "Business Analyst", "Frontend Developer", "Database SQL Developer",
    "Cybersecurity Analyst", "Product Manager", "Data Scientist"
]

def _demo_job_for_candidate(candidate, index=0):
    """Return the candidate's applied job, or a stable demo job when none exists."""
    existing = str(candidate.get("job_applied") or "").strip()
    if existing:
        return existing
    return DEMO_JOB_TITLES[index % len(DEMO_JOB_TITLES)]

def _ensure_demo_job_assignments(rows):
    """Keep demo ATS records useful for presentations by avoiding one job for every row.

    Real candidate records with an explicit job_applied value are preserved. If an
    older demo run stored several candidates under the same generic job, diversify
    only those legacy rows using the project's available job titles.
    """
    if len(rows) < 2:
        return rows
    jobs = [str(r.get("job_applied") or "").strip() for r in rows]
    nonempty = [j for j in jobs if j]
    if nonempty and len(set(nonempty)) == 1:
        for i, row in enumerate(rows):
            row["job_applied"] = DEMO_JOB_TITLES[i % len(DEMO_JOB_TITLES)]
    else:
        for i, row in enumerate(rows):
            if not str(row.get("job_applied") or "").strip():
                row["job_applied"] = DEMO_JOB_TITLES[i % len(DEMO_JOB_TITLES)]
    return rows

def _load_mock_ats():
    try:
        rows = json.loads(MOCK_ATS_FILE.read_text(encoding="utf8"))
        if not isinstance(rows, list):
            return []
        normalized = _ensure_demo_job_assignments(rows)
        if normalized != rows:
            _save_mock_ats(normalized)
        return normalized
    except Exception:
        return []

def _save_mock_ats(rows):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MOCK_ATS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=2), encoding="utf8")
    tmp.replace(MOCK_ATS_FILE)

@app.post("/api/ats/add_candidate")
def mock_ats_add_candidate():
    """Create or update a candidate in the bundled ATS API.

    The endpoint behaves like a real ATS upsert: email is the stable external
    identifier, so syncing the same candidate never creates duplicates.
    """
    payload=request.get_json(silent=True) or {}
    required=["name","email","job_applied","status"]
    missing=[x for x in required if not str(payload.get(x,"")).strip()]
    if missing:
        return jsonify(success=False,error=f"Missing fields: {', '.join(missing)}"),400
    rows=_load_mock_ats()
    email=str(payload.get("email","")).strip().casefold()
    row={k:payload.get(k,"") for k in required}
    row.update({"email":str(row["email"]).strip(),"name":str(row["name"]).strip(),"job_applied":str(row["job_applied"]).strip(),"status":str(row["status"]).strip()})
    existing=next((i for i,r in enumerate(rows) if str(r.get("email","")).strip().casefold()==email),None)
    if existing is None:
        row["created_at"]=datetime.now().isoformat(timespec="seconds")
        rows.append(row); action="created"
    else:
        rows[existing].update(row); row=rows[existing]; action="updated"
    row["updated_at"]=datetime.now().isoformat(timespec="seconds")
    _save_mock_ats(rows)
    return jsonify(success=True,action=action,candidate=row,message=f"Candidate {row['name']} {action} in ATS.")
@app.get("/api/ats/list_candidates")
def mock_ats_list_candidates():
    return jsonify(_load_mock_ats())

@app.put("/api/ats/update_status/<path:email>")
def mock_ats_update_status(email):
    payload=request.get_json(silent=True) or {}
    status=str(payload.get("status","")).strip()
    rows=_load_mock_ats()
    for candidate in rows:
        if candidate.get("email"," ").casefold()==email.casefold():
            candidate["status"]=status; _save_mock_ats(rows)
            return jsonify(message=f"Status updated for {email} to {status}", candidate=candidate)
    return jsonify(error="Candidate not found"),404

@app.get("/api/ats/candidates")
def ats_candidates():
    """Unified candidate-management API used by the ATS dashboard."""
    cfg=load_ats_config() if ATS_FILE.exists() else {"provider":"Demo ATS","base_url":""}
    if str(cfg.get("provider","Demo ATS")).strip().casefold()=="demo ats" or not cfg.get("base_url"):
        response=jsonify(success=True,mode="demo",provider="Demo ATS",candidates=_load_mock_ats())
        response.headers["Cache-Control"]="no-store"
        return response
    try:
        endpoint=_external_candidate_endpoint(cfg["base_url"])
        req=urllib.request.Request(endpoint,headers={"Authorization":f"Bearer {cfg.get('api_key','')}","Accept":"application/json"})
        with urllib.request.urlopen(req,timeout=10) as resp:
            data=json.loads(resp.read().decode("utf-8") or "{}")
        candidates=data.get("candidates",data) if isinstance(data,(dict,list)) else []
        if isinstance(candidates,dict): candidates=[candidates]
        return jsonify(success=True,mode="external",provider=cfg.get("provider"),candidates=candidates)
    except Exception as exc:
        return jsonify(success=False,error=f"Unable to retrieve ATS candidates: {exc}"),502

@app.patch("/api/ats/candidates/<path:email>/status")
def ats_candidate_status(email):
    """Update candidate pipeline status in Demo ATS or a compatible external ATS."""
    payload=request.get_json(silent=True) or {}
    status=str(payload.get("status","")).strip()
    allowed={"New","Screening","Interview Scheduled","Interviewed","Shortlisted","Rejected","Hired","On Hold"}
    if status not in allowed:
        return jsonify(success=False,error=f"Status must be one of: {', '.join(sorted(allowed))}"),400
    cfg=load_ats_config()
    if str(cfg.get("provider","Demo ATS")).casefold()=="demo ats" or not cfg.get("base_url"):
        rows=_load_mock_ats()
        for candidate in rows:
            if str(candidate.get("email","")).casefold()==email.casefold():
                candidate["status"]=status; candidate["updated_at"]=datetime.now().isoformat(timespec="seconds"); _save_mock_ats(rows)
                return jsonify(success=True,mode="demo",candidate=candidate)
        return jsonify(success=False,error="Candidate not found in ATS."),404
    try:
        base=cfg["base_url"].rstrip("/")
        endpoint=(base if base.endswith("/candidates") else base+"/candidates")+"/"+urllib.parse.quote(email,safe="")+"/status"
        body=json.dumps({"status":status}).encode()
        req=urllib.request.Request(endpoint,data=body,method="PATCH",headers={"Authorization":f"Bearer {cfg.get('api_key','')}","Content-Type":"application/json","Accept":"application/json"})
        with urllib.request.urlopen(req,timeout=10) as resp:
            data=json.loads(resp.read().decode("utf-8") or "{}")
        return jsonify(success=True,mode="external",candidate=data.get("candidate",data))
    except Exception as exc:
        return jsonify(success=False,error=f"ATS status update failed: {exc}"),502

ATS_FILE = DATA_DIR / "ats_config.json"
ATS_SYNC_FILE = DATA_DIR / "ats_candidates.json"

def load_ats_config():
    try:
        return json.loads(ATS_FILE.read_text(encoding="utf8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"provider": "Demo ATS", "base_url": "", "api_key": "", "status": "Not connected"}

@app.get("/ats")
def ats_page():
    # ATS is intentionally integrated into the Interview Assistant workspace.
    return redirect('/interview')

@app.get("/api/ats/config")
def ats_config():
    cfg=load_ats_config()
    safe=dict(cfg); safe["api_key"] = "••••••••" if cfg.get("api_key") else ""
    return jsonify(safe)

@app.post("/api/ats/config")
def save_ats_config():
    payload=request.get_json(silent=True) or {}
    provider=str(payload.get("provider","Demo ATS")).strip()
    base_url=str(payload.get("base_url","")).strip().rstrip("/")
    api_key=str(payload.get("api_key","")).strip()
    # Demo ATS is fully local. Ignore any stale URL/API key so connection
    # testing and synchronization cannot accidentally target a fake/external URL.
    if provider.casefold() == "demo ats":
        base_url = ""
        api_key = ""
        status = "Demo mode"
    else:
        status = "Configured" if base_url else "Not connected"
    cfg={"provider":provider,"base_url":base_url,"api_key":api_key,"status":status}
    ATS_FILE.write_text(json.dumps(cfg,indent=2),encoding="utf8")
    return jsonify(success=True, config={**cfg, "api_key":"••••••••" if api_key else ""})

@app.get("/api/ats/demo/health")
def demo_ats_health():
    """Health check for the built-in Demo ATS used by the Interview Assistant."""
    try:
        rows = _load_mock_ats()
        return jsonify(success=True, connected=True, mode="demo", count=len(rows),
                       status="Demo ATS is connected and ready.")
    except Exception as exc:
        return jsonify(success=False, connected=False, error=f"Demo ATS unavailable: {exc}"), 500

@app.get("/api/ats/demo/candidates")
def demo_ats_candidates():
    """Return candidates stored by the built-in Demo ATS."""
    return jsonify(success=True, candidates=_load_mock_ats())

@app.post("/api/ats/test")
def ats_test():
    cfg=load_ats_config()
    # Built-in Demo ATS is always available; no second server is required.
    # Treat it as demo mode even if an old/stale base URL exists in ats_config.json.
    if str(cfg.get("provider", "Demo ATS")).casefold() == "demo ats" or not cfg.get("base_url"):
        return jsonify(success=True, mode="demo", status="Demo ATS connection successful. The built-in ATS is ready.")
    try:
        test_url = cfg["base_url"].rstrip("/")
        # The bundled FastAPI mock exposes GET /ats/list_candidates while its
        # write endpoint is POST /ats/add_candidate. Test the read endpoint when
        # an explicit write endpoint is configured.
        if test_url.endswith("/ats/add_candidate"):
            test_url = test_url[:-len("/ats/add_candidate")] + "/ats/list_candidates"
        req=urllib.request.Request(test_url, headers={
            "Authorization": f"Bearer {cfg.get('api_key','')}",
            "Accept":"application/json"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            return jsonify(success=True, mode="external", status=f"Connection successful (HTTP {resp.status}).")
    except Exception as exc:
        return jsonify(success=False, status=f"Connection test failed: {exc}"), 400

def _external_candidate_endpoint(base_url: str) -> str:
    """Accept either an API root or an explicit candidate endpoint."""
    base_url=base_url.rstrip("/")
    if base_url.endswith(("/candidates", "/ats/add_candidate")):
        return base_url
    return base_url + "/candidates"

@app.post("/api/ats/sync")
def ats_sync():
    """Synchronize explicitly selected candidates to the built-in or external ATS.

    Selection is resolved by candidate ID/email first and by legacy list index only
    as a fallback. This avoids index/order mismatches between the rendered page and
    the database after candidates are added or updated.
    """
    payload=request.get_json(silent=True) or {}
    candidates=load_candidates()
    selected_ids={str(x).strip() for x in (payload.get("candidate_ids") or []) if str(x).strip()}
    selected_emails={str(x).strip().casefold() for x in (payload.get("candidate_emails") or []) if str(x).strip()}
    indexes=[]
    for x in (payload.get("candidate_indexes") or []):
        try: indexes.append(int(x))
        except (TypeError,ValueError): pass

    records=[]
    seen=set()
    for i,c in enumerate(candidates):
        cid=str(c.get("candidate_id") or c.get("id") or "").strip()
        email=str(c.get("email") or "").strip().casefold()
        selected=(cid and cid in selected_ids) or (email and email in selected_emails)
        if not selected and not selected_ids and not selected_emails and i in indexes:
            selected=True
        if selected and email not in seen:
            seen.add(email)
            records.append({
                "candidate_id": cid,
                "candidate_index": i,
                "name": c.get("name") or "",
                "email": c.get("email") or "",
                "phone": c.get("phone") or "",
                "location": c.get("location") or "",
                "skills": c.get("skills") or [],
                "education": c.get("education") or [],
                "experience": c.get("experience") or {},
                "job_applied": _demo_job_for_candidate(c, i),
            })

    if not records:
        return jsonify(success=False, synced=0, error="No valid selected candidates were found. Please refresh the page and select candidates again."),400

    cfg=load_ats_config()
    job_title=str(payload.get("job_title") or "Interview Candidate").strip()

    # Demo ATS is local and must never depend on an external URL.
    if str(cfg.get("provider", "Demo ATS")).casefold() == "demo ats":
        cfg["base_url"] = ""
    if not cfg.get("base_url"):
        rows=_load_mock_ats()
        # Upsert by email so repeated syncs never create duplicates.
        index_by_email={str(r.get("email") or "").strip().casefold():i for i,r in enumerate(rows) if str(r.get("email") or "").strip()}
        added=0
        for c in records:
            key=str(c.get("email") or "").strip().casefold()
            row={
                "candidate_id": c.get("candidate_id") or "",
                "name": c.get("name") or "",
                "email": c.get("email") or "",
                "job_applied": c.get("job_applied") or job_title,
                "status": "Synced to ATS",
                "phone": c.get("phone") or "",
                "location": c.get("location") or "",
                "skills": c.get("skills") or [],
                "education": c.get("education") or [],
                "experience": c.get("experience") or {},
                "synced_at": datetime.now().isoformat(timespec="seconds")
            }
            if key and key in index_by_email:
                rows[index_by_email[key]].update(row)
            else:
                rows.append(row); index_by_email[key]=len(rows)-1; added += 1
        _save_mock_ats(rows)
        synced_rows=[r for r in rows if str(r.get("email") or "").strip().casefold() in {str(c.get("email") or "").strip().casefold() for c in records}]
        return jsonify(success=True,synced=len(records),added=added,mode="demo",records=synced_rows,
                       status=f"{len(records)} candidate(s) synced successfully to the built-in Demo ATS.")

    endpoint=_external_candidate_endpoint(cfg["base_url"])
    try:
        if endpoint.endswith("/ats/add_candidate"):
            synced=0
            for c in records:
                body=json.dumps({"name":c.get("name") or "","email":c.get("email") or "","job_applied":c.get("job_applied") or job_title,"status":"Interview Scheduled"}).encode()
                req=urllib.request.Request(endpoint,data=body,method="POST",headers={"Authorization":f"Bearer {cfg.get('api_key','')}","Content-Type":"application/json","Accept":"application/json"})
                with urllib.request.urlopen(req,timeout=10) as resp:
                    if 200 <= resp.status < 300: synced += 1
            return jsonify(success=True,synced=synced,mode="external",status=f"{synced} candidate(s) synced to the external ATS.")
        body=json.dumps({"candidates":records}).encode()
        req=urllib.request.Request(endpoint,data=body,method="POST",headers={"Authorization":f"Bearer {cfg.get('api_key','')}","Content-Type":"application/json","Accept":"application/json"})
        with urllib.request.urlopen(req,timeout=10) as resp:
            return jsonify(success=True,synced=len(records),mode="external",status=f"External ATS accepted the payload (HTTP {resp.status}).")
    except Exception as exc:
        return jsonify(success=False,synced=0,error=f"External sync failed: {exc}"),400


@app.errorhandler(413)
def too_large(_):
    return jsonify(success=False, error="Maximum file size is 10 MB."), 413


if __name__ == "__main__":
    app.run(debug=True)
