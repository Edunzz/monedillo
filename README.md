# Monedillo — Finanzas de bolsillo
Telemetría de tu plata 📊💸

```text

███╗░░░███╗░█████╗░███╗░░██╗███████╗██████╗░██╗██╗░░░░░██╗░░░░░░█████╗░
████╗░████║██╔══██╗████╗░██║██╔════╝██╔══██╗██║██║░░░░░██║░░░░░██╔══██╗
██╔████╔██║██║░░██║██╔██╗██║█████╗░░██║░░██║██║██║░░░░░██║░░░░░██║░░██║
██║╚██╔╝██║██║░░██║██║╚████║██╔══╝░░██║░░██║██║██║░░░░░██║░░░░░██║░░██║
██║░╚═╝░██║╚█████╔╝██║░╚███║███████╗██████╔╝██║███████╗███████╗╚█████╔╝
╚═╝░░░░░╚═╝░╚════╝░╚═╝░░╚══╝╚══════╝╚═════╝░╚═╝╚══════╝╚══════╝░╚════╝░

                      M  O  N  E  D  I  L  L  O
            Observabilidad “just for fun” de finanzas personales
```

**Monedillo** es un bot de Telegram que usa **IA** para interpretar mensajes en lenguaje natural
y registrar **gastos** / **ingresos**, generar **reportes** y compartirlos en **grupos** (multi-sala).
Construido con **FastAPI**, **MongoDB Atlas** y **OpenRouter**; listo para desplegar en **Render** (y alternativas).

---

## ✨ ¿Qué hace Monedillo?

- Entiende tu texto libre (ej. `gasté 25 en transporte`) y lo convierte en datos estructurados.
- Soporta **tipos**: `gasto`, `ingreso`, `reporte`, `info`, `eliminar`.
- **Multi-grupo**: crea un grupo (`crear Familia`) o únete por código (`unir ABC123`) para compartir gastos sin mezclar.
- **Reportes**: por categoría o general del grupo.
- **Exportación**: endpoint `/exportar` para descargar movimientos en **JSON** (con filtros por fecha y grupo).

> Claim sugerido: **“Monedillo: Telemetría de tu plata”**

---

## 🧠 Cómo funciona (alto nivel)

1. Telegram envía tus mensajes al **webhook**: `POST /<BOT_TOKEN>`.
2. Monedillo usa **OpenRouter** (modelo por defecto `mistralai/mistral-7b-instruct`) para extraer un JSON:
   ```json
   {"tipo": "gasto", "monto": 25, "categoria": "transporte"}
   ```
3. Guarda movimientos en **MongoDB** particionando por `group_code`.
4. Calcula saldos y genera mensajes claros (incluye el `ID` del movimiento para poder eliminar).
5. Permite **exportar** datos con `GET /exportar`.

**Categorías válidas** (según el código actual):
```
salud, limpieza, alimentacion, transporte, salidas, ropa, plantas, arreglos casa, vacaciones
```

---

## 🧩 Arquitectura (resumen)

- **FastAPI**: API + webhook (`/<BOT_TOKEN>`), rutas `/` (salud) y `/exportar` (JSON).
- **MongoDB Atlas** (DB: `telegram_gastos`):
  - `usuarios`: `{ chat_id, group_code, pending, created_at }`
  - `grupos`: `{ code, name, owner_chat_id, members[], created_at }`
  - `movimientos`: `{ chat_id, group_code, tipo, monto, categoria, mensaje_original, fecha }`
- **OpenRouter**: interpreta texto → `{tipo, monto, categoria}`.

**Índices** (performance):  
- `movimientos`: `(group_code, categoria, tipo, fecha)`, `(group_code, fecha)`  
- `usuarios`: `chat_id` (único)  
- `grupos`: `code` (único)

---

## 🔐 Variables de entorno

Crea un `.env` local o configúralas en tu plataforma de despliegue:

```env
# Telegram
BOT_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# MongoDB Atlas
MONGO_URI=mongodb+srv://usuario:pass@cluster/url?retryWrites=true&w=majority

# OpenRouter
OPENROUTER_API_KEY=or-xxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_MODEL=mistralai/mistral-7b-instruct   # opcional (default)

# Opcionales
GROUP_CODE_LENGTH=6          # largo del código de grupo
EXPORT_PASS=0000             # clave requerida por /exportar
```

