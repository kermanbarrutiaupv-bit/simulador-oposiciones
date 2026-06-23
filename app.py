from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import streamlit as st
from supabase import Client, create_client

APP_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = APP_DIR / "data" / "preguntas_DE25_GR2.json"

THEME_RANGES = [
    (1, 70, "Técnico agua: abastecimiento, presas, bombeos y saneamiento"),
    (71, 95, "Legislación de aguas"),
    (96, 145, "Régimen jurídico y procedimiento administrativo"),
    (146, 160, "Euskera"),
    (161, 185, "Empleo público / EBEP"),
    (186, 205, "Igualdad"),
    (206, 245, "Consorcio de Aguas y ordenanzas"),
    (246, 270, "Prevención de riesgos laborales"),
    (271, 295, "Contratación pública"),
    (296, 315, "Protección de datos"),
    (316, 345, "Ofimática"),
]

ANSWER_OPTIONS = ["En blanco", "A", "B", "C", "D"]
CONFIDENCE_ORDER = ["Alta", "Media", "Baja"]
STATUS_OPTIONS = ["Propuesta no oficial", "Revisada manualmente", "Plantilla oficial", "Dudosa"]

st.set_page_config(
    page_title="Simulador oposiciones DE25 GR2 Online",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)


def infer_theme(question_id: int) -> str:
    for start, end, theme in THEME_RANGES:
        if start <= question_id <= end:
            return theme
    return "Sin clasificar"


