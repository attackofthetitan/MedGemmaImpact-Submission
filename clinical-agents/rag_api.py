import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from rag_pipeline import (
    RAGPipeline, DocumentMetadata, create_rag_pipeline,
    EmbeddingClient, VisionClient, VectorStore
)


class IngestTextRequest(BaseModel):
    text: str
    source: str
    source_type: str  # sop, education, protocol, clinical_note
    title: str | None = None
    department: str | None = None
    tags: list[str] = []


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    search_type: str = "hybrid"  # semantic, keyword, hybrid
    filter_source_type: str | None = None
    filter_department: str | None = None
    rerank: bool = False


class SearchResponse(BaseModel):
    query: str
    results: list[dict]
    total_results: int
    search_type: str
    reranked: bool


class DocumentResponse(BaseModel):
    doc_id: str
    source: str
    source_type: str
    title: str | None
    doc_type: str
    created_at: str
    chunk_count: int


router = APIRouter(prefix="/v1/rag", tags=["RAG"])

_pipeline: RAGPipeline | None = None


async def get_pipeline() -> RAGPipeline:
    global _pipeline
    
    if _pipeline is None:
        _pipeline = create_rag_pipeline(
            embedding_url=os.getenv("EMBEDDING_URL", "http://localhost:8003"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "embedgemma"),
            vision_url=os.getenv("VISION_URL", "http://localhost:8002/v1"),
            vision_model=os.getenv("VISION_MODEL", "medgemma"),
            persist_dir=os.getenv("CHROMA_DIR", "./chroma_db"),
        )
    
    return _pipeline


def get_llm_status():
    try:
        from server import llm_status
        return llm_status
    except ImportError:
        return {"embedding": False}


async def require_embedding():
    pipeline = await get_pipeline()
    llm_status = get_llm_status()
    
    if not llm_status.get("embedding", False):
        llm_status["embedding"] = await pipeline.embedding_client.health_check()
    
    if not llm_status.get("embedding", False):
        raise HTTPException(
            503, 
            f"Embedding service not available at {pipeline.embedding_client.base_url}"
        )


@router.get("/health")
async def rag_health():
    pipeline = await get_pipeline()
    llm_status = get_llm_status()
    
    llm_status["embedding"] = await pipeline.embedding_client.health_check()
    
    return {
        "status": "healthy" if llm_status["embedding"] else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "embedding_service": {
            "url": f"{pipeline.embedding_client.base_url}/v1/embeddings",
            "model": pipeline.embedding_client.model_name,
            "connected": llm_status["embedding"],
        },
        "vector_store": pipeline.vector_store.get_stats(),
        "documents": len(pipeline._documents)
    }


@router.post("/ingest/text")
async def ingest_text(request: IngestTextRequest):
    await require_embedding()
    pipeline = await get_pipeline()
    
    metadata = DocumentMetadata(
        source=request.source,
        source_type=request.source_type,
        title=request.title,
        department=request.department,
        tags=request.tags
    )
    
    try:
        doc = await pipeline.ingest_text(request.text, metadata)
        return {
            "status": "success",
            "doc_id": doc.doc_id,
            "message": f"Ingested document with {len(request.text)} characters"
        }
    except Exception as e:
        raise HTTPException(500, f"Ingestion failed: {str(e)}")


