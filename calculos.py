# -*- coding: utf-8 -*-
"""
calculos.py — Lógica de cálculo epidemiológico.

Adaptado del script de consola original (SEGUIMIENTO_EPIDEMIA.py):
misma corrección de Rt (NaN en el primer día en vez de 0.0) y de
"sumar Rt no tiene sentido, se promedia", pero ahora capaz de calcular
todo agregado O desglosado por vía de contagio.
"""
from datetime import datetime
import math
from collections import defaultdict


def _to_fecha(valor):
    if isinstance(valor, str):
        return datetime.strptime(valor[:10], "%Y-%m-%d").date()
    return valor


def recalcular_serie(registros: list[dict]) -> list[dict]:
    """
    Recibe una lista de registros de UNA sola serie (ya sea el agregado
    total o una vía específica) y calcula casos_activos y rt_efectivo
    para cada uno, en orden cronológico.
    """
    serie = sorted(registros, key=lambda r: _to_fecha(r["fecha"]))

    acum_casos = acum_fallecidos = acum_recuperados = 0
    resultado = []

    for i, r in enumerate(serie):
        acum_casos += r["casos_nuevos"]
        acum_fallecidos += r["fallecidos"]
        acum_recuperados += r["recuperados"]

        casos_activos = max(0, acum_casos - acum_fallecidos - acum_recuperados)

        if i > 0:
            anterior = resultado[i - 1]["casos_activos"]
            rt = (casos_activos / anterior) if anterior > 0 else 0.0
        else:
            rt = float("nan")  # No definido: no hay día anterior con qué comparar

        resultado.append({
            **r,
            "casos_activos": casos_activos,
            "rt_efectivo": rt,
            "casos_acumulados": acum_casos,
            "fallecidos_acumulados": acum_fallecidos,
            "recuperados_acumulados": acum_recuperados,
        })

    return resultado


def recalcular_por_via(registros: list[dict]) -> dict[str, list[dict]]:
    """Agrupa por vía de contagio y recalcula cada serie por separado,
    además del agregado total bajo la llave 'TOTAL'."""
    por_via = defaultdict(list)
    for r in registros:
        nombre_via = (r.get("vias_contagio") or {}).get("nombre", "Sin vía")
        por_via[nombre_via].append(r)

    resultado = {via: recalcular_serie(regs) for via, regs in por_via.items()}
    resultado["TOTAL"] = recalcular_serie(registros)
    return resultado


def tasa_crecimiento_y_duplicacion(serie: list[dict]) -> dict:
    """
    Calcula la tasa de crecimiento instantánea r = ln(C_t / C_t-1) sobre
    casos activos, y el tiempo de duplicación T_d = ln(2)/r.
    Es la forma más directa y explicable de "velocidad de transmisión".
    """
    activos = [r["casos_activos"] for r in serie if r["casos_activos"] is not None]
    activos = [a for a in activos if a > 0]

    if len(activos) < 2:
        return {"tasa_r": None, "dias_duplicacion": None}

    tasas = []
    for i in range(1, len(activos)):
        if activos[i - 1] > 0:
            tasas.append(math.log(activos[i] / activos[i - 1]))

    if not tasas:
        return {"tasa_r": None, "dias_duplicacion": None}

    r_prom = sum(tasas) / len(tasas)
    dias_dup = (math.log(2) / r_prom) if r_prom > 0 else None

    return {"tasa_r": r_prom, "dias_duplicacion": dias_dup}


def comparar_velocidad_por_via(por_via: dict[str, list[dict]]) -> list[dict]:
    """
    Calcula, para cada vía (y el TOTAL), la tasa de crecimiento y los días
    de duplicación — para poder verlas todas lado a lado y comparar cuál
    se está expandiendo más rápido en la ventana actual.
    """
    resultado = []
    for nombre_via, serie in por_via.items():
        velocidad = tasa_crecimiento_y_duplicacion(serie)
        resultado.append({
            "via": nombre_via,
            "tasa_r": velocidad["tasa_r"],
            "dias_duplicacion": velocidad["dias_duplicacion"],
            "casos_activos_actuales": serie[-1]["casos_activos"] if serie else 0,
        })
    return sorted(resultado, key=lambda r: (r["tasa_r"] is None, -(r["tasa_r"] or 0)))


def agregar_casos_por_ubicacion(registros: list[dict]) -> list[dict]:
    """
    Suma los casos nuevos por ubicación (para el mapa de burbujas).
    Ignora registros sin ubicación asignada. El nombre mostrado usa el
    nivel más específico disponible (barrio > ciudad > departamento > país).
    """
    acumulado: dict[int, dict] = {}

    for r in registros:
        ubic = r.get("ubicaciones")
        if not ubic or ubic.get("latitud") is None or ubic.get("longitud") is None:
            continue

        clave = (ubic["latitud"], ubic["longitud"])
        if clave not in acumulado:
            nombre = ubic.get("barrio") or ubic.get("ciudad") or ubic.get("departamento") or ubic.get("pais")
            etiqueta_completa = ", ".join(
                p for p in [ubic.get("barrio"), ubic.get("ciudad"), ubic.get("departamento"), ubic.get("pais")] if p
            )
            acumulado[clave] = {
                "nombre": nombre,
                "etiqueta_completa": etiqueta_completa,
                "latitud": ubic["latitud"],
                "longitud": ubic["longitud"],
                "casos_totales": 0,
                "fallecidos_totales": 0,
            }

        acumulado[clave]["casos_totales"] += r["casos_nuevos"]
        acumulado[clave]["fallecidos_totales"] += r["fallecidos"]

    return list(acumulado.values())


def encontrar_pico(serie: list[dict]) -> dict | None:
    """Día con el máximo de casos activos — para anotarlo en el gráfico."""
    validos = [r for r in serie if r.get("casos_activos") is not None]
    if not validos:
        return None
    return max(validos, key=lambda r: r["casos_activos"])


def calcular_fase_por_dia(serie: list[dict], ventana: int = 4) -> list[str | None]:
    """
    Calcula la tasa de crecimiento con una ventana móvil corta (por
    defecto 4 días) para CADA día de la serie, y clasifica su fase.
    Se usa para dibujar líneas de cambio de fase sobre el gráfico
    (dónde el brote pasó de aceleración a meseta, etc.) — es una
    heurística de suavizado local, no un recálculo de todo el histórico.
    """
    # Import local para evitar dependencia circular con clasificacion.py
    import clasificacion

    fases = []
    for i in range(len(serie)):
        sub = serie[max(0, i - ventana + 1): i + 1]
        vel = tasa_crecimiento_y_duplicacion(sub)
        fase = clasificacion.clasificar_fase_heuristica(vel["tasa_r"])
        fases.append(fase["fase"])
    return fases


def detectar_cambios_de_fase(serie: list[dict], ventana: int = 4) -> list[dict]:
    """Devuelve solo los días donde la fase CAMBIÓ respecto al día anterior
    (para no saturar el gráfico con una línea por cada día)."""
    fases = calcular_fase_por_dia(serie, ventana=ventana)
    cambios = []
    anterior = None
    for i, fase in enumerate(fases):
        if fase != anterior and fase != "Sin datos suficientes":
            cambios.append({"fecha": serie[i]["fecha"], "fase": fase})
        anterior = fase
    return cambios
