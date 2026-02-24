import os
import re
import json
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Literal
from enum import Enum
import base64

import httpx


class DocumentType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"
    HTML = "html"
    IMAGE = "image"
    UNKNOWN = "unknown"


@dataclass
class DocumentMetadata:
    source: str
    source_type: str  # sop, education, protocol, clinical_note, lab_report, imaging
    title: str | None = None
    author: str | None = None
    created_date: str | None = None
    department: str | None = None
    version: str | None = None
    language: str = "zh-TW"
    tags: list[str] = field(default_factory=list)
    custom: dict = field(default_factory=dict)


@dataclass
class Document:
    doc_id: str
    content: str
    metadata: DocumentMetadata
    doc_type: DocumentType
    file_path: str | None = None
    file_hash: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # For multimodal
    images: list[dict] = field(default_factory=list)  # [{image_id, base64, description}]


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    content: str
    metadata: dict
    embedding: list[float] | None = None
    chunk_index: int = 0
    start_char: int = 0
    end_char: int = 0
    image_id: str | None = None
    image_description: str | None = None


@dataclass
class SearchResult:
    chunk: Chunk
    score: float
    search_type: str  # semantic, keyword, hybrid


@dataclass
class RAGContext:
    query: str
    results: list[SearchResult]
    reranked: bool = False
    total_tokens: int = 0


class TextExtractor:
    @staticmethod
    def detect_type(file_path: str) -> DocumentType:
        ext = Path(file_path).suffix.lower()
        mapping = {
            ".pdf": DocumentType.PDF,
            ".docx": DocumentType.DOCX,
            ".doc": DocumentType.DOCX,
            ".txt": DocumentType.TXT,
            ".md": DocumentType.MD,
            ".html": DocumentType.HTML,
            ".htm": DocumentType.HTML,
            ".png": DocumentType.IMAGE,
            ".jpg": DocumentType.IMAGE,
            ".jpeg": DocumentType.IMAGE,
            ".webp": DocumentType.IMAGE,
        }
        return mapping.get(ext, DocumentType.UNKNOWN)
    
    @staticmethod
    async def extract(file_path: str) -> tuple[str, list[dict]]:
        doc_type = TextExtractor.detect_type(file_path)
        
        if doc_type == DocumentType.PDF:
            return await TextExtractor._extract_pdf(file_path)
        elif doc_type == DocumentType.DOCX:
            return await TextExtractor._extract_docx(file_path)
        elif doc_type in [DocumentType.TXT, DocumentType.MD]:
            return await TextExtractor._extract_text(file_path)
        elif doc_type == DocumentType.HTML:
            return await TextExtractor._extract_html(file_path)
        elif doc_type == DocumentType.IMAGE:
            return await TextExtractor._extract_image(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_path}")
    
    @staticmethod
    async def _extract_pdf(file_path: str) -> tuple[str, list[dict]]:
        try:
            import fitz
        except ImportError:
            raise ImportError("Install pymupdf: pip install pymupdf")
        
        doc = fitz.open(file_path)
        text_parts = []
        images = []
        
        for page_num, page in enumerate(doc):
            text_parts.append(f"\n--- Page {page_num + 1} ---\n")
            text_parts.append(page.get_text())
            
            for img_index, img in enumerate(page.get_images(full=True)):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    image_id = f"img_{page_num}_{img_index}"
                    images.append({
                        "image_id": image_id,
                        "base64": base64.b64encode(image_bytes).decode(),
                        "ext": image_ext,
                        "page": page_num + 1,
                        "description": None  # To be filled by vision model
                    })
                except Exception:
                    continue
        
        doc.close()
        return "".join(text_parts), images
    
    @staticmethod
    async def _extract_docx(file_path: str) -> tuple[str, list[dict]]:
        try:
            from docx import Document as DocxDocument
        except ImportError:
            raise ImportError("Install python-docx: pip install python-docx")
        
        doc = DocxDocument(file_path)
        text_parts = []
        
        for para in doc.paragraphs:
            text_parts.append(para.text)
        
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text for cell in row.cells)
                text_parts.append(row_text)
        
        return "\n".join(text_parts), []
    
    @staticmethod
    async def _extract_text(file_path: str) -> tuple[str, list[dict]]:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read(), []
    
    @staticmethod
    async def _extract_html(file_path: str) -> tuple[str, list[dict]]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            with open(file_path, "r", encoding="utf-8") as f:
                html = f.read()
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text)
            return text.strip(), []
        
        with open(file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        
        for script in soup(["script", "style"]):
            script.decompose()
        
        return soup.get_text(separator="\n"), []
    
    @staticmethod
    async def _extract_image(file_path: str) -> tuple[str, list[dict]]:
        with open(file_path, "rb") as f:
            image_bytes = f.read()
        
        ext = Path(file_path).suffix.lower().lstrip(".")
        image_id = Path(file_path).stem
        
        images = [{
            "image_id": image_id,
            "base64": base64.b64encode(image_bytes).decode(),
            "ext": ext,
            "description": None
        }]
        
        return "", images


class TextChunker:
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: list[str] | None = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", "。", ".", " "]
    
    def chunk(self, text: str, doc_id: str) -> list[Chunk]:
        if not text.strip():
            return []
        
        chunks = self._recursive_split(text)
        
        result = []
        char_pos = 0
        
        for i, chunk_text in enumerate(chunks):
            start = text.find(chunk_text, char_pos)
            if start == -1:
                start = char_pos
            end = start + len(chunk_text)
            char_pos = max(char_pos, start)
            
            chunk = Chunk(
                chunk_id=f"{doc_id}_chunk_{i}",
                doc_id=doc_id,
                content=chunk_text,
                metadata={},
                chunk_index=i,
                start_char=start,
                end_char=end
            )
            result.append(chunk)
        
        return result
    
    def _recursive_split(self, text: str) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text.strip()] if text.strip() else []
        
        for sep in self.separators:
            if sep and sep in text:
                return self._split_with_separator(text, sep)
        
        return self._split_by_chars(text)
    
    def _split_with_separator(self, text: str, separator: str) -> list[str]:
        parts = text.split(separator)
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            part_with_sep = part + separator if separator else part
            
            if current_length + len(part_with_sep) > self.chunk_size and current_chunk:
                chunk_text = separator.join(current_chunk)
                chunks.append(chunk_text)
                
                overlap_start = max(0, len(current_chunk) - 1)
                current_chunk = current_chunk[overlap_start:] + [part]
                current_length = sum(len(p) + len(separator) for p in current_chunk)
            else:
                current_chunk.append(part)
                current_length += len(part_with_sep)
        
        if current_chunk:
            chunks.append(separator.join(current_chunk))
        
        return chunks
    
    def _split_by_chars(self, text: str) -> list[str]:
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(text[start:end])
            new_start = end - self.chunk_overlap
            if new_start <= start:
                new_start = start + 1
            start = new_start
        
        return chunks


class EmbeddingClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8003",
        model_name: str = "embedgemma",
        api_key: str = "not-needed"
    ):
        self.base_url = base_url.rstrip("/").rstrip("/v1").rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=60.0)
        self._healthy = False
    
    async def health_check(self) -> bool:
        try:
            r = await self.client.get(f"{self.base_url}/v1/models", timeout=5.0)
            self._healthy = r.status_code == 200
            return self._healthy
        except Exception:
            self._healthy = False
            return False
    
    @property
    def is_healthy(self) -> bool:
        return self._healthy
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._healthy:
            raise ConnectionError(f"Embedding server not available at {self.base_url}")
        
        response = await self.client.post(
            f"{self.base_url}/v1/embeddings",
            json={
                "model": self.model_name,
                "input": texts
            },
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        response.raise_for_status()
        
        data = response.json()
        embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [e["embedding"] for e in embeddings]
    
    async def embed_single(self, text: str) -> list[float]:
        embeddings = await self.embed([text])
        return embeddings[0]
    
    async def close(self):
        await self.client.aclose()


class VisionClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8002/v1",
        model_name: str = "medgemma",
        api_key: str = "not-needed"
    ):
        self.base_url = base_url
        self.model_name = model_name
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=120.0)
    
    async def describe_image(
        self,
        image_base64: str,
        image_ext: str = "png",
        prompt: str = "Describe this medical image in detail, including any findings, abnormalities, or relevant clinical information."
    ) -> str:
        media_type = f"image/{image_ext}" if image_ext != "jpg" else "image/jpeg"
        
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{image_base64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                "max_tokens": 1024
            },
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        response.raise_for_status()
        
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    
    async def close(self):
        await self.client.aclose()


