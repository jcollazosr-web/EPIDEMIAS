# -*- coding: utf-8 -*-
"""
canal_endemico.py -- Construye el canal endemico (herramienta clasica de
vigilancia epidemiologica) a partir de casos historicos por semana
epidemiologica, usando el METODO DE CUARTILES:

    Zona de exito:        casos <= percentil 25 historico
    Zona de seguridad:    percentil 25 < casos <= mediana
    Zona de alerta:       mediana < casos <= percentil 75
    Zona de epidemia:     casos > percentil 75

Es uno de los metodos mas simples y ampliamente ensenados -- se eligio
por ser transparente y facil de explicar sin asumir una distribucion
especifica de los datos.

Se recomienda un MINIMO de 5 anios de datos historicos por semana para
que los percentiles tengan algun sentido estadistico.
"""
import statistics

ANIOS_MINIMOS_RECOMENDADOS = 5


def _percentil(valores: list, p: float) -> float:
    """Percentil simple por interpolacion lineal (metodo usado por
    numpy/excel por defecto) -- sin depender de numpy para esto."""
    if not valores:
        return 0.0
    datos = sorted(valores)
    n = len(datos)
    if n == 1:
        return float(datos[0])
    k = (n - 1) * (p / 100)
    f = int(k)
    c = f + 1 if f + 1 < n else f
    if f == c:
        return float(datos[f])
    return float(datos[f] + (datos[c] - datos[f]) * (k - f))


def calcular_canal_endemico(datos: list, anio_actual: int = None) -> dict:
    """
    `datos`: lista de {'anio': int, 'semana': int, 'casos': int}.
    `anio_actual`: si se indica, ese anio se EXCLUYE del historico (se
    usa como la curva a comparar contra el canal construido con los
    anios anteriores) y se devuelve por separado para superponer.

    Devuelve, por cada semana 1-52: percentil 25, mediana, percentil 75
    (las 3 lineas que definen las 4 zonas), mas los anios usados.
    """
    historicos = [d for d in datos if anio_actual is None or d["anio"] != anio_actual]
    actual = [d for d in datos if anio_actual is not None and d["anio"] == anio_actual]

    anios_usados = sorted(set(d["anio"] for d in historicos))

    por_semana = {}
    for d in historicos:
        por_semana.setdefault(d["semana"], []).append(d["casos"])

    bandas = []
    for semana in range(1, 53):
        valores = por_semana.get(semana, [])
        if valores:
            bandas.append({
                "semana": semana,
                "p25": _percentil(valores, 25),
                "mediana": statistics.median(valores),
                "p75": _percentil(valores, 75),
                "n_anios": len(valores),
            })
        else:
            bandas.append({"semana": semana, "p25": None, "mediana": None, "p75": None, "n_anios": 0})

    curva_actual = dict((d["semana"], d["casos"]) for d in actual)

    return {
        "bandas": bandas,
        "anios_usados": anios_usados,
        "n_anios_historicos": len(anios_usados),
        "advertencia_pocos_anios": len(anios_usados) < ANIOS_MINIMOS_RECOMENDADOS,
        "curva_actual": curva_actual,
    }


def clasificar_zona(casos_semana: int, banda_semana: dict) -> str:
    """Dado el numero de casos de una semana y su banda historica,
    devuelve en que zona cae."""
    if banda_semana["p25"] is None:
        return "Sin datos historicos suficientes"
    if casos_semana <= banda_semana["p25"]:
        return "Exito"
    if casos_semana <= banda_semana["mediana"]:
        return "Seguridad"
    if casos_semana <= banda_semana["p75"]:
        return "Alerta"
    return "Epidemia"
