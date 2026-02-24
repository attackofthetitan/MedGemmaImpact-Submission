import pytest
import httpx

BASE_URL = "http://localhost:8080"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as c:
        yield c


class TestHealthEndpoints:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "llm_servers" in data

    def test_rag_health(self, client):
        r = client.get("/v1/rag/health")
        assert r.status_code == 200
        data = r.json()
        assert "embedding_service" in data


class TestDemoEndpoints:
    def test_list_patients(self, client):
        r = client.get("/v1/demo/patients")
        assert r.status_code == 200
        data = r.json()
        assert "patients" in data
        assert len(data["patients"]) > 0

    def test_list_lab_reports(self, client):
        r = client.get("/v1/demo/lab-reports")
        assert r.status_code == 200
        data = r.json()
        assert "reports" in data

    def test_list_knowledge(self, client):
        r = client.get("/v1/demo/knowledge")
        assert r.status_code == 200
        data = r.json()
        assert "chunks" in data


class TestPatientEndpoints:
    def test_get_patient(self, client):
        r = client.get("/v1/patient/P001")
        assert r.status_code == 200
        data = r.json()
        assert "patient" in data

    def test_get_patient_not_found(self, client):
        r = client.get("/v1/patient/INVALID")
        assert r.status_code == 404

    def test_get_medications(self, client):
        r = client.get("/v1/patient/P001/medications")
        assert r.status_code == 200
        data = r.json()
        assert "medications" in data

    def test_get_allergies(self, client):
        r = client.get("/v1/patient/P001/allergies")
        assert r.status_code == 200
        data = r.json()
        assert "allergies" in data

    def test_get_problems(self, client):
        r = client.get("/v1/patient/P001/problems")
        assert r.status_code == 200
        data = r.json()
        assert "problems" in data

    def test_get_labs(self, client):
        r = client.get("/v1/patient/P001/labs")
        assert r.status_code == 200
        data = r.json()
        assert "labs" in data

    def test_get_imaging(self, client):
        r = client.get("/v1/patient/P001/imaging")
        assert r.status_code == 200
        data = r.json()
        assert "imaging" in data


class TestRAGEndpoints:
    def test_list_documents(self, client):
        r = client.get("/v1/rag/documents")
        assert r.status_code == 200
        data = r.json()
        assert "documents" in data

    def test_get_stats(self, client):
        r = client.get("/v1/rag/stats")
        assert r.status_code == 200
        data = r.json()
        assert "documents" in data

    def test_seed_demo_data(self, client):
        r = client.post("/v1/rag/seed")
        if r.status_code == 200:
            data = r.json()
            assert "total" in data
            assert "success" in data
        else:
            assert r.status_code == 503

    def test_search(self, client):
        r = client.post("/v1/rag/search", json={
            "query": "test",
            "top_k": 3
        })
        if r.status_code == 200:
            data = r.json()
            assert "results" in data
        else:
            assert r.status_code == 503

    def test_ingest_text(self, client):
        r = client.post("/v1/rag/ingest/text", json={
            "text": "Test document content",
            "source": "test.txt",
            "source_type": "test",
            "title": "Test Document"
        })
        if r.status_code == 200:
            data = r.json()
            assert "doc_id" in data
        else:
            assert r.status_code == 503


class TestWorkflowEndpoints:
    def test_process_message(self, client):
        r = client.post("/v1/message", json={
            "content": "我最近血糖控制不好",
            "patient_id": "P001"
        })
        if r.status_code == 200:
            data = r.json()
            assert "session_id" in data
        else:
            assert r.status_code == 503

    def test_list_sessions(self, client):
        r = client.get("/v1/sessions")
        assert r.status_code == 200
        data = r.json()
        assert "sessions" in data

    def test_get_session_not_found(self, client):
        r = client.get("/v1/session/invalid-session-id")
        assert r.status_code == 404


class TestLabReportEndpoints:
    def test_get_lab_report(self, client):
        r = client.get("/v1/lab-report/LAB001")
        assert r.status_code == 200
        data = r.json()
        assert "report_id" in data

    def test_get_lab_report_not_found(self, client):
        r = client.get("/v1/lab-report/INVALID")
        assert r.status_code == 404

    def test_analyze_lab_report(self, client):
        r = client.post("/v1/lab-report/LAB001/analyze")
        if r.status_code == 200:
            data = r.json()
            assert "analysis" in data or "summary" in data
        else:
            assert r.status_code in [503, 404]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])