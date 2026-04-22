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

HEADERS_PLL = [
    "DocNum",               # A  - vacío
    "DocEntry",             # B  ← autoincremental
    "ItemCode",             # C
    "",                     # D
    "DocDueDate",           # E
    "CardCode",             # F
    "NumAtCard",            # G  ← nro_factura
    "",                     # H
    "",                     # I
    "",                     # J
    "DocTotal",             # K  ← monto_total
    "DocCurrency",          # L
    "CostingCode",          # M
    "",                     # N
    "JournalMemo",          # O  ← concepto
    "TaxDate",              # P  ← fecha_emision
    "U_RAZSOC",             # Q  ← razon_social_cliente
    "U_NROAUTOR",           # R  ← cod_autorizacion
    "U_FORMA_PAGO",         # S
    "U_NOMBRE_SOLICITANTE", # T
    "U_ADJ_DIRECTA",        # U
    "U_NROCONTRATOADENDA",  # V  ← contrato
    "U_NROPAGOCONTRACTUAL", # W
    "U_FECHAINICIO",        # X
    "U_FECHAFIN",           # Y
    "U_PERIODO",            # Z  ← periodo_facturacion
    "U_NRODEFACTURA",       # AA ← nro_factura (repetido)
    "U_INMUEBLE",           # AB
    "U_Nro_cuenta",         # AC
    "U_Nombre_banco",       # AD
    "U_B_cuf",              # AE ← cod_autorizacion (repetido)
]

# Índices de columna (1-based) usados para búsquedas
COL_FACTURAS_NRO = 1   # columna A: no. fact
COL_PLL_DOCENTRY = 2   # columna B: DocEntry (autoincremental)
COL_PLL_NRO      = 7   # columna G: NumAtCard = nro_factura


def _get_spreadsheet():
    creds_content = os.getenv("GOOGLE_CREDENTIALS_JSON_CONTENT")
    if creds_content:
        info = json.loads(creds_content)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
        if not os.path.exists(credentials_path):
            raise FileNotFoundError(
                f"No se encontro '{credentials_path}'.\n"
                "Descarga el JSON de tu Service Account y colocalo en la raiz del proyecto."
            )
        creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)

    if not SPREADSHEET_ID:
        raise ValueError("La variable SPREADSHEET_ID esta vacia. Agregala en tu .env")

    gc = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID)


def _get_or_create_sheet(spreadsheet, name, headers):
    try:
        return spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=name, rows=1000, cols=len(headers))
        sheet.update("A1", [headers])
        return sheet


def _col_letter(n):
    """Convierte número de columna 1-based a letra(s) Excel."""
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def _next_row_by_col(sheet, col_index):
    """
    Devuelve el número de la próxima fila vacía basándose en la columna indicada.
    Usa la columna que SIEMPRE tiene datos en esa hoja para contar correctamente.
    """
    values = sheet.col_values(col_index)  # incluye el header en [0]
    return len(values) + 1


def _count_data_rows_pll(sheet):
    """
    Cuenta cuántas filas de datos (sin contar el header) hay en PLL MULTIFACTURAS
    usando la columna G (NumAtCard = nro_factura), que siempre se rellena.
    Si la columna G solo tiene el header o está vacía → 0 registros.
    """
    values = sheet.col_values(COL_PLL_NRO)  # col G
    # values[0] es el header "NumAtCard", el resto son datos
    data_rows = [v for v in values[1:] if v.strip() != ""]
    return len(data_rows)


def _safe_append_facturas(sheet, row):
    """Inserta en hoja Facturas usando columna A (no. fact) como referencia."""
    next_row = _next_row_by_col(sheet, COL_FACTURAS_NRO)
    end_col  = _col_letter(len(row))
    sheet.update(f"A{next_row}:{end_col}{next_row}", [row], value_input_option="USER_ENTERED")


def _safe_append_pll(sheet, row):
    """
    Inserta en hoja PLL MULTIFACTURAS usando columna G (NumAtCard) como referencia,
    ya que la columna A (DocNum) siempre está vacía.
    """
    next_row = _next_row_by_col(sheet, COL_PLL_NRO)
    end_col  = _col_letter(len(row))
    sheet.update(f"A{next_row}:{end_col}{next_row}", [row], value_input_option="USER_ENTERED")


def _build_row_facturas(invoice: InvoiceData) -> list:
    servicio = f"SERVICIO MOVIL - {invoice.plan} - {invoice.periodo_facturacion}".upper()
    return [
        invoice.nro_factura,                  # A
        invoice.proveedor,                    # B
        servicio,                             # C
        "",                                   # D
        "",                                   # E
        invoice.periodo_facturacion,          # F
        invoice.fecha_emision,                # G
        invoice.monto_total,                  # H
        "",                                   # I
        "",                                   # J
        "",                                   # K
        "",                                   # L
        invoice.monto_total * 0.87,           # M
        "",                                   # N
    ]


