from __future__ import annotations

import io

import pytest


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4 fake pdf content for testing"


def _png_bytes() -> bytes:
    # Minimal 1x1 PNG
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


@pytest.mark.anyio
async def test_upload_pdf_document(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.post(
        f"/v1/merchants/{merchant_id}/kyc/documents",
        data={"document_type": "PAN"},
        files={"file": ("pan.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["document_type"] == "PAN"
    assert data["status"] == "PENDING"
    assert data["mime_type"] == "application/pdf"


@pytest.mark.anyio
async def test_upload_png_document(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.post(
        f"/v1/merchants/{merchant_id}/kyc/documents",
        data={"document_type": "CANCELLED_CHEQUE"},
        files={"file": ("cheque.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 201
    assert resp.json()["document_type"] == "CANCELLED_CHEQUE"


@pytest.mark.anyio
async def test_upload_invalid_file_type(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.post(
        f"/v1/merchants/{merchant_id}/kyc/documents",
        data={"document_type": "PAN"},
        files={"file": ("malware.exe", b"MZ binary", "application/octet-stream")},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_upload_empty_file(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.post(
        f"/v1/merchants/{merchant_id}/kyc/documents",
        data={"document_type": "PAN"},
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_list_kyc_documents(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    await http.post(
        f"/v1/merchants/{merchant_id}/kyc/documents",
        data={"document_type": "PAN"},
        files={"file": ("pan.pdf", _pdf_bytes(), "application/pdf")},
    )
    resp = await http.get(f"/v1/merchants/{merchant_id}/kyc/documents")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) >= 1
    for doc in docs:
        assert "s3_key_encrypted" not in doc  # never exposed


@pytest.mark.anyio
async def test_response_has_no_s3_path(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.post(
        f"/v1/merchants/{merchant_id}/kyc/documents",
        data={"document_type": "GSTIN"},
        files={"file": ("gstin.pdf", _pdf_bytes(), "application/pdf")},
    )
    data = resp.json()
    assert "s3_key_encrypted" not in data
    assert "s3_key" not in data
