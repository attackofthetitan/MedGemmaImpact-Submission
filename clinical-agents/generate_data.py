import os, json
from pathlib import Path
from datetime import date, timedelta
import pathlib
from models import (
    Medication,
    Allergy,
    Problem,
    LabResult,
    LabReport,
    ImagingReport,
    ImagingFinding,
    Encounter,
    RAGChunk,
    PatientRecord,
    PatientInfo,
)

TODAY = date.today()


PATIENTS = {
    "P001": {
        "patient_id": "P001",
        "name": "王小明",
        "age": 45,
        "sex": "male",
        "mrn": "P001",
        "dob": "1980-03-15",
    },
    "P002": {
        "patient_id": "P002",
        "name": "李美玲",
        "age": 32,
        "sex": "female",
        "mrn": "P002",
        "dob": "1993-07-22",
    },
    "P003": {
        "patient_id": "P003",
        "name": "陳大偉",
        "age": 68,
        "sex": "male",
        "mrn": "P003",
        "dob": "1957-01-08",
    },
    "P004": {
        "patient_id": "P004",
        "name": "張淑芬",
        "age": 55,
        "sex": "female",
        "mrn": "P004",
        "dob": "1970-11-30",
    },
}

MEDICATIONS = {
    "P001": [
        Medication(
            name="Metformin",
            dose="500mg",
            frequency="BID",
            route="PO",
            indication="Type 2 DM",
            status="active",
        ),
        Medication(
            name="Lisinopril",
            dose="10mg",
            frequency="QD",
            route="PO",
            indication="HTN",
            status="active",
        ),
        Medication(
            name="Atorvastatin",
            dose="20mg",
            frequency="QHS",
            route="PO",
            indication="Hyperlipidemia",
            status="active",
        ),
        Medication(
            name="Aspirin",
            dose="100mg",
            frequency="QD",
            route="PO",
            indication="CVD prevention",
            status="active",
        ),
    ],
    "P002": [
        Medication(
            name="Levothyroxine",
            dose="50mcg",
            frequency="QD",
            route="PO",
            indication="Hypothyroidism",
            status="active",
        ),
        Medication(
            name="Vitamin D3",
            dose="1000IU",
            frequency="QD",
            route="PO",
            indication="Deficiency",
            status="active",
        ),
    ],
    "P003": [
        Medication(
            name="Warfarin",
            dose="5mg",
            frequency="QD",
            route="PO",
            indication="Atrial fibrillation",
            status="active",
        ),
        Medication(
            name="Metoprolol",
            dose="50mg",
            frequency="BID",
            route="PO",
            indication="Afib rate control",
            status="active",
        ),
        Medication(
            name="Furosemide",
            dose="40mg",
            frequency="QD",
            route="PO",
            indication="CHF",
            status="active",
        ),
        Medication(
            name="Potassium Chloride",
            dose="20mEq",
            frequency="QD",
            route="PO",
            indication="Hypokalemia prevention",
            status="active",
        ),
        Medication(
            name="Lisinopril",
            dose="20mg",
            frequency="QD",
            route="PO",
            indication="CHF/HTN",
            status="active",
        ),
        Medication(
            name="Omeprazole",
            dose="20mg",
            frequency="QD",
            route="PO",
            indication="GERD",
            status="active",
        ),
    ],
    "P004": [
        Medication(
            name="Amlodipine",
            dose="5mg",
            frequency="QD",
            route="PO",
            indication="HTN",
            status="active",
        ),
        Medication(
            name="Metformin",
            dose="1000mg",
            frequency="BID",
            route="PO",
            indication="Type 2 DM",
            status="active",
        ),
        Medication(
            name="Glimepiride",
            dose="2mg",
            frequency="QD",
            route="PO",
            indication="Type 2 DM",
            status="active",
        ),
    ],
}

ALLERGIES = {
    "P001": [
        Allergy(
            allergen="Penicillin",
            reaction="Rash, hives",
            severity="moderate",
            verified=True,
        ),
    ],
    "P002": [
        Allergy(
            allergen="Sulfa drugs",
            reaction="Anaphylaxis",
            severity="severe",
            verified=True,
        ),
        Allergy(allergen="Shellfish", reaction="Hives", severity="mild", verified=True),
    ],
    "P003": [
        Allergy(
            allergen="Aspirin",
            reaction="GI bleeding",
            severity="moderate",
            verified=True,
        ),
        Allergy(allergen="NSAIDs", reaction="GI upset", severity="mild", verified=True),
    ],
    "P004": [],
}

