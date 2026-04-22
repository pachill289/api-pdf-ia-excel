import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List

from models import InvoiceData, ProcessResult
from services.pdf_extractor import extract_text_from_bytes
from services.openai_parser import parse_invoice_with_gpt
from services.sheets_manager import check_and_save_invoice, get_pll_next_doc_entry

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


@app.post("/process-invoices", response_model=List[ProcessResult])
async def process_invoices(files: List[UploadFile] = File(...)):
    results: List[ProcessResult] = []

    # Calcular el DocEntry base UNA sola vez para todo el lote.
    # Si la hoja PLL está vacía → arranca en 1.
    # Si ya tiene registros → continúa desde el máximo + 1.
    # Cada factura nueva del lote incrementa el contador localmente.
    try:
        doc_entry_counter = get_pll_next_doc_entry()
    except Exception as e:
        # Si falla la conexión a Sheets al inicio, abortar con error claro
        return [ProcessResult(
            status="error",
            nro_factura="—",
            message=f"No se pudo conectar a Google Sheets: {str(e)}",
        )]

    for upload in files:
        nro = "desconocida"
        try:
            pdf_bytes = await upload.read()
            if not pdf_bytes:
                raise ValueError("Archivo vacío")

            text = extract_text_from_bytes(pdf_bytes)
            if not text:
                raise ValueError("No se pudo extraer texto del PDF")

            invoice: InvoiceData = parse_invoice_with_gpt(text)
            nro = invoice.nro_factura or "sin_numero"

            sheet_result = check_and_save_invoice(invoice, doc_entry_counter)

            # Solo incrementar el contador si realmente se insertó en PLL
            if sheet_result["status_pll"] == "added":
                doc_entry_counter += 1

            results.append(ProcessResult(
                status           = sheet_result["status_facturas"],
                nro_factura      = nro,
                message          = sheet_result["message_facturas"],
                spreadsheet_url  = sheet_result["spreadsheet_url"],
                invoice_data     = invoice,
                status_facturas  = sheet_result["status_facturas"],
                message_facturas = sheet_result["message_facturas"],
                status_pll       = sheet_result["status_pll"],
                message_pll      = sheet_result["message_pll"],
            ))

        except Exception as e:
            results.append(ProcessResult(
                status      = "error",
                nro_factura = nro,
                message     = f"Error procesando {upload.filename}: {str(e)}",
            ))

    return results


@app.post("/process-invoice-raw", response_model=ProcessResult)
async def process_invoice_raw(request: Request):
    pdf_bytes = await request.body()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Body vacío")

    nro = "desconocida"
    try:
        text     = extract_text_from_bytes(pdf_bytes)
        invoice  = parse_invoice_with_gpt(text)
        nro      = invoice.nro_factura or "sin_numero"
        entry    = get_pll_next_doc_entry()
        result   = check_and_save_invoice(invoice, entry)

        return ProcessResult(
            status           = result["status_facturas"],
            nro_factura      = nro,
            message          = result["message_facturas"],
            spreadsheet_url  = result["spreadsheet_url"],
            invoice_data     = invoice,
            status_facturas  = result["status_facturas"],
            message_facturas = result["message_facturas"],
            status_pll       = result["status_pll"],
            message_pll      = result["message_pll"],
        )
    except Exception as e:
        return ProcessResult(
            status="error", nro_factura=nro, message=str(e)
        )


@app.get("/health")
def health():
    return {"status": "ok"}