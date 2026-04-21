import fitz  # PyMuPDF


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """
    Recibe bytes de un PDF y devuelve el texto concatenado de todas las páginas.
    Replica exactamente la lógica del nodo HTTP de Make.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text.strip()
