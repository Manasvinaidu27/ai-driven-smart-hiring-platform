# AI-DRIVEN SMART HIRING PLATFORM WITH CANDIDATE MATCHING COPILOT

## Resume Parsing & Candidate Profiling — Corrected Version

This version is focused on accurate extraction of candidate details from PDF and DOCX resumes.

### Main corrections

1. **Name priority**
   - If the resume starts with the candidate name, that first non-empty line is checked first.
   - A later heading such as `Query Handling`, `Problem Solving`, or `KPI Reporting` cannot replace the name.
   - Supports `Name: Candidate Name` and a two-line `Name` / `Candidate Name` layout.

2. **Headline separation**
   - A professional headline is only accepted from the few lines immediately following the candidate name.
   - Later job titles are not incorrectly promoted to the header.

3. **Location extraction**
   - Supports explicit `Location:` labels.
   - Supports common header formats such as `email | Hyderabad, Telangana, India — Open to Relocate`.
   - Removes trailing relocation notes from the location value.

4. **Experience vs internships**
   - Professional experience and internships are separated.
   - Intern roles found under a generic `Experience` heading are classified as internships.
   - Professional role lines are retained separately from descriptions.
   - Internship duration is not counted as professional experience.

5. **Education**
   - Preserves complete education-section entries instead of keeping only the degree keyword line.

6. **Skills, certifications, projects and languages**
   - Extracted into dedicated profile fields.
   - Missing information remains `Not detected`.

### Technologies requested

- PyMuPDF (`fitz`) — PDF extraction
- `python-docx` — DOCX extraction
- spaCy — NLP entities
- Regex — structured fields
- pandas — CSV/structured storage
- Transformers — included in requirements for future NLP enhancements
- Flask — web application

### Install

```bash
pip install pymupdf python-docx spacy pandas transformers flask
python -m spacy download en_core_web_sm
```

### Run

```bash
python app.py
```

Open `http://127.0.0.1:5000`.

### Test parser fixes

```bash
python -m pytest tests
```

If `pytest` is not installed, the tests are optional; the application itself does not require pytest.

### Important

The confidence value is **extraction completeness**, not a guarantee that every extracted fact is correct. The parser does not intentionally invent missing resume information.


## Latest extraction rules
- No headline is displayed.
- Location is not inferred from arbitrary header text or skill lists.
- Values such as "MySQL, PostgreSQL" cannot be used as a location.
- Internship-only resumes remain internship-only; they are not promoted to professional experience.
- Professional experience is shown only when professional role information is actually detected.

## Matching & Skill Analysis
The second module adds a deterministic candidate-job matching engine. Recruiters can create a job requirement with required skills, minimum experience, education, and location. Candidates are ranked with a 100-point hiring score:
- Skills: 60 points
- Experience: 25 points
- Education: 10 points
- Location: 5 points

The module also reports matched skills, missing skills, skill coverage percentage, and a candidate-specific skill-gap report.


## AI Interview Question Generation — Recruiter & Candidate Separation

The interview module now has two separate experiences:

### Recruiter Question Generator
- Recruiters can select from **15 predefined job roles**.
- The system generates **10 role-specific recruiter assessment questions**.
- Questions cover technical, behavioral and situational assessment.
- Recruiter questions are intended for candidate screening/interviewing.

### Candidate Practice Exam
- Candidates have a separate **Interview Practice** page.
- Candidates select a job role and receive **10 practice questions**.
- Exactly **5 of the 10 candidate questions (50%)** assess competencies also covered by the recruiter question set, but they use different wording.
- The remaining **5 questions are practice-only**, so candidates do not receive the complete recruiter question bank.
- Candidates answer all 10 questions and submit the exam.
- The platform calculates an overall practice score and gives question-level feedback.
- The score is a practice aid, not a hiring decision.

### Included job roles
1. Python API Developer
2. Data Analyst
3. Full Stack Developer
4. Backend Engineer
5. QA Automation Engineer
6. Machine Learning Engineer
7. AI Engineer
8. Power BI Developer
9. Cloud DevOps Engineer
10. Business Analyst
11. Frontend Developer
12. Database SQL Developer
13. Cybersecurity Analyst
14. Product Manager
15. Data Scientist

