"""
Configuración editable del análisis. Se guarda en un JSON local,
sin necesidad de base de datos.
"""
import json
import os
from copy import deepcopy
from pathlib import Path

AJUSTES_FILE = Path(__file__).parent / "data" / "ajustes.json"

PERFIL_DEFAULT = """
La Facultad de Ingeniería de la Universidad de Antioquia tiene:
- 12 programas de pregrado: Ingeniería Civil, Sistemas, Industrial, Electrónica, Telecomunicaciones,
  Ambiental, Química, Materiales, Biomédica, Geológica, Agrícola y Mecánica.
- 20+ grupos de investigación reconocidos por Minciencias (categorías A1, A, B, C).
- Centro de Investigación CESET con laboratorios especializados.
- Experiencia en proyectos con entidades públicas y privadas.
- Capacidad para ejecutar contratos de investigación, consultoría, interventoría y obra.
- Convenios internacionales con universidades de Estados Unidos, Europa y Latinoamérica.
- Acreditación de alta calidad institucional.
- Experiencia en proyectos de infraestructura, agua potable, energías renovables,
  TIC, salud digital, medio ambiente y sostenibilidad.
- Presupuesto ejecutado anual promedio de 15.000 millones COP en proyectos externos.
""".strip()

INSTRUCCIONES_DEFAULT = (
    "Si el estado del proceso no está abierto o la fecha de cierre ya pasó, "
    "la recomendación debe ser NO_APLICAR, aunque la convocatoria sea "
    "temáticamente relevante."
)

DEFAULT = {
    "perfil": PERFIL_DEFAULT,
    "modelo": os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite"),
    "temperatura": 0.1,
    "limite_secop": 20,
    "criterios": {
        "afinidad": 40,
        "experiencia": 25,
        "requisitos": 25,
        "viabilidad": 10,
    },
    "umbrales": {
        "aplicar_probabilidad": 65,
        "aplicar_cumplimiento": 60,
        "descartar_probabilidad": 35,
        "descartar_cumplimiento": 30,
        "ajustar_recomendacion": True,
    },
    "instrucciones": INSTRUCCIONES_DEFAULT,
}

CRITERIOS_LABELS = {
    "afinidad": "Afinidad temática",
    "experiencia": "Experiencia y capacidades",
    "requisitos": "Cumplimiento de requisitos",
    "viabilidad": "Viabilidad y competencia",
}


def cargar_ajustes() -> dict:
    """Carga la configuración; ante cualquier error usa los valores por defecto."""
    if not AJUSTES_FILE.exists():
        return deepcopy(DEFAULT)
    try:
        datos = json.loads(AJUSTES_FILE.read_text(encoding="utf-8"))
        return _validar(datos)
    except Exception:
        return deepcopy(DEFAULT)


def guardar_ajustes(datos: dict) -> dict:
    """Valida y guarda la configuración de forma atómica."""
    limpio = _validar(datos)
    AJUSTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporal = AJUSTES_FILE.with_name(AJUSTES_FILE.name + ".tmp")
    temporal.write_text(
        json.dumps(limpio, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporal, AJUSTES_FILE)
    return limpio


def restablecer_ajustes() -> dict:
    return guardar_ajustes(deepcopy(DEFAULT))


def texto_criterios(criterios: dict) -> str:
    """Devuelve los criterios como porcentajes normalizados para el prompt."""
    total = sum(float(criterios.get(k, 0)) for k in CRITERIOS_LABELS) or 1
    lineas = []
    for clave, etiqueta in CRITERIOS_LABELS.items():
        valor = float(criterios.get(clave, 0))
        lineas.append(f"- {etiqueta}: {round(valor / total * 100)}%")
    return "\n".join(lineas)


def _validar(datos: dict) -> dict:
    if not isinstance(datos, dict):
        raise ValueError("La configuración debe ser un objeto JSON.")

    perfil = str(datos.get("perfil", "")).strip()
    if len(perfil) < 20:
        raise ValueError("El perfil institucional debe tener al menos 20 caracteres.")
    if len(perfil) > 20000:
        raise ValueError("El perfil institucional no puede superar 20.000 caracteres.")

    modelo = str(datos.get("modelo", "")).strip()
    if not modelo:
        raise ValueError("Debes indicar el modelo de OpenRouter.")
    if len(modelo) > 120:
        raise ValueError("El nombre del modelo no puede superar 120 caracteres.")

    temperatura = _numero(datos.get("temperatura", 0.1), "La temperatura")
    if not 0 <= temperatura <= 1:
        raise ValueError("La temperatura debe estar entre 0 y 1.")

    limite = _entero(datos.get("limite_secop", 20), "El límite de SECOP")
    if not 1 <= limite <= 50:
        raise ValueError("El límite de SECOP debe estar entre 1 y 50.")

    criterios_raw = datos.get("criterios")
    if not isinstance(criterios_raw, dict):
        raise ValueError("Los criterios de evaluación son obligatorios.")
    criterios = {}
    for clave, etiqueta in CRITERIOS_LABELS.items():
        valor = _numero(criterios_raw.get(clave, 0), f"El peso de {etiqueta.lower()}")
        if not 0 <= valor <= 100:
            raise ValueError(f"El peso de {etiqueta.lower()} debe estar entre 0 y 100.")
        criterios[clave] = round(valor, 2)
    if sum(criterios.values()) <= 0:
        raise ValueError("Al menos un criterio debe tener un peso mayor que cero.")

    umbrales_raw = datos.get("umbrales")
    if not isinstance(umbrales_raw, dict):
        raise ValueError("Los umbrales de recomendación son obligatorios.")

    umbrales = {}
    etiquetas = {
        "aplicar_probabilidad": "umbral de aplicación de probabilidad",
        "aplicar_cumplimiento": "umbral de aplicación de cumplimiento",
        "descartar_probabilidad": "umbral de descarte de probabilidad",
        "descartar_cumplimiento": "umbral de descarte de cumplimiento",
    }
    for clave, etiqueta in etiquetas.items():
        valor = _numero(umbrales_raw.get(clave, 0), f"El {etiqueta}")
        if not 0 <= valor <= 100:
            raise ValueError(f"El {etiqueta} debe estar entre 0 y 100.")
        umbrales[clave] = round(valor, 2)

    if umbrales["descartar_probabilidad"] > umbrales["aplicar_probabilidad"]:
        raise ValueError(
            "El umbral de descarte de probabilidad no puede ser mayor "
            "que el umbral de aplicación."
        )
    if umbrales["descartar_cumplimiento"] > umbrales["aplicar_cumplimiento"]:
        raise ValueError(
            "El umbral de descarte de cumplimiento no puede ser mayor "
            "que el umbral de aplicación."
        )

    ajustar = umbrales_raw.get("ajustar_recomendacion", True)
    if isinstance(ajustar, str):
        ajustar = ajustar.strip().lower() not in ("false", "0", "no", "")
    umbrales["ajustar_recomendacion"] = bool(ajustar)

    instrucciones = str(datos.get("instrucciones", "")).strip()
    if len(instrucciones) > 5000:
        raise ValueError("Las instrucciones adicionales no pueden superar 5.000 caracteres.")

    return {
        "perfil": perfil,
        "modelo": modelo,
        "temperatura": round(temperatura, 2),
        "limite_secop": limite,
        "criterios": criterios,
        "umbrales": umbrales,
        "instrucciones": instrucciones,
    }


def _numero(valor, etiqueta: str) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{etiqueta} debe ser un número.")


def _entero(valor, etiqueta: str) -> int:
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        raise ValueError(f"{etiqueta} debe ser un número entero.")
