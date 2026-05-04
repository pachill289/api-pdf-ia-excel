from pydantic import BaseModel
from typing import Optional

class InvoiceData(BaseModel):
    nro_factura: str = ""
    nit_proveedor: str = ""
    proveedor: str = ""
    cod_autorizacion: str = ""
    fecha_emision: str = ""
    razon_social_cliente: str = ""
    nit_cliente: str = ""
    periodo_facturacion: str = ""
    contrato: str = ""
    plan: str = ""
    subtotal: float = 0          # nuevo
    importe_base_credito_fiscal: float = 0
    monto_total: float = 0
    concepto: str = ""

class ProcessResult(BaseModel):
    status: str
    nro_factura: str
    filename: Optional[str] = None
    message: str
    spreadsheet_url: Optional[str] = None
    invoice_data: Optional[InvoiceData] = None
    status_facturas:  Optional[str] = None
    message_facturas: Optional[str] = None
    status_pll:       Optional[str] = None
    message_pll:      Optional[str] = None