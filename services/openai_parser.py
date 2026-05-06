import json
import re
import os
from dotenv import load_dotenv
from openai import OpenAI
from models import InvoiceData

load_dotenv()

SYSTEM_PROMPT = """Eres un extractor de datos de facturas bolivianas de telecomunicaciones.
Recibes el texto de UNA sola factura. Puede ser de ENTEL o de TIGO.

Responde SOLO con JSON válido, sin backticks ni explicaciones.
Estructura EXACTA:
{
  "nro_factura": "",
  "nit_proveedor": "",
  "proveedor": "",
  "cod_autorizacion": "",
  "fecha_emision": "",
  "razon_social_cliente": "",
  "nit_cliente": "",
  "periodo_facturacion": "",
  "contrato": "",
  "plan": "",
  "subtotal": 0,
  "importe_base_credito_fiscal": 0,
  "monto_total": 0,
  "concepto": ""
}

=== REGLAS CAMPO POR CAMPO ===

nro_factura:
  Busca la etiqueta "NRO.FACTURA:" o "FACTURA NRO" o "NRO FACTURA".
  El número real de factura es un número de 6-7 dígitos como 2317618, 1542847, 1541885.
  Si ves dos números juntos como "1007017028\n2317618", el primero es el NIT del cliente
  (10 dígitos) y el segundo es el número de factura. Toma el SEGUNDO.
  NUNCA uses el NIT del cliente (1007017028) como número de factura.

nit_proveedor:
  NIT del EMISOR (quien emite la factura):
  ENTEL → 1020703023
  TIGO  → 1020255020

proveedor:
  ENTEL → "EMPRESA NACIONAL DE TELECOMUNICACIONES S. A."
  TIGO  → "TELEFONICA CELULAR DE BOLIVIA S.A."

cod_autorizacion:
  Busca "CODIGO DE AUTORIZACION", "Cod. Autorizacion" o "CUF:".
  Concatena TODAS las partes sin espacios ni saltos de línea.
  Ejemplo: "45D6DEA712790ADE4B035EDAA" + "C7A01E79548D16B495B20DDED" + "7ABAF74"
         = "45D6DEA712790ADE4B035EDAAC7A01E79548D16B495B20DDED7ABAF74"

fecha_emision:
  CRÍTICO: La fecha SIEMPRE debe estar en formato DD/MM/YYYY. Nunca devuelvas un número.
  Busca "FECHA DE EMISION:" — tiene hora AM/PM junto a ella.
  Extrae SOLO la parte DD/MM/YYYY. Ejemplo: "03/04/2026 04:02 AM" → "03/04/2026"
  NUNCA uses "FECHA DE CORTE TOTAL" ni "FECHA DE DISPOSICION".
  NUNCA devuelvas un número como 46115 o 46082 — eso es incorrecto.

razon_social_cliente:
  La empresa que RECIBE la factura.
  Busca "RAZON SOCIAL:" seguido del nombre de empresa.
  Resultado esperado: "LA BOLIVIANA CIACRUZ DE SEGUROS Y REASEGUROS S.A."
  NO uses direcciones físicas (ej: "LA PAZ - ZONA CENTRAL...") como razón social.

nit_cliente:
  NIT de quien recibe la factura → 1007017028

periodo_facturacion:
  El MES en MAYÚSCULAS del campo "PERIODO FACTURACION".
  "03/2026" o "03/2026" → "MARZO"
  Tabla: 01=ENERO 02=FEBRERO 03=MARZO 04=ABRIL 05=MAYO 06=JUNIO
         07=JULIO 08=AGOSTO 09=SEPTIEMBRE 10=OCTUBRE 11=NOVIEMBRE 12=DICIEMBRE

contrato:
  Busca "CONTRATO:" si aparece. Muchas facturas no lo tienen → "".

plan:
  Busca "PLAN:" y toma el texto hasta el siguiente salto o hasta "CANTIDAD DE LINEAS".
  NO incluyas "- CANTIDAD DE LINEAS: N" en el plan.
  Si el plan está vacío o no existe, usa el tipo de servicio principal (ej: "CORPORATIVO EXACTO").

subtotal:
  Busca "SUBTOTAL Bs." y toma el número. Decimal permitido.
  Si no aparece, usa el importe total facturado.

importe_base_credito_fiscal:
  Busca "IMPORTE BASE PARA CREDITO FISCAL Bs." o "IMPORTE BASE CREDITO FISCAL".
  Decimal permitido.

monto_total:
  ENTEL: busca "TOTAL ENTEL Bs.:" y toma el ÚLTIMO valor (monto final a pagar).
  TIGO:  busca "Monto Total a Pagar".
  Decimal permitido.

concepto:
  Construir como: "Servicio [marca] - [plan] - [periodo]"
  Ejemplos:
    "Servicio Entel - PBX ANTIGUO - MARZO"
    "Servicio Tigo - Internet Dedicado 7 - MARZO"
    "Servicio Entel - CORPORATIVO EXACTO - MARZO"

REGLA FINAL: Si un campo no existe usar "" o 0. No inventes datos."""


def _fix_date(value: str) -> str:
    """
    Corrige fechas que llegaron como número serial de Excel (ej: 46115)
    convirtiéndolas de vuelta a DD/MM/YYYY.
    También extrae solo la parte de fecha si viene con hora.
    """
    if not value:
        return value

    # Si es un número puro (serial de Excel) → convertir
    try:
        serial = float(value)
        if 40000 < serial < 55000:   # rango de fechas de Excel 2010-2050
            from datetime import date, timedelta
            # Excel epoch: 1 enero 1900 (con bug de año bisiesto 1900)
            dt = date(1899, 12, 30) + timedelta(days=int(serial))
            return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        pass

    # Si viene con hora (ej: "03/04/2026 04:02 AM") → extraer solo fecha
    match = re.match(r'(\d{1,2}/\d{1,2}/\d{4})', str(value))
    if match:
        return match.group(1)

    return value


def parse_invoice_with_gpt(text: str) -> InvoiceData:
    """Envía el texto de UNA factura a GPT y devuelve InvoiceData validado."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY no encontrada en el archivo .env")

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

    # Corrección defensiva de fechas antes de validar con Pydantic
    if "fecha_emision" in data:
        data["fecha_emision"] = _fix_date(str(data["fecha_emision"]))

    return InvoiceData(**data)