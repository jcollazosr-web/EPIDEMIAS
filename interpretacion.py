# -*- coding: utf-8 -*-
"""
interpretacion.py — Genera una explicación en lenguaje sencillo de lo
que muestran las gráficas del dashboard, usando la API de Claude
(Anthropic). Requiere que el usuario configure su propia
ANTHROPIC_API_KEY en los secrets — esta app no incluye una clave propia.
"""

MODELO = "claude-sonnet-5"


def generar_interpretacion(resumen: dict, api_key: str) -> dict:
    """
    `resumen` trae los números YA CALCULADOS por la app (no se le pide a
    la IA que "lea" la gráfica ni que haga cálculos — solo que traduzca
    cifras que la propia app ya validó a un lenguaje sencillo, evitando
    que invente números).
    """
    try:
        import anthropic
    except ImportError:
        return {"valido": False, "mensaje": "Falta instalar la librería 'anthropic' en requirements.txt."}

    if not api_key:
        return {
            "valido": False,
            "mensaje": (
                "Para activar esta función, agrega tu propia clave de Anthropic como "
                "ANTHROPIC_API_KEY en los secrets de la app (console.anthropic.com)."
            ),
        }

    prompt = """Eres un asistente que le explica datos epidemiológicos a alguien SIN formación técnica en estadística. Usa lenguaje simple, sin jerga, en español. No inventes ningún número que no esté en los datos de abajo — solo interprétalos.

Brote: {brote_nombre}
Serie mostrada: {vista}
Casos activos actuales: {casos_activos_actuales}
Tasa de crecimiento diaria (r): {tasa_r}
Días para duplicar los casos activos: {dias_duplicacion}
Fase estimada: {fase}
Rt del último día: {rt_ultimo}

Escribe 3-4 frases explicando qué significa esto en términos prácticos para alguien que no es epidemiólogo. Si algún dato es "N/D" o None, no lo menciones.""".format(**resumen)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        respuesta = client.messages.create(
            model=MODELO,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = "".join(bloque.text for bloque in respuesta.content if hasattr(bloque, "text"))
        return {"valido": True, "texto": texto}
    except Exception as e:
        return {"valido": False, "mensaje": f"No se pudo generar la interpretación: {e}"}
