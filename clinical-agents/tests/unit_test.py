import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestConfig:
    def test_config_from_env_defaults(self):
        import importlib
        import config
        importlib.reload(config)
        
        cfg = config.Config.from_env()
        assert "localhost:8001" in cfg.router_llm.base_url
        assert "localhost:8002" in cfg.medical_llm.base_url
        assert "localhost:8003" in cfg.embedding.base_url
        assert cfg.locale == "zh-TW"

    def test_llm_config_structure(self):
        from config import LLMConfig
        llm = LLMConfig(
            base_url="http://test:8001/v1",
            model_name="test-model"
        )
        assert llm.base_url == "http://test:8001/v1"
        assert llm.model_name == "test-model"
        assert llm.api_key == "not-needed"


class TestLLMClient:
    @pytest.fixture
    def llm_config(self):
        from config import LLMConfig
        return LLMConfig(
            base_url="http://localhost:8001/v1",
            model_name="test-model",
            temperature=0.1,
            max_tokens=512
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, llm_config):
        from llm_client import LLMClient
        client = LLMClient(llm_config)
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            result = await client.health_check()
            assert result is True
            assert client._healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, llm_config):
        from llm_client import LLMClient
        client = LLMClient(llm_config)
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Connection refused")
            
            result = await client.health_check()
            assert result is False
            assert client._healthy is False

    @pytest.mark.asyncio
    async def test_generate_when_unhealthy(self, llm_config):
        from llm_client import LLMClient, LLMConnectionError
        client = LLMClient(llm_config)
        client._healthy = False
        
        with pytest.raises(LLMConnectionError):
            await client.generate("test prompt")

    def test_parse_json_from_code_block(self, llm_config):
        from llm_client import LLMClient
        from pydantic import BaseModel
        
        class TestSchema(BaseModel):
            value: str
        
        client = LLMClient(llm_config)
        text = '```json\n{"value": "test"}\n```'
        result = client._parse_json(text, TestSchema)
        assert result.value == "test"

    def test_parse_json_raw(self, llm_config):
        from llm_client import LLMClient
        from pydantic import BaseModel
        
        class TestSchema(BaseModel):
            value: str
        
        client = LLMClient(llm_config)
        text = '{"value": "test"}'
        result = client._parse_json(text, TestSchema)
        assert result.value == "test"


class TestModels:
    def test_router_decision(self):
        from models import RouterDecision, Intent, RiskLevel
        decision = RouterDecision(
            intent=Intent.SYMPTOMS,
            risk_level=RiskLevel.HIGH,
            red_flags=["chest_pain"],
            next_action="proceed",
            reasoning="test"
        )
        assert decision.intent == Intent.SYMPTOMS
        assert decision.risk_level == RiskLevel.HIGH

    def test_intake_data(self):
        from models import IntakeData
        data = IntakeData(
            intake_id="test123",
            chief_complaint="headache"
        )
        assert data.intake_id == "test123"
        assert data.chief_complaint == "headache"

    def test_patient_reply(self):
        from models import PatientReply
        reply = PatientReply(
            draft_id="d1",
            greeting="Hello",
            acknowledgment="I understand",
            understanding="You have pain",
            response="Please rest",
            action_items=["Take medication"],
            warning_signs=["Fever"],
            closing="Take care"
        )
        assert len(reply.action_items) == 1


class TestDemoData:
    def test_get_patient(self):
        from demo_data import get_patient
        patient = get_patient("P001")
        assert patient is not None
        assert patient["name"] == "王小明"
        assert patient["mrn"] == "P001"

    def test_get_patient_not_found(self):
        from demo_data import get_patient
        patient = get_patient("INVALID")
        assert patient is None

    def test_get_medications(self):
        from demo_data import get_medications
        meds = get_medications("P001")
        assert len(meds) > 0
        assert meds[0].name == "Metformin"

    def test_get_allergies(self):
        from demo_data import get_allergies
        allergies = get_allergies("P001")
        assert isinstance(allergies, list)
        assert len(allergies) > 0

    def test_get_problems(self):
        from demo_data import get_problems
        problems = get_problems("P001")
        assert len(problems) > 0

    def test_search_knowledge(self):
        from demo_data import search_knowledge
        results = search_knowledge("胸痛", top_k=3)
        assert len(results) <= 3
        assert len(results) > 0


