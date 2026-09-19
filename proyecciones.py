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

from clasificacion import obtener_perfil_r0


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


def ajustar_crecimiento_logistico(serie: list[dict], dias_futuros: int = 7, tipo_via: str = None) -> dict:
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

    Si se indica `tipo_via` (respiratoria, zoonótica, etc.), su R0 de
    referencia se usa como PUNTO DE PARTIDA del ajuste (no como un valor
    impuesto — el ajuste sigue basándose en tus datos reales), y además
    se calcula el R0 EFECTIVO que tus propios datos implican, para
    compararlo contra lo típico de esa vía — así la vía deja de ser solo
    una etiqueta y pasa a informar la simulación.
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

    # Punto de partida del parámetro r: si conocemos el tipo de vía, se
    # usa su R0 de referencia (vía la relación R0 ≈ 1 + r·T_generacional)
    # en vez del valor genérico 0.3 — ayuda a converger mejor,
    # especialmente con pocos datos.
    r_inicial = 0.3
    perfil_via = None
    if tipo_via:
        perfil_via = obtener_perfil_r0(tipo_via)
        t_gen = perfil_via["intervalo_generacional_dias"]
        r_inicial = (perfil_via["r0_sugerido"] - 1) / t_gen

    try:
        K0 = max(acumulado) * 2
        p0 = [K0, r_inicial, float(np.median(t))]
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

    # Banda de incertidumbre ±2σ sobre los residuales del ajuste (en
    # escala de casos acumulados) — mismo criterio que en la regresión.
    acumulado_ajustado = logistico(t, K, r, t0)
    residuales = acumulado - acumulado_ajustado
    grados_libertad = max(1, len(t) - 3)  # -3 por K, r, t0
    sigma = float(np.sqrt(np.sum(residuales ** 2) / grados_libertad))

    t_max = t[-1]
    proyeccion = []
    acumulado_anterior = logistico(t_max, K, r, t0)
    for paso in range(1, dias_futuros + 1):
        t_futuro = t_max + paso
        acumulado_futuro = logistico(t_futuro, K, r, t0)
        acumulado_inf = max(0.0, acumulado_futuro - N_SIGMAS * sigma)
        acumulado_sup = acumulado_futuro + N_SIGMAS * sigma
        nuevos_del_dia = max(0.0, acumulado_futuro - acumulado_anterior)
        proyeccion.append({
            "fecha": ultima_fecha + timedelta(days=paso),
            "casos_acumulados_proyectados": float(acumulado_futuro),
            "casos_acumulados_limite_inferior": float(acumulado_inf),
            "casos_acumulados_limite_superior": float(acumulado_sup),
            "casos_nuevos_proyectados": float(nuevos_del_dia),
        })
        acumulado_anterior = acumulado_futuro

    resultado = {
        "valido": True,
        "mensaje": (
            "Modelo de crecimiento logístico (equivalente a un SIR simplificado sin "
            f"necesitar el tamaño de la población), con banda de ±{N_SIGMAS} desviaciones "
            "estándar sobre los residuales del ajuste."
        ),
        "K_techo_estimado": float(K),
        "r_tasa_crecimiento": float(r),
        "t0_dia_pico_estimado": float(t0),
        "sigma_residual": sigma,
        "n_dias_usados_en_ajuste": len(puntos),
        "proyeccion": proyeccion,
    }

    if perfil_via:
        t_gen = perfil_via["intervalo_generacional_dias"]
        r0_efectivo = 1 + r * t_gen
        rango_min, rango_max = perfil_via["rango"]
        dentro_de_rango = rango_min <= r0_efectivo <= rango_max
        resultado["r0_efectivo_estimado"] = r0_efectivo
        resultado["r0_tipico_via"] = perfil_via["r0_sugerido"]
        resultado["r0_rango_tipico_via"] = perfil_via["rango"]
        resultado["r0_dentro_de_rango_tipico"] = dentro_de_rango
        resultado["mensaje"] += (
            f" R0 efectivo estimado desde tus datos: {r0_efectivo:.2f} "
            f"({'dentro' if dentro_de_rango else '⚠️ fuera'} del rango típico "
            f"{rango_min}-{rango_max} para {perfil_via['etiqueta']})."
        )

    return resultado


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


# -----------------------------------------------------------------------
# Descomposición de cualquier proyección en sus 4 componentes:
# casos nuevos, casos activos, recuperados y fallecidos.
#
# Los modelos de arriba proyectan una sola cantidad (casos activos, o
# casos nuevos en el caso logístico). Para desglosarla en las otras tres,
# se usan las tasas HISTÓRICAS de letalidad y recuperación del propio
# brote (fallecidos/nuevos y recuperados/nuevos acumulados), aplicadas
# hacia adelante junto con la identidad contable:
#
#     activos_t = activos_(t-1) + nuevos_t - fallecidos_t - recuperados_t
#
# Es una extrapolación transparente de patrones ya observados en el
# brote, no un modelo nuevo — por eso los cuatro modelos de arriba
# pueden reutilizar esta misma función.
# -----------------------------------------------------------------------
def calcular_tasas_historicas(serie: list[dict]) -> tuple[float, float]:
    total_nuevos = sum(r["casos_nuevos"] for r in serie)
    total_fallecidos = sum(r["fallecidos"] for r in serie)
    total_recuperados = sum(r["recuperados"] for r in serie)

    if total_nuevos == 0:
        return 0.0, 0.0

    tasa_letalidad = total_fallecidos / total_nuevos
    tasa_recuperacion = total_recuperados / total_nuevos

    # Deja al menos un 5% de margen para que la identidad contable
    # (activos = nuevos - fallecidos - recuperados) no se vuelva inestable.
    if tasa_letalidad + tasa_recuperacion >= 0.95:
        factor = 0.95 / (tasa_letalidad + tasa_recuperacion)
        tasa_letalidad *= factor
        tasa_recuperacion *= factor

    return tasa_letalidad, tasa_recuperacion


