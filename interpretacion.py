# -*- coding: utf-8 -*-
"""
interpretacion.py — Genera explicaciones en lenguaje sencillo de los
datos del dashboard, usando el proveedor de IA que el administrador
haya configurado (Anthropic, OpenAI, Google o DeepSeek).

Esta es una función PRO: el administrador decide, por usuario, quién
puede usarla (ver db.tiene_ia_habilitada). Este módulo solo se encarga
de llamar al proveedor configurado — no valida permisos, eso lo hace
la interfaz antes de invocarlo.
"""

PROVEEDORES = {
    "anthropic": {"etiqueta": "Anthropic (Claude)", "modelo_defecto": "claude-sonnet-5"},
    "openai": {"etiqueta": "OpenAI (GPT)", "modelo_defecto": "gpt-4o-mini"},
    "google": {"etiqueta": "Google (Gemini)", "modelo_defecto": "gemini-2.0-flash"},
    "deepseek": {"etiqueta": "DeepSeek", "modelo_defecto": "deepseek-chat"},
    # Groq descontinúa modelos con relativamente poco aviso (ver
    # console.groq.com/docs/deprecations) — si este deja de funcionar,
    # revisa esa página y actualiza el valor de 'modelo_defecto' aquí.
    "groq": {"etiqueta": "Groq (inferencia rápida)", "modelo_defecto": "openai/gpt-oss-120b"},
}


def _llamar_ia(prompt: str, api_key: str, proveedor: str, max_tokens: int = 500) -> str:
    """Despacha la llamada al SDK del proveedor configurado. Cada
    proveedor tiene su propia librería y formato de respuesta — esta
    función homogeneiza todo a un simple string de texto."""
    if proveedor not in PROVEEDORES:
        raise ValueError(f"Proveedor de IA desconocido: {proveedor}")

    modelo = PROVEEDORES[proveedor]["modelo_defecto"]

    if proveedor == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        respuesta = client.messages.create(model=modelo, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
        return "".join(bloque.text for bloque in respuesta.content if hasattr(bloque, "text"))

    elif proveedor == "openai":
        import openai
        client = openai.OpenAI(api_key=api_key)
        respuesta = client.chat.completions.create(model=modelo, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
        return respuesta.choices[0].message.content

    elif proveedor == "deepseek":
        # DeepSeek expone una API compatible con el formato de OpenAI —
        # se reutiliza el mismo SDK, solo cambiando la URL base.
        import openai
        client = openai.OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        respuesta = client.chat.completions.create(model=modelo, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
        return respuesta.choices[0].message.content

    elif proveedor == "groq":
        # Groq también expone una API compatible con el formato de OpenAI.
        import openai
        client = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        respuesta = client.chat.completions.create(model=modelo, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
        return respuesta.choices[0].message.content

    elif proveedor == "google":
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        cliente_modelo = genai.GenerativeModel(modelo)
        respuesta = cliente_modelo.generate_content(prompt)
        return respuesta.text


def generar_interpretacion(resumen: dict, api_key: str, proveedor: str = "anthropic") -> dict:
    """
    `resumen` trae los números YA CALCULADOS por la app (no se le pide a
    la IA que "lea" la gráfica ni que haga cálculos — solo que traduzca
    cifras que la propia app ya validó a un lenguaje sencillo, evitando
    que invente números).
    """
    if not api_key:
        return {
            "valido": False,
            "mensaje": (
                f"El administrador todavía no ha configurado una clave de "
                f"{PROVEEDORES.get(proveedor, {}).get('etiqueta', proveedor)} en el menú 🔑 Administrador."
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
        texto = _llamar_ia(prompt, api_key, proveedor, max_tokens=400)
        return {"valido": True, "texto": texto}
    except ImportError as e:
        return {"valido": False, "mensaje": f"Falta instalar la librería del proveedor {proveedor}: {e}"}
    except Exception as e:
        return {"valido": False, "mensaje": f"No se pudo generar la interpretación: {e}"}


def generar_analisis_descriptivo(titulo_grafico: str, resumen_datos: str, api_key: str, proveedor: str = "anthropic") -> dict:
    """Análisis descriptivo genérico de cualquier gráfico del dashboard,
    a partir de un resumen de texto de sus datos (ya calculados por la
    app, nunca inventados por la IA)."""
    if not api_key:
        return {
            "valido": False,
            "mensaje": (
                f"El administrador todavía no ha configurado una clave de "
                f"{PROVEEDORES.get(proveedor, {}).get('etiqueta', proveedor)} en el menú 🔑 Administrador."
            ),
        }

    prompt = f"""Eres un asistente que le explica datos epidemiológicos a alguien SIN formación técnica. Usa lenguaje simple, en español, sin jerga. No inventes ningún número que no esté en los datos de abajo.

Gráfico: {titulo_grafico}
Datos: {resumen_datos}

Escribe un análisis descriptivo breve (3-5 frases) de lo que muestra este gráfico en particular: la tendencia, algo que destaque, y qué debería observar quien lo mira."""

    try:
        texto = _llamar_ia(prompt, api_key, proveedor, max_tokens=350)
        return {"valido": True, "texto": texto}
    except ImportError as e:
        return {"valido": False, "mensaje": f"Falta instalar la librería del proveedor {proveedor}: {e}"}
    except Exception as e:
        return {"valido": False, "mensaje": f"No se pudo generar el análisis: {e}"}


def generar_analisis_completo(datos_texto: str, api_key: str, proveedor: str = "anthropic") -> dict:
    """
    Análisis integral del brote (no de un solo gráfico): situación
    actual, comparación entre vías, focos geográficos y proyección,
    con recomendaciones. Usa SOLO los datos ya calculados por la app,
    pasados en `datos_texto` — nunca inventa cifras.
    """
    if not api_key:
        return {
            "valido": False,
            "mensaje": (
                f"El administrador todavía no ha configurado una clave de "
                f"{PROVEEDORES.get(proveedor, {}).get('etiqueta', proveedor)} en el menú 🔑 Administrador."
            ),
        }

    prompt = f"""Eres un epidemiólogo asistente que ayuda a interpretar el estado de un brote a partir de datos YA CALCULADOS (nunca inventes números que no estén aquí). Escribe en español, para un lector con conocimiento básico de salud pública (no necesariamente estadístico).

Datos del brote:
{datos_texto}

Estructura tu respuesta en estas secciones cortas, con encabezados en negrita:
**Situación actual**: 2-3 frases sobre cómo va el brote ahora mismo.
**Comparación entre vías**: si hay más de una vía, cuál está creciendo más rápido y qué implica.
**Focos geográficos**: si hay clusters, cuál es el más preocupante y por qué.
**Proyección**: qué dice el modelo sobre lo que viene.
**Recomendación**: 1-2 acciones concretas sugeridas, con el debido cuidado de que esto no reemplaza el juicio clínico/epidemiológico profesional.

Sé breve en cada sección (2-3 frases máximo). Si algún dato no está disponible, omite esa sección en vez de inventar."""

    try:
        texto = _llamar_ia(prompt, api_key, proveedor, max_tokens=700)
        return {"valido": True, "texto": texto}
    except ImportError as e:
        return {"valido": False, "mensaje": f"Falta instalar la librería del proveedor {proveedor}: {e}"}
    except Exception as e:
        return {"valido": False, "mensaje": f"No se pudo generar el análisis: {e}"}
