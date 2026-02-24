"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { RAG_SEARCH_TYPE_OPTIONS, RAG_SOURCE_TYPE_OPTIONS } from "@/lib/model-options";
import type { RagDocumentDetailResponse, RagDocumentListItem, RagSearchResult, RagSearchType, RagSourceType } from "@/lib/types";
import { Button, Card, Input, Select, TextArea } from "@/components/ui/primitives";
import { OptLabel, ReqLabel } from "@/components/dashboard/common/FormLabels";
import { splitComma } from "@/components/dashboard/common/textParsers";
import { StructuredData } from "@/components/dashboard/common/StructuredData";
import { useDashboardContext } from "@/components/dashboard/shell/DashboardContext";

export function RagTab() {
  const { token, show } = useDashboardContext();
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [searchForm, setSearchForm] = useState<{
    query: string;
    top_k: number;
    search_type: RagSearchType;
    filter_source_type: "" | RagSourceType;
    filter_department: string;
    rerank: boolean;
  }>({
    query: "",
    top_k: 5,
    search_type: "hybrid",
    filter_source_type: "",
    filter_department: "",
    rerank: false,
  });
  const [searchResults, setSearchResults] = useState<RagSearchResult[]>([]);
  const [ingestTextForm, setIngestTextForm] = useState({
    text: "",
    source: "",
    source_type: "sop" as RagSourceType,
    title: "",
    department: "",
    tags: "",
  });
  const [ingestFile, setIngestFile] = useState<File | null>(null);
  const [ingestFileForm, setIngestFileForm] = useState({
    source_type: "sop" as RagSourceType,
    title: "",
    department: "",
    tags: "",
    process_images: true,
  });
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [batchForm, setBatchForm] = useState({
    source_type: "sop" as RagSourceType,
    department: "",
  });
  const [documents, setDocuments] = useState<RagDocumentListItem[]>([]);
  const [selectedDocId, setSelectedDocId] = useState("");
  const [selectedDocument, setSelectedDocument] = useState<RagDocumentDetailResponse | null>(null);
  const [confirmDeleteDocId, setConfirmDeleteDocId] = useState("");
  const [isDeletingDoc, setIsDeletingDoc] = useState(false);

  const loadDocuments = useCallback(async () => {
    const res = await api.ragListDocuments(token);
    setDocuments(res.documents);
  }, [token]);

  const refreshHealth = useCallback(() => {
    api.ragHealth(token)
      .then((res) => setHealth(res as unknown as Record<string, unknown>))
      .catch((e) => show("error", String(e)));
  }, [show, token]);

  const refreshStats = useCallback(() => {
    api.ragStats(token)
      .then(setStats)
      .catch((e) => show("error", String(e)));
  }, [show, token]);

  useEffect(() => {
    if (api.mode !== "real") return;
    refreshHealth();
    refreshStats();
    void loadDocuments();
  }, [loadDocuments, refreshHealth, refreshStats]);

  if (api.mode !== "real") {
    return (
      <div className="col">
        <Card title="Knowledge Search">
          <div className="alert">Knowledge features are available only in live mode.</div>
        </Card>
      </div>
    );
  }

  return (
    <div className="col">
      <Card title="Knowledge Status">
        <div className="row">
          <Button variant="secondary" onClick={refreshHealth}>Refresh Status</Button>
          <Button variant="secondary" onClick={refreshStats}>Refresh Metrics</Button>
        </div>
        {health ? <StructuredData title="System Status" data={health} /> : null}
        {stats ? <StructuredData title="Collection Metrics" data={stats} /> : null}
      </Card>

      <Card title="Knowledge Search">
        <div className="form-grid">
          <ReqLabel text="query" /><Input required value={searchForm.query} onChange={(e) => setSearchForm((v) => ({ ...v, query: e.target.value }))} />
          <ReqLabel text="top_k" /><Input required type="number" min={1} value={searchForm.top_k} onChange={(e) => setSearchForm((v) => ({ ...v, top_k: Number(e.target.value) || 1 }))} />
          <ReqLabel text="search_type" /><Select value={searchForm.search_type} onChange={(e) => setSearchForm((v) => ({ ...v, search_type: e.target.value as RagSearchType }))}>{RAG_SEARCH_TYPE_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
          <OptLabel text="filter_source_type" /><Select value={searchForm.filter_source_type} onChange={(e) => setSearchForm((v) => ({ ...v, filter_source_type: e.target.value as "" | RagSourceType }))}><option value="">none</option>{RAG_SOURCE_TYPE_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
          <OptLabel text="filter_department" /><Input value={searchForm.filter_department} onChange={(e) => setSearchForm((v) => ({ ...v, filter_department: e.target.value }))} />
          <label className="small"><input type="checkbox" checked={searchForm.rerank} onChange={(e) => setSearchForm((v) => ({ ...v, rerank: e.target.checked }))} /> rerank</label>
          <Button onClick={() => api.ragSearch(token, {
            query: searchForm.query,
            top_k: searchForm.top_k,
            search_type: searchForm.search_type,
            filter_source_type: searchForm.filter_source_type || null,
            filter_department: searchForm.filter_department || null,
            rerank: searchForm.rerank,
          }).then((res) => setSearchResults(res.results)).catch((e) => show("error", String(e)))}>Search</Button>
        </div>
        <div className="table-wrap" style={{ marginTop: 8 }}>
          <table>
            <thead>
              <tr><th>Chunk ID</th><th>Document ID</th><th>Score</th><th>Search Type</th><th>Image</th><th>Preview</th></tr>
            </thead>
            <tbody>
              {searchResults.length ? searchResults.map((r) => <tr key={`${r.chunk_id}-${r.doc_id}`}><td>{r.chunk_id}</td><td>{r.doc_id}</td><td>{r.score.toFixed(4)}</td><td>{r.search_type}</td><td>{r.is_image ? "true" : "false"}</td><td>{r.content.slice(0, 140)}</td></tr>) : <tr><td colSpan={6}>No results</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid-2">
        <Card title="RAG Ingest Text">
          <div className="col">
            <ReqLabel text="text" /><TextArea value={ingestTextForm.text} onChange={(e) => setIngestTextForm((v) => ({ ...v, text: e.target.value }))} />
            <ReqLabel text="source" /><Input required value={ingestTextForm.source} onChange={(e) => setIngestTextForm((v) => ({ ...v, source: e.target.value }))} />
            <ReqLabel text="source_type" /><Select value={ingestTextForm.source_type} onChange={(e) => setIngestTextForm((v) => ({ ...v, source_type: e.target.value as RagSourceType }))}>{RAG_SOURCE_TYPE_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
            <OptLabel text="title" /><Input value={ingestTextForm.title} onChange={(e) => setIngestTextForm((v) => ({ ...v, title: e.target.value }))} />
            <OptLabel text="department" /><Input value={ingestTextForm.department} onChange={(e) => setIngestTextForm((v) => ({ ...v, department: e.target.value }))} />
            <OptLabel text="tags (comma separated)" /><Input value={ingestTextForm.tags} onChange={(e) => setIngestTextForm((v) => ({ ...v, tags: e.target.value }))} />
            <Button onClick={() => api.ragIngestText(token, {
              text: ingestTextForm.text,
              source: ingestTextForm.source,
              source_type: ingestTextForm.source_type,
              title: ingestTextForm.title || null,
              department: ingestTextForm.department || null,
              tags: splitComma(ingestTextForm.tags),
            }).then((res) => {
              show("success", res.message || "Ingested");
              void loadDocuments();
              void refreshStats();
            }).catch((e) => show("error", String(e)))}>Ingest Text</Button>
          </div>
        </Card>

        <Card title="RAG Ingest File">
          <div className="col">
            <ReqLabel text="file" /><Input required type="file" onChange={(e) => setIngestFile(e.target.files?.[0] ?? null)} />
            <ReqLabel text="source_type" /><Select value={ingestFileForm.source_type} onChange={(e) => setIngestFileForm((v) => ({ ...v, source_type: e.target.value as RagSourceType }))}>{RAG_SOURCE_TYPE_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
            <OptLabel text="title" /><Input value={ingestFileForm.title} onChange={(e) => setIngestFileForm((v) => ({ ...v, title: e.target.value }))} />
            <OptLabel text="department" /><Input value={ingestFileForm.department} onChange={(e) => setIngestFileForm((v) => ({ ...v, department: e.target.value }))} />
            <OptLabel text="tags (comma separated)" /><Input value={ingestFileForm.tags} onChange={(e) => setIngestFileForm((v) => ({ ...v, tags: e.target.value }))} />
            <label className="small"><input type="checkbox" checked={ingestFileForm.process_images} onChange={(e) => setIngestFileForm((v) => ({ ...v, process_images: e.target.checked }))} /> process_images</label>
            <Button onClick={() => {
              if (!ingestFile) {
                show("error", "file is required");
                return;
              }
              api.ragIngestFile(token, ingestFile, {
                source_type: ingestFileForm.source_type,
                title: ingestFileForm.title || undefined,
                department: ingestFileForm.department || undefined,
                tags: ingestFileForm.tags || undefined,
                process_images: ingestFileForm.process_images,
              }).then((res) => {
                show("success", res.message || "Ingested");
                void loadDocuments();
                void refreshStats();
              }).catch((e) => show("error", String(e)));
            }}>Ingest File</Button>
          </div>
        </Card>
      </div>

      <Card title="RAG Ingest Batch">
        <div className="col">
          <ReqLabel text="files" /><Input required type="file" multiple onChange={(e) => setBatchFiles(Array.from(e.target.files ?? []))} />
          <ReqLabel text="source_type" /><Select value={batchForm.source_type} onChange={(e) => setBatchForm((v) => ({ ...v, source_type: e.target.value as RagSourceType }))}>{RAG_SOURCE_TYPE_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}</Select>
          <OptLabel text="department" /><Input value={batchForm.department} onChange={(e) => setBatchForm((v) => ({ ...v, department: e.target.value }))} />
          <Button onClick={() => {
            if (!batchFiles.length) {
              show("error", "at least one file is required");
              return;
            }
            api.ragIngestBatch(token, batchFiles, {
              source_type: batchForm.source_type,
              department: batchForm.department || undefined,
            }).then((res) => {
              show("success", `Batch ingested: ${res.success}/${res.total}`);
              void loadDocuments();
              void refreshStats();
            }).catch((e) => show("error", String(e)));
          }}>Ingest Batch</Button>
        </div>
      </Card>

      <Card title="Knowledge Documents">
        <div className="row">
          <Button variant="secondary" onClick={() => void loadDocuments()}>Refresh</Button>
          <Button variant="secondary" onClick={() => api.ragSeed(token).then(() => {
            show("success", "Seeded demo documents");
            void loadDocuments();
            void refreshStats();
          }).catch((e) => show("error", String(e)))}>Load Sample Documents</Button>
        </div>
        <div className="table-wrap" style={{ marginTop: 8 }}>
          <table>
            <thead><tr><th>Document ID</th><th>Source</th><th>Source Type</th><th>Document Type</th><th>Created</th><th>Images</th></tr></thead>
            <tbody>
              {documents.length ? documents.map((d) => <tr key={d.doc_id}><td>{d.doc_id}</td><td>{d.source}</td><td>{d.source_type}</td><td>{d.doc_type}</td><td>{d.created_at}</td><td>{d.images}</td></tr>) : <tr><td colSpan={6}>No documents</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <OptLabel text="Document ID" htmlFor="rag-doc-id" />
          <Input id="rag-doc-id" name="doc_id" placeholder="Enter document ID..." value={selectedDocId} onChange={(e) => setSelectedDocId(e.target.value)} />
          <Button variant="secondary" onClick={() => api.ragGetDocument(token, selectedDocId).then(setSelectedDocument).catch((e) => show("error", String(e)))}>View Details</Button>
          {confirmDeleteDocId === selectedDocId && selectedDocId ? (
            <>
              <Button
                variant="danger"
                disabled={isDeletingDoc}
                onClick={() => {
                  setIsDeletingDoc(true);
                  api.ragDeleteDocument(token, selectedDocId).then(() => {
                    show("success", `Deleted ${selectedDocId}`);
                    setSelectedDocument(null);
                    setConfirmDeleteDocId("");
                    void loadDocuments();
                    void refreshStats();
                  }).catch((e) => show("error", String(e))).finally(() => setIsDeletingDoc(false));
                }}
              >
                {isDeletingDoc ? "Deleting..." : "Confirm Delete"}
              </Button>
              <Button variant="secondary" onClick={() => setConfirmDeleteDocId("")}>Cancel</Button>
            </>
          ) : (
            <Button variant="danger" disabled={!selectedDocId} onClick={() => setConfirmDeleteDocId(selectedDocId)}>Delete</Button>
          )}
        </div>
        {selectedDocument ? <StructuredData title="Document Details" data={selectedDocument} /> : null}
      </Card>
    </div>
  );
}