### Main interview endpoints
- Recruiter UI: `/interview`
- Recruiter question API: `/api/interview/questions/<job_id>`
- Candidate UI: `/candidate-interview`
- Candidate question API: `/api/candidate-interview/questions/<job_id>`
- Candidate exam submission: `/api/candidate-interview/submit`

## Candidate Information Storage

The platform now uses **SQLite as the primary persistent candidate database**.

### What is stored
Each candidate record contains:
- Unique Candidate ID
- Name, email, phone and location
- Education
- Skills
- Experience and internships
- Certifications
- Projects
- Languages
- Resume parsing confidence
- Original resume filename/path metadata
- Extracted text preview
- Created and updated timestamps

### Storage flow
`PDF/DOCX Resume -> uploads/ -> Parser -> SQLite candidates.db -> ATS Score / Job Match / Interview / Reports`

The recruiter can open **Candidate Database** from the sidebar to search and review stored candidate records.

### Files
- `data/candidates.db` — primary persistent database; created automatically on first use.
- `uploads/` — uploaded PDF/DOCX resumes.
- `data/candidates.json` — maintained as a JSON export for demo/debug use.
- `data/candidates.csv` — maintained as a spreadsheet-friendly export.

Existing `candidates.json` data is automatically migrated into SQLite the first time the database is initialized, so previously stored demo candidates are not lost.

## Milestone 3 — Interview Assistance & ATS Integration

This implementation maps directly to the Week 5–6 milestone requirements:

### 1. Role-specific interview questions
- Recruiter endpoint: `GET /api/interview/questions/<job_id>`
- Candidate practice endpoint: `GET /api/candidate-interview/questions/<job_id>`
- 15 job roles are supported by the role-question profiles and fallback generator.
- Recruiter and candidate question sets are intentionally separated.
- Candidate practice uses 5/10 related competencies with different wording and 5/10 practice-only questions.

### 2. ATS candidate management
- Main Flask app exposes mock ATS endpoints:
  - `POST /api/ats/add_candidate`
  - `GET /api/ats/list_candidates`
  - `PUT /api/ats/update_status/<email>`
- The ATS screening page separately calculates ATS Score and Job Match Score.
- External ATS synchronization uses a configurable REST endpoint and bearer API key.
- `mock_ats_api.py` is a standalone FastAPI mock service matching the milestone example:
  - `POST /ats/add_candidate`
  - `GET /ats/list_candidates`
  - `PUT /ats/update_status/{email}`

Run the standalone mock ATS with:
`uvicorn mock_ats_api:app --reload --port 8001`

### 3. AI-powered interview simulation
- Candidate interview is a 10-question role-specific simulation.
- If `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL` are configured, the complete interview is evaluated through an OpenAI-compatible LLM endpoint.
- AI evaluation returns an overall score, per-question feedback, strengths and improvement areas.
- If an AI endpoint is not configured or is unavailable, the system uses the transparent local evaluator as a fallback so the interview remains operational.

For a real AI evaluation, copy `.env.example` to `.env` and provide credentials through your environment. Never commit API keys to source control.

### Milestone 3 evidence
- **Interview questions generated for multiple job roles:** implemented in recruiter and candidate interview modules.
- **ATS integration functions correctly:** implemented through the mock ATS endpoints and configurable REST synchronization.
- **AI interview simulation operational:** implemented as an interactive candidate interview with optional LLM evaluation and a local fallback.


## Analytics and Voice Screening

The existing Flask recruiter portal remains the main application. An additional Streamlit analytics service reads the same local candidate/job data and provides candidate ranking, hiring scores, skill gaps, interview status, browser audio input, speech-to-text, text-to-speech, screening answer storage, and satisfaction feedback collection.

Run Flask: `python app.py`
Run analytics: `python -m streamlit run streamlit_app.py`
Or run both with `START_ALL.bat`.

Streamlit: `http://127.0.0.1:8501`
Flask: `http://127.0.0.1:5000`
