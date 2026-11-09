"""Deterministic invoice extraction and three-way matching engine.

Supported demo PDF schema is deliberately explicit. Financial arithmetic and
matching are performed in Python, not delegated to an LLM.
"""
from __future__ import annotations
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
import fitz

MONEY = re.compile(r"[-+]?\d[\d,]*(?:\.\d{1,2})?")
def _field(text: str, label: str, required=True):
    m = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.*?)\s*$", text)
    if not m:
        if required:
            raise ValueError(f"Required field '{label}' was not found. Check that this is a readable digital PDF.")
        return None
    value = m.group(1).strip()
    if required and not value:
        raise ValueError(f"Required field '{label}' is empty.")
    return value or None

def _decimal(value, label):
    if value is None:
        raise ValueError(f"Missing numeric field: {label}")
    try:
        return Decimal(value.replace(",", "").replace("₹", "").replace("INR", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"Could not parse {label} as a number: {value!r}")

def extract_pdf(path, expected_type):
    doc = fitz.open(path)
    try:
        text = "\n".join(page.get_text("text") for page in doc).strip()
    finally:
        doc.close()
    if len(text) < 20:
        raise ValueError("This PDF has no extractable text. Scanned/image-only PDFs require OCR and are not supported in this build.")
    heading = text.upper()
    expected_heading = {"INVOICE": "TAX INVOICE", "PO": "PURCHASE ORDER", "GRN": "GOODS RECEIPT NOTE"}[expected_type]
    if expected_heading not in heading:
        raise ValueError(f"Document type mismatch: expected {expected_type}, but the PDF heading does not contain '{expected_heading}'.")
    common = {
        "document_type": expected_type,
        "supplier": _field(text, "Supplier"),
        "gstin": _field(text, "GSTIN", required=False),
        "po_number": _field(text, "PO Number"),
    }
    if expected_type == "INVOICE":
        data = {
            **common,
            "invoice_number": _field(text, "Invoice Number"),
            "invoice_date": _field(text, "Invoice Date", required=False),
            "product_id": _field(text, "Product ID"),
            "description": _field(text, "Description"),
            "quantity": _decimal(_field(text, "Quantity"), "Quantity"),
            "unit_price": _decimal(_field(text, "Unit Price"), "Unit Price"),
            "subtotal": _decimal(_field(text, "Subtotal"), "Subtotal"),
            "tax_rate": _decimal(_field(text, "Tax Rate"), "Tax Rate"),
            "tax_amount": _decimal(_field(text, "Tax Amount"), "Tax Amount"),
            "total": _decimal(_field(text, "Total"), "Total"),
        }
    elif expected_type == "PO":
        data = {
            **common,
            "product_id": _field(text, "Product ID"),
            "description": _field(text, "Description"),
            "quantity": _decimal(_field(text, "Quantity"), "PO Quantity"),
            "unit_price": _decimal(_field(text, "Unit Price"), "PO Unit Price"),
        }
    else:
        data = {
            **common,
            "grn_number": _field(text, "GRN Number"),
            "product_id": _field(text, "Product ID"),
            "description": _field(text, "Description"),
            "received_quantity": _decimal(_field(text, "Received Quantity"), "Received Quantity"),
        }
    return data

def _check(name, passed, message, severity="exception"):
    return {"name": name, "status": "PASS" if passed else ("REVIEW" if severity == "review" else "FAIL"), "message": message}

def validate(invoice, po, grn, previous_invoice_keys=None, tolerance=Decimal("0.01")):
    checks = []
    key = (invoice["supplier"].strip().casefold(), invoice["invoice_number"].strip().casefold())
    duplicate = key in (previous_invoice_keys or set())
    checks.append(_check("Duplicate invoice", not duplicate,
        "No prior invoice with this supplier + invoice number was found." if not duplicate else "This supplier has already submitted this invoice number."))
    checks.append(_check("PO reference", invoice["po_number"] == po["po_number"] == grn["po_number"],
        f"Invoice: {invoice['po_number']} · PO: {po['po_number']} · GRN: {grn['po_number']}"))
    supplier_ok = invoice["supplier"].casefold() == po["supplier"].casefold() == grn["supplier"].casefold()
    checks.append(_check("Supplier identity", supplier_ok, "Supplier names agree across all three documents." if supplier_ok else "Supplier names differ across invoice, PO and/or GRN."))
    gstins = [x.get("gstin") for x in (invoice, po, grn) if x.get("gstin")]
    gst_ok = len(set(gstins)) <= 1
    checks.append(_check("GSTIN consistency", gst_ok, "Available GSTIN values agree." if gst_ok else "GSTIN values conflict across documents.", "review"))
    product_ok = invoice["product_id"] == po["product_id"] == grn["product_id"]
    checks.append(_check("Product ID", product_ok, f"Invoice: {invoice['product_id']} · PO: {po['product_id']} · GRN: {grn['product_id']}"))
    qty_ok = invoice["quantity"] <= po["quantity"] and invoice["quantity"] <= grn["received_quantity"]
    checks.append(_check("Quantity received", qty_ok,
        f"Billed {invoice['quantity']} · Ordered {po['quantity']} · Received {grn['received_quantity']}"))
    price_ok = abs(invoice["unit_price"] - po["unit_price"]) <= tolerance
    checks.append(_check("Unit price", price_ok,
        f"Invoice {invoice['unit_price']} · PO {po['unit_price']} (tolerance ₹{tolerance})"))
    calc_subtotal = invoice["quantity"] * invoice["unit_price"]
    subtotal_ok = abs(invoice["subtotal"] - calc_subtotal) <= tolerance
    checks.append(_check("Subtotal arithmetic", subtotal_ok,
        f"Expected ₹{calc_subtotal:.2f}; invoice shows ₹{invoice['subtotal']:.2f}"))
    expected_tax = invoice["subtotal"] * invoice["tax_rate"] / Decimal("100")
    tax_ok = abs(invoice["tax_amount"] - expected_tax) <= tolerance
    checks.append(_check("Tax arithmetic", tax_ok,
        f"At {invoice['tax_rate']}%, expected ₹{expected_tax:.2f}; invoice shows ₹{invoice['tax_amount']:.2f}"))
    expected_total = invoice["subtotal"] + invoice["tax_amount"]
    total_ok = abs(invoice["total"] - expected_total) <= tolerance
    checks.append(_check("Grand total arithmetic", total_ok,
        f"Expected ₹{expected_total:.2f}; invoice shows ₹{invoice['total']:.2f}"))
    hard_fail = any(c["status"] == "FAIL" for c in checks)
    review = any(c["status"] == "REVIEW" for c in checks)
    decision = "FLAGGED" if hard_fail or review else "MATCHED"
    reasons = [c["message"] for c in checks if c["status"] != "PASS"]
    return {
        "decision": decision,
        "invoice_number": invoice["invoice_number"],
        "supplier": invoice["supplier"],
        "po_number": invoice["po_number"],
        "invoice_total": str(invoice["total"]),
        "checks": checks,
        "summary": "All configured checks passed. Ready for finance review." if decision == "MATCHED" else "Discrepancies or uncertainties require human review: " + " ".join(reasons),
        "disputed_amount": str(invoice["total"] if hard_fail else Decimal("0.00")),
    }
