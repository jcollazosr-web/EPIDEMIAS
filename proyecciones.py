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


def ajustar_crecimiento_logistico(serie: list[dict], dias_futuros: int = 7) -> dict:
    """
    Ajusta un modelo de crecimiento logístico a los CASOS ACUMULADOS:

        C(t) = K / (1 + exp(-r * (t - t0)))

    Es la forma más simple y estándar de aproximar un SIR/SEIR cuando no
    se conoce el tamaño exacto de la población susceptible: K representa
    el techo de casos acumulados que alcanzaría el brote si nada cambia,
    r es la tasa de crecimiento (equivalente al β-γ de un SIR clásico),
    y t0 es el punto de inflexión (el día del pico de nuevos casos).

    Requiere al menos 8 puntos porque son 3 parámetros a estimar (K, r, t0)
    y con menos datos el ajuste no converge de forma confiable.
    """
    try:
        from scipy.optimize import curve_fit
    except ImportError:
        return {"valido": False, "mensaje": "Falta la librería 'scipy' para este modelo.", "proyeccion": []}

    puntos = [(i, r["casos_activos"]) for i, r in enumerate(serie) if r.get("casos_activos") is not None]
    if len(puntos) < 8:
        return {
            "valido": False,
            "mensaje": "Se requieren al menos 8 días con datos para ajustar un modelo de crecimiento logístico (SIR simplificado) de forma confiable.",
            "proyeccion": [],
        }

    t = np.array([p[0] for p in puntos], dtype=float)
    acumulado = np.cumsum([p[1] for p in puntos]).astype(float)

    def logistico(t, K, r, t0):
        return K / (1 + np.exp(-r * (t - t0)))

    try:
        K0 = max(acumulado) * 2
        p0 = [K0, 0.3, float(np.median(t))]
        parametros, _ = curve_fit(logistico, t, acumulado, p0=p0, maxfev=5000)
        K, r, t0 = parametros
    except Exception:
        return {
            "valido": False,
            "mensaje": "El modelo de crecimiento logístico no pudo ajustarse con estos datos (curva demasiado irregular o insuficiente variación).",
            "proyeccion": [],
        }

    ultima_fecha = serie[-1]["fecha"]
    if isinstance(ultima_fecha, str):
        from datetime import datetime
        ultima_fecha = datetime.strptime(ultima_fecha[:10], "%Y-%m-%d").date()

    t_max = t[-1]
    proyeccion = []
    acumulado_anterior = logistico(t_max, K, r, t0)
    for paso in range(1, dias_futuros + 1):
        t_futuro = t_max + paso
        acumulado_futuro = logistico(t_futuro, K, r, t0)
        nuevos_del_dia = max(0.0, acumulado_futuro - acumulado_anterior)
        proyeccion.append({
            "fecha": ultima_fecha + timedelta(days=paso),
            "casos_acumulados_proyectados": float(acumulado_futuro),
            "casos_nuevos_proyectados": float(nuevos_del_dia),
        })
        acumulado_anterior = acumulado_futuro

    return {
        "valido": True,
        "mensaje": (
            "Modelo de crecimiento logístico (equivalente a un SIR simplificado sin "
            "necesitar el tamaño de la población). K = techo estimado de casos acumulados."
        ),
        "K_techo_estimado": float(K),
        "r_tasa_crecimiento": float(r),
        "t0_dia_pico_estimado": float(t0),
        "n_dias_usados_en_ajuste": len(puntos),
        "proyeccion": proyeccion,
    }


def ajustar_arima(serie: list[dict], dias_futuros: int = 7, orden: tuple = (1, 1, 1)) -> dict:
    """
    Ajusta un ARIMA simple sobre casos activos y proyecta a futuro con su
    intervalo de confianza nativo (statsmodels ya calcula esto internamente,
    por eso aquí no se re-implementa la banda ±2σ manualmente).

    Requiere al menos 50 días — con menos, ARIMA no estima sus parámetros
    de forma confiable (ver sugerencia_modelos.UMBRAL_ARIMA).
    """
    try:
        from statsmodels.tsa.arima.model import ARIMA
    except ImportError:
        return {"valido": False, "mensaje": "Falta la librería 'statsmodels' para este modelo.", "proyeccion": []}

    valores = [r["casos_activos"] for r in serie if r.get("casos_activos") is not None]
    if len(valores) < 50:
        return {
            "valido": False,
            "mensaje": "Se requieren al menos 50 días con datos para que ARIMA estime sus parámetros de forma confiable.",
            "proyeccion": [],
        }

    ultima_fecha = serie[-1]["fecha"]
    if isinstance(ultima_fecha, str):
        from datetime import datetime
        ultima_fecha = datetime.strptime(ultima_fecha[:10], "%Y-%m-%d").date()

    try:
        modelo = ARIMA(valores, order=orden).fit()
        pronostico = modelo.get_forecast(steps=dias_futuros)
        medias = pronostico.predicted_mean
        intervalo = pronostico.conf_int(alpha=0.05)  # 95%, banda comparable a ±2σ
    except Exception as e:
        return {"valido": False, "mensaje": f"ARIMA no pudo ajustarse: {e}", "proyeccion": []}

    proyeccion = []
    for i in range(dias_futuros):
        proyeccion.append({
            "fecha": ultima_fecha + timedelta(days=i + 1),
            "valor_central": max(0.0, float(medias[i])),
            "limite_inferior": max(0.0, float(intervalo[i][0])),
            "limite_superior": max(0.0, float(intervalo[i][1])),
        })

    return {
        "valido": True,
        "mensaje": f"ARIMA{orden} ajustado sobre {len(valores)} días, con intervalo de confianza del 95%.",
        "n_dias_usados_en_ajuste": len(valores),
        "proyeccion": proyeccion,
    }
