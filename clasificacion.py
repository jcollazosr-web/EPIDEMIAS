# -*- coding: utf-8 -*-
"""
clasificacion.py — Clasifica la fase de un brote (aceleración / meseta /
desaceleración) por vía de contagio.

IMPORTANTE — transparencia sobre el método actual:
Entrenar un clasificador de Machine Learning real requiere ejemplos
históricos etiquetados (brotes pasados ya clasificados en sus fases),
que no existen todavía en una app recién lanzada. Por eso, hasta que
acumules ese histórico (ver sugerencia_modelos.UMBRAL_ML_POR_VIA),
esta función usa una regla estadística directa sobre la tasa de
crecimiento (la misma que ya calculas en calculos.py), NO un modelo
entrenado. Es una decisión deliberada: es más honesto que fingir una
predicción de ML sin datos para respaldarla.

Cuando acumules suficiente histórico (múltiples brotes/periodos ya
resueltos, cada uno con su fase real conocida en retrospectiva), este
mismo módulo es el lugar natural para entrenar un
RandomForestClassifier con esos ejemplos y reemplazar la regla de abajo.
"""

UMBRAL_ACELERACION = 0.05      # r > esto: creciendo de forma sostenida
UMBRAL_DESACELERACION = -0.05  # r < esto: bajando de forma sostenida


def clasificar_fase_heuristica(tasa_r) -> dict:
    """
    Clasifica la fase usando la tasa de crecimiento diaria (r) ya calculada
    por calculos.tasa_crecimiento_y_duplicacion. No es un modelo entrenado.
    """
    if tasa_r is None:
        return {"fase": "Sin datos suficientes", "metodo": "heurístico", "color": "⚪"}

    if tasa_r > UMBRAL_ACELERACION:
        return {"fase": "Aceleración", "metodo": "heurístico", "color": "🔴"}
    elif tasa_r < UMBRAL_DESACELERACION:
        return {"fase": "Desaceleración", "metodo": "heurístico", "color": "🟢"}
    else:
        return {"fase": "Meseta", "metodo": "heurístico", "color": "🟡"}


# -----------------------------------------------------------------------
# Perfiles orientativos de R0 por tipo de vía de contagio.
#
# IMPORTANTE: son rangos TÍPICOS reportados en la literatura general de
# epidemiología para ilustrar órdenes de magnitud — NO son un valor fijo
# ni específico de tu brote. El R0 real de cualquier enfermedad depende
# de la enfermedad concreta, no solo de su categoría de transmisión.
# Úsalos como punto de partida para el estimador de subregistro, ajusta
# siempre con literatura específica de tu patógeno cuando la tengas.
# -----------------------------------------------------------------------
PERFILES_R0_POR_TIPO_VIA = {
    "respiratoria": {
        "etiqueta": "Respiratoria (gotículas/aerosoles)",
        "r0_sugerido": 2.5,
        "rango": (1.5, 6.0),
        "nota": "Muy variable: desde influenza estacional (~1.3) hasta sarampión (~15). 2.5 es un punto medio ilustrativo, no una regla.",
    },
    "contacto_directo": {
        "etiqueta": "Contacto directo",
        "r0_sugerido": 1.5,
        "rango": (1.1, 3.0),
        "nota": "Suele crecer más lento que la vía respiratoria al depender de contacto físico o fluidos.",
    },
    "zoonotica": {
        "etiqueta": "Zoonótica (animal → humano)",
        "r0_sugerido": 1.2,
        "rango": (0.5, 2.0),
        "nota": "Muchas zoonosis tienen R0 < 1 en transmisión humano-humano (el reservorio es animal) — verifica si tu brote realmente sostiene transmisión de persona a persona.",
    },
    "vectorial": {
        "etiqueta": "Vectorial (mosquito, garrapata, etc.)",
        "r0_sugerido": 2.0,
        "rango": (1.0, 5.0),
        "nota": "Depende fuertemente de la densidad del vector en la zona y la estación — el R0 vectorial varía mucho más geográficamente que otras vías.",
    },
    "hidrica_alimentaria": {
        "etiqueta": "Hídrica/alimentaria",
        "r0_sugerido": 1.8,
        "rango": (1.0, 3.0),
        "nota": "Depende críticamente del acceso a agua potable y saneamiento en la zona del brote.",
    },
    "sexual": {
        "etiqueta": "Transmisión sexual",
        "r0_sugerido": 1.3,
        "rango": (0.8, 4.0),
        "nota": "Muy dependiente del comportamiento poblacional y la red de contactos, más que de la biología del patógeno.",
    },
    "otra": {
        "etiqueta": "Otra / no especificada",
        "r0_sugerido": 2.0,
        "rango": (1.0, 3.0),
        "nota": "Sin un perfil específico — usa literatura de tu patógeno concreto si la tienes.",
    },
}


def obtener_perfil_r0(tipo_via: str) -> dict:
    return PERFILES_R0_POR_TIPO_VIA.get(tipo_via, PERFILES_R0_POR_TIPO_VIA["otra"])
