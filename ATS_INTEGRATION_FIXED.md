# ATS Integration Fix

The Interview Assistant now explicitly loads `static/ats.js`, which wires the ATS candidate-management UI to the Flask ATS endpoints.

## Verified flow
1. Interview Assistant loads ATS JavaScript.
2. ATS config is loaded from `/api/ats/config`.
3. Candidate records are retrieved from `/api/ats/candidates`.
4. Selected candidates are synchronized through `/api/ats/sync`.
5. Demo ATS upserts by candidate email to prevent duplicates.
6. Pipeline status changes are sent to `/api/ats/candidates/<email>/status`.
7. The bundled Mock ATS also exposes `/candidates` and `/candidates/<email>/status` for an end-to-end API demonstration.

## VS Code
Run `python app.py`, open `http://127.0.0.1:5000/interview`, then hard-refresh with `Ctrl+Shift+R`.
