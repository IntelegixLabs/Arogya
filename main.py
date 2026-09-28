"""Arogya - Population Health Management API (FastAPI)."""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import database as db
import seed

app = FastAPI(title="Arogya API", version="1.0.0",
              description="Longitudinal population health management for chronic & cancer care")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

seed.seed_if_empty()
os.makedirs(db.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=db.UPLOAD_DIR), name="uploads")

JOURNEY_STAGES = ["SCREENING", "CONSULTATION", "INVESTIGATION", "BIOPSY",
                  "PATHOLOGY REPORT", "REFERRAL", "SPECIALIST VISIT", "FOLLOW-UP"]


# ---------------------------------------------------------------- helpers
def _find(coll: str, **filters) -> list:
    data = db.load()
    out = data[coll]
    for k, v in filters.items():
        out = [x for x in out if x.get(k) == v]
    return out


def _get_patient(pid: str) -> dict:
    p = _find("patients", id=pid)
    if not p:
        raise HTTPException(404, f"Patient {pid} not found")
    return p[0]


def compute_journey(pid: str) -> list:
    """Compute journey stage statuses for a patient."""
    p = _get_patient(pid)
    consults = _find("consultations", patient_id=pid)
    invs = _find("investigations", patient_id=pid)
    biopsies = _find("biopsies", patient_id=pid)
    path_reports = [r for r in _find("reports", patient_id=pid) if r["category"] == "Biopsy Report"]
    refs = _find("referrals", patient_id=pid)
    fus = _find("followups", patient_id=pid)
    is_cancer = "Cancer" in p.get("condition", "") or p.get("condition") == "Lymphoma"

    def stage(name, status, detail=""):
        return {"stage": name, "status": status, "detail": detail}

    steps = [stage("SCREENING", "done", f"Registered {p['registered_on']}")]

    steps.append(stage("CONSULTATION", "done" if consults else "pending",
                       consults[0]["date"] if consults else "Not yet consulted"))

    if invs:
        n_done = sum(1 for i in invs if i["status"] in ("Completed", "Report uploaded"))
        st = "done" if n_done == len(invs) else ("active" if n_done else "pending")
        steps.append(stage("INVESTIGATION", st, f"{n_done}/{len(invs)} completed"))
    else:
        steps.append(stage("INVESTIGATION", "pending", "Not advised yet"))

    if not is_cancer:
        steps.append(stage("BIOPSY", "na", "Not applicable"))
        steps.append(stage("PATHOLOGY REPORT", "na", "Not applicable"))
        steps.append(stage("REFERRAL", "na" if not refs else "done", ""))
    else:
        if biopsies:
            b = biopsies[-1]
            steps.append(stage("BIOPSY", "done", f"{b['biopsy_type']} on {b['date']}"))
            if b["status"] == "Report available" or path_reports:
                steps.append(stage("PATHOLOGY REPORT", "done",
                                   path_reports[-1]["report_date"] if path_reports else "Available"))
            else:
                steps.append(stage("PATHOLOGY REPORT", "active", f"Status: {b['status']}"))
        else:
            steps.append(stage("BIOPSY", "pending", "Not performed"))
            steps.append(stage("PATHOLOGY REPORT", "pending", "Awaiting biopsy"))

        if refs:
            r = refs[-1]
            st = {"Patient attended": "done", "Appointment scheduled": "active",
                  "Referral created": "active", "Referral not completed": "alert"}.get(r["status"], "pending")
            steps.append(stage("REFERRAL", st, f"{r['department']} - {r['status']}"))
        else:
            steps.append(stage("REFERRAL", "pending", "Not referred"))

    attended = any(r["status"] == "Patient attended" for r in refs)
    steps.append(stage("SPECIALIST VISIT", "done" if attended else "pending",
                       "Attended" if attended else "Awaiting visit"))

    if fus:
        f = fus[-1]
        st = {"Completed": "done", "Scheduled": "active", "Overdue": "alert"}.get(f["status"], "pending")
        steps.append(stage("FOLLOW-UP", st, f"{f['status']} - {f['date']}"))
    else:
        steps.append(stage("FOLLOW-UP", "pending", "Not scheduled"))
    return steps


