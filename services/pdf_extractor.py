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

    Estrategia dual para manejar los dos formatos de ENTEL:

    Formato A (mayoría): Empieza con "EMPRESA NACIONAL DE TELECOMUNICACIONES S. A."
    Formato B (ENTEL SAA/especiales): Empieza directamente con la dirección
      "CALLE FEDERICO ZUAZO Nro. 1771..." y tiene NIT: 1020703023 al lado.

    Para ambos formatos, el inicio real de una factura se detecta por la
    presencia de "NIT:" seguido del NIT del emisor (1020703023 o 1020255020)
    en los primeros 500 caracteres del bloque — esto distingue el encabezado
    real del bloque de resumen al pie que también repite esos datos.

    Adicionalmente maneja facturas de múltiples páginas (Pag. 1/2, Pag. 2/2)
    uniéndolas correctamente antes de dividir.
    """

    # Patrones que marcan el INICIO de una nueva factura
    # Cubre ENTEL formato estándar, ENTEL formato especial (SAA), y TIGO
    START_PATTERNS = [
        # ENTEL estándar: encabezado del emisor
        r'EMPRESA NACIONAL DE TELECOMUNICACIONES S\. A\.',
        # TIGO: encabezado del emisor
        r'TELEFONICA CELULAR DE BOLIVIA S\.A\.',
        # ENTEL especial (SAA): empieza con la dirección + NIT en misma sección
        # Detectamos por "NRO.FACTURA:\s*\d{6,7}\s*Pag\. 1" que solo ocurre en encabezado
        r'NRO\.FACTURA:\s*\d{4,7}\s*\nPag\. 1',
    ]

    combined = '|'.join(f'(?:{p})' for p in START_PATTERNS)
    pattern  = re.compile(combined, re.IGNORECASE)

    positions = [m.start() for m in pattern.finditer(text)]

    # Filtrar posiciones demasiado cercanas (< 300 chars) → misma factura
    filtered = []
    for pos in positions:
        if not filtered or (pos - filtered[-1]) > 300:
            filtered.append(pos)

    if len(filtered) <= 1:
        # Solo un bloque o patrón no detectado → devolver texto completo
        return [text] if text.strip() else []

    blocks = []
    for i, pos in enumerate(filtered):
        end   = filtered[i + 1] if i + 1 < len(filtered) else len(text)
        block = text[pos:end].strip()

        # Descartar fragmentos muy cortos (son bloques de resumen al pie)
        if len(block) > 200:
            blocks.append(block)

    return blocks if blocks else [text]