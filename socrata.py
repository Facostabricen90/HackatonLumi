import os
import re
import unicodedata
from typing import Any

import requests

DATASET_API_URL = os.getenv(
    "SOCRATA_DATASET_API_URL",
    "https://www.datos.gov.co/resource/s2ru-bqt6.json",
)
DEFAULT_LIMIT = 5
MAX_LIMIT = 25
REQUEST_TIMEOUT = 20


class SocrataUnavailable(RuntimeError):
    """La API oficial no respondió dentro del tiempo permitido."""

FIELD_MAP = {
    "departamento": "departamento",
    "municipio": "municipio",
    "naturaleza": "naturaleza",
    "grupo_capacidad": "nom_grupo_capacidad",
    "descripcion_capacidad": "nom_descripcion_capacidad",
    "prestador": "nombre_prestador",
}

SEARCH_FIELD_MAP = {
    "nombre_prestador": "nombre_prestador",
    "sede": "nom_sede_ips",
    "direccion": "direcci_n",
    "todos": None,
}

PRESTADOR_ALIASES = {
    "COMFACALDAS": "CAJA DE COMPENSACION FAMILIAR DE CALDAS",
    "CONFA": "CAJA DE COMPENSACION FAMILIAR DE CALDAS",
}

QUALITATIVE_FIELDS = (
    "departamento, municipio, c_digo_prestador, nombre_prestador, nit_ips, "
    "naturaleza, c_digo_sede, n_mero_sede, nom_sede_ips, gerente, direcci_n, "
    "email, tel_fono, nom_grupo_capacidad, nom_descripcion_capacidad, "
    "num_cantidad_capacidad_instalada, fecha_corte, fuente"
)

DEPARTAMENTOS = {
    "ANTIOQUIA", "ATLANTICO", "BOGOTA", "BOLIVAR", "BOYACA", "CALDAS",
    "CAQUETA", "CASANARE", "CAUCA", "CESAR", "CORDOBA", "CUNDINAMARCA",
    "CHOCO", "HUILA", "LA GUAJIRA", "MAGDALENA", "META", "NARINO",
    "NORTE DE SANTANDER", "PUTUMAYO", "QUINDIO", "RISARALDA", "SANTANDER",
    "SUCRE", "TOLIMA", "VALLE DEL CAUCA", "ARAUCA", "GUAVIARE", "GUAINIA",
    "VAUPES", "VICHADA", "AMAZONAS",
}

MUNICIPIOS_CANONICOS = {
    "BOGOTA": "Bogotá",
    "MEDELLIN": "Medellín",
    "IBAGUE": "Ibagué",
    "POPAYAN": "Popayán",
    "TUNJA": "Tunja",
    "PASTO": "Pasto",
    "MANIZALES": "Manizales",
    "PEREIRA": "Pereira",
    "ARMENIA": "Armenia",
    "CALI": "Cali",
    "CARTAGENA": "Cartagena",
    "BARRANQUILLA": "Barranquilla",
    "BUCARAMANGA": "Bucaramanga",
    "VILLAVICENCIO": "Villavicencio",
    "MONTERIA": "Montería",
    "VALLEDUPAR": "Valledupar",
    "SANTA MARTA": "Santa Marta",
    "NEIVA": "Neiva",
    "CUCUTA": "Cúcuta",
}

MUNICIPIO_PREFIXES = {
    "BOGOTA": "BOGOT",
    "MEDELLIN": "MEDELL",
    "IBAGUE": "IBAGU",
    "POPAYAN": "POPAY",
    "CUCUTA": "CUC",
    "MONTERIA": "MONTER",
}

NUMEROS = {
    "UNO": 1, "DOS": 2, "TRES": 3, "CUATRO": 4, "CINCO": 5,
    "SEIS": 6, "SIETE": 7, "OCHO": 8, "NUEVE": 9, "DIEZ": 10,
    "ONCE": 11, "DOCE": 12, "TRECE": 13, "CATORCE": 14, "QUINCE": 15,
}


def clean_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", str(text).upper())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _escape_literal(value: str) -> str:
    return str(value).replace("'", "''")


