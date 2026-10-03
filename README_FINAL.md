# AI-Driven Smart Hiring Platform — Final

## Included Milestone 3 features

1. **Role-specific interview question generation**
   - Multiple job roles
   - Technical Skills, Behavioral, Situational, and Technical + Behavioral filters
   - Recruiter interview question generator
   - Separate candidate practice interview with 50% competency overlap and different wording

2. **ATS candidate management**
   - Built-in Demo ATS
   - Test Connection
   - Refresh ATS status
   - Select and sync candidates
   - Candidate ID/email-based matching
   - Upsert behavior to prevent duplicates
   - Candidate status and sync timestamp
   - Configurable external REST ATS endpoint

3. **AI-powered interview simulation**
   - Candidate practice interview page
   - Automated evaluation
   - Optional OpenAI-compatible LLM evaluation via `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL`
   - Local evaluation fallback when no LLM is configured

4. **Candidate storage and resume parsing**
   - SQLite persistent candidate records
   - PDF/DOCX resume storage
   - Skills, education, projects, certifications, and experience extraction
   - Candidate Database
   - Experience display remains consistent: duration when reliably detected, otherwise `Experience detected`

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

For the built-in ATS demo, choose Demo ATS; no external ATS account is required.
