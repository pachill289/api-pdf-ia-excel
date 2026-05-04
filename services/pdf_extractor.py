import re
import fitz  # PyMuPDF


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """Extrae todo el texto de un PDF concatenando todas las páginas."""
    doc  = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text.strip()


def split_invoices_from_text(text: str) -> list[str]:
    """
    Divide el texto de un PDF multi-factura en bloques individuales.

    Estrategia para ENTEL:
      Cada factura ENTEL comienza con la cabecera del emisor
      "EMPRESA NACIONAL DE TELECOMUNICACIONES S. A."
      o con "TELEFONICA CELULAR" para TIGO.
      Los bloques de resumen al pie ("NRO.FACTURA: \\n1007017028\\n2317618")
      NO son el inicio de una factura — son el cierre de la anterior.

    Se divide POR EL ENCABEZADO DEL EMISOR, no por NRO.FACTURA,
    para evitar confundir el resumen al pie con una nueva factura.
    """

    # Marcadores que indican el INICIO real de una nueva factura
    # (encabezado del emisor, no del resumen al pie)
    header_pattern = re.compile(
        r'(?='
        r'(?:EMPRESA NACIONAL DE TELECOMUNICACIONES|'
        r'TELEFONICA CELULAR DE BOLIVIA|'
        r'Nro Factura:\s*\d+)'   # TIGO comienza con Nro Factura en encabezado
        r')',
        re.IGNORECASE
    )

    positions = [m.start() for m in header_pattern.finditer(text)]

    # Filtrar posiciones muy cercanas (< 200 chars) que son falsas coincidencias
    # como la firma al pie que repite el nombre del emisor
    filtered = []
    for pos in positions:
        if not filtered or (pos - filtered[-1]) > 200:
            filtered.append(pos)

    if len(filtered) <= 1:
        return [text]

    blocks = []
    for i, pos in enumerate(filtered):
        end   = filtered[i + 1] if i + 1 < len(filtered) else len(text)
        block = text[pos:end].strip()
        if len(block) > 100:   # descartar fragmentos demasiado cortos
            blocks.append(block)

    return blocks if blocks else [text]