PROBLEMS = {
    "P001": [
        Problem(
            icd_code="E11.9", description="Type 2 diabetes mellitus", status="active"
        ),
        Problem(icd_code="I10", description="Essential hypertension", status="active"),
        Problem(icd_code="E78.5", description="Hyperlipidemia", status="active"),
    ],
    "P002": [
        Problem(icd_code="E03.9", description="Hypothyroidism", status="active"),
        Problem(
            icd_code="E55.9", description="Vitamin D deficiency", status="resolved"
        ),
        Problem(icd_code="N94.6", description="Dysmenorrhea", status="active"),
    ],
    "P003": [
        Problem(icd_code="I48.91", description="Atrial fibrillation", status="active"),
        Problem(icd_code="I50.9", description="Heart failure", status="active"),
        Problem(icd_code="I10", description="Essential hypertension", status="active"),
        Problem(
            icd_code="E11.9", description="Type 2 diabetes mellitus", status="active"
        ),
        Problem(icd_code="N18.3", description="CKD stage 3", status="active"),
    ],
    "P004": [
        Problem(
            icd_code="E11.9", description="Type 2 diabetes mellitus", status="active"
        ),
        Problem(icd_code="I10", description="Essential hypertension", status="active"),
        Problem(icd_code="K21.0", description="GERD", status="active"),
    ],
}

LABS = {
    "P001": [
        LabResult(
            test_name="HbA1c",
            value="7.2",
            unit="%",
            reference_range="<7.0",
            flag="high",
            collected_date=TODAY - timedelta(days=14),
        ),
        LabResult(
            test_name="Fasting Glucose",
            value="142",
            unit="mg/dL",
            reference_range="70-100",
            flag="high",
            collected_date=TODAY - timedelta(days=14),
        ),
        LabResult(
            test_name="Creatinine",
            value="1.0",
            unit="mg/dL",
            reference_range="0.7-1.3",
            flag="normal",
            collected_date=TODAY - timedelta(days=14),
        ),
        LabResult(
            test_name="eGFR",
            value="82",
            unit="mL/min/1.73m²",
            reference_range=">60",
            flag="normal",
            collected_date=TODAY - timedelta(days=14),
        ),
        LabResult(
            test_name="Total Cholesterol",
            value="198",
            unit="mg/dL",
            reference_range="<200",
            flag="normal",
            collected_date=TODAY - timedelta(days=14),
        ),
        LabResult(
            test_name="LDL",
            value="118",
            unit="mg/dL",
            reference_range="<100",
            flag="high",
            collected_date=TODAY - timedelta(days=14),
        ),
        LabResult(
            test_name="HDL",
            value="42",
            unit="mg/dL",
            reference_range=">40",
            flag="normal",
            collected_date=TODAY - timedelta(days=14),
        ),
        LabResult(
            test_name="Triglycerides",
            value="165",
            unit="mg/dL",
            reference_range="<150",
            flag="high",
            collected_date=TODAY - timedelta(days=14),
        ),
        LabResult(
            test_name="ALT",
            value="38",
            unit="U/L",
            reference_range="7-56",
            flag="normal",
            collected_date=TODAY - timedelta(days=14),
        ),
        LabResult(
            test_name="AST",
            value="32",
            unit="U/L",
            reference_range="10-40",
            flag="normal",
            collected_date=TODAY - timedelta(days=14),
        ),
    ],
    "P002": [
        LabResult(
            test_name="TSH",
            value="2.8",
            unit="mIU/L",
            reference_range="0.4-4.0",
            flag="normal",
            collected_date=TODAY - timedelta(days=30),
        ),
        LabResult(
            test_name="Free T4",
            value="1.2",
            unit="ng/dL",
            reference_range="0.8-1.8",
            flag="normal",
            collected_date=TODAY - timedelta(days=30),
        ),
        LabResult(
            test_name="Vitamin D, 25-OH",
            value="38",
            unit="ng/mL",
            reference_range="30-100",
            flag="normal",
            collected_date=TODAY - timedelta(days=30),
        ),
        LabResult(
            test_name="CBC - WBC",
            value="7.2",
            unit="K/uL",
            reference_range="4.5-11.0",
            flag="normal",
            collected_date=TODAY - timedelta(days=30),
        ),
        LabResult(
            test_name="CBC - Hemoglobin",
            value="12.8",
            unit="g/dL",
            reference_range="12.0-16.0",
            flag="normal",
            collected_date=TODAY - timedelta(days=30),
        ),
    ],
    "P003": [
        LabResult(
            test_name="INR",
            value="2.8",
            unit="",
            reference_range="2.0-3.0",
            flag="normal",
            collected_date=TODAY - timedelta(days=7),
        ),
        LabResult(
            test_name="Creatinine",
            value="1.8",
            unit="mg/dL",
            reference_range="0.7-1.3",
            flag="high",
            collected_date=TODAY - timedelta(days=7),
        ),
        LabResult(
            test_name="eGFR",
            value="38",
            unit="mL/min/1.73m²",
            reference_range=">60",
            flag="low",
            collected_date=TODAY - timedelta(days=7),
        ),
        LabResult(
            test_name="BUN",
            value="32",
            unit="mg/dL",
            reference_range="7-20",
            flag="high",
            collected_date=TODAY - timedelta(days=7),
        ),
        LabResult(
            test_name="Potassium",
            value="4.8",
            unit="mEq/L",
            reference_range="3.5-5.0",
            flag="normal",
            collected_date=TODAY - timedelta(days=7),
        ),
        LabResult(
            test_name="Sodium",
            value="138",
            unit="mEq/L",
            reference_range="136-145",
            flag="normal",
            collected_date=TODAY - timedelta(days=7),
        ),
        LabResult(
            test_name="BNP",
            value="485",
            unit="pg/mL",
            reference_range="<100",
            flag="high",
            collected_date=TODAY - timedelta(days=7),
            notes="Elevated, consistent with CHF",
        ),
        LabResult(
            test_name="HbA1c",
            value="7.8",
            unit="%",
            reference_range="<7.0",
            flag="high",
            collected_date=TODAY - timedelta(days=30),
        ),
    ],
    "P004": [
        LabResult(
            test_name="HbA1c",
            value="8.5",
            unit="%",
            reference_range="<7.0",
            flag="high",
            collected_date=TODAY - timedelta(days=21),
        ),
        LabResult(
            test_name="Fasting Glucose",
            value="186",
            unit="mg/dL",
            reference_range="70-100",
            flag="high",
            collected_date=TODAY - timedelta(days=21),
        ),
        LabResult(
            test_name="Creatinine",
            value="0.9",
            unit="mg/dL",
            reference_range="0.6-1.1",
            flag="normal",
            collected_date=TODAY - timedelta(days=21),
        ),
        LabResult(
            test_name="Urine Microalbumin",
            value="45",
            unit="mg/L",
            reference_range="<30",
            flag="high",
            collected_date=TODAY - timedelta(days=21),
        ),
    ],
}