def care_gaps() -> list:
    """Population-level care gap detection."""
    data = db.load()
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    gaps = []
    pmap = {p["id"]: p for p in data["patients"]}

    for f in data["followups"]:
        if f["status"] == "Overdue" or (f["status"] == "Scheduled" and f["date"] < today):
            p = pmap.get(f["patient_id"])
            if p:
                gaps.append({"type": "Overdue follow-up", "severity": "high",
                             "patient_id": p["id"], "patient": p["name"], "condition": p["condition"],
                             "detail": f"Follow-up due {f['date']} ({f['purpose']})"})
    for b in data["biopsies"]:
        if b["status"] in ("Processing", "Sent to laboratory") and b["date_sent"] < week_ago:
            p = pmap.get(b["patient_id"])
            if p:
                gaps.append({"type": "Pathology report delayed", "severity": "high",
                             "patient_id": p["id"], "patient": p["name"], "condition": p["condition"],
                             "detail": f"Sent {b['date_sent']}, still '{b['status']}'"})
    for r in data["referrals"]:
        if r["status"] == "Referral not completed":
            p = pmap.get(r["patient_id"])
            if p:
                gaps.append({"type": "Referral incomplete", "severity": "high",
                             "patient_id": p["id"], "patient": p["name"], "condition": p["condition"],
                             "detail": f"{r['department']} referral of {r['referral_date']} not completed"})
    for i in data["investigations"]:
        if i["status"] in ("Advised", "Pending") and i["advised_on"] < week_ago:
            p = pmap.get(i["patient_id"])
            if p:
                gaps.append({"type": "Investigation pending", "severity": "medium",
                             "patient_id": p["id"], "patient": p["name"], "condition": p["condition"],
                             "detail": f"{i['test']} advised {i['advised_on']}, status '{i['status']}'"})
    sev_order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: sev_order[g["severity"]])
    return gaps


# ---------------------------------------------------------------- dashboard / analytics
@app.get("/api/dashboard")
def dashboard():
    data = db.load()
    patients = data["patients"]
    gaps = care_gaps()
    today = datetime.now().strftime("%Y-%m-%d")

    stage_counts = {s: 0 for s in JOURNEY_STAGES}
    for p in patients:
        journey = compute_journey(p["id"])
        current = next((s for s in journey if s["status"] in ("active", "alert", "pending") and s["status"] != "na"), None)
        stage_counts[(current or journey[-1])["stage"]] += 1

    cond_counts = {}
    for p in patients:
        cond_counts[p["condition"]] = cond_counts.get(p["condition"], 0) + 1

    risk_counts = {"High": 0, "Medium": 0, "Low": 0}
    for p in patients:
        risk_counts[p["risk"]] += 1

    # registrations by month (last 12)
    months, reg_by_month = [], []
    now = datetime.now()
    for k in range(11, -1, -1):
        m = (now.replace(day=1) - timedelta(days=k * 30))
        key = m.strftime("%Y-%m")
        months.append(m.strftime("%b"))
        reg_by_month.append(sum(1 for p in patients if p["registered_on"][:7] == key))

    upcoming = [f for f in data["followups"]
                if f["status"] == "Scheduled" and f["date"] >= today]
    upcoming.sort(key=lambda f: f["date"])
    pmap = {p["id"]: p for p in patients}
    upcoming_list = [{**f, "patient": pmap[f["patient_id"]]["name"],
                      "condition": pmap[f["patient_id"]]["condition"]}
                     for f in upcoming[:8] if f["patient_id"] in pmap]

    # risk x condition matrix for 3D chart
    top_conds = sorted(cond_counts, key=cond_counts.get, reverse=True)[:6]
    matrix = []
    for ci, c in enumerate(top_conds):
        for ri, r in enumerate(["Low", "Medium", "High"]):
            n = sum(1 for p in patients if p["condition"] == c and p["risk"] == r)
            matrix.append({"condition": c, "risk": r, "ci": ci, "ri": ri, "count": n})

    return {
        "totals": {
            "patients": len(patients),
            "active_journeys": sum(1 for p in patients if p["stage_idx"] < 7),
            "care_gaps": len(gaps),
            "high_risk": risk_counts["High"],
            "pending_reports": sum(1 for b in data["biopsies"] if b["status"] != "Report available"),
            "overdue_followups": sum(1 for g in gaps if g["type"] == "Overdue follow-up"),
        },
        "stage_distribution": [{"stage": s, "count": stage_counts[s]} for s in JOURNEY_STAGES],
        "condition_distribution": [{"condition": c, "count": n}
                                   for c, n in sorted(cond_counts.items(), key=lambda x: -x[1])],
        "risk_distribution": risk_counts,
        "registrations": {"months": months, "counts": reg_by_month},
        "risk_matrix": {"conditions": top_conds, "risks": ["Low", "Medium", "High"], "cells": matrix},
        "care_gaps": gaps[:12],
        "upcoming_followups": upcoming_list,
    }


