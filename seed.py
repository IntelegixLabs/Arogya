"""Seed generator - realistic longitudinal patient journeys for Arogya."""
import random
from datetime import datetime, timedelta

import database as db

random.seed(42)

FIRST_F = ["Priya", "Anita", "Sunita", "Lakshmi", "Meera", "Kavitha", "Radha", "Geeta", "Shanti", "Deepa",
           "Rekha", "Pooja", "Asha", "Nirmala", "Savita", "Usha", "Vandana", "Sarita", "Kamala", "Jyoti"]
FIRST_M = ["Rajesh", "Suresh", "Ramesh", "Mahesh", "Anil", "Vijay", "Prakash", "Ashok", "Sanjay", "Dinesh",
           "Manoj", "Ravi", "Kiran", "Arun", "Gopal", "Harish", "Naveen", "Mohan", "Vikram", "Sunil"]
LAST = ["Sharma", "Patel", "Reddy", "Kumar", "Singh", "Rao", "Nair", "Iyer", "Das", "Mehta",
        "Gupta", "Joshi", "Verma", "Pillai", "Naidu", "Choudhary", "Bhat", "Menon", "Kulkarni", "Desai"]
CITIES = [("Mumbai", "Mumbai", "Maharashtra"), ("Pune", "Pune", "Maharashtra"),
          ("Bengaluru", "Bengaluru Urban", "Karnataka"), ("Chennai", "Chennai", "Tamil Nadu"),
          ("Hyderabad", "Hyderabad", "Telangana"), ("Kochi", "Ernakulam", "Kerala"),
          ("Nagpur", "Nagpur", "Maharashtra"), ("Mysuru", "Mysuru", "Karnataka")]
LANGS = ["Hindi", "Marathi", "Kannada", "Tamil", "Telugu", "Malayalam", "English"]
OCCUPATIONS = ["Farmer", "Teacher", "Homemaker", "Shop owner", "Driver", "Tailor", "Office worker",
               "Construction worker", "Nurse", "Retired"]

CONDITIONS = [
    {"name": "Breast Cancer", "sex": "Female", "age": (35, 70), "complaint": "Lump in breast",
     "site": "Right breast, upper outer quadrant", "dept": "Breast Clinic", "risk_w": 3},
    {"name": "Cervical Cancer", "sex": "Female", "age": (30, 65), "complaint": "Abnormal vaginal bleeding",
     "site": "Cervix", "dept": "Gynecologic Oncology", "risk_w": 3},
    {"name": "Oral Cancer", "sex": "Any", "age": (40, 75), "complaint": "Non-healing ulcer in mouth",
     "site": "Left buccal mucosa", "dept": "Oral & Maxillofacial Surgery", "risk_w": 3},
    {"name": "Lung Cancer", "sex": "Any", "age": (45, 78), "complaint": "Persistent cough with blood streaks",
     "site": "Right lung", "dept": "Pulmonology", "risk_w": 3},
    {"name": "Lymphoma", "sex": "Any", "age": (25, 60), "complaint": "Painless neck swelling",
     "site": "Cervical lymph nodes", "dept": "Medical Oncology", "risk_w": 2},
    {"name": "Colorectal Cancer", "sex": "Any", "age": (45, 75), "complaint": "Blood in stool, altered bowel habit",
     "site": "Sigmoid colon", "dept": "Gastroenterology", "risk_w": 3},
    {"name": "Diabetes Mellitus", "sex": "Any", "age": (35, 75), "complaint": "Increased thirst and frequent urination",
     "site": "N/A", "dept": "Other", "risk_w": 1},
    {"name": "Hypertension", "sex": "Any", "age": (40, 78), "complaint": "Headache, dizziness",
     "site": "N/A", "dept": "Other", "risk_w": 1},
    {"name": "Maternal Health (High-risk pregnancy)", "sex": "Female", "age": (21, 40),
     "complaint": "Antenatal check-up - high risk", "site": "N/A", "dept": "Other", "risk_w": 2},
]

