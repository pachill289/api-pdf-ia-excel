import json
import re
import os
from dotenv import load_dotenv
from openai import OpenAI
from models import InvoiceData

load_dotenv()

SYSTEM_PROMPT = """Extrae los siguientes campos del texto de una factura de TIGO.
Responde SOLO con un JSON valido (sin backticks, sin explicaciones).
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
- nro_factura: numero que aparece junto a "Nro Factura:" o "Nro. Factura"
- cod_autorizacion: valor junto a "Cod. Autorizacion" o "Cód. Autorización", sin espacios ni saltos de linea, concatenar si aparece en varias lineas
- fecha_emision: extraer de "Lugar y Fecha de Emision", formato DD/MM/YYYY (solo la fecha, ignorar la hora)
- razon_social_cliente: valor de "Nombre o Razon Social" — puede ser una o dos lineas, unir en una sola
- nit_cliente: valor de "NIT / CI / CEX"
- periodo_facturacion: extraer el MES en español del campo "Periodo de Facturacion" (ej: "01/03/2026 a 31/03/2026" → "MARZO")
- contrato: numero junto a "Contrato:"
- plan: valor junto a "Plan:"
- importe_base_credito_fiscal: numero junto a "Importe Base Credito Fiscal", debe ser entero
- monto_total: numero junto a "Monto Total a Pagar", debe ser entero
- concepto: construir como "Servicio Tigo - [plan] - Contrato [contrato]"
- Si un campo no existe usar "" o 0
- No inventar datos
- El texto puede estar desordenado o con saltos de linea, reconstruirlo antes de extraer

Texto de la factura:"""


def parse_invoice_with_gpt(text: str) -> InvoiceData:
    """
    Envia el texto del PDF a GPT-3.5-turbo y devuelve un InvoiceData validado.
    El cliente se instancia dentro de la funcion para garantizar que
    load_dotenv() ya ejecuto antes de leer OPENAI_API_KEY.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY no encontrada. "
            "Asegurate de tenerla en tu archivo .env"
        )

    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": text},
        ],
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"```json|```", "", raw).strip()

    data = json.loads(raw)
    return InvoiceData(**data)
