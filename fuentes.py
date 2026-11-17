"""
Fuentes de convocatorias. Usa APIs públicas donde existen,
scraping simple donde no hay Cloudflare.
Sin dependencia de Playwright — usa httpx puro.
"""
import asyncio
import re
from html import unescape

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
TIMEOUT = 20

MINCIENCIAS_URL = "https://minciencias.gov.co/convocatorias/todas"
MESES_ES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


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
                    "fecha_cierre": "",
                    "fecha_publicacion": item.get("fecha_de_publicacion_del", "").split("T")[0],
                    "estado": item.get("estado_de_apertura_del_proceso", ""),
                    "modalidad": item.get("modalidad_de_contratacion", ""),
                    "departamento": item.get("departamento_entidad", ""),
                    "raw": {},
                })
            print(f"[SECOP] Obtenidas {len(results)} convocatorias")
            return results
    except Exception as e:
        print(f"[SECOP] Error: {e}")
        return []


async def fetch_minciencias(paginas: int = 3) -> list[dict]:
    """
    Minciencias - listado público de convocatorias (Drupal, tabla de vistas).
    Clasifica como "Regalías SGR" las convocatorias financiadas con recursos
    del Sistema General de Regalías y consulta el detalle para obtener estado
    y fecha de cierre.
    """
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={**HEADERS, "Accept": "text/html,application/xhtml+xml"},
        ) as client:
            lista = []
            for page in range(max(1, paginas)):
                r = await client.get(MINCIENCIAS_URL, params={"page": page})
                r.raise_for_status()
                items = _parse_minciencias_listing(r.text)
                if not items:
                    break
                lista.extend(items)

            sem = asyncio.Semaphore(5)

            async def consultar(item):
                async with sem:
                    return await _fetch_minciencias_detalle(client, item)

            detalles = await asyncio.gather(
                *(consultar(item) for item in lista),
                return_exceptions=True,
            )
    except Exception as e:
        print(f"[Minciencias] Error: {e}")
        return []

    resultados = []
    vistos = set()
    for item in detalles:
        if not isinstance(item, dict):
            continue
        estado = item.get("estado") or "No verificada"
        if estado in ("Finalizada", "Cerrada"):
            continue
        entidad = "Ministerio de Ciencias, Tecnología e Innovación"
        key = (item.get("titulo", ""), entidad)
        if key in vistos:
            continue
        vistos.add(key)
        resultados.append({
            "fuente": "Regalías SGR" if item.get("sgr") else "Minciencias",
            "titulo": item.get("titulo", "Sin título"),
            "entidad": entidad,
            "url": item.get("url", ""),
            "monto": item.get("monto", 0),
            "fecha_cierre": item.get("fecha_cierre", ""),
            "fecha_publicacion": item.get("fecha_publicacion", ""),
            "estado": estado,
            "modalidad": "Investigación y CTI",
            "departamento": "Nacional",
            "raw": {},
        })

    print(f"[Minciencias] Obtenidas {len(resultados)} convocatorias vigentes o recientes")
    return resultados


def _parse_minciencias_listing(html: str) -> list[dict]:
    """Extrae las filas de la tabla de convocatorias del listado."""
    tabla = re.search(
        r'<table[^>]*views-table[^>]*>.*?<tbody>(.*?)</tbody>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not tabla:
        return []

    resultados = []
    for fila in re.findall(r'<tr[^>]*>(.*?)</tr>', tabla.group(1), re.DOTALL | re.IGNORECASE):
        enlace = re.search(
            r'views-field-title[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            fila,
            re.DOTALL | re.IGNORECASE,
        )
        if not enlace:
            continue

        href = enlace.group(1).strip()
        titulo = _limpiar_html(enlace.group(2))
        if not titulo:
            continue

        descripcion = _celda(fila, "views-field-body")
        cuantia = _celda(fila, "views-field-field-cuantia")
        fecha = re.search(r'content="(\d{4}-\d{2}-\d{2})', fila, re.IGNORECASE)
        url = href if href.startswith("http") else f"https://minciencias.gov.co{href}"
        texto = f"{titulo} {descripcion}"

        resultados.append({
            "titulo": titulo,
            "url": url,
            "descripcion": descripcion[:1000],
            "monto": _parse_monto(cuantia),
            "fecha_publicacion": fecha.group(1) if fecha else "",
            "sgr": bool(re.search(r"regal[ií]as|\bSGR\b", texto, re.IGNORECASE)),
        })

    return resultados


async def _fetch_minciencias_detalle(client: httpx.AsyncClient, item: dict) -> dict:
    """Consulta una convocatoria para obtener estado, cierre y monto."""
    r = await client.get(item["url"])
    r.raise_for_status()
    html = r.text

    estado_txt = _extraer_texto(html, r"panel-state-tex.*?<p>(.*?)</p>")
    cierre_txt = _extraer_texto(
        html,
        r">\s*Cierre\s*</td>.*?<td[^>]*views-field-body[^>]*>(.*?)</td>",
    )
    recursos_txt = _extraer_texto(
        html,
        r"panel-resoruce.*?panel-resource-tex.*?<p>(.*?)</p>",
    )

    item["estado"] = _normalizar_estado(estado_txt)
    item["fecha_cierre"] = _parse_fecha_larga(cierre_txt)

    if not item.get("monto"):
        monto = re.search(r"\$\s*([\d.,]+)", recursos_txt)
        if monto:
            item["monto"] = _parse_monto(monto.group(1))

    return item


def _celda(fila: str, clase: str) -> str:
    m = re.search(
        r'<td[^>]*class="[^"]*' + re.escape(clase) + r'[^"]*"[^>]*>(.*?)</td>',
        fila,
        re.DOTALL | re.IGNORECASE,
    )
    return _limpiar_html(m.group(1)) if m else ""


def _extraer_texto(html: str, patron: str) -> str:
    m = re.search(patron, html, re.DOTALL | re.IGNORECASE)
    return _limpiar_html(m.group(1)) if m else ""


def _limpiar_html(valor: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", valor or "")
    texto = unescape(texto)
    return re.sub(r"\s+", " ", texto).strip()


def _normalizar_estado(texto: str) -> str:
    t = (texto or "").lower()
    if "finaliz" in t:
        return "Finalizada"
    if "cerrad" in t:
        return "Cerrada"
    if "evaluaci" in t:
        return "En evaluación"
    if "abiert" in t:
        return "Abierta"
    return "No verificada"


def _parse_fecha_larga(texto: str) -> str:
    """Convierte 'viernes 13 noviembre 2026 04:00 pm' a '2026-11-13'."""
    m = re.search(
        r"(\d{1,2})\s+(?:de\s+)?([a-záéíóúñ]+)\s+(?:de\s+)?(\d{4})",
        texto or "",
        re.IGNORECASE,
    )
    if not m:
        return ""
    mes = MESES_ES.get(m.group(2).lower())
    if not mes:
        return ""
    return f"{int(m.group(3)):04d}-{mes:02d}-{int(m.group(1)):02d}"


async def fetch_todas(limite_secop: int = 30) -> list[dict]:
    """Obtiene convocatorias de todas las fuentes en paralelo."""
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
        s = str(valor or "").replace("$", "").replace(" ", "").strip()
        if not s:
            return 0
        if "," in s:
            s = s.split(",")[0].replace(".", "")
        elif s.count(".") > 1:
            s = s.replace(".", "")
        elif "." in s:
            entero, decimales = s.split(".", 1)
            s = entero if len(decimales) <= 2 else s.replace(".", "")
        return int(float(s))
    except Exception:
        return 0
