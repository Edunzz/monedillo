import os
import json
import logging
from fastapi import FastAPI, Request, Query
from pymongo import MongoClient
from datetime import datetime
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from dateutil import parser
from dotenv import load_dotenv
import certifi
import httpx

load_dotenv()

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# === Variables de entorno ===
TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL")

# === Categorías válidas ===
CATEGORIAS_VALIDAS = [
    "salud", "limpieza", "alimentacion", "transporte",
    "salidas", "ropa", "plantas", "arreglos casa", "vacaciones"
]

# === MongoDB ===
mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = mongo_client["telegram_gastos"]
movimientos = db["movimientos"]

# === Procesamiento con modelo ===
def procesar_con_openrouter(texto_usuario: str):
    prompt = f"""
Extrae el tipo, monto y la categoría desde el siguiente texto con las siguientes indicaciones. 
El tipo siempre debe ser gasto por defecto a menos que el texto indica que se debe agregar (o cualquier sinonimo de adicionar).
El monto siempre debe positivo
La categoría debe estar dentro del siguiente listado: salud, limpieza, alimentacion, transporte, salidas, ropa, plantas, arreglos casa, vacaciones. Nota: Si se recibe una palabra con errores ortográficos o con tilde (por ejemplo, alimentación), esta debe normalizarse eliminando las tildes y considerarse como alimentacion, a fin de coincidir con las categorías predefinidas. El objetivo es asegurar una correcta categorización aunque la palabra no esté escrita con exactitud ortográfica.

Devuelve solo un JSON con las claves: "tipo" (texto gasto o ingreso), "monto" (número), "categoria" (texto exacto del listado) y . Nada más.
Texto: "{texto_usuario}"
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tubot.com"
    }

    body = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=30
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        logger.exception("❌ Error en OpenRouter:")
        return {"error": str(e), "raw": content if 'content' in locals() else ""}

# === Guardar en Mongo ===
def guardar_movimiento(chat_id, tipo, monto, categoria, mensaje_original):
    movimientos.insert_one({
        "chat_id": chat_id,
        "tipo": tipo,
        "monto": monto,
        "categoria": categoria,
        "mensaje_original": mensaje_original,
        "fecha": datetime.utcnow()
    })
    logger.info(f"💾 Guardado: {tipo} S/ {monto} en {categoria} ({chat_id})")

def obtener_saldo(categoria, chat_id):
    pipeline = [
        {"$match": {"chat_id": chat_id, "categoria": categoria}},
        {"$group": {"_id": "$tipo", "total": {"$sum": "$monto"}}}
    ]
    result = list(movimientos.aggregate(pipeline))
    ingresos = sum(r["total"] for r in result if r["_id"] == "ingreso")
    gastos = sum(r["total"] for r in result if r["_id"] == "gasto")
    return ingresos - gastos

def obtener_reporte_general(chat_id):
    pipeline = [
        {"$match": {"chat_id": chat_id}},
        {"$group": {"_id": {"categoria": "$categoria", "tipo": "$tipo"}, "total": {"$sum": "$monto"}}}
    ]
    result = list(movimientos.aggregate(pipeline))
    saldos = {}
    for r in result:
        cat = r["_id"]["categoria"]
        tipo = r["_id"]["tipo"]
        saldos.setdefault(cat, {"ingreso": 0, "gasto": 0})
        saldos[cat][tipo] += r["total"]

    mensaje = "📊 *Reporte general de categorías:*\n"
    for cat, vals in saldos.items():
        saldo = vals["ingreso"] - vals["gasto"]
        mensaje += f"• {cat}: S/ {saldo:.2f}\n"

    mensaje += f"\n[📄 Ver reporte en Google Sheets]({GOOGLE_SHEET_URL})"
    return mensaje

# === Rutas ===
@app.get("/")
async def root():
    return {"message": "Bot activo con MongoDB y OpenRouter ✅"}

@app.post(f"/{TOKEN}")
async def telegram_webhook(req: Request):
    try:
        body = await req.json()
        logger.info(f"📩 Mensaje recibido: {body}")

        chat_id = body["message"]["chat"]["id"]
        text = body["message"].get("text", "").strip()

        if not text:
            return {"ok": True}

        if text.lower() in ["reporte", "reporte general", "todo"]:
            msg = obtener_reporte_general(chat_id)
        elif text.lower().startswith("reporte de "):
            categoria = text.lower().replace("reporte de ", "").strip()
            if categoria not in CATEGORIAS_VALIDAS:
                msg = f"❌ Categoría inválida. Usa:\n" + "\n".join(f"- {c}" for c in CATEGORIAS_VALIDAS)
            else:
                saldo = obtener_saldo(categoria, chat_id)
                msg = (
                    f"💼 *Saldo en '{categoria}':*\n"
                    f"S/ {saldo:.2f}\n"
                    f"\n[📄 Ver reporte en Google Sheets]({GOOGLE_SHEET_URL})"
                )
        else:
            resultado = procesar_con_openrouter(text)
            if "error" in resultado or resultado.get("categoria") not in CATEGORIAS_VALIDAS:
                msg = (
                    "⚠️ No pude interpretar tu mensaje.\n"
                    "Ejemplo: 'gasté 30 en transporte' o 'ahorré 50 para salud'\n"
                    "Categorías válidas:\n" + "\n".join(f"- {c}" for c in CATEGORIAS_VALIDAS)
                )
            else:
                monto = resultado["monto"]
                categoria = resultado["categoria"]
                tipo = resultado["tipo"]
                guardar_movimiento(chat_id, tipo, abs(monto), categoria, text)
                saldo = obtener_saldo(categoria, chat_id)
                msg = (
                    f"✅ {tipo.title()} de S/ {abs(monto):.2f} registrado en '{categoria}'.\n"
                    f"💰 Saldo actual: S/ {saldo:.2f}\n"
                    f"\n[📄 Ver reporte en Google Sheets]({GOOGLE_SHEET_URL})"
                )

        httpx.post(f"{BASE_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        })
        return {"ok": True}

    except Exception as e:
        logger.exception("❌ Error inesperado:")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/exportar")
async def exportar_data(clave: str = Query(...), desde: str = None, hasta: str = None):
    CLAVE_CORRECTA = os.getenv("EXPORT_PASS", "0000")
    if clave != CLAVE_CORRECTA:
        return JSONResponse(status_code=401, content={"error": "No autorizado"})

    query = {}
    if desde or hasta:
        try:
            desde_dt = parser.parse(desde) if desde else datetime.min
            hasta_dt = parser.parse(hasta) if hasta else datetime.max
            query["fecha"] = {"$gte": desde_dt, "$lte": hasta_dt}
        except Exception:
            return JSONResponse(status_code=400, content={"error": "Formato de fecha inválido. Usa YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS"})

    docs = list(movimientos.find(query, {"_id": 0}))
    for doc in docs:
        if "fecha" in doc and isinstance(doc["fecha"], datetime):
            doc["fecha"] = doc["fecha"].strftime("%Y-%m-%d %H:%M:%S")

    return JSONResponse(content=jsonable_encoder(docs))
