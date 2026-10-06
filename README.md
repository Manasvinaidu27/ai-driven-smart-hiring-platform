# AI-DRIVEN SMART HIRING PLATFORM WITH CANDIDATE MATCHING COPILOT
  live demo :   https://ai-driven-smart-hiring-platform.onrender.com
  Streamlit Dashboard live demo : https://ai-driven-smart-hiring-streamlit.onrender.com
## Project Objective

The **AI-Driven Smart Hiring Platform with Candidate Matching Copilot** was developed to simplify the recruitment process by automating important activities such as resume screening, candidate-job matching, skill-gap identification, interview assistance, ATS candidate management, interview simulation, analytics, and voice-based screening.

Traditional recruitment often requires recruiters to manually read resumes, compare candidates with job descriptions, prepare interview questions, maintain candidate information, and evaluate candidates.

This project addresses these challenges by creating a centralized recruitment platform that processes candidate information and provides structured insights to recruiters.

---

# 1. Resume Parsing and Candidate Profiling

## What I Did

In the first stage, I developed a resume upload and parsing system that extracts important candidate information from PDF and DOCX resumes.

The system creates a structured candidate profile containing:

- Candidate name
- Email
- Phone number
- Location
- Education
- Professional experience
- Internships
- Skills
- Certifications
- Projects
- Languages
- Resume text
- Resume parsing confidence

The extracted information is stored in a structured format so that it can later be used by the matching, ATS, interview, and analytics components.

---

## Why I Did It

Recruiters often spend a significant amount of time manually reviewing resumes.

Different resumes also use different formats. For example:

- One resume may place the name at the top.
- Another may use `Name:`.
- Some resumes may have separate experience and internship sections.
- Some may contain internships under an `Experience` heading.
- Location may appear beside an email address.
- Some information may be missing completely.

Therefore, I developed a parser that can handle different resume structures and convert unstructured resume documents into structured candidate data.

This provides a consistent candidate profile for the remaining recruitment process.

---

## How I Did It

### Step 1 — Resume Upload

The Flask application provides a resume upload interface.

The recruiter uploads:

```text
PDF
```

or

```text
DOCX
```

The uploaded file is saved in the:

```text
uploads/
```

directory.

---

### Step 2 — PDF Extraction

For PDF files, I used **PyMuPDF (`fitz`)** to extract the text.

The extracted text is then passed to the resume parsing logic.

---

### Step 3 — DOCX Extraction

For DOCX files, I used the **python-docx** library.

The parser reads paragraphs and extracts the available resume text.

---

### Step 4 — Structured Information Extraction

I used a combination of:

- Regex
- Text processing
- spaCy
- Section detection
- Pattern matching

to identify candidate information.

For example:

```text
Email
Phone
Location
Skills
Education
Experience
Projects
Certifications
Languages
```

---

### Step 5 — Name Detection

Special logic was added to prioritize the first meaningful candidate-name line.

For example:

```text
MANASVI NAIDU
Data Analyst
Hyderabad, Telangana
```

The system identifies:

```text
Name = MANASVI NAIDU
```

instead of incorrectly selecting a later heading.

---

### Step 6 — Location Detection

The parser supports explicit location fields:

```text
Location: Hyderabad, Telangana, India
```

and header formats such as:

```text
email@example.com | Hyderabad, Telangana, India
```

It avoids treating unrelated information such as:

```text
MySQL, PostgreSQL
```

as a location.

---

### Step 7 — Experience and Internship Detection

The parser separates:

```text
Professional Experience
```

from:

```text
Internships
```

If an internship appears under a general `Experience` section, the system identifies it as an internship rather than treating it as professional employment.

This prevents internship duration from being incorrectly counted as professional experience.

---

### Step 8 — Candidate Profile Creation

The extracted information is converted into a structured candidate profile.

Example:

```text
Candidate Name: Candidate Name
Email: candidate@email.com
Phone: +91 XXXXX XXXXX
Location: Hyderabad, Telangana
Education: B.Tech Computer Science
Skills: Python, SQL, Power BI
Experience: Not detected
Internships: Data Analytics Intern
Projects: Smart Hiring Platform
Certifications: Not detected
Languages: English, Telugu
```

---

### Step 9 — Database Storage

The candidate profile is stored in SQLite.

The main database is:

