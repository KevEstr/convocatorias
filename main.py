"""
Servidor principal del Radar de Convocatorias.
"""
import asyncio
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from fuentes import fetch_todas
from analizador import analizar_lote
from db import guardar_convocatorias, obtener_todas, obtener_stats

app = FastAPI(title="Radar Convocatorias UdeA")

TEMPLATES = Path(__file__).parent / "templates"


@app.get("/", response_class=HTMLResponse)
async def index():
    return (TEMPLATES / "index.html").read_text(encoding="utf-8")


@app.get("/api/convocatorias")
async def api_convocatorias():
    return JSONResponse(obtener_todas())


@app.get("/api/stats")
async def api_stats():
    return JSONResponse(obtener_stats())


@app.post("/api/actualizar")
async def api_actualizar():
    """
    Obtiene convocatorias de todas las fuentes,
    las analiza con IA y guarda las nuevas.
    """
    try:
        print("Obteniendo convocatorias...")
        convocatorias = await fetch_todas(limite_secop=20)
        print(f"  {len(convocatorias)} obtenidas. Analizando con IA...")

        # Analizar en executor para no bloquear el event loop
        loop = asyncio.get_event_loop()

        def _analizar():
            return analizar_lote(convocatorias)

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
