import json
import unicodedata

MODELO = "gemini-3.8-flash"

INSTRUCCION = """Eres Lumi, un agente de voz que habla español y responde de forma breve y clara.
Tu única fuente de conocimiento es el dataset de IPS públicas y privadas de Colombia, con su nivel de atención y capacidad instalada.
Usa siempre la herramienta consultar_ips para responder con datos.
Si el dato no está en el dataset, dilo. No inventes cifras."""

HERRAMIENTAS = [
    {
        "type": "function",
        "name": "consultar_ips",
        "description": "Busca IPS en el dataset y devuelve el total encontrado, la capacidad instalada total y una muestra de registros.",
        "parameters": {
            "type": "object",
            "properties": {
                "departamento": {"type": "string", "description": "Departamento, por ejemplo Antioquia"},
                "municipio": {"type": "string", "description": "Municipio, por ejemplo Medellín"},
                "naturaleza": {"type": "string", "description": "Pública o Privada"},
                "nivel_atencion": {"type": "string", "description": "Nivel de atención, por ejemplo 1, 2 o 3"},
                "grupo_capacidad": {"type": "string", "description": "Grupo de capacidad, por ejemplo CAMAS"},
                "limite": {"type": "integer", "description": "Cantidad máxima de registros en la muestra. Por defecto 5"},
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


def sin_tildes(texto):
    texto = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(letra for letra in texto if unicodedata.category(letra) != "Mn")


def a_numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0


class Agente:
    def __init__(self, cliente=None, ruta_datos="ips.json"):
        self.cliente = cliente
        self.registros = self.cargar_datos(ruta_datos)
        self.ultima_interaccion_id = None

    def perfil(self):
        def valores(campo):
            return sorted({r.get(campo) for r in self.registros if r.get(campo)})

        return (
            f"El dataset tiene {len(self.registros)} registros. "
            f"Departamentos: {', '.join(valores('departamento'))}. "
            f"Naturaleza: {', '.join(valores('naturaleza'))}. "
            f"Niveles de atención: {', '.join(valores('num_nivel_atencion'))}. "
            f"Grupos de capacidad: {', '.join(valores('nom_grupo_capacidad'))}."
        )

    def cargar_datos(self, ruta):
        with open(ruta, "r", encoding="utf-8") as archivo:
            return json.load(archivo)

    def cumple_filtros(self, registro, filtros):
        for nombre, valor in filtros.items():
            campo = CAMPOS_FILTRO.get(nombre)
            if not campo or not valor:
                continue
            if sin_tildes(valor) not in sin_tildes(registro.get(campo, "")):
                return False
        return True

    def resumir(self, registro):
        return {
            "departamento": registro.get("departamento"),
            "municipio": registro.get("municipio"),
            "prestador": registro.get("nombre_prestador"),
            "naturaleza": registro.get("naturaleza"),
            "nivel_atencion": registro.get("num_nivel_atencion"),
            "grupo_capacidad": registro.get("nom_grupo_capacidad"),
            "capacidad": registro.get("nom_descripcion_capacidad"),
            "cantidad": registro.get("num_cantidad_capacidad_instalada"),
        }

    def consultar_ips(self, limite=5, **filtros):
        encontrados = [r for r in self.registros if self.cumple_filtros(r, filtros)]
        capacidad_total = sum(a_numero(r.get("num_cantidad_capacidad_instalada")) for r in encontrados)
        return {
            "total_registros": len(encontrados),
            "capacidad_total": capacidad_total,
            "muestra": [self.resumir(r) for r in encontrados[: int(limite)]],
        }

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