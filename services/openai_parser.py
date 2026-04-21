import json
import re
from openai import OpenAI
from models import InvoiceData

client = OpenAI()  # Usa OPENAI_API_KEY del entorno

SYSTEM_PROMPT = """Extrae los siguientes campos del texto de una factura de TIGO.
Responde SOLO con un JSON válido (sin backticks, sin explicaciones).
Estructura EXACTA:
{
  "nro_factura": "",
  "nit_proveedor": "1020255020",
  "proveedor": "TELEFONICA CELULAR DE BOLIVIA S.A.",
  "cod_autorizacion": "",
  "fecha_emision": "",
  "razon_social_cliente": "",
  "nit_cliente": "",
  "periodo_facturacion": "",
  "contrato": "",
  "plan": "",
  "importe_base_credito_fiscal": 0,
  "monto_total": 0,
  "concepto": ""
}

Reglas estrictas:
- fecha_emision en formato DD/MM/YYYY
- cod_autorizacion sin espacios ni saltos de línea
- importe_base_credito_fiscal y monto_total deben ser números enteros
- concepto = "Servicio Tigo - [Plan] - Contrato [numero]"
- Si un campo no existe usar "" o 0
- No inventar datos
- El texto puede estar desordenado o con saltos de línea, debes reconstruirlo antes de extraer"""


def parse_invoice_with_gpt(text: str) -> InvoiceData:
    """
    Envía el texto extraído del PDF a GPT-3.5-turbo y devuelve un objeto InvoiceData.
    """
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Texto de la factura:\n{text}"},
        ],
    )

    raw = response.choices[0].message.content.strip()

    # Limpieza defensiva: quitar backticks si GPT los incluyó igual
    raw = re.sub(r"```json|```", "", raw).strip()

    data = json.loads(raw)
    return InvoiceData(**data)