JOURNEY_STAGES = ["SCREENING", "CONSULTATION", "INVESTIGATION", "BIOPSY",
                  "PATHOLOGY REPORT", "REFERRAL", "SPECIALIST VISIT", "FOLLOW-UP"]

BLOOD_TESTS = ["CBC", "ESR/CRP", "Blood glucose", "HbA1c", "LFT", "RFT", "Electrolytes", "Coagulation profile"]
IMAGING = ["X-ray", "Ultrasound", "Mammography", "CT", "MRI", "PET-CT"]
INV_STATUSES = ["Advised", "Scheduled", "Completed", "Report uploaded", "Pending"]
BIOPSY_TYPES = ["Incisional", "Excisional", "Core needle", "FNAC", "Punch"]
LABS = ["City Path Labs", "Apex Diagnostics", "Metropolis", "SRL Diagnostics", "Govt. Medical College Lab"]
HOSPITALS = ["Tata Memorial Hospital", "AIIMS", "Kidwai Cancer Institute", "Regional Cancer Centre",
             "Adyar Cancer Institute", "District General Hospital"]
DOCTORS = ["Dr. A. Krishnan", "Dr. S. Bhattacharya", "Dr. M. Fernandes", "Dr. R. Chawla", "Dr. P. Hegde",
           "Dr. N. Warrier", "Dr. K. Sinha", "Dr. T. Rajan"]