class TestTextChunker:
    def test_chunk_small_text(self):
        from rag_pipeline import TextChunker
        chunker = TextChunker(chunk_size=100)
        chunks = chunker.chunk("Small text", "doc1")
        assert len(chunks) == 1
        assert chunks[0].content == "Small text"

    def test_chunk_large_text(self):
        from rag_pipeline import TextChunker
        chunker = TextChunker(chunk_size=50, chunk_overlap=10)
        text = "This is sentence one. This is sentence two. This is sentence three. This is sentence four. This is the end."
        chunks = chunker.chunk(text, "doc1")
        assert len(chunks) > 1

    def test_chunk_no_separators(self):
        from rag_pipeline import TextChunker
        chunker = TextChunker(chunk_size=50, chunk_overlap=10)
        text = "A" * 200
        chunks = chunker.chunk(text, "doc1")
        assert len(chunks) > 1
        assert all(len(c.content) <= 50 for c in chunks)

    def test_chunk_empty_text(self):
        from rag_pipeline import TextChunker
        chunker = TextChunker()
        chunks = chunker.chunk("", "doc1")
        assert len(chunks) == 0

    def test_chunk_with_paragraphs(self):
        from rag_pipeline import TextChunker
        chunker = TextChunker(chunk_size=100)
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunker.chunk(text, "doc1")
        assert len(chunks) >= 1


class TestTextExtractor:
    def test_detect_type_pdf(self):
        from rag_pipeline import TextExtractor, DocumentType
        assert TextExtractor.detect_type("test.pdf") == DocumentType.PDF

    def test_detect_type_docx(self):
        from rag_pipeline import TextExtractor, DocumentType
        assert TextExtractor.detect_type("test.docx") == DocumentType.DOCX

    def test_detect_type_txt(self):
        from rag_pipeline import TextExtractor, DocumentType
        assert TextExtractor.detect_type("test.txt") == DocumentType.TXT

    def test_detect_type_image(self):
        from rag_pipeline import TextExtractor, DocumentType
        assert TextExtractor.detect_type("test.png") == DocumentType.IMAGE
        assert TextExtractor.detect_type("test.jpg") == DocumentType.IMAGE

    def test_detect_type_unknown(self):
        from rag_pipeline import TextExtractor, DocumentType
        assert TextExtractor.detect_type("test.xyz") == DocumentType.UNKNOWN


class TestEmbeddingClient:
    @pytest.fixture
    def embedding_client(self):
        from rag_pipeline import EmbeddingClient
        return EmbeddingClient(
            base_url="http://localhost:8003",
            model_name="test-embed"
        )

    @pytest.mark.asyncio
    async def test_health_check(self, embedding_client):
        with patch.object(embedding_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            result = await embedding_client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_embed_when_unhealthy(self, embedding_client):
        embedding_client._healthy = False
        with pytest.raises(ConnectionError):
            await embedding_client.embed(["test"])

    def test_base_url_normalization(self):
        from rag_pipeline import EmbeddingClient
        client1 = EmbeddingClient(base_url="http://localhost:8003/v1")
        client2 = EmbeddingClient(base_url="http://localhost:8003/")
        client3 = EmbeddingClient(base_url="http://localhost:8003")
        
        assert client1.base_url == "http://localhost:8003"
        assert client2.base_url == "http://localhost:8003"
        assert client3.base_url == "http://localhost:8003"


class TestDocumentMetadata:
    def test_create_metadata(self):
        from rag_pipeline import DocumentMetadata
        meta = DocumentMetadata(
            source="test.pdf",
            source_type="sop",
            title="Test Document",
            department="Cardiology"
        )
        assert meta.source == "test.pdf"
        assert meta.language == "zh-TW"


class TestAgentsHelpers:
    def test_extract_json_valid(self):
        from agents import extract_json
        result = extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_json_from_code_block(self):
        from agents import extract_json
        result = extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_extract_json_invalid(self):
        from agents import extract_json
        result = extract_json('not json', default={})
        assert result == {}

    def test_extract_json_array(self):
        from agents import extract_json
        result = extract_json('["a", "b", "c"]')
        assert result == ["a", "b", "c"]


class TestRouterAgent:
    def test_quick_screen_chest_pain(self):
        from agents import RouterAgent
        from config import config
        agent = RouterAgent(MagicMock())
        
        flags = agent.quick_screen("我有胸痛的症狀")
        assert "chest_pain" in flags

    def test_quick_screen_stroke(self):
        from agents import RouterAgent
        agent = RouterAgent(MagicMock())
        
        flags = agent.quick_screen("我中風了")
        assert "stroke_symptoms" in flags

    def test_quick_screen_breathing(self):
        from agents import RouterAgent
        agent = RouterAgent(MagicMock())
        
        flags = agent.quick_screen("我喘不過氣")
        assert "breathing_difficulty" in flags

    def test_quick_screen_no_flags(self):
        from agents import RouterAgent
        agent = RouterAgent(MagicMock())
        
        flags = agent.quick_screen("我想預約門診")
        assert len(flags) == 0


class TestQAGateAgent:
    def _make_agent(self, llm_response):
        from agents import QAGateAgent
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value=llm_response)
        return QAGateAgent(mock_client)

    @pytest.mark.asyncio
    async def test_passes_on_clean_response(self):
        from models import RiskLevel
        agent = self._make_agent('{"passed": true, "checks": {"no_diagnosis": true, "has_safety_warning": true, "appropriate_routing": true, "language_appropriate": true}, "issues": [], "suggestions": []}')
        result = await agent.validate("如有緊急狀況請撥打119。", RiskLevel.HIGH)
        assert result.passed is True
        assert result.issues == []

    @pytest.mark.asyncio
    async def test_fails_on_diagnosis(self):
        from models import RiskLevel
        agent = self._make_agent('{"passed": false, "checks": {"no_diagnosis": false, "has_safety_warning": true, "appropriate_routing": true, "language_appropriate": true}, "issues": ["Contains diagnostic statement"], "suggestions": []}')
        result = await agent.validate("您確診為糖尿病。", RiskLevel.LOW)
        assert result.passed is False
        assert result.checks["no_diagnosis"] is False

    @pytest.mark.asyncio
    async def test_fails_on_missing_safety_warning(self):
        from models import RiskLevel
        agent = self._make_agent('{"passed": false, "checks": {"no_diagnosis": true, "has_safety_warning": false, "appropriate_routing": true, "language_appropriate": true}, "issues": ["Missing emergency instruction"], "suggestions": []}')
        result = await agent.validate("請多休息。", RiskLevel.CRITICAL)
        assert result.passed is False
        assert result.checks["has_safety_warning"] is False

    @pytest.mark.asyncio
    async def test_propagates_connection_error(self):
        from agents import QAGateAgent
        from models import RiskLevel
        from llm_client import LLMConnectionError
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(side_effect=LLMConnectionError("offline"))
        agent = QAGateAgent(mock_client)
        with pytest.raises(LLMConnectionError):
            await agent.validate("content", RiskLevel.LOW)

    @pytest.mark.asyncio
    async def test_handles_malformed_llm_output(self):
        from models import RiskLevel
        agent = self._make_agent("not json")
        result = await agent.validate("content", RiskLevel.LOW)
        assert result.passed is False
        assert result.checks == {}


