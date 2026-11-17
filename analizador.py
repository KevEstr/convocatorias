"""
Analiza cada convocatoria con IA y calcula:
- Probabilidad de que la Facultad de Ingeniería gane
- % cumplimiento de requisitos
- Áreas relevantes
- Resumen ejecutivo

El perfil institucional, los criterios y los umbrales se leen desde
data/ajustes.json y pueden editarse desde el frontend.
"""
import json
import os
import re

from openai import OpenAI
from dotenv import load_dotenv

from ajustes import cargar_ajustes, texto_criterios

load_dotenv()


def get_client():
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY no configurada en .env")
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={"HTTP-Referer": "convocatorias-udea"},
    )


def analizar_convocatoria(conv: dict, ajustes: dict | None = None) -> dict:
    """
    Analiza una convocatoria y retorna el análisis estructurado.
    """
    ajustes = ajustes or cargar_ajustes()

    try:
        client = get_client()
        perfil = ajustes["perfil"]
        criterios = texto_criterios(ajustes["criterios"])
        instrucciones = ajustes.get("instrucciones") or "Ninguna."
        descripcion = (conv.get("descripcion") or "").strip()

        prompt = f"""Analiza esta convocatoria y evalúa si la Facultad de Ingeniería de la Universidad de Antioquia debería aplicar.

PERFIL DE LA FACULTAD:
{perfil}

CRITERIOS Y PESOS PARA LA ESTIMACIÓN:
{criterios}
Usa estos pesos como referencia al estimar probabilidad_ganar y cumplimiento_requisitos.

INSTRUCCIONES ADICIONALES:
{instrucciones}

CONVOCATORIA:
Título: {conv.get('titulo', '')}
Entidad: {conv.get('entidad', '')}
Fuente: {conv.get('fuente', '')}
Monto: ${conv.get('monto', 0):,} COP
Modalidad: {conv.get('modalidad', '')}
Estado: {conv.get('estado', '')}
Fecha cierre: {conv.get('fecha_cierre', '')}
Departamento: {conv.get('departamento', '')}
Descripción: {descripcion[:1000] or 'No registrada'}

Responde ÚNICAMENTE con este JSON exacto (sin markdown, sin explicaciones):
{{
  "relevante": true/false,
  "probabilidad_ganar": 0-100,
  "cumplimiento_requisitos": 0-100,
  "areas_relevantes": ["área1", "área2"],
  "resumen": "2-3 oraciones sobre qué es y por qué aplica o no",
  "fortalezas": ["fortaleza1", "fortaleza2"],
  "riesgos": ["riesgo1"],
  "recomendacion": "APLICAR" | "EVALUAR" | "NO_APLICAR"
}}"""

        response = client.chat.completions.create(
            model=ajustes["modelo"],
            messages=[{"role": "user", "content": prompt}],
            temperature=float(ajustes["temperatura"]),
            max_tokens=500,
        )

        text = response.choices[0].message.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        analisis = json.loads(text)
        return _aplicar_umbrales(analisis, ajustes["umbrales"])

    except Exception as e:
        raise RuntimeError(f"No se pudo analizar la convocatoria con IA: {e}") from e


def probar_conexion(ajustes: dict | None = None) -> str:
    """Realiza una llamada mínima para validar clave, modelo y conectividad."""
    ajustes = ajustes or cargar_ajustes()
    client = get_client()
    response = client.chat.completions.create(
        model=ajustes["modelo"],
        messages=[{"role": "user", "content": "Responde únicamente con la palabra OK."}],
        temperature=0,
        max_tokens=5,
    )
    return (response.choices[0].message.content or "").strip()


def analizar_lote(convocatorias: list[dict], ajustes: dict | None = None) -> list[dict]:
    """Analiza una lista de convocatorias y retorna las enriquecidas."""
    ajustes = ajustes or cargar_ajustes()
    resultado = []
    total = len(convocatorias)
    for i, conv in enumerate(convocatorias):
        print(f"  Analizando {i + 1}/{total}: {conv.get('titulo', '')[:60]}...")
        analisis = analizar_convocatoria(conv, ajustes)
        resultado.append({**conv, "analisis": analisis})
    return resultado


def _aplicar_umbrales(analisis: dict, umbrales: dict) -> dict:
    """Ajusta la recomendación final con los umbrales configurados."""
    if not umbrales.get("ajustar_recomendacion", True):
        return analisis

    try:
        probabilidad = float(analisis.get("probabilidad_ganar", 0))
        cumplimiento = float(analisis.get("cumplimiento_requisitos", 0))
    except (TypeError, ValueError):
        return analisis

    recomendacion_modelo = analisis.get("recomendacion")

    if (
        probabilidad >= float(umbrales["aplicar_probabilidad"])
        and cumplimiento >= float(umbrales["aplicar_cumplimiento"])
    ):
        recomendacion = "APLICAR"
    elif (
        probabilidad < float(umbrales["descartar_probabilidad"])
        or cumplimiento < float(umbrales["descartar_cumplimiento"])
    ):
        recomendacion = "NO_APLICAR"
    else:
        recomendacion = "EVALUAR"

    if recomendacion_modelo:
        analisis["recomendacion_modelo"] = recomendacion_modelo
    analisis["recomendacion"] = recomendacion
    return analisis
