"""Análisis de sentimiento local (sin red ni cuota) para respaldo del modelo.

Usa un léxico en español con normalización de tildes, manejo simple de
negaciones e intensificadores. Devuelve el mismo formato que el modelo:
{"sentimiento": "positivo|neutral|negativo", "emocion": str, "intensidad": float}
"""

import re
import unicodedata

EMOCIONES = {
    "alegría": ("positivo", {
        "feliz", "felices", "contento", "contenta", "alegre", "alegria", "genial", "excelente",
        "perfecto", "perfecta", "maravilloso", "maravillosa", "encanta", "encanto", "super",
        "buenisimo", "buenisima", "chevere", "bacano", "bacana", "increible", "fantastico",
    }),
    "gratitud": ("positivo", {
        "gracias", "agradezco", "agradecido", "agradecida", "amable", "amables", "util",
        "utiles", "sirvio", "ayudo", "bendiciones",
    }),
    "satisfacción": ("positivo", {
        "bien", "bueno", "buena", "buenos", "buenas", "claro", "listo", "entendi", "vale",
        "correcto", "dale", "sirve", "facil", "rapido",
    }),
    "curiosidad": ("neutral", {
        "cuantas", "cuantos", "cuales", "donde", "como", "que", "quisiera", "saber", "consultar",
        "pregunta", "informacion", "dime", "muestrame", "busca", "buscar",
    }),
    "confusión": ("negativo", {
        "confundido", "confundida", "entiendo", "raro", "extrano", "perdido", "perdida",
        "complicado", "dificil", "duda", "dudas",
    }),
    "preocupación": ("negativo", {
        "preocupa", "preocupado", "preocupada", "urgente", "urgencia", "emergencia", "grave",
        "miedo", "asustado", "asustada", "dolor", "enfermo", "enferma", "riesgo", "ayuda",
    }),
    "tristeza": ("negativo", {
        "triste", "tristeza", "lamentable", "deprimido", "deprimida", "solo", "sola", "llorar",
        "desanimado", "desanimada", "pena",
    }),
    "frustración": ("negativo", {
        "malo", "mala", "pesimo", "pesima", "terrible", "horrible", "falla", "fallo", "error",
        "lento", "lenta", "funciona", "sirve", "inutil", "cansado", "cansada", "harto", "harta",
    }),
    "enojo": ("negativo", {
        "molesto", "molesta", "enojado", "enojada", "rabia", "furioso", "furiosa", "bravo",
        "brava", "odio", "estupido", "absurdo", "indignado", "indignada",
    }),
}

NEGACIONES = {"no", "nunca", "jamas", "tampoco", "ni", "nada"}
INTENSIFICADORES = {"muy", "super", "demasiado", "bastante", "tan", "totalmente", "realmente", "mucho"}
INVERSO = {"positivo": "negativo", "negativo": "positivo", "neutral": "neutral"}


def _normalizar(texto: str) -> list[str]:
    plano = unicodedata.normalize("NFD", texto.lower())
    plano = "".join(c for c in plano if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-zñ]+", plano)


def analizar_local(texto: str) -> dict:
    palabras = _normalizar(texto or "")
    puntajes: dict[str, float] = {}

    for i, palabra in enumerate(palabras):
        for emocion, (_, lexico) in EMOCIONES.items():
            if palabra not in lexico:
                continue
            ventana = palabras[max(0, i - 3):i]
            peso = 1.5 if any(p in INTENSIFICADORES for p in ventana) else 1.0
            if any(p in NEGACIONES for p in ventana):
                # "no funciona", "no entiendo" refuerzan lo negativo; "no está bien" invierte lo positivo
                polaridad = EMOCIONES[emocion][0]
                if polaridad == "positivo":
                    emocion = "frustración"
                elif emocion in ("frustración", "confusión"):
                    peso += 0.5
            puntajes[emocion] = puntajes.get(emocion, 0) + peso

    if not puntajes:
        return {"sentimiento": "neutral", "emocion": "neutral", "intensidad": 0.2, "fuente": "local"}

    # La curiosidad pesa menos: casi todas las preguntas la contienen
    if "curiosidad" in puntajes and len(puntajes) > 1:
        puntajes["curiosidad"] *= 0.5

    emocion = max(puntajes, key=puntajes.get)
    sentimiento = EMOCIONES[emocion][0]
    exclamaciones = min((texto or "").count("!"), 3) * 0.08
    intensidad = min(1.0, 0.35 + 0.18 * puntajes[emocion] + exclamaciones)
    if sentimiento == "neutral":
        intensidad = min(intensidad, 0.5)

    return {
        "sentimiento": sentimiento,
        "emocion": emocion,
        "intensidad": round(intensidad, 2),
        "fuente": "local",
    }