# ---------------------------------------------------------------- patients
@app.get("/api/patients")
def list_patients(q: Optional[str] = None, condition: Optional[str] = None, risk: Optional[str] = None):
    data = db.load()
    out = data["patients"]
    if q:
        ql = q.lower()
        out = [p for p in out if ql in p["name"].lower() or ql in p["id"].lower()
               or ql in p.get("phone", "").lower() or ql in p.get("condition", "").lower()]
    if condition:
        out = [p for p in out if p["condition"] == condition]
    if risk:
        out = [p for p in out if p["risk"] == risk]
    result = []
    for p in sorted(out, key=lambda x: x["registered_on"], reverse=True):
        journey = compute_journey(p["id"])
        current = next((s for s in journey if s["status"] in ("active", "alert", "pending")), journey[-1])
        result.append({**p, "current_stage": current["stage"], "stage_status": current["status"]})
    return result


@app.post("/api/patients")
def create_patient(payload: dict):
    data = db.load()
    year = datetime.now().year
    seq = 1000 + len(data["patients"])
    patient = {
        "id": f"AR-{year}-{seq}",
        "name": payload.get("name", "").strip(),
        "age": payload.get("age"),
        "dob": payload.get("dob", ""),
        "sex": payload.get("sex", ""),
        "phone": payload.get("phone", ""),
        "address": payload.get("address", ""),
        "city": payload.get("city", ""),
        "district": payload.get("district", ""),
        "state": payload.get("state", ""),
        "language": payload.get("language", ""),
        "registered_on": datetime.now().strftime("%Y-%m-%d"),
        "occupation": payload.get("occupation", ""),
        "marital_status": payload.get("marital_status", ""),
        "referred_by": payload.get("referred_by", ""),
        "previous_hospital": payload.get("previous_hospital", ""),
        "existing_patient_id": payload.get("existing_patient_id", ""),
        "condition": payload.get("condition", "Under evaluation"),
        "risk": payload.get("risk", "Low"),
        "stage_idx": 0,
        "photo_hue": abs(hash(payload.get("name", ""))) % 360,
    }
    if not patient["name"]:
        raise HTTPException(400, "Patient name is required")
    data["patients"].append(patient)
    db.save()
    return patient


@app.get("/api/patients/{pid}")
def get_patient(pid: str):
    p = _get_patient(pid)
    return {
        "patient": p,
        "consultations": _find("consultations", patient_id=pid),
        "investigations": _find("investigations", patient_id=pid),
        "reports": _find("reports", patient_id=pid),
        "biopsies": _find("biopsies", patient_id=pid),
        "referrals": _find("referrals", patient_id=pid),
        "prescriptions": _find("prescriptions", patient_id=pid),
        "advices": _find("advices", patient_id=pid),
        "followups": _find("followups", patient_id=pid),
        "journey": compute_journey(pid),
    }