@router.post("/ingest/file")
async def ingest_file(
    file: UploadFile = File(...),
    source_type: str = Form(...),
    title: str = Form(None),
    department: str = Form(None),
    tags: str = Form(""),
    process_images: bool = Form(True)
):
    await require_embedding()
    pipeline = await get_pipeline()
    
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        metadata = DocumentMetadata(
            source=file.filename,
            source_type=source_type,
            title=title or file.filename,
            department=department,
            tags=[t.strip() for t in tags.split(",") if t.strip()]
        )
        
        doc = await pipeline.ingest_file(tmp_path, metadata, process_images=process_images)
        
        return {
            "status": "success",
            "doc_id": doc.doc_id,
            "doc_type": doc.doc_type.value,
            "content_length": len(doc.content),
            "images_processed": len(doc.images),
            "message": f"Ingested {file.filename}"
        }
    except Exception as e:
        raise HTTPException(500, f"Ingestion failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


@router.post("/ingest/batch")
async def ingest_batch(
    files: list[UploadFile] = File(...),
    source_type: str = Form(...),
    department: str = Form(None)
):
    await require_embedding()
    pipeline = await get_pipeline()
    
    results = []
    
    for file in files:
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
        
        try:
            metadata = DocumentMetadata(
                source=file.filename,
                source_type=source_type,
                title=file.filename,
                department=department
            )
            
            doc = await pipeline.ingest_file(tmp_path, metadata)
            results.append({
                "filename": file.filename,
                "status": "success",
                "doc_id": doc.doc_id
            })
        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": str(e)
            })
        finally:
            os.unlink(tmp_path)
    
    success_count = sum(1 for r in results if r["status"] == "success")
    return {
        "total": len(files),
        "success": success_count,
        "failed": len(files) - success_count,
        "results": results
    }


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    await require_embedding()
    pipeline = await get_pipeline()
    
    filter_metadata = None
    if request.filter_source_type or request.filter_department:
        filter_metadata = {}
        if request.filter_source_type:
            filter_metadata["source_type"] = request.filter_source_type
        if request.filter_department:
            filter_metadata["department"] = request.filter_department
    
    try:
        context = await pipeline.search(
            query=request.query,
            top_k=request.top_k,
            search_type=request.search_type,
            filter_metadata=filter_metadata,
            rerank=request.rerank
        )
        
        results = []
        for r in context.results:
            results.append({
                "chunk_id": r.chunk.chunk_id,
                "doc_id": r.chunk.doc_id,
                "content": r.chunk.content,
                "score": r.score,
                "search_type": r.search_type,
                "metadata": r.chunk.metadata,
                "is_image": r.chunk.image_id is not None
            })
        
        return SearchResponse(
            query=request.query,
            results=results,
            total_results=len(results),
            search_type=request.search_type,
            reranked=context.reranked
        )
    except Exception as e:
        raise HTTPException(500, f"Search failed: {str(e)}")


@router.get("/search")
async def search_get(
    query: str,
    top_k: int = 5,
    search_type: str = "hybrid",
    source_type: str = None,
    department: str = None
):
    request = SearchRequest(
        query=query,
        top_k=top_k,
        search_type=search_type,
        filter_source_type=source_type,
        filter_department=department
    )
    return await search(request)


@router.get("/documents")
async def list_documents():
    pipeline = await get_pipeline()
    
    docs = []
    for doc in pipeline.list_documents():
        docs.append({
            "doc_id": doc.doc_id,
            "source": doc.metadata.source,
            "source_type": doc.metadata.source_type,
            "title": doc.metadata.title,
            "doc_type": doc.doc_type.value,
            "created_at": doc.created_at,
            "content_length": len(doc.content),
            "images": len(doc.images)
        })
    
    return {"documents": docs, "total": len(docs)}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    pipeline = await get_pipeline()
    
    doc = pipeline.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    
    return {
        "doc_id": doc.doc_id,
        "source": doc.metadata.source,
        "source_type": doc.metadata.source_type,
        "title": doc.metadata.title,
        "doc_type": doc.doc_type.value,
        "created_at": doc.created_at,
        "content": doc.content[:5000] + "..." if len(doc.content) > 5000 else doc.content,
        "content_length": len(doc.content),
        "images": [
            {
                "image_id": img["image_id"],
                "description": img.get("description"),
                "has_base64": "base64" in img
            }
            for img in doc.images
        ],
        "metadata": {
            "department": doc.metadata.department,
            "tags": doc.metadata.tags,
            "language": doc.metadata.language
        }
    }


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    pipeline = await get_pipeline()
    
    if pipeline.delete_document(doc_id):
        return {"status": "deleted", "doc_id": doc_id}
    else:
        raise HTTPException(404, "Document not found")


@router.get("/stats")
async def get_stats():
    pipeline = await get_pipeline()
    return pipeline.get_stats()