# implemented with chromadb
class VectorStore:
    def __init__(self, persist_dir: str = "./chroma_db", collection_name: str = "clinical_docs"):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._collection = None
        self._client = None
    
    def _get_collection(self):
        if self._collection is None:
            try:
                import chromadb
                from chromadb.config import Settings
            except ImportError:
                raise ImportError("Install chromadb: pip install chromadb")
            
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(anonymized_telemetry=False)
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        return self._collection
    
    def add(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        
        collection = self._get_collection()
        
        valid_chunks = [c for c in chunks if c.embedding is not None]
        if not valid_chunks:
            return
        
        collection.add(
            ids=[c.chunk_id for c in valid_chunks],
            embeddings=[c.embedding for c in valid_chunks],
            documents=[c.content for c in valid_chunks],
            metadatas=[{
                "doc_id": c.doc_id,
                "chunk_index": c.chunk_index,
                "start_char": c.start_char,
                "end_char": c.end_char,
                "image_id": c.image_id or "",
                **c.metadata
            } for c in valid_chunks]
        )
    
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict | None = None
    ) -> list[tuple[str, float, dict]]:
        collection = self._get_collection()
        
        where = filter_metadata if filter_metadata else None
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"]
        )
        
        output = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                # ChromaDB returns distance, convert to similarity score
                distance = results["distances"][0][i]
                score = 1 - distance  # cosine distance to similarity
                
                output.append((
                    chunk_id,
                    score,
                    {
                        "content": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i]
                    }
                ))
        
        return output
    
    def delete_by_doc_id(self, doc_id: str) -> None:
        collection = self._get_collection()
        collection.delete(where={"doc_id": doc_id})
    
    def get_stats(self) -> dict:
        collection = self._get_collection()
        return {
            "name": self.collection_name,
            "count": collection.count(),
            "persist_dir": self.persist_dir
        }


