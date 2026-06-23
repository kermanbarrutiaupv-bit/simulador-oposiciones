"""Carga las preguntas del JSON en Supabase desde tu ordenador o desde un entorno online.

Uso:
    export SUPABASE_URL="https://...supabase.co"
    export SUPABASE_SERVICE_ROLE_KEY="..."
    python tools/seed_supabase.py

También puedes usar el botón de la sección Admin de la app, sin ejecutar este script.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = ROOT / "data" / "preguntas_DE25_GR2.json"

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


def infer_theme(question_id: int) -> str:
    for start, end, theme in THEME_RANGES:
        if start <= question_id <= end:
            return theme
    return "Sin clasificar"


def to_db_row(q: dict) -> dict:
    opts = q.get("opciones", {})
    answer = q.get("respuesta_correcta") or ""
    return {
        "id": int(q["id"]),
        "exam_code": "DE25_GR2",
        "question_text": q.get("pregunta", ""),
        "option_a": opts.get("A", ""),
        "option_b": opts.get("B", ""),
        "option_c": opts.get("C", ""),
        "option_d": opts.get("D", ""),
        "correct_option": answer,
        "correct_text": q.get("texto_respuesta_correcta", opts.get(answer, "")),
        "theme": q.get("tema") or infer_theme(int(q["id"])),
        "confidence": q.get("confianza", "Media"),
        "status": q.get("estado", "Propuesta no oficial"),
        "notes": q.get("observaciones", ""),
        "source": q.get("fuente", "Batería DE25 GR2"),
    }


def chunks(items: list[dict], size: int = 100):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def main() -> None:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(url, key)
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    rows = [to_db_row(q) for q in data]
    for part in chunks(rows):
        client.table("questions").upsert(part, on_conflict="id").execute()
    print(f"Cargadas/actualizadas {len(rows)} preguntas.")


if __name__ == "__main__":
    main()