IMAGING = {
    "P001": [
        ImagingReport(
            report_id="IMG001",
            patient_id="P001",
            study_type="Chest X-ray",
            study_date=TODAY - timedelta(days=60),
            body_part="Chest",
            indication="Annual screening",
            findings=[
                ImagingFinding(
                    location="Heart",
                    finding="Normal cardiac silhouette",
                    severity="normal",
                ),
                ImagingFinding(
                    location="Lungs",
                    finding="Clear lung fields bilaterally",
                    severity="normal",
                ),
            ],
            impression=["No acute cardiopulmonary abnormality"],
            radiologist="Dr. 林放射科",
        ),
    ],
    "P002": [],
    "P003": [
        ImagingReport(
            report_id="IMG003",
            patient_id="P003",
            study_type="Echocardiogram",
            study_date=TODAY - timedelta(days=45),
            body_part="Heart",
            indication="Heart failure evaluation",
            findings=[
                ImagingFinding(
                    location="Left ventricle",
                    finding="Reduced ejection fraction",
                    severity="moderate",
                ),
                ImagingFinding(
                    location="Left atrium", finding="Mildly dilated", severity="mild"
                ),
                ImagingFinding(
                    location="Mitral valve",
                    finding="Mild regurgitation",
                    severity="mild",
                ),
            ],
            impression=[
                "LVEF 35-40%, reduced from prior",
                "Mild LV diastolic dysfunction",
                "Mild mitral regurgitation",
            ],
            critical_findings=["Reduced LVEF 35-40%"],
            radiologist="Dr. 心臟超音波",
        ),
        ImagingReport(
            report_id="IMG004",
            patient_id="P003",
            study_type="Chest X-ray",
            study_date=TODAY - timedelta(days=7),
            body_part="Chest",
            indication="Shortness of breath",
            findings=[
                ImagingFinding(
                    location="Heart", finding="Cardiomegaly", severity="moderate"
                ),
                ImagingFinding(
                    location="Lungs",
                    finding="Mild pulmonary vascular congestion",
                    severity="mild",
                ),
                ImagingFinding(
                    location="Pleural space",
                    finding="Small bilateral pleural effusions",
                    severity="mild",
                ),
            ],
            impression=[
                "Cardiomegaly with pulmonary vascular congestion",
                "Small bilateral pleural effusions",
                "Findings consistent with CHF",
            ],
            radiologist="Dr. 林放射科",
        ),
    ],
    "P004": [
        ImagingReport(
            report_id="IMG005",
            patient_id="P004",
            study_type="Abdominal Ultrasound",
            study_date=TODAY - timedelta(days=90),
            body_part="Abdomen",
            indication="Elevated liver enzymes",
            findings=[
                ImagingFinding(
                    location="Liver", finding="Hepatic steatosis", severity="mild"
                ),
                ImagingFinding(
                    location="Gallbladder", finding="No gallstones", severity="normal"
                ),
                ImagingFinding(
                    location="Kidneys",
                    finding="Normal size and echogenicity bilaterally",
                    severity="normal",
                ),
            ],
            impression=["Mild hepatic steatosis", "Otherwise unremarkable"],
            radiologist="Dr. 腹部超音波",
        ),
    ],
}