def descomponer_proyeccion_desde_activos(serie: list[dict], activos_futuros: list[dict]) -> list[dict]:
    """activos_futuros: [{'fecha':..., 'valor': casos_activos_proyectados}, ...]"""
    tasa_letalidad, tasa_recuperacion = calcular_tasas_historicas(serie)
    denominador = 1 - tasa_letalidad - tasa_recuperacion

    activos_previos = [r["casos_activos"] for r in serie if r.get("casos_activos") is not None]
    activos_anterior = activos_previos[-1] if activos_previos else 0.0

    resultado = []
    for punto in activos_futuros:
        activos_t = punto["valor"]
        delta = activos_t - activos_anterior
        nuevos_t = max(0.0, delta / denominador) if denominador > 0.05 else max(0.0, delta)
        fallecidos_t = nuevos_t * tasa_letalidad
        recuperados_t = nuevos_t * tasa_recuperacion
        resultado.append({
            "fecha": punto["fecha"],
            "casos_nuevos_proyectados": nuevos_t,
            "casos_activos_proyectados": activos_t,
            "recuperados_proyectados": recuperados_t,
            "fallecidos_proyectados": fallecidos_t,
        })
        activos_anterior = activos_t
    return resultado


def descomponer_proyeccion_desde_nuevos(serie: list[dict], nuevos_futuros: list[dict]) -> list[dict]:
    """nuevos_futuros: [{'fecha':..., 'valor': casos_nuevos_proyectados}, ...]
    (usado por el modelo de crecimiento logístico, que ya proyecta nuevos directamente)."""
    tasa_letalidad, tasa_recuperacion = calcular_tasas_historicas(serie)

    activos_previos = [r["casos_activos"] for r in serie if r.get("casos_activos") is not None]
    activos_anterior = activos_previos[-1] if activos_previos else 0.0

    resultado = []
    for punto in nuevos_futuros:
        nuevos_t = punto["valor"]
        fallecidos_t = nuevos_t * tasa_letalidad
        recuperados_t = nuevos_t * tasa_recuperacion
        activos_t = max(0.0, activos_anterior + nuevos_t - fallecidos_t - recuperados_t)
        resultado.append({
            "fecha": punto["fecha"],
            "casos_nuevos_proyectados": nuevos_t,
            "casos_activos_proyectados": activos_t,
            "recuperados_proyectados": recuperados_t,
            "fallecidos_proyectados": fallecidos_t,
        })
        activos_anterior = activos_t
    return resultado


# -----------------------------------------------------------------------
# Estimación de infectados NO diagnosticados (subregistro), a partir del
# número reproductivo básico (R0), la población total y la susceptible.
#
# Usa la relación clásica de "tamaño final" de una epidemia SIR cerrada
# (Kermack-McKendrick): la fracción de la población susceptible que
# terminaría infectada, z, satisface:
#
#       z = 1 - exp(-R0 * z)
#
# resuelta por iteración de punto fijo. Es una idealización (asume
# población homogénea, epidemia que corre hasta su fin natural) — sirve
# como orden de magnitud orientativo, NO como conteo preciso en tiempo
# real. Se documenta así explícitamente en el mensaje de resultado.
# -----------------------------------------------------------------------
def estimar_infectados_no_diagnosticados(
    r0: float, poblacion_total: int, poblacion_susceptible: int, casos_diagnosticados_acumulados: int
) -> dict:
    if r0 <= 1:
        return {
            "valido": False,
            "mensaje": (
                "Con R0 ≤ 1 el modelo de tamaño final no aplica: la epidemia se apaga "
                "sin necesariamente alcanzar una fracción amplia de la población."
            ),
        }
    if poblacion_total <= 0 or poblacion_susceptible <= 0:
        return {"valido": False, "mensaje": "La población total y la susceptible deben ser mayores a cero."}

    z = 0.5
    for _ in range(500):
        z_nuevo = 1 - math.exp(-r0 * z)
        if abs(z_nuevo - z) < 1e-9:
            z = z_nuevo
            break
        z = z_nuevo

    infectados_totales_estimados = z * poblacion_susceptible
    no_diagnosticados = max(0.0, infectados_totales_estimados - casos_diagnosticados_acumulados)
    tasa_deteccion = (casos_diagnosticados_acumulados / infectados_totales_estimados) if infectados_totales_estimados > 0 else None

    return {
        "valido": True,
        "fraccion_final_infectada": z,
        "infectados_totales_estimados": infectados_totales_estimados,
        "casos_diagnosticados": casos_diagnosticados_acumulados,
        "no_diagnosticados_estimados": no_diagnosticados,
        "tasa_deteccion_estimada": tasa_deteccion,
        "mensaje": (
            "Estimación basada en la relación de tamaño final de un modelo SIR cerrado "
            "(supone población homogénea y que la epidemia corre hasta agotar su "
            "dinámica natural). Es un orden de magnitud orientativo para planeación, "
            "no un conteo preciso — útil para dimensionar capacidad, no para reportar "
            "cifras oficiales."
        ),
    }