@app.put("/api/patients/{pid}")
def update_patient(pid: str, payload: dict):
    p = _get_patient(pid)
    for k, v in payload.items():
        if k != "id":
            p[k] = v
    db.save()
    return p


# ---------------------------------------------------------------- sub-entities (generic factory)
def _add_child(coll: str, prefix: str, pid: str, payload: dict, defaults: dict) -> dict:
    _get_patient(pid)
    data = db.load()
    rec = {**defaults, **payload, "id": db.uid(prefix), "patient_id": pid}
    data[coll].append(rec)
    db.save()
    return rec


@app.post("/api/patients/{pid}/consultations")
def add_consultation(pid: str, payload: dict):
    return _add_child("consultations", "CN", pid, payload,
                      {"date": datetime.now().strftime("%Y-%m-%d")})


@app.post("/api/patients/{pid}/investigations")
def add_investigation(pid: str, payload: dict):
    return _add_child("investigations", "IV", pid, payload,
                      {"status": "Advised", "advised_on": datetime.now().strftime("%Y-%m-%d"),
                       "scheduled_on": "", "completed_on": "", "notes": ""})


@app.patch("/api/investigations/{iid}")
def update_investigation(iid: str, payload: dict):
    recs = _find("investigations", id=iid)
    if not recs:
        raise HTTPException(404, "Investigation not found")
    recs[0].update({k: v for k, v in payload.items() if k not in ("id", "patient_id")})
    db.save()
    return recs[0]


@app.post("/api/patients/{pid}/biopsies")
def add_biopsy(pid: str, payload: dict):
    return _add_child("biopsies", "BX", pid, payload,
                      {"status": "Sample collected", "date": datetime.now().strftime("%Y-%m-%d")})


@app.patch("/api/biopsies/{bid}")
def update_biopsy(bid: str, payload: dict):
    recs = _find("biopsies", id=bid)
    if not recs:
        raise HTTPException(404, "Biopsy not found")
    recs[0].update({k: v for k, v in payload.items() if k not in ("id", "patient_id")})
    db.save()
    return recs[0]


@app.post("/api/patients/{pid}/referrals")
def add_referral(pid: str, payload: dict):
    return _add_child("referrals", "RF", pid, payload,
                      {"status": "Referral created",
                       "referral_date": datetime.now().strftime("%Y-%m-%d")})


@app.patch("/api/referrals/{rid}")
def update_referral(rid: str, payload: dict):
    recs = _find("referrals", id=rid)
    if not recs:
        raise HTTPException(404, "Referral not found")
    recs[0].update({k: v for k, v in payload.items() if k not in ("id", "patient_id")})
    db.save()
    return recs[0]


@app.post("/api/patients/{pid}/prescriptions")
def add_prescription(pid: str, payload: dict):
    return _add_child("prescriptions", "RX", pid, payload,
                      {"date": datetime.now().strftime("%Y-%m-%d"), "items": []})


@app.post("/api/patients/{pid}/advice")
def add_advice(pid: str, payload: dict):
    return _add_child("advices", "AD", pid, payload,
                      {"date": datetime.now().strftime("%Y-%m-%d"),
                       "patient_informed": False, "caregiver_informed": False,
                       "written_instructions": False})


@app.post("/api/patients/{pid}/followups")
def add_followup(pid: str, payload: dict):
    return _add_child("followups", "FU", pid, payload, {"status": "Scheduled", "notes": ""})


@app.patch("/api/followups/{fid}")
def update_followup(fid: str, payload: dict):
    recs = _find("followups", id=fid)
    if not recs:
        raise HTTPException(404, "Follow-up not found")
    recs[0].update({k: v for k, v in payload.items() if k not in ("id", "patient_id")})
    db.save()
    return recs[0]


