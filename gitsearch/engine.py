# -*- coding: utf-8 -*-
"""
engine.py — Motor de consultas Git (solo lectura).

Responsabilidad única: ejecutar el comando git elegido por strategy.py
y retornar la lista de commits encontrados con sus metadatos completos,
incluyendo el commit padre para navegación en el HTML.

Nunca escribe en el repositorio. Nunca envía datos al remoto.
"""

from datetime import datetime
from .filters import validar_y_normalizar, FiltroInvalido
from .strategy import seleccionar_estrategia


def buscar(repo, params: dict, topologia: dict = None) -> dict:
    """
    Busca commits en el repositorio según los parámetros dados.

    Args:
        repo      : objeto Repo de GitPython (ya abierto, solo lectura)
        params    : dict con campos: texto, modo, autor, desde, hasta,
                    archivo, funcion, max_count
        topologia : dict pre-calculado {sha: info} de main.py (opcional,
                    para enriquecer resultados con info de tags)

    Retorna dict con estructura compatible con __GLOBAL_SEARCH__ del HTML:
        {
          "criterio":   str,
          "modo":       str,
          "descripcion": str,
          "total":      int,
          "resultados": [
              {
                "hash":       str (7 chars),
                "full_hash":  str,
                "tipo":       str,
                "mensaje":    str,
                "autor":      str,
                "fecha":      str,
                "tags":       list[str],
                "archivos":   list[str],
                "parents":    list[str],   ← hash corto del padre (para UI)
                "parent_full": list[str],  ← hash completo del padre
                "tag_sha":    str | None,  ← sha del nodo del grafo que contiene este commit
              }
          ]
        }
    """
    # 1. Validar parámetros
    try:
        p = validar_y_normalizar(params)
    except FiltroInvalido as e:
        return {"criterio": params.get("texto", ""), "modo": "error",
                "descripcion": f"Parámetro inválido: {e}", "total": 0, "resultados": []}

    # 2. Elegir estrategia
    estrategia = seleccionar_estrategia(p)
    modo       = estrategia["modo"]
    flags      = estrategia["flags_base"] + estrategia["flags_contenido"]

    print(f"[GitSearch] {estrategia['descripcion']}")

    # 3. Ejecutar comando git (solo lectura)
    shas_encontrados = {}  # sha_completo → tipo_match

    if not p["texto"] and not p["autor"] and not p["desde"] and not p["hasta"]:
        # Sin criterios reales: evitar escanear todo el repositorio
        return {
            "criterio":    "",
            "modo":        modo,
            "descripcion": estrategia["descripcion"],
            "total":       0,
            "resultados":  []
        }

    try:
        raw = repo.git.log(*flags)
        for linea in raw.splitlines():
            linea = linea.strip()
            if linea and len(linea) == 40 and all(c in "0123456789abcdefABCDEF" for c in linea):
                if linea not in shas_encontrados:
                    shas_encontrados[linea] = estrategia["descripcion"]
    except Exception as e:
        print(f"[GitSearch] Error en git log: {e}")

    # 4. Construir mapa commit → tags desde topología (reutiliza la ya calculada)
    commit_to_tags = {}   # hash_corto → [tags]
    commit_to_sha  = {}   # hash_corto → sha_nodo_del_grafo
    if topologia:
        for tag_sha, info in topologia.items():
            nombres = info.get("all_tags", [])
            if nombres:
                commit_to_tags[tag_sha[:7]] = nombres
                commit_to_sha[tag_sha[:7]]  = tag_sha
                for c_meta in info.get("stats", {}).get("commits_list", []):
                    commit_to_tags[c_meta["hash"]] = nombres
                    commit_to_sha[c_meta["hash"]]  = tag_sha

    # 5. Construir lista de resultados enriquecidos
    resultados = []
    for sha, tipo in shas_encontrados.items():
        try:
            c = repo.commit(sha)
            hash_corto = c.hexsha[:7]

            # Tags asociados
            tags_del_commit = commit_to_tags.get(hash_corto) or []
            tag_sha = commit_to_sha.get(hash_corto)
            if not tags_del_commit:
                try:
                    out_tags = repo.git.tag("--contains", c.hexsha).splitlines()
                    tags_del_commit = [t.strip() for t in out_tags if t.strip()]
                except Exception:
                    tags_del_commit = []

            # Archivos modificados
            archivos = []
            try:
                if c.parents:
                    for d in c.parents[0].diff(c):
                        if d.a_path:
                            archivos.append(d.a_path)
                        elif d.b_path:
                            archivos.append(d.b_path)
            except Exception:
                pass

            # Padres (para navegación en el HTML)
            parents_corto = [p.hexsha[:7] for p in c.parents]
            parents_full  = [p.hexsha for p in c.parents]

            resultados.append({
                "hash":        hash_corto,
                "full_hash":   c.hexsha,
                "tipo":        tipo,
                "mensaje":     c.message.splitlines()[0][:100] if c.message else "Sin mensaje",
                "mensaje_full": c.message.strip() if c.message else "",
                "autor":       c.author.name,
                "fecha":       datetime.fromtimestamp(c.committed_date).strftime("%Y-%m-%d %H:%M"),
                "tags":        tags_del_commit,
                "archivos":    sorted(set(archivos)),
                "parents":     parents_corto,
                "parent_full": parents_full,
                "tag_sha":     tag_sha,
            })
        except Exception:
            continue

    resultados.sort(key=lambda x: x["fecha"], reverse=True)

    print(f"[GitSearch] {len(resultados)} coincidencias encontradas con modo '{modo}'.")
    return {
        "criterio":    p["texto"],
        "modo":        modo,
        "descripcion": estrategia["descripcion"],
        "total":       len(resultados),
        "resultados":  resultados,
    }
