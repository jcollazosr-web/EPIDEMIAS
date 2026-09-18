# Manual de Uso — Sistema de Seguimiento de Epidemia

Guía rápida para usar la app sin necesidad de conocimientos técnicos.

## 1. Crear tu cuenta

1. Entra a la app y ve a la pestaña **"Crear cuenta"**.
2. Escribe tu correo y una contraseña (mínimo 6 caracteres).
3. Revisa tu correo y confirma la cuenta antes de iniciar sesión.

## 2. Tu primer brote

Al entrar por primera vez, la app te crea automáticamente un brote
llamado **"Brote 1"**. Un "brote" es una epidemia que estás siguiendo —
puedes crear tantos como necesites (por ejemplo, uno para dengue y
otro para una gripe estacional, cada uno con su propio historial).

Para crear uno nuevo: en la barra lateral izquierda, abre
**"+ Crear nuevo brote"**, ponle un nombre y guárdalo. Para cambiar
entre brotes, usa el menú desplegable arriba de esa misma sección.

## 3. Registrar un caso

En la barra lateral, abre **"✍️ Registrar un caso"**:
- Elige la fecha.
- Elige (o crea) la **vía de contagio** — respiratoria, contacto
  directo, zoonótica, vectorial, etc. Esto es opcional pero útil: la
  app usa ese dato para sugerirte parámetros más adelante.
- Escribe el país/ciudad (se ubica solo en el mapa).
- Escribe cuántos casos nuevos, fallecidos y recuperados hubo ESE día.
- Dale "Guardar registro".

Si registras la misma fecha y vía dos veces, la app actualiza el
registro existente en vez de duplicarlo.

## 4. Cargar muchos datos de una vez

Si ya tienes tus datos en un Excel o CSV, no los captures uno por uno:
en **"📤 Cargar datos desde Excel/CSV"**, sube el archivo (debe tener
al menos las columnas `fecha` y `casos_nuevos`) o pega el enlace a un
archivo público (por ejemplo, un export de la OMS o de Datos Abiertos
Colombia).

## 5. Entender el dashboard

- **KPIs arriba**: casos activos, Rt del último día, tasa de
  crecimiento, y la fase estimada del brote (🔴 acelerando, 🟡 en
  meseta, 🟢 desacelerando).
- **Gráfico principal**: casos activos y nuevos por día. Puedes hacer
  zoom, arrastrar la barra de abajo, o usar los botones 7d/30d/90d/todo.
- **Gráfico de activos/recuperados/fallecidos**: elige qué líneas ver
  con el filtro de arriba.
- **Mapa**: si registraste ubicación, aparecen burbujas — más grandes
  donde hay más casos.
- **Proyección**: elige un modelo (más simple con pocos datos, más
  sofisticado con más historial) y cuántos días proyectar. Debajo
  aparece la tabla con nuevos/activos/recuperados/fallecidos
  proyectados.
- **🤖 Explícame estos datos**: si configuraste una clave de IA, un
  botón te da la interpretación en palabras simples.

## 6. Compartir tu brote

- **Colaboradores**: invita a otra persona (que ya tenga cuenta) por
  su correo, para que vea y edite el mismo brote contigo.
- **Enlace público**: genera un enlace que cualquiera puede abrir SIN
  cuenta, para mostrar el estado del brote a donantes o a la comunidad.

## 7. Exportar

- Botón de Excel en la tabla histórica.
- Botón de PDF junto a la proyección (incluye gráfico y tablas).

## 8. Si algo no aparece o da error

Escríbele a quien administra tu cuenta (o revisa que tengas conexión
a internet) — la mayoría de errores se resuelven recargando la página.

---
*Fundación Juan Manuel Collazos — este sistema es gratuito. Si te es
útil, considera donar desde el botón de la barra lateral.*
