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
import reportes
import datos_oficiales
import interpretacion
import sugerencia_modelos as sm

LINK_DONACION = "https://checkout.bold.co/payment/LNK_ATP7YCXF33"
URL_BASE_APP = "https://epidemias-jmcr.streamlit.app"
RUTA_LOGO = os.path.join(os.path.dirname(__file__), "assets", "logo_jmc.png")

# Colores del manual de marca (Fundación Juan Manuel Collazos)
COLOR_AZUL_OSCURO = "#000d5c"
COLOR_VIOLETA = "#9e33b2"
COLOR_CIAN = "#00d6ff"
COLOR_AZUL_COMPLEMENTARIO = "#303896"

st.set_page_config(page_title="Seguimiento de Epidemia", page_icon=RUTA_LOGO, layout="wide")

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
            st.session_state.pop("_supabase_client", None)


_restaurar_sesion_desde_cookie()


# ---------------------------------------------------------------------
# Pantalla de autenticación
# ---------------------------------------------------------------------
def pantalla_login():
    col_logo, col_titulo = st.columns([1, 3])
    with col_logo:
        st.image(RUTA_LOGO, width=180)
    with col_titulo:
        st.title("Sistema de Seguimiento de Epidemia")
    st.markdown(
        f'<a class="boton-donar" href="{LINK_DONACION}" target="_blank">💙 Apoya a la Fundación Juan Manuel Collazos — Donar</a>',
        unsafe_allow_html=True,
    )
    st.write("")
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
    st.image(RUTA_LOGO, use_container_width=True)
    st.markdown(f"**Sesión:** {usuario['email']}")

    with st.expander("❓ Cómo usar esta app"):
        ruta_manual = os.path.join(os.path.dirname(__file__), "MANUAL_DE_USO.md")
        try:
            with open(ruta_manual, encoding="utf-8") as f:
                st.markdown(f.read())
        except FileNotFoundError:
            st.caption("Manual no disponible en este momento.")

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
        st.session_state.pop("_supabase_client", None)
        st.rerun()


def seccion_lateral_brotes(usuario_id: str) -> dict:
    st.markdown("### 🦠 Brote activo")
    db.asegurar_brote_por_defecto(usuario_id)
    brotes = db.listar_brotes(usuario_id)
    etiquetas = {
        f"{b['nombre']}" + ("" if b.get("es_dueno", b["usuario_id"] == usuario_id) else " (colaborador)"): b
        for b in brotes
    }

    etiqueta_sel = st.selectbox("Selecciona el brote a trabajar", options=list(etiquetas.keys()), key="selector_brote")
    brote = etiquetas[etiqueta_sel]

    with st.expander("+ Crear nuevo brote"):
        with st.form("form_nuevo_brote"):
            nombre_nuevo = st.text_input("Nombre del brote (ej. 'Dengue Cali 2026')")
            desc_nuevo = st.text_area("Descripción (opcional)")
            crear = st.form_submit_button("Crear brote")
        if crear and nombre_nuevo.strip():
            db.crear_brote(usuario_id, nombre_nuevo, desc_nuevo)
            st.success(f"Brote '{nombre_nuevo}' creado.")
            st.rerun()

    if brote.get("es_dueno", brote["usuario_id"] == usuario_id):
        with st.expander("👥 Colaboradores de este brote"):
            with st.form("form_invitar_colaborador"):
                correo_colab = st.text_input("Correo del colaborador (debe tener cuenta ya creada)")
                invitar = st.form_submit_button("Invitar")
            if invitar and correo_colab.strip():
                try:
                    db.invitar_colaborador(brote["id"], correo_colab.strip())
                    st.success(f"{correo_colab} ahora puede ver y editar este brote.")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo invitar: {e}")

            try:
                colaboradores = db.listar_colaboradores(brote["id"])
            except Exception:
                colaboradores = []
            if colaboradores:
                st.caption("Colaboradores actuales:")
                for c in colaboradores:
                    cc1, cc2 = st.columns([4, 1])
                    cc1.caption(c["email"])
                    if cc2.button("✕", key=f"quitar_colab_{c['usuario_id']}"):
                        db.quitar_colaborador(brote["id"], c["usuario_id"])
                        st.rerun()
            else:
                st.caption("Todavía no hay colaboradores en este brote.")

        with st.expander("🔗 Compartir públicamente"):
            st.caption("Genera un enlace de solo lectura, sin necesidad de iniciar sesión.")
            if brote.get("token_publico"):
                url_publica = f"{URL_BASE_APP}/?token_publico={brote['token_publico']}"
                st.text_input("Enlace completo (cópialo y compártelo):", value=url_publica, key="url_publica_actual")
                if st.button("Revocar enlace público"):
                    db.revocar_token_publico(brote["id"])
                    st.rerun()
            else:
                if st.button("Generar enlace público"):
                    db.generar_token_publico(brote["id"])
                    st.rerun()

        with st.expander("⚠️ Eliminar este brote"):
            st.warning("Esto borra el brote y TODOS sus registros permanentemente. No se puede deshacer.")
            confirmar = st.checkbox(f"Sí, quiero eliminar '{brote['nombre']}' y todos sus datos", key="confirmar_eliminar_brote")
            if confirmar and st.button("Eliminar brote definitivamente"):
                db.eliminar_brote(brote["id"])
                st.success("Brote eliminado.")
                st.rerun()

    return brote


