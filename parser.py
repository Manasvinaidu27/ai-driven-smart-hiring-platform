import json
import re
from pathlib import Path

import fitz
import docx
import pandas as pd
import spacy
import sqlite3
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
JSON_FILE = DATA_DIR / "candidates.json"
CSV_FILE = DATA_DIR / "candidates.csv"
DB_FILE = DATA_DIR / "candidates.db"
DATA_DIR.mkdir(exist_ok=True)

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # Keep regex/section extraction usable even when the optional spaCy model
    # has not been downloaded yet. NER-based location/name fallback is simply
    # unavailable until en_core_web_sm is installed.
    nlp = spacy.blank("en")

# Ordered from more specific to more general so C++ is not swallowed by C.
SKILLS = [
    "Machine Learning", "Deep Learning", "Natural Language Processing",
    "Data Analysis", "Data Visualization", "Automation Testing",
    "Project Management", "Power BI", "Power Query", "TensorFlow",
    "PyTorch", "PostgreSQL", "JavaScript", "TypeScript", "Node.js",
    "Spring Boot", "REST API", "GitHub", "MySQL", "MongoDB", "Oracle",
    "React", "Angular", "Django", "Flask", "Docker", "AWS", "Azure",
    "Tableau", "Excel", "Selenium", "Linux", "Python", "Java", "C++",
    "C#", "C", "SQL", "HTML", "CSS", "Git", "Jira", "NLP",
    "Communication", "Leadership"
]

DEGREE_PATTERNS = [
    r"\bb\.?\s*tech\b", r"\bb\.?\s*e\.?\b", r"\bb\.?\s*sc\b",
    r"\bb\.?\s*com\b", r"\bb\.?\s*b\.?\s*a\.?\b", r"\bb\.?\s*c\.?\s*a\.?\b",
    r"\bm\.?\s*tech\b", r"\bm\.?\s*e\.?\b", r"\bm\.?\s*sc\b",
    r"\bm\.?\s*c\.?\s*a\.?\b", r"\bm\.?\s*b\.?\s*a\.?\b", r"\bms\b",
    r"\bmaster(?:'s)?\b", r"\bbachelor(?:'s)?\b", r"\bph\.?d\b"
]

ROLE_WORDS = {
    "analyst", "developer", "engineer", "intern", "manager", "consultant",
    "tester", "specialist", "lead", "administrator", "executive", "trainee",
    "associate", "architect", "designer", "scientist", "recruiter", "reporting"
}

SECTION_ALIASES = {
    "education": {
        "education", "educational qualifications", "academic background",
        "academic qualifications", "academics"
    },
    "experience": {
        "experience", "work experience", "professional experience", "employment",
        "work history", "professional history"
    },
    "internships": {"internship", "internships", "internship experience", "internship experiences", "training & internships"},
    "skills": {"skills", "technical skills", "core skills", "key skills", "skill set"},
    "certifications": {"certifications", "certificates", "professional certifications", "licenses"},
    "projects": {"projects", "academic projects", "personal projects", "key projects"},
    "languages": {"languages", "language proficiency"},
    "summary": {"summary", "profile", "professional summary", "career objective", "objective"},
}

ALL_HEADINGS = set().union(*SECTION_ALIASES.values()) | {
    "achievements", "awards", "declaration", "personal details", "contact", "interests", "hobbies"
}

LOCATION_TERMS = {
    "india", "telangana", "andhra pradesh", "delhi", "new delhi",
    "hyderabad", "secunderabad", "bangalore", "bengaluru", "chennai",
    "mumbai", "pune", "kolkata", "gurugram", "gurgaon", "noida",
    "visakhapatnam", "vijayawada", "warangal", "tirupati", "kochi",
    "coimbatore", "jaipur", "ahmedabad", "surat", "nagpur", "bhopal",
    "lucknow", "kanpur", "indore", "patna", "bhubaneswar", "mysuru",
    "mysore", "vadodara", "thiruvananthapuram", "kerala", "karnataka",
    "tamil nadu", "maharashtra", "uttar pradesh", "west bengal",
    "odisha", "rajasthan", "gujarat", "punjab", "haryana", "bihar",
    "jharkhand", "chhattisgarh", "goa", "assam", "united states",
    "usa", "united kingdom", "uk", "canada", "australia"
}

