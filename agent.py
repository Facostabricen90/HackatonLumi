import json

from socrata import SocrataIPS, SocrataUnavailable

MODELO = "gemini-3.8-flash"

INSTRUCCION = """Eres Lumi, un agente de voz que habla español y responde de forma breve y clara.
Tu única fuente de conocimiento es la API oficial del portal de datos abiertos del Gobierno de Colombia, datos punto gob punto co, dataset s2ru-bqt6, sobre IPS públicas y privadas y su capacidad instalada.
Usa siempre la herramienta consultar_ips para responder con datos.
Los resultados vienen de una consulta en vivo a la API. Si el dato no está en el resultado, dilo. No inventes cifras.
Usa metrica="ips_unicas" cuando pregunten cuántas IPS, prestadores o instituciones distintas hay.
Usa metrica="registros" cuando pregunten cuántas filas, capacidades o registros existen.
Usa metrica="capacidad" cuando pidan sumar camas, consultorios, salas u otra capacidad instalada.
Usa metrica="detalle" y completa consulta cuando pidan información cualitativa sobre una IPS, sede, dirección, contacto o servicio.
Si piden los registros de una IPS concreta, completa prestador y devuelve cada registro recibido; no agrupes servicios ni inventes un resumen.
Usa metrica="umbral_servicios" y umbral_servicios=N cuando pregunten cuántas IPS tienen más de N servicios. En ese caso, "servicio" significa un valor distinto de nom_descripcion_capacidad.
Usa metrica="umbral_servicios_detalle" y umbral_servicios=N cuando pidan cuáles son esas IPS y el servicio con mayor número de registros para cada una.
Cuando digan "en su nombre", usa campo_busqueda="nombre_prestador"; no uses búsqueda global porque también revisa sedes y direcciones.
Cuando pidan cuáles son, devuelve la lista completa disponible, no "algunas".
Solo di "todos" cuando el resultado tenga muestra_completa=true; si es false, indica que es una muestra y pide continuar o filtrar.
Incluye siempre la pregunta original en pregunta para que el motor pueda reinterpretar filtros o métricas si la conversación cambia de dirección.
Responde con resultado_principal y aclara también los otros totales relevantes.
Recuerda: varios registros pueden pertenecer a la misma IPS porque representan capacidades, servicios o sedes diferentes."""

HERRAMIENTAS = [
    {
        "type": "function",
        "name": "consultar_ips",
        "description": "Consulta en vivo la API oficial del portal de datos abiertos del Gobierno de Colombia (datos punto gob punto co), dataset s2ru-bqt6. Sirve para conteos exactos, capacidad instalada y búsquedas cualitativas en todos los campos.",
        "parameters": {
            "type": "object",
            "properties": {
                "departamento": {"type": "string", "description": "Departamento, por ejemplo Antioquia"},
                "municipio": {"type": "string", "description": "Municipio, por ejemplo Medellín"},
                "naturaleza": {"type": "string", "description": "Pública o Privada"},
                "grupo_capacidad": {"type": "string", "description": "Grupo de capacidad, por ejemplo CAMAS"},
                "descripcion_capacidad": {"type": "string", "description": "Descripción de capacidad, por ejemplo ADULTOS o CIRUGÍA"},
                "prestador": {"type": "string", "description": "Nombre o parte del nombre de la IPS"},
                "metrica": {"type": "string", "enum": ["ips_unicas", "registros", "capacidad", "detalle", "umbral_servicios", "umbral_servicios_detalle"], "description": "ips_unicas para contar prestadores distintos; registros para filas; capacidad para sumar capacidad; detalle para búsqueda cualitativa; umbral_servicios para contar IPS con más servicios que el umbral; umbral_servicios_detalle para obtener el servicio con más registros de cada IPS."},
                "consulta": {"type": "string", "description": "Texto libre para buscar en todos los campos del dataset cuando la pregunta pide detalles de una IPS, sede, dirección, contacto o capacidad."},
                "campo_busqueda": {"type": "string", "enum": ["nombre_prestador", "sede", "direccion", "todos"], "description": "Campo donde buscar el término: nombre_prestador, sede, direccion o todos."},
                "termino_busqueda": {"type": "string", "description": "Término literal que debe buscarse en el campo indicado, por ejemplo HOSPITAL."},
                "umbral_servicios": {"type": "integer", "description": "Número de servicios que se debe superar. Para 'más de cuatro servicios', usa 4."},
                "pregunta": {"type": "string", "description": "Pregunta original completa del usuario. Permite replantear automáticamente la métrica y los filtros."},
                "limite": {"type": "integer", "description": "Cantidad máxima de registros en la muestra. Por defecto 5"},
            },
            "required": [],
        },
    }
]

