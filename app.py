# -*- coding: utf-8 -*-
"""
app.py — Sistema de Seguimiento de Epidemia (versión comercial)

Estructura:
  - Barra lateral izquierda: todo lo que es CAPTURA/CONTROL — sesión,
    selector y creación de brotes, formulario de un registro, carga
    masiva desde Excel/CSV, edición/eliminación, y el enlace de donación.
  - Cuerpo principal: DASHBOARD del brote seleccionado — KPIs, gráficos
    interactivos, mapa, comparación entre vías, proyecciones.
  - Un usuario puede llevar tantos brotes (epidemias) en paralelo como
    quiera; cada uno tiene su propia línea de tiempo independiente.
"""
import io
import os
from datetime import date

import pandas as pd
import streamlit as st
import extra_streamlit_components as stx

import db
import calculos
import proyecciones
import clasificacion
import sugerencia_modelos as sm

LINK_DONACION = "https://checkout.bold.co/payment/LNK_ATP7YCXF33"

# Colores del manual de marca (Fundación Juan Manuel Collazos)
COLOR_AZUL_OSCURO = "#000d5c"
COLOR_VIOLETA = "#9e33b2"
COLOR_CIAN = "#00d6ff"
COLOR_AZUL_COMPLEMENTARIO = "#303896"

st.set_page_config(page_title="Seguimiento de Epidemia", page_icon="🦠", layout="wide")