ENCOUNTERS = {
    "P001": [
        Encounter(
            encounter_id="E001",
            date=TODAY - timedelta(days=30),
            type="Office Visit",
            provider="Dr. 陳內科",
            chief_complaint="Diabetes follow-up",
            diagnoses=["Type 2 DM - suboptimal control", "Hypertension - controlled"],
            summary="HbA1c 7.2%, up from 6.8%. Discussed diet compliance. Increased Metformin to 500mg BID. Recheck in 3 months.",
        ),
        Encounter(
            encounter_id="E002",
            date=TODAY - timedelta(days=120),
            type="Office Visit",
            provider="Dr. 陳內科",
            chief_complaint="Annual physical",
            diagnoses=["Type 2 DM", "Hypertension", "Hyperlipidemia"],
            summary="Routine annual exam. All conditions stable. Continue current medications.",
        ),
    ],
    "P002": [
        Encounter(
            encounter_id="E003",
            date=TODAY - timedelta(days=45),
            type="Office Visit",
            provider="Dr. 王家醫",
            chief_complaint="Thyroid follow-up",
            diagnoses=["Hypothyroidism - controlled"],
            summary="TSH normalized on current dose. Continue Levothyroxine 50mcg daily.",
        ),
    ],
    "P003": [
        Encounter(
            encounter_id="E004",
            date=TODAY - timedelta(days=7),
            type="Office Visit",
            provider="Dr. 張心臟",
            chief_complaint="Increased shortness of breath",
            diagnoses=["CHF exacerbation", "Atrial fibrillation"],
            summary="Worsening dyspnea on exertion. CXR shows pulmonary congestion. Increased Furosemide to 40mg BID. Close follow-up in 1 week.",
        ),
        Encounter(
            encounter_id="E005",
            date=TODAY - timedelta(days=45),
            type="Cardiology Consult",
            provider="Dr. 張心臟",
            chief_complaint="Echo follow-up",
            diagnoses=["CHF with reduced EF", "Atrial fibrillation"],
            summary="Echo shows EF 35-40%. Continue current HF regimen. INR therapeutic.",
        ),
    ],
    "P004": [
        Encounter(
            encounter_id="E006",
            date=TODAY - timedelta(days=21),
            type="Office Visit",
            provider="Dr. 陳內科",
            chief_complaint="Diabetes management",
            diagnoses=["Type 2 DM - poor control", "Early diabetic nephropathy"],
            summary="HbA1c 8.5%, not at goal. Microalbuminuria detected. Started ACE inhibitor. Dietary counseling provided. Consider adding basal insulin if no improvement.",
        ),
    ],
}

if __name__ == "__main__":
    PATIENTS_RECORDS = []
    for i in PATIENTS:
        PATIENTS_RECORDS.append(
            PatientRecord(
                patient_id=i,
                info=PatientInfo(**PATIENTS[i]),
                medications=MEDICATIONS.get(i, []),
                allergies=ALLERGIES.get(i, []),
                problems=PROBLEMS.get(i, []),
                labs=LABS.get(i, []),
                imaging=IMAGING.get(i, []),
                encounters=ENCOUNTERS.get(i, []),
            )
        )
    for p in PATIENTS_RECORDS:
        filename = f"{p.patient_id}.json"
        base_dir = os.path.dirname(os.path.abspath(__file__))
        dir_path = os.path.join(base_dir, "mock_data")
        filename = os.path.join(dir_path, filename)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(p.model_dump_json(indent=4, ensure_ascii=False))
            print(f"Successfully exported: {filename}")