def _contains_clause(field: str, value: str) -> str:
    normalized = clean_text(value)
    if field == "naturaleza":
        if normalized.startswith("PUBLIC"):
            return "naturaleza = 'Pública'"
        if normalized.startswith("PRIVAD"):
            return "naturaleza like 'Privad%'"

    if field in {"nombre_prestador", "nom_grupo_capacidad", "nom_descripcion_capacidad"}:
        if field == "nombre_prestador":
            value = PRESTADOR_ALIASES.get(normalized, value)
            normalized = clean_text(value)
        return f"upper({field}) like '%{_escape_literal(normalized)}%'"

    canonical = MUNICIPIOS_CANONICOS.get(normalized, value)
    prefix = MUNICIPIO_PREFIXES.get(normalized)
    if prefix is None:
        source = str(canonical).upper() if field == "municipio" else str(canonical)
        decomposed = unicodedata.normalize("NFD", source)
        accent_position = next(
            (index for index, char in enumerate(decomposed) if unicodedata.category(char) == "Mn"),
            len(decomposed),
        )
        prefix = decomposed[:accent_position]
    return f"{field} like '%{_escape_literal(prefix)}%'"


def _number(value: Any) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0


def _inferir_intencion(pregunta: str) -> tuple[str | None, int | None, dict[str, str]]:
    normalized = clean_text(pregunta)
    threshold_match = re.search(r"(?:MAS|MAYOR|SUPERIOR)\s+(?:DE|A)\s+(\d+|[A-Z]+)\s+SERVICIOS?", normalized)
    threshold_value = threshold_match.group(1) if threshold_match else None
    threshold = int(threshold_value) if threshold_value and threshold_value.isdigit() else NUMEROS.get(threshold_value) if threshold_value else None
    if threshold is not None:
        metric = "umbral_servicios_detalle" if any(word in normalized for word in ("CUALES", "CUAL", "SERVICIO CON MAS", "PRINCIPAL")) else "umbral_servicios"
    elif "SERVICIO CON MAS" in normalized or "SERVICIO PRINCIPAL" in normalized:
        metric = "detalle"
    elif "REGISTROS" in normalized or "FILAS" in normalized:
        metric = "registros"
    elif "CAPACIDAD" in normalized or "CAMAS" in normalized or "CONSULTORIOS" in normalized:
        metric = "capacidad"
    elif "SERVICIO" in normalized:
        metric = "servicios_prestador"
    elif "IPS" in normalized or "PRESTADORES" in normalized or "INSTITUCIONES" in normalized:
        metric = "ips_unicas"
    else:
        metric = None

    inferred_filters = {}
    for normalized_name, canonical_name in MUNICIPIOS_CANONICOS.items():
        if re.search(rf"\b{re.escape(normalized_name)}\b", normalized):
            inferred_filters["municipio"] = canonical_name
            break
    for alias, canonical_name in PRESTADOR_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            inferred_filters["prestador"] = canonical_name
            break
    return metric, threshold, inferred_filters


def _inferir_busqueda(pregunta: str) -> tuple[str, str]:
    normalized = clean_text(pregunta)
    term_match = re.search(r"(?:PALABRA|CONTENGA|CONTIENE)\s+([A-Z0-9]+)", normalized)
    if not term_match:
        return "", ""
    if "EN SU NOMBRE" in normalized or "EN EL NOMBRE" in normalized:
        return "nombre_prestador", term_match.group(1)
    if "EN LA SEDE" in normalized or "EN SU SEDE" in normalized:
        return "sede", term_match.group(1)
    if "EN LA DIRECCION" in normalized or "EN SU DIRECCION" in normalized:
        return "direccion", term_match.group(1)
    return "todos", term_match.group(1)


