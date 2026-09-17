# -*- coding: utf-8 -*-
"""
app.py — Sistema de Seguimiento de Epidemia (versión comercial)

Punto de entrada de Streamlit. Maneja:
  - Registro / inicio de sesión (Supabase Auth)
  - Persistencia de sesión entre refrescos (cookie firmada)
  - Captura de datos diarios por vía de contagio
  - Tabla histórica con casos activos / Rt (agregado y por vía)
  - Badge de qué modelo predictivo está disponible según el volumen de datos

Los modelos predictivos en sí (regresión, SIR, ARIMA, ML) se conectan
en un paso siguiente, como módulos separados que consumen
`db.obtener_registros_ultimos_n_dias` / `db.obtener_registros`.
"""
import io
import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import extra_streamlit_components as stx

import db
import calculos
import proyecciones
import clasificacion
import sugerencia_modelos as sm


st.set_page_config(page_title="Seguimiento de Epidemia", page_icon="🦠", layout="wide")

# ---------------------------------------------------------------------
# Cookies (persistencia de sesión entre refrescos del navegador)
#
# Nota: a diferencia de streamlit-cookies-manager (descontinuado, rompe
# con Streamlit reciente porque usa st.cache), extra-streamlit-components
# no cifra el contenido de la cookie en el navegador. Esto es aceptable
# aquí porque lo que guardamos son los tokens de sesión de Supabase
# (JWT firmados y de corta duración, no la contraseña), el mismo tipo
# de dato que casi cualquier app guarda en una cookie de sesión.
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
                st.session_state["usuario"] = {
                    "id": user.user.id,
                    "email": user.user.email,
                }
        except Exception:
            # Token vencido o inválido: se limpia y se pide login de nuevo
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
                st.session_state["usuario"] = {
                    "id": respuesta.user.id,
                    "email": respuesta.user.email,
                }
                if recordar:
                    cookie_manager.set(
                        "access_token", respuesta.session.access_token, key="set_access_token"
                    )
                    cookie_manager.set(
                        "refresh_token", respuesta.session.refresh_token, key="set_refresh_token"
                    )
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo iniciar sesión: {e}")

    with tab_registro:
        st.caption(
            "El registro es abierto y gratuito. Tus datos quedan visibles "
            "únicamente para tu propia cuenta."
        )
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
                    st.success(
                        "Cuenta creada. Revisa tu correo para confirmar la cuenta "
                        "antes de iniciar sesión."
                    )
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


# ---------------------------------------------------------------------
# App principal (usuario autenticado)
# ---------------------------------------------------------------------
def barra_lateral_sesion():
    usuario = st.session_state["usuario"]
    with st.sidebar:
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


