"""
Analiza cada convocatoria con IA y calcula:
- Probabilidad de que la Facultad de Ingeniería gane
- % cumplimiento de requisitos
- Áreas relevantes
- Resumen ejecutivo
"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

PERFIL_FACULTAD = """
La Facultad de Ingeniería de la Universidad de Antioquia tiene:
- 12 programas de pregrado: Ingeniería Civil, Sistemas, Industrial, Electrónica, Telecomunicaciones, 
  Ambiental, Química, Materiales, Biomédica, Geológica, Agrícola, Mecánica
- 20+ grupos de investigación reconocidos por Minciencias (categorías A1, A, B, C)
- Centro de Investigación CESET con laboratorios especializados
- Experiencia en proyectos con entidades públicas y privadas
- Capacidad para ejecutar contratos de investigación, consultoría, interventoría y obra
- Convenios internacionales con universidades de USA, Europa y Latinoamérica
- Acreditación de alta calidad institucional
- Experiencia en proyectos de infraestructura, agua potable, energías renovables, 
  TIC, salud digital, medio ambiente y sostenibilidad
- Presupuesto ejecutado anual promedio: 15.000 millones COP en proyectos externos
"""

def get_client():
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY no configurada en .env")
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={"HTTP-Referer": "convocatorias-udea"},
    )


def analizar_convocatoria(conv: dict) -> dict:
    """
    Analiza una convocatoria y retorna el análisis estructurado.
    """
    try:
        client = get_client()
        model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite")

        prompt = f"""Analiza esta convocatoria y evalúa si la Facultad de Ingeniería de la Universidad de Antioquia debería aplicar.

PERFIL DE LA FACULTAD:
{PERFIL_FACULTAD}

CONVOCATORIA:
Título: {conv.get('titulo', '')}
Entidad: {conv.get('entidad', '')}
Fuente: {conv.get('fuente', '')}
Monto: ${conv.get('monto', 0):,} COP
Modalidad: {conv.get('modalidad', '')}
Estado: {conv.get('estado', '')}
Fecha cierre: {conv.get('fecha_cierre', '')}
Departamento: {conv.get('departamento', '')}

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
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )

        import json, re
        text = response.choices[0].message.content.strip()
        # Limpiar markdown si viene con ```json
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        analisis = json.loads(text)
        return analisis

    except Exception as e:
        return {
            "relevante": True,
            "probabilidad_ganar": 50,
            "cumplimiento_requisitos": 50,
            "areas_relevantes": [],
            "resumen": f"No se pudo analizar: {str(e)[:100]}",
            "fortalezas": [],
            "riesgos": ["Error en análisis IA"],
            "recomendacion": "EVALUAR",
        }


def analizar_lote(convocatorias: list[dict]) -> list[dict]:
    """Analiza una lista de convocatorias y retorna las enriquecidas."""
    resultado = []
    total = len(convocatorias)
    for i, conv in enumerate(convocatorias):
        print(f"  Analizando {i+1}/{total}: {conv.get('titulo', '')[:60]}...")
        analisis = analizar_convocatoria(conv)
        resultado.append({**conv, "analisis": analisis})
    return resultado