NAME_REJECT_WORDS = {
    "resume", "curriculum", "vitae", "profile", "summary", "objective", "education",
    "skills", "experience", "projects", "certifications", "certificate", "internship",
    "reporting", "analytics", "analysis", "visualization", "developer", "engineer",
    "manager", "analyst", "consultant", "tester", "specialist", "associate", "trainee",
    "github", "linkedin", "foundation", "technology", "computer", "science", "bachelor",
    "master", "university", "college", "school", "python", "javascript", "typescript",
    "sql", "mysql", "postgresql", "power", "excel", "project", "management"
}


def normalize(text: str) -> str:
    text = (text or "").replace("\x00", " ").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" \t\r\n:|-•·")


def unique(items):
    result, seen = [], set()
    for item in items:
        item = clean(item)
        key = item.casefold()
        if item and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def lines(text):
    return [clean(x) for x in normalize(text).splitlines() if clean(x)]


def extract_text_from_pdf(pdf_path):
    document = fitz.open(str(pdf_path))
    try:
        return "\n".join(page.get_text("text") for page in document)
    finally:
        document.close()


def extract_text_from_docx(docx_path):
    document = docx.Document(str(docx_path))
    chunks = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                chunks.append(" | ".join(cells))
    return "\n".join(chunks)


def extract_email(text):
    match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    return match.group(0) if match else None


