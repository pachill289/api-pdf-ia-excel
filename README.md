# Invoice Processor API

API que reemplaza el flujo de Make.com para procesar facturas PDF de TIGO y registrarlas en Google Sheets.

## Stack (100% gratuito excepto OpenAI)

| Componente | Herramienta | Costo |
|---|---|---|
| Servidor web | FastAPI + Uvicorn | Gratis |
| Extracción PDF | PyMuPDF | Gratis |
| Parseo inteligente | GPT-3.5-turbo | ~$0.001 por factura |
| Google Sheets | gspread | Gratis |
| Deploy | Railway / Render / tu VPS | Gratis (tier gratuito) |

---

## Setup paso a paso

### 1. Clonar e instalar

```bash
pip install -r requirements.txt
```

### 2. Crear credenciales de Google (Service Account)

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un proyecto → **APIs & Services** → **Enable APIs**
3. Habilita **Google Sheets API** y **Google Drive API**
4. Ve a **Credentials** → **Create Credentials** → **Service Account**
5. Descarga el JSON y nómbralo `credentials.json` en la raíz del proyecto
6. **Comparte tu Google Sheet** con el email de la Service Account (termina en `@...gserviceaccount.com`) con rol **Editor**

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Edita .env con tus valores reales
```

### 4. Ejecutar localmente

```bash
uvicorn main:app --reload --port 8000
```

Visita `http://localhost:8000/docs` para probar la API con Swagger UI.

---

## Endpoints

### POST `/process-invoices` — múltiples PDFs (recomendado)

```bash
curl -X POST http://localhost:8000/process-invoices \
  -F "files=@factura1.pdf" \
  -F "files=@factura2.pdf"
```

**Respuesta:**
```json
[
  {
    "status": "added",
    "nro_factura": "12345678",
    "message": "Factura 12345678 agregada correctamente.",
    "spreadsheet_url": "https://docs.google.com/spreadsheets/d/...",
    "invoice_data": { ... }
  }
]
```

### POST `/process-invoice-raw` — bytes crudos (compatible con Make)

Igual a tu endpoint `/extract-text` actual pero hace todo el flujo completo.

```bash
curl -X POST http://localhost:8000/process-invoice-raw \
  --data-binary @factura.pdf \
  -H "Content-Type: application/pdf"
```

---

## Deploy gratuito en Railway

```bash
# 1. Instala Railway CLI
npm install -g @railway/cli

# 2. Login y deploy
railway login
railway init
railway up

# 3. Configura las variables de entorno en el dashboard de Railway
# 4. Sube credentials.json como variable GOOGLE_CREDENTIALS_JSON_CONTENT
#    y ajusta el código para leer desde variable de entorno si necesitas
```

## Deploy gratuito en Render

1. Crea cuenta en [render.com](https://render.com)
2. Conecta tu repositorio de GitHub
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Agrega las variables de entorno en el dashboard

---

## Diferencias con el flujo de Make

| Make | Esta API |
|---|---|
| Webhook → recibe PDF | POST /process-invoices |
| Iterator | Loop interno sobre `files` |
| HTTP → /extract-text | `extract_text_from_bytes()` |
| HTTP → OpenAI | `parse_invoice_with_gpt()` |
| JSON parser | Incluido en el parser |
| Google Sheets (buscar) | `check_and_save_invoice()` |
| Router (¿existe?) | Lógica if/else en sheets_manager |
| Webhook response | JSON response del endpoint |
