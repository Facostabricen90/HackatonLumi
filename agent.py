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


def pedir_datos(parametros):
    respuesta = cliente_http.get(URL_DATOS, params=parametros)
    if respuesta.status_code >= 400:
        raise RuntimeError(f"datos.gov.co respondió {respuesta.status_code}: {respuesta.text[:300]}")
    return respuesta.json()


class Agente:
    def __init__(self, cliente=None):
        self.cliente = cliente
        self.ultima_interaccion_id = None
        self.catalogo = {}
        self.texto_perfil = None

    def valores_de(self, campo):
        if campo not in self.catalogo:
            filas = pedir_datos({"$select": campo, "$group": campo, "$limit": 5000})
            self.catalogo[campo] = sorted(fila[campo] for fila in filas if fila.get(campo))
        return self.catalogo[campo]

    def perfil(self):
        if not self.texto_perfil:
            campos = ["fecha_corte", "departamento", "naturaleza", "num_nivel_atencion", CAMPO_GRUPO, "municipio"]
            with ThreadPoolExecutor() as pool:
                pendiente_total = pool.submit(pedir_datos, {"$select": "count(*) as filas"})
                list(pool.map(self.valores_de, campos))
                total = pendiente_total.result()[0]["filas"]
            self.texto_perfil = (
                f"El dataset tiene {total} filas; cada fila es una capacidad instalada de una sede de una IPS. "
                f"Fecha de corte: {', '.join(self.valores_de('fecha_corte'))}. "
                f"Departamentos: {', '.join(self.valores_de('departamento'))}. "
                f"Naturaleza: {', '.join(self.valores_de('naturaleza'))}. "
                f"Niveles de atención: {', '.join(self.valores_de('num_nivel_atencion'))}. "
                f"Grupos de capacidad: {', '.join(self.valores_de(CAMPO_GRUPO))}."
            )
        return self.texto_perfil

    def resolver(self, campo, pedido):
        pedido = sin_tildes(pedido).strip()
        valores = self.valores_de(campo)
        exactos = [valor for valor in valores if sin_tildes(valor) == pedido]
        return exactos or [valor for valor in valores if pedido in sin_tildes(valor)]

    def armar_filtro(self, filtros):
        condiciones = []
        for nombre, pedido in filtros.items():
            if not pedido:
                continue
            if nombre == "prestador":
                patron = entre_comillas(f"%{str(pedido).upper()}%")
                condiciones.append(f"upper({CAMPO_PRESTADOR}) like {patron}")
                continue
            campo = CAMPOS_FILTRO.get(nombre)
            if not campo:
                continue
            encontrados = self.resolver(campo, pedido)
            if not encontrados:
                opciones = ", ".join(self.valores_de(campo)[:40])
                raise ValueError(f"No encontré {nombre} '{pedido}'. Opciones: {opciones}")
            condiciones.append(f"{campo} in ({', '.join(entre_comillas(v) for v in encontrados)})")
        return " AND ".join(condiciones)

    def resumir(self, registro):
        return {
            "departamento": registro.get("departamento"),
            "municipio": registro.get("municipio"),
            "prestador": registro.get("nombre_prestador"),
            "naturaleza": registro.get("naturaleza"),
            "nivel_atencion": registro.get("num_nivel_atencion"),
            "grupo_capacidad": registro.get(CAMPO_GRUPO),
            "capacidad": registro.get("nom_descripcion_capacidad"),
            "cantidad": registro.get(CAMPO_CAPACIDAD),
        }

    def consultar_ips(self, agrupar_por=None, limite=5, **filtros):
        try:
            donde = self.armar_filtro(filtros)
        except ValueError as error:
            return {"error": str(error)}

        base = {"$where": donde} if donde else {}
        suma = f"count(*) as filas, sum({CAMPO_CAPACIDAD}) as capacidad_total"
        consultas = {"por_grupo": {**base, "$select": f"{CAMPO_GRUPO}, {suma}", "$group": CAMPO_GRUPO}}

        if donde:
            consultas["codigos"] = {**base, "$select": CAMPO_CODIGO, "$group": CAMPO_CODIGO, "$limit": 50000}

        if agrupar_por in CAMPOS_AGRUPAR:
            campo = CAMPOS_AGRUPAR[agrupar_por]
            orden = "capacidad_total DESC" if filtros.get("grupo_capacidad") else "filas DESC"
            consultas["detalle"] = {**base, "$select": f"{campo}, {suma}", "$group": campo, "$order": orden, "$limit": int(limite)}
        else:
            consultas["detalle"] = {**base, "$limit": int(limite)}

        with ThreadPoolExecutor() as pool:
            pendientes = {nombre: pool.submit(pedir_datos, parametros) for nombre, parametros in consultas.items()}
            respuestas = {nombre: pendiente.result() for nombre, pendiente in pendientes.items()}

        por_grupo = respuestas["por_grupo"]
        resultado = {
            "filas_de_capacidad": sum(a_numero(g["filas"]) for g in por_grupo),
            "capacidad_por_grupo": [
                {"grupo": g.get(CAMPO_GRUPO), "filas": a_numero(g["filas"]), "capacidad_total": a_numero(g.get("capacidad_total"))}
                for g in por_grupo
            ],
        }
        if "codigos" in respuestas:
            resultado["ips_distintas"] = len(respuestas["codigos"])
        if agrupar_por in CAMPOS_AGRUPAR:
            campo = CAMPOS_AGRUPAR[agrupar_por]
            resultado["ranking"] = [
                {agrupar_por: g.get(campo), "filas": a_numero(g["filas"]), "capacidad_total": a_numero(g.get("capacidad_total"))}
                for g in respuestas["detalle"]
            ]
        else:
            resultado["muestra"] = [self.resumir(r) for r in respuestas["detalle"]]
        return resultado

    def analizar_sentimiento(self, texto):
        try:
            interaccion = self.cliente.interactions.create(model=MODELO, input=PROMPT_SENTIMIENTO + texto)
            limpio = interaccion.output_text.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(limpio)
        except Exception as error:
            print("Error de sentimiento:", error)
            return {"sentimiento": "neutral", "emocion": "neutral", "intensidad": 0}

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