def seccion_captura_datos(usuario_id: str):
    st.subheader("Registrar / actualizar datos de una fecha")

    db.asegurar_vias_por_defecto(usuario_id)
    vias = db.listar_vias(usuario_id)
    nombres_vias = {v["nombre"]: v["id"] for v in vias}

    col_nueva_via, _ = st.columns([2, 3])
    with col_nueva_via.popover("+ Añadir nueva vía de contagio"):
        nueva_via = st.text_input("Nombre de la vía", key="nueva_via_input")
        if st.button("Guardar vía"):
            if nueva_via.strip():
                db.crear_via(usuario_id, nueva_via.strip())
                st.rerun()

    st.markdown("**Ubicación del caso**")
    c_pais, c_depto, c_ciudad, c_barrio = st.columns(4)
    pais = c_pais.text_input("País", value="Colombia", key="ubic_pais")
    departamento = c_depto.text_input("Departamento", key="ubic_depto")
    ciudad = c_ciudad.text_input("Ciudad", key="ubic_ciudad")
    barrio = c_barrio.text_input("Barrio (opcional)", key="ubic_barrio")
    st.caption("La ubicación se geocodifica automáticamente (OpenStreetMap) la primera vez que la usas.")

    with st.form("form_captura"):
        c1, c2 = st.columns(2)
        fecha_sel = c1.date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
        via_sel_nombre = c2.selectbox("Vía de contagio", options=list(nombres_vias.keys()))

        c3, c4, c5 = st.columns(3)
        casos_nuevos = c3.number_input("Casos nuevos", min_value=0, step=1)
        fallecidos = c4.number_input("Fallecidos", min_value=0, step=1)
        recuperados = c5.number_input("Recuperados", min_value=0, step=1)

        guardar = st.form_submit_button("Guardar registro")

    if guardar:
        via_id = nombres_vias.get(via_sel_nombre)

        ubicacion_id = None
        if pais.strip():
            ubicacion = db.obtener_o_crear_ubicacion(
                usuario_id, pais.strip(), departamento.strip(), ciudad.strip(), barrio.strip()
            )
            ubicacion_id = ubicacion.get("id")
            if ubicacion and ubicacion.get("latitud") is None:
                st.warning(
                    "No se pudo ubicar automáticamente esta dirección en el mapa "
                    "(quedó guardada sin coordenadas). Verifica la ortografía o "
                    "usa un nivel más general (ciudad en vez de barrio)."
                )

        db.upsert_registro(
            usuario_id=usuario_id,
            fecha=fecha_sel,
            via_contagio_id=via_id,
            ubicacion_id=ubicacion_id,
            casos_nuevos=int(casos_nuevos),
            fallecidos=int(fallecidos),
            recuperados=int(recuperados),
        )
        st.success(f"Registro guardado para {fecha_sel.strftime('%d/%m/%Y')} — vía: {via_sel_nombre}")
        st.rerun()

    seccion_editar_eliminar_registros(usuario_id)


def seccion_editar_eliminar_registros(usuario_id: str):
    with st.expander("Editar o eliminar registros existentes"):
        registros = db.obtener_registros(usuario_id)
        if not registros:
            st.caption("No hay registros todavía.")
            return

        registros_recientes = sorted(registros, key=lambda r: r["fecha"], reverse=True)[:30]

        for r in registros_recientes:
            nombre_via = (r.get("vias_contagio") or {}).get("nombre", "Sin vía")
            nombre_ubic = (r.get("ubicaciones") or {}).get("ciudad") or "Sin ubicación"
            fecha_legible = pd.to_datetime(r["fecha"]).strftime("%d/%m/%Y")

            c1, c2, c3 = st.columns([3, 1, 1])
            c1.markdown(
                f"**{fecha_legible}** — {nombre_via} — {nombre_ubic} — "
                f"Nuevos: {r['casos_nuevos']} · Fallecidos: {r['fallecidos']} · Recuperados: {r['recuperados']}"
            )
            if c2.button("🗑️ Eliminar", key=f"del_{r['id']}"):
                db.eliminar_registro(r["id"])
                st.rerun()
            c3.caption("Para corregir: guarda un nuevo registro con la misma fecha/vía/ubicación arriba — se actualiza solo.")

        if len(registros) > 30:
            st.caption(f"Mostrando los 30 más recientes de {len(registros)} registros totales.")