```text
data/candidates.db
```

Additional JSON and CSV exports are maintained for demonstration and data portability.

---

## Technologies Used

- Python
- Flask
- PyMuPDF
- python-docx
- spaCy
- Regex
- Pandas
- SQLite

---

## Result

The first stage converts:

```text
Unstructured Resume
        ↓
Resume Parser
        ↓
Structured Candidate Profile
        ↓
Candidate Database
```

This structured information becomes the foundation for the remaining platform.

---

# 2. Matching and Skill Analysis

## What I Did

In the second stage, I developed a candidate-job matching engine.

The recruiter can define a job requirement containing:

- Required skills
- Minimum experience
- Education
- Location

The system compares the candidate profile with the job requirements.

It generates:

- Hiring score
- Matched skills
- Missing skills
- Skill coverage percentage
- Candidate ranking
- Skill-gap report

---

## Why I Did It

Recruiters need to identify suitable candidates quickly.

Manually comparing every resume against every job description can be time-consuming and inconsistent.

For example, if a job requires:

```text
Python
SQL
Power BI
Excel
Pandas
```

and a candidate has:

```text
Python
SQL
Excel
```

the recruiter needs to immediately understand:

```text
Matched:
Python
SQL
Excel

Missing:
Power BI
Pandas
```

Therefore, I developed a matching system that provides a structured comparison between candidate capabilities and job requirements.

---

## How I Did It

### Step 1 — Create Job Requirements

The recruiter enters information such as:

```text
Job Role: Data Analyst

Required Skills:
Python
SQL
Power BI
Excel
Pandas

Minimum Experience:
1 year

Education:
Bachelor's Degree

Location:
Hyderabad
```

---

### Step 2 — Retrieve Candidate Profile

The system retrieves the candidate's structured information from SQLite.

The candidate profile contains the skills, education, experience, and location extracted during resume parsing.

---

### Step 3 — Skill Matching

The system compares:

```text
Required Skills
```

against:

```text
Candidate Skills
```

It identifies:

```text
Matched Skills
```

and:

```text
Missing Skills
```

---

### Step 4 — Skill Coverage

The platform calculates skill coverage based on the required skills that are present in the candidate profile.

For example:

```text
Required Skills = 5
Matched Skills = 3
```

Skill coverage:

```text
3 / 5 × 100 = 60%
```

---

### Step 5 — Hiring Score

I designed a 100-point scoring system.

| Category | Score |
|---|---:|
| Skills | 60 |
| Experience | 25 |
| Education | 10 |
| Location | 5 |
| **Total** | **100** |

This provides a standardized candidate-job comparison.

---

### Step 6 — Skill Gap Analysis

The system identifies skills required for the job that are not available in the candidate profile.

For example:

```text
Candidate Skills:
Python
SQL
Excel

Required:
Python
SQL
Power BI
Excel
Pandas
```

The system generates:

```text
Skill Gap:
Power BI
Pandas
```

This information can help recruiters understand candidate suitability and potential training requirements.

---

### Step 7 — Candidate Ranking

Candidates can be compared using their calculated hiring scores.

For example:

```text
Candidate A → 92/100
Candidate B → 81/100
Candidate C → 68/100
```

This allows recruiters to prioritize candidates for further evaluation.

---

## Result

The second stage transforms:

```text
Candidate Profile + Job Requirements
                ↓
        Matching Engine
                ↓
        Hiring Score
                ↓
    Skill Gap + Candidate Ranking
```

This provides recruiters with structured candidate-job comparison rather than relying only on manual resume review.

---

# 3. Interview Assistance and ATS Integration

## What I Did

In the third stage, I developed the interview and ATS functionality.

This includes:

- Role-specific interview question generation
- Recruiter interview questions
- Candidate interview practice
- ATS candidate management
- ATS score
- Job match score
- Candidate status management
- Candidate synchronization
- AI-powered interview simulation
- Interview evaluation

---

## Why I Did It

After resume screening and candidate matching, recruiters need to evaluate candidates through interviews.

Recruiters also need to manage candidate information and interview status.

Without a structured system, recruiters may need separate tools for:

- Resume screening
- Candidate management
- Interview questions
- Candidate evaluation

Therefore, I integrated these activities into the same platform.

---

# Recruiter Question Generator

## What I Did

I created a recruiter interview question generator supporting 15 job roles.

