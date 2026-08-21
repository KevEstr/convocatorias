import json
import re
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL, FACULTY_PROFILE, ENGINEERING_KEYWORDS

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# ---------------------------------------------------------------------------
# LLM-based analysis via OpenRouter
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """Analiza esta convocatoria para la Facultad de Ingeniería de la UdeA.

PERFIL DE LA FACULTAD:
{faculty_profile}

CONVOCATORIA:
Título: {titulo}
Entidad: {entidad}
Descripción: {descripcion}
Monto: {monto}
Fecha cierre: {fecha_cierre}

Responde SOLO con JSON válido (sin markdown, sin texto extra):
{{
  "probabilidad_ganar": <número 0-100>,
  "cumplimiento_requisitos": <número 0-100>,
  "areas_requeridas": ["area1", "area2"],
  "razon_scoring": "<explicación en 2-3 oraciones>",
  "recomendacion": "<alta|media|baja|no aplica>"
}}"""


async def analyze_with_llm(conv: dict) -> dict:
    """Analyze a convocatoria using OpenRouter LLM."""
    if not OPENAI_AVAILABLE or not OPENROUTER_API_KEY:
        return keyword_scoring(conv)

    client = AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
    )

    monto_str = f"${conv.get('monto'):,.0f} COP" if conv.get("monto") else "No especificado"

    prompt = ANALYSIS_PROMPT.format(
        faculty_profile=FACULTY_PROFILE.strip(),
        titulo=conv.get("titulo", ""),
        entidad=conv.get("entidad", ""),
        descripcion=(conv.get("descripcion") or "")[:800],
        monto=monto_str,
        fecha_cierre=conv.get("fecha_cierre") or "No especificada",
    )

    try:
        response = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=512,
            extra_headers={
                "HTTP-Referer": "https://udea.edu.co",
                "X-Title": "Monitor Convocatorias FI UdeA",
            },
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)
        # Validate & clamp
        result["probabilidad_ganar"] = max(0, min(100, int(result.get("probabilidad_ganar", 50))))
        result["cumplimiento_requisitos"] = max(0, min(100, int(result.get("cumplimiento_requisitos", 50))))
        if result.get("recomendacion") not in ("alta", "media", "baja", "no aplica"):
            result["recomendacion"] = "media"
        return result

    except json.JSONDecodeError as e:
        print(f"[Analyzer] JSON parse error: {e} — raw: {raw[:200]}")
        return keyword_scoring(conv)
    except Exception as e:
        print(f"[Analyzer] LLM error: {e}")
        return keyword_scoring(conv)


# ---------------------------------------------------------------------------
# Fallback: keyword-based scoring (no API key needed)
# ---------------------------------------------------------------------------

AREA_MAP = {
    "sistemas": "Ingeniería de Sistemas",
    "software": "Desarrollo de Software",
    "civil": "Ingeniería Civil",
    "electrónica": "Ingeniería Electrónica",
    "electronica": "Ingeniería Electrónica",
    "industrial": "Ingeniería Industrial",
    "ambiental": "Ingeniería Ambiental",
    "materiales": "Ingeniería de Materiales",
    "bioingeniería": "Bioingeniería",
    "bioingenieria": "Bioingeniería",
    "telecomunicaciones": "Telecomunicaciones",
    "investigación": "Investigación",
    "investigacion": "Investigación",
    "innovación": "Innovación",
    "innovacion": "Innovación",
    "iot": "IoT / Sensores",
    "datos": "Ciencia de Datos",
    "inteligencia artificial": "Inteligencia Artificial",
    "machine learning": "Machine Learning",
    "energía": "Energía",
    "energia": "Energía",
    "agua": "Recursos Hídricos",
    "infraestructura": "Infraestructura",
    "construcción": "Construcción",
    "construccion": "Construcción",
    "digital": "Transformación Digital",
    "redes": "Redes",
    "ciberseguridad": "Ciberseguridad",
    "robótica": "Robótica",
    "robotica": "Robótica",
    "automatización": "Automatización",
    "automatizacion": "Automatización",
}


def keyword_scoring(conv: dict) -> dict:
    """Simple keyword-based scoring when no LLM is available."""
    text = " ".join([
        str(conv.get("titulo", "")),
        str(conv.get("descripcion", "")),
        str(conv.get("entidad", "")),
    ]).lower()

    # Count keyword matches
    matches = [kw for kw in ENGINEERING_KEYWORDS if kw in text]
    score = min(len(matches) * 8, 90)

    # Detect areas
    areas = []
    seen_areas = set()
    for kw, area in AREA_MAP.items():
        if kw in text and area not in seen_areas:
            areas.append(area)
            seen_areas.add(area)

    # Bonus for university-targeting entities
    university_entities = ["minciencias", "colciencias", "sena", "mintic", "colciencias"]
    if any(ent in text for ent in university_entities):
        score = min(score + 15, 95)

    # Determine recommendation
    if score >= 70:
        recomendacion = "alta"
    elif score >= 40:
        recomendacion = "media"
    elif score >= 15:
        recomendacion = "baja"
    else:
        recomendacion = "no aplica"

    cumplimiento = min(score + 5, 95)

    reasons = []
    if areas:
        reasons.append(f"Áreas identificadas: {', '.join(areas[:3])}.")
    if matches:
        reasons.append(f"Coincidencia con {len(matches)} términos clave de ingeniería.")
    else:
        reasons.append("Poca coincidencia con el perfil de la Facultad de Ingeniería.")
    reasons.append("Scoring generado automáticamente por análisis de palabras clave.")

    return {
        "probabilidad_ganar": score,
        "cumplimiento_requisitos": cumplimiento,
        "areas_requeridas": areas[:5] if areas else ["No identificadas"],
        "razon_scoring": " ".join(reasons),
        "recomendacion": recomendacion,
    }


async def analyze_batch(convocatorias: list[dict]) -> None:
    """Analyze a list of convocatorias and update the database."""
    from database import update_analysis

    if not convocatorias:
        print("[Analyzer] No hay convocatorias pendientes de análisis.")
        return

    print(f"[Analyzer] Analizando {len(convocatorias)} convocatorias...")
    mode = "LLM (OpenRouter)" if (OPENAI_AVAILABLE and OPENROUTER_API_KEY) else "keywords (sin API key)"
    print(f"[Analyzer] Modo: {mode}")

    for i, conv in enumerate(convocatorias, 1):
        print(f"[Analyzer] ({i}/{len(convocatorias)}) {conv.get('titulo', '')[:60]}...")
        result = await analyze_with_llm(conv)
        update_analysis(conv["id"], result)
        print(f"  → recomendación: {result['recomendacion']} | prob: {result['probabilidad_ganar']}%")

    print(f"[Analyzer] Análisis completado.")
