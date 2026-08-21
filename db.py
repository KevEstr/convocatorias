"""
Base de datos simple en JSON. Sin dependencias externas.
Para producción reemplazar con PostgreSQL o Supabase.
"""
import json
import os
from datetime import datetime
from pathlib import Path

DB_FILE = Path(__file__).parent / "data" / "convocatorias.json"


def _load() -> list[dict]:
    if not DB_FILE.exists():
        DB_FILE.parent.mkdir(exist_ok=True)
        return []
    try:
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except:
        return []


def _save(data: list[dict]):
    DB_FILE.parent.mkdir(exist_ok=True)
    DB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def guardar_convocatorias(nuevas: list[dict]) -> int:
    """Guarda convocatorias nuevas (evita duplicados por título+entidad)."""
    existentes = _load()
    keys_existentes = {(c.get("titulo", ""), c.get("entidad", "")) for c in existentes}

    agregadas = 0
    for conv in nuevas:
        key = (conv.get("titulo", ""), conv.get("entidad", ""))
        if key not in keys_existentes:
            conv["guardado_en"] = datetime.now().isoformat()
            existentes.append(conv)
            keys_existentes.add(key)
            agregadas += 1

    _save(existentes)
    return agregadas


def obtener_todas(solo_relevantes: bool = False) -> list[dict]:
    data = _load()
    if solo_relevantes:
        data = [c for c in data if c.get("analisis", {}).get("relevante", True)]
    # Ordenar por probabilidad de ganar descendente
    data.sort(
        key=lambda x: x.get("analisis", {}).get("probabilidad_ganar", 0),
        reverse=True
    )
    return data


def obtener_stats() -> dict:
    data = _load()
    relevantes = [c for c in data if c.get("analisis", {}).get("relevante", True)]
    aplicar = [c for c in relevantes if c.get("analisis", {}).get("recomendacion") == "APLICAR"]
    return {
        "total": len(data),
        "relevantes": len(relevantes),
        "aplicar": len(aplicar),
        "ultima_actualizacion": max(
            (c.get("guardado_en", "") for c in data), default="Nunca"
        ),
    }


def limpiar():
    _save([])
