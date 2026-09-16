# -*- coding: utf-8 -*-
"""
sugerencia_modelos.py — Recomienda qué modelo(s) predictivos usar
según cuántos registros hay disponibles (agregado y por vía de contagio).

Los umbrales están documentados en cada rama; el ajuste real de cada
modelo (regresión, SIR, ARIMA, ML) se implementa en módulos aparte y
se conecta aquí como siguiente paso.
"""

NOMBRES_LEGIBLES = {
    "regresion_log_lineal": "Regresión log-lineal (tendencia básica)",
    "sir_seir_ajustado": "Modelo SIR/SEIR ajustado",
    "suavizado_holt": "Suavizado exponencial (Holt)",
    "arima": "ARIMA",
    "ml_clasificacion_fase": "Clasificación de fase por Machine Learning",
}

UMBRAL_MINIMO = 5
UMBRAL_SIR = 15
UMBRAL_HOLT = 30
UMBRAL_ARIMA = 50
UMBRAL_ML = 100
UMBRAL_ML_POR_VIA = 30


def sugerir_modelo(n_registros: int, n_por_via: dict[str, int] | None = None) -> dict:
    """
    Devuelve qué modelos están disponibles dado el volumen de datos,
    y qué vías específicas ya tienen suficiente volumen para ML.
    """
    if n_registros < UMBRAL_MINIMO:
        return {
            "modelos_disponibles": [],
            "vias_con_ml_habilitado": [],
            "mensaje": (
                f"Con menos de {UMBRAL_MINIMO} registros no es posible estimar "
                "ninguna tendencia confiable. Solo se muestra la tabla descriptiva."
            ),
        }

    disponibles = ["regresion_log_lineal"]
    if n_registros >= UMBRAL_SIR:
        disponibles.append("sir_seir_ajustado")
    if n_registros >= UMBRAL_HOLT:
        disponibles.append("suavizado_holt")
    if n_registros >= UMBRAL_ARIMA:
        disponibles.append("arima")
    if n_registros >= UMBRAL_ML:
        disponibles.append("ml_clasificacion_fase")

    vias_ml = []
    if n_por_via:
        vias_ml = [via for via, n in n_por_via.items() if n >= UMBRAL_ML_POR_VIA]

    ultimo = NOMBRES_LEGIBLES[disponibles[-1]]
    return {
        "modelos_disponibles": disponibles,
        "vias_con_ml_habilitado": vias_ml,
        "mensaje": f"Con {n_registros} registros, el modelo más avanzado disponible es: {ultimo}.",
    }


def nivel_semaforo(n_registros: int) -> str:
    """Para el badge visual en la UI: rojo / amarillo / verde."""
    if n_registros < UMBRAL_MINIMO:
        return "🔴"
    if n_registros < UMBRAL_ML:
        return "🟡"
    return "🟢"
