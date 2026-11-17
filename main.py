"""
Servidor principal del Radar de Convocatorias.
"""
import asyncio
import sys
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from fuentes import fetch_todas
from analizador import analizar_lote, probar_conexion
from ajustes import cargar_ajustes, guardar_ajustes, restablecer_ajustes
from db import actualizar_analisis, guardar_convocatorias, obtener_todas, obtener_stats

app = FastAPI(title="Radar Convocatorias UdeA")

TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (TEMPLATES / "index.html").read_text(encoding="utf-8")


@app.get("/api/convocatorias")
async def api_convocatorias():
    return JSONResponse(obtener_todas())


@app.get("/api/stats")
async def api_stats():
    return JSONResponse(obtener_stats())


@app.get("/api/ajustes")
async def api_obtener_ajustes():
    return JSONResponse(cargar_ajustes())


@app.put("/api/ajustes")
async def api_guardar_ajustes(payload: dict = Body(...)):
    try:
        return JSONResponse(guardar_ajustes(payload))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/ajustes/restablecer")
async def api_restablecer_ajustes():
    return JSONResponse(restablecer_ajustes())


@app.post("/api/probar_modelo")
async def api_probar_modelo():
    """Valida la clave de OpenRouter y el modelo configurado."""
    ajustes = cargar_ajustes()
    try:
        respuesta = probar_conexion(ajustes)
        return {"ok": True, "modelo": ajustes["modelo"], "respuesta": respuesta}
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content={"ok": False, "modelo": ajustes["modelo"], "error": str(e)},
        )


@app.post("/api/reanalizar")
async def api_reanalizar():
    """Vuelve a analizar las convocatorias registradas con la configuración actual."""
    try:
        ajustes = cargar_ajustes()
        data = obtener_todas()
        if not data:
            return {"ok": True, "total": 0, "actualizados": 0}

        print(f"Reanalizando {len(data)} convocatorias...")
        analizadas = analizar_lote(data, ajustes)
        por_clave = {
            (c.get("titulo", ""), c.get("entidad", "")): c.get("analisis")
            for c in analizadas
        }
        actualizados = actualizar_analisis(por_clave)
        print(f"  {actualizados} análisis actualizados.")

        return {"ok": True, "total": len(analizadas), "actualizados": actualizados}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/actualizar")
async def api_actualizar():
    """
    Obtiene convocatorias de todas las fuentes,
    las analiza con IA y guarda las nuevas.
    """
    try:
        ajustes = cargar_ajustes()
        print("Obteniendo convocatorias...")
        convocatorias = await fetch_todas(limite_secop=ajustes["limite_secop"])
        print(f"  {len(convocatorias)} obtenidas. Analizando con IA...")

        # Analizar en executor para no bloquear el event loop
        loop = asyncio.get_event_loop()

        def _analizar():
            return analizar_lote(convocatorias, ajustes)

        if sys.platform == "win32":
            # En Windows correr en thread con ProactorEventLoop no aplica aquí
            # porque no usamos Playwright — httpx es puro async, funciona directo
            analizadas = _analizar()
        else:
            analizadas = await loop.run_in_executor(None, _analizar)

        nuevas = guardar_convocatorias(analizadas)
        print(f"  {nuevas} convocatorias nuevas guardadas.")

        return {"ok": True, "total": len(analizadas), "nuevas": nuevas}

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8090, reload=True)