The supported roles include:

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

The recruiter receives 10 role-specific questions.

---

## How I Did It

The system identifies the selected job role and uses the corresponding question profile.

Questions cover:

### Technical

Questions related to the technologies and responsibilities of the role.

### Behavioral

Questions related to communication, teamwork, and professional behavior.

### Situational

Questions that evaluate how a candidate would handle realistic workplace situations.

---

# Candidate Interview Practice

## What I Did

I created a separate candidate interview practice page.

The candidate selects a role and receives exactly 10 questions.

The candidate answers all 10 questions before submitting the practice exam.

The system then calculates:

- Overall practice score
- Question-level feedback

---

## Question Distribution

The candidate receives:

```text
5 related competency questions
+
5 practice-only questions
=
10 questions
```

The related questions assess competencies covered by recruiter questions but use different wording.

This prevents the candidate from simply receiving the complete recruiter question bank.

---

# ATS Candidate Management

## What I Did

I implemented ATS functionality for managing candidates.

The system supports:

```text
Add Candidate
List Candidates
Update Candidate Status
Synchronize Candidates
Prevent Duplicate Candidates
```

Main endpoints include:

```text
POST /api/ats/add_candidate
```

```text
GET /api/ats/list_candidates
```

```text
PUT /api/ats/update_status/<email>
```

---

## Mock ATS

I also created a standalone mock ATS API using FastAPI.

The mock service provides:

```text
POST /ats/add_candidate
GET /ats/list_candidates
PUT /ats/update_status/{email}
```

It can be started using:

```bash
uvicorn mock_ats_api:app --reload --port 8001
```

This provides a test environment for ATS integration without requiring a production ATS account.

---

# AI-Powered Interview Simulation

## What I Did

I developed an interactive interview simulation where candidates answer role-specific questions.

The system evaluates the answers and provides:

- Overall score
- Question-level feedback
- Strengths
- Improvement areas

---

## How I Did It

The system supports an optional OpenAI-compatible LLM endpoint.

Environment variables can be configured for:

```text
AI_API_URL
AI_API_KEY
AI_MODEL
```

If an AI endpoint is unavailable, the system uses a local evaluation fallback.

This means the interview functionality can continue operating without requiring an external AI service.

---

## Result

The third stage provides:

```text
Candidate
    ↓
Job Role
    ↓
Interview Questions
    ↓
Candidate Answers
    ↓
Evaluation
    ↓
Score + Feedback
```

At the same time, recruiters can manage candidate information through ATS functionality.

---

# 4. Dashboard and Deployment

## What I Did

In the fourth stage, I developed the analytics and screening functionality and prepared the application for testing and deployment.

This includes:

- Recruitment dashboard
- Candidate ranking
- Hiring-score visualization
- Skill-gap information
- Interview status
- Voice-based screening
- Speech-to-text
- Text-to-speech
- Screening answer storage
- Feedback collection
- Application testing
- Deployment preparation

---

## Why I Did It

Recruiters need more than individual candidate information.

They also need an overview of the recruitment process.

For example, recruiters may want to understand:

- Which candidates have the highest scores?
- Which candidates match the job requirements?
- What skills are missing?
- Which candidates completed interviews?
- What are the screening results?

Therefore, the dashboard and analytics component provides a centralized view of recruitment information.

---

# Recruitment Dashboard

## What I Did

I developed a Streamlit-based analytics component that works with the recruitment data.

The dashboard can provide information such as:

- Candidate ranking
- Hiring scores
- Job matching
- Skill gaps
- Interview status
- Candidate information
- Screening results

---

## How I Did It

The analytics application reads the available candidate and job data and processes it using Python and Pandas.

The information can then be displayed through Streamlit components and analytics views.

The main Flask application remains responsible for the core recruitment workflow.

---

# Voice-Based Screening

## What I Did

I implemented voice-based screening functionality.

The screening system supports:

```text
Browser Audio
      ↓
Speech-to-Text
      ↓
Candidate Answer
      ↓
Screening Evaluation
      ↓
Answer Storage
```

Text-to-speech functionality can also be used to present questions or prompts to candidates.

---

## Why I Did It

Traditional screening requires recruiters to manually conduct the initial screening of every candidate.

Voice-based screening can help automate the initial stage and provide a more interactive candidate experience.