> **Atlas tip**: agrega IPs salientes de tu plataforma (o `0.0.0.0/0` durante desarrollo), para ponerlo a funcionar pon el rango de tu ip donde corra tu app. Usa un usuario con permisos mínimos.

---

## 🧪 Uso (Telegram)

1) Crea o configura tu bot con **@BotFather** → copia tu **BOT_TOKEN**.  
2) En tu chat con Monedillo:
- `crear Familia` → genera `group_code` (compártelo).
- `unir ABC123` → te unes a ese grupo.
- `gasté 25 en transporte` → registra gasto.
- `ahorré 100 para vacaciones` → registra ingreso.
- `reporte de ropa` o `reporte general` → muestra saldos.
- `eliminar <ID_de_Mongo>` → borra un movimiento (del grupo actual).
- `info` → ver ayuda y estado del grupo.

---

## 🚀 Despliegue en Render (paso a paso)

1. **New Web Service** → conecta el repo.
2. **Runtime**: Python.
3. **Build Command**: `pip install -r requirements.txt`
4. **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. **Instance Type**: *Free* (tests) o *Starter* (más estabilidad).
6. **Environment**: agrega todas las variables del bloque `.env`.
7. **Deploy**.
8. Configura el webhook con tu URL pública de Render:
   ```bash
   curl "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<tu-servicio>.onrender.com/<BOT_TOKEN>"
   curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
   ```

> Planes gratis pueden “dormir”. Si pierdes updates, considera plan pago o plataformas con arranque rápido.

---

## 🌐 Alternativas de despliegue

- **Railway** — simple, buen free tier inicial.
- **Koyeb** — arranque rápido, variables por entorno.
- **Fly.io** — control de regiones; requiere Dockerfile.
- **Google Cloud Run** — serverless con buen free tier.

> En todas: expón `/<BOT_TOKEN>` por **HTTPS** público y configura el webhook.

---

## 🔎 Endpoints HTTP

- `GET /` → Salud del servicio.
- `POST /<BOT_TOKEN>` → Webhook que recibe updates de Telegram.
- `GET /exportar` → Exporta JSON (requiere `clave` = `EXPORT_PASS`).
  - Query params:
    - `clave` (obligatorio)
    - `group` (opcional, ej. `AB12CD`)
    - `desde` / `hasta` (opcional; formatos flexibles: `2024-01-01`, `01/01/2024`, etc.)

**Ejemplos:**
```bash
curl "https://TU_DOMINIO/exportar?clave=0000"
curl "https://TU_DOMINIO/exportar?clave=0000&group=AB12CD"
curl "https://TU_DOMINIO/exportar?clave=0000&desde=2025-01-01&hasta=2025-12-31&group=AB12CD"
```

---

## 🛡️ Seguridad y buenas prácticas

- No publiques `BOT_TOKEN`, `OPENROUTER_API_KEY` ni `MONGO_URI` en el repo.
- Cambia `EXPORT_PASS` por una clave fuerte si expondrás `/exportar`.
- Considera validar cabeceras de Telegram (`X-Telegram-Bot-Api-Secret-Token`).
- Usa roles con privilegios mínimos en MongoDB.

---

## 🧰 Troubleshooting rápido

- **El webhook no recibe mensajes**: verifica `getWebhookInfo`, la URL pública y que el path sea `/<BOT_TOKEN>`.
- **Errores con OpenRouter**: revisa `OPENROUTER_API_KEY` y el modelo. Controla timeouts.
- **Conexión a MongoDB falla**: chequea IP allowlist en Atlas y credenciales.
- **IDs para eliminar**: el `ID` se muestra al registrar; también aparece en la exportación.

---

## 🗺️ Roadmap (ideas cortas)

- Exportar a **CSV/Excel** desde `/exportar`.
- Resúmenes automáticos semanales/mensuales.
- Presupuestos por categoría y alertas.
- Mini dashboard web con gráficos.

---

## 📦 Requirements sugeridos

Incluye (ajusta según tu proyecto):

```
fastapi
uvicorn
pymongo
python-dotenv
python-dateutil
httpx
certifi
```


---

**Hecho con ❤️ por Jose Romero para quienes quieren mirar su plata con ojos de observabilidad.**
**Monedillo** te acompaña con IA para registrar, medir y decidir.
