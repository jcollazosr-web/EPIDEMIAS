# -*- coding: utf-8 -*-
"""
datos_oficiales.py — Comparación contra fuentes de datos abiertas del
Estado colombiano (datos.gov.co, API Socrata).

IMPORTANTE — alcance real de esta integración:
El portal de Datos Abiertos Colombia no tiene un dataset único para
"todas las epidemias" — cada enfermedad tiene su propio dataset (o no
tiene ninguno público). Esta integración viene configurada por defecto
con el dataset histórico de COVID-19 (el más completo y estable), y
deja el `dataset_id` como parámetro para que puedas apuntarla a otro
dataset de datos.gov.co si tu brote es de otra enfermedad — necesitas
buscar el "Dataset ID" (aparece en la URL del dataset, ej. gt2j-8ykr)
en https://www.datos.gov.co.

NOTA TÉCNICA: esta función se ejecuta en el servidor donde corre la
app (Streamlit Cloud), no en el entorno donde se escribió este código,
así que su acceso a internet depende de la red de ese servidor.
"""
import requests

DATASET_COVID_COLOMBIA = "gt2j-8ykr"  # Casos positivos de COVID-19 en Colombia
BASE_URL = "https://www.datos.gov.co/resource/{dataset_id}.json"


def obtener_casos_oficiales_por_departamento(
    departamento: str,
    fecha_desde: str,
    fecha_hasta: str,
    dataset_id: str = DATASET_COVID_COLOMBIA,
    limite: int = 5000,
) -> dict:
    """
    Consulta el dataset oficial filtrando por departamento y rango de
    fechas. Devuelve el conteo de casos oficiales por fecha, para
    comparar contra tus propios registros.

    fecha_desde / fecha_hasta: strings 'YYYY-MM-DD'.
    """
    url = BASE_URL.format(dataset_id=dataset_id)
    where = (
        f"upper(departamento) = upper('{departamento}') "
        f"AND fecha_reporte_web >= '{fecha_desde}T00:00:00.000' "
        f"AND fecha_reporte_web <= '{fecha_hasta}T23:59:59.000'"
    )
    params = {
        "$select": "fecha_reporte_web, count(*) as casos",
        "$where": where,
        "$group": "fecha_reporte_web",
        "$order": "fecha_reporte_web",
        "$limit": limite,
    }

    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        datos = resp.json()
        return {
            "valido": True,
            "datos": [{"fecha": d["fecha_reporte_web"][:10], "casos_oficiales": int(d["casos"])} for d in datos],
            "mensaje": f"{len(datos)} días con datos oficiales encontrados para {departamento}.",
        }
    except requests.exceptions.RequestException as e:
        return {
            "valido": False,
            "datos": [],
            "mensaje": f"No se pudo consultar Datos Abiertos Colombia: {e}",
        }
    except Exception as e:
        return {
            "valido": False,
            "datos": [],
            "mensaje": f"Respuesta inesperada del portal de datos abiertos: {e}",
        }
