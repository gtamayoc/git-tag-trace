"""
filters.py — Validación y normalización de parámetros de búsqueda.
Responsabilidad: garantizar que sólo parámetros válidos llegan al motor.
"""

import re
from datetime import datetime
from typing import Any

MODOS_VALIDOS = {"s", "g", "grep", "l"}


class FiltroInvalido(ValueError):
    """Se lanza cuando un parámetro de búsqueda no supera la validación."""
    pass


def validar_y_normalizar(params: dict[str, Any]) -> dict[str, Any]:
    """Valida y normaliza el dict de parámetros de búsqueda."""
    out: dict[str, Any] = {}

    texto = str(params.get("texto", "")).strip()
    out["texto"] = texto

    modo = str(params.get("modo", "auto")).strip().lower()
    if modo not in MODOS_VALIDOS and modo != "auto":
        raise FiltroInvalido(
            f"Modo '{modo}' no válido. Use: {', '.join(sorted(MODOS_VALIDOS))} o 'auto'."
        )
    out["modo"] = modo

    if modo == "l" and not params.get("archivo", "").strip():
        raise FiltroInvalido("El modo 'l' (trazabilidad de función/rango) requiere el parámetro 'archivo'.")

    out["autor"] = str(params.get("autor", "")).strip()

    def _validar_fecha(valor: str, nombre: str) -> str:
        valor = str(valor).strip()
        if not valor:
            return ""
        try:
            datetime.strptime(valor, "%Y-%m-%d")
            return valor
        except ValueError as e:
            raise FiltroInvalido(f"'{nombre}' debe tener formato YYYY-MM-DD. Recibido: '{valor}'") from e

    out["desde"] = _validar_fecha(params.get("desde", ""), "desde")
    out["hasta"] = _validar_fecha(params.get("hasta", ""), "hasta")

    out["archivo"] = str(params.get("archivo", "")).strip()
    out["funcion"] = str(params.get("funcion", "")).strip()

    try:
        max_count = int(params.get("max_count", 2000))
        if max_count <= 0:
            max_count = 2000
    except (ValueError, TypeError):
        max_count = 2000
    out["max_count"] = max_count

    if modo in ("g",) and texto:
        try:
            re.compile(texto)
        except re.error as e:
            raise FiltroInvalido(f"El patrón regex '{texto}' no es válido: {e}") from e

    return out
