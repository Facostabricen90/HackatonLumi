import datetime
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google import genai
from agent import Agente, INSTRUCCION_VOZ, HERRAMIENTAS_VOZ

load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=True)

MODELO_VOZ = "gemini-3.8-live"
VOZ_DEFECTO = os.getenv("VOZ_GEMINI", "Aoede")

app = FastAPI()
frontend_origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

gemini_api_key = os.getenv("GEMINI_API_KEY")
cliente = genai.Client(api_key=gemini_api_key) if gemini_api_key else None
agente = Agente(cliente)


@app.get("/api/sesion")
@app.get("/sesion")
def crear_sesion():
    if not cliente:
        raise HTTPException(
            status_code=500,
            detail="Falta configurar GEMINI_API_KEY en las variables de entorno de Vercel (Project Settings -> Environment Variables)"
        )
    try:
        ahora = datetime.datetime.now(tz=datetime.timezone.utc)
        token = cliente.auth_tokens.create(config={
            "uses": 1,
            "expire_time": ahora + datetime.timedelta(minutes=30),
            "new_session_expire_time": ahora + datetime.timedelta(minutes=1),
        })
        return {
            "token": token.name,
            "modelo": MODELO_VOZ,
            "voz": VOZ_DEFECTO,
            "instruccion": f"{INSTRUCCION_VOZ}\n\n{agente.perfil()}",
            "herramientas": HERRAMIENTAS_VOZ,
        }
    except Exception as error:
        print("Error al crear sesión Live:", error)
        raise HTTPException(status_code=500, detail=f"Error al generar token Live de Gemini: {str(error)}")


@app.post("/api/consulta")
@app.post("/consulta")
def consultar(filtros: dict):
    return agente.consultar_ips(**filtros)


@app.post("/api/sentimiento")
@app.post("/sentimiento")
def analizar_sentimiento(datos: dict):
    return agente.analizar_sentimiento(datos.get("texto", ""))

# Solo montar en local si la carpeta existe; en Vercel los archivos se sirven automáticamente
public_path = Path(__file__).resolve().parent / "public"
if public_path.exists():
    app.mount("/", StaticFiles(directory=str(public_path), html=True), name="frontend")

