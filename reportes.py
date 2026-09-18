# -*- coding: utf-8 -*-
"""
reportes.py — Genera un PDF con el resumen histórico y la proyección
de un brote, para descargar o enviar a terceros (junta directiva,
entidad de salud, etc.).
"""
import io
from datetime import date

import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors as rl_colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

COLOR_AZUL_OSCURO = "#000d5c"
COLOR_VIOLETA = "#9e33b2"


def _generar_grafico_png(serie: list, tabla_proyeccion) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df_h = pd.DataFrame(serie)
    df_h["fecha"] = pd.to_datetime(df_h["fecha"])

    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot(df_h["fecha"], df_h["casos_activos"], label="Activos (histórico)", color=COLOR_AZUL_OSCURO)
    ax.plot(df_h["fecha"], df_h["recuperados_acumulados"], label="Recuperados acum.", color="green", alpha=0.7)
    ax.plot(df_h["fecha"], df_h["fallecidos_acumulados"], label="Fallecidos acum.", color="red", alpha=0.7)

    if tabla_proyeccion:
        df_p = pd.DataFrame(tabla_proyeccion)
        df_p["fecha"] = pd.to_datetime(df_p["fecha"])
        ax.plot(df_p["fecha"], df_p["casos_activos_proyectados"], "--", label="Activos (proyección)", color=COLOR_VIOLETA)

    ax.set_ylabel("Casos")
    ax.legend(fontsize=7)
    fig.autofmt_xdate()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def generar_pdf_reporte(brote_nombre: str, serie: list, tabla_proyeccion=None, mensaje_modelo: str = "") -> bytes:
    """Devuelve los bytes del PDF (listo para st.download_button)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Reporte de Seguimiento Epidemiológico", styles["Title"]))
    story.append(Paragraph(f"Brote: {brote_nombre}", styles["Heading2"]))
    story.append(Paragraph(f"Generado: {date.today().strftime('%d/%m/%Y')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    try:
        img_bytes = _generar_grafico_png(serie, tabla_proyeccion)
        story.append(Image(io.BytesIO(img_bytes), width=460, height=195))
        story.append(Spacer(1, 12))
    except Exception:
        story.append(Paragraph("(No se pudo generar el gráfico)", styles["Normal"]))

    story.append(Paragraph("Histórico (últimos 15 días con datos)", styles["Heading2"]))
    ultimos = serie[-15:]
    data = [["Fecha", "Nuevos", "Fallecidos", "Recuperados", "Activos", "Rt"]]
    for r in ultimos:
        rt = r.get("rt_efectivo")
        rt_str = f"{rt:.2f}" if rt == rt else "N/D"  # rt != rt detecta NaN
        data.append([str(r["fecha"])[:10], r["casos_nuevos"], r["fallecidos"], r["recuperados"], r["casos_activos"], rt_str])

    tabla = Table(data, hAlign="LEFT")
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor(COLOR_AZUL_OSCURO)),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(tabla)
    story.append(Spacer(1, 16))

    if tabla_proyeccion:
        story.append(Paragraph("Proyección", styles["Heading2"]))
        if mensaje_modelo:
            story.append(Paragraph(mensaje_modelo, styles["Normal"]))
        story.append(Spacer(1, 6))

        data2 = [["Fecha", "Nuevos proy.", "Activos proy.", "Recuperados proy.", "Fallecidos proy."]]
        for p in tabla_proyeccion:
            data2.append([
                str(p["fecha"])[:10],
                f"{p['casos_nuevos_proyectados']:.1f}",
                f"{p['casos_activos_proyectados']:.1f}",
                f"{p['recuperados_proyectados']:.1f}",
                f"{p['fallecidos_proyectados']:.1f}",
            ])
        tabla2 = Table(data2, hAlign="LEFT")
        tabla2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor(COLOR_VIOLETA)),
            ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(tabla2)
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "<i>Nota: Recuperados/fallecidos proyectados se derivan de las tasas históricas "
            "de letalidad y recuperación observadas en este brote, no de un modelo separado.</i>",
            styles["Normal"],
        ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