def d(days_ago: int) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def build_seed() -> dict:
    data = {k: [] for k in db.EMPTY}
    data["meta"] = {"seeded_at": datetime.now().isoformat()}
    n_patients = 52

    for i in range(n_patients):
        cond = random.choice(CONDITIONS)
        sex = cond["sex"] if cond["sex"] != "Any" else random.choice(["Male", "Female"])
        first = random.choice(FIRST_F if sex == "Female" else FIRST_M)
        name = f"{first} {random.choice(LAST)}"
        age = random.randint(*cond["age"])
        dob = (datetime.now() - timedelta(days=age * 365 + random.randint(0, 364))).strftime("%Y-%m-%d")
        city, district, state = random.choice(CITIES)
        reg_days_ago = random.randint(3, 360)
        pid = f"AR-{2024 + (1 if reg_days_ago < 270 else 0)}-{1000 + i}"

        # how far along the journey is this patient (index into JOURNEY_STAGES)
        stage_idx = random.choices(range(8), weights=[4, 8, 12, 10, 10, 8, 5, 8])[0]
        is_cancer = "Cancer" in cond["name"] or cond["name"] == "Lymphoma"
        if not is_cancer:
            stage_idx = min(stage_idx, 2) if stage_idx < 5 else 7  # chronic: consult/investigate/follow-up

        risk = random.choices(["High", "Medium", "Low"],
                              weights=[cond["risk_w"] * 2, 3, 2])[0]

        patient = {
            "id": pid,
            "name": name,
            "age": age,
            "dob": dob,
            "sex": sex,
            "phone": f"+91 {random.randint(70000, 99999)} {random.randint(10000, 99999)}",
            "address": f"{random.randint(1, 250)}, {random.choice(['MG Road', 'Station Road', 'Gandhi Nagar', 'Nehru Street', 'Lake View Colony'])}",
            "city": city, "district": district, "state": state,
            "language": random.choice(LANGS),
            "registered_on": d(reg_days_ago),
            "occupation": random.choice(OCCUPATIONS),
            "marital_status": random.choice(["Married", "Single", "Widowed"]),
            "referred_by": random.choice(["Self", "PHC Referral", "Camp screening", "Private clinic", "ASHA worker"]),
            "previous_hospital": random.choice(["None", "District Hospital", "Private clinic", "CHC"]),
            "existing_patient_id": "" if random.random() > 0.3 else f"EXT-{random.randint(10000, 99999)}",
            "condition": cond["name"],
            "risk": risk,
            "stage_idx": stage_idx,
            "photo_hue": random.randint(0, 360),
        }
        data["patients"].append(patient)

        # ---- Consultation (stage >= 1) ----
        if stage_idx >= 1:
            consult_ago = max(1, reg_days_ago - random.randint(0, 3))
            data["consultations"].append({
                "id": db.uid("CN"), "patient_id": pid, "date": d(consult_ago),
                "doctor": random.choice(DOCTORS),
                "chief_complaint": cond["complaint"],
                "duration": f"{random.randint(1, 9)} {random.choice(['weeks', 'months'])}",
                "site": cond["site"],
                "onset": random.choice(["Gradual", "Sudden", "Insidious"]),
                "progression": random.choice(["Progressive", "Static", "Waxing and waning"]),
                "associated_complaints": random.choice(
                    ["Weight loss, loss of appetite", "Fatigue", "Fever on and off", "None significant", "Pain at site"]),
                "hpi": {
                    "symptom_start": f"{random.randint(1, 9)} months ago",
                    "progression": "Gradually progressive",
                    "previous_consultation": random.choice(["None", "Local GP", "PHC"]),
                    "previous_investigations": random.choice(["None", "Basic blood tests", "Ultrasound outside"]),
                    "previous_treatment": random.choice(["None", "Antibiotics course", "Symptomatic treatment"]),
                    "relevant_symptoms": "As above",
                },
                "medical_history": {
                    "diabetes": random.random() < 0.25, "hypertension": random.random() < 0.3,
                    "tuberculosis": random.random() < 0.05, "cardiac": random.random() < 0.1,
                    "kidney": random.random() < 0.05, "liver": random.random() < 0.05,
                    "previous_cancer": random.random() < 0.05, "other": False, "details": "",
                },
                "surgical_history": random.choice(["None", "Appendicectomy 2015 - District Hospital",
                                                   "Caesarean section 2018", "Hernia repair 2020"]),
                "medications": random.choice(["None", "Metformin 500mg BD - 3 years",
                                              "Amlodipine 5mg OD - 2 years", "Telmisartan 40mg OD"]),
                "allergies": random.choice(["None known", "Penicillin - rash", "Sulfa drugs - itching"]),
                "family_history": random.choice(["None significant", "Mother - breast cancer",
                                                 "Father - diabetes", "Sibling - hypertension"]),
                "personal_history": {
                    "smoking": random.choice(["Never", "10 pack-years", "Quit 5 years ago"]),
                    "tobacco": random.choice(["None", "Chewing tobacco 10 years", "Gutkha daily"]),
                    "alcohol": random.choice(["None", "Occasional", "Regular"]),
                    "occupational_exposure": random.choice(["None", "Pesticides", "Dust/silica", "None known"]),
                },
                "examination": {
                    "general_condition": random.choice(["Fair", "Good", "Moderate"]),
                    "pulse": random.randint(68, 110),
                    "bp": f"{random.randint(100, 168)}/{random.randint(64, 100)}",
                    "rr": random.randint(14, 24),
                    "temperature": round(random.uniform(97.4, 100.8), 1),
                    "spo2": random.randint(92, 99),
                    "weight": random.randint(42, 92),
                    "height": random.randint(148, 182),
                },
                "clinical_notes": "Detailed local examination performed. Plan investigations as advised.",
            })

        # ---- Investigations (stage >= 2) ----
        if stage_idx >= 2:
            n_inv = random.randint(2, 5)
            chosen_blood = random.sample(BLOOD_TESTS, k=min(3, n_inv))
            chosen_img = random.sample(IMAGING, k=random.randint(1, 2))
            for t in chosen_blood + chosen_img:
                kind = "Blood" if t in BLOOD_TESTS else "Imaging"
                if stage_idx == 2:
                    status = random.choice(["Advised", "Scheduled", "Completed", "Pending"])
                else:
                    status = random.choice(["Completed", "Report uploaded", "Report uploaded"])
                inv_ago = max(1, reg_days_ago - random.randint(2, 8))
                data["investigations"].append({
                    "id": db.uid("IV"), "patient_id": pid, "type": kind, "test": t,
                    "status": status, "advised_on": d(inv_ago),
                    "scheduled_on": d(max(0, inv_ago - 2)) if status != "Advised" else "",
                    "completed_on": d(max(0, inv_ago - 4)) if status in ("Completed", "Report uploaded") else "",
                    "notes": "",
                })
                if status == "Report uploaded":
                    data["reports"].append({
                        "id": db.uid("RP"), "patient_id": pid, "category": f"{kind} Report",
                        "test_name": t, "laboratory": random.choice(LABS),
                        "sample_date": d(max(0, inv_ago - 4)), "report_date": d(max(0, inv_ago - 5)),
                        "uploaded_by": random.choice(DOCTORS), "notes": "Within described limits" if random.random() > 0.4 else "Abnormal - see report",
                        "file_name": "", "file_url": "",
                    })

        # ---- Biopsy (stage >= 3, cancer patients only) ----
        if stage_idx >= 3 and is_cancer:
            b_ago = max(1, reg_days_ago - random.randint(8, 15))
            if stage_idx == 3:
                b_status = random.choice(["Sample collected", "Sent to laboratory", "Processing"])
            elif stage_idx == 4:
                b_status = random.choice(["Processing", "Report available"]) if random.random() > 0.5 else "Processing"
            else:
                b_status = "Report available"
            data["biopsies"].append({
                "id": db.uid("BX"), "patient_id": pid,
                "biopsy_type": random.choice(BIOPSY_TYPES),
                "anatomical_site": cond["site"], "side": random.choice(["Left", "Right", "Midline", "N/A"]),
                "exact_location": cond["site"],
                "lesion_description": random.choice(["Firm, irregular, non-tender", "Ulceroproliferative growth",
                                                     "Well-defined nodule", "Indurated ulcer with everted edges"]),
                "size": f"{round(random.uniform(0.8, 5.5), 1)} cm",
                "num_specimens": random.randint(1, 4),
                "date": d(b_ago), "time": f"{random.randint(9, 15)}:{random.choice(['00', '15', '30', '45'])}",
                "operator": random.choice(DOCTORS),
                "anaesthesia": random.choice(["Local", "Local with sedation", "General"]),
                "specimen_label": f"SP-{random.randint(1000, 9999)}",
                "fixative": "10% Neutral buffered formalin",
                "clinical_impression": f"Suspicious of {cond['name'].lower()}",
                "lab_instructions": random.choice(["Routine H&E", "IHC panel if malignant", "Urgent processing requested"]),
                "laboratory": random.choice(LABS),
                "lab_accession": f"ACC-{random.randint(100000, 999999)}",
                "date_sent": d(max(0, b_ago - 1)), "sent_by": "Ward staff", "received_by": "Lab reception",
                "status": b_status,
            })
            if b_status == "Report available":
                data["reports"].append({
                    "id": db.uid("RP"), "patient_id": pid, "category": "Biopsy Report",
                    "test_name": "Histopathology", "laboratory": random.choice(LABS),
                    "sample_date": d(b_ago), "report_date": d(max(0, b_ago - random.randint(4, 8))),
                    "uploaded_by": "Dr. Pathologist", "pathologist": "Dr. V. Iyer (MD Path)",
                    "notes": random.choice(["Invasive carcinoma confirmed", "Benign - follow up advised",
                                            "Dysplasia noted - requires review", "Malignancy confirmed - refer oncology"]),
                    "file_name": "", "file_url": "",
                })

        # ---- Referral (stage >= 5, cancer patients) ----
        if stage_idx >= 5 and is_cancer:
            r_ago = max(1, reg_days_ago - random.randint(16, 24))
            if stage_idx == 5:
                r_status = random.choice(["Referral created", "Appointment scheduled", "Referral not completed"])
            elif stage_idx == 6:
                r_status = random.choice(["Appointment scheduled", "Patient attended"])
            else:
                r_status = "Patient attended"
            data["referrals"].append({
                "id": db.uid("RF"), "patient_id": pid,
                "department": cond["dept"], "referred_to": random.choice(DOCTORS),
                "hospital": random.choice(HOSPITALS),
                "referral_date": d(r_ago),
                "reason": f"Confirmed/suspected {cond['name']} - for specialist management",
                "urgency": random.choice(["Routine", "Urgent", "Emergency"]),
                "documents_attached": True,
                "appointment_date": d(max(0, r_ago - random.randint(3, 10))) if r_status != "Referral created" else "",
                "status": r_status,
            })

        # ---- Prescription + advice (stage >= 1) ----
        if stage_idx >= 1:
            rx_map = {
                "Diabetes Mellitus": [["Tab. Metformin 500mg", "1-0-1", "30 days"],
                                      ["Tab. Glimepiride 1mg", "1-0-0", "30 days"]],
                "Hypertension": [["Tab. Amlodipine 5mg", "0-0-1", "30 days"],
                                 ["Tab. Telmisartan 40mg", "1-0-0", "30 days"]],
            }
            items = rx_map.get(cond["name"],
                               [["Tab. Paracetamol 650mg", "SOS", "5 days"],
                                ["Cap. Multivitamin", "0-0-1", "30 days"]])
            data["prescriptions"].append({
                "id": db.uid("RX"), "patient_id": pid, "date": d(max(1, reg_days_ago - 1)),
                "doctor": random.choice(DOCTORS),
                "items": [{"drug": x[0], "dose": x[1], "duration": x[2]} for x in items],
                "notes": "Take after food. Report if any adverse reaction.",
            })
            data["advices"].append({
                "id": db.uid("AD"), "patient_id": pid, "date": d(max(1, reg_days_ago - 1)),
                "doctor_advice": random.choice([
                    "Complete advised investigations at the earliest.",
                    "Maintain healthy diet, avoid tobacco/alcohol entirely.",
                    "Strict medication compliance; monitor symptoms.",
                    "Attend specialist appointment; carry all reports."]),
                "patient_instructions": "Return immediately if symptoms worsen. Keep all reports safe.",
                "patient_informed": True, "caregiver_informed": random.random() > 0.4,
                "written_instructions": random.random() > 0.3,
            })

        # ---- Follow-up ----
        if stage_idx >= 1:
            # some overdue (care gap), some upcoming
            if random.random() < 0.3:
                fu_date = (datetime.now() - timedelta(days=random.randint(2, 30))).strftime("%Y-%m-%d")
                fu_status = "Overdue"
            elif random.random() < 0.5:
                fu_date = (datetime.now() + timedelta(days=random.randint(1, 45))).strftime("%Y-%m-%d")
                fu_status = "Scheduled"
            else:
                fu_date = d(random.randint(5, 60))
                fu_status = "Completed"
            data["followups"].append({
                "id": db.uid("FU"), "patient_id": pid, "date": fu_date, "status": fu_status,
                "purpose": random.choice(["Review reports", "Post-referral review", "Chronic disease review",
                                          "Treatment response assessment", "Antenatal visit"]),
                "notes": "",
            })

    return data


def seed_if_empty(force: bool = False) -> bool:
    data = db.load()
    if force or not data["patients"]:
        db.reset(build_seed())
        return True
    return False


if __name__ == "__main__":
    import sys
    seed_if_empty(force="--force" in sys.argv)
    print(f"Seeded {len(db.load()['patients'])} patients.")
