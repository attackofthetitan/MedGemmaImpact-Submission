"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  ALLERGY_SEVERITY_OPTIONS,
  DOCUMENT_TYPE_OPTIONS,
  IMAGING_FINDING_SEVERITY_OPTIONS,
  LAB_FLAG_OPTIONS,
  MEDICATION_STATUS_OPTIONS,
  PROBLEM_STATUS_OPTIONS,
  SEX_OPTIONS,
} from "@/lib/model-options";
import type {
  Allergy,
  DocumentEntry,
  Encounter,
  ImagingFinding,
  ImagingReport,
  LabResult,
  Medication,
  PatientInfo,
  PatientInfoCreatePayload,
  Problem,
} from "@/lib/types";
import { Button, Card, Input, Select, TextArea } from "@/components/ui/primitives";
import { OptLabel, ReqLabel } from "@/components/dashboard/common/FormLabels";
import { splitLines } from "@/components/dashboard/common/textParsers";
import { useDashboardContext } from "@/components/dashboard/shell/DashboardContext";
import { CreateCard } from "@/features/ehr-create/components/CreateCard";

export function EhrCreateTab() {
  const { token, perms, show } = useDashboardContext();
  const [patientId, setPatientId] = useState("");
  const [patientOptions, setPatientOptions] = useState<PatientInfo[]>([]);
  const [newPatient, setNewPatient] = useState<PatientInfoCreatePayload>({ name: "", sex: "male", dob: "2000-01-01" });
  const [med, setMed] = useState<Medication>({ name: "", dose: "", frequency: "", route: "", indication: "", start_date: "", status: "active" });
  const [allergy, setAllergy] = useState<Allergy>({ allergen: "", reaction: "", severity: null, verified: false });
  const [problem, setProblem] = useState<Problem>({ description: "", icd_code: "", onset_date: "", status: "active" });
  const [lab, setLab] = useState<LabResult>({ test_name: "", value: "", unit: "", reference_range: "", flag: null, collected_date: "", notes: "" });
  const [finding, setFinding] = useState<ImagingFinding>({ location: "", finding: "", severity: null });
  const [imagingImpressionText, setImagingImpressionText] = useState("");
  const [imagingCriticalText, setImagingCriticalText] = useState("");
  const [imaging, setImaging] = useState<ImagingReport>({ report_id: "", patient_id: "", study_type: "", study_date: "", body_part: "", indication: "", technique: "", findings: [], impression: [], critical_findings: [], radiologist: "" });
  const [encounterDiagText, setEncounterDiagText] = useState("");
  const [encounter, setEncounter] = useState<Encounter>({ encounter_id: "", date: new Date().toISOString().slice(0, 10), type: "", provider: "", chief_complaint: "", diagnoses: [], summary: "" });
  const [docFile, setDocFile] = useState<File | null>(null);
  const [docType, setDocType] = useState<DocumentEntry["doc_type"]>("scan");
  const [docDesc, setDocDesc] = useState("");

  useEffect(() => {
    api.listDemoPatients(token)
      .then((res) => {
        setPatientOptions(res.patients);
        setPatientId((prev) => (prev || !res.patients.length ? prev : res.patients[0].patient_id));
      })
      .catch((e) => show("error", String(e)));
  }, [show, token]);

  return (
    <div className="col">
      <Card title="EHR Create">
        <p className="section-intro">Select a patient, then add clinical records using the forms below.</p>
        <ReqLabel text="Patient ID for nested entities" />
        <Select required value={patientId} onChange={(e) => setPatientId(e.target.value)} disabled={!patientOptions.length}>
          <option value="">-- select patient --</option>
          {patientOptions.map((p) => (
            <option key={p.patient_id} value={p.patient_id}>
              {p.patient_id} · {p.name}
            </option>
          ))}
        </Select>
      </Card>

      <div className="grid-2">
        {perms.canCreatePatient ? (
          <Card title="Create Patient">
            <div className="form-grid">
              <ReqLabel text="name" /><Input required value={newPatient.name} onChange={(e) => setNewPatient((v) => ({ ...v, name: e.target.value }))} />
              <ReqLabel text="sex" /><Select required value={newPatient.sex} onChange={(e) => setNewPatient((v) => ({ ...v, sex: e.target.value as PatientInfoCreatePayload["sex"] }))}>{SEX_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
              <ReqLabel text="dob" /><Input required type="date" value={newPatient.dob} onChange={(e) => setNewPatient((v) => ({ ...v, dob: e.target.value }))} />
              <Button onClick={() => api.createPatient(token, newPatient).then(() => show("success", "Patient created")).catch((e) => show("error", String(e)))}>Create Patient</Button>
            </div>
          </Card>
        ) : null}

        {perms.canWriteMeds ? (
          <CreateCard title="Add Medication" onSubmit={() => api.addMedication(token, patientId, med)} show={show}>
            <ReqLabel text="name" /><Input required value={med.name} onChange={(e) => setMed((v) => ({ ...v, name: e.target.value }))} />
            <OptLabel text="dose" /><Input value={med.dose ?? ""} onChange={(e) => setMed((v) => ({ ...v, dose: e.target.value }))} />
            <OptLabel text="frequency" /><Input value={med.frequency ?? ""} onChange={(e) => setMed((v) => ({ ...v, frequency: e.target.value }))} />
            <OptLabel text="route" /><Input value={med.route ?? ""} onChange={(e) => setMed((v) => ({ ...v, route: e.target.value }))} />
            <OptLabel text="indication" /><Input value={med.indication ?? ""} onChange={(e) => setMed((v) => ({ ...v, indication: e.target.value }))} />
            <OptLabel text="start_date" /><Input type="date" value={med.start_date ?? ""} onChange={(e) => setMed((v) => ({ ...v, start_date: e.target.value }))} />
            <OptLabel text="status" /><Select value={med.status} onChange={(e) => setMed((v) => ({ ...v, status: e.target.value as Medication["status"] }))}>{MEDICATION_STATUS_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
          </CreateCard>
        ) : null}

        {perms.canWriteAllergiesLabsEncountersDocs ? (
          <CreateCard title="Add Allergy" onSubmit={() => api.addAllergy(token, patientId, allergy)} show={show}>
            <ReqLabel text="allergen" /><Input required value={allergy.allergen} onChange={(e) => setAllergy((v) => ({ ...v, allergen: e.target.value }))} />
            <OptLabel text="reaction" /><Input value={allergy.reaction ?? ""} onChange={(e) => setAllergy((v) => ({ ...v, reaction: e.target.value }))} />
            <OptLabel text="severity" /><Select value={allergy.severity ?? ""} onChange={(e) => setAllergy((v) => ({ ...v, severity: (e.target.value || null) as Allergy["severity"] }))}><option value="">none</option>{ALLERGY_SEVERITY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
            <label className="small"><input type="checkbox" checked={allergy.verified} onChange={(e) => setAllergy((v) => ({ ...v, verified: e.target.checked }))} /> verified</label>
          </CreateCard>
        ) : null}

        {perms.canWriteProblems ? (
          <CreateCard title="Add Problem" onSubmit={() => api.addProblem(token, patientId, problem)} show={show}>
            <ReqLabel text="description" /><Input required value={problem.description} onChange={(e) => setProblem((v) => ({ ...v, description: e.target.value }))} />
            <OptLabel text="icd_code" /><Input value={problem.icd_code ?? ""} onChange={(e) => setProblem((v) => ({ ...v, icd_code: e.target.value }))} />
            <OptLabel text="onset_date" /><Input type="date" value={problem.onset_date ?? ""} onChange={(e) => setProblem((v) => ({ ...v, onset_date: e.target.value }))} />
            <OptLabel text="status" /><Select value={problem.status} onChange={(e) => setProblem((v) => ({ ...v, status: e.target.value as Problem["status"] }))}>{PROBLEM_STATUS_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
          </CreateCard>
        ) : null}

        {perms.canWriteAllergiesLabsEncountersDocs ? (
          <CreateCard title="Add Lab" onSubmit={() => api.addLab(token, patientId, lab)} show={show}>
            <ReqLabel text="test_name" /><Input required value={lab.test_name} onChange={(e) => setLab((v) => ({ ...v, test_name: e.target.value }))} />
            <ReqLabel text="value" /><Input required value={lab.value} onChange={(e) => setLab((v) => ({ ...v, value: e.target.value }))} />
            <OptLabel text="unit" /><Input value={lab.unit ?? ""} onChange={(e) => setLab((v) => ({ ...v, unit: e.target.value }))} />
            <OptLabel text="reference_range" /><Input value={lab.reference_range ?? ""} onChange={(e) => setLab((v) => ({ ...v, reference_range: e.target.value }))} />
            <OptLabel text="flag" /><Select value={lab.flag ?? ""} onChange={(e) => setLab((v) => ({ ...v, flag: (e.target.value || null) as LabResult["flag"] }))}><option value="">none</option>{LAB_FLAG_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
            <OptLabel text="collected_date" /><Input type="date" value={lab.collected_date ?? ""} onChange={(e) => setLab((v) => ({ ...v, collected_date: e.target.value }))} />
            <OptLabel text="notes" /><TextArea value={lab.notes ?? ""} onChange={(e) => setLab((v) => ({ ...v, notes: e.target.value }))} />
          </CreateCard>
        ) : null}

        {perms.canWriteImaging ? (
          <CreateCard title="Add Imaging" onSubmit={() => api.addImaging(token, patientId, {
            study_type: imaging.study_type,
            study_date: imaging.study_date,
            body_part: imaging.body_part,
            indication: imaging.indication,
            technique: imaging.technique,
            radiologist: imaging.radiologist,
            findings: finding.location && finding.finding ? [finding] : [],
            impression: splitLines(imagingImpressionText),
            critical_findings: splitLines(imagingCriticalText),
          } as ImagingReport)} show={show}>
            <div className="hint">Provide exam type and body area to create an imaging report.</div>
            <ReqLabel text="study_type" /><Input required value={imaging.study_type} onChange={(e) => setImaging((v) => ({ ...v, study_type: e.target.value }))} />
            <ReqLabel text="body_part" /><Input required value={imaging.body_part} onChange={(e) => setImaging((v) => ({ ...v, body_part: e.target.value }))} />
            <OptLabel text="study_date" /><Input type="date" value={imaging.study_date ?? ""} onChange={(e) => setImaging((v) => ({ ...v, study_date: e.target.value }))} />
            <OptLabel text="indication" /><Input value={imaging.indication ?? ""} onChange={(e) => setImaging((v) => ({ ...v, indication: e.target.value }))} />
            <OptLabel text="technique" /><Input value={imaging.technique ?? ""} onChange={(e) => setImaging((v) => ({ ...v, technique: e.target.value }))} />
            <OptLabel text="radiologist" /><Input value={imaging.radiologist ?? ""} onChange={(e) => setImaging((v) => ({ ...v, radiologist: e.target.value }))} />
            <OptLabel text="finding.location" /><Input value={finding.location} onChange={(e) => setFinding((v) => ({ ...v, location: e.target.value }))} />
            <OptLabel text="finding.finding" /><Input value={finding.finding} onChange={(e) => setFinding((v) => ({ ...v, finding: e.target.value }))} />
            <OptLabel text="finding.severity" /><Select value={finding.severity ?? ""} onChange={(e) => setFinding((v) => ({ ...v, severity: (e.target.value || null) as ImagingFinding["severity"] }))}><option value="">none</option>{IMAGING_FINDING_SEVERITY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
            <OptLabel text="impression (one per line)" /><TextArea value={imagingImpressionText} onChange={(e) => setImagingImpressionText(e.target.value)} />
            <OptLabel text="critical_findings (one per line)" /><TextArea value={imagingCriticalText} onChange={(e) => setImagingCriticalText(e.target.value)} />
          </CreateCard>
        ) : null}

        {perms.canWriteAllergiesLabsEncountersDocs ? (
          <CreateCard title="Add Encounter" onSubmit={() => api.addEncounter(token, patientId, {
            ...encounter,
            diagnoses: splitLines(encounterDiagText),
          })} show={show}>
            <div className="hint">Complete the essential encounter details to save this record.</div>
            <ReqLabel text="encounter_id" /><Input required value={encounter.encounter_id} onChange={(e) => setEncounter((v) => ({ ...v, encounter_id: e.target.value }))} />
            <ReqLabel text="date" /><Input required type="date" value={encounter.date} onChange={(e) => setEncounter((v) => ({ ...v, date: e.target.value }))} />
            <ReqLabel text="type" /><Input required value={encounter.type} onChange={(e) => setEncounter((v) => ({ ...v, type: e.target.value }))} />
            <ReqLabel text="provider" /><Input required value={encounter.provider} onChange={(e) => setEncounter((v) => ({ ...v, provider: e.target.value }))} />
            <OptLabel text="chief_complaint" /><Input value={encounter.chief_complaint ?? ""} onChange={(e) => setEncounter((v) => ({ ...v, chief_complaint: e.target.value }))} />
            <OptLabel text="diagnoses (one per line)" /><TextArea value={encounterDiagText} onChange={(e) => setEncounterDiagText(e.target.value)} />
            <OptLabel text="summary" /><TextArea value={encounter.summary ?? ""} onChange={(e) => setEncounter((v) => ({ ...v, summary: e.target.value }))} />
          </CreateCard>
        ) : null}

        {perms.canWriteAllergiesLabsEncountersDocs ? (
          <Card title="Upload Document">
            <div className="col">
              <ReqLabel text="file" />
              <Input required type="file" onChange={(e) => setDocFile(e.target.files?.[0] ?? null)} />
              <OptLabel text="doc_type" />
              <Select value={docType} onChange={(e) => setDocType(e.target.value as DocumentEntry["doc_type"])}>{DOCUMENT_TYPE_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
              <OptLabel text="description" />
              <TextArea value={docDesc} onChange={(e) => setDocDesc(e.target.value)} />
              <Button onClick={() => {
                if (!docFile) {
                  show("error", "file is required");
                  return;
                }
                api.uploadDocument(token, patientId, docFile, docType, docDesc)
                  .then(() => show("success", "Document uploaded"))
                  .catch((e) => show("error", String(e)));
              }}>Upload</Button>
            </div>
          </Card>
        ) : null}
      </div>
    </div>
  );
}

