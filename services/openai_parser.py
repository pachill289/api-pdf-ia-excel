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
  ENTEL: Busca la línea que dice exactamente "FACTURA NRO:" (en el encabezado superior).
         El número de factura es el que aparece en esa misma línea o inmediatamente después.
         Ejemplos reales: 2317618, 2319711, 1542847, 2318913.
         NUNCA uses el NIT del cliente (1007017028) como número de factura.
         NUNCA uses los códigos de servicio (31978, 31958, 31982, etc.) como número de factura.
         Si el texto tiene "NRO.FACTURA:" seguido de dos números en líneas separadas
         (primero el NIT del cliente, luego el número real), toma el SEGUNDO número (el más corto).
  TIGO:  Busca "Nro Factura:" en el encabezado y toma el número que le sigue.

nit_proveedor:
  Es el NIT del EMISOR (quien emite la factura):
  ENTEL → "1020703023"
  TIGO  → "1020255020"

proveedor:
  ENTEL → "EMPRESA NACIONAL DE TELECOMUNICACIONES S. A."
  TIGO  → "TELEFONICA CELULAR DE BOLIVIA S.A."

cod_autorizacion:
  Busca "CODIGO DE AUTORIZACION" o "Cod. Autorizacion" o "CUF:".
  Concatena TODAS las partes sin espacios ni saltos de línea.
  Ejemplo: "45D6DEA712790ADE4B035EDAA" + "C7A01E79548D16B495B20DDED" + "7ABAF74"
         → "45D6DEA712790ADE4B035EDAAC7A01E79548D16B495B20DDED7ABAF74"

fecha_emision:
  ENTEL: Busca la etiqueta "FECHA DE EMISION:" (tiene hora AM/PM).
         Extrae SOLO la parte DD/MM/YYYY. Ejemplo: "03/04/2026 04:02 AM" → "03/04/2026"
  TIGO:  Busca "Lugar y Fecha de Emision:" → extrae solo DD/MM/YYYY.
  NUNCA uses "FECHA DE CORTE TOTAL" ni "FECHA DE DISPOSICION".

razon_social_cliente:
  Es la empresa que RECIBE la factura (el cliente).
  ENTEL: Busca "RAZON SOCIAL:" seguido del nombre de la empresa cliente.
         El resultado esperado es: "LA BOLIVIANA CIACRUZ DE SEGUROS Y REASEGUROS S.A."
         NO uses la dirección (ej: "LA PAZ - ZONA CENTRAL...") como razón social.
  TIGO:  Busca "Nombre o Razon Social:".

nit_cliente:
  NIT de quien recibe la factura. ENTEL y TIGO: 1007017028

periodo_facturacion:
  Extrae el MES en español MAYÚSCULAS del campo periodo.
  "03/2026" o "01/03/2026 a 31/03/2026" → "MARZO"
  Tabla: 01=ENERO 02=FEBRERO 03=MARZO 04=ABRIL 05=MAYO 06=JUNIO
         07=JULIO 08=AGOSTO 09=SEPTIEMBRE 10=OCTUBRE 11=NOVIEMBRE 12=DICIEMBRE

contrato:
  ENTEL: Busca "CONTRATO:" si aparece. Muchas facturas no tienen contrato → "".
  TIGO:  Busca "Contrato:".

plan:
  ENTEL: Busca "PLAN:" y toma el texto hasta el siguiente salto de línea.
         Ejemplos: "PBX ANTIGUO", "LINEA ENTEL LOCAL", "FIBRA HOGAR NUEVO".
         Si hay "CANTIDAD DE LINEAS:" NO lo incluyas en el plan.
  TIGO:  Busca "Plan:".

subtotal:
  Busca "SUBTOTAL Bs." y toma el número. Número con decimales permitido.

importe_base_credito_fiscal:
  ENTEL: "IMPORTE BASE PARA CREDITO FISCAL Bs."
  TIGO:  "Importe Base Credito Fiscal"
  Número con decimales permitido.

monto_total:
  ENTEL: "TOTAL ENTEL Bs.:" — toma el último valor (el monto final a pagar).
  TIGO:  "Monto Total a Pagar"
  Número con decimales permitido.

concepto:
  Construir como: "Servicio [marca] - [plan] - [periodo]"
  Ejemplos:
    "Servicio Entel - PBX ANTIGUO - MARZO"
    "Servicio Tigo - Internet Dedicado 7 - MARZO"

REGLA FINAL: Si un campo no existe usar "" o 0. No inventes datos."""


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
    return InvoiceData(**data)