class SocrataIPS:
    def __init__(self, url: str = DATASET_API_URL, app_token: str | None = None):
        self.url = url
        self.app_token = app_token or os.getenv("SOCRATA_APP_TOKEN")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "LumiIPS/1.0"})
        if self.app_token:
            self.session.headers["X-App-Token"] = self.app_token

    def _get(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            response = self.session.get(self.url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as error:
            raise SocrataUnavailable("datos.gov.co no respondió a tiempo") from error
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("La API Socrata devolvió un formato inesperado")
        return payload

    def _where(self, filtros: dict[str, Any]) -> str:
        clauses = []
        for name, value in filtros.items():
            if not value or name not in FIELD_MAP:
                continue
            field = FIELD_MAP[name]
            clauses.append(_contains_clause(field, str(value)))
        return " AND ".join(clauses) or "1=1"

    def consultar(
        self,
        limite: int = DEFAULT_LIMIT,
        metrica: str | None = None,
        consulta: str = "",
        umbral_servicios: int | None = None,
        pregunta: str = "",
        campo_busqueda: str = "",
        termino_busqueda: str = "",
        **filtros: Any,
    ) -> dict[str, Any]:
        inferred_metric, inferred_threshold, inferred_filters = _inferir_intencion(pregunta)
        metrica = metrica or inferred_metric or "ips_unicas"
        umbral_servicios = umbral_servicios if umbral_servicios is not None else inferred_threshold
        for name, value in inferred_filters.items():
            filtros.setdefault(name, value)
        inferred_field, inferred_term = _inferir_busqueda(pregunta)
        campo_busqueda = campo_busqueda or inferred_field
        termino_busqueda = termino_busqueda or inferred_term
        if not consulta and metrica == "detalle":
            consulta = pregunta
        limite = min(max(int(limite or DEFAULT_LIMIT), 1), MAX_LIMIT)
        where = self._where(filtros)
        search_field = SEARCH_FIELD_MAP.get(campo_busqueda)
        if search_field and termino_busqueda:
            search_clause = f"upper({search_field}) like '%{_escape_literal(clean_text(termino_busqueda))}%'"
            where = f"({where}) AND {search_clause}"
        provider_detail = metrica == "detalle" and bool(filtros.get("prestador"))
        query_params = {"$where": where}
        if consulta.strip() and not search_field and not provider_detail:
            query_params["$q"] = consulta.strip()
        if metrica == "servicios_prestador":
            servicios = self._get({
                **query_params,
                "$select": "nom_descripcion_capacidad, count(*) as registros_servicio, sum(num_cantidad_capacidad_instalada) as capacidad_servicio",
                "$group": "nom_descripcion_capacidad",
                "$order": "nom_descripcion_capacidad ASC",
                "$limit": 50000,
            })
            return {
                "fuente": "datos.gov.co / s2ru-bqt6",
                "consulta_en_vivo": True,
                "metrica_solicitada": "servicios_prestador",
                "resultado_principal": {"valor": len(servicios), "unidad": "servicios únicos"},
                "prestador_consultado": filtros.get("prestador"),
                "filtros_aplicados": {key: value for key, value in filtros.items() if value},
                "servicios": [
                    {
                        "servicio": row.get("nom_descripcion_capacidad"),
                        "registros": int(_number(row.get("registros_servicio"))),
                        "capacidad_total": _number(row.get("capacidad_servicio")),
                    }
                    for row in servicios
                ],
                "muestra_completa": True,
            }
        if metrica == "umbral_servicios" or umbral_servicios is not None:
            threshold = max(int(umbral_servicios or 0), 0)
            grouped = self._get({
                **query_params,
                "$select": "c_digo_prestador, nombre_prestador, count(distinct nom_descripcion_capacidad) as servicios, count(*) as registros, sum(num_cantidad_capacidad_instalada) as capacidad_total",
                "$group": "c_digo_prestador, nombre_prestador",
                "$having": f"count(distinct nom_descripcion_capacidad) > {threshold}",
                "$order": "servicios DESC",
                "$limit": 5000,
            })
            if metrica == "umbral_servicios_detalle":
                detail_rows = self._get({
                    **query_params,
                    "$select": "c_digo_prestador, nombre_prestador, nom_descripcion_capacidad, count(*) as registros_servicio, sum(num_cantidad_capacidad_instalada) as capacidad_servicio",
                    "$group": "c_digo_prestador, nombre_prestador, nom_descripcion_capacidad",
                    "$order": "registros_servicio DESC",
                    "$limit": 50000,
                })
                qualifying_ids = {row.get("c_digo_prestador") for row in grouped if row.get("c_digo_prestador")}
                by_provider: dict[str, dict[str, Any]] = {}
                for row in detail_rows:
                    provider_id = row.get("c_digo_prestador")
                    if provider_id not in qualifying_ids:
                        continue
                    provider = by_provider.setdefault(provider_id, {
                        "prestador": row.get("nombre_prestador"),
                        "ips_id": provider_id,
                        "servicios_totales": 0,
                        "servicio_mas_registros": None,
                    })
                    provider["servicios_totales"] += 1
                    service = {
                        "servicio": row.get("nom_descripcion_capacidad"),
                        "registros": int(_number(row.get("registros_servicio"))),
                        "capacidad_total": _number(row.get("capacidad_servicio")),
                    }
                    current = provider["servicio_mas_registros"]
                    if current is None or service["registros"] > current["registros"]:
                        provider["servicio_mas_registros"] = service
                detailed_list = list(by_provider.values())
                detailed_list.sort(key=lambda item: item["servicio_mas_registros"]["registros"], reverse=True)
                return {
                    "fuente": "datos.gov.co / s2ru-bqt6",
                    "consulta_en_vivo": True,
                    "metrica_solicitada": "umbral_servicios_detalle",
                    "definicion_servicio": "valor distinto de nom_descripcion_capacidad",
                    "umbral": threshold,
                    "resultado_principal": {"valor": len(detailed_list), "unidad": "IPS únicas"},
                    "total_ips_que_superan_umbral": len(detailed_list),
                    "filtros_aplicados": {key: value for key, value in filtros.items() if value},
                    "consulta_textual": consulta.strip() or None,
                    "lista_que_cumplen": detailed_list[:10],
                }
            lista = [
                {
                    "prestador": row.get("nombre_prestador"),
                    "ips_id": row.get("c_digo_prestador"),
                    "servicios": int(_number(row.get("servicios"))),
                    "registros": int(_number(row.get("registros"))),
                    "capacidad_total": _number(row.get("capacidad_total")),
                }
                for row in grouped
            ]
            return {
                "fuente": "datos.gov.co / s2ru-bqt6",
                "consulta_en_vivo": True,
                "metrica_solicitada": "umbral_servicios",
                "definicion_servicio": "valor distinto de nom_descripcion_capacidad",
                "umbral": threshold,
                "resultado_principal": {"valor": len(lista), "unidad": "IPS únicas"},
                "total_ips_que_superan_umbral": len(lista),
                "filtros_aplicados": {key: value for key, value in filtros.items() if value},
                "consulta_textual": consulta.strip() or None,
                "lista_que_cumplen": lista[:10],
            }
        metricas = self._get({
            **query_params,
            "$select": "count(*) as total_registros, count(distinct c_digo_prestador) as ips_unicas, sum(num_cantidad_capacidad_instalada) as capacidad_total",
        })
        if search_field and termino_busqueda:
            muestra = self._get({
                **query_params,
                "$select": "c_digo_prestador, nombre_prestador, c_digo_sede, nom_sede_ips, direcci_n, count(*) as registros_encontrados",
                "$group": "c_digo_prestador, nombre_prestador, c_digo_sede, nom_sede_ips, direcci_n",
                "$order": "nombre_prestador ASC",
                "$limit": 50000,
            })
        elif provider_detail:
            muestra = self._get({
                **query_params,
                "$select": QUALITATIVE_FIELDS,
                "$order": "nom_descripcion_capacidad ASC",
                "$limit": 50000,
            })
        else:
            muestra = self._get({
                **query_params,
                "$select": QUALITATIVE_FIELDS,
                "$order": "nombre_prestador ASC",
                "$limit": limite,
            })
        metricas = metricas[0] if metricas else {}
        total_registros = int(_number(metricas.get("total_registros")))
        ips_unicas = int(_number(metricas.get("ips_unicas")))
        capacidad_total = _number(metricas.get("capacidad_total"))
        valores_principales = {
            "ips_unicas": (ips_unicas, "IPS únicas"),
            "registros": (total_registros, "registros"),
            "capacidad": (capacidad_total, "unidades de capacidad instalada"),
            "detalle": (ips_unicas, "IPS únicas"),
        }
        valor_principal, unidad_principal = valores_principales.get(metrica, valores_principales["ips_unicas"])
        return {
            "fuente": "datos.gov.co / s2ru-bqt6",
            "consulta_en_vivo": True,
            "metrica_solicitada": metrica,
            "resultado_principal": {"valor": valor_principal, "unidad": unidad_principal},
            "filtros_aplicados": {key: value for key, value in filtros.items() if value},
            "consulta_textual": consulta.strip() or None,
            "campo_busqueda": campo_busqueda or None,
            "termino_busqueda": termino_busqueda or None,
            "muestra_completa": bool(search_field and termino_busqueda) or provider_detail,
            "total_registros": total_registros,
            "ips_unicas": ips_unicas,
            "capacidad_total": capacidad_total,
            "muestra": muestra,
        }

    def perfil(self) -> str:
        try:
            total = self._get({"$select": "count(*) as total"})
            sample = self._get({"$limit": 1})
            total_rows = int(_number(total[0].get("total"))) if total else 0
            columns = ", ".join(sample[0].keys()) if sample else "sin columnas disponibles"
            return (
                f"Fuente exclusiva: datos.gov.co, dataset s2ru-bqt6. "
                f"La API contiene {total_rows} registros y las columnas disponibles son: {columns}. "
                "Cada consulta se resuelve en vivo mediante SoQL; no se usa una copia local."
            )
        except SocrataUnavailable:
            return (
                "Fuente exclusiva: datos.gov.co, dataset s2ru-bqt6. "
                "El perfil detallado no pudo cargarse ahora; las consultas se intentarán en vivo. "
                "No se usa una copia local."
            )