class TestEmergencyResponse:
    def test_emergency_response_exists(self):
        from agents import get_emergency_response
        response = get_emergency_response()
        assert response is not None
        assert "119" in response


class TestVectorStore:
    @pytest.fixture
    def temp_store(self, tmp_path):
        from rag_pipeline import VectorStore
        return VectorStore(
            persist_dir=str(tmp_path / "chroma"),
            collection_name="test_collection"
        )

    def test_get_stats(self, temp_store):
        stats = temp_store.get_stats()
        assert "count" in stats
        assert stats["count"] == 0

    def test_add_and_search(self, temp_store):
        from rag_pipeline import Chunk
        
        chunk = Chunk(
            chunk_id="c1",
            doc_id="d1",
            content="test content",
            metadata={"source": "test"},
            embedding=[0.1] * 384
        )
        
        temp_store.add([chunk])
        
        results = temp_store.search([0.1] * 384, top_k=1)
        assert len(results) == 1
        assert results[0][0] == "c1"


class TestKeywordSearch:
    def test_add_and_search(self):
        from rag_pipeline import KeywordSearch, Chunk
        
        search = KeywordSearch()
        chunk = Chunk(
            chunk_id="c1",
            doc_id="d1",
            content="This is a test document about medicine",
            metadata={}
        )
        
        search.add([chunk])
        results = search.search("medicine", top_k=1)
        
        assert len(results) == 1
        assert results[0][0] == "c1"

    def test_delete_by_doc_id(self):
        from rag_pipeline import KeywordSearch, Chunk
        
        search = KeywordSearch()
        chunk = Chunk(
            chunk_id="c1",
            doc_id="d1",
            content="test content",
            metadata={}
        )
        
        search.add([chunk])
        assert len(search._documents) == 1
        
        search.delete_by_doc_id("d1")
        assert len(search._documents) == 0


class TestRAGPipelineIntegration:
    @pytest.mark.asyncio
    async def test_ingest_text(self, tmp_path):
        from rag_pipeline import RAGPipeline, EmbeddingClient, VectorStore, DocumentMetadata
        
        embedding_client = EmbeddingClient()
        embedding_client._healthy = True
        
        with patch.object(embedding_client, 'embed', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [[0.1] * 384]
            
            pipeline = RAGPipeline(
                embedding_client=embedding_client,
                vector_store=VectorStore(persist_dir=str(tmp_path / "chroma"))
            )
            
            metadata = DocumentMetadata(
                source="test.txt",
                source_type="sop",
                title="Test"
            )
            
            doc = await pipeline.ingest_text("Test content", metadata)
            
            assert doc.doc_id is not None
            assert doc.content == "Test content"
            assert len(pipeline._documents) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])