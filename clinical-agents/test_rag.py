import httpx
import asyncio

BASE_URL = "http://localhost:8080"


async def req(client, method, url, **kwargs):
    try:
        r = await client.request(method, url, **kwargs)
        print(f"  [{r.status_code}] {method} {url}")
        if r.status_code >= 400:
            print(f"  Error: {r.text}")
            return None
        return r.json() if r.text else None
    except Exception as e:
        print(f"  Error: {e}")
        return None


async def test_rag():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as c:
        
        print("1. RAG Health Check")
        data = await req(c, "GET", "/v1/rag/health")
        if data:
            print(f"  Status: {data.get('status')}")
            emb = data.get('embedding_service', {})
            print(f"  Embedding URL: {emb.get('url')}")
            print(f"  Embedding Model: {emb.get('model')}")
            print(f"  Embedding Connected: {emb.get('connected')}")
            print(f"  Documents: {data.get('documents')}")
            
            if not emb.get('connected'):
                print("\n Embedding service not connected!")
                return
        
        print("2. Seed Demo Data")
        data = await req(c, "POST", "/v1/rag/seed")
        if data:
            print(f"  Total: {data.get('total')}")
            print(f"  Success: {data.get('success')}")
            for r in data.get("results", []):
                status = "✓" if r["status"] == "success" else "✗"
                print(f"    {status} {r['title']}")
        else:
            print("  Seeding failed - is embedding service running?")
            print("  Start with: EMBEDDING_MODEL_PATH=./embedgemma ./scripts/start_vllm.sh")
            return
        
        print("3. List Documents")
        data = await req(c, "GET", "/v1/rag/documents")
        if data:
            print(f"  Total: {data.get('total')}")
            for doc in data.get("documents", [])[:5]:
                print(f"    - [{doc['source_type']}] {doc['title']}")
        
        print("4. Search: 胸痛評估")
        data = await req(c, "POST", "/v1/rag/search", json={
            "query": "胸痛評估流程",
            "top_k": 3,
            "search_type": "hybrid"
        })
        if data:
            print(f"  Results: {data.get('total_results')}")
            for r in data.get("results", []):
                print(f"    [{r['score']:.3f}] {r['content']}...")
        
        print("5. Search: 糖尿病用藥")
        data = await req(c, "POST", "/v1/rag/search", json={
            "query": "糖尿病第一線藥物選擇",
            "top_k": 3,
            "search_type": "semantic"
        })
        if data:
            print(f"  Results: {data.get('total_results')}")
            for r in data.get("results", []):
                print(f"    [{r['score']:.3f}] {r['content']}...")
        
        print("6. Search with Filter: source_type=sop")
        data = await req(c, "GET", "/v1/rag/search", params={
            "query": "監測",
            "top_k": 3,
            "source_type": "sop"
        })
        if data:
            print(f"  Results: {data.get('total_results')}")
            for r in data.get("results", []):
                print(f"    [{r['metadata'].get('source_type')}] {r['content']}...")
        
        print("7. Ingest Custom Text")
        data = await req(c, "POST", "/v1/rag/ingest/text", json={
            "text": """急性腎損傷處置流程
            
1. 定義：48小時內肌酸酐上升0.3 mg/dL或上升50%
2. 立即停用腎毒性藥物（NSAIDs, aminoglycosides）
3. 評估體液狀態，必要時給予輸液
4. 監測尿量，目標>0.5 mL/kg/hr
5. 追蹤腎功能，每日監測肌酸酐
6. 必要時會診腎臟科""",
            "source": "aki_protocol.txt",
            "source_type": "sop",
            "title": "急性腎損傷處置流程",
            "department": "腎臟內科"
        })
        if data:
            print(f"  Status: {data.get('status')}")
            print(f"  Doc ID: {data.get('doc_id')}")
        
        print("8. Search New Document")
        data = await req(c, "POST", "/v1/rag/search", json={
            "query": "急性腎損傷處置",
            "top_k": 2
        })
        if data:
            for r in data.get("results", []):
                print(f"    [{r['score']:.3f}] {r['content']}...")
        
        print("9. Get Stats")
        data = await req(c, "GET", "/v1/rag/stats")
        if data:
            print(f"  Documents: {data.get('documents')}")
            vs = data.get('vector_store', {})
            print(f"  Chunks: {vs.get('count')}")
        
        print("RAG Test Complete")


if __name__ == "__main__":
    print("\nRAG PIPELINE TEST\n")
    asyncio.run(test_rag())