st.markdown(
    f"""
    <style>
    h1, h2, h3 {{ color: {COLOR_AZUL_OSCURO}; }}
    [data-testid="stSidebar"] {{ border-right: 3px solid {COLOR_VIOLETA}; }}
    .stButton>button, .stDownloadButton>button {{
        background-color: {COLOR_AZUL_COMPLEMENTARIO};
        color: white;
        border: none;
    }}
    .stButton>button:hover, .stDownloadButton>button:hover {{
        background-color: {COLOR_VIOLETA};
        color: white;
    }}
    a.boton-donar {{
        display: block;
        text-align: center;
        background-color: {COLOR_CIAN};
        color: {COLOR_AZUL_OSCURO} !important;
        font-weight: bold;
        padding: 0.6em;
        border-radius: 0.5em;
        text-decoration: none;
        margin-top: 0.5em;
    }}
    a.boton-donar:hover {{ background-color: {COLOR_VIOLETA}; color: white !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------
# Cookies (persistencia de sesión entre refrescos del navegador)
# ---------------------------------------------------------------------
cookie_manager = stx.CookieManager()
_cookies_actuales = cookie_manager.get_all() or {}


def _restaurar_sesion_desde_cookie():
    if "usuario" in st.session_state:
        return
    access_token = _cookies_actuales.get("access_token")
    refresh_token = _cookies_actuales.get("refresh_token")
    if access_token and refresh_token:
        try:
            db.set_auth_session(access_token, refresh_token)
            client = db.get_client()
            user = client.auth.get_user(access_token)
            if user and user.user:
                st.session_state["usuario"] = {"id": user.user.id, "email": user.user.email}
        except Exception:
            cookie_manager.delete("access_token", key="del_access_token_expirado")
            cookie_manager.delete("refresh_token", key="del_refresh_token_expirado")


_restaurar_sesion_desde_cookie()


# ---------------------------------------------------------------------
# Pantalla de autenticación
# ---------------------------------------------------------------------
def pantalla_login():
    st.title("🦠 Sistema de Seguimiento de Epidemia")
    tab_login, tab_registro, tab_recuperar = st.tabs(
        ["Iniciar sesión", "Crear cuenta", "Olvidé mi contraseña"]
    )

    with tab_login:
        with st.form("form_login"):
            email = st.text_input("Correo electrónico")
            password = st.text_input("Contraseña", type="password")
            recordar = st.checkbox("Mantener sesión iniciada en este navegador", value=True)
            enviado = st.form_submit_button("Iniciar sesión")

        if enviado:
            try:
                respuesta = db.iniciar_sesion(email, password)
                st.session_state["usuario"] = {"id": respuesta.user.id, "email": respuesta.user.email}
                if recordar:
                    cookie_manager.set("access_token", respuesta.session.access_token, key="set_access_token")
                    cookie_manager.set("refresh_token", respuesta.session.refresh_token, key="set_refresh_token")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo iniciar sesión: {e}")

    with tab_registro:
        st.caption("El registro es abierto y gratuito. Tus datos quedan visibles únicamente para tu propia cuenta.")
        with st.form("form_registro"):
            email_r = st.text_input("Correo electrónico", key="email_registro")
            password_r = st.text_input("Contraseña (mínimo 6 caracteres)", type="password", key="pw_registro")
            password_r2 = st.text_input("Confirmar contraseña", type="password", key="pw_registro_2")
            acepta = st.checkbox("Acepto el tratamiento de mis datos personales (Ley 1581 de 2012)")
            enviado_r = st.form_submit_button("Crear cuenta")

        with st.expander("Ver política de tratamiento de datos personales"):
            ruta_privacidad = os.path.join(os.path.dirname(__file__), "PRIVACIDAD.md")
            try:
                with open(ruta_privacidad, encoding="utf-8") as f:
                    st.markdown(f.read())
            except FileNotFoundError:
                st.caption("Documento no disponible en este momento.")

        if enviado_r:
            if password_r != password_r2:
                st.error("Las contraseñas no coinciden.")
            elif len(password_r) < 6:
                st.error("La contraseña debe tener al menos 6 caracteres.")
            elif not acepta:
                st.error("Debes aceptar el tratamiento de datos para continuar.")
            else:
                try:
                    db.registrar_usuario(email_r, password_r)
                    st.success("Cuenta creada. Revisa tu correo para confirmar la cuenta antes de iniciar sesión.")
                except Exception as e:
                    st.error(f"No se pudo crear la cuenta: {e}")

    with tab_recuperar:
        with st.form("form_recuperar"):
            email_rec = st.text_input("Correo electrónico", key="email_recuperar")
            enviado_rec = st.form_submit_button("Enviar enlace de recuperación")
        if enviado_rec:
            try:
                db.recuperar_password(email_rec)
                st.success("Si el correo existe, se envió un enlace de recuperación.")
            except Exception as e:
                st.error(f"No se pudo procesar la solicitud: {e}")


# =======================================================================
# BARRA LATERAL — todo lo que es entrada/control de datos
# =======================================================================
def barra_lateral_sesion(usuario: dict):
    st.markdown(f"**Sesión:** {usuario['email']}")
    with st.expander("Cambiar contraseña"):
        with st.form("form_cambiar_password"):
            pw_nueva = st.text_input("Nueva contraseña (mínimo 6 caracteres)", type="password", key="pw_nueva")
            pw_nueva2 = st.text_input("Confirmar nueva contraseña", type="password", key="pw_nueva2")
            cambiar = st.form_submit_button("Actualizar contraseña")
        if cambiar:
            if pw_nueva != pw_nueva2:
                st.error("Las contraseñas no coinciden.")
            elif len(pw_nueva) < 6:
                st.error("Debe tener al menos 6 caracteres.")
            else:
                try:
                    db.cambiar_password(pw_nueva)
                    st.success("Contraseña actualizada.")
                except Exception as e:
                    st.error(f"No se pudo actualizar: {e}")

    if st.button("Cerrar sesión"):
        db.cerrar_sesion()
        cookie_manager.delete("access_token", key="del_access_token_logout")
        cookie_manager.delete("refresh_token", key="del_refresh_token_logout")
        del st.session_state["usuario"]
        st.rerun()


def seccion_lateral_brotes(usuario_id: str) -> dict:
    st.markdown("### 🦠 Brote activo")
    db.asegurar_brote_por_defecto(usuario_id)
    brotes = db.listar_brotes(usuario_id)
    nombres = {b["nombre"]: b for b in brotes}

    nombre_sel = st.selectbox("Selecciona el brote a trabajar", options=list(nombres.keys()), key="selector_brote")

    with st.expander("+ Crear nuevo brote"):
        with st.form("form_nuevo_brote"):
            nombre_nuevo = st.text_input("Nombre del brote (ej. 'Dengue Cali 2026')")
            desc_nuevo = st.text_area("Descripción (opcional)")
            crear = st.form_submit_button("Crear brote")
        if crear and nombre_nuevo.strip():
            db.crear_brote(usuario_id, nombre_nuevo, desc_nuevo)
            st.success(f"Brote '{nombre_nuevo}' creado.")
            st.rerun()

    return nombres[nombre_sel]


def seccion_lateral_captura(usuario_id: str, brote_id: int):
    st.markdown("### ✍️ Registrar un caso")
    db.asegurar_vias_por_defecto(usuario_id)
    vias = db.listar_vias(usuario_id)
    nombres_vias = {v["nombre"]: v["id"] for v in vias}

    with st.popover("+ Añadir nueva vía de contagio"):
        nueva_via = st.text_input("Nombre de la vía", key="nueva_via_input")
        if st.button("Guardar vía"):
            if nueva_via.strip():
                db.crear_via(usuario_id, nueva_via.strip())
                st.rerun()

    st.caption("Ubicación (se geocodifica automáticamente con OpenStreetMap)")
    pais = st.text_input("País", value="Colombia", key="ubic_pais")
    departamento = st.text_input("Departamento", key="ubic_depto")
    ciudad = st.text_input("Ciudad", key="ubic_ciudad")
    barrio = st.text_input("Barrio (opcional)", key="ubic_barrio")

    with st.form("form_captura"):
        fecha_sel = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
        via_sel_nombre = st.selectbox("Vía de contagio", options=list(nombres_vias.keys()))
        casos_nuevos = st.number_input("Casos nuevos", min_value=0, step=1)
        fallecidos = st.number_input("Fallecidos", min_value=0, step=1)
        recuperados = st.number_input("Recuperados", min_value=0, step=1)
        guardar = st.form_submit_button("Guardar registro")

    if guardar:
        via_id = nombres_vias.get(via_sel_nombre)
        ubicacion_id = None
        if pais.strip():
            ubicacion = db.obtener_o_crear_ubicacion(usuario_id, pais.strip(), departamento.strip(), ciudad.strip(), barrio.strip())
            ubicacion_id = ubicacion.get("id")
            if ubicacion and ubicacion.get("latitud") is None:
                st.warning("No se pudo geocodificar esta dirección (quedó guardada sin coordenadas).")

        db.upsert_registro(
            usuario_id=usuario_id, brote_id=brote_id, fecha=fecha_sel, via_contagio_id=via_id,
            ubicacion_id=ubicacion_id, casos_nuevos=int(casos_nuevos), fallecidos=int(fallecidos),
            recuperados=int(recuperados),
        )
        st.success(f"Registro guardado para {fecha_sel.strftime('%d/%m/%Y')}")
        st.rerun()


def seccion_lateral_carga_masiva(usuario_id: str, brote_id: int):
    st.markdown("### 📤 Cargar datos desde Excel/CSV")
    st.caption(
        "Columnas esperadas: **fecha, casos_nuevos, fallecidos, recuperados** "
        "(fallecidos/recuperados opcionales, se asumen 0). Opcionales: "
        "**via, pais, departamento, ciudad, barrio**."
    )
    archivo = st.file_uploader("Selecciona un archivo", type=["csv", "xlsx", "xls"], key="uploader_masivo")

    if archivo is not None:
        try:
            if archivo.name.endswith(".csv"):
                df_subida = pd.read_csv(archivo)
            else:
                df_subida = pd.read_excel(archivo)
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")
            return

        df_subida.columns = [c.strip().lower() for c in df_subida.columns]
        st.dataframe(df_subida.head(10), use_container_width=True)

        columnas_requeridas = {"fecha", "casos_nuevos"}
        if not columnas_requeridas.issubset(set(df_subida.columns)):
            st.error(f"Faltan columnas obligatorias: {columnas_requeridas - set(df_subida.columns)}")
            return

        if st.button(f"Importar {len(df_subida)} filas a este brote"):
            filas = []
            for _, fila in df_subida.iterrows():
                try:
                    fecha_val = pd.to_datetime(fila["fecha"]).date()
                except Exception:
                    continue
                filas.append({
                    "fecha": fecha_val,
                    "casos_nuevos": fila.get("casos_nuevos", 0),
                    "fallecidos": fila.get("fallecidos", 0) if pd.notna(fila.get("fallecidos", 0)) else 0,
                    "recuperados": fila.get("recuperados", 0) if pd.notna(fila.get("recuperados", 0)) else 0,
                    "via_nombre": str(fila.get("via", "")) if pd.notna(fila.get("via", "")) else "",
                    "ubicacion": {
                        "pais": str(fila.get("pais", "")) if pd.notna(fila.get("pais", "")) else "",
                        "departamento": str(fila.get("departamento", "")) if pd.notna(fila.get("departamento", "")) else "",
                        "ciudad": str(fila.get("ciudad", "")) if pd.notna(fila.get("ciudad", "")) else "",
                        "barrio": str(fila.get("barrio", "")) if pd.notna(fila.get("barrio", "")) else "",
                    } if "pais" in df_subida.columns else None,
                })

            with st.spinner("Importando..."):
                resultado = db.importar_registros_masivo(usuario_id, brote_id, filas)

            st.success(f"{resultado['exitosos']} filas importadas correctamente.")
            if resultado["fallidos"]:
                st.warning(f"{len(resultado['fallidos'])} filas fallaron.")
                st.dataframe(pd.DataFrame(resultado["fallidos"]), use_container_width=True)
            st.rerun()


def seccion_lateral_editar_eliminar(usuario_id: str, brote_id: int):
    with st.expander("🗑️ Editar o eliminar registros"):
        registros = db.obtener_registros(usuario_id, brote_id=brote_id)
        if not registros:
            st.caption("No hay registros en este brote todavía.")
            return
        recientes = sorted(registros, key=lambda r: r["fecha"], reverse=True)[:20]
        for r in recientes:
            nombre_via = (r.get("vias_contagio") or {}).get("nombre", "Sin vía")
            fecha_legible = pd.to_datetime(r["fecha"]).strftime("%d/%m/%Y")
            c1, c2 = st.columns([4, 1])
            c1.caption(f"{fecha_legible} — {nombre_via} — Nuevos: {r['casos_nuevos']}")
            if c2.button("🗑️", key=f"del_{r['id']}"):
                db.eliminar_registro(r["id"])
                st.rerun()
        if len(registros) > 20:
            st.caption(f"Mostrando 20 de {len(registros)} registros.")


def seccion_lateral_donacion():
    st.markdown("### 💙 Apoya la Fundación")
    st.caption("Esta app es gratuita. Si te resulta útil, considera donar a la Fundación Juan Manuel Collazos.")
    st.markdown(f'<a class="boton-donar" href="{LINK_DONACION}" target="_blank">Donar ahora</a>', unsafe_allow_html=True)


# =======================================================================
# DASHBOARD PRINCIPAL — visualización del brote seleccionado
# =======================================================================
def dashboard_kpis(serie: list, velocidad: dict, fase: dict):
    ultimo = serie[-1] if serie else {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Casos activos", ultimo.get("casos_activos", 0))
    c2.metric("Rt efectivo (último día)", f"{ultimo.get('rt_efectivo', 0):.2f}" if ultimo.get("rt_efectivo") == ultimo.get("rt_efectivo") else "N/D")
    c3.metric("Tasa de crecimiento (r)", f"{velocidad['tasa_r']:.3f}" if velocidad["tasa_r"] is not None else "N/D")
    c4.metric("Fase estimada", f"{fase['color']} {fase['fase']}")


def dashboard_grafico_principal(serie: list):
    df = pd.DataFrame(serie)
    if df.empty:
        st.info("Sin datos para graficar todavía.")
        return
    df["fecha"] = pd.to_datetime(df["fecha"])

    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["fecha"], y=df["casos_activos"], name="Casos activos",
                                  mode="lines+markers", line=dict(color=COLOR_AZUL_COMPLEMENTARIO, width=3)))
        fig.add_trace(go.Bar(x=df["fecha"], y=df["casos_nuevos"], name="Casos nuevos",
                              marker_color=COLOR_CIAN, opacity=0.5, yaxis="y2"))
        fig.update_layout(
            height=400,
            yaxis=dict(title="Casos activos"),
            yaxis2=dict(title="Casos nuevos", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(l=10, r=10, t=40, b=10),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.line_chart(df.set_index("fecha")[["casos_activos"]])


def dashboard_comparacion_vias(por_via: dict):
    if len(por_via) <= 2:
        return
    st.markdown("#### Velocidad de transmisión por vía")
    comparacion = calculos.comparar_velocidad_por_via(por_via)
    df_comp = pd.DataFrame(comparacion)

    try:
        import plotly.express as px

        fig = px.bar(
            df_comp, x="via", y="tasa_r", color="via",
            color_discrete_sequence=[COLOR_AZUL_OSCURO, COLOR_VIOLETA, COLOR_CIAN, COLOR_AZUL_COMPLEMENTARIO],
            labels={"tasa_r": "Tasa de crecimiento (r)", "via": ""},
        )
        fig.update_layout(showlegend=False, height=320, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.dataframe(df_comp, use_container_width=True, hide_index=True)

    st.dataframe(
        df_comp.rename(columns={
            "via": "Vía", "tasa_r": "Tasa de crecimiento", "dias_duplicacion": "Días para duplicar",
            "casos_activos_actuales": "Casos activos",
        }).round(3),
        use_container_width=True, hide_index=True,
    )


def dashboard_tabla_y_export(serie: list, nombre_serie: str):
    df = pd.DataFrame(serie)
    if df.empty:
        return
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.strftime("%d/%m/%Y")
    columnas = ["fecha", "casos_nuevos", "fallecidos", "recuperados", "casos_activos", "rt_efectivo"]
    df_mostrar = df[columnas].rename(columns={
        "fecha": "Fecha", "casos_nuevos": "Casos nuevos", "fallecidos": "Fallecidos",
        "recuperados": "Recuperados", "casos_activos": "Casos activos", "rt_efectivo": "Rt efectivo",
    })
    with st.expander("Ver tabla histórica completa"):
        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)
        buffer_excel = io.BytesIO()
        with pd.ExcelWriter(buffer_excel, engine="openpyxl") as writer:
            df_mostrar.to_excel(writer, index=False, sheet_name=nombre_serie[:31])
        st.download_button(
            "📥 Exportar a Excel", data=buffer_excel.getvalue(),
            file_name=f"seguimiento_{nombre_serie}_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def seccion_proyeccion(serie: list, nombre_serie: str):
    st.markdown("#### Proyección a futuro")
    n_dias_disponibles = len([r for r in serie if r.get("casos_activos") is not None])
    opciones_modelo = ["Regresión log-lineal (±2σ)"]
    if n_dias_disponibles >= 8:
        opciones_modelo.append("Crecimiento logístico (SIR simplificado)")
    if n_dias_disponibles >= 50:
        opciones_modelo.append("ARIMA (95% de confianza)")

    modelo_sel = st.selectbox("Modelo de proyección", options=opciones_modelo, key=f"modelo_{nombre_serie}")
    dias_futuros = st.slider("Días a proyectar", min_value=3, max_value=14, value=7, key=f"slider_{nombre_serie}")

    if modelo_sel.startswith("Regresión"):
        resultado = proyecciones.proyectar_regresion_log_lineal(serie, dias_futuros=dias_futuros)
        _mostrar_proyeccion_con_banda(serie, resultado, "Tasa de crecimiento diaria estimada", "tasa_crecimiento_diaria")
    elif modelo_sel.startswith("ARIMA"):
        resultado = proyecciones.ajustar_arima(serie, dias_futuros=dias_futuros)
        _mostrar_proyeccion_con_banda(serie, resultado, None, None)
    else:
        resultado = proyecciones.ajustar_crecimiento_logistico(serie, dias_futuros=dias_futuros)
        _mostrar_proyeccion_logistica(resultado)


def _mostrar_proyeccion_con_banda(serie: list, resultado: dict, etiqueta_metrica, campo_metrica):
    if not resultado["valido"]:
        st.warning(resultado["mensaje"])
        return
    st.caption(resultado["mensaje"])

    df_hist = pd.DataFrame([{"fecha": r["fecha"], "valor": r["casos_activos"]} for r in serie if r.get("casos_activos") is not None])
    df_proy = pd.DataFrame([{"fecha": p["fecha"], "valor": p["valor_central"],
                              "limite_inferior": p["limite_inferior"], "limite_superior": p["limite_superior"]}
                             for p in resultado["proyeccion"]])

    try:
        import plotly.graph_objects as go

        df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])
        df_proy["fecha"] = pd.to_datetime(df_proy["fecha"])

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_proy["fecha"], y=df_proy["limite_superior"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=df_proy["fecha"], y=df_proy["limite_inferior"], fill="tonexty",
                                  fillcolor="rgba(158,51,178,0.2)", line=dict(width=0), name="Banda de incertidumbre"))
        fig.add_trace(go.Scatter(x=df_hist["fecha"], y=df_hist["valor"], name="Histórico",
                                  line=dict(color=COLOR_AZUL_OSCURO, width=3)))
        fig.add_trace(go.Scatter(x=df_proy["fecha"], y=df_proy["valor"], name="Proyección",
                                  line=dict(color=COLOR_VIOLETA, width=3, dash="dash")))
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.info("Instala 'plotly' para ver el gráfico interactivo.")

    if etiqueta_metrica and campo_metrica in resultado:
        c1, c2 = st.columns(2)
        c1.metric(etiqueta_metrica, f"{resultado[campo_metrica]:.3f}")
        c2.metric("Días usados en el ajuste", resultado["n_dias_usados_en_ajuste"])
    else:
        st.metric("Días usados en el ajuste", resultado["n_dias_usados_en_ajuste"])


def _mostrar_proyeccion_logistica(resultado: dict):
    if not resultado["valido"]:
        st.warning(resultado["mensaje"])
        return
    st.caption(resultado["mensaje"])
    c1, c2, c3 = st.columns(3)
    c1.metric("K (techo estimado)", f"{resultado['K_techo_estimado']:.0f}")
    c2.metric("r (tasa de crecimiento)", f"{resultado['r_tasa_crecimiento']:.3f}")
    c3.metric("Días usados en el ajuste", resultado["n_dias_usados_en_ajuste"])
    df_proy = pd.DataFrame(resultado["proyeccion"])
    df_proy["fecha"] = pd.to_datetime(df_proy["fecha"]).dt.strftime("%d/%m/%Y")
    st.dataframe(df_proy.round(1), use_container_width=True, hide_index=True)


def dashboard_mapa(usuario_id: str, brote_id: int):
    registros = db.obtener_registros(usuario_id, brote_id=brote_id)
    ubicaciones_agregadas = calculos.agregar_casos_por_ubicacion(registros)
    if not ubicaciones_agregadas:
        return

    st.markdown("#### Mapa de casos")
    df_mapa = pd.DataFrame(ubicaciones_agregadas)
    try:
        import pydeck as pdk

        radio_max = float(df_mapa["casos_totales"].max()) or 1.0
        df_mapa["radio"] = 300 + (df_mapa["casos_totales"] / radio_max) * 3000
        vista = pdk.ViewState(latitude=float(df_mapa["latitud"].mean()), longitude=float(df_mapa["longitud"].mean()), zoom=4)
        capa = pdk.Layer("ScatterplotLayer", data=df_mapa, get_position="[longitud, latitud]",
                          get_radius="radio", get_fill_color="[158, 51, 178, 160]", pickable=True)
        tooltip = {"html": "<b>{etiqueta_completa}</b><br/>Casos: {casos_totales}<br/>Fallecidos: {fallecidos_totales}"}
        st.pydeck_chart(pdk.Deck(layers=[capa], initial_view_state=vista, tooltip=tooltip))
        st.caption("Datos de mapa: © OpenStreetMap contributors.")
    except ImportError:
        st.map(df_mapa.rename(columns={"latitud": "lat", "longitud": "lon"})[["lat", "lon"]])


def seccion_panel_admin(usuario_id: str):
    if not db.es_admin(usuario_id):
        return
    st.divider()
    st.subheader("🔑 Panel de administrador")
    st.caption("Visible solo para tu cuenta porque tiene rol 'admin' en la base de datos.")

    try:
        stats = db.estadisticas_globales_admin()
    except Exception as e:
        st.warning(f"No se pudieron cargar las estadísticas: {e}")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Usuarios registrados (total)", stats["total_usuarios_registrados"])
    c2.metric("Usuarios con al menos un registro", stats["usuarios_con_al_menos_un_registro"])
    c3.metric("Usuarios activos (últimos 7 días)", stats["usuarios_activos_ultimos_7_dias"])

    c4, c5, c6 = st.columns(3)
    c4.metric("Registros diarios capturados (total)", stats["total_registros_capturados"])
    c5.metric("Casos nuevos acumulados (todos los usuarios)", stats["total_casos_nuevos_acumulados"])
    c6.metric("Fallecidos acumulados (todos los usuarios)", stats["total_fallecidos_acumulados"])

    with st.expander("Ver lista de usuarios registrados"):
        try:
            usuarios = db.listar_usuarios_admin()
            st.dataframe(pd.DataFrame(usuarios), use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"No se pudo obtener la lista de usuarios: {e}")


# =======================================================================
# Enrutamiento principal
# =======================================================================
def app_principal():
    usuario = st.session_state["usuario"]

    with st.sidebar:
        barra_lateral_sesion(usuario)
        st.divider()
        brote = seccion_lateral_brotes(usuario["id"])
        st.divider()
        seccion_lateral_captura(usuario["id"], brote["id"])
        st.divider()
        seccion_lateral_carga_masiva(usuario["id"], brote["id"])
        st.divider()
        seccion_lateral_editar_eliminar(usuario["id"], brote["id"])
        st.divider()
        seccion_lateral_donacion()

    st.title(f"🦠 Dashboard — {brote['nombre']}")
    if brote.get("descripcion"):
        st.caption(brote["descripcion"])

    registros = db.obtener_registros(usuario["id"], brote_id=brote["id"])
    if not registros:
        st.info("Este brote todavía no tiene registros. Usa el panel de la izquierda para capturar el primero.")
        seccion_panel_admin(usuario["id"])
        return

    por_via = calculos.recalcular_por_via(registros)
    opciones_vista = ["TOTAL"] + [k for k in por_via.keys() if k != "TOTAL"]
    vista_sel = st.selectbox("Ver serie:", options=opciones_vista, key="vista_dashboard")
    serie = por_via[vista_sel]

    velocidad = calculos.tasa_crecimiento_y_duplicacion(serie)
    fase = clasificacion.clasificar_fase_heuristica(velocidad["tasa_r"])

    dashboard_kpis(serie, velocidad, fase)
    dashboard_grafico_principal(serie)
    dashboard_comparacion_vias(por_via)
    dashboard_mapa(usuario["id"], brote["id"])
    dashboard_tabla_y_export(serie, vista_sel)
    seccion_proyeccion(serie, vista_sel)

    conteo_por_via = db.contar_registros_por_via(usuario["id"], brote_id=brote["id"])
    sugerencia = sm.sugerir_modelo(len(registros), conteo_por_via)
    st.caption(sugerencia["mensaje"])

    seccion_panel_admin(usuario["id"])


# ---------------------------------------------------------------------
# Enrutamiento
# ---------------------------------------------------------------------
if "usuario" not in st.session_state:
    pantalla_login()
else:
    app_principal()