@router.post("/seed")
async def seed_demo_data():
    await require_embedding()
    pipeline = await get_pipeline()
    
    demo_docs = [
        {
            "text": """胸痛評估流程 (Chest Pain Assessment Protocol)

1. 初步評估 (Initial Assessment)
- 立即評估ABC（呼吸道、呼吸、循環）
- 測量生命徵象：血壓、心率、呼吸、血氧
- 12導程心電圖應在10分鐘內完成

2. PQRST問診法
- P (Provocation/Palliation): 什麼引發或緩解疼痛？
- Q (Quality): 疼痛性質？壓迫感、刺痛、悶痛？
- R (Radiation): 是否放射到其他部位？手臂、下巴、背部？
- S (Severity): 疼痛程度1-10分？
- T (Timing): 何時開始？持續多久？

3. 危險因子評估
- 年齡 > 65歲
- 糖尿病史
- 高血壓
- 高血脂
- 吸菸史
- 心血管疾病家族史

4. HEART Score 評估
- History: 高度懷疑=2, 中度=1, 低度=0
- ECG: ST上升=2, 非特異性改變=1, 正常=0
- Age: ≥65=2, 45-64=1, <45=0
- Risk factors: ≥3=2, 1-2=1, 0=0
- Troponin: ≥3x正常=2, 1-3x=1, 正常=0

HEART Score ≥7: 高風險，考慮入院
HEART Score 4-6: 中風險，進一步檢查
HEART Score 0-3: 低風險，可考慮門診追蹤

5. 處置建議
- 高風險：立即會診心臟科，考慮心導管
- 中風險：留觀，連續心電圖和心肌酶
- 低風險：門診追蹤，衛教警示症狀""",
            "source": "chest_pain_protocol_v3.pdf",
            "source_type": "sop",
            "title": "胸痛評估流程",
            "department": "急診醫學科"
        },
        {
            "text": """糖尿病照護指引 (Diabetes Care Guidelines)

一、血糖控制目標
- HbA1c < 7.0% (一般成人)
- HbA1c < 8.0% (老年人或有低血糖風險者)
- 空腹血糖：80-130 mg/dL
- 餐後血糖：< 180 mg/dL

二、用藥原則

第一線藥物：Metformin
- 起始劑量：500mg 每日一次，隨餐服用
- 最大劑量：2000-2550mg/天
- eGFR 30-45：最大劑量減半
- eGFR < 30：禁用
- 副作用：腸胃不適、乳酸中毒（罕見）

第二線藥物選擇：
1. SGLT2抑制劑（如Empagliflozin）
   - 心血管疾病或心衰竭優先選擇
   - 注意泌尿道感染風險

2. GLP-1受體促效劑（如Semaglutide）
   - 體重過重者優先選擇
   - 可降低心血管風險

3. DPP-4抑制劑（如Sitagliptin）
   - 老年人或腎功能不全可考慮
   - 副作用較少

三、監測頻率
- 新診斷或調整藥物：每日自我監測
- 穩定控制：每週2-3次
- HbA1c：每3個月檢測一次

四、併發症篩檢
- 眼底檢查：每年一次
- 尿液微量白蛋白：每年一次
- 足部檢查：每次就診
- 神經病變評估：每年一次

五、生活型態建議
- 飲食：低GI飲食，減少精緻澱粉
- 運動：每週150分鐘中等強度運動
- 體重：維持BMI 18.5-24""",
            "source": "diabetes_guidelines_2024.pdf",
            "source_type": "sop",
            "title": "糖尿病照護指引",
            "department": "內分泌科"
        },
        {
            "text": """心衰竭病患衛教 (Heart Failure Patient Education)

什麼是心衰竭？
心衰竭是指心臟無法有效地將血液輸送到全身。這不代表心臟停止跳動，而是心臟的泵血功能減弱。

常見症狀：
- 呼吸困難，尤其是躺下時
- 腳踝、腿部或腹部腫脹
- 容易疲倦
- 體重突然增加（水分滯留）
- 咳嗽，尤其是夜間

每日監測重點：
1. 每天固定時間量體重
   - 一天增加超過1公斤要注意
   - 一週增加超過2公斤要就醫

2. 觀察呼吸狀況
   - 平躺是否會喘
   - 需要幾個枕頭才能睡

3. 注意腫脹程度
   - 腳踝、小腿是否比平常腫

何時需要立即就醫？
- 突然嚴重呼吸困難
- 胸痛或胸悶
- 意識改變或昏厥
- 咳出粉紅色泡沫痰

藥物注意事項：
- 利尿劑：早上吃，避免夜間頻尿
- 血管張力素轉化酶抑制劑：可能乾咳
- 乙型阻斷劑：心跳會變慢，這是正常的
- 絕對不可自行停藥

飲食建議：
- 限制鈉攝取：每日少於2公克
- 避免醃製食品、罐頭、速食
- 水分攝取：依醫師指示，通常1.5-2公升/天
- 避免酒精""",
            "source": "heart_failure_education.md",
            "source_type": "education",
            "title": "心衰竭病患衛教",
            "department": "心臟內科"
        },
        {
            "text": """抗凝血藥物監測流程 (Anticoagulation Monitoring Protocol)

一、Warfarin監測

目標INR範圍：
- 一般靜脈栓塞：2.0-3.0
- 機械性心臟瓣膜：2.5-3.5
- 心房顫動：2.0-3.0

監測頻率：
- 起始治療：每2-3天
- 劑量穩定後：每週
- 長期穩定：每4週

INR異常處理：
INR > 3.0 but < 5.0：
- 減少Warfarin劑量10-20%
- 3天後複查INR

INR 5.0-9.0 無出血：
- 暫停1-2劑
- 考慮口服Vitamin K 1-2.5mg
- 次日複查INR

INR > 9.0 無出血：
- 暫停Warfarin
- 口服Vitamin K 2.5-5mg
- 密切監測，6-12小時複查

任何出血：
- 立即會診
- 考慮Vitamin K靜脈注射
- 嚴重出血考慮FFP或PCC

二、藥物交互作用

增強抗凝效果（INR上升）：
- 抗生素：Metronidazole, Fluconazole
- 心臟藥物：Amiodarone
- 止痛藥：NSAIDs
- 其他：酒精

減弱抗凝效果（INR下降）：
- 抗癲癇藥：Phenytoin, Carbamazepine
- 維生素K含量高的食物
- 中藥：人參、當歸

三、DOAC監測

不需常規監測，但注意：
- 腎功能（每3-6個月）
- 肝功能
- 血紅素

腎功能劑量調整（以Rivaroxaban為例）：
- CrCl > 50: 標準劑量
- CrCl 30-50: 減量
- CrCl < 30: 禁用或謹慎使用""",
            "source": "anticoagulation_protocol.pdf",
            "source_type": "sop",
            "title": "抗凝血藥物監測流程",
            "department": "心臟內科"
        },
        {
            "text": """危急值通報標準作業流程

一、危急值定義
危急值（Critical Values）是指檢驗結果嚴重異常，可能危及病人生命，需要立即通報並處理的數值。

二、常見危急值項目

血液學：
- 血紅素：< 7 g/dL 或 > 20 g/dL
- 血小板：< 20,000 或 > 1,000,000 /μL
- 白血球：< 2,000 或 > 30,000 /μL
- INR：> 5.0

生化學：
- 血糖：< 50 或 > 500 mg/dL
- 鈉離子：< 120 或 > 160 mEq/L
- 鉀離子：< 2.5 或 > 6.5 mEq/L
- 鈣離子：< 6.0 或 > 13.0 mg/dL
- 肌酸酐：新發 > 4.0 mg/dL

心臟標記：
- Troponin I：> 0.5 ng/mL（依各院標準）

血液氣體：
- pH：< 7.20 或 > 7.60
- pCO2：< 20 或 > 70 mmHg
- pO2：< 40 mmHg

三、通報流程

1. 檢驗科發現危急值
   ↓
2. 立即電話通報病房/診間（30分鐘內）
   ↓
3. 接聽者複誦確認數值
   ↓
4. 記錄通報時間、通報者、接聽者
   ↓
5. 接聽者立即通知主治醫師
   ↓
6. 醫師評估並處置

四、注意事項
- 危急值須於發現後30分鐘內完成通報
- 無法聯繫病房時，通報護理站或值班醫師
- 門診病人須聯繫病患本人或緊急聯絡人
- 所有通報須完整記錄於系統""",
            "source": "critical_value_protocol.pdf",
            "source_type": "protocol",
            "title": "危急值通報標準作業流程",
            "department": "檢驗醫學科"
        }
    ]
    
    results = []
    for doc_data in demo_docs:
        try:
            metadata = DocumentMetadata(
                source=doc_data["source"],
                source_type=doc_data["source_type"],
                title=doc_data["title"],
                department=doc_data.get("department")
            )
            doc = await pipeline.ingest_text(doc_data["text"], metadata)
            results.append({"title": doc_data["title"], "status": "success", "doc_id": doc.doc_id})
        except Exception as e:
            results.append({"title": doc_data["title"], "status": "error", "error": str(e)})
    
    return {
        "message": "Demo data seeded",
        "total": len(demo_docs),
        "success": sum(1 for r in results if r["status"] == "success"),
        "results": results
    }