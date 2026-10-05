        with urllib.request.urlopen(req, timeout=5) as resp:
            return jsonify(success=True, mode="external", status=f"Connection successful (HTTP {resp.status}).")
    except Exception as exc:
        return jsonify(success=False, status=f"Connection test failed: {exc}"), 400

def _external_candidate_endpoint(base_url: str) -> str:
    """Accept either an API root or an explicit candidate endpoint."""
    base_url=base_url.rstrip("/")
    if base_url.endswith(("/candidates", "/ats/add_candidate")):
        return base_url
    return base_url + "/candidates"

@app.post("/api/ats/sync")
def ats_sync():
    """Synchronize explicitly selected candidates to the built-in or external ATS.

    Selection is resolved by candidate ID/email first and by legacy list index only
    as a fallback. This avoids index/order mismatches between the rendered page and
    the database after candidates are added or updated.
    """
    payload=request.get_json(silent=True) or {}
    candidates=load_candidates()
    selected_ids={str(x).strip() for x in (payload.get("candidate_ids") or []) if str(x).strip()}
    selected_emails={str(x).strip().casefold() for x in (payload.get("candidate_emails") or []) if str(x).strip()}
    indexes=[]
    for x in (payload.get("candidate_indexes") or []):
        try: indexes.append(int(x))
        except (TypeError,ValueError): pass

    records=[]
    seen=set()
    for i,c in enumerate(candidates):
        cid=str(c.get("candidate_id") or c.get("id") or "").strip()
        email=str(c.get("email") or "").strip().casefold()
        selected=(cid and cid in selected_ids) or (email and email in selected_emails)
        if not selected and not selected_ids and not selected_emails and i in indexes:
            selected=True
        if selected and email not in seen:
            seen.add(email)
            records.append({
                "candidate_id": cid,
                "candidate_index": i,
                "name": c.get("name") or "",
                "email": c.get("email") or "",
                "phone": c.get("phone") or "",
                "location": c.get("location") or "",
                "skills": c.get("skills") or [],
                "education": c.get("education") or [],
                "experience": c.get("experience") or {},
                "job_applied": _demo_job_for_candidate(c, i),
            })

    if not records:
        return jsonify(success=False, synced=0, error="No valid selected candidates were found. Please refresh the page and select candidates again."),400

    cfg=load_ats_config()
    job_title=str(payload.get("job_title") or "Interview Candidate").strip()

    # Demo ATS is local and must never depend on an external URL.
    if str(cfg.get("provider", "Demo ATS")).casefold() == "demo ats":
        cfg["base_url"] = ""
    if not cfg.get("base_url"):
        rows=_load_mock_ats()
        # Upsert by email so repeated syncs never create duplicates.
        index_by_email={str(r.get("email") or "").strip().casefold():i for i,r in enumerate(rows) if str(r.get("email") or "").strip()}
        added=0
        for c in records:
            key=str(c.get("email") or "").strip().casefold()
            row={
                "candidate_id": c.get("candidate_id") or "",
                "name": c.get("name") or "",
                "email": c.get("email") or "",
                "job_applied": c.get("job_applied") or job_title,
                "status": "Synced to ATS",
                "phone": c.get("phone") or "",
                "location": c.get("location") or "",
                "skills": c.get("skills") or [],
                "education": c.get("education") or [],
                "experience": c.get("experience") or {},
                "synced_at": datetime.now().isoformat(timespec="seconds")
            }
            if key and key in index_by_email:
                rows[index_by_email[key]].update(row)
            else:
                rows.append(row); index_by_email[key]=len(rows)-1; added += 1
        _save_mock_ats(rows)
        synced_rows=[r for r in rows if str(r.get("email") or "").strip().casefold() in {str(c.get("email") or "").strip().casefold() for c in records}]
        return jsonify(success=True,synced=len(records),added=added,mode="demo",records=synced_rows,
                       status=f"{len(records)} candidate(s) synced successfully to the built-in Demo ATS.")

    endpoint=_external_candidate_endpoint(cfg["base_url"])
    try:
        if endpoint.endswith("/ats/add_candidate"):
            synced=0
            for c in records:
                body=json.dumps({"name":c.get("name") or "","email":c.get("email") or "","job_applied":c.get("job_applied") or job_title,"status":"Interview Scheduled"}).encode()
                req=urllib.request.Request(endpoint,data=body,method="POST",headers={"Authorization":f"Bearer {cfg.get('api_key','')}","Content-Type":"application/json","Accept":"application/json"})
                with urllib.request.urlopen(req,timeout=10) as resp:
                    if 200 <= resp.status < 300: synced += 1
            return jsonify(success=True,synced=synced,mode="external",status=f"{synced} candidate(s) synced to the external ATS.")
        body=json.dumps({"candidates":records}).encode()
        req=urllib.request.Request(endpoint,data=body,method="POST",headers={"Authorization":f"Bearer {cfg.get('api_key','')}","Content-Type":"application/json","Accept":"application/json"})
        with urllib.request.urlopen(req,timeout=10) as resp:
            return jsonify(success=True,synced=len(records),mode="external",status=f"External ATS accepted the payload (HTTP {resp.status}).")
    except Exception as exc:
        return jsonify(success=False,synced=0,error=f"External sync failed: {exc}"),400


@app.errorhandler(413)
def too_large(_):
    return jsonify(success=False, error="Maximum file size is 10 MB."), 413


if __name__ == "__main__":
    app.run(debug=True)
