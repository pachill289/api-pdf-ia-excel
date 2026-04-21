"""
API unificada para procesamiento de facturas TIGO.
Reemplaza el flujo completo de Make.com:
  Webhook → Iterator → HTTP (extract) → HTTP (GPT) → JSON → Sheets → Router → Webhook response
"""

import os
from dotenv import load_dotenv
load_dotenv()

# CORS
from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from typing import List

from models import InvoiceData, ProcessResult
from services.pdf_extractor import extract_text_from_bytes
from services.openai_parser import parse_invoice_with_gpt
from services.sheets_manager import check_and_save_invoice

app = FastAPI(
    title="Invoice Processor API",
    description="Procesa facturas PDF de TIGO y las registra en Google Sheets",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "https://facturas-ia-excel.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# ENDPOINT PRINCIPAL — reemplaza TODO el flujo
# ─────────────────────────────────────────────

@app.post("/process-invoices", response_model=List[ProcessResult])
async def process_invoices(files: List[UploadFile] = File(...)):
    """
    Recibe uno o varios archivos PDF y por cada uno:
    1. Extrae el texto (PyMuPDF)
    2. Parsea los campos con GPT-3.5-turbo
    3. Verifica/agrega en Google Sheets
    4. Devuelve el resultado

    Uso desde Make (webhook) o cualquier cliente HTTP:
      POST /process-invoices
      Content-Type: multipart/form-data
      files: [archivo1.pdf, archivo2.pdf, ...]
    """
    results: List[ProcessResult] = []

    for upload in files:
        nro = "desconocida"
        try:
            # ① Leer bytes del PDF
            pdf_bytes = await upload.read()
            if not pdf_bytes:
                raise ValueError("Archivo vacío")

            # ② Extraer texto
            text = extract_text_from_bytes(pdf_bytes)
            if not text:
                raise ValueError("No se pudo extraer texto del PDF")

            # ③ Parsear con GPT → InvoiceData
            invoice: InvoiceData = parse_invoice_with_gpt(text)
            nro = invoice.nro_factura or "sin_numero"

            # ④ Verificar y guardar en Google Sheets
            sheet_result = check_and_save_invoice(invoice)

            results.append(ProcessResult(
                status=sheet_result["status"],
                nro_factura=nro,
                message=sheet_result["message"],
                spreadsheet_url=sheet_result["spreadsheet_url"],
                invoice_data=invoice,
            ))

        except Exception as e:
            results.append(ProcessResult(
                status="error",
                nro_factura=nro,
                message=f"Error procesando {upload.filename}: {str(e)}",
            ))

    return results


# ─────────────────────────────────────────────
# ENDPOINT LEGADO — compatible con tu lógica actual
# (recibe bytes crudos, igual que tu /extract-text)
# ─────────────────────────────────────────────

@app.post("/process-invoice-raw", response_model=ProcessResult)
async def process_invoice_raw(request: Request):
    """
    Compatibilidad con el nodo HTTP de Make que envía datos binarios crudos.
    Recibe los bytes del PDF directamente en el body (sin multipart).
    """
    pdf_bytes = await request.body()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Body vacío")

    nro = "desconocida"
    try:
        text = extract_text_from_bytes(pdf_bytes)
        invoice: InvoiceData = parse_invoice_with_gpt(text)
        nro = invoice.nro_factura or "sin_numero"
        sheet_result = check_and_save_invoice(invoice)

        return ProcessResult(
            status=sheet_result["status"],
            nro_factura=nro,
            message=sheet_result["message"],
            spreadsheet_url=sheet_result["spreadsheet_url"],
            invoice_data=invoice,
        )
    except Exception as e:
        return ProcessResult(
            status="error",
            nro_factura=nro,
            message=str(e),
        )


# ─────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}
