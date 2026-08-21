import httpx
import hashlib
import re
from datetime import datetime, date
from typing import Optional

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_id(source: str, raw_id: str) -> str:
    return hashlib.md5(f"{source}:{raw_id}".encode()).hexdigest()


def _parse_monto(value) -> Optional[float]:
    if value is None:
        return None
    try:
        cleaned = re.sub(r"[^\d.]", "", str(value))
        return float(cleaned) if cleaned else None
    except Exception:
        return None


def _fmt_date(value: str) -> Optional[str]:
    """Normalize various date formats to ISO date string YYYY-MM-DD."""
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
                "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value[:19], fmt[:len(value[:19])]).strftime("%Y-%m-%d")
        except Exception:
            continue
    # Return as-is if nothing matched
    return str(value)[:10]


# ---------------------------------------------------------------------------
# SECOP II – datos.gov.co SODA API
# ---------------------------------------------------------------------------

SECOP_URL = "https://www.datos.gov.co/resource/jbjy-vk9h.json"

# Fields that suggest engineering / research relevance
ENGINEERING_TERMS = [
    "ingeniería", "ingenieria", "sistemas", "tecnología", "tecnologia",
    "software", "infraestructura", "consultoría", "consultoria",
    "ambiental", "electrónica", "electronica", "civil", "industrial",
    "investigación", "investigacion", "desarrollo", "innovación", "innovacion",
    "construcción", "construccion", "digital", "datos", "redes", "energía",
    "energia", "agua", "saneamiento", "educación", "educacion",
]


def _is_engineering_relevant(record: dict) -> bool:
    text = " ".join([
        str(record.get("nombre_del_procedimiento", "")),
        str(record.get("descripci_n_del_procedimiento", "")),
        str(record.get("objeto_a_contratar", "")),
    ]).lower()
    return any(term in text for term in ENGINEERING_TERMS)


async def fetch_secop() -> list[dict]:
    """Fetch open procurement calls from SECOP II via datos.gov.co SODA API."""
    params = {
        "$where": "estado_del_proceso='Convocatoria'",
        "$limit": "50",
        "$order": "fecha_de_publicacion_del_proceso DESC",
    }
    results = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(SECOP_URL, params=params)
            resp.raise_for_status()
            records = resp.json()

        for r in records:
            if not _is_engineering_relevant(r):
                continue

            raw_id = r.get("id_del_portafolio") or r.get("referencia_del_proceso") or str(r)
            item = {
                "id": _make_id("secop", raw_id),
                "titulo": r.get("nombre_del_procedimiento") or r.get("objeto_a_contratar", "Sin título"),
                "entidad": r.get("nombre_entidad", "Entidad no especificada"),
                "fuente": "secop",
                "url": r.get("urlproceso", {}).get("url") if isinstance(r.get("urlproceso"), dict) else r.get("urlproceso", ""),
                "monto": _parse_monto(r.get("precio_base")),
                "fecha_cierre": _fmt_date(r.get("fecha_limite_de_recepci_n")),
                "fecha_publicacion": _fmt_date(r.get("fecha_de_publicacion_del_proceso")),
                "descripcion": (r.get("descripci_n_del_procedimiento") or r.get("objeto_a_contratar") or "")[:1000],
                "estado": "abierta",
            }
            results.append(item)

        print(f"[SECOP] Obtenidas {len(results)} convocatorias relevantes")
    except Exception as e:
        print(f"[SECOP] Error al obtener datos: {e}")

    return results


# ---------------------------------------------------------------------------
# Minciencias scraping
# ---------------------------------------------------------------------------

MINCIENCIAS_URL = "https://minciencias.gov.co/convocatorias/todas"


