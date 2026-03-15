"""
strategy.py — Selección inteligente del comando Git según los parámetros.

Regla núcleo: aplicar filtros de fecha/autor PRIMERO para acotar el universo
de commits antes de analizar diffs (que es la operación más costosa).

Nunca escribe en el repositorio. Solo lectura.
"""

from typing import Any


def seleccionar_estrategia(params: dict[str, Any]) -> dict[str, Any]:
    """
    Dado un dict de parámetros normalizados (de filters.py), determina:
        - el modo definitivo (s / g / grep / l)
        - el orden de los flags git
        - una descripción legible de la estrategia elegida

    Retorna dict:
        {
          "modo":        str,   # modo final elegido
          "descripcion": str,   # texto legible para logs
          "flags_base":  list,  # flags de fecha/autor a aplicar PRIMERO
          "flags_contenido": list,  # flags de diff/texto a aplicar DESPUÉS
        }
    """
    texto: str = params.get("texto", "").strip()
    modo: str = params.get("modo", "auto")
    autor: str = params.get("autor", "").strip()
    desde: str = params.get("desde", "").strip()
    hasta: str = params.get("hasta", "").strip()
    archivo: str = params.get("archivo", "").strip()
    funcion: str = params.get("funcion", "").strip()
    max_count: int = params.get("max_count", 2000)

    flags_base: list[str] = ["--all"]
    if autor:
        flags_base.append(f"--author={autor}")
    if desde:
        flags_base.append(f"--since={desde}")
    if hasta:
        flags_base.append(f"--until={hasta}")
    flags_base.append(f"--max-count={max_count}")

    if modo == "auto":
        if archivo and (funcion or texto.isdigit()):
            modo = "l"
        elif modo == "auto" and texto:
            REGEX_INDICADORES = (r".*", r".+", r"\d", r"\w", r"[", r"(", r"^", r"|")
            es_regex = any(ind in texto for ind in REGEX_INDICADORES)
            modo = "g" if es_regex else "grep"
        else:
            modo = "grep"

    flags_contenido: list[str] = []
    descripcion: str = ""

    if modo == "s":
        flags_contenido = [f"-S{texto}", "--name-only", "--format=%H"]
        descripcion = f"Pickaxe (-S): busca aparición/desaparición exacta de '{texto}'"

    elif modo == "g":
        flags_contenido = [f"-G{texto}", "--format=%H"]
        descripcion = f"Regex en diff (-G): busca patrón '{texto}' en cambios"

    elif modo == "grep":
        flags_contenido = [f"--grep={texto}", "-i", "--format=%H"]
        descripcion = f"Mensaje de commit (--grep): busca '{texto}' en mensajes"

    elif modo == "l":
        rango = f":{funcion}:{archivo}" if funcion else f"{texto}:{archivo}"
        flags_contenido = [f"-L{rango}", "--format=%H"]
        descripcion = f"Trazabilidad (-L): historia de '{funcion or texto}' en {archivo}"

    return {
        "modo": modo,
        "descripcion": descripcion,
        "flags_base": flags_base,
        "flags_contenido": flags_contenido,
    }
