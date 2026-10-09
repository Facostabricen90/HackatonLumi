import datetime
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from google import genai
from agent import Agente, INSTRUCCION_VOZ, HERRAMIENTAS_VOZ

load_dotenv()

MODELO_VOZ = "gemini-3.8-live"

app = FastAPI()
cliente = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
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
        "instruccion": f"{INSTRUCCION_VOZ}\n\n{agente.perfil()}",
        "herramientas": HERRAMIENTAS_VOZ,
    }


@app.post("/api/consulta")
def consultar(filtros: dict):
    return agente.consultar_ips(**filtros)