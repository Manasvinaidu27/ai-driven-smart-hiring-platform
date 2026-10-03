from pathlib import Path

from matcher import match_candidate_to_job, rank_candidates


def test_candidate_job_matching_for_dashboard():
    candidate = {
        "name": "Test Candidate",
        "email": "test@example.com",
        "skills": ["Python", "Django", "SQL", "Git"],
        "education": ["B.Tech Computer Science"],
        "experience": {"roles": [], "details": [], "internships": [], "total_experience": "0 years"},
        "projects": ["API project"],
        "certifications": [],
        "location": "Hyderabad, India",
        "confidence": 95,
    }
    job = {
        "id": 1,
        "title": "Python API Developer",
        "required_skills": ["Python", "REST API", "Django", "SQL", "Git"],
        "min_experience": 0,
        "education": "B.Tech / B.E. / equivalent",
        "location": "Hyderabad, India",
    }
    result = match_candidate_to_job(candidate, job)
    assert 0 <= result["score"] <= 100
    assert "REST API" in result["missing_skills"]


def test_rank_candidates_returns_candidate_index():
    candidate = {"name": "A", "skills": ["Python"], "education": [], "experience": {}, "location": "Hyderabad"}
    job = {"id": 1, "title": "Python API Developer", "required_skills": ["Python"], "min_experience": 0, "education": "Any", "location": "Any"}
    ranked = rank_candidates([candidate], job)
    assert len(ranked) == 1
    assert ranked[0]["candidate_index"] == 0


def test_dashboard_voice_deployment_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "templates" / "dashboard.html").exists()
    assert (root / "templates" / "voice_screening.html").exists()
    assert (root / "Dockerfile").exists()
    assert (root / "docker-compose.yml").exists()
    assert (root / "START_PROJECT.bat").exists()