def normalize_user(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def safe_compare(a: str, b: str) -> bool:
    return hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest()


def get_configured_users() -> dict[str, str]:
    users: dict[str, str] = {}
    try:
        if "users" in st.secrets:
            users = {normalize_user(k): str(v) for k, v in dict(st.secrets["users"]).items()}
    except Exception:
        users = {}

    # Fallback opcional para despliegues de una sola persona.
    if not users:
        default_user = normalize_user(str(st.secrets.get("APP_USER", "kerman"))) if "APP_USER" in st.secrets else "kerman"
        if "APP_PIN" in st.secrets:
            users[default_user] = str(st.secrets["APP_PIN"])
    return users


def is_admin(user_id: str) -> bool:
    admins = [normalize_user(x) for x in st.secrets.get("ADMIN_USERS", [])] if "ADMIN_USERS" in st.secrets else []
    return user_id in admins


@st.cache_resource(show_spinner=False)
def supabase_client() -> Client:
    missing = [k for k in ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"] if k not in st.secrets]
    if missing:
        raise RuntimeError(f"Faltan secretos de Supabase: {', '.join(missing)}")
    return create_client(str(st.secrets["SUPABASE_URL"]), str(st.secrets["SUPABASE_SERVICE_ROLE_KEY"]))


def to_db_row(q: dict[str, Any]) -> dict[str, Any]:
    opts = q.get("opciones", {}) or {}
    answer = q.get("respuesta_correcta") or ""
    qid = int(q["id"])
    return {
        "id": qid,
        "exam_code": "DE25_GR2",
        "question_text": q.get("pregunta", ""),
        "option_a": opts.get("A", ""),
        "option_b": opts.get("B", ""),
        "option_c": opts.get("C", ""),
        "option_d": opts.get("D", ""),
        "correct_option": answer,
        "correct_text": q.get("texto_respuesta_correcta", opts.get(answer, "")),
        "theme": q.get("tema") or infer_theme(qid),
        "confidence": q.get("confianza", "Media"),
        "status": q.get("estado", "Propuesta no oficial"),
        "notes": q.get("observaciones", ""),
        "source": q.get("fuente", "Batería DE25 GR2"),
    }


def chunked(items: list[dict[str, Any]], size: int = 100) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def seed_questions(client: Client, replace: bool = False) -> int:
    if replace:
        # Borra intentos antes de recargar preguntas para evitar conflictos de FK.
        client.table("quiz_answers").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        client.table("quiz_attempts").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        client.table("questions").delete().neq("id", -1).execute()
    raw = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    rows = [to_db_row(q) for q in raw]
    for part in chunked(rows):
        client.table("questions").upsert(part, on_conflict="id").execute()
    st.cache_data.clear()
    return len(rows)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_questions() -> list[dict[str, Any]]:
    client = supabase_client()
    res = client.table("questions").select("*").order("id").execute()
    rows = res.data or []
    for row in rows:
        row["id"] = int(row["id"])
        row["theme"] = row.get("theme") or infer_theme(row["id"])
    return rows


def question_to_display_row(q: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": q.get("id"),
        "tema": q.get("theme", ""),
        "pregunta": q.get("question_text", ""),
        "A": q.get("option_a", ""),
        "B": q.get("option_b", ""),
        "C": q.get("option_c", ""),
        "D": q.get("option_d", ""),
        "respuesta_correcta": q.get("correct_option", ""),
        "texto_respuesta_correcta": q.get("correct_text", ""),
        "confianza": q.get("confidence", ""),
        "estado": q.get("status", ""),
        "observaciones": q.get("notes", ""),
        "fuente": q.get("source", ""),
    }


def questions_df(questions: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([question_to_display_row(q) for q in questions])


def fetch_all_answers(user_id: str) -> list[dict[str, Any]]:
    client = supabase_client()
    rows: list[dict[str, Any]] = []
    start = 0
    page_size = 1000
    while True:
        res = (
            client.table("quiz_answers")
            .select("question_id, selected_option, correct_option, is_correct, is_blank, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def build_progress_df(questions: list[dict[str, Any]], answers: list[dict[str, Any]]) -> pd.DataFrame:
    stats: dict[int, dict[str, Any]] = {}
    for a in answers:
        qid = int(a.get("question_id"))
        item = stats.setdefault(qid, {"seen": 0, "correct": 0, "wrong": 0, "blank": 0, "last_answer": "", "last_date": "", "last_correct": False})
        item["seen"] += 1
        if a.get("is_blank"):
            item["blank"] += 1
        elif a.get("is_correct"):
            item["correct"] += 1
        else:
            item["wrong"] += 1
        item["last_answer"] = a.get("selected_option") or "En blanco"
        item["last_date"] = a.get("created_at") or ""
        item["last_correct"] = bool(a.get("is_correct"))

    records = []
    for q in questions:
        qid = int(q["id"])
        p = stats.get(qid, {})
        seen = int(p.get("seen", 0))
        correct = int(p.get("correct", 0))
        wrong = int(p.get("wrong", 0))
        blank = int(p.get("blank", 0))
        records.append(
            {
                "id": qid,
                "tema": q.get("theme", infer_theme(qid)),
                "pregunta": q.get("question_text", ""),
                "respuesta_correcta": q.get("correct_option", ""),
                "texto_respuesta_correcta": q.get("correct_text", ""),
                "confianza": q.get("confidence", ""),
                "estado": q.get("status", ""),
                "vistas": seen,
                "aciertos": correct,
                "fallos": wrong,
                "blancos": blank,
                "% acierto": round(correct / seen, 4) if seen else None,
                "última respuesta": p.get("last_answer", ""),
                "última fecha": p.get("last_date", ""),
            }
        )
    return pd.DataFrame(records)


def calculate_score(results: list[dict[str, Any]], penalty_mode: str, custom_penalty: float) -> dict[str, Any]:
    total = len(results)
    correct = sum(1 for r in results if r["is_correct"])
    blank = sum(1 for r in results if r["is_blank"])
    wrong = total - correct - blank
    if penalty_mode == "Sin penalización":
        penalty = 0.0
    elif penalty_mode == "Restar 1/3 por fallo":
        penalty = 1 / 3
    else:
        penalty = float(custom_penalty)
    raw_score = round((correct / total) * 10, 2) if total else 0.0
    net_points = max(0.0, correct - wrong * penalty)
    net_score = round((net_points / total) * 10, 2) if total else 0.0
    return {
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "blank": blank,
        "penalty": penalty,
        "raw_score": raw_score,
        "net_score": net_score,
    }


def save_attempt(user_id: str, results: list[dict[str, Any]], score: dict[str, Any]) -> str:
    client = supabase_client()
    themes = sorted(set(str(r.get("theme", "")) for r in results if r.get("theme")))
    question_ids = [int(r["id"]) for r in results]
    attempt_payload = {
        "user_id": user_id,
        "num_questions": score["total"],
        "correct": score["correct"],
        "wrong": score["wrong"],
        "blank": score["blank"],
        "penalty": score["penalty"],
        "raw_score": score["raw_score"],
        "net_score": score["net_score"],
        "themes": themes,
        "question_ids": question_ids,
    }
    attempt = client.table("quiz_attempts").insert(attempt_payload).execute().data[0]
    attempt_id = attempt["id"]
    answer_rows = []
    for r in results:
        answer_rows.append(
            {
                "attempt_id": attempt_id,
                "user_id": user_id,
                "question_id": int(r["id"]),
                "selected_option": None if r["is_blank"] else r["answer"],
                "correct_option": r["correct_answer"],
                "is_correct": bool(r["is_correct"]),
                "is_blank": bool(r["is_blank"]),
            }
        )
    for part in chunked(answer_rows, 100):
        client.table("quiz_answers").insert(part).execute()
    st.cache_data.clear()
    return attempt_id


def fetch_attempts(user_id: str, limit: int = 100) -> pd.DataFrame:
    client = supabase_client()
    res = (
        client.table("quiz_attempts")
        .select("id, created_at, num_questions, correct, wrong, blank, penalty, raw_score, net_score, themes")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(res.data or [])


def delete_user_progress(user_id: str) -> None:
    client = supabase_client()
    client.table("quiz_answers").delete().eq("user_id", user_id).execute()
    client.table("quiz_attempts").delete().eq("user_id", user_id).execute()
    st.cache_data.clear()


def make_excel_bytes(df_main: pd.DataFrame, df_progress: pd.DataFrame | None = None) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_main.to_excel(writer, sheet_name="Resumen_respuestas", index=False)
        if df_progress is not None:
            df_progress.to_excel(writer, sheet_name="Progreso", index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                header = str(col[0].value or "")
                width = min(max(len(header) + 2, 12), 55)
                if header.lower() in {"pregunta", "texto_respuesta_correcta", "observaciones"}:
                    width = 55
                ws.column_dimensions[col[0].column_letter].width = width
                for cell in col:
                    cell.alignment = cell.alignment.copy(wrap_text=True, vertical="top")
    return output.getvalue()


def render_setup_error(exc: Exception) -> None:
    st.error("La app no está conectada todavía a Supabase.")
    st.write("Revisa que has creado las tablas con `sql/schema_supabase.sql` y que has añadido `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` en los Secrets de Streamlit.")
    with st.expander("Detalle técnico"):
        st.code(str(exc))


def require_login() -> str | None:
    if st.session_state.get("user_id"):
        return str(st.session_state["user_id"])

    st.title("📝 Simulador oposiciones DE25 GR2")
    st.caption("Versión online con Supabase: simulacros, fallos y estadísticas guardadas por usuario.")

    configured_users = get_configured_users()
    if not configured_users:
        st.warning("No hay usuarios configurados. Añade una sección [users] en Streamlit Secrets.")
        st.code('[users]\nkerman = "1234"')
        return None

    with st.form("login"):
        username = st.text_input("Usuario")
        pin = st.text_input("PIN", type="password")
        submitted = st.form_submit_button("Entrar", type="primary")
    if submitted:
        user_id = normalize_user(username)
        expected_pin = configured_users.get(user_id)
        if expected_pin and safe_compare(pin, expected_pin):
            st.session_state["user_id"] = user_id
            st.rerun()
        else:
            st.error("Usuario o PIN incorrecto.")
    return None


def sidebar_filters(qdf: pd.DataFrame) -> tuple[list[str], list[str], list[str]]:
    themes = sorted(qdf["tema"].dropna().unique().tolist()) if not qdf.empty else []
    states = sorted(qdf["estado"].dropna().unique().tolist()) if not qdf.empty else STATUS_OPTIONS
    selected_themes = st.sidebar.multiselect("Temas", options=themes, default=themes)
    selected_conf = st.sidebar.multiselect("Confianza", options=CONFIDENCE_ORDER, default=CONFIDENCE_ORDER)
    selected_states = st.sidebar.multiselect("Estado", options=states, default=states)
    return selected_themes, selected_conf, selected_states


user_id = require_login()
if not user_id:
    st.stop()

try:
    client = supabase_client()
except Exception as exc:
    render_setup_error(exc)
    st.stop()

st.sidebar.title("Simulador DE25 GR2")
st.sidebar.caption(f"Usuario: **{user_id}**")
if st.sidebar.button("Cerrar sesión"):
    st.session_state.clear()
    st.rerun()

try:
    questions = fetch_questions()
except Exception as exc:
    render_setup_error(exc)
    st.stop()

if not questions:
    st.title("Inicializar banco de preguntas")
    st.warning("La tabla `questions` existe, pero todavía no tiene preguntas.")
    if st.button("Cargar las 345 preguntas en Supabase", type="primary"):
        try:
            count = seed_questions(client)
            st.success(f"Preguntas cargadas: {count}. Recarga la app si no aparecen automáticamente.")
            st.rerun()
        except Exception as exc:
            st.error("No se pudieron cargar las preguntas.")
            st.code(str(exc))
    st.stop()

q_by_id = {int(q["id"]): q for q in questions}
qdf = questions_df(questions)
answers = fetch_all_answers(user_id)
progress = build_progress_df(questions, answers)

page = st.sidebar.radio(
    "Apartado",
    [
        "Simulacro",
        "Repasar fallos",
        "Resumen de respuestas",
        "Banco / editar respuestas",
        "Estadísticas",
        "Admin / datos",
    ],
)

st.title("📝 Simulador oposiciones DE25 GR2 Online")
st.caption("Batería de 345 preguntas con respuestas propuestas. Las respuestas no son plantilla oficial salvo que tú las marques como tal.")

if page == "Simulacro":
    selected_themes, selected_conf, selected_states = sidebar_filters(qdf)
    st.header("Generar simulacro")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        num_questions = st.number_input("Número de preguntas", min_value=1, max_value=len(questions), value=min(50, len(questions)), step=1)
    with c2:
        mode = st.selectbox("Modo", ["Todas", "Solo falladas", "Solo no vistas", "Falladas + no vistas"])
    with c3:
        penalty_mode = st.selectbox("Penalización", ["Sin penalización", "Restar 1/3 por fallo", "Personalizada"])
    with c4:
        custom_penalty = st.number_input("Penalización personalizada", min_value=0.0, max_value=2.0, value=0.33, step=0.05, disabled=(penalty_mode != "Personalizada"))

    candidates = [
        q for q in questions
        if q.get("theme") in selected_themes
        and q.get("confidence") in selected_conf
        and q.get("status") in selected_states
    ]
    p_lookup = progress.set_index("id").to_dict(orient="index")
    if mode == "Solo falladas":
        candidates = [q for q in candidates if int(p_lookup.get(int(q["id"]), {}).get("fallos", 0)) > 0]
    elif mode == "Solo no vistas":
        candidates = [q for q in candidates if int(p_lookup.get(int(q["id"]), {}).get("vistas", 0)) == 0]
    elif mode == "Falladas + no vistas":
        candidates = [q for q in candidates if int(p_lookup.get(int(q["id"]), {}).get("fallos", 0)) > 0 or int(p_lookup.get(int(q["id"]), {}).get("vistas", 0)) == 0]

    st.info(f"Preguntas disponibles con estos filtros: {len(candidates)}")
    if st.button("🎲 Generar simulacro", type="primary"):
        if not candidates:
            st.error("No hay preguntas con esos filtros.")
        else:
            sample_size = min(int(num_questions), len(candidates))
            st.session_state["quiz_ids"] = [int(q["id"]) for q in random.sample(candidates, sample_size)]
            st.session_state["quiz_corrected"] = False
            st.session_state.pop("last_results", None)
            st.session_state.pop("last_score", None)
            for qid in st.session_state["quiz_ids"]:
                st.session_state.pop(f"answer_{qid}", None)
            st.rerun()

    quiz_ids = st.session_state.get("quiz_ids", [])
    if quiz_ids:
        quiz_questions = [q_by_id[qid] for qid in quiz_ids if qid in q_by_id]
        st.subheader(f"Simulacro activo: {len(quiz_questions)} preguntas")
        with st.form("quiz_form"):
            for idx, q in enumerate(quiz_questions, start=1):
                st.markdown(f"### {idx}. Pregunta {q['id']}")
                st.write(q.get("question_text", ""))
                labels = ["En blanco"] + [
                    f"{letter}) {q.get(f'option_{letter.lower()}', '')}" for letter in ["A", "B", "C", "D"]
                ]
                st.radio("Tu respuesta", labels, key=f"answer_{q['id']}", label_visibility="collapsed")
                st.divider()
            submitted = st.form_submit_button("✅ Corregir y guardar", type="primary")

        if submitted:
            results = []
            for q in quiz_questions:
                raw = st.session_state.get(f"answer_{q['id']}", "En blanco")
                selected = "En blanco" if raw == "En blanco" else raw.split(")", 1)[0]
                correct = q.get("correct_option", "")
                is_blank = selected == "En blanco"
                results.append(
                    {
                        "id": int(q["id"]),
                        "theme": q.get("theme", ""),
                        "question": q.get("question_text", ""),
                        "answer": selected,
                        "correct_answer": correct,
                        "correct_text": q.get("correct_text", ""),
                        "is_blank": is_blank,
                        "is_correct": (not is_blank) and selected == correct,
                        "confidence": q.get("confidence", ""),
                    }
                )
            score = calculate_score(results, penalty_mode, float(custom_penalty))
            try:
                attempt_id = save_attempt(user_id, results, score)
                st.session_state["last_attempt_id"] = attempt_id
                st.session_state["last_results"] = results
                st.session_state["last_score"] = score
                st.session_state["quiz_corrected"] = True
                st.rerun()
            except Exception as exc:
                st.error("No se pudo guardar el simulacro en Supabase.")
                st.code(str(exc))

    if st.session_state.get("quiz_corrected"):
        score = st.session_state.get("last_score", {})
        results = st.session_state.get("last_results", [])
        st.success("Simulacro corregido y guardado en Supabase.")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Aciertos", score.get("correct", 0))
        m2.metric("Fallos", score.get("wrong", 0))
        m3.metric("Blancos", score.get("blank", 0))
        m4.metric("Nota bruta / 10", score.get("raw_score", 0))
        m5.metric("Nota neta / 10", score.get("net_score", 0))

        wrong_or_blank = [r for r in results if not r["is_correct"]]
        if wrong_or_blank:
            st.subheader("Corrección de fallos y blancos")
            for r in wrong_or_blank:
                q = q_by_id[int(r["id"])]
                st.markdown(f"**Pregunta {r['id']} — {r['theme']}**")
                st.write(q.get("question_text", ""))
                st.write(f"Tu respuesta: **{r['answer']}**")
                st.success(f"Correcta: **{r['correct_answer']}** — {r['correct_text']}")
                st.caption(f"Confianza: {r['confidence']}")
                st.divider()
        else:
            st.balloons()
            st.write("Perfecto: no has fallado ninguna.")

elif page == "Repasar fallos":
    selected_themes, selected_conf, selected_states = sidebar_filters(qdf)
    st.header("Repasar fallos")
    failed_df = progress[
        (progress["fallos"] > 0)
        & progress["tema"].isin(selected_themes)
        & progress["confianza"].isin(selected_conf)
        & progress["estado"].isin(selected_states)
    ].sort_values(["fallos", "vistas"], ascending=[False, False])
    st.write(f"Preguntas con al menos un fallo: **{len(failed_df)}**")
    if failed_df.empty:
        st.info("Todavía no tienes fallos guardados con estos filtros.")
    else:
        limit = st.slider("Cuántas mostrar", 1, min(100, len(failed_df)), min(20, len(failed_df)))
        for _, row in failed_df.head(limit).iterrows():
            q = q_by_id[int(row["id"])]
            st.markdown(f"### Pregunta {int(row['id'])} — {row['tema']}")
            st.caption(f"Fallos: {row['fallos']} · Aciertos: {row['aciertos']} · Vista: {row['vistas']} veces")
            st.write(q.get("question_text", ""))
            for letter in ["A", "B", "C", "D"]:
                text = q.get(f"option_{letter.lower()}", "")
                if letter == q.get("correct_option"):
                    st.success(f"{letter}) {text}")
                else:
                    st.write(f"{letter}) {text}")
            if q.get("notes"):
                st.caption(q["notes"])
            st.divider()

elif page == "Resumen de respuestas":
    selected_themes, selected_conf, selected_states = sidebar_filters(qdf)
    st.header("Resumen de todas las respuestas buenas")
    df = qdf[qdf["tema"].isin(selected_themes) & qdf["confianza"].isin(selected_conf) & qdf["estado"].isin(selected_states)].copy()
    search = st.text_input("Buscar por palabra")
    if search:
        mask = df.apply(lambda row: search.lower() in " ".join(map(str, row.values)).lower(), axis=1)
        df = df[mask]
    st.write(f"Preguntas mostradas: **{len(df)}**")
    st.dataframe(
        df[["id", "tema", "pregunta", "respuesta_correcta", "texto_respuesta_correcta", "confianza", "estado", "observaciones"]],
        use_container_width=True,
        hide_index=True,
    )
    excel_bytes = make_excel_bytes(df, progress)
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Descargar resumen en Excel",
            data=excel_bytes,
            file_name="resumen_respuestas_DE25_GR2_online.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col2:
        st.download_button(
            "⬇️ Descargar resumen en CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="resumen_respuestas_DE25_GR2_online.csv",
            mime="text/csv",
        )

elif page == "Banco / editar respuestas":
    st.header("Banco de preguntas y edición manual")
    st.warning("Modifica una respuesta solo si la has contrastado con normativa, plantilla oficial o criterio propio. Se guarda en Supabase para todos los usuarios de la app.")
    ids = sorted([int(q["id"]) for q in questions])
    selected_id = st.number_input("ID de pregunta", min_value=min(ids), max_value=max(ids), value=min(ids), step=1)
    q = q_by_id.get(int(selected_id))
    if q:
        st.subheader(f"Pregunta {q['id']}")
        st.write(q.get("question_text", ""))
        for letter in ["A", "B", "C", "D"]:
            st.write(f"**{letter})** {q.get(f'option_{letter.lower()}', '')}")
        with st.form("edit_question"):
            answer_options = ["A", "B", "C", "D"]
            current_answer = q.get("correct_option") if q.get("correct_option") in answer_options else "A"
            answer = st.selectbox("Respuesta correcta", answer_options, index=answer_options.index(current_answer))
            current_conf = q.get("confidence", "Media") if q.get("confidence") in CONFIDENCE_ORDER else "Media"
            confidence = st.selectbox("Confianza", CONFIDENCE_ORDER, index=CONFIDENCE_ORDER.index(current_conf))
            current_status = q.get("status", "Propuesta no oficial") if q.get("status") in STATUS_OPTIONS else "Propuesta no oficial"
            status = st.selectbox("Estado", STATUS_OPTIONS, index=STATUS_OPTIONS.index(current_status))
            theme = st.text_input("Tema", value=q.get("theme", infer_theme(int(q["id"]))))
            notes = st.text_area("Observaciones", value=q.get("notes", ""), height=100)
            save = st.form_submit_button("💾 Guardar cambios")
        if save:
            old_answer = q.get("correct_option")
            payload = {
                "correct_option": answer,
                "correct_text": q.get(f"option_{answer.lower()}", ""),
                "confidence": confidence,
                "status": status,
                "theme": theme,
                "notes": notes,
            }
            try:
                client.table("questions").update(payload).eq("id", int(q["id"])).execute()
                client.table("question_edits").insert(
                    {
                        "user_id": user_id,
                        "question_id": int(q["id"]),
                        "old_correct_option": old_answer,
                        "new_correct_option": answer,
                        "old_status": q.get("status"),
                        "new_status": status,
                        "old_confidence": q.get("confidence"),
                        "new_confidence": confidence,
                        "notes": notes,
                    }
                ).execute()
                st.cache_data.clear()
                st.success("Pregunta actualizada en Supabase.")
                st.rerun()
            except Exception as exc:
                st.error("No se pudo actualizar la pregunta.")
                st.code(str(exc))
    st.subheader("Vista rápida del banco")
    st.dataframe(qdf[["id", "tema", "pregunta", "respuesta_correcta", "texto_respuesta_correcta", "confianza", "estado"]], use_container_width=True, hide_index=True)

elif page == "Estadísticas":
    st.header("Estadísticas")
    total_seen = int(progress["vistas"].sum())
    total_correct = int(progress["aciertos"].sum())
    total_wrong = int(progress["fallos"].sum())
    total_blank = int(progress["blancos"].sum())
    unique_seen = int((progress["vistas"] > 0).sum())
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preguntas vistas", unique_seen)
    c2.metric("Respuestas totales", total_seen)
    c3.metric("Aciertos", total_correct)
    c4.metric("Fallos", total_wrong)
    c5.metric("Blancos", total_blank)

    if total_seen:
        by_theme = progress.groupby("tema", as_index=False).agg(
            vistas=("vistas", "sum"),
            aciertos=("aciertos", "sum"),
            fallos=("fallos", "sum"),
            blancos=("blancos", "sum"),
        )
        by_theme["% acierto"] = (by_theme["aciertos"] / by_theme["vistas"].replace(0, pd.NA)).round(4)
        st.subheader("Progreso por tema")
        st.dataframe(by_theme, use_container_width=True, hide_index=True)
        st.bar_chart(by_theme.set_index("tema")[["aciertos", "fallos", "blancos"]])

        st.subheader("Preguntas más falladas")
        most_failed = progress.sort_values(["fallos", "vistas"], ascending=[False, False]).head(30)
        st.dataframe(most_failed[["id", "tema", "pregunta", "fallos", "aciertos", "blancos", "texto_respuesta_correcta"]], use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay simulacros corregidos.")

    attempts_df = fetch_attempts(user_id)
    if not attempts_df.empty:
        st.subheader("Historial de simulacros")
        st.dataframe(attempts_df, use_container_width=True, hide_index=True)
    else:
        st.info("Todavía no existe historial de simulacros.")

elif page == "Admin / datos":
    st.header("Admin / datos")
    st.subheader("Estado")
    c1, c2, c3 = st.columns(3)
    c1.metric("Preguntas en Supabase", len(questions))
    c2.metric("Tus respuestas guardadas", len(answers))
    c3.metric("Usuario admin", "Sí" if is_admin(user_id) else "No")

    st.subheader("Exportar")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button("⬇️ Banco JSON", data=json.dumps(questions, ensure_ascii=False, indent=2).encode("utf-8"), file_name="preguntas_supabase_DE25_GR2.json", mime="application/json")
    with col2:
        st.download_button("⬇️ Banco CSV", data=qdf.to_csv(index=False).encode("utf-8-sig"), file_name="preguntas_supabase_DE25_GR2.csv", mime="text/csv")
    with col3:
        st.download_button("⬇️ Progreso CSV", data=progress.to_csv(index=False).encode("utf-8-sig"), file_name=f"progreso_{user_id}_DE25_GR2.csv", mime="text/csv")

    st.subheader("Reiniciar mi progreso")
    st.write("Borra tus simulacros, respuestas, fallos y estadísticas. No borra el banco de preguntas.")
    confirm = st.checkbox("Confirmo que quiero borrar mi progreso")
    if st.button("🧹 Borrar mi progreso", disabled=not confirm):
        delete_user_progress(user_id)
        st.success("Progreso borrado.")
        st.rerun()

    st.subheader("Inicializar o actualizar banco de preguntas")
    st.write("Carga el JSON incluido en la app a Supabase. Usa 'actualizar' si quieres restaurar el banco base.")
    if st.button("Actualizar banco desde JSON incluido"):
        try:
            count = seed_questions(client, replace=False)
            st.success(f"Banco actualizado: {count} preguntas.")
            st.rerun()
        except Exception as exc:
            st.error("No se pudo actualizar el banco.")
            st.code(str(exc))

    if is_admin(user_id):
        st.subheader("Zona peligrosa")
        st.warning("Esto borra preguntas y progreso de todos los usuarios antes de recargar el banco base.")
        confirm_replace = st.checkbox("Confirmo que quiero borrar todo y recargar el banco base")
        if st.button("⚠️ Reemplazar banco completo", disabled=not confirm_replace):
            try:
                count = seed_questions(client, replace=True)
                st.success(f"Banco reemplazado: {count} preguntas.")
                st.rerun()
            except Exception as exc:
                st.error("No se pudo reemplazar el banco.")
                st.code(str(exc))
    else:
        st.info("La opción de reemplazar todo queda reservada a usuarios incluidos en ADMIN_USERS.")

st.sidebar.divider()
st.sidebar.caption("Consejo: marca como 'Plantilla oficial' las respuestas cuando consigas la plantilla del tribunal.")
