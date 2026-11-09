# Verification record

Executed in the build environment on 2026-11-09.

- `python -m pytest -q`: **14 passed**
- Coverage includes deterministic matching rules, duplicate detection, quantity/price/product/supplier/PO/tax/total discrepancies, GSTIN review, PDF field extraction and wrong-document-type rejection.
- The four sample PDF sets were generated and are included under `data/sample_documents/`.

The build environment did not have Flask installed and had no network access to install it, so the Flask HTTP server/browser workflow was **not runtime-smoke-tested here**. Install `requirements.txt` and follow the README before deploying. After deployment, run each of the four UI sample buttons and verify the dashboard history before sharing the live URL.
