# Feature Verification – AI-Driven Smart Hiring Platform

## 1. Role-specific interview questions
- Recruiter route: `/api/interview/questions/<job_id>`
- Candidate route: `/api/candidate-interview/questions/<job_id>`
- Each supported role has a 10-question recruiter bank.
- Candidate practice returns exactly 10 questions: 5 shared competencies with different wording + 5 practice-only questions.
- The recruiter UI now shows all 10 questions when `All` is selected.

## 2. AI-powered interview simulation
- Recruiter answer evaluation: `/api/interview/evaluate`
- Candidate full-practice evaluation: `/api/candidate-interview/submit`
- Every answer receives a score plus relevance, communication, structure and specificity signals.
- The built-in evaluator works without an external AI key, so the demo does not break.
- If `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL` are configured, the same evaluation flow uses an OpenAI-compatible LLM and falls back safely if the external service fails.

## 3. ATS candidate management
- Built-in Demo ATS is enabled by default and persists records in `data/mock_ats_candidates.json`.
- Candidate sync is an email/candidate-ID upsert, preventing duplicate records on repeated sync.
- Health check: `/api/ats/demo/health`
- Candidate list: `/api/ats/demo/candidates`
- Sync: `/api/ats/sync`
- External ATS configuration is supported through the ATS settings page.
- The bundled FastAPI mock can be run with `RUN_MOCK_ATS.bat` for an end-to-end external API demonstration.

## Demo credentials
- Recruiter: `admin` / `admin123`
- Candidate login is available from the login page.

## Optional real LLM
Copy `.env.example` to `.env` and set:
- `AI_API_URL`
- `AI_API_KEY`
- `AI_MODEL`

Without these values, the built-in evaluator is used automatically.


## Job Description Analysis — Added
- Paste raw job description text or upload a PDF/DOCX job description.
- Automatically extracts job title, required skills, minimum experience, education/qualifications, location and responsibilities.
- Generates a structured job requirement profile with parser confidence and source information.
- "Use This Profile" transfers the extracted requirements into Create Job Requirement for candidate matching/ranking.
- Backend endpoint: `POST /api/jobs/analyze`.
- Deterministic local parser; no external AI/API key is required for this feature.
