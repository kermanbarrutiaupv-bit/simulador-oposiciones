# Simulador Oposiciones DE25 GR2 - Nivel 3 online

App online para hacer simulacros con la batería **DE25 GR2**:

- 345 preguntas cargadas desde el PDF original.
- Acceso por usuario + PIN mediante Streamlit Secrets.
- Base de datos Supabase/PostgreSQL.
- Historial de simulacros.
- Fallos guardados por pregunta.
- Simulacros aleatorios, solo falladas, solo no vistas o falladas + no vistas.
- Penalización sin resta, resta 1/3 o personalizada.
- Resumen descargable en Excel/CSV.
- Edición de respuestas y estado: propuesta, revisada, plantilla oficial o dudosa.

> Importante: las respuestas incluidas son una propuesta no oficial. Cuando consigas plantilla oficial, puedes editar la respuesta y marcarla como `Plantilla oficial`.

---

## 1. Crear proyecto en Supabase

1. Entra en Supabase.
2. Crea un proyecto nuevo.
3. Abre **SQL Editor**.
4. Crea una consulta nueva.
5. Copia y ejecuta el contenido de:

```text
sql/schema_supabase.sql
```

Esto crea las tablas:

- `questions`
- `quiz_attempts`
- `quiz_answers`
- `question_edits`

---

## 2. Conseguir las claves de Supabase

En Supabase:

1. Ve a **Project Settings**.
2. Entra en **API**.
3. Copia:
   - `Project URL`
   - `service_role key`

La `service_role key` es sensible. No la subas nunca a GitHub.

---

## 3. Subir la app a GitHub

Sube estos archivos a un repositorio de GitHub:

```text
app.py
requirements.txt
README.md
data/preguntas_DE25_GR2.json
sql/schema_supabase.sql
.streamlit/secrets.example.toml
```

No subas un archivo real llamado `.streamlit/secrets.toml`.

---

## 4. Desplegar en Streamlit Community Cloud

1. Entra en Streamlit Community Cloud.
2. Crea una app nueva.
3. Elige tu repositorio de GitHub.
4. Archivo principal: `app.py`.
5. Antes o después de desplegar, entra en **Settings > Secrets**.
6. Pega este contenido, cambiando los valores:

```toml
SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "TU_SERVICE_ROLE_KEY"
APP_SECRET = "cambia-esta-frase-larga"
ADMIN_USERS = ["kerman"]

[users]
kerman = "1234"
```

Puedes añadir más usuarios:

```toml
[users]
kerman = "1234"
otro_usuario = "5678"
```

---

## 5. Primer arranque

Al abrir la app online:

1. Inicia sesión con el usuario y PIN configurado.
2. Si la tabla `questions` está vacía, la app te mostrará un botón para cargar las 345 preguntas.
3. Pulsa **Cargar las 345 preguntas en Supabase**.
4. Ya puedes hacer simulacros.

También puedes entrar en **Admin / datos** y pulsar **Actualizar banco desde JSON incluido**.

---

## 6. Estructura de la base de datos

### `questions`

Banco de preguntas y respuestas correctas.

### `quiz_attempts`

Cada simulacro corregido.

### `quiz_answers`

Cada respuesta individual del usuario.

### `question_edits`

Historial de cambios cuando editas una respuesta correcta, confianza o estado.

---

## 7. Seguridad práctica

Esta versión está pensada para uso personal o de pocas personas conocidas.

- No pongas `SUPABASE_SERVICE_ROLE_KEY` en GitHub.
- Guárdala solo en Streamlit Secrets.
- Usa un PIN que no sea obvio.
- Si quieres abrir la app a mucha gente, lo correcto sería pasar a Supabase Auth con usuarios reales y políticas RLS por usuario.

---

## 8. Uso local opcional

Aunque está pensada para online, también funciona localmente si tienes Python:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Necesitarías crear `.streamlit/secrets.toml` copiando el contenido de `.streamlit/secrets.example.toml` y rellenando tus claves.

---

## 9. Cargar preguntas con script opcional

Si algún día puedes ejecutar Python, también puedes cargar preguntas así:

```bash
export SUPABASE_URL="https://TU-PROYECTO.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="TU_SERVICE_ROLE_KEY"
python tools/seed_supabase.py
```

No es necesario para el despliegue normal, porque la app trae un botón de carga.
