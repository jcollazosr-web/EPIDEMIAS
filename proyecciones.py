# -*- coding: utf-8 -*-
"""
proyecciones.py — Proyección a futuro con banda de incertidumbre.

Todas las proyecciones se reportan con banda de ±2 desviaciones estándar
de los residuales del ajuste (≈95% de cobertura si los residuales son
aproximadamente normales). El ajuste se hace en escala logarítmica sobre
casos activos (estándar en modelos de crecimiento epidémico) y se
retransforma a la escala original con exp(), lo que evita que la banda
baje de cero — un error común si se aplica ±2σ directamente en la escala
de casos.

Requiere al menos 5 puntos válidos (mismo umbral que
sugerencia_modelos.UMBRAL_MINIMO) para que el ajuste tenga sentido.
"""
import math
from datetime import timedelta

import numpy as np


N_SIGMAS = 2  # ±2 desviaciones estándar ≈ 95% de cobertura


def proyectar_regresion_log_lineal(serie: list[dict], dias_futuros: int = 7) -> dict:
    """
    Ajusta log(casos_activos + 1) = a + b*t por mínimos cuadrados, y
    proyecta `dias_futuros` días adelante con banda de ±2 sigma de los
    residuales del ajuste (en escala log, retransformada a escala real).

    Devuelve también la tasa de crecimiento diaria (b) y su banda,
    para que sea consistente con calculos.tasa_crecimiento_y_duplicacion.
    """
    puntos = [(i, r["casos_activos"]) for i, r in enumerate(serie) if r.get("casos_activos") is not None]

    if len(puntos) < 5:
        return {
            "valido": False,
            "mensaje": "Se requieren al menos 5 días con datos para proyectar con una banda de incertidumbre confiable.",
            "proyeccion": [],
        }

    t = np.array([p[0] for p in puntos], dtype=float)
    y_log = np.log(np.array([p[1] for p in puntos], dtype=float) + 1)

    # Ajuste por mínimos cuadrados: y_log = a + b*t
    b, a = np.polyfit(t, y_log, 1)

    # Desviación estándar de los residuales del ajuste (en escala log)
    y_pred = a + b * t
    residuales = y_log - y_pred
    grados_libertad = max(1, len(puntos) - 2)  # -2 por los dos parámetros estimados (a, b)
    sigma = float(np.sqrt(np.sum(residuales ** 2) / grados_libertad))

    ultima_fecha = serie[-1]["fecha"]
    if isinstance(ultima_fecha, str):
        from datetime import datetime
        ultima_fecha = datetime.strptime(ultima_fecha[:10], "%Y-%m-%d").date()

    t_max = t[-1]
    proyeccion = []
    for paso in range(1, dias_futuros + 1):
        t_futuro = t_max + paso
        log_central = a + b * t_futuro

        log_inferior = log_central - N_SIGMAS * sigma
        log_superior = log_central + N_SIGMAS * sigma

        proyeccion.append({
            "fecha": ultima_fecha + timedelta(days=paso),
            "valor_central": max(0.0, math.exp(log_central) - 1),
            "limite_inferior": max(0.0, math.exp(log_inferior) - 1),
            "limite_superior": max(0.0, math.exp(log_superior) - 1),
        })

    return {
        "valido": True,
        "mensaje": (
            f"Proyección con banda de ±{N_SIGMAS} desviaciones estándar "
            f"(≈95% de cobertura si los residuales son aproximadamente normales)."
        ),
        "tasa_crecimiento_diaria": float(b),
        "sigma_residual_log": sigma,
        "n_dias_usados_en_ajuste": len(puntos),
        "proyeccion": proyeccion,
    }