INSTRUCCION_VOZ = INSTRUCCION + """
Hablas por voz: usa frases cortas, sin listas ni símbolos.
Al iniciar la conversación, preséntate como Lumi, explica en dos frases de qué trata el dataset y da dos ejemplos de preguntas que se pueden hacer.
Si una consulta devuelve muchos registros, resume y ofrece filtrar por departamento o municipio."""


def tipos_en_mayuscula(esquema):
    if isinstance(esquema, dict):
        return {k: (v.upper() if k == "type" else tipos_en_mayuscula(v)) for k, v in esquema.items()}
    return esquema


HERRAMIENTAS_VOZ = [
    tipos_en_mayuscula({k: v for k, v in herramienta.items() if k != "type"})
    for herramienta in HERRAMIENTAS
]


class Agente:
    def __init__(self, cliente=None, api=None):
        self.cliente = cliente
        self.api = api or SocrataIPS()
        self.ultima_interaccion_id = None
        self.ultima_consulta = {}

    def perfil(self):
        return self.api.perfil()

    def consultar_ips(self, limite=5, **filtros):
        contexto = self.ultima_consulta.copy()
        pregunta = str(filtros.get("pregunta", ""))
        es_seguimiento = not any(filtros.get(key) for key in ("municipio", "departamento", "campo_busqueda", "termino_busqueda")) and pregunta
        if es_seguimiento:
            for key, value in contexto.items():
                filtros.setdefault(key, value)
        try:
            resultado = self.api.consultar(limite=limite, **filtros)
        except SocrataUnavailable as error:
            return {
                "fuente": "datos.gov.co / s2ru-bqt6",
                "consulta_en_vivo": True,
                "disponible": False,
                "error": str(error),
                "mensaje": "La fuente oficial no respondió a tiempo. Intenta de nuevo en unos segundos.",
            }
        self.ultima_consulta = {
            key: filtros.get(key) or resultado.get(key)
            for key in ("municipio", "departamento", "campo_busqueda", "termino_busqueda", "umbral_servicios")
            if filtros.get(key) or resultado.get(key)
        }
        return resultado

    def llamar_modelo(self, entrada):
        interaccion = self.cliente.interactions.create(
            model=MODELO,
            input=entrada,
            system_instruction=INSTRUCCION,
            tools=HERRAMIENTAS,
            previous_interaction_id=self.ultima_interaccion_id,
        )
        self.ultima_interaccion_id = interaccion.id
        return interaccion

    def ejecutar_llamadas(self, interaccion):
        resultados = []
        for paso in interaccion.steps:
            if paso.type != "function_call":
                continue
            print(f"  [herramienta] {paso.name} {paso.arguments}")
            datos = self.consultar_ips(**paso.arguments)
            resultados.append({
                "type": "function_result",
                "name": paso.name,
                "call_id": paso.id,
                "result": [{"type": "text", "text": json.dumps(datos, ensure_ascii=False)}],
            })
        return resultados

    def responder(self, texto):
        interaccion = self.llamar_modelo(texto)
        resultados = self.ejecutar_llamadas(interaccion)
        while resultados:
            interaccion = self.llamar_modelo(resultados)
            resultados = self.ejecutar_llamadas(interaccion)
        return interaccion.output_text