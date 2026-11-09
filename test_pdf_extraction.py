from pathlib import Path
from backend.engine import extract_pdf

ROOT = Path(__file__).resolve().parents[1] / "data" / "sample_documents"

def test_invoice_pdf_extracts_fields():
    data = extract_pdf(ROOT / "INV_HAPPY.pdf", "INVOICE")
    assert data["invoice_number"] == "INV-1001"
    assert data["total"] == 59000

def test_po_pdf_extracts_order():
    data = extract_pdf(ROOT / "PO_HAPPY.pdf", "PO")
    assert data["po_number"] == "PO-1001"
    assert data["quantity"] == 10

def test_grn_pdf_extracts_received_quantity():
    data = extract_pdf(ROOT / "GRN_HAPPY.pdf", "GRN")
    assert data["received_quantity"] == 10

def test_wrong_document_type_is_rejected():
    import pytest
    with pytest.raises(ValueError, match="Document type mismatch"):
        extract_pdf(ROOT / "PO_HAPPY.pdf", "INVOICE")
