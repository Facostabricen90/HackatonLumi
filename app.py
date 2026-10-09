import datetime
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
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
if not gemini_api_key:
    raise RuntimeError("Falta GEMINI_API_KEY en .env o en las variables del entorno")
cliente = genai.Client(api_key=gemini_api_key)
agente = Agente(cliente)


@app.get("/api/sesion")
def crear_sesion():
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


@app.post("/api/consulta")
def consultar(filtros: dict):
    return agente.consultar_ips(**filtros)

@app.post("/api/sentimiento")
def analizar_sentimiento(datos: dict):
    return agente.analizar_sentimiento(datos.get("texto", ""))

app.mount("/", StaticFiles(directory="public", html=True), name="frontend")
