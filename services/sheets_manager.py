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

# ── Encabezados hoja Facturas (estructura original del cliente) ───────────────
HEADERS_FACTURAS = [
    "no. fact",            # A
    "Proveedor",           # B
    "Servicio",            # C
    "Codigo Articulo",     # D - vacío
    "Concepto Articulo",   # E - vacío
    "Periodo Facturacion", # F
    "Fecha de la factura", # G
    "Monto Fact en BS.",   # H
    "CeCos 2026",          # I - vacío
    "ID-Borrador",         # J - vacío
    "ID=OC 26000000",      # K - vacío
    "Columna1",            # L - vacío
    "al 87%",              # M  ← monto_total * 0.87
    "Tipo de Pago",        # N - vacío
]

# Fila 1: nombres técnicos
HEADERS_PLL_ROW1 = [
    "DocNum","DocEntry","ItemCode","","DocDueDate","CardCode","NumAtCard",
    "","","","DocTotal","DocCurrency","CostingCode","","JournalMemo",
    "TaxDate","U_RAZSOC","U_NROAUTOR","U_FORMA_PAGO","U_NOMBRE_SOLICITANTE",
    "U_ADJ_DIRECTA","U_NROCONTRATOADENDA","U_NROPAGOCONTRACTUAL",
    "U_FECHAINICIO","U_FECHAFIN","U_PERIODO","U_NRODEFACTURA",
    "U_INMUEBLE","U_Nro_cuenta","U_Nombre_banco","U_B_cuf","Subtotal",
]

# Fila 2: nombres legibles en rojo
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
    "CUF/NRO AUTORIZACION","SUBTOTAL Bs.",
]

COL_FACTURAS_NRO = 1   # col A: no. fact
COL_PLL_DOCENTRY = 2   # col B: DocEntry
COL_PLL_NRO      = 7   # col G: NumAtCard
COL_PLL_CUF      = 18  # col R: U_NROAUTOR (CUF)
PLL_DATA_START   = 3   # datos desde fila 3 (filas 1 y 2 son headers)


# ── Utilidades ────────────────────────────────────────────────────────────────

def _col_letter(n):
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def _with_retry(fn, retries=3, delay=2):
    last_err = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    raise last_err


def _get_spreadsheet():
    creds_content = os.getenv("GOOGLE_CREDENTIALS_JSON_CONTENT")
    if creds_content:
        info  = json.loads(creds_content)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        path = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No se encontro '{path}'.")
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)

    if not SPREADSHEET_ID:
        raise ValueError("SPREADSHEET_ID vacia en .env")

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
    try:
        return spreadsheet.worksheet(SHEET_NAME_PLL)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(
            title=SHEET_NAME_PLL, rows=1000, cols=len(HEADERS_PLL_ROW1)
        )
        sheet.update("A1", [HEADERS_PLL_ROW1, HEADERS_PLL_ROW2])
        return sheet


# ── Conteo y posicionamiento ──────────────────────────────────────────────────

def _count_data_rows_pll(sheet) -> int:
    values = sheet.col_values(COL_PLL_NRO)
    return len([v for v in values[2:] if v.strip() != ""])


def _next_row_facturas(sheet) -> int:
    return len(sheet.col_values(COL_FACTURAS_NRO)) + 1


def _next_row_pll(sheet) -> int:
    values = sheet.col_values(COL_PLL_NRO)
    data   = [v for v in values[2:] if v.strip() != ""]
    return PLL_DATA_START + len(data)


# ── Construcción de filas ─────────────────────────────────────────────────────

def _build_row_facturas(invoice: InvoiceData) -> list:
    servicio = f"SERVICIO MOVIL - {invoice.plan} - {invoice.periodo_facturacion}".upper()
    return [
        invoice.nro_factura,                   # A  no. fact
        invoice.proveedor,                     # B  Proveedor
        servicio,                              # C  Servicio
        "",                                    # D  Codigo Articulo   — vacío
        "",                                    # E  Concepto Articulo — vacío
        invoice.periodo_facturacion,           # F  Periodo
        invoice.fecha_emision,                 # G  Fecha factura
        invoice.monto_total,                   # H  Monto Fact en BS.
        "",                                    # I  CeCos 2026        — vacío
        "",                                    # J  ID-Borrador       — vacío
        "",                                    # K  ID=OC 26000000    — vacío
        "",                                    # L  Columna1          — vacío
        round(invoice.monto_total * 0.87, 4),  # M  al 87%
        "",                                    # N  Tipo de Pago      — vacío
    ]


