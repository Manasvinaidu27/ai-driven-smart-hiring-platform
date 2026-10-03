"""Standalone Mock ATS API for Milestone 3 demonstration.
Run: uvicorn mock_ats_api:app --reload --port 8001
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from urllib.parse import unquote

app = FastAPI(title="Smart Hiring Mock ATS API")
ats_db = []

class Candidate(BaseModel):
    name: str
    email: str
    job_applied: str
    status: str

@app.post("/ats/add_candidate")
def add_candidate(candidate: Candidate):
    payload = candidate.model_dump() if hasattr(candidate, "model_dump") else candidate.dict()
    for existing in ats_db:
        if existing.get("email", "").lower() == payload["email"].lower():
            existing.update(payload)
            return {"message": f"Candidate {candidate.name} updated successfully.", "candidate": existing, "updated": True}
    ats_db.append(payload)
    return {"message": f"Candidate {candidate.name} added successfully.", "candidate": payload, "created": True}

@app.get("/ats/list_candidates")
def list_candidates() -> List[dict]:
    return ats_db

# Generic ATS API contract used by the main application.
@app.get("/candidates")
def candidates() -> List[dict]:
    return ats_db

@app.post("/candidates")
def create_or_update_candidates(payload: dict):
    records = payload.get("candidates", [payload]) if isinstance(payload, dict) else []
    if isinstance(records, dict):
        records = [records]
    results = []
    for item in records:
        email = str(item.get("email", "")).strip()
        if not email:
            continue
        row = {
            "name": item.get("name", ""), "email": email,
            "job_applied": item.get("job_applied", ""),
            "status": item.get("status", "New"),
            "phone": item.get("phone", ""), "location": item.get("location", ""),
            "skills": item.get("skills", []), "education": item.get("education", []),
            "experience": item.get("experience", {})
        }
        found = next((x for x in ats_db if x.get("email", "").lower() == email.lower()), None)
        if found:
            found.update(row); results.append(found)
        else:
            ats_db.append(row); results.append(row)
    return {"success": True, "candidates": results}

@app.patch("/candidates/{email}/status")
def patch_candidate_status(email: str, payload: dict):
    email = unquote(email)
    status = str(payload.get("status", "")).strip()
    allowed = {"New", "Screening", "Interview Scheduled", "Interviewed", "Shortlisted", "Rejected", "Hired", "On Hold"}
    if status not in allowed:
        return {"success": False, "error": "Invalid status"}
    for candidate in ats_db:
        if candidate.get("email", "").lower() == email.lower():
            candidate["status"] = status
            return {"success": True, "candidate": candidate}
    return {"success": False, "error": "Candidate not found"}

@app.put("/ats/update_status/{email}")
def update_status(email: str, status: str):
    for candidate in ats_db:
        if candidate["email"].lower() == email.lower():
            candidate["status"] = status
            return {"message": f"Status updated for {email} to {status}"}
    return {"error": "Candidate not found"}