It can also help collect candidate responses in a structured format.

---

# Testing and Optimization

Before deployment, the application was tested across the major components.

Testing included:

### Resume Parsing

- PDF upload
- DOCX upload
- Name extraction
- Location extraction
- Education extraction
- Experience detection
- Internship detection
- Skills extraction

### Matching

- Skill matching
- Hiring score
- Missing skills
- Skill coverage
- Candidate ranking

### Interview

- Role selection
- Question generation
- Candidate practice
- Answer submission
- Score calculation
- Feedback generation

### ATS

- Candidate creation
- Candidate listing
- Status update
- Candidate synchronization
- Duplicate handling

### Dashboard

- Candidate data loading
- Analytics
- Candidate ranking
- Screening information

---

# Deployment

The application was prepared for deployment so that the recruitment platform can be accessed outside the local development environment.

The main application is built using Flask and can be deployed to a compatible Python hosting platform.

The project also separates services such as:

```text
Flask Application
Streamlit Analytics
Mock ATS API
```

This makes the different components easier to test and maintain.

---

# Overall System Workflow

The complete platform works as follows:

```text
                  RESUME
                    |
                    v
             Resume Upload
                    |
                    v
             Resume Parsing
                    |
                    v
          Candidate Profile
                    |
                    v
            SQLite Database
                    |
          +---------+---------+
          |                   |
          v                   v
     Job Matching          ATS
          |                   |
          v                   v
    Hiring Score        Candidate Status
          |
          v
    Skill Gap Analysis
          |
          v
 Interview Question Generation
          |
          v
 Candidate Interview
          |
          v
 AI Interview Evaluation
          |
          v
       Score + Feedback
          |
          v
 Analytics Dashboard
          |
          v
 Voice-Based Screening
```

---

# Technologies Used

## Programming

- Python
- JavaScript

## Backend

- Flask
- FastAPI

## Frontend

- HTML5
- CSS3
- JavaScript

## Database

- SQLite

## Resume Processing

- PyMuPDF
- python-docx
- spaCy
- Regex
- Pandas
- Transformers

## Analytics

- Streamlit
- Pandas

## APIs

- REST APIs
- Mock ATS API
- OpenAI-compatible AI API

## Development Tools

- Git
- GitHub
- VS Code
- Postman

---

# Project Architecture

```text
                        USER
                         |
          +--------------+--------------+
          |                             |
      RECRUITER                      CANDIDATE
          |                             |
          v                             v
   Flask Recruiter Portal       Candidate Portal
          |                             |
          +--------------+--------------+
                         |
                         v
                  Flask Backend
                         |
       +-----------------+-----------------+
       |                 |                 |
       v                 v                 v
 Resume Parser     Matching Engine    Interview Engine
       |                 |                 |
       v                 v                 v
 Candidate DB       Hiring Score       Evaluation
       |                 |                 |
       +-----------------+-----------------+
                         |
                         v
                   SQLite Database
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
            ATS      Analytics    Screening
                         |
                         v
                 Streamlit Dashboard
```

---

# Main Project Benefits

## For Recruiters

- Reduces manual resume screening
- Provides structured candidate profiles
- Quickly compares candidates with job requirements
- Calculates hiring scores
- Identifies missing skills
- Generates interview questions
- Manages candidate status
- Supports ATS workflows
- Provides recruitment analytics
- Supports voice-based screening

## For Candidates

- Provides role-specific interview practice
- Provides multiple practice questions
- Provides interview scoring
- Provides question-level feedback
- Identifies areas for improvement

---

# Project Outcome

The project combines four major areas of the recruitment lifecycle:

```text
1. Resume Parsing and Candidate Profiling

2. Matching and Skill Analysis

3. Interview Assistance and ATS Integration

4. Dashboard and Deployment
```

Together, these components create a complete recruitment workflow:

```text
Resume
   ↓
Candidate Profile
   ↓
Job Matching
   ↓
Hiring Score
   ↓
Skill Gap
   ↓
ATS Screening
   ↓
Interview
   ↓
AI Evaluation
   ↓
Analytics
   ↓
Voice Screening
```

The overall goal of the project is to provide recruiters with a centralized platform that can organize candidate information, automate repetitive recruitment tasks, support structured candidate evaluation, and provide useful insights throughout the hiring process.