def extract_phone(text):
    patterns = [
        r"(?<!\d)(?:\+91[\s.-]?)?[6-9]\d{9}(?!\d)",
        r"(?<!\d)\+?[0-9][0-9 ()-]{8,}[0-9](?!\d)"
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = clean(match.group(0))
            digits = re.sub(r"\D", "", value)
            if 10 <= len(digits) <= 15:
                return value
    return None


def email_name_tokens(email):
    if not email:
        return []
    local = email.split("@", 1)[0]
    local = re.sub(r"\d+", " ", local)
    return [x.casefold() for x in re.split(r"[._-]+", local) if x]


def normalized_compact(value):
    return re.sub(r"[^a-z]", "", (value or "").casefold())


def is_heading(line):
    return clean(line).casefold().strip(" :-") in ALL_HEADINGS


def is_contact_line(line):
    low = line.casefold()
    return (
        "@" in line or "linkedin.com" in low or "github.com" in low
        or bool(re.search(r"\+?\d[\d ()-]{8,}\d", line))
    )


def plausible_name(value):
    value = clean(value)
    if not value or not 3 <= len(value) <= 70:
        return False
    words = value.split()
    if not 2 <= len(words) <= 4:
        return False
    if re.search(r"\d|[@:/\\|]", value):
        return False
    if any(w.casefold().strip(".,") in NAME_REJECT_WORDS for w in words):
        return False
    return all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", w) for w in words)


def extract_name(text, doc, email=None):
    """Extract the candidate name from the resume header first.

    Project requirement: the uploaded resumes used by this application start
    with the candidate's actual name. Therefore the first non-empty extracted
    line is the highest-priority source, before job titles or NER entities.
    """
    top = lines(text)[:30]

    # HIGHEST PRIORITY: the resume starts with the candidate's name.
    # Never allow a later title such as "Query Handling" to replace it.
    for first_line in top:
        first_line = clean(first_line)
        if not first_line:
            continue
        if plausible_name(first_line) and not is_contact_line(first_line):
            return first_line
        break
    email_tokens = email_name_tokens(email)
    email_compact = normalized_compact("".join(email_tokens))

    # 1. Explicit name label.
    # Supports both:
    #   Name: Manasvi Naidu
    # and a two-line header:
    #   Name
    #   Manasvi Naidu
    for i, line in enumerate(top):
        stripped = clean(line)
        if not stripped:
            continue

        m = re.match(r"^\s*(?:candidate\s+)?(?:full\s+)?name\s*[:\-]\s*(.+)$", stripped, re.I)
        if m and plausible_name(m.group(1)):
            return clean(m.group(1))

        # "Name" as a standalone heading. The following line(s) are checked
        # for the actual candidate name.
        if re.fullmatch(r"(?:candidate\s+)?(?:full\s+)?name", stripped, re.I):
            for nxt in top[i + 1:i + 5]:
                candidate = clean(nxt)
                if not candidate or is_contact_line(candidate):
                    continue
                if is_heading(candidate):
                    continue
                if plausible_name(candidate):
                    return candidate

    # 2. Visual header: check the first few lines before general NER.
    for line in top[:8]:
        candidate = clean(line)
        if candidate and not is_contact_line(candidate) and plausible_name(candidate):
            tokens = [w.casefold().strip(".,") for w in candidate.split()]
            if email_tokens and sum(t in email_tokens for t in tokens) >= max(1, len(tokens) // 2):
                return candidate

    # 3. PERSON entities near the header. Email similarity is a very strong signal.
    scored = []
    for ent in doc.ents:
        if ent.label_ != "PERSON" or ent.start_char > 1600:
            continue
        value = clean(ent.text)
        if not plausible_name(value):
            continue
        compact = normalized_compact(value)
        score = max(0, 1800 - ent.start_char)
        if email_compact and compact == email_compact:
            score += 10000
        elif email_compact and (compact in email_compact or email_compact in compact):
            score += 2500
        if ent.start_char < 600:
            score += 1200
        scored.append((score, value))
    if scored:
        scored.sort(reverse=True)
        return scored[0][1]

    # 4. Header lines. A title like "KPI Reporting" is rejected by plausible_name().
    for line in top:
        if is_contact_line(line) or is_heading(line):
            continue
        if plausible_name(line):
            # Prefer a line whose tokens occur in the email.
            tokens = [w.casefold().strip(".,") for w in line.split()]
            if email_tokens and sum(t in email_tokens for t in tokens) >= max(1, len(tokens) // 2):
                return line

    for line in top:
        if is_contact_line(line) or is_heading(line):
            continue
        if plausible_name(line):
            return line

    return None


def looks_like_location(value):
    value = clean(value)
    if not value or len(value) > 100:
        return False
    low = value.casefold()
    if any(x in low for x in ("open to relocate", "remote", "hybrid", "available", "relocate")):
        return False
    if re.search(r"@|https?://|www\.|linkedin|github", low):
        return False

    # Reject comma/semicolon-separated skill lists such as MySQL, PostgreSQL.
    parts = [clean(x) for x in re.split(r"[,;/|]+", value) if clean(x)]
    if len(parts) >= 2:
        skill_hits = sum(
            any(part.casefold() == skill.casefold() for skill in SKILLS)
            for part in parts
        )
        if skill_hits >= 1 and skill_hits / len(parts) >= 0.5:
            return False

    return any(term in low for term in LOCATION_TERMS)



def extract_location_from_line(line):
    """Return only the place portion from a contact/header line.

    Examples:
      Portfolio | Hyderabad -> Hyderabad
      Company Name | Hyderabad -> Hyderabad
      Hyderabad, Telangana, India — Open to Relocate -> Hyderabad, Telangana, India
    """
    line = clean(line)
    if not line:
        return None

    # Remove status text that follows an em/en dash or spaced hyphen.
    line = re.split(r"\s+[—–-]\s+", line, maxsplit=1)[0].strip()

    # First prefer pipe/bullet separated contact/header fields.
    fields = [clean(x) for x in re.split(r"\s*[|•·]\s*", line) if clean(x)]
    if len(fields) > 1:
        location_fields = []
        for field in fields:
            low = field.casefold()
            if re.search(r"@|\+?\d", field):
                continue
            if any(term in low for term in LOCATION_TERMS):
                location_fields.append(field)
        if location_fields:
            # A single place field is the normal case.
            return location_fields[-1][:120]

    # Preserve a full city/state/country string when its comma-separated
    # components are location terms.
    comma_parts = [clean(x) for x in re.split(r"\s*,\s*", line) if clean(x)]
    if len(comma_parts) > 1:
        location_parts = [
            part for part in comma_parts
            if any(term == part.casefold() or term in part.casefold() for term in LOCATION_TERMS)
        ]
        if location_parts and len(location_parts) == len(comma_parts):
            return ", ".join(location_parts)[:120]
        if location_parts:
            # If a larger field contains a known place, return that field only.
            return location_parts[-1][:120]

    # Finally accept a short field that contains a known location term.
    if looks_like_location(line):
        # If the line contains a known location embedded in extra words,
        # return the exact matching place rather than the whole line.
        matches = []
        for term in LOCATION_TERMS:
            m = re.search(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", line, re.I)
            if m:
                matches.append((len(term), m.group(0)))
        if matches:
            return max(matches)[1][:120]
        return line[:120]
    return None

def extract_location(text, doc):
    """Return a real place only; never turn a skill list into a location."""
    # 1. Explicit location labels.
    patterns = [
        r"(?:location|city|based\s+in|residing\s+in)\s*[:\-]\s*([^\n|]+)",
        r"(?:address)\s*[:\-]\s*([^\n]+)"
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            value = extract_location_from_line(m.group(1))
            if value:
                return value

    # 2. Contact/header line. Only use a segment that is clearly a place.
    email = extract_email(text)
    if email:
        for line in lines(text)[:20]:
            if email.casefold() not in line.casefold():
                continue
            value = extract_location_from_line(line)
            if value:
                return value

    # 3. NLP location entity in the resume header.
    entities = []
    for ent in doc.ents:
        if ent.label_ not in {"GPE", "LOC"} or ent.start_char > 2500:
            continue
        value = clean(ent.text)
        if looks_like_location(value):
            entities.append((2500 - ent.start_char, value))
    if entities:
        entities.sort(reverse=True)
        return entities[0][1]

    # 4. Conservative fallback for common places when spaCy misses the entity.
    for term in sorted(LOCATION_TERMS, key=len, reverse=True):
        m = re.search(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", text, re.I)
        if not m:
            continue
        line = next((x for x in lines(text) if m.group(0).casefold() in x.casefold()), m.group(0))
        value = extract_location_from_line(line)
        if value:
            return value
        if looks_like_location(term):
            return term

    return None

def section_lines(text, section_key):
    wanted = SECTION_ALIASES[section_key]
    all_lines = lines(text)
    result = []
    active = False
    for line in all_lines:
        heading = line.casefold().strip(" :-")
        if heading in wanted:
            active = True
            continue
        if active and heading in ALL_HEADINGS:
            break
        if active:
            result.append(line)
    return result


def all_section_lines(text, section_key):
    wanted = SECTION_ALIASES[section_key]
    all_lines = lines(text)
    chunks = []
    active = False
    current = []
    for line in all_lines:
        heading = line.casefold().strip(" :-")
        if heading in wanted:
            if current:
                chunks.extend(current)
            current = []
            active = True
            continue
        if active and heading in ALL_HEADINGS:
            chunks.extend(current)
            current = []
            active = False
            continue
        if active:
            current.append(line)
    if current:
        chunks.extend(current)
    return unique(chunks)


def extract_education(text):
    """Return meaningful education entries, preserving degree + institution + year lines."""
    section = all_section_lines(text, "education")
    if section:
        # Remove obvious contact-only lines but preserve complete education records.
        return unique([x for x in section if not is_contact_line(x)])[:15]

    # Fallback when the resume has no explicit Education heading.
    degree_lines = [x for x in lines(text) if any(re.search(p, x, re.I) for p in DEGREE_PATTERNS)]
    return unique(degree_lines)[:15]

def extract_skills(text):
    # First use a dedicated Skills section, then use whole-resume keyword matching.
    source = "\n".join(all_section_lines(text, "skills"))
    if not source:
        source = text
    found = []
    for skill in SKILLS:
        pattern = r"(?<![A-Za-z0-9+#.])" + re.escape(skill) + r"(?![A-Za-z0-9+#.])"
        if re.search(pattern, source, re.I):
            # Canonicalize HTML5 -> HTML and CSS3 -> CSS so analytics do not
            # split the same web skill into multiple labels.
            if skill.casefold() in {"html", "html5"}:
                found.append("HTML")
            elif skill.casefold() in {"css", "css3"}:
                found.append("CSS")
            else:
                found.append(skill)
    return unique(found)


def extract_headline(text, name):
    """Extract only a genuine header headline.

    A headline is accepted only from the few lines immediately following the
    candidate name. This prevents later section headings such as "Query
    Handling" or "KPI Reporting" from becoming a person's name/headline.
    """
    top = lines(text)[:20]
    name_norm = normalized_compact(name)
    if not name_norm:
        return None

    name_index = None
    for i, line in enumerate(top):
        if normalized_compact(line) == name_norm:
            name_index = i
            break
    if name_index is None:
        return None

    for line in top[name_index + 1:name_index + 4]:
        if not line or is_heading(line) or is_contact_line(line):
            continue
        if normalized_compact(line) == name_norm or len(line) > 90 or re.search(r"\d", line):
            continue
        # Accept a short professional headline, but never a known section heading.
        return line if 3 <= len(line) <= 70 else None
    return None

def extract_experience(text):
    """Extract professional experience, internships and duration robustly.

    Handles common resume layouts such as:
      Software Engineer | ABC Ltd | Jan 2024 - Present
      Business Analyst - XYZ | Jun 2022 – Dec 2023
      Executive – Business Operations\nIndiaInsure\nAug 2025 – Apr 2026

    Internship entries are kept separate and do not count toward professional
    experience years.
    """
    all_lines = lines(text)
    explicit_professional = all_section_lines(text, "experience")
    explicit_internships = all_section_lines(text, "internships")

    blocked = {"not detected", "none", "n/a", "na", "no professional experience"}

    def meaningful(items):
        return unique([
            x for x in items
            if x and not is_contact_line(x) and not is_heading(x)
            and x.casefold().strip(" .:-") not in blocked
        ])

    explicit_professional = meaningful(explicit_professional)
    explicit_internships = meaningful(explicit_internships)

    role_words = ROLE_WORDS | {
        "officer", "developer", "designer", "administrator", "executive",
        "technician", "associate", "coordinator", "representative", "specialist",
        "scientist", "architect", "consultant", "auditor", "intern"
    }
    # Multi-word titles that may not contain a ROLE_WORD token by themselves.
    title_phrases = {
        "software", "business analyst", "data analyst", "data scientist",
        "machine learning engineer", "ml engineer", "ai engineer",
        "project manager", "product manager", "operations manager",
        "business operations", "quality analyst", "quality engineer",
        "qa engineer", "qa analyst", "customer support", "technical support",
        "human resources", "hr executive", "account executive",
        "web developer", "frontend developer", "backend developer",
        "full stack developer", "python developer", "java developer",
        "software engineer", "devops engineer", "cloud engineer",
        "database administrator", "system administrator"
    }

    # Common date-range formats found in resumes.
    month = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    date_point = rf"(?:{month}\s+)?(?:19|20)\d{{2}}|{month}\s+(?:19|20)\d{{2}}"
    range_re = re.compile(
        rf"(?P<start>{date_point})\s*(?:-|–|—|to)\s*(?P<end>(?:{date_point}|present|current|now))",
        re.I
    )
    year_range_re = re.compile(r"(?<!\d)(?:19|20)\d{2}\s*(?:-|–|—|to)\s*(?:(?:19|20)\d{2}|present|current|now)(?!\d)", re.I)

    def has_role_signal(value):
        low = value.casefold()
        if re.search(r"\b(?:intern|internship|trainee|apprentice)\b", low):
            return True
        if any(phrase in low for phrase in title_phrases):
            return True
        return any(re.search(r"\b" + re.escape(word) + r"\b", low, re.I) for word in role_words)

    def is_intern(value):
        return bool(re.search(r"\b(?:intern|internship|trainee|apprentice)\b", value, re.I))

    # Find date-range lines and use nearby lines as the experience block.
    # This catches resumes whose headings are not literally "Experience".
    date_indexes = [
        i for i, line in enumerate(all_lines)
        if range_re.search(line) or year_range_re.search(line)
    ]

    professional_details = list(explicit_professional)
    internship_details = list(explicit_internships)

    for i in date_indexes:
        window = all_lines[max(0, i - 3): min(len(all_lines), i + 2)]
        window_text = " | ".join(window)
        if any(is_heading(x) for x in window) and not has_role_signal(window_text):
            continue
        # A date range by itself is not enough; require a plausible role/company signal.
        if not has_role_signal(window_text):
            continue
        if is_intern(window_text):
            internship_details.extend(window)
        else:
            professional_details.extend(window)

    # Parse explicit Experience section into blocks. A role/company line starts a block;
    # date lines and description lines belong to the current block.
    def parse_section(items):
        prof, interns = [], []
        current = []
        current_kind = None

        def flush():
            nonlocal current, current_kind
            if not current:
                return
            target = interns if current_kind == "internship" else prof
            target.extend(current)
            current, current_kind = [], None

        for line in items:
            starts_role = has_role_signal(line) or bool(range_re.search(line) or year_range_re.search(line))
            if starts_role and not current:
                current = [line]
                current_kind = "internship" if is_intern(line) else "professional"
            elif starts_role and current:
                # A new role/date line starts another record.
                if is_intern(line) != (current_kind == "internship") or range_re.search(line) or year_range_re.search(line):
                    flush()
                    current = [line]
                    current_kind = "internship" if is_intern(line) else "professional"
                else:
                    current.append(line)
            elif current:
                current.append(line)
        flush()
        return meaningful(prof), meaningful(interns)

    parsed_prof, parsed_interns = parse_section(explicit_professional)
    if parsed_prof or parsed_interns:
        professional_details.extend(parsed_prof)
        internship_details.extend(parsed_interns)

    professional_details = meaningful(professional_details)
    internship_details = meaningful(internship_details)

    # Remove internship-only records from professional details.
    professional_details = [x for x in professional_details if not is_intern(x)]

    # If no explicit section exists, use date-range blocks as the fallback.
    if not explicit_professional and not explicit_internships:
        fallback_prof = []
        for i in date_indexes:
            window = all_lines[max(0, i - 2): min(len(all_lines), i + 2)]
            text_window = " | ".join(window)
            if has_role_signal(text_window) and not is_intern(text_window):
                fallback_prof.extend(window)
        professional_details = meaningful(fallback_prof)

    professional_roles = unique([
        x for x in professional_details
        if has_role_signal(x) and not is_intern(x)
    ])[:15]

    # Calculate duration from explicit numeric year ranges and month/year ranges.
    def parse_point(value):
        value = value.strip().casefold()
        if value in {"present", "current", "now"}:
            now = datetime.now()
            return now.year, now.month
        m = re.search(r"(19|20)\d{2}", value)
        if not m:
            return None
        year = int(m.group(0))
        month_map = {
            "jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,
            "apr":4,"april":4,"may":5,"jun":6,"june":6,"jul":7,"july":7,
            "aug":8,"august":8,"sep":9,"sept":9,"september":9,"oct":10,
            "october":10,"nov":11,"november":11,"dec":12,"december":12
        }
        mm = re.search(r"\b([A-Za-z]{3,9})\b", value)
        month_num = month_map.get(mm.group(1).casefold()[:9], 1) if mm else 1
        # Normalize September variants.
        token = mm.group(1).casefold() if mm else ""
        month_num = month_map.get(token, month_num)
        return year, month_num

    ranges = []
    for line in professional_details:
        for m in range_re.finditer(line):
            a, b = parse_point(m.group("start")), parse_point(m.group("end"))
            if a and b:
                ranges.append((a, b))
        if not range_re.search(line):
            for m in year_range_re.finditer(line):
                parts = re.split(r"\s*(?:-|–|—|to)\s*", m.group(0), maxsplit=1, flags=re.I)
                if len(parts) == 2:
                    a, b = parse_point(parts[0]), parse_point(parts[1])
                    if a and b:
                        ranges.append((a, b))

    total = None
    if ranges:
        months = 0
        for (sy, sm), (ey, em) in ranges:
            end_months = ey * 12 + em
            start_months = sy * 12 + sm
            if end_months >= start_months:
                months += end_months - start_months + 1
        if months:
            years_value = months / 12
            total = f"{int(years_value) if years_value.is_integer() else round(years_value, 1)} years"
    else:
        # Fall back to explicit statements such as "2.5 years experience".
        years = re.findall(r"(?<!\d)(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", "\n".join(professional_details), re.I)
        if years:
            maximum = max(float(x) for x in years)
            total = f"{int(maximum) if maximum.is_integer() else maximum} years"

    return {
        "total_experience": total,
        "roles": professional_roles,
        "details": professional_details[:40],
        "internships": unique(internship_details)[:30]
    }

def extract_certifications(text):
    section = all_section_lines(text, "certifications")
    if section:
        return unique(section)[:20]
    return unique([
        line for line in lines(text)
        if re.search(r"\b(certification|certified|certificate)\b", line, re.I)
    ])[:20]


def extract_projects(text):
    return all_section_lines(text, "projects")[:25]


def extract_languages(text):
    return all_section_lines(text, "languages")[:15]


def confidence(profile):
    # This is extraction completeness, not model accuracy.
    fields = [
        bool(profile.get("name")), bool(profile.get("email")), bool(profile.get("phone")),
        bool(profile.get("location")), bool(profile.get("education")),
        bool(profile.get("skills")), bool(profile.get("experience", {}).get("roles") or profile.get("experience", {}).get("details") or profile.get("experience", {}).get("internships")),
        bool(profile.get("certifications")), bool(profile.get("projects"))
    ]
    return round(sum(fields) / len(fields) * 100)


def extract_candidate_info(text):
    text = normalize(text)
    doc = nlp(text)
    email = extract_email(text)
    candidate = {
        "name": extract_name(text, doc, email),
        "headline": "",
        "email": email,
        "phone": extract_phone(text),
        "location": extract_location(text, doc),
        "education": extract_education(text),
        "skills": extract_skills(text),
        "experience": extract_experience(text),
        "certifications": extract_certifications(text),
        "projects": extract_projects(text),
        "languages": extract_languages(text),
    }
    return candidate


def generate_profile(candidate, source_file=""):
    profile = {
        "name": candidate.get("name") or "Not detected",
        "headline": "",
        "email": candidate.get("email") or "Not detected",
        "phone": candidate.get("phone") or "Not detected",
        "location": candidate.get("location") or "Not detected",
        "education": candidate.get("education", []),
        "skills": candidate.get("skills", []),
        "experience": candidate.get("experience", {"total_experience": None, "roles": [], "details": [], "internships": []}),
        "certifications": candidate.get("certifications", []),
        "projects": candidate.get("projects", []),
        "languages": candidate.get("languages", []),
        "source_file": source_file,
    }
    profile["confidence"] = confidence(profile)
    return profile


def profile_to_dataframe(profiles):
    rows = []
    for p in profiles:
        exp = p.get("experience", {})
        rows.append({
            "name": p.get("name"), "headline": "",
            "email": p.get("email"), "phone": p.get("phone"),
            "location": p.get("location"),
            "education": "; ".join(p.get("education", [])),
            "skills": "; ".join(p.get("skills", [])),
            "experience": exp.get("total_experience") or "",
            "experience_roles": "; ".join(exp.get("roles", [])),
            "experience_details": "; ".join(exp.get("details", [])),
            "internships": "; ".join(exp.get("internships", [])),
            "certifications": "; ".join(p.get("certifications", [])),
            "projects": "; ".join(p.get("projects", [])),
            "languages": "; ".join(p.get("languages", [])),
            "confidence": p.get("confidence", 0),
            "source_file": p.get("source_file", ""),
        })
    return pd.DataFrame(rows)


def _db_connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_candidate_db():
    """Create the persistent candidate database used by the application."""
    with _db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT UNIQUE,
                phone TEXT,
                location TEXT,
                education_json TEXT NOT NULL DEFAULT '[]',
                skills_json TEXT NOT NULL DEFAULT '[]',
                experience_json TEXT NOT NULL DEFAULT '{}',
                certifications_json TEXT NOT NULL DEFAULT '[]',
                projects_json TEXT NOT NULL DEFAULT '[]',
                languages_json TEXT NOT NULL DEFAULT '[]',
                confidence REAL NOT NULL DEFAULT 0,
                source_file TEXT,
                resume_path TEXT,
                raw_text_preview TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()


def _json(value, default):
    return json.dumps(value if value is not None else default, ensure_ascii=False)


def _row_to_profile(row):
    def loads(key, default):
        try:
            value = json.loads(row[key]) if row[key] else default
            return value
        except (TypeError, json.JSONDecodeError):
            return default
    profile = {
        "candidate_id": row["id"],
        "name": row["name"] or "Not detected",
        "headline": "",
        "email": row["email"] or "Not detected",
        "phone": row["phone"] or "Not detected",
        "location": row["location"] or "Not detected",
        "education": loads("education_json", []),
        "skills": loads("skills_json", []),
        "experience": loads("experience_json", {}),
        "certifications": loads("certifications_json", []),
        "projects": loads("projects_json", []),
        "languages": loads("languages_json", []),
        "confidence": row["confidence"] or 0,
        "source_file": row["source_file"] or "",
        "resume_path": row["resume_path"] or "",
        "raw_text_preview": row["raw_text_preview"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    return profile


def _migrate_json_to_db():
    """One-time migration so existing demo candidates are not lost."""
    with _db_connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    if count:
        return
    try:
        existing = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        existing = []
    if not isinstance(existing, list):
        return
    for profile in reversed(existing):
        save_profile(profile, sync_legacy=False)


def save_profile(profile, sync_legacy=True):
    """Persist a structured candidate in SQLite and keep JSON/CSV as exports."""
    init_candidate_db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    email = profile.get("email")
    email_value = email if email and email != "Not detected" else None
    # SQLite UNIQUE email gives us an update path for the same candidate.
    with _db_connect() as conn:
        if email_value:
            existing = conn.execute("SELECT id, created_at FROM candidates WHERE lower(email)=lower(?)", (email_value,)).fetchone()
        else:
            existing = None
        if existing:
            conn.execute("""
                UPDATE candidates SET name=?, phone=?, location=?, education_json=?, skills_json=?,
                experience_json=?, certifications_json=?, projects_json=?, languages_json=?, confidence=?,
                source_file=?, resume_path=?, raw_text_preview=?, updated_at=? WHERE id=?
            """, (
                profile.get("name"), profile.get("phone"), profile.get("location"), _json(profile.get("education", []), []),
                _json(profile.get("skills", []), []), _json(profile.get("experience", {}), {}),
                _json(profile.get("certifications", []), []), _json(profile.get("projects", []), []),
                _json(profile.get("languages", []), []), profile.get("confidence", 0), profile.get("source_file", ""),
                profile.get("resume_path", ""), profile.get("raw_text_preview", ""), now, existing["id"]
            ))
            candidate_id = existing["id"]
            created_at = existing["created_at"]
        else:
            cur = conn.execute("""
                INSERT INTO candidates
                (name,email,phone,location,education_json,skills_json,experience_json,certifications_json,projects_json,languages_json,confidence,source_file,resume_path,raw_text_preview,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                profile.get("name"), email_value, profile.get("phone"), profile.get("location"),
                _json(profile.get("education", []), []), _json(profile.get("skills", []), []),
                _json(profile.get("experience", {}), {}), _json(profile.get("certifications", []), []),
                _json(profile.get("projects", []), []), _json(profile.get("languages", []), []),
                profile.get("confidence", 0), profile.get("source_file", ""), profile.get("resume_path", ""),
                profile.get("raw_text_preview", ""), now, now
            ))
            candidate_id = cur.lastrowid
            created_at = now
        conn.commit()

    profile["candidate_id"] = candidate_id
    profile["created_at"] = created_at
    profile["updated_at"] = now

    if sync_legacy:
        # JSON/CSV remain convenient exports for demos and spreadsheet analysis.
        all_profiles = load_candidates()
        profile_to_dataframe(all_profiles).to_csv(CSV_FILE, index=False)
        JSON_FILE.write_text(json.dumps(all_profiles, indent=2, ensure_ascii=False), encoding="utf-8")
    return candidate_id


def load_candidates():
    init_candidate_db()
    _migrate_json_to_db()
    with _db_connect() as conn:
        rows = conn.execute("SELECT * FROM candidates ORDER BY updated_at DESC, id DESC").fetchall()
    return [_row_to_profile(row) for row in rows]


def get_candidate(candidate_id):
    init_candidate_db()
    with _db_connect() as conn:
        row = conn.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
    return _row_to_profile(row) if row else None

def process_resume(file_path):
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        raw_text = extract_text_from_pdf(path)
    elif path.suffix.lower() == ".docx":
        raw_text = extract_text_from_docx(path)
    else:
        raise ValueError("Unsupported file format. Please upload PDF or DOCX.")

    raw_text = normalize(raw_text)
    if not raw_text:
        raise ValueError(
            "No selectable text was found. This may be a scanned/image-only PDF. "
            "OCR is required for image-only resumes."
        )

    candidate = extract_candidate_info(raw_text)
    profile = generate_profile(candidate, path.name)
    profile["raw_text_preview"] = raw_text[:5000]
    profile["resume_path"] = str(path)
    save_profile(profile)
    return profile