def _build_row_pll(invoice: InvoiceData, doc_entry: int) -> list:
    return [
        "",                              # A  DocNum            — vacío
        doc_entry,                       # B  DocEntry          ← autoincremental
        "", "", "", "",                  # C D E F              — vacíos
        invoice.nro_factura,             # G  NumAtCard         ← nro_factura
        invoice.subtotal,                # H  SUBTOTAL          ← subtotal
        "", "",                          # I J                  — vacíos
        invoice.monto_total,             # K  DocTotal          ← monto_total
        "", "", "",                      # L M N                — vacíos
        invoice.concepto,                # O  JournalMemo       ← concepto
        invoice.fecha_emision,           # P  TaxDate           ← fecha_emision
        invoice.razon_social_cliente,    # Q  U_RAZSOC          ← razon_social
        invoice.cod_autorizacion,        # R  U_NROAUTOR (CUF)  ← cod_autorizacion
        "", "", "",                      # S T U                — vacíos
        invoice.contrato,                # V  U_NROCONTRATO     ← contrato
        "", "", "",                      # W X Y                — vacíos
        invoice.periodo_facturacion,     # Z  U_PERIODO         ← periodo
        invoice.nro_factura,             # AA U_NRODEFACTURA    ← nro_factura (repetido)
        "", "", "",                      # AB AC AD             — vacíos
        invoice.cod_autorizacion,        # AE U_B_cuf           ← cod_autorizacion (repetido)
        invoice.subtotal,                # AF Subtotal Bs.      ← subtotal
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


# ── Limpieza de hojas ─────────────────────────────────────────────────────────

def clear_all_invoices() -> dict:
    """
    Elimina todos los registros de datos (no los headers) de ambas hojas:
      - Facturas: desde fila 2 hasta la última fila con datos
      - PLL MULTIFACTURAS: desde fila 3 hasta la última fila con datos
    Deja los headers intactos.
    """
    spreadsheet    = _with_retry(_get_spreadsheet)
    sheet_facturas = _get_or_create_sheet_facturas(spreadsheet)
    sheet_pll      = _get_or_create_sheet_pll(spreadsheet)

    cleared = {"facturas": 0, "pll": 0}

    # ── Limpiar hoja Facturas (desde fila 2) ─────────────────────────────────
    last_row_f = len(sheet_facturas.col_values(COL_FACTURAS_NRO))
    if last_row_f >= 2:
        end_col_f = _col_letter(len(HEADERS_FACTURAS))
        _with_retry(lambda: sheet_facturas.batch_clear(
            [f"A2:{end_col_f}{last_row_f}"]
        ))
        cleared["facturas"] = last_row_f - 1

    # ── Limpiar hoja PLL (desde fila 3) ──────────────────────────────────────
    col_g_vals = sheet_pll.col_values(COL_PLL_NRO)
    last_row_p = PLL_DATA_START + len([v for v in col_g_vals[2:] if v.strip() != ""]) - 1
    if last_row_p >= PLL_DATA_START:
        end_col_p = _col_letter(len(HEADERS_PLL_ROW1))
        _with_retry(lambda: sheet_pll.batch_clear(
            [f"A{PLL_DATA_START}:{end_col_p}{last_row_p}"]
        ))
        cleared["pll"] = last_row_p - PLL_DATA_START + 1

    return cleared


# ── API pública ───────────────────────────────────────────────────────────────

def get_pll_next_doc_entry() -> int:
    spreadsheet = _with_retry(_get_spreadsheet)
    sheet_pll   = _get_or_create_sheet_pll(spreadsheet)

    if _count_data_rows_pll(sheet_pll) == 0:
        return 1

    doc_entry_values = sheet_pll.col_values(COL_PLL_DOCENTRY)
    numbers = []
    for v in doc_entry_values[2:]:
        try:
            numbers.append(int(float(v)))
        except (ValueError, TypeError):
            pass

    return (max(numbers) + 1) if numbers else 1


def check_and_save_invoice(invoice: InvoiceData, pll_doc_entry: int) -> dict:
    """
    Hoja Facturas  → valida duplicado por nro_factura (col A).
    Hoja PLL       → valida duplicado por CUF (col R); si no hay CUF, por nro_factura (col G).
    Ambas hojas son independientes entre sí.
    """
    spreadsheet    = _with_retry(_get_spreadsheet)
    sheet_facturas = _get_or_create_sheet_facturas(spreadsheet)
    sheet_pll      = _get_or_create_sheet_pll(spreadsheet)

    spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"

    # ── Hoja Facturas ─────────────────────────────────────────────────────────
    existing_f = _with_retry(lambda: sheet_facturas.col_values(COL_FACTURAS_NRO))
    if invoice.nro_factura in existing_f:
        status_facturas  = "duplicate"
        message_facturas = f"Factura {invoice.nro_factura} ya existe en Facturas."
    else:
        _safe_append_facturas(sheet_facturas, _build_row_facturas(invoice))
        status_facturas  = "added"
        message_facturas = f"Factura {invoice.nro_factura} agregada en Facturas."

    # ── Hoja PLL ──────────────────────────────────────────────────────────────
    existing_cuf = _with_retry(lambda: sheet_pll.col_values(COL_PLL_CUF))

    if invoice.cod_autorizacion and invoice.cod_autorizacion in existing_cuf:
        status_pll  = "duplicate"
        message_pll = f"Factura {invoice.nro_factura} ya existe en PLL (CUF duplicado)."
    elif not invoice.cod_autorizacion:
        existing_nro = _with_retry(lambda: sheet_pll.col_values(COL_PLL_NRO))
        if invoice.nro_factura in existing_nro:
            status_pll  = "duplicate"
            message_pll = f"Factura {invoice.nro_factura} ya existe en PLL."
        else:
            _safe_append_pll(sheet_pll, _build_row_pll(invoice, pll_doc_entry))
            status_pll  = "added"
            message_pll = f"Factura {invoice.nro_factura} agregada en PLL."
    else:
        _safe_append_pll(sheet_pll, _build_row_pll(invoice, pll_doc_entry))
        status_pll  = "added"
        message_pll = f"Factura {invoice.nro_factura} agregada en PLL."

    return {
        "status_facturas":  status_facturas,
        "message_facturas": message_facturas,
        "status_pll":       status_pll,
        "message_pll":      message_pll,
        "spreadsheet_url":  spreadsheet_url,
    }