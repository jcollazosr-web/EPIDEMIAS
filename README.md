# Sistema de Seguimiento de Epidemia — Esqueleto comercial

Esqueleto funcional de la app: registro/login de usuarios, aislamiento de
datos por usuario (Row Level Security en Postgres), captura diaria de
casos por vía de contagio, y el motor de sugerencia de modelo predictivo
según volumen de datos disponible.

Los modelos predictivos en sí (regresión, SIR/SEIR, ARIMA, ML) **no están
implementados todavía** — este esqueleto deja los "ganchos" listos
(`db.obtener_registros_ultimos_n_dias`, `sugerencia_modelos.py`) para
conectarlos como siguiente paso.

## 1. Crear el proyecto en Supabase

1. Ve a https://supabase.com y crea un proyecto gratuito.
2. En **Project Settings > API**, copia:
   - `Project URL` → será tu `SUPABASE_URL`
   - `anon public key` → será tu `SUPABASE_ANON_KEY`
3. En **Authentication > Providers**, confirma que "Email" esté habilitado.
4. (Recomendado) En **Authentication > Settings**, activa "Confirm email"
   para que el registro abierto no permita cuentas falsas sin verificar.
5. (Recomendado) Activa hCaptcha en **Authentication > Settings** para
   prevenir registro masivo de bots, dado que el acceso es público.

## 2. Ejecutar el esquema de base de datos

1. En el dashboard de Supabase, ve a **SQL Editor**.
2. Pega y ejecuta el contenido completo de `schema.sql`.
3. Verifica en **Table Editor** que aparezcan las tablas:
   `vias_contagio`, `registros_diarios`, `perfiles`.
4. Verifica en cada tabla que "Row Level Security" aparezca como
   **Enabled** (así lo deja el script, pero confírmalo).

## 3. Configurar credenciales locales

```bash
mkdir -p .streamlit
cp secrets.toml.example .streamlit/secrets.toml
# Edita .streamlit/secrets.toml con tus valores reales de Supabase
```

## 4. Instalar dependencias y correr localmente

