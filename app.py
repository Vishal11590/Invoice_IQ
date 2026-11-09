from __future__ import annotations
import json, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal
from flask import Flask, jsonify, request, send_from_directory, abort
from werkzeug.utils import secure_filename
from backend.engine import extract_pdf, validate

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "data" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
DB = Path(os.environ.get("INVOICEIQ_DB", BASE / "instance" / "invoiceiq.sqlite3"))
DB.parent.mkdir(parents=True, exist_ok=True)
app = Flask(__name__, static_folder="frontend", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL,
            invoice_number TEXT, supplier TEXT, decision TEXT, total TEXT,
            result_json TEXT, error TEXT
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS processed_keys (
            supplier_key TEXT NOT NULL, invoice_key TEXT NOT NULL, run_id TEXT NOT NULL,
            PRIMARY KEY(supplier_key, invoice_key)
        )""")
init_db()

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "InvoiceIQ", "version": "1.0"})

@app.get("/api/runs")
def list_runs():
    with db() as con:
        rows = con.execute("SELECT id,created_at,status,invoice_number,supplier,decision,total,error FROM runs ORDER BY created_at DESC LIMIT 100").fetchall()
    return jsonify([dict(r) for r in rows])

@app.get("/api/runs/<run_id>")
def get_run(run_id):
    with db() as con:
        row = con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not row: abort(404)
    out = dict(row)
    out["result"] = json.loads(out.pop("result_json")) if out.get("result_json") else None
    return jsonify(out)

def save_run(run_id, status, invoice_number=None, supplier=None, decision=None, total=None, result=None, error=None):
    with db() as con:
        con.execute("""UPDATE runs SET status=?, invoice_number=COALESCE(?,invoice_number),
        supplier=COALESCE(?,supplier), decision=?, total=COALESCE(?,total), result_json=?, error=?
        WHERE id=?""", (status, invoice_number, supplier, decision, total,
                        json.dumps(result) if result else None, error, run_id))

@app.post("/api/process")
def process():
    required = ["invoice", "po", "grn"]
    if any(k not in request.files for k in required):
        return jsonify({"error": "Upload all three PDFs: invoice, purchase order and goods receipt note."}), 400
    uploads = {}
    for key in required:
        f = request.files[key]
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            return jsonify({"error": f"{key.upper()} must be a PDF file."}), 400
        safe = secure_filename(f.filename)
        if not safe:
            return jsonify({"error": f"Invalid filename for {key}."}), 400
        path = UPLOADS / f"{uuid.uuid4().hex}_{safe}"
        f.save(path)
        uploads[key] = path
    run_id = uuid.uuid4().hex[:12]
    created = datetime.now(timezone.utc).isoformat()
    with db() as con:
        con.execute("INSERT INTO runs(id,created_at,status) VALUES(?,?,?)", (run_id, created, "RUNNING"))
    stages = []
    try:
        stages.append({"stage":"Input received","status":"complete","detail":"Three PDF files received and type-checked by extension."})
        invoice = extract_pdf(uploads["invoice"], "INVOICE")
        stages.append({"stage":"Invoice extraction","status":"complete","detail":f"Extracted {invoice['invoice_number']} from invoice PDF."})
        po = extract_pdf(uploads["po"], "PO")
        stages.append({"stage":"Purchase order extraction","status":"complete","detail":f"Loaded PO {po['po_number']}."})
        grn = extract_pdf(uploads["grn"], "GRN")
        stages.append({"stage":"Goods receipt extraction","status":"complete","detail":f"Loaded GRN {grn['grn_number']}."})
        key = (invoice["supplier"].strip().casefold(), invoice["invoice_number"].strip().casefold())
        with db() as con:
            prior = { (r["supplier_key"], r["invoice_key"]) for r in con.execute("SELECT supplier_key,invoice_key FROM processed_keys") }
        stages.append({"stage":"Duplicate screening","status":"complete","detail":"Checked invoice identity against persistent processed-invoice history."})
        result = validate(invoice, po, grn, prior)
        stages.append({"stage":"Three-way matching","status":"complete","detail":"Compared supplier, PO reference, product ID, ordered/received quantity and unit price."})
        stages.append({"stage":"Financial validation","status":"complete","detail":"Recomputed subtotal, tax and grand total using Decimal arithmetic."})
        stages.append({"stage":"Decision","status":"complete","detail":result["summary"]})
        result["stages"] = stages
        result["run_id"] = run_id
        with db() as con:
            con.execute("INSERT OR IGNORE INTO processed_keys VALUES(?,?,?)", (key[0],key[1],run_id))
        save_run(run_id,"COMPLETED",result["invoice_number"],result["supplier"],result["decision"],result["invoice_total"],result)
        return jsonify({"run_id":run_id,"status":"COMPLETED","result":result})
    except Exception as exc:
        stages.append({"stage":"Processing error","status":"failed","detail":str(exc)})
        error_result = {"run_id":run_id,"decision":"NEEDS_REVIEW","stages":stages,"summary":str(exc)}
        save_run(run_id,"FAILED",decision="NEEDS_REVIEW",result=error_result,error=str(exc))
        return jsonify({"run_id":run_id,"status":"FAILED","error":str(exc),"result":error_result}), 422
    finally:
        for path in uploads.values():
            try: path.unlink(missing_ok=True)
            except OSError: pass

@app.get("/api/samples")
def samples():
    folder = BASE / "data" / "sample_documents"
    return jsonify(sorted(x.name for x in folder.glob("*.pdf")))

@app.post("/api/process-sample/<case>")
def process_sample(case):
    folder = BASE / "data" / "sample_documents"
    mapping = {
        "happy": ("INV_HAPPY.pdf","PO_HAPPY.pdf","GRN_HAPPY.pdf"),
        "quantity": ("INV_QUANTITY.pdf","PO_QUANTITY.pdf","GRN_QUANTITY.pdf"),
        "duplicate": ("INV_HAPPY.pdf","PO_HAPPY.pdf","GRN_HAPPY.pdf"),
        "math": ("INV_MATH.pdf","PO_MATH.pdf","GRN_MATH.pdf"),
    }
    if case not in mapping: abort(404)
    class F:
        def __init__(self,path): self.filename=path.name
        def save(self,dest): Path(dest).write_bytes(pathlib_read(self.filename))
    import io
    class Upload:
        def __init__(self,name): self.filename=name
        def save(self,dest): Path(dest).write_bytes((folder/name).read_bytes())
    class Multi:
        def __init__(self,name): self.filename=name
        def save(self,dest): Path(dest).write_bytes((folder/name).read_bytes())
    # Reuse the same processing path without exposing a second implementation.
    from werkzeug.datastructures import FileStorage
    from io import BytesIO
    files = {}
    for field,name in zip(("invoice","po","grn"),mapping[case]):
        files[field] = (BytesIO((folder/name).read_bytes()), name)
    with app.test_request_context("/api/process", method="POST", data=files, content_type="multipart/form-data"):
        return process()

def pathlib_read(name):
    return (BASE/"data"/"sample_documents"/name).read_bytes()

if __name__ == "__main__":
    app.run(host="127.0.0.1",port=int(os.environ.get("PORT",5000)))
