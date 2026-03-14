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
                tag_sha_short = tag_sha[:7]
                commit_to_tags[tag_sha_short] = nombres
                commit_to_sha[tag_sha_short] = tag_sha
                commits_list = info.get("stats", {}).get("commits_list", [])
                for c_meta in commits_list:
                    c_hash = c_meta["hash"]
                    commit_to_tags[c_hash] = nombres
                    commit_to_sha[c_hash] = tag_sha

    commit_cache = {}

    from_timestamp = datetime.fromtimestamp
    strftime_fmt = "%Y-%m-%d %H:%M"
    
    resultados = []
    
    for sha, tipo in shas_encontrados.items():
        try:
            c = commit_cache.get(sha)
            if c is None:
                c = repo.commit(sha)
                commit_cache[sha] = c
            
            hash_corto = c.hexsha[:7]
            hexsha = c.hexsha
            autor = c.author.name
            committed_date = c.committed_date
            message = c.message

            tags_del_commit = commit_to_tags.get(hash_corto) or []
            tag_sha = commit_to_sha.get(hash_corto)
            
            if not tags_del_commit:
                cached_tags = commit_to_tags.get(hexsha)
                if cached_tags:
                    tags_del_commit = cached_tags

            archivos = []
            try:
                if c.parents:
                    parents0 = c.parents[0]
                    cached_parent = commit_cache.get(parents0.hexsha)
                    if cached_parent is None:
                        cached_parent = parents0
                        commit_cache[parents0.hexsha] = parents0
                    for d in cached_parent.diff(c):
                        if d.a_path:
                            archivos.append(d.a_path)
                        elif d.b_path:
                            archivos.append(d.b_path)
            except Exception:
                pass

            parents_corto = [p.hexsha[:7] for p in c.parents]
            parents_full  = [p.hexsha for p in c.parents]

            resultados.append({
                "hash":        hash_corto,
                "full_hash":   hexsha,
                "tipo":        tipo,
                "mensaje":     message.splitlines()[0][:100] if message else "Sin mensaje",
                "mensaje_full": message.strip() if message else "",
                "autor":       autor,
                "fecha":       from_timestamp(committed_date).strftime(strftime_fmt),
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
