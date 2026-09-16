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

## Próximos pasos sugeridos

1. Implementar el ajuste real de cada modelo (regresión log-lineal, SIR/SEIR,
   Holt, ARIMA) como funciones que reciben la ventana de 15 días
   (`db.obtener_registros_ultimos_n_dias`) y devuelven la proyección.
2. Implementar el modelo de ML de clasificación de fase, entrenado con
   el histórico acumulado completo (no solo la ventana de 15 días).
3. Añadir exportación de reportes (Excel/PDF) — reutilizable de tu
   experiencia previa con Clinical Extractor Pro.
4. Añadir gráfico comparativo de velocidad de transmisión entre vías
   de contagio (ya calculada en `calculos.tasa_crecimiento_y_duplicacion`).
