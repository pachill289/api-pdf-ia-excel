import os
import json
import time
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from models import InvoiceData

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

SHEET_NAME      = os.getenv("SHEET_NAME", "Facturas")
SHEET_NAME_PLL  = "PLL MULTIFACTURAS"
SPREADSHEET_ID  = os.getenv("SPREADSHEET_ID", "")

HEADERS_FACTURAS = [
    "no. fact",            # A
    "Proveedor",           # B
    "Servicio",            # C
    "Codigo Articulo",     # D
    "Concepto Articulo",   # E
    "Periodo Facturacion", # F
    "Fecha de la factura", # G
    "Monto Fact en BS.",   # H
    "CeCos 2026",          # I
    "ID-Borrador",         # J
    "ID=OC 26000000",      # K
    "Columna1",            # L
    "al 87%",              # M
    "Tipo de Pago",        # N
]

# Fila 1: nombres técnicos (header principal)
HEADERS_PLL_ROW1 = [
    "DocNum","DocEntry","ItemCode","","DocDueDate","CardCode","NumAtCard",
    "","","","DocTotal","DocCurrency","CostingCode","","JournalMemo",
    "TaxDate","U_RAZSOC","U_NROAUTOR","U_FORMA_PAGO","U_NOMBRE_SOLICITANTE",
    "U_ADJ_DIRECTA","U_NROCONTRATOADENDA","U_NROPAGOCONTRACTUAL",
    "U_FECHAINICIO","U_FECHAFIN","U_PERIODO","U_NRODEFACTURA",
    "U_INMUEBLE","U_Nro_cuenta","U_Nombre_banco","U_B_cuf",
]

# Fila 2: nombres legibles en rojo (segundo encabezado)
HEADERS_PLL_ROW2 = [
    "","N°","N° ARTÍCULO","DESCRIPCION ARTÍCULO","FECHA DE SOLICITUD",
    "CODIGO PROVEEDOR EN SAP","N° FACTURA","SUBTOTAL","DESCUENTO","%",
    "MONTO TOTAL DE LA FACTURA","MONEDA","CENTRO DE COSTO","IMPORTE CECO",
    "COMENTARIO/DESCRIPCION DE PAGO DE LA FACTURA","FECHA DE FACTURA",
    "RAZON SOCIAL","CUF/NRO AUTORIZACION","FORMA DE PAGO","NOMBRE SOLICITANTE",
    "PAGO PROVEEDOR","CONTRATO O ADENDA (INDICAR EL VIGENTE)",
    "N° DE PAGO QUE SE ESTA REALIZANDO DEL CTTO O ADENDA",
    "FECHA INICIO CTTO O ADENDA","FECHA FIN CTTO O ADENDA","PERIODO DEL SERVICIO",
    "NRO DE FACTURA","SUCURSAL","NRO CUENTA BANCARIA","NOMBRE BANCO",
    "CUF/NRO AUTORIZACION",
]

COL_FACTURAS_NRO = 1   # col A: no. fact
COL_PLL_DOCENTRY = 2   # col B: DocEntry
COL_PLL_NRO      = 7   # col G: NumAtCard = nro_factura
PLL_DATA_START   = 3   # los datos arrancan en fila 3 (filas 1 y 2 son headers)

# ── Utilidades ────────────────────────────────────────────────────────────────

def _col_letter(n):
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def _with_retry(fn, retries=3, delay=2):
    """
    Reintenta fn() hasta `retries` veces ante errores de red/timeout.
    Resuelve los errores intermitentes en Render (plan gratuito hiberna).
    """
    last_err = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))  # backoff: 2s, 4s
    raise last_err


def _get_spreadsheet():
    creds_content = os.getenv("GOOGLE_CREDENTIALS_JSON_CONTENT")
    if creds_content:
        info  = json.loads(creds_content)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        path = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"No se encontro '{path}'.\n"
                "Descarga el JSON de tu Service Account y colocalo en la raiz del proyecto."
            )
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)

    if not SPREADSHEET_ID:
        raise ValueError("La variable SPREADSHEET_ID esta vacia. Agregala en tu .env")

    gc = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID)


def _get_or_create_sheet_facturas(spreadsheet):
    try:
        return spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(
            title=SHEET_NAME, rows=1000, cols=len(HEADERS_FACTURAS)
        )
        sheet.update("A1", [HEADERS_FACTURAS])
        return sheet


def _get_or_create_sheet_pll(spreadsheet):
    """
    Crea la hoja PLL con dos filas de encabezado si no existe.
    Los datos arrancan siempre desde la fila 3.
    """
    try:
        return spreadsheet.worksheet(SHEET_NAME_PLL)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(
            title=SHEET_NAME_PLL, rows=1000, cols=len(HEADERS_PLL_ROW1)
        )
        # Escribir ambas filas de header en una sola llamada
        sheet.update("A1", [HEADERS_PLL_ROW1, HEADERS_PLL_ROW2])
        return sheet


# ── Conteo de filas de datos ──────────────────────────────────────────────────

def _count_data_rows_pll(sheet) -> int:
    """
    Cuenta filas de datos en PLL usando col G (NumAtCard).
    Ignora las dos primeras filas (headers).
    Si col G tiene solo headers o está vacía → 0 registros.
    """
    values    = sheet.col_values(COL_PLL_NRO)   # incluye fila1 y fila2
    data_rows = [v for v in values[2:] if v.strip() != ""]
    return len(data_rows)