def seccion_tabla_y_resumen(usuario_id: str):
    st.subheader("Histórico de la epidemia")

    registros = db.obtener_registros(usuario_id)
    if not registros:
        st.info("Aún no hay registros. Usa el formulario de arriba para empezar a capturar datos.")
        return

    total_registros = len(registros)
    conteo_por_via = db.contar_registros_por_via(usuario_id)

    sugerencia = sm.sugerir_modelo(total_registros, conteo_por_via)
    semaforo = sm.nivel_semaforo(total_registros)
    st.info(f"{semaforo} {sugerencia['mensaje']}")

    with st.expander("Ver qué modelos están disponibles y por qué"):
        for clave, nombre in sm.NOMBRES_LEGIBLES.items():
            disponible = clave in sugerencia["modelos_disponibles"]
            st.checkbox(nombre, value=disponible, disabled=True, key=f"chk_{clave}")
        if sugerencia["vias_con_ml_habilitado"]:
            st.caption("Vías con suficiente volumen para ML: " + ", ".join(sugerencia["vias_con_ml_habilitado"]))
        else:
            st.caption(f"Ninguna vía alcanza aún los {sm.UMBRAL_ML_POR_VIA} registros necesarios para ML por vía.")

    # Filtro de fechas
    fechas_todas = sorted({pd.to_datetime(r["fecha"]).date() for r in registros})
    c_desde, c_hasta = st.columns(2)
    fecha_desde = c_desde.date_input("Desde", value=fechas_todas[0], key="filtro_desde")
    fecha_hasta = c_hasta.date_input("Hasta", value=fechas_todas[-1], key="filtro_hasta")
    registros_filtrados = [
        r for r in registros
        if fecha_desde <= pd.to_datetime(r["fecha"]).date() <= fecha_hasta
    ]

    por_via = calculos.recalcular_por_via(registros_filtrados)

    opciones_vista = ["TOTAL"] + [k for k in por_via.keys() if k != "TOTAL"]
    vista_sel = st.selectbox("Ver serie:", options=opciones_vista)

    serie = por_via[vista_sel]
    df = pd.DataFrame(serie)
    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"]).dt.strftime("%d/%m/%Y")
        columnas_mostrar = ["fecha", "casos_nuevos", "fallecidos", "recuperados", "casos_activos", "rt_efectivo"]
        df_mostrar = df[columnas_mostrar].rename(columns={
            "fecha": "Fecha", "casos_nuevos": "Casos nuevos", "fallecidos": "Fallecidos",
            "recuperados": "Recuperados", "casos_activos": "Casos activos", "rt_efectivo": "Rt efectivo",
        })
        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

        buffer_excel = io.BytesIO()
        with pd.ExcelWriter(buffer_excel, engine="openpyxl") as writer:
            df_mostrar.to_excel(writer, index=False, sheet_name=vista_sel[:31])
        st.download_button(
            "📥 Exportar esta tabla a Excel",
            data=buffer_excel.getvalue(),
            file_name=f"seguimiento_epidemia_{vista_sel}_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    velocidad = calculos.tasa_crecimiento_y_duplicacion(serie)
    fase = clasificacion.clasificar_fase_heuristica(velocidad["tasa_r"])

    c1, c2, c3 = st.columns(3)
    c1.metric("Tasa de crecimiento diaria (r)", f"{velocidad['tasa_r']:.3f}" if velocidad["tasa_r"] is not None else "N/D")
    c2.metric("Días para duplicar casos activos", f"{velocidad['dias_duplicacion']:.1f}" if velocidad["dias_duplicacion"] is not None else "N/D")
    c3.metric("Fase estimada", f"{fase['color']} {fase['fase']}")
    st.caption(
        "La fase se calcula con una regla estadística directa sobre la tasa de crecimiento "
        "(no un modelo de Machine Learning entrenado — ver clasificacion.py para el porqué)."
    )

    if not df.empty and len(df) >= 2:
        st.line_chart(df.set_index("Fecha" if "Fecha" in df.columns else "fecha")[["casos_activos"]]
                       if "casos_activos" in df.columns else df.set_index("fecha")[["casos_activos"]])

    if len(por_via) > 2:  # más de TOTAL + 1 vía
        seccion_comparacion_vias(por_via)

    seccion_proyeccion(serie, vista_sel)


def seccion_comparacion_vias(por_via: dict):
    st.markdown("#### Comparación de velocidad de transmisión entre vías")
    comparacion = calculos.comparar_velocidad_por_via(por_via)
    df_comp = pd.DataFrame(comparacion)
    df_comp_mostrar = df_comp.rename(columns={
        "via": "Vía", "tasa_r": "Tasa de crecimiento (r)",
        "dias_duplicacion": "Días para duplicar", "casos_activos_actuales": "Casos activos actuales",
    })
    st.dataframe(df_comp_mostrar.round(3), use_container_width=True, hide_index=True)
    st.caption("Ordenado de mayor a menor velocidad de crecimiento. TOTAL incluye todas las vías juntas.")


def seccion_proyeccion(serie: list[dict], nombre_serie: str):
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
        _mostrar_proyeccion_con_banda(serie, resultado, "Tasa de crecimiento diaria estimada (regresión)", "tasa_crecimiento_diaria")
    elif modelo_sel.startswith("ARIMA"):
        resultado = proyecciones.ajustar_arima(serie, dias_futuros=dias_futuros)
        _mostrar_proyeccion_con_banda(serie, resultado, None, None)
    else:
        resultado = proyecciones.ajustar_crecimiento_logistico(serie, dias_futuros=dias_futuros)
        _mostrar_proyeccion_logistica(resultado)


def _mostrar_proyeccion_con_banda(serie: list[dict], resultado: dict, etiqueta_metrica, campo_metrica):
    if not resultado["valido"]:
        st.warning(resultado["mensaje"])
        return

    st.caption(resultado["mensaje"])

    df_hist = pd.DataFrame([
        {"fecha": r["fecha"], "valor": r["casos_activos"]}
        for r in serie if r.get("casos_activos") is not None
    ])
    df_proy = pd.DataFrame([
        {"fecha": p["fecha"], "valor": p["valor_central"],
         "limite_inferior": p["limite_inferior"], "limite_superior": p["limite_superior"]}
        for p in resultado["proyeccion"]
    ])

    try:
        import altair as alt

        df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])
        df_proy["fecha"] = pd.to_datetime(df_proy["fecha"])

        banda = alt.Chart(df_proy).mark_area(opacity=0.25, color="orange").encode(
            x="fecha:T", y="limite_inferior:Q", y2="limite_superior:Q"
        )
        linea_hist = alt.Chart(df_hist).mark_line(color="steelblue", point=True).encode(
            x="fecha:T", y=alt.Y("valor:Q", title="Casos activos")
        )
        linea_proy = alt.Chart(df_proy).mark_line(color="orange", strokeDash=[5, 3], point=True).encode(
            x="fecha:T", y="valor:Q"
        )
        st.altair_chart((banda + linea_hist + linea_proy).properties(height=350), use_container_width=True)
    except ImportError:
        st.info("Instala 'altair' (incluido con Streamlit) para ver el gráfico de banda de incertidumbre.")

    if etiqueta_metrica and campo_metrica in resultado:
        c1, c2 = st.columns(2)
        c1.metric(etiqueta_metrica, f"{resultado[campo_metrica]:.3f}")
        c2.metric("Días con datos usados en el ajuste", resultado["n_dias_usados_en_ajuste"])
    else:
        st.metric("Días con datos usados en el ajuste", resultado["n_dias_usados_en_ajuste"])

    df_tabla_proy = pd.DataFrame(resultado["proyeccion"])
    df_tabla_proy["fecha"] = pd.to_datetime(df_tabla_proy["fecha"]).dt.strftime("%d/%m/%Y")
    df_tabla_proy = df_tabla_proy.rename(columns={
        "fecha": "Fecha", "valor_central": "Proyección central",
        "limite_inferior": "Límite inferior", "limite_superior": "Límite superior",
    })
    st.dataframe(df_tabla_proy.round(1), use_container_width=True, hide_index=True)


