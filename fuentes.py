"""
Fuentes de convocatorias. Usa APIs públicas donde existen,
scraping simple donde no hay Cloudflare.
Sin dependencia de Playwright — usa httpx puro.
"""
import httpx
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
TIMEOUT = 20


async def fetch_secop(limite: int = 30) -> list[dict]:
    """
    SECOP II - API pública datos.gov.co (dataset p6dx-8zbt).
    Procesos en fase de presentación de oferta (convocados/abiertos).
    """
    url = "https://www.datos.gov.co/resource/p6dx-8zbt.json"
    params = {
        "$limit": limite,
        "$where": (
            "estado_de_apertura_del_proceso='Abierto' AND ("
            "upper(nombre_del_procedimiento) like '%INGENIERIA%' OR "
            "upper(nombre_del_procedimiento) like '%INFRAESTRUCTURA%' OR "
            "upper(nombre_del_procedimiento) like '%INVESTIGACION%' OR "
            "upper(nombre_del_procedimiento) like '%TECNOLOGIA%' OR "
            "upper(nombre_del_procedimiento) like '%INNOVACION%' OR "
            "upper(nombre_del_procedimiento) like '%CONSULTORIA%' OR "
            "upper(nombre_del_procedimiento) like '%INTERVENTORIA%' OR "
            "upper(nombre_del_procedimiento) like '%AMBIENTAL%' OR "
            "upper(nombre_del_procedimiento) like '%SISTEMAS%' OR "
            "upper(nombre_del_procedimiento) like '%SOFTWARE%' OR "
            "upper(nombre_del_procedimiento) like '%ENERGIA%' OR "
            "upper(nombre_del_procedimiento) like '%CONSTRUCCION%'"
            ")"
        ),
        "$order": "fecha_de_publicacion_del DESC",
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(url, params=params, headers=HEADERS)
            r.raise_for_status()
            data = r.json()
            results = []
            for item in data:
                url_proceso = ""
                u = item.get("urlproceso")
                if isinstance(u, dict):
                    url_proceso = u.get("url", "")
                elif isinstance(u, str):
                    url_proceso = u

                results.append({
                    "fuente": "SECOP II",
                    "titulo": item.get("nombre_del_procedimiento") or item.get("descripci_n_del_procedimiento", "Sin título"),
                    "entidad": item.get("entidad", ""),
                    "url": url_proceso,
                    "monto": _parse_monto(item.get("precio_base", "0")),
                    "fecha_cierre": item.get("fecha_de_ultima_publicaci", "").split("T")[0],
                    "fecha_publicacion": item.get("fecha_de_publicacion_del", "").split("T")[0],
                    "estado": item.get("estado_de_apertura_del_proceso", ""),
                    "modalidad": item.get("modalidad_de_contratacion", ""),
                    "departamento": item.get("departamento_entidad", ""),
                    "raw": {},
                })
            return results
    except Exception as e:
        print(f"[SECOP] Error: {e}")
        return []


async def fetch_minciencias() -> list[dict]:
    """
    Minciencias - scraping de página de convocatorias.
    Sin Cloudflare, HTML estático.
    """
    url = "https://minciencias.gov.co/convocatorias/todas"
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={**HEADERS, "Accept": "text/html,application/xhtml+xml"},
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            return _parse_minciencias_html(r.text)
    except Exception as e:
        print(f"[Minciencias] Error: {e}")
        return []


def _parse_minciencias_html(html: str) -> list[dict]:
    """Extrae convocatorias del HTML de Minciencias con regex."""
    import re
    results = []

    # Extraer bloques de convocatoria
    bloques = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)

    for bloque in bloques[:30]:
        # Título con link
        titulo_m = re.search(
            r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]{10,}?)\s*</a>',
            bloque, re.IGNORECASE
        )
        fecha_m = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})', bloque)
        estado_m = re.search(
            r'(Abierta|Cerrada|Pr[oó]ximamente|En evaluaci[oó]n)',
            bloque, re.IGNORECASE
        )
        monto_m = re.search(r'\$\s*([\d.,]+)', bloque)

        if not titulo_m:
            continue

        href = titulo_m.group(1).strip()
        titulo = titulo_m.group(2).strip()
        estado = estado_m.group(1) if estado_m else "Abierta"

        if "cerrada" in estado.lower():
            continue

        full_url = href if href.startswith("http") else f"https://minciencias.gov.co{href}"

        results.append({
            "fuente": "Minciencias",
            "titulo": titulo,
            "entidad": "Ministerio de Ciencias, Tecnología e Innovación",
            "url": full_url,
            "monto": _parse_monto(monto_m.group(1)) if monto_m else 0,
            "fecha_cierre": fecha_m.group(1) if fecha_m else "",
            "fecha_publicacion": "",
            "estado": estado,
            "modalidad": "Investigación y CTI",
            "departamento": "Nacional",
            "raw": {},
        })

    return results


async def fetch_todas(limite_secop: int = 30) -> list[dict]:
    """Obtiene convocatorias de todas las fuentes en paralelo."""
    import asyncio
    resultados = await asyncio.gather(
        fetch_secop(limite_secop),
        fetch_minciencias(),
        return_exceptions=True,
    )
    todas = []
    for r in resultados:
        if isinstance(r, list):
            todas.extend(r)
        elif isinstance(r, Exception):
            print(f"[fuentes] Error en fuente: {r}")
    return todas


def _parse_monto(valor: str) -> int:
    try:
        return int(float(str(valor).replace(",", "").replace("$", "").replace(".", "").strip()))
    except:
        return 0
