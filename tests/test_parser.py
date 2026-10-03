from parser import extract_candidate_info


def test_name_at_top_is_not_replaced_by_headings():
    text = """Manasvi Naidu
manasvinaidu27@gmail.com | Telangana
+91 7731880118
Education
Bachelor of Technology – Computer Science with Artificial Intelligence and Machine Learning | 2021–2025
Skills
Python SQL MySQL Power BI
Experience
Certifications
Advanced Data Analytics Internship Certificate – EDUNET Foundation
"""
    profile = extract_candidate_info(text)
    assert profile["name"] == "Manasvi Naidu"
    assert profile["name"] not in {"Query Handling", "Problem Solving", "KPI Reporting"}
    assert profile["location"] == "Telangana"


def test_experience_and_internships_are_separated():
    text = """Salman Mohammed
salman18.mohammed@gmail.com | Hyderabad, Telangana, India — Open to Relocate
+91 9347839704
Education
Bachelor of Technology in CSE (AIML)
Experience
Software Developer Intern — Mangos Orange Services Pvt Ltd
Sep 2024 – Feb 2025
Implemented a Facial & Manual Attendance System.
Full Stack Web Developer Intern — Edunet Foundation
Feb 2024 – Apr 2024
Delivered a job application portal.
"""
    profile = extract_candidate_info(text)
    assert profile["name"] == "Salman Mohammed"
    assert not profile["experience"]["roles"]
    assert profile["experience"]["internships"]


def test_professional_experience_is_detected_when_present():
    text = """Ajay Kumar
ajaykumar@gmail.com | Delhi
+91 9876543210
Education
Bachelor of Technology – Computer Science and Engineering
Experience
HRIC – SOFTWARE DEVELOPER
Developed web applications and APIs.
"""
    profile = extract_candidate_info(text)
    assert profile["name"] == "Ajay Kumar"
    assert "HRIC – SOFTWARE DEVELOPER" in profile["experience"]["roles"]