async def fetch_minciencias() -> list[dict]:
    """Scrape open calls from Minciencias website."""
    if not BS4_AVAILABLE:
        print("[Minciencias] BeautifulSoup no disponible, saltando.")
        return []

    results = []
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "es-CO,es;q=0.9",
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(MINCIENCIAS_URL, headers=headers)
            resp.raise_for_status()
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")

        # Try multiple selectors – Minciencias changes their layout occasionally
        cards = (
            soup.select(".view-convocatorias .views-row") or
            soup.select(".convocatoria-item") or
            soup.select("article.convocatoria") or
            soup.select(".field-content a[href*='convocatoria']") or
            soup.select("h3 a, h2 a")
        )

        seen = set()
        for card in cards[:30]:
            # Extract link + title
            link_tag = card.find("a") if card.name != "a" else card
            if not link_tag:
                continue
            title = link_tag.get_text(strip=True)
            href = link_tag.get("href", "")
            if not href or not title or title in seen:
                continue
            seen.add(title)

            if not href.startswith("http"):
                href = "https://minciencias.gov.co" + href

            # Try to find date nearby
            date_text = ""
            parent = link_tag.parent
            if parent:
                date_tag = parent.find(class_=re.compile(r"date|fecha", re.I))
                if date_tag:
                    date_text = date_tag.get_text(strip=True)

            item = {
                "id": _make_id("minciencias", href),
                "titulo": title[:300],
                "entidad": "Minciencias",
                "fuente": "minciencias",
                "url": href,
                "monto": None,
                "fecha_cierre": _fmt_date(date_text) if date_text else None,
                "fecha_publicacion": date.today().isoformat(),
                "descripcion": title,
                "estado": "abierta",
            }
            results.append(item)

        print(f"[Minciencias] Obtenidas {len(results)} convocatorias")
    except Exception as e:
        print(f"[Minciencias] Error al obtener datos: {e}")

    return results


# ---------------------------------------------------------------------------
# Demo data (always available)
# ---------------------------------------------------------------------------