def seccion_lateral_captura(usuario_id: str, brote: dict):
    brote_id = brote["id"]
    catalogo_id = brote["usuario_id"]  # catálogo compartido: siempre el dueño del brote

    with st.expander("✍️ Registrar un caso", expanded=False):
        db.asegurar_vias_por_defecto(catalogo_id)
        vias = db.listar_vias(catalogo_id)
        nombres_vias = {v["nombre"]: v["id"] for v in vias}

        with st.popover("+ Añadir nueva vía de contagio"):
            nueva_via = st.text_input("Nombre de la vía", key="nueva_via_input")
            tipo_nueva_via = st.selectbox(
                "Tipo de transmisión",
                options=list(clasificacion.PERFILES_R0_POR_TIPO_VIA.keys()),
                format_func=lambda k: clasificacion.PERFILES_R0_POR_TIPO_VIA[k]["etiqueta"],
                key="tipo_nueva_via_input",
                help="Se usa solo para sugerir un R0 de referencia en el estimador de subregistro — no cambia los cálculos de Rt ni las proyecciones.",
            )
            if st.button("Guardar vía"):
                if nueva_via.strip():
                    db.crear_via(catalogo_id, nueva_via.strip(), tipo=tipo_nueva_via)
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
                ubicacion = db.obtener_o_crear_ubicacion(catalogo_id, pais.strip(), departamento.strip(), ciudad.strip(), barrio.strip())
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


def seccion_lateral_carga_masiva(usuario_id: str, brote: dict):
    brote_id = brote["id"]
    catalogo_id = brote["usuario_id"]

    with st.expander("📤 Cargar datos desde Excel/CSV", expanded=False):
        st.caption(
            "Columnas esperadas: **fecha, casos_nuevos, fallecidos, recuperados** "
            "(fallecidos/recuperados opcionales, se asumen 0). Opcionales: "
            "**via, pais, departamento, ciudad, barrio**."
        )
        modo = st.radio("Origen de los datos", ["Subir archivo", "Importar desde una URL pública (OMS, OPS, Datos Abiertos, etc.)"], key="modo_carga_masiva")

        df_subida = None
        if modo == "Subir archivo":
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
        else:
            st.caption(
                "Pega el enlace directo a un archivo CSV o Excel público — por ejemplo, un "
                "export de la OMS, la OPS, o cualquier portal de datos abiertos. La URL debe "
                "apuntar DIRECTAMENTE al archivo (terminar en .csv o .xlsx), no a una página web."
            )
            url_datos = st.text_input("URL del archivo CSV/Excel", key="url_carga_masiva")
            if url_datos and st.button("Descargar y previsualizar"):
                try:
                    resp = requests.get(url_datos, timeout=30)
                    resp.raise_for_status()
                    contenido = io.BytesIO(resp.content)
                    if url_datos.lower().endswith(".csv"):
                        df_subida = pd.read_csv(contenido)
                    else:
                        df_subida = pd.read_excel(contenido)
                    st.session_state["_df_url_cache"] = df_subida
                except Exception as e:
                    st.error(f"No se pudo descargar o leer el archivo desde esa URL: {e}")
                    return
            elif "_df_url_cache" in st.session_state:
                df_subida = st.session_state["_df_url_cache"]

        if df_subida is None:
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
                resultado = db.importar_registros_masivo(usuario_id, brote_id, filas, catalogo_usuario_id=catalogo_id)

            st.success(f"{resultado['exitosos']} filas importadas correctamente.")
            if resultado["fallidos"]:
                st.warning(f"{len(resultado['fallidos'])} filas fallaron.")
                st.dataframe(pd.DataFrame(resultado["fallidos"]), use_container_width=True)
            st.session_state.pop("_df_url_cache", None)
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


