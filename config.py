import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "google/gemini-2.5-flash-lite"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DB_PATH = "convocatorias.db"

FACULTY_PROFILE = """
Facultad de Ingeniería - Universidad de Antioquia
- Áreas: Ingeniería de Sistemas, Civil, Electrónica, Industrial, Ambiental, Materiales, Bioingeniería, Telecomunicaciones
- Grupos de investigación acreditados en Colciencias
- Capacidad para proyectos de investigación, consultoría técnica, formación
- Ubicación: Medellín, Colombia
- Entidad pública (universidad estatal)
- Experiencia en proyectos con MinCiencias, SENA, Alcaldía de Medellín
"""

# Keywords para scoring sin IA
ENGINEERING_KEYWORDS = [
    "ingeniería", "sistemas", "civil", "electrónica", "industrial",
    "ambiental", "materiales", "bioingeniería", "telecomunicaciones",
    "software", "tecnología", "innovación", "investigación", "desarrollo",
    "consultoría", "infraestructura", "construcción", "diseño", "redes",
    "automatización", "robótica", "energía", "agua", "medio ambiente",
    "ti", "informática", "digital", "transformación digital", "datos",
    "inteligencia artificial", "machine learning", "iot", "sensores",
    "universidad", "académico", "educación superior", "formación",
]
