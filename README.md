# InvoiceIQ — Explainable Invoice Processing

**Zamp AI Solutions Analyst case study · PS-1 Finance / AP**

InvoiceIQ accepts three real PDF inputs — a supplier invoice, purchase order (PO), and goods receipt note (GRN) — extracts structured fields, performs deterministic three-way matching and financial checks, and returns an explainable `MATCHED` or `FLAGGED` result. It includes a browser UI, visible processing stages, persistent run history, sample scenarios and automated tests.

> **Safety boundary:** InvoiceIQ is a decision-support prototype. `MATCHED` means the configured checks passed; it is not payment authorization. A finance reviewer remains responsible for approval. Demo documents and vendor data are synthetic.

## Run locally

Python 3.10+ recommended.

```bash
git clone <your-repository-url>
cd invoiceiq_submission
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open **http://127.0.0.1:5000**.

Run tests:

```bash
pytest -q
```

## Try the working examples

Use the UI sample buttons:
- **Happy path:** all three documents agree; expected `MATCHED`.
- **Quantity edge case:** invoice bills more than the GRN received; expected `FLAGGED`.
- **Duplicate edge case:** process the happy-path invoice again; persistent invoice history detects the duplicate.
- **Math edge case:** invoice total does not equal subtotal + tax; expected `FLAGGED`.

You can also upload your own PDFs. For this prototype, PDFs must contain selectable text and use the labelled field layout shown in `data/sample_documents/`. Scanned/image-only PDFs are rejected with a clear message; OCR is not silently simulated.

## Workflow

```text
Invoice PDF ─┐
PO PDF ──────┼─> PDF text extraction + document-type checks
GRN PDF ─────┘                 |
                               v
                 Structured field extraction
                               |
                               v
                 Persistent duplicate screening
                               |
                               v
                  Three-way deterministic match
                  supplier · GSTIN · PO · product
                  quantity · received quantity · price
                               |
                               v
                   Financial arithmetic checks
                   subtotal · tax · grand total
                               |
                               v
                   Explainable decision + evidence
                               |
                               v
                  SQLite run history + UI dashboard
```

## Controls and decision policy

| Control | Logic |
|---|---|
| Duplicate invoice | Supplier + invoice number compared against prior processed invoices |
| PO reference | Invoice, PO and GRN PO numbers must agree |
| Supplier | Supplier names must agree across documents |
| GSTIN | All supplied GSTIN values must agree; missing values are not fabricated |
| Product | Product IDs must agree |
| Quantity | Billed quantity cannot exceed ordered or received quantity |
| Unit price | Invoice and PO unit prices compared with ₹0.01 tolerance |
| Subtotal | Quantity × unit price recomputed |
| Tax | Subtotal × stated tax rate recomputed |
| Total | Subtotal + tax amount recomputed |

Any failed check or GSTIN uncertainty results in `FLAGGED`. The tax rate is read from the invoice; no universal tax rate is hard-coded.

## API

- `GET /api/health` — service health
- `GET /api/runs` — latest 100 persisted runs
- `GET /api/runs/<run_id>` — full result for one run
- `POST /api/process` — multipart form with `invoice`, `po`, `grn` PDF fields
- `POST /api/process-sample/<happy|quantity|duplicate|math>` — execute a bundled test case

## Deployment

A Render Blueprint is included in `render.yaml`. Push this repository to GitHub, create a new Render Blueprint from the repository, and deploy. The included SQLite database is suitable for a single-instance demo; for production or multi-instance deployment, use managed PostgreSQL and object storage. Confirm the deployed URL and run the sample cases before submitting.

## Project structure

```text
invoiceiq_submission/
├── app.py
├── run.py
├── backend/
│   ├── __init__.py
│   └── engine.py
├── frontend/
│   └── index.html
├── data/
│   └── sample_documents/       # synthetic PDFs
├── tests/
│   └── test_engine.py
├── requirements.txt
├── Procfile
├── render.yaml
└── README.md
```

## Assumptions and limitations

- One invoice, one PO and one GRN per run; split invoices and multi-line invoices are not supported.
- The parser targets labelled, text-based PDFs; OCR and arbitrary vendor layouts are future work.
- Product identity uses an exact product ID. Semantic product matching is not enabled in this version.
- GSTIN comparison is a consistency check, not a government registry verification.
- Duplicate detection is scoped to this application's persistent database.
- SQLite is appropriate for a demo, not concurrent production workloads.
- No ERP integration, payment execution, or automatic final approval is performed.

## Why deterministic validation?

An LLM is not used to decide whether amounts add up or whether quantities match. Python `Decimal` arithmetic and explicit rules make those checks reproducible and auditable. AI-assisted extraction/semantic matching can be added later behind a review gate, but should never override hard financial controls.

## Demo video outline (under 5 minutes)

1. **0:00–0:35** — Explain the AP problem and show the three PDF upload inputs.
2. **0:35–1:35** — Run the happy path; narrate extraction, duplicate screening, three-way matching and arithmetic checks.
3. **1:35–2:30** — Open the evidence table and explain why each check passed.
4. **2:30–3:25** — Run the quantity edge case; show the received quantity mismatch and `FLAGGED` decision.
5. **3:25–4:10** — Run the same happy invoice again; show duplicate detection using persisted history.
6. **4:10–4:45** — Show dashboard history and state limitations honestly.

Do not use an AI voice. Record the actual app running, not a mockup.
