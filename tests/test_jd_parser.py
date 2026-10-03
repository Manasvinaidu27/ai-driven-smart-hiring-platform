from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jd_parser import analyze_job_description, extract_min_experience, extract_skills


def sample_jd():
    return """
    Python API Developer

    Responsibilities:
    - Build and maintain Python REST APIs and backend services.
    - Work with SQL databases and Git in an Agile team.

    Requirements:
    - 2+ years of experience in Python backend development.
    - Bachelor's degree in Computer Science or related field.
    - Strong Python, Django, REST APIs, SQL and Git skills.
    - Experience with Postman and API Testing is preferred.

    Location: Hyderabad, India
    """


def test_extract_skills_and_experience():
    text = sample_jd()
    skills = extract_skills(text)
    assert "Python" in skills
    assert "Django" in skills
    assert "REST API" in skills
    assert "SQL" in skills
    assert extract_min_experience(text) == 2.0


def test_analyze_job_description_returns_structured_profile():
    profile = analyze_job_description(sample_jd(), "python_api_developer.docx")
    assert profile["title"] == "Python API Developer"
    assert profile["min_experience"] == 2.0
    assert profile["experience_requirement"] == "2+ years"
    assert "Python" in profile["required_skills"]
    assert "Django" in profile["required_skills"]
    assert "SQL" in profile["required_skills"]
    assert "Bachelor's degree in Computer Science or related field." in profile["qualifications"]
    assert profile["location"] == "Hyderabad, India"
    assert profile["responsibilities"]
    assert profile["confidence"] >= 80


def test_jd_analyze_api_with_recruiter_login():
    import app as app_module
    client = app_module.app.test_client()
    login = client.post('/recruiter-login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
    assert login.status_code in (302, 303)
    response = client.post('/api/jobs/analyze', json={'text': sample_jd()})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['profile']['title'] == 'Python API Developer'
    assert 'Django' in payload['profile']['required_skills']
