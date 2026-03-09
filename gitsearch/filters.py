# -*- coding: utf-8 -*-
"""
filters.py — Validación y normalización de parámetros de búsqueda.
Responsabilidad: garantizar que sólo parámetros válidos llegan al motor.
"""

import re
from datetime import datetime


# Modos de búsqueda soportados
MODOS_VALIDOS = {"s", "g", "grep", "l"}


class FiltroInvalido(ValueError):
    """Se lanza cuando un parámetro de búsqueda no supera la validación."""
    pass


def validar_y_normalizar(params: dict) -> dict:
    """
    Valida y normaliza el dict de parámetros de búsqueda.

    Campos esperados (todos opcionales salvo que el modo los requiera):
        texto   : str  — cadena o patrón a buscar
        modo    : str  — 's' | 'g' | 'grep'  (default: auto)
        autor   : str  — filtro por autor (--author)
        desde   : str  — fecha inicio YYYY-MM-DD (--since)
        hasta   : str  — fecha fin YYYY-MM-DD (--until)
        archivo : str  — ruta de archivo (requerido para modo 'l')
        funcion : str  — nombre de función (modo 'l')
        max_count: int — límite de commits a analizar (default: 2000)

    Retorna dict normalizado listo para strategy.py.
    Lanza FiltroInvalido si hay un error irrecuperable.
    """
    out = {}

    # --- texto ---
    texto = str(params.get("texto", "")).strip()
    out["texto"] = texto

    # --- modo ---
    modo = str(params.get("modo", "auto")).strip().lower()
    if modo not in MODOS_VALIDOS and modo != "auto":
        raise FiltroInvalido(
            f"Modo '{modo}' no válido. Use: {', '.join(sorted(MODOS_VALIDOS))} o 'auto'."
        )
    out["modo"] = modo

    # --- modo 'l' requiere archivo ---
    if modo == "l" and not params.get("archivo", "").strip():
        raise FiltroInvalido("El modo 'l' (trazabilidad de función/rango) requiere el parámetro 'archivo'.")

    # --- autor ---
    out["autor"] = str(params.get("autor", "")).strip()

    # --- fechas ---
    def _validar_fecha(valor: str, nombre: str) -> str:
        valor = str(valor).strip()
        if not valor:
            return ""
        try:
            datetime.strptime(valor, "%Y-%m-%d")
            return valor
        except ValueError:
            raise FiltroInvalido(f"'{nombre}' debe tener formato YYYY-MM-DD. Recibido: '{valor}'")

    out["desde"] = _validar_fecha(params.get("desde", ""), "desde")
    out["hasta"] = _validar_fecha(params.get("hasta", ""), "hasta")

    # --- archivo y función (para modo -L) ---
    out["archivo"] = str(params.get("archivo", "")).strip()
    out["funcion"] = str(params.get("funcion", "")).strip()

    # --- max_count ---
    try:
        max_count = int(params.get("max_count", 2000))
        if max_count <= 0:
            max_count = 2000
    except (ValueError, TypeError):
        max_count = 2000
    out["max_count"] = max_count

    # --- regex: si modo 'g' o 's', validar que el patrón compile ---
    if modo in ("g",) and texto:
        try:
            re.compile(texto)
        except re.error as e:
            raise FiltroInvalido(f"El patrón regex '{texto}' no es válido: {e}")

    return out
