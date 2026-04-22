from pydantic import BaseModel
from typing import Optional

class InvoiceData(BaseModel):
    nro_factura: str = ""
    nit_proveedor: str = "1020255020"
    proveedor: str = "TELEFONICA CELULAR DE BOLIVIA S.A."
    cod_autorizacion: str = ""
    fecha_emision: str = ""
    razon_social_cliente: str = ""
    nit_cliente: str = ""
    periodo_facturacion: str = ""
    contrato: str = ""
    plan: str = ""
    importe_base_credito_fiscal: int = 0
    monto_total: int = 0
    concepto: str = ""

class ProcessResult(BaseModel):
    # Estado global (para compatibilidad con el frontend)
    status: str                         # "added" | "duplicate" | "error"
    nro_factura: str
    message: str
    spreadsheet_url: Optional[str] = None
    invoice_data: Optional[InvoiceData] = None
    # Estado individual por hoja
    status_facturas:  Optional[str] = None
    message_facturas: Optional[str] = None
    status_pll:       Optional[str] = None
    message_pll:      Optional[str] = None