def _next_row_facturas(sheet) -> int:
    values = sheet.col_values(COL_FACTURAS_NRO)
    return len(values) + 1


def _next_row_pll(sheet) -> int:
    """
    Calcula la próxima fila vacía en PLL usando col G.
    Como hay 2 headers, si no hay datos devuelve 3.
    """
    values = sheet.col_values(COL_PLL_NRO)   # fila1=header1, fila2=header2, resto=datos
    data   = [v for v in values[2:] if v.strip() != ""]
    return PLL_DATA_START + len(data)        # 3 + cantidad de datos


# ── Construcción de filas ─────────────────────────────────────────────────────

def _build_row_facturas(invoice: InvoiceData) -> list:
    servicio = f"SERVICIO MOVIL - {invoice.plan} - {invoice.periodo_facturacion}".upper()
    return [
        invoice.nro_factura,
        invoice.proveedor,
        servicio,
        "", "",
        invoice.periodo_facturacion,
        invoice.fecha_emision,
        invoice.monto_total,
        "", "", "", "",
        invoice.monto_total * 0.87,
        "",
    ]


def _build_row_pll(invoice: InvoiceData, doc_entry: int) -> list:
    return [
        "",                              # A  DocNum
        doc_entry,                       # B  DocEntry        ← autoincremental
        "", "", "", "",                  # C D E F
        invoice.nro_factura,             # G  NumAtCard
        "", "", "",                      # H I J
        invoice.monto_total,             # K  DocTotal
        "", "", "",                      # L M N
        invoice.concepto,                # O  JournalMemo
        invoice.fecha_emision,           # P  TaxDate
        invoice.razon_social_cliente,    # Q  U_RAZSOC
        invoice.cod_autorizacion,        # R  U_NROAUTOR
        "", "", "",                      # S T U
        invoice.contrato,                # V  U_NROCONTRATOADENDA
        "", "", "",                      # W X Y
        invoice.periodo_facturacion,     # Z  U_PERIODO
        invoice.nro_factura,             # AA U_NRODEFACTURA
        "", "", "",                      # AB AC AD
        invoice.cod_autorizacion,        # AE U_B_cuf
    ]


# ── Inserción segura ──────────────────────────────────────────────────────────

def _safe_append_facturas(sheet, row):
    next_row = _next_row_facturas(sheet)
    end_col  = _col_letter(len(row))
    _with_retry(lambda: sheet.update(
        f"A{next_row}:{end_col}{next_row}", [row], value_input_option="USER_ENTERED"
    ))


def _safe_append_pll(sheet, row):
    next_row = _next_row_pll(sheet)
    end_col  = _col_letter(len(row))
    _with_retry(lambda: sheet.update(
        f"A{next_row}:{end_col}{next_row}", [row], value_input_option="USER_ENTERED"
    ))


# ── API pública ───────────────────────────────────────────────────────────────

def get_pll_next_doc_entry() -> int:
    """
    Devuelve el próximo DocEntry para PLL MULTIFACTURAS.
    - Hoja vacía o recién limpiada → 1 (reset de secuencia).
    - Con registros → max(DocEntry existente) + 1.
    """
    spreadsheet = _with_retry(_get_spreadsheet)
    sheet_pll   = _get_or_create_sheet_pll(spreadsheet)

    if _count_data_rows_pll(sheet_pll) == 0:
        return 1

    doc_entry_values = sheet_pll.col_values(COL_PLL_DOCENTRY)
    numbers = []
    for v in doc_entry_values[2:]:   # ignorar las 2 filas de header
        try:
            numbers.append(int(float(v)))
        except (ValueError, TypeError):
            pass

    return (max(numbers) + 1) if numbers else 1


def check_and_save_invoice(invoice: InvoiceData, pll_doc_entry: int) -> dict:
    """
    Inserta en ambas hojas con validación independiente y reintentos automáticos.
    """
    spreadsheet    = _with_retry(_get_spreadsheet)
    sheet_facturas = _get_or_create_sheet_facturas(spreadsheet)
    sheet_pll      = _get_or_create_sheet_pll(spreadsheet)

    spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"

    # ── Hoja Facturas ─────────────────────────────────────────────────────────
    existing_facturas = _with_retry(lambda: sheet_facturas.col_values(COL_FACTURAS_NRO))
    if invoice.nro_factura in existing_facturas:
        status_facturas  = "duplicate"
        message_facturas = f"Factura {invoice.nro_factura} ya existe en Facturas."
    else:
        _safe_append_facturas(sheet_facturas, _build_row_facturas(invoice))
        status_facturas  = "added"
        message_facturas = f"Factura {invoice.nro_factura} agregada en Facturas."

    # ── Hoja PLL MULTIFACTURAS ────────────────────────────────────────────────
    existing_pll = _with_retry(lambda: sheet_pll.col_values(COL_PLL_NRO))
    if invoice.nro_factura in existing_pll:
        status_pll  = "duplicate"
        message_pll = f"Factura {invoice.nro_factura} ya existe en PLL MULTIFACTURAS."
    else:
        _safe_append_pll(sheet_pll, _build_row_pll(invoice, pll_doc_entry))
        status_pll  = "added"
        message_pll = f"Factura {invoice.nro_factura} agregada en PLL MULTIFACTURAS."

    return {
        "status_facturas":  status_facturas,
        "message_facturas": message_facturas,
        "status_pll":       status_pll,
        "message_pll":      message_pll,
        "spreadsheet_url":  spreadsheet_url,
    }