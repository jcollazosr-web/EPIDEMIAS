# -*- coding: utf-8 -*-
"""
clusters.py — Agrupa las ubicaciones de un brote en clusters geográficos
por proximidad, para poder calcular métricas (velocidad de transmisión,
casos totales, etc.) de forma independiente por cada foco del brote.

Método: distancia haversine (línea recta sobre la esfera terrestre) +
Union-Find. Dos ubicaciones quedan en el mismo cluster si la distancia
entre ellas es menor o igual al radio configurado — es un método simple
de encadenamiento por cercanía, no un algoritmo de clustering estadístico
como k-means o DBSCAN, pero es transparente y no requiere elegir un
número de clusters de antemano.
"""
import math

RADIO_KM_DEFECTO = 15.0


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1.0, a)))


def detectar_clusters(ubicaciones: list, radio_km: float = RADIO_KM_DEFECTO) -> list:
    """
    `ubicaciones`: lista de dicts, cada uno con al menos 'id', 'latitud',
    'longitud' (y cualquier otro campo que quieras conservar, como
    'etiqueta'). Ubicaciones sin coordenadas se ignoran.

    Devuelve una lista de clusters; cada cluster es una lista de las
    ubicaciones que quedaron agrupadas.
    """
    validas = [u for u in ubicaciones if u.get("latitud") is not None and u.get("longitud") is not None]
    n = len(validas)
    if n == 0:
        return []

    padre = list(range(n))

    def encontrar(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    def unir(x, y):
        rx, ry = encontrar(x), encontrar(y)
        if rx != ry:
            padre[rx] = ry

    for i in range(n):
        for j in range(i + 1, n):
            d = _haversine_km(validas[i]["latitud"], validas[i]["longitud"], validas[j]["latitud"], validas[j]["longitud"])
            if d <= radio_km:
                unir(i, j)

    grupos = {}
    for i in range(n):
        raiz = encontrar(i)
        grupos.setdefault(raiz, []).append(validas[i])

    # Clusters más grandes (más ubicaciones) primero
    return sorted(grupos.values(), key=len, reverse=True)


def etiquetar_cluster(cluster: list) -> str:
    """Nombre legible para un cluster, usando los nombres de sus ubicaciones."""
    nombres = [u.get("etiqueta") or u.get("nombre") or "Ubicación sin nombre" for u in cluster]
    if len(nombres) <= 2:
        return " y ".join(nombres)
    return f"{nombres[0]}, {nombres[1]} y {len(nombres) - 2} más"