def seccion_lateral_admin(usuario_id: str):
    if not db.es_admin(usuario_id):
        return
    with st.expander("🔑 Administrador"):
        with st.form("form_config_anthropic"):
            st.caption("Clave de Anthropic para el chatbot de interpretación (🤖 en el dashboard) — aplica para TODOS los usuarios de la app, no solo para ti.")
            clave_actual = db.obtener_configuracion("ANTHROPIC_API_KEY")
            nueva_clave = st.text_input(
                "ANTHROPIC_API_KEY", type="password",
                placeholder="sk-ant-..." if not clave_actual else "•••••••••••••• (ya configurada, pega una nueva para reemplazarla)",
            )
            guardar_clave = st.form_submit_button("Guardar clave")
        if guardar_clave and nueva_clave.strip():
            try:
                db.guardar_configuracion_admin("ANTHROPIC_API_KEY", nueva_clave.strip())
                st.success("Clave guardada — ya aplica para todos los usuarios.")
            except Exception as e:
                st.error(f"No se pudo guardar: {e}")

        try:
            stats = db.estadisticas_globales_admin()
        except Exception as e:
            st.warning(f"No se pudieron cargar las estadísticas: {e}")
            return

        st.metric("Usuarios registrados (total)", stats["total_usuarios_registrados"])
        st.metric("Usuarios con al menos un registro", stats["usuarios_con_al_menos_un_registro"])
        st.metric("Usuarios activos (últimos 7 días)", stats["usuarios_activos_ultimos_7_dias"])
        st.metric("Registros diarios capturados (total)", stats["total_registros_capturados"])
        st.metric("Casos nuevos acumulados (todos los usuarios)", stats["total_casos_nuevos_acumulados"])
        st.metric("Fallecidos acumulados (todos los usuarios)", stats["total_fallecidos_acumulados"])

        st.markdown("**Usuarios registrados**")
        try:
            usuarios = db.listar_usuarios_admin()
        except Exception as e:
            st.error(f"No se pudo obtener la lista de usuarios: {e}")
            return

        for u in usuarios:
            cu1, cu2 = st.columns([4, 1])
            cu1.caption(f"{u['email']} — {'✅ confirmado' if u['confirmado'] else '⏳ sin confirmar'}")
            if u["usuario_id"] != usuario_id:  # no permitir auto-eliminarse desde aquí
                if cu2.button("🗑️", key=f"del_usuario_{u['usuario_id']}"):
                    st.session_state[f"confirmar_del_{u['usuario_id']}"] = True

            if st.session_state.get(f"confirmar_del_{u['usuario_id']}"):
                st.warning(f"¿Eliminar a {u['email']} y TODOS sus brotes/registros? No se puede deshacer.")
                cc1, cc2 = st.columns(2)
                if cc1.button("Sí, eliminar", key=f"confirmar_si_{u['usuario_id']}"):
                    try:
                        db.eliminar_usuario_admin(u["usuario_id"])
                        st.success("Usuario eliminado.")
                        del st.session_state[f"confirmar_del_{u['usuario_id']}"]
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo eliminar: {e}")
                if cc2.button("Cancelar", key=f"confirmar_no_{u['usuario_id']}"):
                    del st.session_state[f"confirmar_del_{u['usuario_id']}"]
                    st.rerun()


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


def _aplicar_interactividad_tiempo(fig):
    """Agrega scroll/zoom en el eje de tiempo: selector de rango (7d/30d/todo)
    y una barra deslizante debajo del gráfico para navegar el histórico."""
    fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=[
                dict(count=7, label="7d", step="day", stepmode="backward"),
                dict(count=30, label="30d", step="day", stepmode="backward"),
                dict(count=90, label="90d", step="day", stepmode="backward"),
                dict(step="all", label="Todo"),
            ]
        ),
    )
    return fig


def dashboard_grafico_principal(serie: list):
    df = pd.DataFrame(serie)
    if df.empty:
        st.info("Sin datos para graficar todavía.")
        return
    df["fecha"] = pd.to_datetime(df["fecha"])

    series_disponibles = {"Casos activos": "casos_activos", "Casos nuevos": "casos_nuevos"}
    seleccion = st.multiselect(
        "Mostrar en el gráfico:", options=list(series_disponibles.keys()),
        default=list(series_disponibles.keys()), key="filtro_grafico_principal",
    )

    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        if "Casos activos" in seleccion:
            fig.add_trace(go.Scatter(x=df["fecha"], y=df["casos_activos"], name="Casos activos",
                                      mode="lines+markers", line=dict(color=COLOR_AZUL_COMPLEMENTARIO, width=3)))
        if "Casos nuevos" in seleccion:
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
        fig = _aplicar_interactividad_tiempo(fig)
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.line_chart(df.set_index("fecha")[["casos_activos"]])


