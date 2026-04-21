import os
import json
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from models import InvoiceData

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

SHEET_NAME = os.getenv("SHEET_NAME", "Facturas")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
INVOICE_COL_INDEX = 1  # Columna A = no. fact

# Encabezados exactos del Excel del cliente
# Columnas que quedan en blanco: Codigo Articulo, Concepto Articulo,
# CeCos 2026, ID-Borrador, ID=OC 26000000, Columna1, al 87%, Tipo de Pago
HEADERS = [
    "no. fact",               # A - nro_factura
    "Proveedor",              # B - proveedor
    "Servicio",               # C - concepto (plan + contrato + periodo)
    "Codigo Articulo",        # D - VACIO
    "Concepto Articulo",      # E - VACIO
    "Periodo Facturacion",    # F - periodo_facturacion
    "Fecha de la factura",    # G - fecha_emision
    "Monto Fact en BS.",      # H - monto_total
    "CeCos 2026",             # I - VACIO
    "ID-Borrador",            # J - VACIO
    "ID=OC 26000000",         # K - VACIO
    "Columna1",               # L - VACIO
    "al 87%",                 # M - importe_base_credito_fiscal
    "Tipo de Pago",           # N - VACIO
]


def _get_sheet():
    """
    Autentica con Google y devuelve la hoja de calculo.
    Modo local:  GOOGLE_CREDENTIALS_JSON = ruta al .json
    Modo deploy: GOOGLE_CREDENTIALS_JSON_CONTENT = contenido JSON completo
    """
    creds_content = os.getenv("GOOGLE_CREDENTIALS_JSON_CONTENT")
    if creds_content:
        info = json.loads(creds_content)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
        if not os.path.exists(credentials_path):
            raise FileNotFoundError(
                f"No se encontro '{credentials_path}'.\n"
                "Descarga el JSON de tu Service Account y colócalo en la raíz del proyecto."
            )
        creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)

    if not SPREADSHEET_ID:
        raise ValueError("La variable SPREADSHEET_ID está vacía. Agrégala en tu .env")

    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    try:
        sheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=20)
        sheet.append_row(HEADERS)

    return sheet, spreadsheet


def check_and_save_invoice(invoice: InvoiceData) -> dict:
    """
    Verifica si no. fact ya existe en el Sheet.
      - Si existe  -> status='duplicate'
      - Si no existe -> agrega la fila con el formato del Excel -> status='added'
    """
    sheet, _ = _get_sheet()

    existing_values = sheet.col_values(INVOICE_COL_INDEX)
    spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"

    if invoice.nro_factura in existing_values:
        return {
            "status": "duplicate",
            "message": f"Factura {invoice.nro_factura} ya existe en el registro.",
            "spreadsheet_url": spreadsheet_url,
        }

    # Armar el campo Servicio igual al formato del Excel original:
    # "SERVICIO MOVIL - [plan] - [periodo]"
    servicio = f"SERVICIO MOVIL - {invoice.plan} - {invoice.periodo_facturacion}".upper()

    row = [
        invoice.nro_factura,           # A  no. fact
        invoice.proveedor,             # B  Proveedor
        servicio,                      # C  Servicio
        "",                            # D  Codigo Articulo     — VACIO
        "",                            # E  Concepto Articulo   — VACIO
        invoice.periodo_facturacion,   # F  Periodo Facturacion
        invoice.fecha_emision,         # G  Fecha de la factura
        invoice.monto_total,           # H  Monto Fact en BS.
        "",                            # I  CeCos 2026          — VACIO
        "",                            # J  ID-Borrador         — VACIO
        "",                            # K  ID=OC 26000000      — VACIO
        "",                            # L  Columna1            — VACIO
        invoice.monto_total * 0.87,    # M  al 87%
        "",                            # N  Tipo de Pago        — VACIO
    ]
    sheet.append_row(row, value_input_option="USER_ENTERED")

    return {
        "status": "added",
        "message": f"Factura {invoice.nro_factura} agregada correctamente.",
        "spreadsheet_url": spreadsheet_url,
    }