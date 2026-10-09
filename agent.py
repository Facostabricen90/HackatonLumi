import json
import os
import unicodedata
import httpx
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

MODELO = "gemini-3.8-flash"
URL_DATOS = os.getenv("SOCRATA_DATASET_API_URL")
TOKEN_DATOS = os.getenv("SOCRATA_APP_TOKEN")

INSTRUCCION = """Eres Lumi, un agente de voz que habla español y responde de forma breve y clara.
Tu única fuente de conocimiento es el dataset de IPS públicas y privadas de Colombia, con su nivel de atención y capacidad instalada.
Cada fila del dataset es una capacidad instalada (camas, salas, ambulancias...) de una sede de una IPS.
La capacidad solo se puede sumar dentro de un mismo grupo de capacidad: camas con camas, salas con salas.
Bogotá D.C, Cali, Barranquilla, Cartagena, Santa Marta y Buenaventura figuran como departamento propio: para esas ciudades filtra por departamento con ese nombre.
Usa siempre la herramienta consultar_ips para responder con datos.
Si la herramienta devuelve un error con opciones, ofrécelas al usuario.
Si el dato no está en el dataset, dilo. No inventes cifras."""

INSTRUCCION_VOZ = INSTRUCCION + """
Hablas por voz: usa frases cortas, sin listas ni símbolos.
Al iniciar la conversación, preséntate como Lumi, explica en dos frases de qué trata el dataset y da dos ejemplos de preguntas que se pueden hacer.
Si una consulta devuelve muchos registros, resume y ofrece filtrar por departamento o municipio."""

HERRAMIENTAS = [
    {
        "type": "function",
        "name": "consultar_ips",
        "description": "Consulta el dataset de IPS. Devuelve filas de capacidad, capacidad por grupo, IPS distintas (si hay filtros) y una muestra o un ranking.",
        "parameters": {
            "type": "object",
            "properties": {
                "departamento": {"type": "string", "description": "Departamento, por ejemplo Antioquia"},
                "municipio": {"type": "string", "description": "Municipio, por ejemplo Medellín"},
                "naturaleza": {"type": "string", "description": "Pública o Privada"},
                "nivel_atencion": {"type": "string", "description": "Nivel de atención, por ejemplo 1, 2 o 3"},
                "grupo_capacidad": {"type": "string", "description": "Grupo de capacidad, por ejemplo CAMAS"},
                "prestador": {"type": "string", "description": "Parte del nombre de la IPS"},
                "agrupar_por": {
                    "type": "string",
                    "enum": ["departamento", "municipio", "naturaleza", "nivel_atencion", "grupo_capacidad", "prestador"],
                    "description": "Devuelve un ranking agrupado por este campo",
                },
                "limite": {"type": "integer", "description": "Cantidad de filas o grupos a devolver. Por defecto 5"},
            },
            "required": [],
        },
    }
]

CAMPOS_FILTRO = {
    "departamento": "departamento",
    "municipio": "municipio",
    "naturaleza": "naturaleza",
    "nivel_atencion": "num_nivel_atencion",
    "grupo_capacidad": "nom_grupo_capacidad",
}
CAMPOS_AGRUPAR = {**CAMPOS_FILTRO, "prestador": "nombre_prestador"}
CAMPO_PRESTADOR = "nombre_prestador"
CAMPO_CODIGO = "c_digo_prestador"
CAMPO_GRUPO = "nom_grupo_capacidad"
CAMPO_CAPACIDAD = "num_cantidad_capacidad_instalada"


def tipos_en_mayuscula(esquema):
    if isinstance(esquema, dict):
        return {k: (v.upper() if k == "type" else tipos_en_mayuscula(v)) for k, v in esquema.items()}
    return esquema


HERRAMIENTAS_VOZ = [
    tipos_en_mayuscula({k: v for k, v in herramienta.items() if k != "type"})
    for herramienta in HERRAMIENTAS
]

PROMPT_SENTIMIENTO = """Analiza el sentimiento y la emoción del siguiente texto en español.
Responde SOLO con un JSON con esta forma exacta:
{"sentimiento": "positivo", "emocion": "alegría", "intensidad": 0.7}
sentimiento solo puede ser: positivo, neutral o negativo.
emocion es una sola palabra en español.
intensidad es un número entre 0 y 1.
Texto: """


encabezados_datos = {"X-App-Token": TOKEN_DATOS} if TOKEN_DATOS else {}
cliente_http = httpx.Client(headers=encabezados_datos, timeout=20)

def sin_tildes(texto):
    texto = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(letra for letra in texto if unicodedata.category(letra) != "Mn")


def a_numero(valor):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 0
    return int(numero) if numero.is_integer() else numero


def entre_comillas(valor):
    return "'" + str(valor).replace("'", "''") + "'"