def dashboard_grafico_componentes(serie: list):
    """Evolución de activos vs. recuperados y fallecidos acumulados —
    para responder directamente '¿cómo van los recuperados y fallecidos?'"""
    df = pd.DataFrame(serie)
    if df.empty:
        return
    df["fecha"] = pd.to_datetime(df["fecha"])

    st.markdown("#### Activos, recuperados y fallecidos")
    series_disponibles = {"Activos": "casos_activos", "Recuperados (acum.)": "recuperados_acumulados", "Fallecidos (acum.)": "fallecidos_acumulados"}
    seleccion = st.multiselect(
        "Mostrar en el gráfico:", options=list(series_disponibles.keys()),
        default=list(series_disponibles.keys()), key="filtro_grafico_componentes",
    )

    try:
        import plotly.graph_objects as go

        colores = {"Activos": COLOR_AZUL_OSCURO, "Recuperados (acum.)": "green", "Fallecidos (acum.)": "red"}
        fig = go.Figure()
        for nombre in seleccion:
            campo = series_disponibles[nombre]
            fig.add_trace(go.Scatter(x=df["fecha"], y=df[campo], name=nombre, line=dict(color=colores[nombre], width=2 if nombre != "Activos" else 3)))
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified",
                           legend=dict(orientation="h", yanchor="bottom", y=1.02))
        fig = _aplicar_interactividad_tiempo(fig)
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.line_chart(df.set_index("fecha")[[series_disponibles[n] for n in seleccion]] if seleccion else df.set_index("fecha")[["casos_activos"]])


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


def seccion_proyeccion(serie: list, nombre_serie: str, brote_nombre: str):
    st.markdown("#### Proyección a futuro")
    n_dias_disponibles = len([r for r in serie if r.get("casos_activos") is not None])
    opciones_modelo = ["Regresión log-lineal (±2σ)"]
    if n_dias_disponibles >= 8:
        opciones_modelo.append("Crecimiento logístico (SIR simplificado)")
    if n_dias_disponibles >= 50:
        opciones_modelo.append("ARIMA (95% de confianza)")

    modelo_sel = st.selectbox("Modelo de proyección", options=opciones_modelo, key=f"modelo_{nombre_serie}")
    dias_futuros = st.slider("Días a proyectar", min_value=3, max_value=14, value=7, key=f"slider_{nombre_serie}")

    tabla_combinada = None
    mensaje_modelo = ""

    if modelo_sel.startswith("Regresión"):
        resultado = proyecciones.proyectar_regresion_log_lineal(serie, dias_futuros=dias_futuros)
        _mostrar_proyeccion_con_banda(serie, resultado, "Tasa de crecimiento diaria estimada", "tasa_crecimiento_diaria")
        if resultado["valido"]:
            activos_futuros = [{"fecha": p["fecha"], "valor": p["valor_central"]} for p in resultado["proyeccion"]]
            tabla_combinada = proyecciones.descomponer_proyeccion_desde_activos(serie, activos_futuros)
            mensaje_modelo = resultado["mensaje"]
    elif modelo_sel.startswith("ARIMA"):
        resultado = proyecciones.ajustar_arima(serie, dias_futuros=dias_futuros)
        _mostrar_proyeccion_con_banda(serie, resultado, None, None)
        if resultado["valido"]:
            activos_futuros = [{"fecha": p["fecha"], "valor": p["valor_central"]} for p in resultado["proyeccion"]]
            tabla_combinada = proyecciones.descomponer_proyeccion_desde_activos(serie, activos_futuros)
            mensaje_modelo = resultado["mensaje"]
    else:
        resultado = proyecciones.ajustar_crecimiento_logistico(serie, dias_futuros=dias_futuros)
        _mostrar_proyeccion_logistica(resultado, serie)
        if resultado["valido"]:
            nuevos_futuros = [{"fecha": p["fecha"], "valor": p["casos_nuevos_proyectados"]} for p in resultado["proyeccion"]]
            tabla_combinada = proyecciones.descomponer_proyeccion_desde_nuevos(serie, nuevos_futuros)
            mensaje_modelo = resultado["mensaje"]

    if tabla_combinada:
        _mostrar_tabla_componentes_proyectados(tabla_combinada)

        pdf_bytes = reportes.generar_pdf_reporte(brote_nombre, serie, tabla_combinada, mensaje_modelo)
        st.download_button(
            "📄 Exportar reporte a PDF (histórico + proyección)",
            data=pdf_bytes,
            file_name=f"reporte_{brote_nombre}_{date.today().isoformat()}.pdf",
            mime="application/pdf",
        )


