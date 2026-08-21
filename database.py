import sqlite3
import json
from datetime import datetime
from config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS convocatorias (
            id TEXT PRIMARY KEY,
            titulo TEXT,
            entidad TEXT,
            fuente TEXT,
            url TEXT,
            monto REAL,
            fecha_cierre TEXT,
            fecha_publicacion TEXT,
            descripcion TEXT,
            estado TEXT,
            analizado INTEGER DEFAULT 0,
            probabilidad_ganar INTEGER,
            cumplimiento_requisitos INTEGER,
            areas_requeridas TEXT,
            razon_scoring TEXT,
            recomendacion TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def upsert_convocatoria(data: dict):
    conn = get_connection()
    now = datetime.now().isoformat()

    # Check if exists
    existing = conn.execute(
        "SELECT id FROM convocatorias WHERE id = ?", (data["id"],)
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE convocatorias SET
                titulo=?, entidad=?, fuente=?, url=?, monto=?,
                fecha_cierre=?, fecha_publicacion=?, descripcion=?,
                estado=?, updated_at=?
            WHERE id=?
        """, (
            data.get("titulo"), data.get("entidad"), data.get("fuente"),
            data.get("url"), data.get("monto"), data.get("fecha_cierre"),
            data.get("fecha_publicacion"), data.get("descripcion"),
            data.get("estado", "abierta"), now, data["id"]
        ))
    else:
        conn.execute("""
            INSERT INTO convocatorias
                (id, titulo, entidad, fuente, url, monto, fecha_cierre,
                 fecha_publicacion, descripcion, estado, analizado,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            data["id"], data.get("titulo"), data.get("entidad"),
            data.get("fuente"), data.get("url"), data.get("monto"),
            data.get("fecha_cierre"), data.get("fecha_publicacion"),
            data.get("descripcion"), data.get("estado", "abierta"),
            now, now
        ))
    conn.commit()
    conn.close()


def update_analysis(conv_id: str, analysis: dict):
    conn = get_connection()
    now = datetime.now().isoformat()
    areas = json.dumps(analysis.get("areas_requeridas", []), ensure_ascii=False)
    conn.execute("""
        UPDATE convocatorias SET
            analizado=1,
            probabilidad_ganar=?,
            cumplimiento_requisitos=?,
            areas_requeridas=?,
            razon_scoring=?,
            recomendacion=?,
            updated_at=?
        WHERE id=?
    """, (
        analysis.get("probabilidad_ganar"),
        analysis.get("cumplimiento_requisitos"),
        areas,
        analysis.get("razon_scoring"),
        analysis.get("recomendacion"),
        now,
        conv_id
    ))
    conn.commit()
    conn.close()


def get_unanalyzed() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM convocatorias WHERE analizado=0"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM convocatorias ORDER BY fecha_publicacion DESC"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        item = dict(r)
        # Parse JSON fields
        try:
            item["areas_requeridas"] = json.loads(item["areas_requeridas"] or "[]")
        except Exception:
            item["areas_requeridas"] = []
        result.append(item)
    return result


def get_stats() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM convocatorias").fetchone()[0]
    abiertas = conn.execute(
        "SELECT COUNT(*) FROM convocatorias WHERE estado='abierta'"
    ).fetchone()[0]
    alta_prioridad = conn.execute(
        "SELECT COUNT(*) FROM convocatorias WHERE recomendacion='alta'"
    ).fetchone()[0]
    monto_total = conn.execute(
        "SELECT SUM(monto) FROM convocatorias WHERE monto IS NOT NULL"
    ).fetchone()[0] or 0
    conn.close()
    return {
        "total": total,
        "abiertas": abiertas,
        "alta_prioridad": alta_prioridad,
        "monto_total": monto_total,
    }
