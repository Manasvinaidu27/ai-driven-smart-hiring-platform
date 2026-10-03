# Milestone 4 — Dashboard & Deployment

Milestone 4 is implemented on top of the existing Flask recruitment platform.

## 1. Streamlit Recruitment Dashboard

Run:

```bash
streamlit run streamlit_app.py
```

Open `http://127.0.0.1:8501`.

The dashboard uses the same local candidate/job data as the Flask app and provides:

- Candidate totals and active job metrics
- Candidate ranking by hiring score
- Matched and missing skills
- Skill-gap reports with JSON download
- Interview status from the existing `data/interview_sessions.json` records
- User satisfaction survey and a calculated survey score

## 2. Voice-Based Screening

The **Voice Screening** tab provides:

1. Candidate and job selection
2. Role-specific screening questions
3. Optional question text-to-speech using `pyttsx3`
4. Browser microphone recording using Streamlit audio input
5. Speech-to-text using `SpeechRecognition`
6. Typed-answer fallback when microphone/speech recognition is unavailable
7. Role-aware local answer evaluation
8. Persistent screening records in `data/voice_screening_results.json`

SpeechRecognition's Google recognizer requires network access for transcription. The application does not claim offline speech recognition.

## 3. Testing

Run:

```bash
pytest -q
```

The existing resume-parser tests remain in `tests/test_parser.py`; Milestone 4 checks are in `tests/test_milestone4.py`.

## 4. Deployment

### Windows demo

Double-click `START_MILESTONE4.bat`. It starts:

- Flask recruiter portal: `http://127.0.0.1:5000`
- Streamlit Milestone 4 dashboard: `http://127.0.0.1:8501`

### Docker Compose

```bash
docker compose up --build
```

Then open ports 5000 and 8501.

## Satisfaction metric

The project does **not** fabricate a user-satisfaction result. It records actual survey responses and calculates the current score. The project can only claim `>=85%` after real responses produce that value.