def _mostrar_tabla_componentes_proyectados(tabla_combinada: list):
    st.markdown("##### Proyección de nuevos, activos, recuperados y fallecidos")
    st.caption(
        "Recuperados y fallecidos proyectados se derivan de las tasas históricas de "
        "letalidad y recuperación observadas en este brote, aplicadas hacia adelante."
    )

    df = pd.DataFrame(tabla_combinada)
    try:
        import plotly.graph_objects as go

        df_plot = df.copy()
        df_plot["fecha"] = pd.to_datetime(df_plot["fecha"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_plot["fecha"], y=df_plot["casos_nuevos_proyectados"], name="Nuevos", line=dict(color=COLOR_CIAN, width=2)))
        fig.add_trace(go.Scatter(x=df_plot["fecha"], y=df_plot["casos_activos_proyectados"], name="Activos", line=dict(color=COLOR_AZUL_OSCURO, width=3)))
        fig.add_trace(go.Scatter(x=df_plot["fecha"], y=df_plot["recuperados_proyectados"], name="Recuperados", line=dict(color="green", width=2)))
        fig.add_trace(go.Scatter(x=df_plot["fecha"], y=df_plot["fallecidos_proyectados"], name="Fallecidos", line=dict(color="red", width=2)))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified",
                           legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        pass

    df["fecha"] = pd.to_datetime(df["fecha"]).dt.strftime("%d/%m/%Y")
    df = df.rename(columns={
        "fecha": "Fecha", "casos_nuevos_proyectados": "Nuevos proy.",
        "casos_activos_proyectados": "Activos proy.", "recuperados_proyectados": "Recuperados proy.",
        "fallecidos_proyectados": "Fallecidos proy.",
    })
    st.dataframe(df.round(1), use_container_width=True, hide_index=True)


def _mostrar_proyeccion_con_banda(serie: list, resultado: dict, etiqueta_metrica, campo_metrica):
    if not resultado["valido"]:
        st.warning(resultado["mensaje"])
        return
    st.caption(resultado["mensaje"])

    df_hist = pd.DataFrame([{"fecha": r["fecha"], "valor": r["casos_activos"]} for r in serie if r.get("casos_activos") is not None])
    df_proy = pd.DataFrame([{"fecha": p["fecha"], "valor": p["valor_central"],
                              "limite_inferior": p["limite_inferior"], "limite_superior": p["limite_superior"]}
                             for p in resultado["proyeccion"]])

    # Conectar visualmente el histórico con la proyección: sin este punto
    # "puente", la línea de proyección arranca un día después de donde
    # termina el histórico y se ve como un corte/salto en el gráfico.
    if not df_hist.empty and not df_proy.empty:
        ultimo_punto = df_hist.iloc[-1]
        puente = pd.DataFrame([{
            "fecha": ultimo_punto["fecha"], "valor": ultimo_punto["valor"],
            "limite_inferior": ultimo_punto["valor"], "limite_superior": ultimo_punto["valor"],
        }])
        df_proy = pd.concat([puente, df_proy], ignore_index=True)

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
        fig = _aplicar_interactividad_tiempo(fig)
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.info("Instala 'plotly' para ver el gráfico interactivo.")

    if etiqueta_metrica and campo_metrica in resultado:
        c1, c2 = st.columns(2)
        c1.metric(etiqueta_metrica, f"{resultado[campo_metrica]:.3f}")
        c2.metric("Días usados en el ajuste", resultado["n_dias_usados_en_ajuste"])
    else:
        st.metric("Días usados en el ajuste", resultado["n_dias_usados_en_ajuste"])