# ---------------------------------------------------------------- reports (upload)
@app.post("/api/patients/{pid}/reports")
async def upload_report(pid: str,
                        file: Optional[UploadFile] = File(None),
                        category: str = Form("Other Documents"),
                        test_name: str = Form(""),
                        laboratory: str = Form(""),
                        sample_date: str = Form(""),
                        report_date: str = Form(""),
                        uploaded_by: str = Form(""),
                        pathologist: str = Form(""),
                        notes: str = Form("")):
    _get_patient(pid)
    data = db.load()
    file_name, file_url = "", ""
    if file and file.filename:
        safe = f"{db.uid('F')}_{os.path.basename(file.filename)}"
        dest = os.path.join(db.UPLOAD_DIR, safe)
        with open(dest, "wb") as out:
            out.write(await file.read())
        file_name, file_url = file.filename, f"/uploads/{safe}"
    rec = {
        "id": db.uid("RP"), "patient_id": pid, "category": category,
        "test_name": test_name, "laboratory": laboratory,
        "sample_date": sample_date, "report_date": report_date or datetime.now().strftime("%Y-%m-%d"),
        "uploaded_by": uploaded_by, "pathologist": pathologist, "notes": notes,
        "file_name": file_name, "file_url": file_url,
    }
    data["reports"].append(rec)
    db.save()
    return rec


@app.get("/api/reports")
def list_reports(category: Optional[str] = None):
    data = db.load()
    out = data["reports"]
    if category:
        out = [r for r in out if r["category"] == category]
    pmap = {p["id"]: p["name"] for p in data["patients"]}
    return [{**r, "patient": pmap.get(r["patient_id"], "?")}
            for r in sorted(out, key=lambda r: r.get("report_date", ""), reverse=True)]


# ---------------------------------------------------------------- registry & journey views
@app.get("/api/registry")
def registry():
    """Population registry grouped by condition with journey progress."""
    data = db.load()
    groups = {}
    for p in data["patients"]:
        g = groups.setdefault(p["condition"], {"condition": p["condition"], "patients": []})
        journey = compute_journey(p["id"])
        done = sum(1 for s in journey if s["status"] == "done")
        applicable = sum(1 for s in journey if s["status"] != "na")
        g["patients"].append({
            "id": p["id"], "name": p["name"], "age": p["age"], "sex": p["sex"],
            "risk": p["risk"], "registered_on": p["registered_on"],
            "progress": round(done / max(applicable, 1) * 100),
            "journey": journey,
        })
    return sorted(groups.values(), key=lambda g: -len(g["patients"]))


@app.get("/api/patients/{pid}/journey")
def patient_journey(pid: str):
    return compute_journey(pid)


@app.get("/api/care-gaps")
def get_care_gaps():
    return care_gaps()