```bash
python -m venv venv
source venv/bin/activate          # En Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## 5. Desplegar (gratis) en Streamlit Community Cloud

1. Sube este proyecto a un repositorio de GitHub (sin el `secrets.toml`
   real — usa `.gitignore` para excluirlo).
2. En https://share.streamlit.io, conecta el repositorio.
3. En la configuración de la app, pega el contenido de tu
   `secrets.toml` real en la sección "Secrets" del panel de Streamlit
   Cloud (no se sube por git, se configura ahí directamente).
4. Despliega. La base de datos vive en Supabase, así que los datos
   persisten aunque la app de Streamlit se reinicie por inactividad.

## Estructura del proyecto

```
seguimiento_epidemia/
├── app.py                    # Interfaz de Streamlit (login + captura + tabla)
├── db.py                     # Capa de acceso a datos (Supabase)
├── calculos.py                # Recálculo de casos activos, Rt, velocidad de transmisión
├── sugerencia_modelos.py      # Motor de recomendación de modelo según volumen de datos
├── schema.sql                 # Esquema de base de datos + políticas RLS
├── requirements.txt
├── secrets.toml.example
└── README.md
```

## Novedades de esta versión

- **Múltiples brotes**: cada usuario puede crear y llevar en paralelo tantas
  epidemias (brotes) como quiera, cada una con su propia línea de tiempo,
  vías y ubicaciones independientes. Selector en la barra lateral.
- **Diseño rediseñado**: todos los controles de captura, carga y edición
  viven en la barra lateral izquierda, organizados en menús desplegables;
  el cuerpo principal es un dashboard de solo lectura con gráficos
  interactivos (Plotly).
- **Carga masiva desde Excel/CSV**: en la barra lateral, sube un archivo
  con columnas `fecha, casos_nuevos, fallecidos, recuperados` (y
  opcionalmente `via, pais, departamento, ciudad, barrio`).
- **Colores de marca**: la interfaz usa la paleta del Manual de Identidad
  Corporativa de la Fundación (`.streamlit/config.toml` + CSS inline).
- **Botón de donación**: enlaza al checkout de Bold de la Fundación,
  visible tanto en la pantalla de login como en la barra lateral.
- **Menú "🔑 Administrador"**: todas las estadísticas globales y la lista
  de usuarios quedaron agrupadas en un único menú desplegable en la
  barra lateral (solo visible para cuentas con rol admin).
- **Gráfica de activos/recuperados/fallecidos**: además del gráfico de
  casos activos y nuevos, ahora se ve la evolución acumulada de
  recuperados y fallecidos.
- **Proyección completa**: debajo del gráfico de proyección aparece una
  tabla y gráfico con los 4 componentes proyectados (nuevos, activos,
  recuperados, fallecidos), derivados de las tasas históricas de
  letalidad/recuperación del propio brote.
- **Exportar reporte a PDF**: botón de descarga con el histórico
  reciente, el gráfico y la tabla de proyección completa.
- **Bug corregido**: `admin_listar_usuarios()` fallaba por una discrepancia
  de tipos (`varchar` vs `text`) al leer `auth.users.email` — ya corregido
  en la base de datos y en `schema.sql`.

## Novedades de esta versión (lote grande)

- **Colaboradores por brote**: el dueño puede invitar (por correo) a otros
  usuarios ya registrados a ver/editar un brote específico.
- **Auditoría de cambios**: cada crear/actualizar/eliminar sobre un registro
  queda guardado en `historial_cambios`, visible en el dashboard.
- **Dashboard público**: enlace `?token_publico=...` que muestra un
  resumen de solo lectura sin necesidad de iniciar sesión — ideal para
  compartir con donantes o la comunidad.
- **Comparar brotes**: gráfico que superpone la curva de varios brotes,
  alineados por "días desde el inicio" (no por fecha calendario).
- **Botón de eliminar brote completo** y **botón de eliminar usuarios**
  (panel de administrador), ambos con confirmación.
- **±2σ en TODOS los modelos de proyección**, incluido el crecimiento
  logístico (antes no tenía banda de incertidumbre).
- **Gráficas más interactivas**: zoom, selector de rango (7d/30d/90d/todo)
  y barra deslizante en el eje de tiempo (Plotly rangeslider).
- **Estimador de infectados no diagnosticados**: a partir de R0, población
  total y susceptible, usando la relación de tamaño final de un SIR
  cerrado — es una herramienta orientativa de planeación, no un conteo
  preciso (documentado así en la propia interfaz).
- **Integración con Datos Abiertos Colombia**: comparación contra el
  dataset oficial de COVID-19 (datos.gov.co) filtrado por departamento.
  ⚠️ No se pudo probar en vivo desde el entorno de desarrollo (el dominio
  datos.gov.co no está en su lista de acceso) — pruébalo tú en la app ya
  desplegada y avisa si falla.

### Nota técnica importante: catálogos compartidos entre colaboradores
Las vías de contagio y ubicaciones ahora son de LECTURA abierta para
cualquier usuario autenticado (son solo etiquetas descriptivas, sin datos
sensibles) — esto es necesario para que un colaborador vea correctamente
los nombres en un brote compartido. La ESCRITURA (crear/editar/borrar via
o ubicación) sigue restringida al dueño del catálogo.

### Bugs corregidos después del despliegue
- `KeyError: 'es_dueno'` al listar brotes si la app corría con un
  despliegue a mitad de camino — ahora es defensivo (`.get(...)`).
- Al eliminar un brote completo, el trigger de auditoría intentaba
  registrar el borrado en cascada de sus registros usando un `brote_id`
  que ya no existía (violación de llave foránea). El trigger ahora
  verifica que el brote siga existiendo antes de auditar un borrado.
- **Bug crítico de concurrencia**: el cliente de Supabase estaba cacheado
  con `@st.cache_resource`, compartiendo UN SOLO objeto entre TODOS los
  usuarios del servidor. Cerrar sesión (o cualquier cambio de auth) podía
  afectar a otras sesiones activas en el mismo proceso, o dejar una
  sesión "zombie" que fallaba con 401 en la siguiente operación (esto
  fue lo que causó el error al intentar cerrar sesión). Ahora cada
  sesión de navegador tiene su propio cliente en `st.session_state`.

### Lote: correcciones de gráficas + nuevas funciones (sesión de depuración)
- **Fix crítico de sesión**: `set_session()` del SDK no sincronizaba
  siempre el header de PostgREST al restaurar desde cookie — se fuerza
  ahora explícitamente con `client.postgrest.auth(access_token)`.
  `sign_out()` cambiado a `scope="local"`.
- **Fix de gráficas de proyección**: la línea de proyección no conectaba
  visualmente con el histórico (se veía "cortada"). Se agrega un punto
  puente en ambos modelos.
- El modelo de **crecimiento logístico ahora tiene gráfico** (antes solo
  mostraba tabla), comparado correctamente contra el acumulado histórico.
- **Filtros de series** en los gráficos (activos/nuevos/recuperados/
  fallecidos) vía multiselect.
- **Tipo de vía de contagio** (respiratoria, zoonótica, contacto directo,
  vectorial, hídrica/alimentaria, sexual, otra) con perfiles de R0
  orientativos (`clasificacion.PERFILES_R0_POR_TIPO_VIA`) que alimentan
  el estimador de subregistro.
- **Chatbot de interpretación** (`interpretacion.py`, API de Claude) —
  requiere `ANTHROPIC_API_KEY` propia en los secrets.
- **Importar desde URL pública** (OMS, OPS, cualquier portal) además de
  subir archivo local, en la carga masiva.
- **Enlace público completo** con la URL real de la app
  (`https://epidemias-jmcr.streamlit.app`).
- **Manual de uso no técnico** (`MANUAL_DE_USO.md`), enlazado también
  dentro de la app en la barra lateral ("❓ Cómo usar esta app").