def _mostrar_proyeccion_logistica(resultado: dict, serie: list):
    if not resultado["valido"]:
        st.warning(resultado["mensaje"])
        return
    st.caption(resultado["mensaje"])
    c1, c2, c3 = st.columns(3)
    c1.metric("K (techo estimado)", f"{resultado['K_techo_estimado']:.0f}")
    c2.metric("r (tasa de crecimiento)", f"{resultado['r_tasa_crecimiento']:.3f}")
    c3.metric("Días usados en el ajuste", resultado["n_dias_usados_en_ajuste"])

    # Este modelo proyecta CASOS ACUMULADOS (no activos), así que se
    # compara contra el acumulado histórico — no contra casos_activos,
    # que es una magnitud distinta.
    df_hist = pd.DataFrame([{"fecha": r["fecha"], "valor": r["casos_acumulados"]} for r in serie if r.get("casos_acumulados") is not None])
    df_proy = pd.DataFrame([{
        "fecha": p["fecha"], "valor": p["casos_acumulados_proyectados"],
        "limite_inferior": p["casos_acumulados_limite_inferior"], "limite_superior": p["casos_acumulados_limite_superior"],
    } for p in resultado["proyeccion"]])

    if not df_hist.empty and not df_proy.empty:
        ultimo_punto = df_hist.iloc[-1]
        puente = pd.DataFrame([{
            "fecha": ultimo_punto["fecha"], "valor": ultimo_punto["valor"],
            "limite_inferior": ultimo_punto["valor"], "limite_superior": ultimo_punto["valor"],
        }])
        df_proy = pd.concat([puente, df_proy], ignore_index=True)

    try:
        import plotly.graph_objects as go

        df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])
        df_proy["fecha"] = pd.to_datetime(df_proy["fecha"])

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_proy["fecha"], y=df_proy["limite_superior"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=df_proy["fecha"], y=df_proy["limite_inferior"], fill="tonexty",
                                  fillcolor="rgba(158,51,178,0.2)", line=dict(width=0), name="Banda de incertidumbre"))
        fig.add_trace(go.Scatter(x=df_hist["fecha"], y=df_hist["valor"], name="Histórico (acumulado)",
                                  line=dict(color=COLOR_AZUL_OSCURO, width=3)))
        fig.add_trace(go.Scatter(x=df_proy["fecha"], y=df_proy["valor"], name="Proyección (acumulado)",
                                  line=dict(color=COLOR_VIOLETA, width=3, dash="dash")))
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified",
                           yaxis_title="Casos acumulados")
        fig = _aplicar_interactividad_tiempo(fig)
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.info("Instala 'plotly' para ver el gráfico interactivo.")

    df_tabla = pd.DataFrame(resultado["proyeccion"])
    df_tabla["fecha"] = pd.to_datetime(df_tabla["fecha"]).dt.strftime("%d/%m/%Y")
    df_tabla = df_tabla.rename(columns={
        "fecha": "Fecha", "casos_acumulados_proyectados": "Acumulados proy.",
        "casos_acumulados_limite_inferior": "Límite inferior", "casos_acumulados_limite_superior": "Límite superior",
        "casos_nuevos_proyectados": "Nuevos proy.",
    })
    st.dataframe(df_tabla.round(1), use_container_width=True, hide_index=True)


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


