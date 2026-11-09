from decimal import Decimal
from backend.engine import validate

def docs():
    inv={"supplier":"Northstar Systems","gstin":"27ABCDE1234F1Z5","po_number":"PO-1001","invoice_number":"INV-1001","product_id":"SSD-1TB","description":"1TB NVMe SSD","quantity":Decimal("10"),"unit_price":Decimal("5000"),"subtotal":Decimal("50000"),"tax_rate":Decimal("18"),"tax_amount":Decimal("9000"),"total":Decimal("59000")}
    po={"supplier":"Northstar Systems","gstin":"27ABCDE1234F1Z5","po_number":"PO-1001","product_id":"SSD-1TB","description":"1TB NVMe SSD","quantity":Decimal("10"),"unit_price":Decimal("5000")}
    grn={"supplier":"Northstar Systems","gstin":"27ABCDE1234F1Z5","po_number":"PO-1001","grn_number":"GRN-1001","product_id":"SSD-1TB","description":"1TB NVMe SSD","received_quantity":Decimal("10")}
    return inv,po,grn

def test_happy_path_matches():
    i,p,g=docs()
    assert validate(i,p,g)["decision"]=="MATCHED"

def test_quantity_shortfall_flagged():
    i,p,g=docs(); g["received_quantity"]=Decimal("8")
    assert validate(i,p,g)["decision"]=="FLAGGED"

def test_price_mismatch_flagged():
    i,p,g=docs(); i["unit_price"]=Decimal("5100")
    assert validate(i,p,g)["decision"]=="FLAGGED"

def test_duplicate_flagged():
    i,p,g=docs()
    assert validate(i,p,g,{("northstar systems","inv-1001")})["decision"]=="FLAGGED"

def test_wrong_po_flagged():
    i,p,g=docs(); i["po_number"]="PO-OTHER"
    assert validate(i,p,g)["decision"]=="FLAGGED"

def test_tax_math_flagged():
    i,p,g=docs(); i["tax_amount"]=Decimal("100")
    assert validate(i,p,g)["decision"]=="FLAGGED"

def test_total_math_flagged():
    i,p,g=docs(); i["total"]=Decimal("60000")
    assert validate(i,p,g)["decision"]=="FLAGGED"

def test_product_id_flagged():
    i,p,g=docs(); g["product_id"]="SSD-512GB"
    assert validate(i,p,g)["decision"]=="FLAGGED"

def test_supplier_mismatch_flagged():
    i,p,g=docs(); p["supplier"]="Other Vendor"
    assert validate(i,p,g)["decision"]=="FLAGGED"

def test_gstin_conflict_requires_review():
    i,p,g=docs(); g["gstin"]="DIFFERENT"
    result=validate(i,p,g)
    assert result["decision"]=="FLAGGED"
    assert any(c["status"]=="REVIEW" for c in result["checks"])
