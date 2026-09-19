# -*- coding: utf-8 -*-
"""
fuentes_externas.py — Conexión configurable a fuentes de datos externas
de solo lectura, sin necesidad de credenciales.

Reemplaza al antiguo `datos_oficiales.py` (que estaba fijo al dataset de
COVID-19 de Colombia). Ahora el usuario configura, desde la interfaz,
cualquier fuente de estos dos tipos:

- **Socrata**: la tecnología detrás de cientos de portales de datos
  abiertos gubernamentales en el mundo (Colombia, EE.UU., y muchos más).
  Solo se necesita el dominio y el ID del dataset — sin credenciales,
  sin costo, de solo lectura.
- **API REST genérica**: cualquier endpoint que devuelva JSON, con una
  ruta simple para extraer la lista de registros de la respuesta.

IMPORTANTE — límite deliberado: esto NO conecta bases de datos SQL
externas reales (como el servidor de una IPS). Eso requeriría guardar
credenciales y ejecutar consultas arbitrarias, con riesgos de seguridad
serios (inyección SQL, filtración de credenciales) que van más allá de
una conexión de solo lectura a datos públicos.
"""
import requests


def consultar_socrata(dominio: str, dataset_id: str, campo_filtro: str = None, valor_filtro: str = None,
                       campo_fecha: str = None, fecha_desde: str = None, fecha_hasta: str = None,
                       limite: int = 5000) -> dict:
    """
    Consulta cualquier dataset de Socrata (formato estándar en cientos de
    portales de datos abiertos). `dominio` es solo el host, ej.
    'www.datos.gov.co' o 'data.cityofnewyork.us' (sin https://).
    """
    url = f"https://{dominio}/resource/{dataset_id}.json"

    condiciones = []
    if campo_filtro and valor_filtro:
        condiciones.append(f"upper({campo_filtro}) = upper('{valor_filtro}')")
    if campo_fecha and fecha_desde:
        condiciones.append(f"{campo_fecha} >= '{fecha_desde}T00:00:00.000'")
    if campo_fecha and fecha_hasta:
        condiciones.append(f"{campo_fecha} <= '{fecha_hasta}T23:59:59.000'")

    params = {"$limit": limite}
    if condiciones:
        params["$where"] = " AND ".join(condiciones)

    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        datos = resp.json()
        return {"valido": True, "datos": datos, "mensaje": f"{len(datos)} registros encontrados."}
    except requests.exceptions.RequestException as e:
        return {"valido": False, "datos": [], "mensaje": f"No se pudo consultar la fuente: {e}"}
    except Exception as e:
        return {"valido": False, "datos": [], "mensaje": f"Respuesta inesperada de la fuente: {e}"}


def consultar_api_rest(url: str, ruta_lista: str = "") -> dict:
    """
    Consulta un endpoint REST genérico que devuelve JSON.
    `ruta_lista`: si los registros vienen anidados (ej. {"data": {"items": [...]}}),
    indica la ruta separada por puntos hasta la lista (ej. "data.items").
    Déjalo vacío si la respuesta ya es directamente una lista.
    """
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        datos = resp.json()

        if ruta_lista:
            for clave in ruta_lista.split("."):
                datos = datos[clave]

        if not isinstance(datos, list):
            return {"valido": False, "datos": [], "mensaje": "La ruta indicada no apunta a una lista de registros."}

        return {"valido": True, "datos": datos, "mensaje": f"{len(datos)} registros encontrados."}
    except requests.exceptions.RequestException as e:
        return {"valido": False, "datos": [], "mensaje": f"No se pudo consultar la fuente: {e}"}
    except (KeyError, TypeError):
        return {"valido": False, "datos": [], "mensaje": f"No se encontró la ruta '{ruta_lista}' en la respuesta."}
    except Exception as e:
        return {"valido": False, "datos": [], "mensaje": f"Respuesta inesperada de la fuente: {e}"}