def _mostrar_proyeccion_logistica(resultado: dict):
    if not resultado["valido"]:
        st.warning(resultado["mensaje"])
        return

    st.caption(resultado["mensaje"])

    c1, c2, c3 = st.columns(3)
    c1.metric("K (techo estimado de casos acumulados)", f"{resultado['K_techo_estimado']:.0f}")
    c2.metric("r (tasa de crecimiento)", f"{resultado['r_tasa_crecimiento']:.3f}")
    c3.metric("Días usados en el ajuste", resultado["n_dias_usados_en_ajuste"])

    df_proy = pd.DataFrame(resultado["proyeccion"])
    df_proy["fecha"] = pd.to_datetime(df_proy["fecha"]).dt.strftime("%d/%m/%Y")
    df_proy = df_proy.rename(columns={
        "fecha": "Fecha", "casos_acumulados_proyectados": "Casos acumulados proyectados",
        "casos_nuevos_proyectados": "Casos nuevos proyectados",
    })
    st.dataframe(df_proy.round(1), use_container_width=True, hide_index=True)


def seccion_mapa(usuario_id: str):
    st.subheader("Mapa de casos")

    registros = db.obtener_registros(usuario_id)
    ubicaciones_agregadas = calculos.agregar_casos_por_ubicacion(registros)

    if not ubicaciones_agregadas:
        st.info(
            "Aún no hay casos con ubicación geocodificada. Registra casos indicando "
            "país/departamento/ciudad/barrio en el formulario de arriba."
        )
        return

    df_mapa = pd.DataFrame(ubicaciones_agregadas)

    try:
        import pydeck as pdk

        radio_max = float(df_mapa["casos_totales"].max()) or 1.0
        df_mapa["radio"] = 300 + (df_mapa["casos_totales"] / radio_max) * 3000

        vista = pdk.ViewState(
            latitude=float(df_mapa["latitud"].mean()),
            longitude=float(df_mapa["longitud"].mean()),
            zoom=4,
        )
        capa = pdk.Layer(
            "ScatterplotLayer",
            data=df_mapa,
            get_position="[longitud, latitud]",
            get_radius="radio",
            get_fill_color="[220, 90, 40, 160]",
            pickable=True,
        )
        tooltip = {"html": "<b>{etiqueta_completa}</b><br/>Casos: {casos_totales}<br/>Fallecidos: {fallecidos_totales}"}
        st.pydeck_chart(pdk.Deck(layers=[capa], initial_view_state=vista, tooltip=tooltip))
        st.caption("Tamaño de burbuja proporcional a casos acumulados. Datos de mapa: © OpenStreetMap contributors.")
    except ImportError:
        st.info("Instala 'pydeck' (incluido con Streamlit) para ver el mapa de burbujas.")
        st.map(df_mapa.rename(columns={"latitud": "lat", "longitud": "lon"})[["lat", "lon"]])

    st.dataframe(
        df_mapa[["etiqueta_completa", "casos_totales", "fallecidos_totales"]]
        .rename(columns={"etiqueta_completa": "Ubicación", "casos_totales": "Casos", "fallecidos_totales": "Fallecidos"})
        .sort_values("Casos", ascending=False),
        use_container_width=True, hide_index=True,
    )


def seccion_panel_admin(usuario_id: str):
    if not db.es_admin(usuario_id):
        return

    st.divider()
    st.subheader("🔑 Panel de administrador")
    st.caption("Visible solo para tu cuenta porque tiene rol 'admin' en la base de datos.")

    try:
        stats = db.estadisticas_globales_admin()
    except RuntimeError as e:
        st.warning(str(e))
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
            df_usuarios = pd.DataFrame(usuarios)
            st.dataframe(df_usuarios, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"No se pudo obtener la lista de usuarios: {e}")


def app_principal():
    usuario = st.session_state["usuario"]
    barra_lateral_sesion()
    st.title("🦠 Sistema de Seguimiento de Epidemia")
    seccion_captura_datos(usuario["id"])
    st.divider()
    seccion_tabla_y_resumen(usuario["id"])
    st.divider()
    seccion_mapa(usuario["id"])
    seccion_panel_admin(usuario["id"])


# ---------------------------------------------------------------------
# Enrutamiento
# ---------------------------------------------------------------------
if "usuario" not in st.session_state:
    pantalla_login()
else:
    app_principal()
