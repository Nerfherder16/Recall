"""
Document memory routes.

Handles document upload, listing, detail, deletion,
and cascading operations (pin/unpin, domain update).
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.api.auth import require_auth
from src.core import Durability, User
from src.core.document_ingest import compute_file_hash, ingest_document
from src.storage import get_neo4j_store, get_postgres_store, get_qdrant_store
from src.storage.neo4j_documents import Neo4jDocumentStore

logger = structlog.get_logger()
router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_TYPES = {"pdf", "markdown", "text", "docx"}


# =============================================================
# RESPONSE MODELS
# =============================================================


class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_hash: str
    file_type: str
    domain: str
    durability: str | None
    pinned: bool
    memory_count: int
    created_at: str
    user_id: int | None = None
    username: str | None = None


class DocumentDetailResponse(DocumentResponse):
    child_memory_ids: list[str]


class IngestResponse(BaseModel):
    document: DocumentResponse
    memories_created: int
    child_ids: list[str]


class UpdateDocumentRequest(BaseModel):
    domain: str | None = None
    durability: str | None = Field(default=None, pattern="^(ephemeral|durable|permanent)$")


# =============================================================
# ENDPOINTS
# =============================================================


@router.post("/ingest", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    domain: str = Form(default="general"),
    durability: str | None = Form(default=None),
    file_type: str | None = Form(default=None),
    user: User = Depends(require_auth),
):
    """Upload and ingest a document, extracting memories from its content."""
    # Validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit")

    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # Determine file type
    ft = file_type
    if not ft:
        fname = (file.filename or "").lower()
        if fname.endswith(".pdf"):
            ft = "pdf"
        elif fname.endswith((".docx",)):
            ft = "docx"
        elif fname.endswith((".md", ".markdown")):
            ft = "markdown"
        elif fname.endswith((".txt", ".text", ".log", ".csv", ".json", ".yaml", ".yml")):
            ft = "text"
        else:
            ft = "text"

    if ft not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ft}'. Allowed: {', '.join(ALLOWED_TYPES)}",
        )

    # Validate durability
    dur = None
    if durability:
        try:
            dur = Durability(durability)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid durability value")

    # Check for duplicate hash (O(1) indexed lookup)
    file_hash = compute_file_hash(content)
    neo4j = await get_neo4j_store()
    doc_store = Neo4jDocumentStore(neo4j.driver)
    existing = await doc_store.get_document_by_hash(file_hash)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Document with same content already exists (id: {existing.get('id')})",
        )

    # Run ingestion
    doc, child_ids = await ingest_document(
        file_bytes=content,
        filename=file.filename or "unnamed",
        file_type=ft,
        domain=domain,
        durability=dur,
        user_id=user.id if user and user.id and user.id > 0 else None,
        username=user.username if user and user.username != "system" else None,
    )

    # Audit
    try:
        pg = await get_postgres_store()
        await pg.log_audit(
            "document_ingest",
            doc.id,
            actor=user.username if user else "user",
            details={
                "filename": doc.filename,
                "file_type": doc.file_type,
                "memories_created": len(child_ids),
            },
        )
    except Exception:
        pass

    return IngestResponse(
        document=_doc_to_response(doc.__dict__),
        memories_created=len(child_ids),
        child_ids=child_ids,
    )


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    domain: str | None = None,
    limit: int = 50,
    user: User = Depends(require_auth),
):
    """List all documents, optionally filtered by domain."""
    neo4j = await get_neo4j_store()
    doc_store = Neo4jDocumentStore(neo4j.driver)
    docs = await doc_store.list_documents(domain=domain, limit=limit)
    return [_doc_to_response(d) for d in docs]


@router.get("/{doc_id}", response_model=DocumentDetailResponse)
async def get_document(
    doc_id: str,
    user: User = Depends(require_auth),
):
    """Get document detail with child memory IDs."""
    neo4j = await get_neo4j_store()
    doc_store = Neo4jDocumentStore(neo4j.driver)
    doc = await doc_store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    child_ids = await doc_store.get_document_children(doc_id)
    resp = _doc_to_response(doc)
    return DocumentDetailResponse(**resp.model_dump(), child_memory_ids=child_ids)


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    user: User = Depends(require_auth),
):
    """Delete a document and all its child memories."""
    neo4j = await get_neo4j_store()
    doc_store = Neo4jDocumentStore(neo4j.driver)
    qdrant = await get_qdrant_store()

    doc = await doc_store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get children and delete from Qdrant
    child_ids = await doc_store.delete_document_cascade(doc_id)
    for cid in child_ids:
        try:
            await qdrant.delete(cid)
        except Exception:
            pass
        # Also delete from Neo4j memory nodes
        try:
            async with neo4j.driver.session() as session:
                await session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=cid)
        except Exception:
            pass

    # Audit
    try:
        pg = await get_postgres_store()
        await pg.log_audit(
            "document_delete",
            doc_id,
            actor=user.username if user else "user",
            details={"children_deleted": len(child_ids)},
        )
    except Exception:
        pass

    return {
        "deleted": True,
        "document_id": doc_id,
        "children_deleted": len(child_ids),
    }


@router.patch("/{doc_id}")
async def update_document(
    doc_id: str,
    req: UpdateDocumentRequest,
    user: User = Depends(require_auth),
):
    """Update document domain/durability, cascading to children."""
    neo4j = await get_neo4j_store()
    doc_store = Neo4jDocumentStore(neo4j.driver)
    qdrant = await get_qdrant_store()

    doc = await doc_store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    fields: dict[str, Any] = {}
    if req.domain is not None:
        fields["domain"] = req.domain
    if req.durability is not None:
        fields["durability"] = req.durability

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Update document node
    await doc_store.update_document(doc_id, **fields)

    # Cascade to children
    child_ids = await doc_store.get_document_children(doc_id)
    for cid in child_ids:
        if req.domain is not None:
            await qdrant.client.set_payload(
                collection_name=qdrant.collection,
                payload={"domain": req.domain},
                points=[cid],
            )
        if req.durability is not None:
            await qdrant.update_durability(cid, req.durability)

    return {
        "updated": True,
        "document_id": doc_id,
        "children_updated": len(child_ids),
    }


@router.post("/{doc_id}/pin")
async def pin_document(
    doc_id: str,
    user: User = Depends(require_auth),
):
    """Pin a document and all its child memories."""
    neo4j = await get_neo4j_store()
    doc_store = Neo4jDocumentStore(neo4j.driver)
    qdrant = await get_qdrant_store()

    doc = await doc_store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await doc_store.update_document(doc_id, pinned=True)

    child_ids = await doc_store.get_document_children(doc_id)
    for cid in child_ids:
        await qdrant.client.set_payload(
            collection_name=qdrant.collection,
            payload={"pinned": "true"},
            points=[cid],
        )

    return {"pinned": True, "document_id": doc_id, "children_pinned": len(child_ids)}


@router.delete("/{doc_id}/pin")
async def unpin_document(
    doc_id: str,
    user: User = Depends(require_auth),
):
    """Unpin a document and all its child memories."""
    neo4j = await get_neo4j_store()
    doc_store = Neo4jDocumentStore(neo4j.driver)
    qdrant = await get_qdrant_store()

    doc = await doc_store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await doc_store.update_document(doc_id, pinned=False)

    child_ids = await doc_store.get_document_children(doc_id)
    for cid in child_ids:
        await qdrant.client.set_payload(
            collection_name=qdrant.collection,
            payload={"pinned": "false"},
            points=[cid],
        )

    return {"pinned": False, "document_id": doc_id, "children_unpinned": len(child_ids)}


# =============================================================
# HELPERS
# =============================================================


def _doc_to_response(doc: dict[str, Any]) -> DocumentResponse:
    """Convert a document dict to response model."""
    created_at = doc.get("created_at", "")
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()

    durability = doc.get("durability")
    if hasattr(durability, "value"):
        durability = durability.value

    return DocumentResponse(
        id=doc.get("id", ""),
        filename=doc.get("filename", ""),
        file_hash=doc.get("file_hash", ""),
        file_type=doc.get("file_type", ""),
        domain=doc.get("domain", "general"),
        durability=durability,
        pinned=doc.get("pinned", False),
        memory_count=doc.get("memory_count", 0),
        created_at=str(created_at),
        user_id=doc.get("user_id"),
        username=doc.get("username"),
    )