# ---------------------------------------------------------------- AI assistant (rule-based)
@app.post("/api/ai")
def ai_assistant(payload: dict):
    q = (payload.get("message") or "").lower().strip()
    data = db.load()
    patients = data["patients"]
    gaps = care_gaps()

    def reply(text, items=None):
        return {"reply": text, "items": items or []}

    if not q:
        return reply("Hi! Ask me about care gaps, high-risk patients, overdue follow-ups, pending pathology, or any patient by name.")

    # patient lookup by name
    matches = [p for p in patients if any(tok in p["name"].lower() for tok in q.split() if len(tok) > 3)]
    if matches and any(w in q for w in ["patient", "about", "who is", "status", "journey", "show"]):
        p = matches[0]
        journey = compute_journey(p["id"])
        current = next((s for s in journey if s["status"] in ("active", "alert", "pending")), journey[-1])
        p_gaps = [g for g in gaps if g["patient_id"] == p["id"]]
        txt = (f"**{p['name']}** ({p['id']}) - {p['age']}y {p['sex']}, {p['condition']}, risk: {p['risk']}. "
               f"Current stage: {current['stage']} ({current['detail']}).")
        if p_gaps:
            txt += f" ⚠ {len(p_gaps)} care gap(s): " + "; ".join(g["detail"] for g in p_gaps)
        return reply(txt, [{"label": f"{p['name']} - {p['condition']}", "patient_id": p["id"]}])

    if "care gap" in q or "gap" in q or "attention" in q or "action" in q:
        top = gaps[:6]
        return reply(f"There are **{len(gaps)} open care gaps** across the population. Highest priority:",
                     [{"label": f"[{g['severity'].upper()}] {g['patient']} - {g['type']}: {g['detail']}",
                       "patient_id": g["patient_id"]} for g in top])

    if "overdue" in q or "follow" in q:
        od = [g for g in gaps if g["type"] == "Overdue follow-up"]
        return reply(f"**{len(od)} patients have overdue follow-ups.**",
                     [{"label": f"{g['patient']} ({g['condition']}) - {g['detail']}",
                       "patient_id": g["patient_id"]} for g in od[:8]])

    if "high risk" in q or "high-risk" in q or "risk" in q:
        hr = [p for p in patients if p["risk"] == "High"]
        return reply(f"**{len(hr)} high-risk patients** are under care. Top of the list:",
                     [{"label": f"{p['name']} - {p['condition']} ({p['id']})",
                       "patient_id": p["id"]} for p in hr[:8]])

    if "patholog" in q or "biopsy" in q or "report" in q:
        pend = [b for b in data["biopsies"] if b["status"] != "Report available"]
        pmap = {p["id"]: p["name"] for p in patients}
        return reply(f"**{len(pend)} biopsy/pathology reports are still pending.**",
                     [{"label": f"{pmap.get(b['patient_id'], '?')} - {b['biopsy_type']} ({b['status']}, sent {b['date_sent']})",
                       "patient_id": b["patient_id"]} for b in pend[:8]])

    if "referral" in q:
        inc = [r for r in data["referrals"] if r["status"] != "Patient attended"]
        pmap = {p["id"]: p["name"] for p in patients}
        return reply(f"**{len(inc)} referrals are not yet completed.**",
                     [{"label": f"{pmap.get(r['patient_id'], '?')} → {r['department']} ({r['status']})",
                       "patient_id": r["patient_id"]} for r in inc[:8]])

    if "summary" in q or "overview" in q or "population" in q or "dashboard" in q:
        conds = {}
        for p in patients:
            conds[p["condition"]] = conds.get(p["condition"], 0) + 1
        top = ", ".join(f"{c} ({n})" for c, n in sorted(conds.items(), key=lambda x: -x[1])[:4])
        return reply(f"Population: **{len(patients)} patients**. Top conditions: {top}. "
                     f"Open care gaps: {len(gaps)}. High-risk: {sum(1 for p in patients if p['risk'] == 'High')}.")

    if "cancer" in q:
        ca = [p for p in patients if "Cancer" in p["condition"] or p["condition"] == "Lymphoma"]
        return reply(f"**{len(ca)} patients in the cancer registry.**",
                     [{"label": f"{p['name']} - {p['condition']} (risk {p['risk']})",
                       "patient_id": p["id"]} for p in ca[:8]])

    if matches:
        p = matches[0]
        return reply(f"Found **{p['name']}** ({p['id']}) - {p['condition']}, risk {p['risk']}.",
                     [{"label": f"Open {p['name']}'s profile", "patient_id": p["id"]}])

    return reply("I can help with: 'show care gaps', 'overdue follow-ups', 'high risk patients', "
                 "'pending pathology reports', 'incomplete referrals', 'population summary', "
                 "or ask about a patient by name.")


@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


# ---------------------------------------------------------------- optional: serve built frontend (single-container deploys)
FRONTEND_DIST = os.environ.get("FRONTEND_DIST", os.path.join(db.BASE_DIR, "static"))
if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