def _build_row_pll(invoice: InvoiceData, doc_entry: int) -> list:
    return [
        "",                                   # A  DocNum          — vacío
        doc_entry,                            # B  DocEntry        ← autoincremental
        "",                                   # C  ItemCode        — vacío
        "",                                   # D                  — vacío
        "",                                   # E  DocDueDate      — vacío
        "",                                   # F  CardCode        — vacío
        invoice.nro_factura,                  # G  NumAtCard       ← nro_factura
        "",                                   # H                  — vacío
        "",                                   # I                  — vacío
        "",                                   # J                  — vacío
        invoice.monto_total,                  # K  DocTotal        ← monto_total
        "",                                   # L  DocCurrency     — vacío
        "",                                   # M  CostingCode     — vacío
        "",                                   # N                  — vacío
        invoice.concepto,                     # O  JournalMemo     ← concepto
        invoice.fecha_emision,                # P  TaxDate         ← fecha_emision
        invoice.razon_social_cliente,         # Q  U_RAZSOC        ← razon_social_cliente
        invoice.cod_autorizacion,             # R  U_NROAUTOR      ← cod_autorizacion
        "",                                   # S  U_FORMA_PAGO    — vacío
        "",                                   # T  U_NOMBRE_SOL.   — vacío
        "",                                   # U  U_ADJ_DIRECTA   — vacío
        invoice.contrato,                     # V  U_NROCONTRATO   ← contrato
        "",                                   # W  U_NROPAGO       — vacío
        "",                                   # X  U_FECHAINICIO   — vacío
        "",                                   # Y  U_FECHAFIN      — vacío
        invoice.periodo_facturacion,          # Z  U_PERIODO       ← periodo_facturacion
        invoice.nro_factura,                  # AA U_NRODEFACTURA  ← nro_factura (repetido)
        "",                                   # AB U_INMUEBLE      — vacío
        "",                                   # AC U_Nro_cuenta    — vacío
        "",                                   # AD U_Nombre_banco  — vacío
        invoice.cod_autorizacion,             # AE U_B_cuf         ← cod_autorizacion (repetido)
    ]


def check_and_save_invoice(invoice: InvoiceData, pll_doc_entry: int) -> dict:
    """
    Inserta la factura en cada hoja con validación INDEPENDIENTE.

    Hoja 'Facturas'         → verifica duplicado en col A (no. fact)
    Hoja 'PLL MULTIFACTURAS' → verifica duplicado en col G (NumAtCard)

    pll_doc_entry: número de secuencia ya calculado externamente para esta factura.
    """
    spreadsheet = _get_spreadsheet()

    sheet_facturas = _get_or_create_sheet(spreadsheet, SHEET_NAME,     HEADERS_FACTURAS)
    sheet_pll      = _get_or_create_sheet(spreadsheet, SHEET_NAME_PLL, HEADERS_PLL)

    spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"

    # ── Hoja Facturas ─────────────────────────────────────────────────────────
    existing_facturas = sheet_facturas.col_values(COL_FACTURAS_NRO)
    if invoice.nro_factura in existing_facturas:
        status_facturas  = "duplicate"
        message_facturas = f"Factura {invoice.nro_factura} ya existe en Facturas."
    else:
        _safe_append_facturas(sheet_facturas, _build_row_facturas(invoice))
        status_facturas  = "added"
        message_facturas = f"Factura {invoice.nro_factura} agregada en Facturas."

    # ── Hoja PLL MULTIFACTURAS ────────────────────────────────────────────────
    existing_pll = sheet_pll.col_values(COL_PLL_NRO)  # col G: NumAtCard
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


def get_pll_next_doc_entry() -> int:
    """
    Calcula el próximo DocEntry para la hoja PLL MULTIFACTURAS.
    - Si no hay registros (hoja vacía o recién limpiada) → empieza desde 1.
    - Si hay registros → toma el máximo DocEntry existente + 1.
    Esto permite al cliente limpiar la hoja y reiniciar la secuencia.
    """
    spreadsheet = _get_spreadsheet()
    sheet_pll   = _get_or_create_sheet(spreadsheet, SHEET_NAME_PLL, HEADERS_PLL)

    data_count = _count_data_rows_pll(sheet_pll)
    if data_count == 0:
        return 1  # hoja vacía o recién limpiada → resetear secuencia

    # Leer col B (DocEntry) para encontrar el máximo actual
    doc_entry_values = sheet_pll.col_values(COL_PLL_DOCENTRY)
    # doc_entry_values[0] = "DocEntry" (header), el resto son números o vacíos
    numbers = []
    for v in doc_entry_values[1:]:
        try:
            numbers.append(int(float(v)))
        except (ValueError, TypeError):
            pass

    return (max(numbers) + 1) if numbers else 1