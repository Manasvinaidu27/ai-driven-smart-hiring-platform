import re
from typing import Dict, List, Tuple

# Common aliases help matching when resumes and job descriptions use different spellings.
ALIASES = {
    "power bi": "Power BI",
    "microsoft power bi": "Power BI",
    "ms excel": "Excel",
    "microsoft excel": "Excel",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "python": "Python",
    "sql": "SQL",
    "rest api": "REST API",
    "rest apis": "REST API",
    "github": "GitHub",
    "git hub": "GitHub",
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "data analysis": "Data Analysis",
    "data analytics": "Data Analysis",
    "data visualization": "Data Visualization",
    "django": "Django",
    "flask": "Flask",
    "c++": "C++",
    "c#": "C#",
}

EDUCATION_LEVELS = {
    "phd": 5,
    "ph.d": 5,
    "doctorate": 5,
    "master": 4,
    "m.tech": 4,
    "mtech": 4,
    "mca": 4,
    "mba": 4,
    "msc": 4,
    "m.sc": 4,
    "ms": 4,
    "bachelor": 3,
    "b.tech": 3,
    "btech": 3,
    "b.e": 3,
    "be": 3,
    "b.sc": 3,
    "bsc": 3,
    "bca": 3,
    "diploma": 2,
}


def norm(value: str) -> str:
    value = str(value or "").casefold()
    value = re.sub(r"[^a-z0-9+#.]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_skill(value: str) -> str:
    key = norm(value)
    return ALIASES.get(key, str(value or "").strip())


def normalize_skill_list(skills) -> List[str]:
    result = []
    seen = set()
    for skill in skills or []:
        canonical = canonical_skill(skill)
        key = norm(canonical)
        if key and key not in seen:
            result.append(canonical)
            seen.add(key)
    return result


def skills_from_job(job: Dict) -> List[str]:
    values = job.get("required_skills", [])
    if isinstance(values, str):
        values = re.split(r"[,;|\n]+", values)
    return normalize_skill_list(values)


def candidate_years(candidate: Dict) -> float:
    exp = candidate.get("experience", {}) or {}
    value = exp.get("total_experience")
    if value:
        m = re.search(r"(\d+(?:\.\d+)?)", str(value))
        if m:
            return float(m.group(1))
    return 0.0


def candidate_text(candidate: Dict) -> str:
    exp = candidate.get("experience", {}) or {}
    parts = [
        candidate.get("name", ""),
        " ".join(candidate.get("education", []) or []),
        " ".join(candidate.get("skills", []) or []),
        " ".join(exp.get("roles", []) or []),
        " ".join(exp.get("details", []) or []),
        " ".join(exp.get("internships", []) or []),
        " ".join(candidate.get("projects", []) or []),
        " ".join(candidate.get("certifications", []) or []),
    ]
    return norm(" ".join(parts))


def education_level(candidate: Dict) -> int:
    text = norm(" ".join(candidate.get("education", []) or []))
    level = 0
    for term, score in EDUCATION_LEVELS.items():
        if term in text:
            level = max(level, score)
    return level


def required_education_level(value: str) -> int:
    text = norm(value)
    if not text or text in {"any", "not specified", "none"}:
        return 0
    level = 0
    for term, score in EDUCATION_LEVELS.items():
        if term in text:
            level = max(level, score)
    return level


def location_match(candidate: Dict, job: Dict) -> float:
    required = norm(job.get("location", ""))
    if not required or required in {"any", "any location", "remote or any location"}:
        return 1.0
    actual = norm(candidate.get("location", ""))
    if not actual or actual == "not detected":
        return 0.0
    if required in actual or actual in required:
        return 1.0
    req_parts = set(required.split())
    act_parts = set(actual.split())
    return 0.5 if req_parts & act_parts else 0.0


def match_candidate_to_job(candidate: Dict, job: Dict) -> Dict:
    required_skills = skills_from_job(job)
    candidate_skills = normalize_skill_list(candidate.get("skills", []))
    candidate_keys = {norm(x) for x in candidate_skills}

    matched = [skill for skill in required_skills if norm(skill) in candidate_keys]
    missing = [skill for skill in required_skills if norm(skill) not in candidate_keys]
    skill_score = (len(matched) / len(required_skills) * 60.0) if required_skills else 60.0

    required_years = float(job.get("min_experience", 0) or 0)
    actual_years = candidate_years(candidate)
    if required_years <= 0:
        experience_score = 25.0
    else:
        experience_score = min(actual_years / required_years, 1.0) * 25.0

    required_edu = required_education_level(job.get("education", ""))
    actual_edu = education_level(candidate)
    if required_edu == 0:
        education_score = 10.0
    elif actual_edu >= required_edu:
        education_score = 10.0
    elif actual_edu == max(required_edu - 1, 0):
        education_score = 5.0
    else:
        education_score = 0.0

    location_score = location_match(candidate, job) * 5.0
    total = round(min(skill_score + experience_score + education_score + location_score, 100.0), 1)

    if total >= 80:
        recommendation = "Strong Match"
    elif total >= 65:
        recommendation = "Good Match"
    elif total >= 50:
        recommendation = "Partial Match"
    else:
        recommendation = "Low Match"

    return {
        "candidate_name": candidate.get("name") or "Not detected",
        "candidate_email": candidate.get("email") or "Not detected",
        "score": total,
        "recommendation": recommendation,
        "matched_skills": matched,
        "missing_skills": missing,
        "skill_match_percent": round((len(matched) / len(required_skills) * 100) if required_skills else 100, 1),
        "experience": {"required_years": required_years, "candidate_years": actual_years, "score": round(experience_score, 1)},
        "education": {"required": job.get("education", "") or "Any", "candidate_level": actual_edu, "score": round(education_score, 1)},
        "location": {"required": job.get("location", "") or "Any", "candidate": candidate.get("location") or "Not detected", "score": round(location_score, 1)},
    }



def ats_compatibility_score(candidate: Dict, job: Dict) -> Dict:
    """Calculate a separate, demo-friendly ATS compatibility score.

    This is intentionally separate from job-fit matching: it measures how well the
    parsed resume is structured and how clearly job-relevant terms are represented.
    It is not a claim about any commercial ATS vendor's proprietary scoring.
    """
    text = candidate_text(candidate)
    required = skills_from_job(job)
    skill_hits = [skill for skill in required if norm(skill) in text]
    skill_keyword = (len(skill_hits) / len(required) * 40.0) if required else 40.0

    description = norm(f"{job.get('title','')} {job.get('description','')}")
    stop = {"and","the","for","with","from","that","this","are","you","your","job","role","work","will","into","using","use","build","maintain"}
    desc_terms = [t for t in description.split() if len(t) >= 4 and t not in stop]
    desc_terms = list(dict.fromkeys(desc_terms))
    desc_hits = sum(1 for term in desc_terms if term in text)
    keyword_alignment = (desc_hits / len(desc_terms) * 10.0) if desc_terms else 10.0

    section_checks = {
        "Contact details": bool(candidate.get('email') and candidate.get('email') != 'Not detected' and candidate.get('phone') and candidate.get('phone') != 'Not detected'),
        "Skills section": bool(candidate.get('skills')),
        "Education section": bool(candidate.get('education')),
        "Experience section": bool((candidate.get('experience') or {}).get('roles') or (candidate.get('experience') or {}).get('internships')),
        "Projects section": bool(candidate.get('projects')),
    }
    completeness = sum(section_checks.values()) / len(section_checks) * 20.0

    parser_confidence = float(candidate.get('confidence', 0) or 0)
    parser_score = min(max(parser_confidence, 0), 100) / 100 * 15.0

    clean_structure = 5.0 if len(text.split()) >= 40 else 2.5 if len(text.split()) >= 15 else 0.0
    total = round(min(skill_keyword + keyword_alignment + completeness + parser_score + clean_structure, 100.0), 1)

    if total >= 80:
        status = "ATS Ready"
    elif total >= 65:
        status = "Needs Minor Improvements"
    elif total >= 50:
        status = "Needs Optimization"
    else:
        status = "Low ATS Compatibility"

    return {
        "score": total,
        "status": status,
        "keyword_score": round(skill_keyword + keyword_alignment, 1),
        "resume_structure_score": round(completeness, 1),
        "contact_score": 4.0 if section_checks["Contact details"] else 0.0,
        "parser_score": round(parser_score, 1),
        "matched_keywords": skill_hits,
        "missing_keywords": [skill for skill in required if skill not in skill_hits],
        "section_checks": section_checks,
    }

def rank_candidates(candidates: List[Dict], job: Dict) -> List[Dict]:
    ranked = []
    for index, candidate in enumerate(candidates):
        result = match_candidate_to_job(candidate, job)
        result["ats"] = ats_compatibility_score(candidate, job)
        result["candidate_index"] = index
        ranked.append(result)
    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def build_skill_gap_report(candidate: Dict, job: Dict) -> Dict:
    result = match_candidate_to_job(candidate, job)
    required = skills_from_job(job)
    matched = result["matched_skills"]
    missing = result["missing_skills"]
    coverage = result["skill_match_percent"]

    if not missing:
        summary = "All required skills were detected in the candidate profile."
    else:
        summary = f"{len(missing)} required skill(s) were not detected in the candidate profile."

    return {
        "candidate_name": result["candidate_name"],
        "job_title": job.get("title", "Untitled Job"),
        "required_skills": required,
        "matched_skills": matched,
        "missing_skills": missing,
        "skill_coverage": coverage,
        "summary": summary,
        "priority_gaps": missing[:5],
        "recommendation": result["recommendation"],
    }