### Lote: rediseño de marca + edición + interactividad (EpiScan)
- **App renombrada a "EpiScan"** (subtítulo: "Sistema de vigilancia
  epidemiológica"), logo recortado y en tamaño más discreto.
- **Ícono personalizado del chatbot**: robot con pensamiento flotante,
  dibujado con los colores de marca (`assets/robot_pensamiento.png`).
- **Edición real de registros** (antes solo se podía eliminar): botón
  ✏️ abre un formulario para modificar fecha, vía, casos, fallecidos
  y recuperados de un registro existente.
- **Filtros como botones de clic** (`st.pills`, con respaldo a
  checkboxes en versiones antiguas de Streamlit) en vez de menús
  desplegables, en los 3 gráficos principales.
- **Barra de desplazamiento simplificada**: se quitaron los botones
  7d/30d/90d/Todo (confundían junto a la vista previa en miniatura),
  dejando una barra delgada aplicada consistentemente a TODOS los
  gráficos de series temporales.
- **Gráfico de activos/recuperados/fallecidos** ahora incluye también
  las series por día (no solo acumuladas), todas filtrables.
- **Botón "📊 Análisis descriptivo"** bajo los 3 gráficos principales,
  conectado a la IA (misma clave que gestiona el admin).

### Lote: anotaciones, sparklines, eventos, mapa de calor
- **Anotaciones automáticas**: línea + etiqueta en el día del pico de
  casos activos, y líneas de cambio de fase (aceleración/meseta/
  desaceleración) directamente sobre el gráfico principal.
- **Sparklines** en los KPIs de Casos activos y Rt (mini-tendencia de
  los últimos 14 días debajo del número).
- **Comparar todas las vías EN el gráfico principal**: interruptor
  "Comparar todas las vías aquí" superpone las líneas de cada vía.
- **Eventos/intervenciones**: nueva sección en la barra lateral para
  marcar fechas clave (vacunación, cuarentena, etc.), que se dibujan
  como líneas verticales con etiqueta en los gráficos.
- **Mapa de calor semanal**: día de la semana vs. semana del año, para
  detectar patrones (¿suben los casos los fines de semana?).
- **Layout en columnas**: el gráfico principal y el mapa de casos ahora
  van lado a lado en pantallas anchas, en vez de apilados.

### Lote: geolocalización mejorada + clusters automáticos
- **Menús desplegables de país/departamento/ciudad** en vez de texto
  libre — evita errores ortográficos que rompían la geocodificación.
  Colombia tiene los 33 departamentos y ciudades principales por
  departamento; siempre hay una opción "Otro/a (escribir)" para lo que
  no esté en la lista (`geografia.py`).
- **Casos el mismo día en lugares distintos**: ya era posible a nivel
  de base de datos (la restricción única incluye la ubicación); con los
  menús desplegables ahora es más rápido cambiar de ubicación entre un
  registro y otro sin volver a escribir todo.
- **Clusters geográficos automáticos** (`clusters.py`): agrupa las
  ubicaciones del brote por cercanía (distancia en línea recta,
  Union-Find) y calcula casos totales y velocidad de transmisión de
  forma INDEPENDIENTE para cada cluster — con un radio ajustable y
  botón de análisis descriptivo con IA sobre los clusters detectados.
- **Sobre Google Maps**: se evaluó pero se recomienda mantener
  OpenStreetMap (gratis, sin tarjeta de crédito) — Google Maps requiere
  facturación de Google Cloud más allá de su crédito mensual gratuito.

- **Captura de ubicación por GPS**: botón "📍 Usar mi ubicación GPS
  actual" en el formulario de captura — pide el GPS del navegador/celular
  y usa esa coordenada exacta (con geocodificación inversa para sugerir
  país/ciudad), en vez de depender de escribir el nombre del lugar.
  ⚠️ No se pudo probar en vivo desde el entorno de desarrollo (mismo
  límite de red de siempre) — pruébalo tú en la app desplegada.

## Estado actual de los modelos predictivos

- ✅ Regresión log-lineal con banda ±2σ
- ✅ Crecimiento logístico (SIR/SEIR simplificado, sin necesitar población total)
- ✅ ARIMA con intervalo de confianza del 95% (requiere 50+ días)
- ✅ Clasificación de fase (aceleración/meseta/desaceleración) — **heurística
  por ahora**, no un modelo de ML entrenado (ver `clasificacion.py` para el
  razonamiento: no hay histórico de brotes etiquetados todavía para entrenar
  un clasificador real)
- ✅ Comparación de velocidad de transmisión entre vías
- ✅ Exportación a Excel de la tabla histórica

## Próximos pasos sugeridos

1. Exportación a PDF (hoy solo Excel).
2. Entrenar el clasificador de fase con ML real una vez acumules varios
   brotes/periodos históricos ya resueltos (ver el umbral en
   `sugerencia_modelos.UMBRAL_ML_POR_VIA`).
3. hCaptcha en el registro (configuración manual en el dashboard de
   Supabase: Authentication > Settings).
4. Repositorio de GitHub en privado (Settings > Danger Zone > Change visibility).
5. Considerar el plan Pro de Supabase y evitar que Streamlit Cloud
   "duerma" la app, si el uso real empieza a ser constante.
