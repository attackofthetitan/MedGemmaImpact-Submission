import asyncio
import json
import sqlite3
import threading
from datetime import date, timedelta, datetime
from pathlib import Path

from models import (
    PatientAccess,
    PatientInfo,
    PatientRecord,
    Medication,
    Allergy,
    Problem,
    LabResult,
    LabReport,
    ImagingReport,
    ImagingFinding,
    Encounter,
    Document,
    User,
    UserRole,
    AuditEntry,
)


class EHRDatabase:
    def __init__(self, db_path: str = "./clinical.db"):
        self.db_path = db_path
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    async def initialize(self):
        await asyncio.to_thread(self._create_tables)
        count = await asyncio.to_thread(self._count_patients)
        if count == 0:
            print("[DB] No patients found, seeding from mock_data...")
            await asyncio.to_thread(self._seed_from_mock_data)
        else:
            print(f"[DB] {count} patients already in database.")
        await asyncio.to_thread(self._ensure_default_admin)

    def _create_tables(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform_id TEXT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'staff',
                name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                sex TEXT NOT NULL,
                mrn TEXT UNIQUE NOT NULL,
                dob TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS user_patient_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform_id TEXT NOT NULL,
                patient_id TEXT NOT NULL REFERENCES patients(patient_id),
                relationship TEXT NOT NULL,
                access_level TEXT NOT NULL DEFAULT 'read',
                UNIQUE(platform_id, patient_id, relationship)
            );

            CREATE TABLE IF NOT EXISTS medications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL REFERENCES patients(patient_id),
                name TEXT NOT NULL,
                dose TEXT,
                frequency TEXT,
                route TEXT,
                indication TEXT,
                start_date TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS allergies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL REFERENCES patients(patient_id),
                allergen TEXT NOT NULL,
                reaction TEXT,
                severity TEXT,
                verified INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS problems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL REFERENCES patients(patient_id),
                icd_code TEXT,
                description TEXT NOT NULL,
                onset_date TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS lab_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL REFERENCES patients(patient_id),
                test_name TEXT NOT NULL,
                value TEXT NOT NULL,
                unit TEXT,
                reference_range TEXT,
                flag TEXT,
                collected_date TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS lab_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT UNIQUE NOT NULL,
                patient_id TEXT REFERENCES patients(patient_id),
                collected_date TEXT,
                reported_date TEXT,
                ordering_provider TEXT,
                interpretation TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS lab_report_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL REFERENCES lab_reports(report_id),
                test_name TEXT NOT NULL,
                value TEXT NOT NULL,
                unit TEXT,
                reference_range TEXT,
                flag TEXT
            );

            CREATE TABLE IF NOT EXISTS lab_report_critical_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL REFERENCES lab_reports(report_id),
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS imaging_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT UNIQUE NOT NULL,
                patient_id TEXT REFERENCES patients(patient_id),
                study_type TEXT NOT NULL,
                study_date TEXT,
                body_part TEXT NOT NULL,
                indication TEXT,
                technique TEXT,
                radiologist TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS imaging_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL REFERENCES imaging_reports(report_id),
                location TEXT NOT NULL,
                finding TEXT NOT NULL,
                severity TEXT
            );

            CREATE TABLE IF NOT EXISTS imaging_impressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL REFERENCES imaging_reports(report_id),
                impression TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS imaging_critical_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL REFERENCES imaging_reports(report_id),
                finding TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS encounters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id TEXT UNIQUE NOT NULL,
                patient_id TEXT NOT NULL REFERENCES patients(patient_id),
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                provider TEXT NOT NULL,
                chief_complaint TEXT,
                summary TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS encounter_diagnoses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id TEXT NOT NULL REFERENCES encounters(encounter_id),
                diagnosis TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL REFERENCES patients(patient_id),
                doc_type TEXT NOT NULL DEFAULT 'scan',
                filename TEXT NOT NULL,
                mime_type TEXT,
                data BLOB,
                description TEXT,
                uploaded_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT,
                details TEXT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_medications_patient ON medications(patient_id);
            CREATE INDEX IF NOT EXISTS idx_allergies_patient ON allergies(patient_id);
            CREATE INDEX IF NOT EXISTS idx_problems_patient ON problems(patient_id);
            CREATE INDEX IF NOT EXISTS idx_lab_results_patient ON lab_results(patient_id);
            CREATE INDEX IF NOT EXISTS idx_encounters_patient ON encounters(patient_id);
            CREATE INDEX IF NOT EXISTS idx_imaging_patient ON imaging_reports(patient_id);
            CREATE INDEX IF NOT EXISTS idx_documents_patient ON documents(patient_id);
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
        """)
        conn.commit()

    def _count_patients(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM patients").fetchone()
        return row[0]

    def _seed_from_mock_data(self):
        from config import config

        mock_dir = Path(config.mock_data_dir)
        if not mock_dir.exists():
            print(f"[DB] Mock data directory not found: {mock_dir}")
            return

        for f in sorted(mock_dir.glob("*.json")):
            with open(f, "r", encoding="utf-8") as infile:
                data = json.load(infile)
            record = PatientRecord.model_validate(data)
            self._insert_patient_record(record)
            print(f"[DB] Seeded patient {record.patient_id}: {record.info.name}")

        self._seed_lab_reports()

    def _insert_patient_record(self, record: PatientRecord):
        conn = self._get_conn()
        info = record.info

        conn.execute(
            "INSERT OR IGNORE INTO patients (patient_id, name, age, sex, mrn, dob) VALUES (?, ?, ?, ?, ?, ?)",
            (info.patient_id, info.name, info.age, info.sex, info.mrn, str(info.dob)),
        )

        for m in record.medications:
            conn.execute(
                "INSERT INTO medications (patient_id, name, dose, frequency, route, indication, start_date, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.patient_id,
                    m.name,
                    m.dose,
                    m.frequency,
                    m.route,
                    m.indication,
                    str(m.start_date) if m.start_date else None,
                    m.status,
                ),
            )

        for a in record.allergies:
            conn.execute(
                "INSERT INTO allergies (patient_id, allergen, reaction, severity, verified) VALUES (?, ?, ?, ?, ?)",
                (
                    record.patient_id,
                    a.allergen,
                    a.reaction,
                    a.severity,
                    int(a.verified),
                ),
            )

        for p in record.problems:
            conn.execute(
                "INSERT INTO problems (patient_id, icd_code, description, onset_date, status) VALUES (?, ?, ?, ?, ?)",
                (
                    record.patient_id,
                    p.icd_code,
                    p.description,
                    str(p.onset_date) if p.onset_date else None,
                    p.status,
                ),
            )

        for l in record.labs:
            conn.execute(
                "INSERT INTO lab_results (patient_id, test_name, value, unit, reference_range, flag, collected_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.patient_id,
                    l.test_name,
                    l.value,
                    l.unit,
                    l.reference_range,
                    l.flag,
                    str(l.collected_date) if l.collected_date else None,
                    l.notes,
                ),
            )

        for img in record.imaging:
            conn.execute(
                "INSERT OR IGNORE INTO imaging_reports (report_id, patient_id, study_type, study_date, body_part, indication, technique, radiologist) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    img.report_id,
                    record.patient_id,
                    img.study_type,
                    str(img.study_date) if img.study_date else None,
                    img.body_part,
                    img.indication,
                    img.technique,
                    img.radiologist,
                ),
            )
            for finding in img.findings:
                conn.execute(
                    "INSERT INTO imaging_findings (report_id, location, finding, severity) VALUES (?, ?, ?, ?)",
                    (
                        img.report_id,
                        finding.location,
                        finding.finding,
                        finding.severity,
                    ),
                )
            for imp in img.impression:
                conn.execute(
                    "INSERT INTO imaging_impressions (report_id, impression) VALUES (?, ?)",
                    (img.report_id, imp),
                )
            for cf in img.critical_findings:
                conn.execute(
                    "INSERT INTO imaging_critical_findings (report_id, finding) VALUES (?, ?)",
                    (img.report_id, cf),
                )

        for enc in record.encounters:
            conn.execute(
                "INSERT OR IGNORE INTO encounters (encounter_id, patient_id, date, type, provider, chief_complaint, summary) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    enc.encounter_id,
                    record.patient_id,
                    str(enc.date),
                    enc.type,
                    enc.provider,
                    enc.chief_complaint,
                    enc.summary,
                ),
            )
            for dx in enc.diagnoses:
                conn.execute(
                    "INSERT INTO encounter_diagnoses (encounter_id, diagnosis) VALUES (?, ?)",
                    (enc.encounter_id, dx),
                )

        conn.commit()

    def _seed_lab_reports(self):
        conn = self._get_conn()
        today = date.today()

        reports = [
            {
                "report_id": "LAB001",
                "patient_id": "P001",
                "collected_date": str(today - timedelta(days=1)),
                "reported_date": str(today),
                "ordering_provider": "Dr. 陳內科",
                "interpretation": "血糖控制不理想，HbA1c較前次上升。腎功能穩定。建議加強飲食控制並考慮調整藥物。",
                "results": [
                    ("Glucose, Fasting", "156", "mg/dL", "70-100", "high"),
                    ("HbA1c", "7.5", "%", "<7.0", "high"),
                    ("Creatinine", "1.1", "mg/dL", "0.7-1.3", "normal"),
                    ("BUN", "18", "mg/dL", "7-20", "normal"),
                    ("eGFR", "78", "mL/min/1.73m²", ">60", "normal"),
                    ("Potassium", "4.2", "mEq/L", "3.5-5.0", "normal"),
                    ("Sodium", "140", "mEq/L", "136-145", "normal"),
                ],
                "critical_values": [],
            },
            {
                "report_id": "LAB002",
                "patient_id": "P003",
                "collected_date": str(today - timedelta(days=1)),
                "reported_date": str(today),
                "ordering_provider": "Dr. 張心臟",
                "interpretation": "INR偏高，建議減少Warfarin劑量。腎功能較前惡化，BNP上升提示心衰竭控制不佳。需密切追蹤。",
                "results": [
                    ("INR", "3.8", "", "2.0-3.0", "high"),
                    ("Creatinine", "2.0", "mg/dL", "0.7-1.3", "high"),
                    ("eGFR", "32", "mL/min/1.73m²", ">60", "low"),
                    ("BUN", "38", "mg/dL", "7-20", "high"),
                    ("Potassium", "5.4", "mEq/L", "3.5-5.0", "high"),
                    ("BNP", "650", "pg/mL", "<100", "high"),
                ],
                "critical_values": ["INR 3.8 - 超出治療範圍"],
            },
        ]

        for rpt in reports:
            conn.execute(
                "INSERT OR IGNORE INTO lab_reports (report_id, patient_id, collected_date, reported_date, ordering_provider, interpretation) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    rpt["report_id"],
                    rpt["patient_id"],
                    rpt["collected_date"],
                    rpt["reported_date"],
                    rpt["ordering_provider"],
                    rpt["interpretation"],
                ),
            )
            for r in rpt["results"]:
                conn.execute(
                    "INSERT INTO lab_report_results (report_id, test_name, value, unit, reference_range, flag) VALUES (?, ?, ?, ?, ?, ?)",
                    (rpt["report_id"], *r),
                )
            for cv in rpt["critical_values"]:
                conn.execute(
                    "INSERT INTO lab_report_critical_values (report_id, value) VALUES (?, ?)",
                    (rpt["report_id"], cv),
                )

        conn.commit()

    def _ensure_default_admin(self):
        from config import config
        from auth import hash_password

        conn = self._get_conn()
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (config.auth.default_admin_user,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, name) VALUES (?, ?, ?, ?)",
                (
                    config.auth.default_admin_user,
                    hash_password(config.auth.default_admin_password),
                    "admin",
                    "System Admin",
                ),
            )
            conn.commit()
            print(f"[DB] Created default admin user: {config.auth.default_admin_user}")

    async def list_patients(self) -> list[dict]:
        def _q():
            conn = self._get_conn()
            rows = conn.execute("SELECT patient_id, name, age, sex, mrn, dob FROM patients ORDER BY patient_id").fetchall()
            results = []
            today = date.today()
            for r in rows:
                d = dict(r)
                if d.get("dob"):
                    try:
                        dob = date.fromisoformat(d["dob"])
                        d["age"] = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                    except (ValueError, TypeError):
                        pass
                results.append(d)
            return results
        return await asyncio.to_thread(_q)

    async def get_patient(self, patient_id: str) -> dict | None:
        def _q():
            conn = self._get_conn()
            row = conn.execute("SELECT patient_id, name, age, sex, mrn, dob FROM patients WHERE patient_id = ?", (patient_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("dob"):
                try:
                    dob = date.fromisoformat(d["dob"])
                    today = date.today()
                    d["age"] = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                except (ValueError, TypeError):
                    pass
            return d
        return await asyncio.to_thread(_q)

    async def create_patient(self, info: PatientInfo) -> dict:
        def _q():
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO patients (patient_id, name, age, sex, mrn, dob) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    info.patient_id,
                    info.name,
                    info.age,
                    info.sex,
                    info.mrn,
                    str(info.dob),
                ),
            )
            conn.commit()
            return {"patient_id": info.patient_id, "name": info.name, "mrn": info.mrn}

        return await asyncio.to_thread(_q)

    async def update_patient(self, patient_id: str, updates: dict) -> dict | None:
        def _q():
            conn = self._get_conn()
            allowed = {"name", "age", "sex", "dob"}
            fields = {k: v for k, v in updates.items() if k in allowed}
            if not fields:
                return None
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            values = list(fields.values()) + [patient_id]
            conn.execute(
                f"UPDATE patients SET {set_clause}, updated_at = datetime('now') WHERE patient_id = ?",
                values,
            )
            conn.commit()
            row = conn.execute(
                "SELECT patient_id, name, age, sex, mrn, dob FROM patients WHERE patient_id = ?",
                (patient_id,),
            ).fetchone()
            return dict(row) if row else None

        return await asyncio.to_thread(_q)

    async def get_medications(self, patient_id: str) -> list[Medication]:
        def _q():
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM medications WHERE patient_id = ? ORDER BY id",
                (patient_id,),
            ).fetchall()
            return [
                Medication(
                    id=r["id"],
                    name=r["name"],
                    dose=r["dose"],
                    frequency=r["frequency"],
                    route=r["route"],
                    indication=r["indication"],
                    start_date=date.fromisoformat(r["start_date"])
                    if r["start_date"]
                    else None,
                    status=r["status"],
                )
                for r in rows
            ]

        return await asyncio.to_thread(_q)

    async def add_medication(self, patient_id: str, med: Medication) -> int:
        def _q():
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT INTO medications (patient_id, name, dose, frequency, route, indication, start_date, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    patient_id,
                    med.name,
                    med.dose,
                    med.frequency,
                    med.route,
                    med.indication,
                    str(med.start_date) if med.start_date else None,
                    med.status,
                ),
            )
            conn.commit()
            return cur.lastrowid

        return await asyncio.to_thread(_q)

    async def update_medication(
        self, patient_id: str, med_id: int, updates: dict
    ) -> bool:
        def _q():
            conn = self._get_conn()
            allowed = {
                "name",
                "dose",
                "frequency",
                "route",
                "indication",
                "start_date",
                "status",
            }
            fields = {k: v for k, v in updates.items() if k in allowed}
            if not fields:
                return False
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            values = list(fields.values()) + [med_id, patient_id]
            cur = conn.execute(
                f"UPDATE medications SET {set_clause} WHERE id = ? AND patient_id = ?",
                values,
            )
            conn.commit()
            return cur.rowcount > 0

        return await asyncio.to_thread(_q)

    async def get_allergies(self, patient_id: str) -> list[Allergy]:
        def _q():
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM allergies WHERE patient_id = ? ORDER BY id",
                (patient_id,),
            ).fetchall()
            return [
                Allergy(
                    id=r["id"],
                    allergen=r["allergen"],
                    reaction=r["reaction"],
                    severity=r["severity"],
                    verified=bool(r["verified"]),
                )
                for r in rows
            ]

        return await asyncio.to_thread(_q)

    async def add_allergy(self, patient_id: str, allergy: Allergy) -> int:
        def _q():
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT INTO allergies (patient_id, allergen, reaction, severity, verified) VALUES (?, ?, ?, ?, ?)",
                (
                    patient_id,
                    allergy.allergen,
                    allergy.reaction,
                    allergy.severity,
                    int(allergy.verified),
                ),
            )
            conn.commit()
            return cur.lastrowid

        return await asyncio.to_thread(_q)

    async def get_problems(self, patient_id: str) -> list[Problem]:
        def _q():
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM problems WHERE patient_id = ? ORDER BY id", (patient_id,)
            ).fetchall()
            return [
                Problem(
                    id=r["id"],
                    icd_code=r["icd_code"],
                    description=r["description"],
                    onset_date=date.fromisoformat(r["onset_date"])
                    if r["onset_date"]
                    else None,
                    status=r["status"],
                )
                for r in rows
            ]

        return await asyncio.to_thread(_q)

    async def add_problem(self, patient_id: str, problem: Problem) -> int:
        def _q():
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT INTO problems (patient_id, icd_code, description, onset_date, status) VALUES (?, ?, ?, ?, ?)",
                (
                    patient_id,
                    problem.icd_code,
                    problem.description,
                    str(problem.onset_date) if problem.onset_date else None,
                    problem.status,
                ),
            )
            conn.commit()
            return cur.lastrowid

        return await asyncio.to_thread(_q)

    async def update_problem(
        self, patient_id: str, prob_id: int, updates: dict
    ) -> bool:
        def _q():
            conn = self._get_conn()
            allowed = {"icd_code", "description", "onset_date", "status"}
            fields = {k: v for k, v in updates.items() if k in allowed}
            if not fields:
                return False
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            values = list(fields.values()) + [prob_id, patient_id]
            cur = conn.execute(
                f"UPDATE problems SET {set_clause} WHERE id = ? AND patient_id = ?",
                values,
            )
            conn.commit()
            return cur.rowcount > 0

        return await asyncio.to_thread(_q)

    async def get_labs(self, patient_id: str, days: int = 30) -> list[LabResult]:
        def _q():
            conn = self._get_conn()
            cutoff = str(date.today() - timedelta(days=days))
            rows = conn.execute(
                "SELECT * FROM lab_results WHERE patient_id = ? AND (collected_date >= ? OR collected_date IS NULL) ORDER BY collected_date DESC",
                (patient_id, cutoff),
            ).fetchall()
            return [
                LabResult(
                    id=r["id"],
                    test_name=r["test_name"],
                    value=r["value"],
                    unit=r["unit"],
                    reference_range=r["reference_range"],
                    flag=r["flag"],
                    collected_date=date.fromisoformat(r["collected_date"])
                    if r["collected_date"]
                    else None,
                    notes=r["notes"],
                )
                for r in rows
            ]

        return await asyncio.to_thread(_q)

    async def add_lab_result(self, patient_id: str, lab: LabResult) -> int:
        def _q():
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT INTO lab_results (patient_id, test_name, value, unit, reference_range, flag, collected_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    patient_id,
                    lab.test_name,
                    lab.value,
                    lab.unit,
                    lab.reference_range,
                    lab.flag,
                    str(lab.collected_date) if lab.collected_date else None,
                    lab.notes,
                ),
            )
            conn.commit()
            return cur.lastrowid

        return await asyncio.to_thread(_q)

    async def get_lab_report(self, report_id: str) -> LabReport | None:
        def _q():
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM lab_reports WHERE report_id = ?", (report_id,)
            ).fetchone()
            if not row:
                return None
            results = conn.execute(
                "SELECT * FROM lab_report_results WHERE report_id = ?", (report_id,)
            ).fetchall()
            crit = conn.execute(
                "SELECT value FROM lab_report_critical_values WHERE report_id = ?",
                (report_id,),
            ).fetchall()
            return LabReport(
                report_id=row["report_id"],
                patient_id=row["patient_id"],
                collected_date=date.fromisoformat(row["collected_date"])
                if row["collected_date"]
                else None,
                reported_date=date.fromisoformat(row["reported_date"])
                if row["reported_date"]
                else None,
                ordering_provider=row["ordering_provider"],
                interpretation=row["interpretation"],
                results=[
                    LabResult(
                        test_name=r["test_name"],
                        value=r["value"],
                        unit=r["unit"],
                        reference_range=r["reference_range"],
                        flag=r["flag"],
                    )
                    for r in results
                ],
                critical_values=[c["value"] for c in crit],
            )

        return await asyncio.to_thread(_q)

    async def add_lab_report(self, report: LabReport) -> str:
        def _q():
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO lab_reports (report_id, patient_id, collected_date, reported_date, ordering_provider, interpretation) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    report.report_id,
                    report.patient_id,
                    str(report.collected_date) if report.collected_date else None,
                    str(report.reported_date) if report.reported_date else None,
                    report.ordering_provider,
                    report.interpretation,
                ),
            )
            for r in report.results:
                conn.execute(
                    "INSERT INTO lab_report_results (report_id, test_name, value, unit, reference_range, flag) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        report.report_id,
                        r.test_name,
                        r.value,
                        r.unit,
                        r.reference_range,
                        r.flag,
                    ),
                )
            for cv in report.critical_values:
                conn.execute(
                    "INSERT INTO lab_report_critical_values (report_id, value) VALUES (?, ?)",
                    (report.report_id, cv),
                )
            conn.commit()
            return report.report_id

        return await asyncio.to_thread(_q)

    async def get_imaging(
        self, patient_id: str, days: int = 180
    ) -> list[ImagingReport]:
        def _q():
            conn = self._get_conn()
            cutoff = str(date.today() - timedelta(days=days))
            rows = conn.execute(
                "SELECT * FROM imaging_reports WHERE patient_id = ? AND (study_date >= ? OR study_date IS NULL) ORDER BY study_date DESC",
                (patient_id, cutoff),
            ).fetchall()
            reports = []
            for r in rows:
                findings = conn.execute(
                    "SELECT * FROM imaging_findings WHERE report_id = ?",
                    (r["report_id"],),
                ).fetchall()
                impressions = conn.execute(
                    "SELECT impression FROM imaging_impressions WHERE report_id = ?",
                    (r["report_id"],),
                ).fetchall()
                criticals = conn.execute(
                    "SELECT finding FROM imaging_critical_findings WHERE report_id = ?",
                    (r["report_id"],),
                ).fetchall()
                reports.append(
                    ImagingReport(
                        report_id=r["report_id"],
                        patient_id=r["patient_id"],
                        study_type=r["study_type"],
                        study_date=date.fromisoformat(r["study_date"])
                        if r["study_date"]
                        else None,
                        body_part=r["body_part"],
                        indication=r["indication"],
                        technique=r["technique"],
                        radiologist=r["radiologist"],
                        findings=[
                            ImagingFinding(
                                location=f["location"],
                                finding=f["finding"],
                                severity=f["severity"],
                            )
                            for f in findings
                        ],
                        impression=[i["impression"] for i in impressions],
                        critical_findings=[c["finding"] for c in criticals],
                    )
                )
            return reports

        return await asyncio.to_thread(_q)

    async def add_imaging_report(self, patient_id: str, report: ImagingReport) -> str:
        def _q():
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO imaging_reports (report_id, patient_id, study_type, study_date, body_part, indication, technique, radiologist) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    report.report_id,
                    patient_id,
                    report.study_type,
                    str(report.study_date) if report.study_date else None,
                    report.body_part,
                    report.indication,
                    report.technique,
                    report.radiologist,
                ),
            )
            for f in report.findings:
                conn.execute(
                    "INSERT INTO imaging_findings (report_id, location, finding, severity) VALUES (?, ?, ?, ?)",
                    (report.report_id, f.location, f.finding, f.severity),
                )
            for imp in report.impression:
                conn.execute(
                    "INSERT INTO imaging_impressions (report_id, impression) VALUES (?, ?)",
                    (report.report_id, imp),
                )
            for cf in report.critical_findings:
                conn.execute(
                    "INSERT INTO imaging_critical_findings (report_id, finding) VALUES (?, ?)",
                    (report.report_id, cf),
                )
            conn.commit()
            return report.report_id

        return await asyncio.to_thread(_q)

    async def get_encounters(self, patient_id: str, days: int = 90) -> list[Encounter]:
        def _q():
            conn = self._get_conn()
            cutoff = str(date.today() - timedelta(days=days))
            rows = conn.execute(
                "SELECT * FROM encounters WHERE patient_id = ? AND date >= ? ORDER BY date DESC",
                (patient_id, cutoff),
            ).fetchall()
            encounters = []
            for r in rows:
                dx = conn.execute(
                    "SELECT diagnosis FROM encounter_diagnoses WHERE encounter_id = ?",
                    (r["encounter_id"],),
                ).fetchall()
                encounters.append(
                    Encounter(
                        encounter_id=r["encounter_id"],
                        date=date.fromisoformat(r["date"]),
                        type=r["type"],
                        provider=r["provider"],
                        chief_complaint=r["chief_complaint"],
                        summary=r["summary"],
                        diagnoses=[d["diagnosis"] for d in dx],
                    )
                )
            return encounters

        return await asyncio.to_thread(_q)

    async def add_encounter(self, patient_id: str, enc: Encounter) -> str:
        def _q():
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO encounters (encounter_id, patient_id, date, type, provider, chief_complaint, summary) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    enc.encounter_id,
                    patient_id,
                    str(enc.date),
                    enc.type,
                    enc.provider,
                    enc.chief_complaint,
                    enc.summary,
                ),
            )
            for dx in enc.diagnoses:
                conn.execute(
                    "INSERT INTO encounter_diagnoses (encounter_id, diagnosis) VALUES (?, ?)",
                    (enc.encounter_id, dx),
                )
            conn.commit()
            return enc.encounter_id

        return await asyncio.to_thread(_q)

    async def add_document(self, patient_id: str, filename: str, data: bytes,
                           mime_type: str | None = None, doc_type: str = "scan",
                           description: str | None = None, uploaded_by: str | None = None) -> int:
        def _q():
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT INTO documents (patient_id, doc_type, filename, mime_type, data, description, uploaded_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    patient_id,
                    doc_type,
                    filename,
                    mime_type,
                    data,
                    description,
                    uploaded_by,
                ),
            )
            conn.commit()
            return cur.lastrowid

        return await asyncio.to_thread(_q)

    async def get_documents(self, patient_id: str) -> list[Document]:
        def _q():
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT id, patient_id, doc_type, filename, mime_type, description, uploaded_by, created_at FROM documents WHERE patient_id = ? ORDER BY created_at DESC",
                (patient_id,),
            ).fetchall()
            return [
                Document(
                    id=r["id"],
                    patient_id=r["patient_id"],
                    doc_type=r["doc_type"],
                    filename=r["filename"],
                    mime_type=r["mime_type"],
                    description=r["description"],
                    uploaded_by=r["uploaded_by"],
                    created_at=datetime.fromisoformat(r["created_at"])
                    if r["created_at"]
                    else None,
                )
                for r in rows
            ]

        return await asyncio.to_thread(_q)

    async def get_document_data(
        self, doc_id: int, patient_id: str
    ) -> tuple[bytes, str, str] | None:
        def _q():
            conn = self._get_conn()
            row = conn.execute(
                "SELECT data, filename, mime_type FROM documents WHERE id = ? AND patient_id = ?",
                (doc_id, patient_id),
            ).fetchone()
            if not row:
                return None
            return (row["data"], row["filename"], row["mime_type"])

        return await asyncio.to_thread(_q)

    async def get_user_by_username(self, username: str) -> dict | None:
        def _q():
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? AND active = 1", (username,)
            ).fetchone()
            return dict(row) if row else None

        return await asyncio.to_thread(_q)

    async def get_user_by_platform_id(self, platform_id: str) -> dict | None:
        def _q():
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM users WHERE platform_id = ? AND active = 1",
                (platform_id,),
            ).fetchone()
            return dict(row) if row else None

        return await asyncio.to_thread(_q)

    async def get_user_by_id(self, user_id: int) -> dict | None:
        def _q():
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)
            ).fetchone()
            return dict(row) if row else None

        return await asyncio.to_thread(_q)

    async def create_user(
        self,
        username: str,
        password_hash: str,
        role: str,
        name: str,
    ) -> int:
        def _q():
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, role, name) VALUES (?, ?, ?, ?)",
                (username, password_hash, role, name),
            )
            conn.commit()
            return cur.lastrowid

        return await asyncio.to_thread(_q)

    async def list_users(self) -> list[User]:
        def _q():
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT id, platform_id ,username, role, name, active, created_at FROM users ORDER BY id"
            ).fetchall()
            return [
                User(
                    id=r["id"],
                    platform_id=r["platform_id"],
                    username=r["username"],
                    role=UserRole(r["role"]),
                    name=r["name"],
                    active=bool(r["active"]),
                    created_at=datetime.fromisoformat(r["created_at"])
                    if r["created_at"]
                    else None,
                )
                for r in rows
            ]

        return await asyncio.to_thread(_q)

    async def update_user(self, user_id: int, updates: dict) -> dict | None:
        def _q():
            conn = self._get_conn()
            allowed = ["platform_id", "role", "name", "active"]
            fields = {k: v for k, v in updates.items() if k in allowed}
            if not fields:
                return None
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            values = list(fields.values()) + [user_id]
            conn.execute(f"UPDATE users SET {set_clause}  WHERE id = ?", values)
            conn.commit()
            row = conn.execute(
                "SELECT id, platform_id ,username, role, name, active, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

        return await asyncio.to_thread(_q)

    async def list_user_patient_access(self) -> list:
        def _q():
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT id, patient_id, platform_id, relationship,access_level FROM user_patient_access ORDER BY id"
            ).fetchall()
            return [
                PatientAccess(
                    id=r["id"],
                    patient_id=r["patient_id"],
                    platform_id=r["platform_id"],
                    relationship=r["relationship"],
                    access_level=r["access_level"],
                )
                for r in rows
            ]

        return await asyncio.to_thread(_q)

    async def get_patient_by_platform_id(self, platform_id: str):
        def _q():
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM user_patient_access WHERE platform_id = ?",
                (platform_id,),
            ).fetchone()
            return dict(row) if row else None

        return await asyncio.to_thread(_q)
    
    async def get_platform_id_by_patient_id(self, patient_id: str):
        def _q():
            conn = self._get_conn()
            row = conn.execute(
                "SELECT platform_id FROM user_patient_access WHERE patient_id = ?",
                (patient_id,),
            ).fetchone()
            return row["platform_id"] if row else None

        return await asyncio.to_thread(_q)

    async def get_staff_by_relationship(self, relationship: str, patient_id: str):
        def _q():
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM user_patient_access WHERE relationship = ? AND patient_id = ?",
                (relationship, patient_id),
            ).fetchone()
            return dict(row) if row else None

        return await asyncio.to_thread(_q)

    async def creae_user_patient_access(
        self,
        patient_id: str,
        platform_id: str,
        relationship: str,
        access_level: str,
    ) -> bool:
        def _q():
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT INTO user_patient_access (patient_id, platform_id, relationship, access_level) VALUES (?, ?, ?, ?)",
                (patient_id, platform_id, relationship, access_level),
            )
            conn.commit()
            return cur.lastrowid

        return await asyncio.to_thread(_q)

    async def log_audit(
        self,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        user_id: int | None = None,
        username: str | None = None,
        details: dict | None = None,
    ):
        def _q():
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO audit_log (user_id, username, action, resource_type, resource_id, details) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    username,
                    action,
                    resource_type,
                    resource_id,
                    json.dumps(details or {}, ensure_ascii=False),
                ),
            )
            conn.commit()

        await asyncio.to_thread(_q)

    async def get_audit_log(
        self, limit: int = 100, resource_type: str | None = None
    ) -> list[AuditEntry]:
        def _q():
            conn = self._get_conn()
            if resource_type:
                rows = conn.execute(
                    "SELECT * FROM audit_log WHERE resource_type = ? ORDER BY timestamp DESC LIMIT ?",
                    (resource_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
                ).fetchall()
            return [
                AuditEntry(
                    id=r["id"],
                    user_id=r["user_id"],
                    username=r["username"],
                    action=r["action"],
                    resource_type=r["resource_type"],
                    resource_id=r["resource_id"],
                    details=json.loads(r["details"]) if r["details"] else {},
                    timestamp=datetime.fromisoformat(r["timestamp"])
                    if r["timestamp"]
                    else None,
                )
                for r in rows
            ]

        return await asyncio.to_thread(_q)

    async def close(self):
        def _close():
            conn = getattr(self._local, "conn", None)
            if conn:
                conn.close()
                self._local.conn = None
        await asyncio.to_thread(_close)


db = EHRDatabase()
