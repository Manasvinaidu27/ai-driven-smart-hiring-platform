"""Job Description analysis utilities.

Parses pasted or uploaded job descriptions into a structured job-requirement profile.
The parser is intentionally deterministic so the demo works without an external LLM/API.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from parser import extract_text_from_pdf, extract_text_from_docx

SKILL_PATTERNS = [
    "Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#", "Go", "R",
    "HTML5", "HTML", "CSS3", "CSS", "React", "Angular", "Vue", "Node.js", "Django",
    "Flask", "FastAPI", "Spring Boot", "REST API", "REST APIs", "GraphQL", "Microservices",
    "SQL", "MySQL", "PostgreSQL", "MongoDB", "Oracle", "Redis", "SQLite",
    "Git", "GitHub", "GitLab", "Docker", "Kubernetes", "Jenkins", "CI/CD",
    "AWS", "Azure", "Google Cloud", "GCP", "Linux", "Terraform", "Ansible",
    "Power BI", "Tableau", "Excel", "Pandas", "NumPy", "PySpark", "Spark",
    "Machine Learning", "Deep Learning", "Artificial Intelligence", "NLP", "TensorFlow", "PyTorch",
    "Scikit-learn", "Data Science", "Data Analysis", "Data Analytics", "Data Visualization",
    "Selenium", "Cypress", "Playwright", "API Testing", "Automation Testing", "Manual Testing",
    "Jira", "Agile", "Scrum", "SDLC", "Postman", "Unit Testing", "PyTest",
    "Cybersecurity", "Network Security", "Cloud Security", "Information Security",
    "Business Analysis", "Requirements Gathering", "Product Management", "Figma",
]

# Longer phrases first so "REST APIs" is detected before "REST"-like substrings.
SKILL_PATTERNS = sorted(set(SKILL_PATTERNS), key=lambda x: (-len(x), x.casefold()))

EDUCATION_PATTERNS = [
    r"\bPh\.?D(?:\s+in\s+[^,.;\n]+)?",
    r"\bDoctorate(?:\s+in\s+[^,.;\n]+)?",
    r"\bMaster(?:'s)?(?:\s+degree)?(?:\s+in\s+[^,.;\n]+)?",
    r"\bM\.?Tech(?:\s+in\s+[^,.;\n]+)?",
    r"\bM\.?E(?:\s+in\s+[^,.;\n]+)?",
    r"\bM\.?CA(?:\s+in\s+[^,.;\n]+)?",
    r"\bM\.?Sc(?:\s+in\s+[^,.;\n]+)?",
    r"\bMBA(?:\s+in\s+[^,.;\n]+)?",
    r"\bBachelor(?:'s)?(?:\s+degree)?(?:\s+in\s+[^,.;\n]+)?",
    r"\bB\.?Tech(?:\s+in\s+[^,.;\n]+)?",
    r"\bB\.?E(?:\s+in\s+[^,.;\n]+)?",
    r"\bB\.?CA(?:\s+in\s+[^,.;\n]+)?",
    r"\bB\.?Sc(?:\s+in\s+[^,.;\n]+)?",
    r"\bDiploma(?:\s+in\s+[^,.;\n]+)?",
]

SECTION_HEADERS = {
    "requirements": ["requirements", "required qualifications", "qualifications", "what you need", "must have"],
    "responsibilities": ["responsibilities", "what you will do", "key responsibilities", "role responsibilities", "duties"],
    "preferred": ["preferred qualifications", "nice to have", "good to have", "preferred skills"],
}


def normalize_text(text: str) -> str:
    text = (text or "").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_line(line: str) -> str:
    line = re.sub(r"^[\s•*\-–—▪◦]+", "", line.strip())
    return re.sub(r"\s+", " ", line).strip(" :")


def extract_skills(text: str) -> List[str]:
    found = []
    low = text.casefold()
    for skill in SKILL_PATTERNS:
        # Allow punctuation in names such as C++, C#, CI/CD and .NET-like tokens.
        pattern = re.escape(skill.casefold())
        if re.search(r"(?<![a-z0-9])" + pattern + r"(?![a-z0-9])", low):
            canonical = "REST API" if skill.casefold() in {"rest api", "rest apis"} else skill
            if canonical not in found:
                found.append(canonical)
    return found


def extract_min_experience(text: str) -> float:
    patterns = [
        r"(?:minimum|min\.?|at least|more than|over)\s*(\d+(?:\.\d+)?)\s*\+?\s*years?(?:\s+of)?(?:\s+[a-z+#/.&-]+){0,5}\s+experience",
        r"(\d+(?:\.\d+)?)\s*\+\s*years?(?:\s+of)?(?:\s+[a-z+#/.&-]+){0,5}\s+experience",
        r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*years?(?:\s+of)?(?:\s+[a-z+#/.&-]+){0,5}\s+experience",
        r"(\d+(?:\.\d+)?)\s*years?\s+(?:of\s+)?experience",
    ]
    values = []
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.I):
            try:
                values.append(float(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else float(m.group(1)))
            except ValueError:
                pass
    return max(values) if values else 0.0


def extract_education(text: str) -> str:
    found = []
    for pattern in EDUCATION_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            value = _clean_line(m.group(0))
            if value and value.casefold() not in {x.casefold() for x in found}:
                found.append(value)
    # Normalize repeated generic phrases into a compact qualification string.
    return "; ".join(found[:5])


def extract_location(text: str) -> str:
    patterns = [
        r"(?:location|based in|work location|job location)\s*[:\-]\s*([^\n]+)",
        r"(?:location|based in|work location|job location)\s+(?:is\s+)?([^\n]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            value = _clean_line(m.group(1))
            if value:
                return value[:100]
    return ""


def extract_title(text: str, fallback: str = "") -> str:
    # Explicit labels are preferred.
    m = re.search(r"(?:job title|position|role|designation)\s*[:\-]\s*([^\n]+)", text, re.I)
    if m:
        return _clean_line(m.group(1))[:120]
    for line in text.splitlines():
        line = _clean_line(line)
        if not line or len(line) > 90:
            continue
        low = line.casefold()
        if any(token in low for token in ["developer", "engineer", "analyst", "scientist", "manager", "designer", "administrator", "consultant", "specialist", "architect"]):
            return line[:120]
    return fallback.strip()[:120]


def _extract_section(text: str, names: List[str]) -> List[str]:
    lines = text.splitlines()
    active = False
    out = []
    normalized_names = {x.casefold() for x in names}
    for raw in lines:
        line = _clean_line(raw)
        low = line.casefold()
        if not line:
            if active and out:
                # Keep reading across a single blank line; section boundaries are handled by headers.
                continue
        is_header = low.rstrip(":") in normalized_names or any(low.startswith(n + ":") for n in normalized_names)
        if is_header:
            active = True
            continue
        if active:
            if low.rstrip(":") in {x.casefold() for vals in SECTION_HEADERS.values() for x in vals}:
                break
            if line:
                out.append(line)
    return out[:12]


def extract_qualifications(text: str, education: str, skills: List[str]) -> List[str]:
    items = _extract_section(text, SECTION_HEADERS["requirements"])
    if not items:
        # Capture concise qualification statements when no explicit section exists.
        for line in text.splitlines():
            clean = _clean_line(line)
            low = clean.casefold()
            if any(k in low for k in ["degree", "bachelor", "master", "certification", "years of experience", "experience in"]):
                items.append(clean)
    if education and education not in items:
        items.insert(0, education)
    if skills:
        items.append("Required skills: " + ", ".join(skills))
    return list(dict.fromkeys(items))[:10]


def extract_responsibilities(text: str) -> List[str]:
    return _extract_section(text, SECTION_HEADERS["responsibilities"])


def analyze_job_description(text: str, source_name: str = "") -> Dict:
    text = normalize_text(text)
    skills = extract_skills(text)
    education = extract_education(text)
    experience = extract_min_experience(text)
    location = extract_location(text)
    title = extract_title(text, Path(source_name).stem if source_name else "")
    qualifications = extract_qualifications(text, education, skills)
    responsibilities = extract_responsibilities(text)

    # Confidence is a transparent heuristic based on how many required fields were found.
    signals = [bool(title), bool(skills), bool(education), experience > 0, bool(qualifications), bool(responsibilities)]
    confidence = round(sum(signals) / len(signals) * 100)
    return {
        "title": title or "Untitled Job",
        "required_skills": skills,
        "min_experience": experience,
        "experience_requirement": f"{experience:g}+ years" if experience else "Not specified",
        "education": education,
        "location": location,
        "qualifications": qualifications,
        "responsibilities": responsibilities,
        "description": text,
        "source_name": source_name,
        "source_type": Path(source_name).suffix.lower().lstrip(".") if source_name else "text",
        "confidence": confidence,
    }


def analyze_job_file(path: str | Path) -> Dict:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = extract_text_from_pdf(path)
    elif suffix == ".docx":
        text = extract_text_from_docx(path)
    else:
        raise ValueError("Only PDF and DOCX job descriptions are supported.")
    return analyze_job_description(text, path.name)