def seccion_comparar_brotes(usuario_id: str, brote_actual_id: int):
    todos_los_brotes = db.listar_brotes(usuario_id)
    if len(todos_los_brotes) < 2:
        return

    with st.expander("📊 Comparar con otros brotes"):
        etiquetas = {b["nombre"]: b for b in todos_los_brotes}
        seleccionados = st.multiselect(
            "Selecciona brotes a comparar (por días desde su inicio, no por fecha calendario)",
            options=list(etiquetas.keys()),
        )
        if not seleccionados:
            st.caption("Elige al menos un brote para comparar contra el actual.")
            return

        try:
            import plotly.graph_objects as go

            fig = go.Figure()
            colores = [COLOR_AZUL_OSCURO, COLOR_VIOLETA, COLOR_CIAN, COLOR_AZUL_COMPLEMENTARIO, "green", "orange"]
            for i, nombre in enumerate(seleccionados):
                b = etiquetas[nombre]
                registros_b = db.obtener_registros(usuario_id, brote_id=b["id"])
                if not registros_b:
                    continue
                serie_b = calculos.recalcular_serie(registros_b)
                dias = list(range(len(serie_b)))
                activos = [r["casos_activos"] for r in serie_b]
                fig.add_trace(go.Scatter(x=dias, y=activos, name=nombre, line=dict(color=colores[i % len(colores)], width=2)))

            fig.update_layout(
                height=380, xaxis_title="Días desde el inicio del brote", yaxis_title="Casos activos",
                margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.info("Instala 'plotly' para ver la comparación.")


def seccion_historial_cambios(brote_id: int):
    with st.expander("📝 Historial de cambios (auditoría)"):
        try:
            historial = db.obtener_historial(brote_id)
        except Exception as e:
            st.error(f"No se pudo cargar el historial: {e}")
            return
        if not historial:
            st.caption("Sin cambios registrados todavía.")
            return
        for h in historial:
            icono = {"crear": "🟢", "actualizar": "🟡", "eliminar": "🔴"}.get(h["accion"], "⚪")
            fecha_legible = pd.to_datetime(h["creado_en"]).strftime("%d/%m/%Y %H:%M")
            st.caption(f"{icono} {h['accion'].capitalize()} — registro #{h['registro_id']} — {fecha_legible}")


def seccion_subregistro(serie: list, tipo_via_actual: str = None):
    with st.expander("🔬 Estimar infectados no diagnosticados"):
        st.caption(
            "Usa la relación de tamaño final de un modelo SIR cerrado para estimar, de forma "
            "orientativa, cuántas infecciones totales (diagnosticadas + no diagnosticadas) "
            "implicaría un R0 dado. No es un conteo preciso — es una herramienta de planeación."
        )
        casos_diagnosticados_default = sum(r["casos_nuevos"] for r in serie)

        r0_default = 2.0
        if tipo_via_actual:
            perfil = clasificacion.obtener_perfil_r0(tipo_via_actual)
            r0_default = perfil["r0_sugerido"]
            st.info(
                f"Vía **{perfil['etiqueta']}**: R0 de referencia sugerido **{perfil['r0_sugerido']}** "
                f"(rango típico {perfil['rango'][0]}–{perfil['rango'][1]}). {perfil['nota']}"
            )

        c1, c2 = st.columns(2)
        r0 = c1.number_input("R0 (número reproductivo básico)", min_value=0.1, value=r0_default, step=0.1)
        poblacion_total = c2.number_input("Población total del área", min_value=1, value=100000, step=1000)
        poblacion_susceptible = c1.number_input("Población susceptible (sin inmunidad)", min_value=1, value=int(poblacion_total * 0.9), step=1000)
        casos_diagnosticados = c2.number_input("Casos diagnosticados acumulados", min_value=0, value=int(casos_diagnosticados_default), step=1)

        if st.button("Calcular estimación"):
            resultado = proyecciones.estimar_infectados_no_diagnosticados(r0, int(poblacion_total), int(poblacion_susceptible), int(casos_diagnosticados))
            if not resultado["valido"]:
                st.warning(resultado["mensaje"])
            else:
                st.caption(resultado["mensaje"])
                cc1, cc2, cc3 = st.columns(3)
                cc1.metric("Infectados totales estimados", f"{resultado['infectados_totales_estimados']:.0f}")
                cc2.metric("No diagnosticados estimados", f"{resultado['no_diagnosticados_estimados']:.0f}")
                tasa = resultado["tasa_deteccion_estimada"]
                cc3.metric("Tasa de detección estimada", f"{tasa*100:.1f}%" if tasa is not None else "N/D")


def seccion_chatbot_interpretacion(serie: list, velocidad: dict, fase: dict, brote_nombre: str, vista: str):
    with st.expander("🤖 ¿No entiendes la gráfica? Pídele una explicación a la IA"):
        # Primero busca la clave configurada por el admin (aplica para
        # todos); si no existe, cae a los Secrets de Streamlit (por si
        # se configuró a la manera antigua).
        try:
            api_key = db.obtener_configuracion("ANTHROPIC_API_KEY")
        except Exception:
            api_key = None
        if not api_key:
            api_key = st.secrets.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY"))

        if not api_key:
            st.caption(
                "Esta función todavía no está activada. El administrador de la app puede "
                "configurarla en el menú 🔑 Administrador de la barra lateral."
            )
            return

        if st.button("Explícame estos datos en palabras simples"):
            ultimo = serie[-1] if serie else {}
            rt_ultimo = ultimo.get("rt_efectivo")
            resumen = {
                "brote_nombre": brote_nombre,
                "vista": vista,
                "casos_activos_actuales": ultimo.get("casos_activos", "N/D"),
                "tasa_r": f"{velocidad['tasa_r']:.3f}" if velocidad["tasa_r"] is not None else "N/D",
                "dias_duplicacion": f"{velocidad['dias_duplicacion']:.1f}" if velocidad["dias_duplicacion"] is not None else "N/D",
                "fase": fase["fase"],
                "rt_ultimo": f"{rt_ultimo:.2f}" if rt_ultimo == rt_ultimo else "N/D",
            }
            with st.spinner("Pensando..."):
                resultado = interpretacion.generar_interpretacion(resumen, api_key)
            if not resultado["valido"]:
                st.warning(resultado["mensaje"])
            else:
                st.markdown(resultado["texto"])


def seccion_datos_oficiales(serie: list):
    with st.expander("🏛️ Comparar con Datos Abiertos Colombia"):
        st.caption(
            "Compara tus casos contra el dataset oficial de COVID-19 en datos.gov.co, filtrado "
            "por departamento. Si tu brote es de otra enfermedad, este dataset específico no "
            "aplicará — es un ejemplo configurado por defecto (ver datos_oficiales.py)."
        )
        departamento = st.text_input("Departamento (como aparece en el dataset oficial)", value="Valle del Cauca")
        fechas_disponibles = [r["fecha"] for r in serie]
        if not fechas_disponibles:
            return
        fecha_desde = str(fechas_disponibles[0])[:10]
        fecha_hasta = str(fechas_disponibles[-1])[:10]

        if st.button("Consultar cifras oficiales"):
            with st.spinner("Consultando datos.gov.co..."):
                resultado = datos_oficiales.obtener_casos_oficiales_por_departamento(departamento, fecha_desde, fecha_hasta)
            if not resultado["valido"]:
                st.warning(resultado["mensaje"])
            else:
                st.caption(resultado["mensaje"])
                df_oficial = pd.DataFrame(resultado["datos"])
                if not df_oficial.empty:
                    st.dataframe(df_oficial, use_container_width=True, hide_index=True)


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
        seccion_lateral_captura(usuario["id"], brote)
        seccion_lateral_carga_masiva(usuario["id"], brote)
        seccion_lateral_editar_eliminar(usuario["id"], brote["id"])
        st.divider()
        seccion_lateral_admin(usuario["id"])
        st.divider()
        seccion_lateral_donacion()

    st.title(f"🦠 Dashboard — {brote['nombre']}")
    if brote.get("descripcion"):
        st.caption(brote["descripcion"])

    registros = db.obtener_registros(usuario["id"], brote_id=brote["id"])
    if not registros:
        st.info("Este brote todavía no tiene registros. Usa el panel de la izquierda para capturar el primero.")
        return

    por_via = calculos.recalcular_por_via(registros)
    opciones_vista = ["TOTAL"] + [k for k in por_via.keys() if k != "TOTAL"]
    vista_sel = st.selectbox("Ver serie:", options=opciones_vista, key="vista_dashboard")
    serie = por_via[vista_sel]

    # Tipo de la vía actualmente seleccionada (si no es TOTAL), para
    # sugerir un R0 de referencia en el estimador de subregistro.
    tipo_via_actual = None
    if vista_sel != "TOTAL":
        vias_del_brote = db.listar_vias(brote["usuario_id"])
        via_encontrada = next((v for v in vias_del_brote if v["nombre"] == vista_sel), None)
        tipo_via_actual = via_encontrada.get("tipo") if via_encontrada else None

    velocidad = calculos.tasa_crecimiento_y_duplicacion(serie)
    fase = clasificacion.clasificar_fase_heuristica(velocidad["tasa_r"])

    dashboard_kpis(serie, velocidad, fase)
    dashboard_grafico_principal(serie)
    dashboard_grafico_componentes(serie)
    dashboard_comparacion_vias(por_via)
    dashboard_mapa(usuario["id"], brote["id"])
    dashboard_tabla_y_export(serie, vista_sel)
    seccion_proyeccion(serie, vista_sel, brote["nombre"])
    seccion_comparar_brotes(usuario["id"], brote["id"])
    seccion_historial_cambios(brote["id"])
    seccion_subregistro(serie, tipo_via_actual)
    seccion_datos_oficiales(serie)
    seccion_chatbot_interpretacion(serie, velocidad, fase, brote["nombre"], vista_sel)

    conteo_por_via = db.contar_registros_por_via(usuario["id"], brote_id=brote["id"])
    sugerencia = sm.sugerir_modelo(len(registros), conteo_por_via)
    st.caption(sugerencia["mensaje"])


# =======================================================================
# DASHBOARD PÚBLICO — vista de solo lectura, sin necesidad de login
# =======================================================================
def pantalla_dashboard_publico(token: str):
    try:
        datos = db.obtener_brote_publico(token)
    except Exception as e:
        st.error(f"Este enlace no es válido o fue revocado por el dueño del brote. ({e})")
        return

    st.title(f"🦠 {datos.get('nombre', 'Brote')} — Vista pública")
    if datos.get("descripcion"):
        st.caption(datos["descripcion"])
    st.info("Estás viendo un dashboard público de solo lectura, compartido por el equipo de seguimiento.")

    st.markdown(
        f'<a class="boton-donar" href="{LINK_DONACION}" target="_blank">💙 Apoya a la Fundación Juan Manuel Collazos — Donar</a>',
        unsafe_allow_html=True,
    )
    st.write("")

    registros = datos.get("registros") or []
    if not registros:
        st.info("Este brote todavía no tiene registros públicos.")
        return

    # Adaptar al formato que espera calculos.recalcular_serie (mismos
    # nombres de campo que trae la función pública)
    serie = calculos.recalcular_serie(registros)

    velocidad = calculos.tasa_crecimiento_y_duplicacion(serie)
    fase = clasificacion.clasificar_fase_heuristica(velocidad["tasa_r"])
    dashboard_kpis(serie, velocidad, fase)
    dashboard_grafico_principal(serie)
    dashboard_grafico_componentes(serie)


# ---------------------------------------------------------------------
# Enrutamiento
# ---------------------------------------------------------------------
_parametros_url = st.query_params
_token_publico = _parametros_url.get("token_publico")

if _token_publico:
    pantalla_dashboard_publico(_token_publico)
elif "usuario" not in st.session_state:
    pantalla_login()
else:
    app_principal()
