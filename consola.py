import os
from dotenv import load_dotenv
from google import genai
from agent import Agente

load_dotenv()

clave = os.getenv("GEMINI_API_KEY")
if not clave:
    raise SystemExit("Falta GEMINI_API_KEY en el archivo .env")

agente = Agente(genai.Client(api_key=clave))
PALABRAS_SALIDA = ["salir", "exit", "quit", "chao", "adiós"]

print("Lumi listo. Escribe 'salir' para terminar.")

while True:
    texto = input("Tú: ").strip()
    if not texto:
        continue
    if texto.lower() in PALABRAS_SALIDA:
        print("Hasta luego.")
        break
    print("Lumi:", agente.responder(texto))