def get_demo_data() -> list[dict]:
    """Realistic demo convocatorias for when APIs are unavailable."""
    today = date.today().isoformat()
    return [
        {
            "id": _make_id("demo", "mintic-2025-001"),
            "titulo": "Convocatoria para proyectos de Transformación Digital en Entidades Públicas",
            "entidad": "MinTIC",
            "fuente": "demo",
            "url": "https://www.mintic.gov.co/portal/convocatorias/",
            "monto": 1_500_000_000,
            "fecha_cierre": "2025-09-30",
            "fecha_publicacion": today,
            "descripcion": (
                "Convocatoria para financiar proyectos de transformación digital en entidades públicas "
                "colombianas, con énfasis en desarrollo de software, interoperabilidad, gobierno digital "
                "y ciberseguridad. Dirigida a universidades e instituciones de educación superior."
            ),
            "estado": "abierta",
        },
        {
            "id": _make_id("demo", "minciencias-2025-cv001"),
            "titulo": "Convocatoria 894 - Proyectos de I+D+i en Áreas Estratégicas Nacionales",
            "entidad": "Minciencias",
            "fuente": "demo",
            "url": "https://minciencias.gov.co/convocatorias",
            "monto": 3_200_000_000,
            "fecha_cierre": "2025-10-15",
            "fecha_publicacion": today,
            "descripcion": (
                "Financiación de proyectos de investigación, desarrollo tecnológico e innovación "
                "en áreas prioritarias: biotecnología, materiales avanzados, energías renovables, "
                "TIC y medio ambiente. Grupos de investigación avalados por universidades públicas."
            ),
            "estado": "abierta",
        },
        {
            "id": _make_id("demo", "sena-2025-soft"),
            "titulo": "Alianzas para la Formación – Programa TIC y Desarrollo de Software",
            "entidad": "SENA",
            "fuente": "demo",
            "url": "https://www.sena.edu.co/es-co/Empresarios/Paginas/alianzasFormacion.aspx",
            "monto": 800_000_000,
            "fecha_cierre": "2025-08-31",
            "fecha_publicacion": today,
            "descripcion": (
                "Convocatoria para alianzas entre el SENA y entidades del sector educativo para "
                "diseño y ejecución de programas de formación en desarrollo de software, "
                "programación, ciberseguridad y análisis de datos. Dirigida a instituciones de "
                "educación superior con programas de ingeniería de sistemas."
            ),
            "estado": "abierta",
        },
        {
            "id": _make_id("demo", "alcaldia-med-2025-003"),
            "titulo": "Consultoría – Diseño y Supervisión de Obras de Infraestructura Vial Urbana",
            "entidad": "Alcaldía de Medellín – INDER",
            "fuente": "demo",
            "url": "https://www.medellin.gov.co/secop",
            "monto": 650_000_000,
            "fecha_cierre": "2025-09-10",
            "fecha_publicacion": today,
            "descripcion": (
                "Proceso de selección para prestación de servicios de consultoría en diseño "
                "geométrico, estudio de suelos y supervisión técnica de obras de rehabilitación "
                "vial en comunas 8, 13 y 16 de Medellín. Requiere experiencia en ingeniería civil "
                "y topografía."
            ),
            "estado": "abierta",
        },
        {
            "id": _make_id("demo", "epm-2025-env"),
            "titulo": "Servicios de Monitoreo Ambiental y Modelación Hidráulica – Proyecto Ituango",
            "entidad": "EPM – Empresas Públicas de Medellín",
            "fuente": "demo",
            "url": "https://www.epm.com.co/site/proveedores-y-contratistas",
            "monto": 2_100_000_000,
            "fecha_cierre": "2025-10-05",
            "fecha_publicacion": today,
            "descripcion": (
                "Contratación de servicios especializados en monitoreo de calidad del agua, "
                "modelación hidráulica computacional y evaluación de impacto ambiental en el "
                "área de influencia del proyecto hidroeléctrico Ituango. Se requiere equipo "
                "interdisciplinario de ingeniería ambiental, civil e hidráulica."
            ),
            "estado": "abierta",
        },
        {
            "id": _make_id("demo", "gobant-2025-tic"),
            "titulo": "Implementación de Plataforma de Gestión de Residuos Sólidos con IoT",
            "entidad": "Gobernación de Antioquia",
            "fuente": "demo",
            "url": "https://www.antioquia.gov.co/proveedores",
            "monto": 450_000_000,
            "fecha_cierre": "2025-08-25",
            "fecha_publicacion": today,
            "descripcion": (
                "Desarrollo e implementación de un sistema de información integrado con "
                "sensores IoT para el monitoreo y optimización de rutas de recolección "
                "de residuos sólidos en 15 municipios del departamento. Incluye desarrollo "
                "de app móvil y dashboard de gestión."
            ),
            "estado": "abierta",
        },
        {
            "id": _make_id("demo", "colciencias-2025-jovenes"),
            "titulo": "Convocatoria Jóvenes Investigadores e Innovadores 2025",
            "entidad": "Minciencias",
            "fuente": "demo",
            "url": "https://minciencias.gov.co/convocatorias/jovenes-investigadores",
            "monto": 120_000_000,
            "fecha_cierre": "2025-09-20",
            "fecha_publicacion": today,
            "descripcion": (
                "Convocatoria nacional para vincular jóvenes profesionales y recién graduados "
                "a grupos de investigación reconocidos. Áreas prioritarias: ingeniería, ciencias "
                "exactas, ciencias de la vida y ciencias sociales. Las universidades deben avalar "
                "los proyectos y co-financiar hasta el 30%."
            ),
            "estado": "abierta",
        },
        {
            "id": _make_id("demo", "icontec-2025-norm"),
            "titulo": "Servicios de Asistencia Técnica en Normalización – Sector Construcción Sostenible",
            "entidad": "ICONTEC",
            "fuente": "demo",
            "url": "https://www.icontec.org/contratacion",
            "monto": 180_000_000,
            "fecha_cierre": "2025-08-15",
            "fecha_publicacion": today,
            "descripcion": (
                "Contratación de entidad universitaria para prestar servicios de asistencia "
                "técnica en el proceso de actualización de normas técnicas colombianas relacionadas "
                "con construcción sostenible, materiales de construcción y eficiencia energética "
                "en edificaciones."
            ),
            "estado": "abierta",
        },
    ]
