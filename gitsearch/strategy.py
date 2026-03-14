"""
strategy.py — Selección inteligente del comando Git según los parámetros.

Regla núcleo: aplicar filtros de fecha/autor PRIMERO para acotar el universo
de commits antes de analizar diffs (que es la operación más costosa).

Nunca escribe en el repositorio. Solo lectura.
"""


def seleccionar_estrategia(params: dict) -> dict:
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
    texto   = params.get("texto", "").strip()
    modo    = params.get("modo", "auto")
    autor   = params.get("autor", "").strip()
    desde   = params.get("desde", "").strip()
    hasta   = params.get("hasta", "").strip()
    archivo = params.get("archivo", "").strip()
    funcion = params.get("funcion", "").strip()
    max_count = params.get("max_count", 2000)

    # ── Flags de acotamiento (siempre van primero) ──────────────────────────
    flags_base = ["--all"]
    if autor:
        flags_base.append(f"--author={autor}")
    if desde:
        flags_base.append(f"--since={desde}")
    if hasta:
        flags_base.append(f"--until={hasta}")
    flags_base.append(f"--max-count={max_count}")

    # ── Determinar modo definitivo ───────────────────────────────────────────
    if modo == "auto":
        if archivo and (funcion or texto.isdigit()):
            modo = "l"          # Trazabilidad de función/rango
        elif modo == "auto" and texto:
            # Heurística: si el texto parece un patrón regex, usar -G; si no, -S
            REGEX_INDICADORES = (r".*", r".+", r"\d", r"\w", r"[", r"(", r"^", r"|")
            es_regex = any(ind in texto for ind in REGEX_INDICADORES)
            modo = "g" if es_regex else "grep"
        else:
            modo = "grep"       # Fallback más rápido (solo metadatos)

    # ── Flags de contenido según modo ───────────────────────────────────────
    flags_contenido = []
    descripcion = ""

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
        # Para -L necesitamos el repo directamente (ver engine.py)
        if funcion:
            rango = f":{funcion}:{archivo}"
        else:
            rango = f"{texto}:{archivo}"  # texto = "desde,hasta"
        flags_contenido = [f"-L{rango}", "--format=%H"]
        descripcion = f"Trazabilidad (-L): historia de '{funcion or texto}' en {archivo}"

    return {
        "modo":             modo,
        "descripcion":      descripcion,
        "flags_base":       flags_base,
        "flags_contenido":  flags_contenido,
    }
