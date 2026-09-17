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