class KeywordSearch:
    def __init__(self):
        self._documents: dict[str, Chunk] = {}
        self._index = None
    
    def add(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            self._documents[chunk.chunk_id] = chunk
        self._rebuild_index()
    
    def _rebuild_index(self):
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            self._index = None
            return
        
        if not self._documents:
            self._index = None
            return
        
        tokenized = []
        self._doc_ids = []
        for chunk_id, chunk in self._documents.items():
            tokens = self._tokenize(chunk.content)
            tokenized.append(tokens)
            self._doc_ids.append(chunk_id)
        
        self._index = BM25Okapi(tokenized)
    
    def _tokenize(self, text: str) -> list[str]:
        tokens = re.findall(r'\w+', text.lower())
        return tokens
    
    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        if self._index is None:
            return []
        
        query_tokens = self._tokenize(query)
        scores = self._index.get_scores(query_tokens)
        
        indexed_scores = [(self._doc_ids[i], scores[i]) for i in range(len(scores))]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        
        return indexed_scores[:top_k]
    
    def delete_by_doc_id(self, doc_id: str) -> None:
        to_delete = [cid for cid, c in self._documents.items() if c.doc_id == doc_id]
        for cid in to_delete:
            del self._documents[cid]
        self._rebuild_index()


class RAGPipeline:
    def __init__(
        self,
        embedding_client: EmbeddingClient,
        vision_client: VisionClient | None = None,
        vector_store: VectorStore | None = None,
        chunker: TextChunker | None = None,
        enable_keyword_search: bool = True
    ):
        self.embedding_client = embedding_client
        self.vision_client = vision_client
        self.vector_store = vector_store or VectorStore()
        self.chunker = chunker or TextChunker()
        self.keyword_search = KeywordSearch() if enable_keyword_search else None
        self._documents: dict[str, Document] = {}
    
    async def ingest_file(
        self,
        file_path: str,
        metadata: DocumentMetadata,
        process_images: bool = True
    ) -> Document:
        file_hash = self._compute_hash(file_path)
        for doc in self._documents.values():
            if doc.file_hash == file_hash:
                return doc
        
        text, images = await TextExtractor.extract(file_path)
        
        if process_images and images and self.vision_client:
            for img in images:
                try:
                    description = await self.vision_client.describe_image(
                        img["base64"],
                        img.get("ext", "png")
                    )
                    img["description"] = description
                except Exception as e:
                    img["description"] = f"[Image processing failed: {e}]"
        
        doc_id = hashlib.md5(f"{file_path}_{datetime.utcnow().isoformat()}".encode()).hexdigest()[:12]
        doc = Document(
            doc_id=doc_id,
            content=text,
            metadata=metadata,
            doc_type=TextExtractor.detect_type(file_path),
            file_path=file_path,
            file_hash=file_hash,
            images=images
        )
        
        await self._process_document(doc)
        
        self._documents[doc_id] = doc
        return doc
    
    async def ingest_text(
        self,
        text: str,
        metadata: DocumentMetadata,
        doc_id: str | None = None
    ) -> Document:
        doc_id = doc_id or hashlib.md5(text[:100].encode()).hexdigest()[:12]
        
        doc = Document(
            doc_id=doc_id,
            content=text,
            metadata=metadata,
            doc_type=DocumentType.TXT
        )
        
        await self._process_document(doc)
        
        self._documents[doc_id] = doc
        return doc
    
    async def _process_document(self, doc: Document) -> None:
        chunks = []
        
        if doc.content:
            text_chunks = self.chunker.chunk(doc.content, doc.doc_id)
            for chunk in text_chunks:
                chunk.metadata = {
                    "source": doc.metadata.source,
                    "source_type": doc.metadata.source_type,
                    "title": doc.metadata.title or "",
                    "department": doc.metadata.department or "",
                }
            chunks.extend(text_chunks)
        
        for img in doc.images:
            if img.get("description"):
                img_chunk = Chunk(
                    chunk_id=f"{doc.doc_id}_img_{img['image_id']}",
                    doc_id=doc.doc_id,
                    content=img["description"],
                    metadata={
                        "source": doc.metadata.source,
                        "source_type": doc.metadata.source_type,
                        "is_image": True,
                    },
                    image_id=img["image_id"],
                    image_description=img["description"]
                )
                chunks.append(img_chunk)
        
        if not chunks:
            return
        
        texts = [c.content for c in chunks]
        embeddings = await self.embedding_client.embed(texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        
        self.vector_store.add(chunks)
        
        if self.keyword_search:
            self.keyword_search.add(chunks)
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        search_type: Literal["semantic", "keyword", "hybrid"] = "hybrid",
        filter_metadata: dict | None = None,
        rerank: bool = False
    ) -> RAGContext:
        results = []
        
        if search_type in ["semantic", "hybrid"]:
            query_embedding = await self.embedding_client.embed_single(query)
            semantic_results = self.vector_store.search(
                query_embedding,
                top_k=top_k * 2 if search_type == "hybrid" else top_k,
                filter_metadata=filter_metadata
            )
            
            for chunk_id, score, data in semantic_results:
                chunk = Chunk(
                    chunk_id=chunk_id,
                    doc_id=data["metadata"].get("doc_id", ""),
                    content=data["content"],
                    metadata=data["metadata"]
                )
                results.append(SearchResult(chunk=chunk, score=score, search_type="semantic"))
        
        if search_type in ["keyword", "hybrid"] and self.keyword_search:
            keyword_results = self.keyword_search.search(
                query,
                top_k=top_k * 2 if search_type == "hybrid" else top_k
            )
            
            for chunk_id, score in keyword_results:
                if chunk_id in self.keyword_search._documents:
                    chunk = self.keyword_search._documents[chunk_id]
                    norm_score = min(score / 10, 1.0)
                    results.append(SearchResult(chunk=chunk, score=norm_score, search_type="keyword"))
        
        if search_type == "hybrid":
            results = self._merge_results(results)
        
        results.sort(key=lambda x: x.score, reverse=True)
        results = results[:top_k]
        
        if rerank and results:
            results = await self._rerank(query, results)
        
        return RAGContext(
            query=query,
            results=results,
            reranked=rerank,
            total_tokens=sum(len(r.chunk.content) // 4 for r in results) #guess?
        )
    
    def _merge_results(self, results: list[SearchResult]) -> list[SearchResult]:
        # Reciprocal Rank Fusion, something that aggregates ranks
        k = 60  # RRF constant
        
        scores: dict[str, float] = {}
        chunks: dict[str, SearchResult] = {}
        
        for i, result in enumerate(results):
            cid = result.chunk.chunk_id
            rank = i + 1
            rrf_score = 1 / (k + rank)
            
            if cid in scores:
                scores[cid] += rrf_score
            else:
                scores[cid] = rrf_score
                chunks[cid] = result
        
        merged = []
        for cid, score in scores.items():
            result = chunks[cid]
            merged.append(SearchResult(
                chunk=result.chunk,
                score=score,
                search_type="hybrid"
            ))
        
        return merged
    
    async def _rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        return results
    
    def delete_document(self, doc_id: str) -> bool:
        if doc_id not in self._documents:
            return False
        
        self.vector_store.delete_by_doc_id(doc_id)
        if self.keyword_search:
            self.keyword_search.delete_by_doc_id(doc_id)
        
        del self._documents[doc_id]
        return True
    
    def get_document(self, doc_id: str) -> Document | None:
        return self._documents.get(doc_id)
    
    def list_documents(self) -> list[Document]:
        return list(self._documents.values())
    
    def get_stats(self) -> dict:
        return {
            "documents": len(self._documents),
            "vector_store": self.vector_store.get_stats(),
            "embedding_healthy": self.embedding_client._healthy,
        }
    
    def _compute_hash(self, file_path: str) -> str:
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()


def create_rag_pipeline(
    embedding_url: str = "http://localhost:8003",
    embedding_model: str = "embedgemma",
    vision_url: str = "http://localhost:8002/v1",
    vision_model: str = "medgemma",
    persist_dir: str = "./chroma_db",
    collection_name: str = "clinical_docs"
) -> RAGPipeline:
    embedding_client = EmbeddingClient(
        base_url=embedding_url,
        model_name=embedding_model
    )
    
    vision_client = VisionClient(
        base_url=vision_url,
        model_name=vision_model
    )
    
    vector_store = VectorStore(
        persist_dir=persist_dir,
        collection_name=collection_name
    )
    
    return RAGPipeline(
        embedding_client=embedding_client,
        vision_client=vision_client,
        vector_store=vector_store
    )