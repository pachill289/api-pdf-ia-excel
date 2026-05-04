import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List

from models import InvoiceData, ProcessResult
from services.pdf_extractor import extract_text_from_bytes, split_invoices_from_text
from services.openai_parser import parse_invoice_with_gpt
from services.sheets_manager import check_and_save_invoice, get_pll_next_doc_entry, clear_all_invoices

app = FastAPI(
    title="Invoice Processor API",
    description="Procesa facturas PDF de telecomunicaciones (TIGO, ENTEL, etc.) y las registra en Google Sheets",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "https://facturas-ia-excel.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _process_single_invoice(
    text: str,
    filename: str,
    doc_entry_counter: int,
) -> tuple[ProcessResult, int]:
    """
    Procesa el texto de UNA factura y la guarda en Sheets.
    Devuelve (ProcessResult, nuevo_doc_entry_counter).
    """
    nro = "desconocida"
    try:
        invoice: InvoiceData = parse_invoice_with_gpt(text)
        nro = invoice.nro_factura or "sin_numero"

        sheet_result = check_and_save_invoice(invoice, doc_entry_counter)

        if sheet_result["status_pll"] == "added":
            doc_entry_counter += 1

        result = ProcessResult(
            status           = sheet_result["status_facturas"],
            nro_factura      = nro,
            filename         = filename,
            message          = sheet_result["message_facturas"],
            spreadsheet_url  = sheet_result["spreadsheet_url"],
            invoice_data     = invoice,
            status_facturas  = sheet_result["status_facturas"],
            message_facturas = sheet_result["message_facturas"],
            status_pll       = sheet_result["status_pll"],
            message_pll      = sheet_result["message_pll"],
        )
    except Exception as e:
        result = ProcessResult(
            status      = "error",
            nro_factura = nro,
            filename    = filename,
            message     = f"Error al procesar: {str(e)}",
        )

    return result, doc_entry_counter


@app.post("/process-invoices", response_model=List[ProcessResult])
async def process_invoices(files: List[UploadFile] = File(...)):
    """
    Recibe uno o varios archivos PDF.
    Cada PDF puede contener UNA o MÚLTIPLES facturas (ej: PDF multi-factura de ENTEL).
    Por cada factura detectada se genera un ProcessResult independiente.
    """
    results: List[ProcessResult] = []

    # Calcular el DocEntry base una sola vez para todo el lote
    try:
        doc_entry_counter = get_pll_next_doc_entry()
    except Exception as e:
        return [ProcessResult(
            status="error",
            nro_factura="—",
            filename=None,
            message=f"No se pudo conectar a Google Sheets: {str(e)}",
        )]

    for upload in files:
        filename = upload.filename or "archivo_desconocido.pdf"
        try:
            pdf_bytes = await upload.read()
            if not pdf_bytes:
                results.append(ProcessResult(
                    status="error", nro_factura="desconocida",
                    filename=filename, message="Archivo vacío",
                ))
                continue

            # Extraer todo el texto del PDF
            full_text = extract_text_from_bytes(pdf_bytes)
            if not full_text:
                results.append(ProcessResult(
                    status="error", nro_factura="desconocida",
                    filename=filename, message="No se pudo extraer texto del PDF",
                ))
                continue

            # Dividir en bloques individuales (1 bloque si es mono-factura,
            # N bloques si el PDF tiene múltiples facturas como los de ENTEL)
            invoice_blocks = split_invoices_from_text(full_text)

            for i, block in enumerate(invoice_blocks):
                # Si el PDF tiene múltiples facturas, añadir el índice al filename
                block_filename = (
                    filename if len(invoice_blocks) == 1
                    else f"{filename} (factura {i + 1}/{len(invoice_blocks)})"
                )
                result, doc_entry_counter = await _process_single_invoice(
                    block, block_filename, doc_entry_counter
                )
                results.append(result)

        except Exception as e:
            results.append(ProcessResult(
                status="error",
                nro_factura="desconocida",
                filename=filename,
                message=f"Error leyendo el archivo: {str(e)}",
            ))

    return results


@app.post("/process-invoice-raw", response_model=ProcessResult)
async def process_invoice_raw(request: Request):
    """Endpoint legado — recibe bytes crudos de un único PDF."""
    pdf_bytes = await request.body()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Body vacío")

    nro = "desconocida"
    try:
        full_text = extract_text_from_bytes(pdf_bytes)
        blocks    = split_invoices_from_text(full_text)
        # Para el endpoint raw solo procesamos la primera factura detectada
        invoice   = parse_invoice_with_gpt(blocks[0])
        nro       = invoice.nro_factura or "sin_numero"
        entry     = get_pll_next_doc_entry()
        result    = check_and_save_invoice(invoice, entry)

        return ProcessResult(
            status           = result["status_facturas"],
            nro_factura      = nro,
            filename         = None,
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
            status="error", nro_factura=nro, filename=None, message=str(e)
        )

@app.delete("/clear-invoices")
def clear_invoices():
    """
    Elimina todos los registros de datos de ambas hojas (conserva headers).
      - Facturas: borra desde fila 2 en adelante
      - PLL MULTIFACTURAS: borra desde fila 3 en adelante
    """
    try:
        cleared = clear_all_invoices()
        return {
            "status": "ok",
            "message": f"Se eliminaron {cleared['facturas']} filas de Facturas y {cleared['pll']} filas de PLL MULTIFACTURAS.",
            "cleared": cleared,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/health")
def health():
    return {"status": "ok"}