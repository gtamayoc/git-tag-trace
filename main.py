#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analizador Técnico Offline de Repositorio Git
Uso: python main.py <ruta_repositorio> [--output archivo.md]
"""

import sys
import os
import argparse
import json
from datetime import datetime
from collections import Counter
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from git import Repo, InvalidGitRepositoryError, NoSuchPathError
except ImportError:
    print("[ERROR] GitPython no está instalado. Ejecuta start.bat para configurar el entorno.")
    sys.exit(1)

# ── GitSearch: módulo complementario de búsqueda avanzada (aditivo) ──────────
try:
    from gitsearch.html_builder import generar_panel_busqueda as _gs_generar_panel
    _GITSEARCH_OK = True
except ImportError:
    _GITSEARCH_OK = False
    _gs_generar_panel = None


# ──────────────────────────────────────────────
# SECCIÓN 1 — HISTORIAL
# ──────────────────────────────────────────────

def obtener_historial(repo: Repo) -> dict:
    STASH_PREFIXES = (
        "On ",          # "On main: ..."
        "index on ",    # "index on main: ..."
        "WIP on ",      # "WIP on main: ..."
        "untracked files on ",
    )

    def es_stash(commit) -> bool:
        msg = commit.message.strip().lower()
        return any(msg.startswith(p.lower()) for p in STASH_PREFIXES)

    try:
        # Iterar solo sobre heads y remotes
        refs = list(repo.heads) + list(repo.remotes[0].refs if repo.remotes else [])
        seen = set()
        commits = []
        for ref in refs:
            for c in repo.iter_commits(ref):
                if c.hexsha not in seen and not es_stash(c):
                    seen.add(c.hexsha)
                    commits.append(c)
        commits.sort(key=lambda c: c.committed_date, reverse=True)
    except Exception:
        commits = [c for c in repo.iter_commits() if not es_stash(c)]

    if not commits:
        return {"commits": [], "total": 0, "autores": {}, "fecha_inicio": None, "fecha_fin": None}

    autores = Counter(c.author.name for c in commits)
    fechas = sorted(c.committed_datetime for c in commits)

    print(f"[INFO] Procesando metadatos para {len(commits)} commits...")
    lista = []
    
    git_show = repo.git.show
    from_timestamp = datetime.fromtimestamp
    strftime_fmt = "%Y-%m-%d %H:%M"
    
    for i, c in enumerate(commits):
        msg_lines = c.message.strip().splitlines()
        first_line = msg_lines[0][:80] if msg_lines else "Sin mensaje"
        
        commit_hexsha = c.hexsha
        autor_name = c.author.name
        committed_date = c.committed_date
        parents_hashes = [p.hexsha for p in c.parents]
        
        diff_preview = ""
        try:
            diff_preview = git_show(commit_hexsha, "-p", "--stat", "--no-color", "--format=", max_count=1)
            if len(diff_preview) > 6000:
                diff_preview = diff_preview[:6000] + "\n\n... (diff truncado por tamaño, mostrando primeros 6000 caracteres) ..."
        except:
            diff_preview = "(Error cargando diff)"

        lista.append({
            "hash": commit_hexsha[:7],
            "full_hash": commit_hexsha,
            "autor": autor_name,
            "fecha": from_timestamp(committed_date).strftime(strftime_fmt),
            "mensaje": first_line,
            "mensaje_full": c.message.strip(),
            "parents": parents_hashes,
            "diff": diff_preview
        })

    return {
        "commits": lista,
        "total": len(commits),
        "autores": dict(autores.most_common()),
        "fecha_inicio": fechas[0].strftime("%Y-%m-%d"),
        "fecha_fin": fechas[-1].strftime("%Y-%m-%d"),
    }


# ──────────────────────────────────────────────
# SECCIÓN 2 — TAGS Y VERSIONADO
# ──────────────────────────────────────────────

def obtener_tags(repo: Repo) -> list:
    """Obtiene todos los tags del repositorio con su metadata."""
    tags = []
    for tag in repo.tags:
        try:
            # Formato ISO para ordenamiento interno
            fecha_iso = ""
            if tag.tag:  # tag anotado
                commit = tag.tag.object
                fecha = datetime.fromtimestamp(tag.tag.tagged_date).strftime("%Y-%m-%d")
                fecha_iso = datetime.fromtimestamp(tag.tag.tagged_date).strftime("%Y-%m-%d %H:%M:%S")
                autor = tag.tag.tagger.name
            else:  # tag ligero
                commit = tag.commit
                fecha = datetime.fromtimestamp(commit.committed_date).strftime("%Y-%m-%d")
                fecha_iso = datetime.fromtimestamp(commit.committed_date).strftime("%Y-%m-%d %H:%M:%S")
                autor = commit.author.name

            tags.append({
                "nombre": tag.name,
                "fecha": fecha,
                "fecha_iso": fecha_iso,
                "autor": autor,
                "hash": commit.hexsha[:7] if hasattr(commit, 'hexsha') else "N/A",
                "hash_completo": commit.hexsha if hasattr(commit, 'hexsha') else "N/A",
                "es_semver": tag.name.startswith("v") and tag.name[1:2].isdigit(),
            })
        except Exception:
            tags.append({
                "nombre": tag.name,
                "fecha": "N/A",
                "fecha_iso": "",
                "autor": "N/A",
                "hash": "N/A",
                "hash_completo": "N/A",
                "es_semver": False,
            })

    return sorted(tags, key=lambda t: t["fecha_iso"] if t["fecha_iso"] else t["fecha"])


# ──────────────────────────────────────────────
# SECCIÓN 3 — ANÁLISIS TOPOLÓGICO DEL GRAFO GIT
# ──────────────────────────────────────────────

def comparar_tags(repo: Repo, tags: list) -> Optional[dict]:
    """Compara los dos últimos tags (topológicamente) y retorna diferencias."""
    if len(tags) < 2:
        return None

    tag_anterior = tags[-2]["nombre"]
    tag_actual   = tags[-1]["nombre"]

    try:
        c_actual   = repo.commit(tags[-1]["hash_completo"])
        c_anterior = repo.commit(tags[-2]["hash_completo"])
        bases      = repo.merge_base(c_anterior, c_actual)
        base       = bases[0] if bases else c_anterior

        # Commits exclusivos de tag_actual respecto al punto de divergencia
        commits_entre = list(repo.iter_commits(f"{base.hexsha}..{c_actual.hexsha}", max_count=5000))
        autores = list({c.author.name for c in commits_entre})

        archivos_modificados = set()
        try:
            diff = base.diff(c_actual)
            for d in diff:
                if d.a_path: archivos_modificados.add(d.a_path)
                if d.b_path: archivos_modificados.add(d.b_path)
        except Exception:
            pass

        lista_commits = [
            {
                "hash":    c.hexsha[:7],
                "autor":   c.author.name,
                "fecha":   datetime.fromtimestamp(c.committed_date).strftime("%Y-%m-%d %H:%M"),
                "mensaje": c.message.strip().splitlines()[0][:80],
            }
            for c in commits_entre
        ]

        return {
            "tag_anterior": tag_anterior,
            "tag_actual":   tag_actual,
            "total_commits":      len(commits_entre),
            "autores":            autores,
            "archivos_modificados": sorted(archivos_modificados),
            "total_archivos":     len(archivos_modificados),
            "commits":            lista_commits,
        }

    except Exception as e:
        return {"error": str(e)}


# ── 3a. Construcción del mapa completo de commits (DAG) ──────────────────────

def construir_mapa_commits(repo: Repo) -> dict:
    """
    Recorre ALL refs (branches locales, remotas, tags) y construye un dict
    {hexsha_completo: commit_obj} con todos los commits accesibles del repo.
    Excluye refs de stash para no contaminar el grafo.
    """
    STASH_PREFIXES = ("refs/stash", "stash@")
    seen = {}

    def _walk(ref_commit):
        stack = [ref_commit]
        while stack:
            c = stack.pop()
            if c.hexsha in seen:
                continue
            seen[c.hexsha] = c
            stack.extend(c.parents)

    # Branches locales
    for head in repo.heads:
        try:
            _walk(head.commit)
        except Exception:
            pass

    # Branches remotas
    for remote in repo.remotes:
        for ref in remote.refs:
            if any(ref.name.startswith(p) for p in STASH_PREFIXES):
                continue
            try:
                _walk(ref.commit)
            except Exception:
                pass

    # Tags (por si algún commit de tag no está en ninguna rama)
    for tag in repo.tags:
        try:
            _walk(tag.commit)
        except Exception:
            pass

    return seen


# ── 3b. Identificar ramas que contienen cada tag ─────────────────────────────

def identificar_ramas_de_tag(repo: Repo, commit_sha: str, sha_a_ramas: dict = None) -> list:
    """
    Devuelve lista de nombres de ramas en las que el commit del tag está presente.
    Si se pasa sha_a_ramas (un dict pre-calculado sha→[ramas]), se usa ese;
    de lo contrario recurre al git branch --contains (más lento).
    """
    if sha_a_ramas is not None:
        return sorted(sha_a_ramas.get(commit_sha, []))

    # Fallback individual (solo cuando no se pasa el dict pre-calculado)
    ramas = []
    try:
        resultado = repo.git.branch("-a", "--contains", commit_sha)
        for linea in resultado.splitlines():
            nombre = linea.strip().lstrip("* ").strip()
            if nombre and "HEAD detached" not in nombre:
                if nombre.startswith("remotes/"):
                    nombre = nombre[len("remotes/"):]
                ramas.append(nombre)
    except Exception:
        pass
    return sorted(set(ramas))


def _construir_sha_a_ramas(repo: Repo) -> dict:
    """
    Construye un dict {sha: [rama1, rama2, ...]} en UNA SOLA llamada git.
    Lee git log --decorate=full para extraer ref-names de cada commit.
    """
    raw = repo.git.log("--all", "--pretty=format:%H %D")
    sha_a_ramas_direct: dict = {}  # sha → ramas directas (HEAD commits)

    for line in raw.splitlines():
        if not line.strip():
            continue
        idx_sep = line.index(" ") if " " in line else -1
        if idx_sep < 0:
            continue
        sha  = line[:idx_sep].strip()
        deco = line[idx_sep + 1:].strip()
        if not deco:
            continue
        ramas = []
        for parte in deco.split(","):
            parte = parte.strip()
            if parte.startswith("HEAD ->"):
                rama = parte[len("HEAD ->"):].strip()
                if rama:
                    ramas.append(rama)
            elif parte.startswith("refs/heads/"):
                ramas.append(parte[len("refs/heads/"):])
            elif parte.startswith("refs/remotes/"):
                ramas.append(parte[len("refs/remotes/"):])
            elif "/" in parte and not parte.startswith("tag:"):
                ramas.append(parte)
        if ramas:
            sha_a_ramas_direct[sha] = ramas

    return sha_a_ramas_direct


# ── 3c. Commits exclusivos por tag (usando merge_base) ───────────────────────

def calcular_commits_exclusivos_tag(
    repo: Repo,
    commit_tag: object,
    commit_padre_tag: object,
) -> dict:
    """
    Calcula los commits que están en commit_tag pero NO en commit_padre_tag,
    usando merge_base para encontrar el punto de divergencia exacto.
    Esto funciona correctamente con ramas paralelas y merges.
    """
    from_timestamp = datetime.fromtimestamp
    strftime_fmt = "%Y-%m-%d %H:%M"
    
    try:
        bases = repo.merge_base(commit_padre_tag, commit_tag)
        base  = bases[0] if bases else commit_padre_tag

        commits = list(repo.iter_commits(
            f"{base.hexsha}..{commit_tag.hexsha}", max_count=5000
        ))

        commits_data = []
        autores_set = set()
        archivos_set = set()
        
        for c in commits:
            autores_set.add(c.author.name)
            message = c.message
            commits_data.append({
                "hash":    c.hexsha[:7],
                "full_hash": c.hexsha,
                "autor":   c.author.name,
                "mensaje": message.strip().splitlines()[0][:80] if message else "",
                "mensaje_full": message.strip() if message else "",
                "fecha":   from_timestamp(c.committed_date).strftime(strftime_fmt),
                "parents": [p.hexsha[:7] for p in c.parents]
            })

        try:
            diff = base.diff(commit_tag)
            for d in diff:
                if d.a_path: archivos_set.add(d.a_path)
                elif d.b_path: archivos_set.add(d.b_path)
        except Exception:
            pass

        dias = 0
        try:
            delta = (
                from_timestamp(commit_tag.committed_date)
                - from_timestamp(base.committed_date)
            )
            dias = delta.days
        except Exception:
            pass

        return {
            "num_commits":  len(commits),
            "autores":      sorted(autores_set),
            "num_archivos": len(archivos_set),
            "archivos":     sorted(archivos_set),
            "commits_list": commits_data,
            "dias":          dias,
            "merge_base_sha": base.hexsha[:7],
        }

    except Exception as e:
        print(f"[DEBUG] Error en calcular_commits_exclusivos_tag: {e}")
        return {
            "num_commits":   0,
            "autores":       [],
            "num_archivos":  0,
            "archivos":      [],
            "commits_list": [],
            "dias":          0,
            "merge_base_sha": "N/A",
        }


# ── 3d. Análisis topológico: aristas reales entre tags ───────────────────────

def analizar_topologia_tags(repo: Repo, tags: list) -> dict:
    """
    Determina los ancestros directos (padres de tag) en el DAG real usando
    un recorrido topológico único. Agrupa tags asociados al mismo commit.
    """
    if not tags:
        return {}

    print("[INFO] Resolviendo commits de tags...")
    sha_a_tags_list = {}
    tag_to_obj = {}

    for t in tags:
        sha = t.get("hash_completo", "N/A")
        if sha == "N/A":
            continue
        sha_a_tags_list.setdefault(sha, []).append(t["nombre"])
        if t["nombre"] not in tag_to_obj:
            try:
                tag_to_obj[t["nombre"]] = repo.commit(sha)
            except Exception:
                pass

    if not sha_a_tags_list:
        return {}

    print(f"[INFO] {len(tags)} tags en {len(sha_a_tags_list)} commits únicos. Leyendo grafo...")

    # ── Lectura del grafo + decoraciones en DOS llamadas git totales ──────────
    raw = repo.git.log(
        "--all",
        "--topo-order",
        "--pretty=format:%H %P",
    )

    parent_map = {}
    topo_order = []
    for line in raw.splitlines():
        parts = line.split()
        if not parts:
            continue
        sha  = parts[0]
        pars = parts[1:]
        parent_map[sha] = pars
        topo_order.append(sha)

    print("[INFO] Construyendo mapa sha -> ramas...")
    sha_a_ramas_direct = _construir_sha_a_ramas(repo)

    sha_al_rama_activo: dict = {}
    for sha in reversed(topo_order):
        ramas_aqui = set(sha_a_ramas_direct.get(sha, []))
        sha_al_rama_activo.setdefault(sha, set()).update(ramas_aqui)
        for p_sha in parent_map.get(sha, []):
            sha_al_rama_activo.setdefault(p_sha, set()).update(
                sha_al_rama_activo.get(sha, set())
            )

    sha_a_ramas_completo = {
        sha: sorted(ramas)
        for sha, ramas in sha_al_rama_activo.items()
    }

    commit_cache = {}
    def get_commit_cached(sha: str):
        if sha not in commit_cache:
            commit_cache[sha] = repo.commit(sha)
        return commit_cache[sha]

    def es_ancestro_rapido(sha_a: str, sha_b: str) -> bool:
        try:
            repo.git.merge_base("--is-ancestor", sha_a, sha_b)
            return True
        except Exception:
            return False

    resultado = {}
    for sha, tnames in sha_a_tags_list.items():
        rep_tag = tnames[0]
        commit = tag_to_obj.get(rep_tag)
        if not commit: continue
        resultado[sha] = {
            "all_tags":    tnames,
            "commit":      commit,
            "padres_shas": [],
            "ramas":       identificar_ramas_de_tag(repo, sha, sha_a_ramas_completo),
            "stats":       {}
        }

    tags_vistos_en_commit: dict[str, set] = {}

    for sha in reversed(topo_order):
        tags_heredados = set()
        parents = parent_map.get(sha)
        if parents:
            for p_sha in parents:
                tags_heredados.update(tags_vistos_en_commit.get(p_sha, set()))

        if sha in sha_a_tags_list:
            candidatos = list(tags_heredados)
            padres_directos = []
            num_candidatos = len(candidatos)
            
            if num_candidatos == 1:
                padres_directos = candidatos
            elif num_candidatos > 1:
                for cand_sha in candidatos:
                    es_superado = any(
                        otro_sha != cand_sha
                        and es_ancestro_rapido(cand_sha, otro_sha)
                        for otro_sha in candidatos
                    )
                    if not es_superado:
                        padres_directos.append(cand_sha)

            resultado[sha]["padres_shas"] = padres_directos

            tags_vistos_en_commit[sha] = {sha}

            if padres_directos:
                padre_commit = get_commit_cached(padres_directos[0])
                stats = calcular_commits_exclusivos_tag(repo, resultado[sha]["commit"], padre_commit)
            else:
                stats = {
                    "num_commits":   0, "autores":       [], "num_archivos":  0,
                    "archivos":      [], "commits_list": [], "dias":           0,
                    "merge_base_sha": "(raíz)",
                }
            resultado[sha]["stats"] = stats
        else:
            tags_vistos_en_commit[sha] = tags_heredados

    aristas = sum(len(v["padres_shas"]) for v in resultado.values())
    print(f"[INFO] Topología completa: {aristas} aristas entre {len(resultado)} nodos de versión.")
    return resultado



def generar_grafo_html(repo: Repo, tags: list, topologia: dict = None, historial: dict = None, busqueda: dict = None) -> str:
    """Genera un archivo HTML con un grafo interactivo de los tags y un explorador de commits."""
    if not tags:
        return "<html><body style='font-family:sans-serif; padding:50px;'><h1>No se encontraron tags</h1><p>El repositorio requiere al menos un tag para generar el grafo.</p></body></html>"

    nodes = []
    edges = []

    # Agrupar tags por SHA
    tags_by_sha = {}
    for t in tags:
        sha = t.get("hash_completo", "N/A")
        if sha == "N/A": continue
        tags_by_sha.setdefault(sha, []).append(t)

    shas_ordenados = sorted(tags_by_sha.keys(), key=lambda s: tags_by_sha[s][0].get("fecha_iso") or "")

    # Agrega aquí los prefijos de tus tags que quieras recortar del label visual.
    # Ejemplo: ["mi_proyecto_prod_", "release_"] → "mi_proyecto_prod_v1.2" → "v1.2"
    env_prefixes = os.getenv("TAG_PREFIXES", "")
    PREFIJOS_LIMPIAR: list[str] = [p.strip() for p in env_prefixes.split(",") if p.strip()]

    def limpiar_label(nombre):
        for pfx in PREFIJOS_LIMPIAR:
            if nombre.startswith(pfx): return nombre[len(pfx):]
        return nombre

    RAMAS_PRINCIPALES = {"main", "master", "develop", "trunk"}

    def es_rama_principal(ramas: list) -> bool:
        for r in ramas:
            n = r.split("/")[-1].lower()
            if n in RAMAS_PRINCIPALES: return True
        return False

    # Mapeo de commits a tags (para la búsqueda)
    commit_to_tag = {}

    for i, sha in enumerate(shas_ordenados):
        tags_en_sha = tags_by_sha[sha]
        rep_tag = tags_en_sha[0]
        
        topo_info = topologia.get(sha, {}) if topologia else {}
        ramas     = topo_info.get("ramas", [])
        stats     = topo_info.get("stats", {})
        padres    = topo_info.get("padres_shas", [])
        es_main   = es_rama_principal(ramas)

        # Mapear todos los commits exclusivos de este tag a este nodo
        for c_meta in stats.get("commits_list", []):
            commit_to_tag[c_meta["hash"]] = sha
            # También para full hashes si están disponibles
            if "full_hash" in c_meta:
                 commit_to_tag[c_meta["full_hash"]] = sha

        label_name = ", ".join([limpiar_label(t["nombre"]) for t in tags_en_sha])
        if len(tags_en_sha) > 2:
            label_name = f"{limpiar_label(tags_en_sha[0]['nombre'])} (+{len(tags_en_sha)-1})"

        title_txt = f"Tags: {', '.join(t['nombre'] for t in tags_en_sha)}\nFecha: {rep_tag['fecha']}\nAutor: {rep_tag['autor']}\nHash: {rep_tag['hash']}"

        nodes.append({
            "id":          sha,
            "label":       label_name,
            "title":       title_txt,
            "all_tags":    tags_en_sha,
            "author":      rep_tag["autor"],
            "date":        rep_tag["fecha"],
            "hash":        rep_tag["hash"],
            "full_hash":   sha,
            "is_main":     es_main,
            "ramas":       ramas,
            "stats":       stats,
            "value":       i + 1,
        })

        if topologia:
            for padre_sha in padres:
                n_exc = stats.get("num_commits", 0)
                n_arch = stats.get("num_archivos", 0)
                edge_label = ""
                if n_exc > 0:
                     edge_label = f"{n_exc} cmts" + (f" • {n_arch} files" if n_arch else "")
                     
                edges.append({
                    "id": f"{padre_sha}_{sha}",
                    "from": padre_sha, "to": sha, "arrows": "to",
                    "label": edge_label,
                    "is_parallel": not es_main,
                    "n_archivos": n_arch,
                    "n_commits": n_exc
                })
        elif i > 0:
            edges.append({
                "id": f"{shas_ordenados[i-1]}_{sha}",
                "from": shas_ordenados[i-1], "to": sha, "arrows": "to", "is_parallel": False
            })

    html_template = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitSearch — Git Version Traceability Explorer</title>
    <meta name="description" content="Explorador interactivo de historial y versiones de repositorios Git. Análisis topológico de tags y búsqueda avanzada de commits.">
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        /* ═══════════════════════════════════════════════════════════
           GitSearch UI — Theming System & Styling
           ═══════════════════════════════════════════════════════════ */
        :root, .gs-theme-dark {
            /* Modo Oscuro Balanceado (No negro absoluto) */
            --bg-color:        #181a1f;
            --bg-surface:      #21242b;
            --bg-raised:       #292d36;
            --bg-hover:        #323742;
            --panel-bg:        rgba(33, 36, 43, 0.96);
            --panel-border:    rgba(255, 255, 255, 0.08);

            --text-primary:    #e4e6eb;
            --text-secondary:  #a0a4ab;
            --text-muted:      #7a7e85;

            --accent-primary:  #d0d0d0;
            --accent-dim:      #60646b;
            --accent-active:   #ffffff;

            --border-subtle:   rgba(255, 255, 255, 0.08);
            --border-normal:   rgba(255, 255, 255, 0.12);
            --border-strong:   rgba(255, 255, 255, 0.20);

            --diff-added:      #4a9960;
            --diff-removed:    #b55050;

            --shadow-panel:    0 8px 40px rgba(0, 0, 0, 0.5);
            --shadow-modal:    0 20px 80px rgba(0, 0, 0, 0.7);
            --panel-width:     500px;

            --radius-sm:  4px;
            --radius-md:  8px;
            --radius-lg:  12px;

            --transition-fast: 0.15s ease;
            --transition-med:  0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .gs-theme-light {
            /* Modo Claro Cálido (Blanco hueso/suave) */
            --bg-color:        #f4f2ee;
            --bg-surface:      #e9e6e0;
            --bg-raised:       #dfdbd4;
            --bg-hover:        #d4cfc7;
            --panel-bg:        rgba(233, 230, 224, 0.96);
            --panel-border:    rgba(0, 0, 0, 0.12);

            --text-primary:    #1a1a1a;
            --text-secondary:  #4a4a4a;
            --text-muted:      #666666;

            --accent-primary:  #333333;
            --accent-dim:      #aaaaaa;
            --accent-active:   #000000;

            --border-subtle:   rgba(0, 0, 0, 0.08);
            --border-normal:   rgba(0, 0, 0, 0.14);
            --border-strong:   rgba(0, 0, 0, 0.25);

            --diff-added:      #2e7a43;
            --diff-removed:    #a83232;

            --shadow-panel:    0 12px 30px rgba(0, 0, 0, 0.15);
            --shadow-modal:    0 20px 60px rgba(0, 0, 0, 0.25);
        }

        /* ── Reset y base ── */
        *, *::before, *::after { box-sizing: border-box; }

        body, html {
            margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden;
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 14px;
            -webkit-font-smoothing: antialiased;
        }

        #mynetwork { width: 100%; height: 100%; }

        /* ── Barra superior — branding GitSearch ── */
        /* [VISUAL ONLY] Topbar de identidad del proyecto */
        #gs-topbar {
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 48px;
            background: rgba(10, 10, 10, 0.92);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            padding: 0 20px;
            z-index: 50;
            gap: 12px;
        }
        #gs-topbar .gs-brand {
            font-size: 0.88rem;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: -0.02em;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        #gs-topbar .gs-brand-dot {
            width: 7px; height: 7px;
            border-radius: 50%;
            background: var(--text-primary);
        }
        #gs-topbar .gs-separator {
            width: 1px; height: 18px;
            background: var(--border-normal);
        }
        #gs-topbar .gs-subtitle {
            font-size: 0.75rem;
            color: var(--text-muted);
            font-weight: 400;
        }

        /* ── Contenedor principal — offset por topbar ── */
        #mynetwork { padding-top: 48px; }

        /* ── Panel de búsqueda dentro del side-panel ── */
        .search-area {
            background: var(--bg-raised);
            padding: 12px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border-normal);
            margin-bottom: 16px;
            display: flex;
            gap: 8px;
        }
        .search-area input {
            flex: 1;
            background: var(--bg-surface);
            border: 1px solid var(--border-normal);
            color: var(--text-primary);
            padding: 8px 12px;
            border-radius: var(--radius-sm);
            font-size: 0.82rem;
            outline: none;
            font-family: inherit;
            transition: border-color var(--transition-fast);
        }
        .search-area input:focus { border-color: var(--border-strong); }
        .search-area input::placeholder { color: var(--text-muted); }
        .search-area button {
            background: var(--bg-hover);
            border: 1px solid var(--border-normal);
            color: var(--text-primary);
            padding: 7px 14px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            font-size: 0.78rem;
            font-weight: 600;
            font-family: inherit;
            transition: background var(--transition-fast), border-color var(--transition-fast);
        }
        .search-area button:hover {
            background: #2a2a2a;
            border-color: var(--border-strong);
        }

        /* ── Side Panel ── */
        .side-panel {
            position: absolute;
            top: 48px; /* offset topbar */
            right: 0;
            width: var(--panel-width);
            height: calc(100% - 48px);
            background: var(--panel-bg);
            backdrop-filter: blur(24px);
            border-left: 1px solid var(--panel-border);
            box-shadow: var(--shadow-panel);
            z-index: 1000;
            transform: translateX(100%);
            transition: transform var(--transition-med);
            display: flex;
            flex-direction: column;
        }
        .side-panel.open { transform: translateX(0); }

        /* ── Panel Header ── */
        .panel-header {
            padding: 20px 28px 16px;
            border-bottom: 1px solid var(--border-subtle);
            position: relative;
            flex-shrink: 0;
        }
        .close-btn {
            position: absolute;
            top: 20px; right: 20px;
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 20px;
            cursor: pointer;
            line-height: 1;
            padding: 4px 6px;
            border-radius: var(--radius-sm);
            transition: color var(--transition-fast), background var(--transition-fast);
        }
        .close-btn:hover { color: var(--text-primary); background: var(--bg-raised); }

        /* ── Panel Nav (tabs) ── */
        .panel-nav {
            display: flex;
            border-bottom: 1px solid var(--border-subtle);
            flex-shrink: 0;
        }
        .nav-item {
            flex: 1;
            padding: 11px 8px;
            text-align: center;
            cursor: pointer;
            color: var(--text-muted);
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            transition: color var(--transition-fast), border-color var(--transition-fast);
            border-bottom: 2px solid transparent;
            user-select: none;
        }
        .nav-item:hover { color: var(--text-secondary); }
        .nav-item.active {
            color: var(--text-primary);
            border-bottom-color: var(--text-primary);
        }

        /* ── Panel Content ── */
        .panel-content {
            flex: 1;
            overflow-y: auto;
            padding: 20px 28px;
            scrollbar-width: thin;
            scrollbar-color: #333 transparent;
        }
        .panel-content::-webkit-scrollbar { width: 4px; }
        .panel-content::-webkit-scrollbar-track { background: transparent; }
        .panel-content::-webkit-scrollbar-thumb { background: #333; border-radius: 2px; }

        /* ── Section titles ── */
        .section-title {
            font-size: 0.68rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin: 20px 0 10px 0;
        }

        /* ── Commit Explorer List ── */
        .commit-explorer-list { display: flex; flex-direction: column; gap: 2px; }
        .ce-item {
            padding: 9px 12px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            transition: background var(--transition-fast);
            border: 1px solid transparent;
            display: grid;
            grid-template-columns: 72px 1fr;
            gap: 12px;
            align-items: start;
        }
        .ce-item:hover { background: var(--bg-raised); }
        .ce-item.active {
            background: var(--bg-raised);
            border-color: var(--border-normal);
        }
        .ce-hash {
            font-family: 'JetBrains Mono', 'Courier New', monospace;
            font-size: 0.72rem;
            color: var(--text-secondary);
            font-weight: 500;
            padding-top: 1px;
        }
        .ce-msg {
            font-size: 0.82rem;
            color: var(--text-primary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .ce-meta {
            font-size: 0.68rem;
            color: var(--text-muted);
            margin-top: 3px;
        }

        /* ── Diff ── */
        .diff-container {
            font-family: 'JetBrains Mono', 'Courier New', monospace;
            font-size: 0.73rem;
            background: var(--bg-color);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            margin-top: 12px;
            white-space: pre-wrap;
            word-break: break-all;
            overflow-x: auto;
            padding: 12px 0;
            color: #aaaaaa;
            line-height: 1.5;
        }
        .diff-added  { color: var(--diff-added);   background: rgba(74, 153, 96, 0.08); display: block; }
        .diff-removed{ color: var(--diff-removed); background: rgba(181, 80, 80, 0.08); display: block; }
        .diff-info   { color: var(--text-muted); }

        /* ── Intro Panel (leyenda del grafo) ── */
        .intro-panel {
            position: absolute;
            top: 68px; /* topbar + gap */
            left: 20px;
            width: 220px;
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-lg);
            padding: 16px 18px;
            z-index: 100;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        }

        /* ── Tag Badge ── */
        .tag-badge {
            display: inline-block;
            padding: 2px 7px;
            border-radius: var(--radius-sm);
            background: var(--bg-raised);
            border: 1px solid var(--border-normal);
            color: var(--text-secondary);
            font-size: 0.68rem;
            font-weight: 600;
            margin-left: 8px;
            font-family: 'JetBrains Mono', monospace;
        }

        /* ── Controls (zoom) ── */
        .controls {
            position: absolute;
            bottom: 20px;
            left: 20px;
            display: flex;
            gap: 6px;
            z-index: 100;
        }
        .btn-round {
            width: 36px; height: 36px;
            border-radius: var(--radius-md);
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            color: var(--text-secondary);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            transition: background var(--transition-fast), color var(--transition-fast);
            line-height: 1;
        }
        .btn-round:hover {
            background: var(--bg-raised);
            color: var(--text-primary);
            border-color: var(--border-strong);
        }

        /* ── Hash code ── */
        .hash-code {
            font-family: 'JetBrains Mono', monospace;
            background: var(--bg-raised);
            padding: 3px 8px;
            border-radius: var(--radius-sm);
            font-size: 0.78rem;
            border: 1px solid var(--border-normal);
            color: var(--text-secondary);
        }

        /* ── Modal Commit Detail ── */
        .modal-overlay {
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(6px);
            z-index: 2000;
            display: none;
            align-items: center;
            justify-content: center;
        }
        .modal-content {
            background: var(--bg-surface);
            width: 85%;
            max-width: 960px;
            height: 82%;
            border-radius: var(--radius-lg);
            border: 1px solid var(--border-normal);
            display: flex;
            flex-direction: column;
            box-shadow: var(--shadow-modal);
            font-family: 'Inter', sans-serif;
            animation: modalFadeIn 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        @keyframes modalFadeIn {
            from { opacity: 0; transform: scale(0.97) translateY(8px); }
            to   { opacity: 1; transform: scale(1)    translateY(0); }
        }
        .modal-header {
            padding: 18px 24px;
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-shrink: 0;
        }
        .modal-body {
            padding: 20px 24px;
            overflow-y: auto;
            flex: 1;
            background: var(--bg-color);
            scrollbar-width: thin;
            scrollbar-color: #2a2a2a transparent;
            border-bottom-left-radius: var(--radius-lg);
            border-bottom-right-radius: var(--radius-lg);
        }

        /* ── Copy icon ── */
        .copy-icon {
            cursor: pointer;
            opacity: 0.6;
            transition: opacity var(--transition-fast), background var(--transition-fast);
            vertical-align: middle;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px; height: 22px;
            border-radius: var(--radius-sm);
            background: var(--bg-raised);
            border: 1px solid var(--border-normal);
            margin-left: 6px;
            color: var(--text-muted);
        }
        .copy-icon:hover { opacity: 1; background: var(--bg-hover); color: var(--text-primary); }
        .copy-icon svg { width: 12px; height: 12px; fill: currentColor; }
    </style>
</head>
<body>
    <!-- Barra superior GitSearch [VISUAL ONLY] -->
    <div id="gs-topbar">
        <div class="gs-brand">
            <div class="gs-brand-dot"></div>
            GitSearch
        </div>
        <div class="gs-separator"></div>
        <div class="gs-subtitle">Git Version Traceability Explorer</div>
    </div>

    <div id="mynetwork"></div>

    <!-- Panel de leyenda del grafo [VISUAL ONLY] -->
    <div class="intro-panel">
        <h2 style="margin:0 0 4px; font-size:0.88rem; font-weight:600; color:var(--text-primary);">Mapa de Versiones</h2>
        <div style="font-size:0.72rem; color:var(--text-muted); margin-bottom:14px;">Historial de tags y commits</div>
        <div style="font-size:0.72rem; color:var(--text-secondary);">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:7px;">
                <div style="width:8px; height:8px; border-radius:50%; background:#e0e0e0; flex-shrink:0;"></div>
                Rama Principal
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <div style="width:8px; height:8px; border-radius:50%; background:#666666; flex-shrink:0;"></div>
                Rama Lateral
            </div>
        </div>
    </div>

    <div class="side-panel" id="side-panel">
        <div class="panel-header">
            <button class="close-btn" onclick="closePanel()">&times;</button>
            <div id="panel-title-primary" style="font-weight:700; font-size:1.1rem;">Detalles del Nodo</div>
            <div id="panel-subtitle" style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px;">Metadatos del historial</div>
        </div>

        <div class="panel-nav">
            <div class="nav-item active" onclick="setPanelTab('info')" id="nav-info">Información</div>
            <div class="nav-item" onclick="setPanelTab('history')" id="nav-history">Historial Nodo</div>
            <div class="nav-item" onclick="setPanelTab('search')" id="nav-search" style="display: none;">Búsqueda Global</div>
        </div>
        
        <div class="panel-content" id="panel-content">
            <!-- Content will be injected here -->
        </div>
    </div>

    <div class="controls">
        <button class="btn-round" onclick="network.moveTo({scale: network.getScale()*1.5, animation:true})">+</button>
        <button class="btn-round" onclick="network.moveTo({scale: network.getScale()/1.5, animation:true})">-</button>
        <button class="btn-round" onclick="network.fit({animation:true})">⛶</button>
        <button class="btn-round" id="btn-lock" onclick="toggleNodeLock()" title="Alternar Modo de Layout" style="font-size: 0.75rem; width: auto; padding: 0 10px; font-weight: 500;">🧊 Fijo</button>
        <button class="btn-round" onclick="toggleTheme()" title="Cambiar Tema (Claro / Oscuro)">🌓</button>
    </div>

    <!-- Modal Commit Detail -->
    <div id="commit-modal" class="modal-overlay" onclick="if(event.target===this) hideCommitModal()">
        <div class="modal-content">
            <div class="modal-header">
                <div style="flex:1;">
                    <!-- [VISUAL] modal-title color monocromático -->
                    <h2 id="modal-title" style="margin:0; font-size:1.1rem; font-weight:600; color:var(--text-primary); margin-bottom:8px; line-height:1.4;"></h2>
                    <div id="modal-meta" style="color:var(--text-secondary); font-size:0.82rem;"></div>
                </div>
                <button class="close-btn" style="position:static; margin-left:16px; font-size:24px;" onclick="hideCommitModal()">&times;</button>
            </div>
            <div class="modal-body">
                <!-- [VISUAL] info cards monocromáticas -->
                <div style="display:flex; gap:24px; margin-bottom:20px; flex-wrap:wrap; background:var(--bg-raised); padding:14px 16px; border-radius:8px; border:1px solid var(--border-subtle);">
                    <div>
                        <div class="section-title" style="margin-top:0;">Identificador (SHA)</div>
                        <div id="modal-hash-container" style="display:flex; align-items:center;"></div>
                    </div>
                    <div>
                        <div class="section-title" style="margin-top:0;">Padres</div>
                        <div id="modal-parents-container" style="display:flex; align-items:center; gap:8px;"></div>
                    </div>
                </div>
                <div class="section-title" style="margin-bottom:10px;">Archivos Modificados y Cambios Reales (Diff)</div>
                <div id="modal-diff" class="diff-container" style="margin-top:0;"></div>
            </div>
        </div>
    </div>

    <script type="text/javascript">
        const nodesData = __NODES_DATA__;
        const edgesData = __EDGES_DATA__;
        const historyData = __HISTORY_DATA__;
        const commitToTag = __COMMIT_MAP__;
        const globalSearchData = __GLOBAL_SEARCH__;

        let currentTab = 'info';
        let selectedNode = null;   // Nodo del grafo seleccionado
        let selectedCommit = null; // Commit específico visualizado
        let lastHighlightedNode = null;

        const container = document.getElementById('mynetwork');
        let savedPositions = {};
        try { savedPositions = JSON.parse(localStorage.getItem('gitsearch_positions')) || {}; } catch(e){}
        let nodesLocked = localStorage.getItem('gitsearch_locked') === 'true';

        const THEMES_CONFIG = {
            dark: { mainBg: '#e4e6eb', mainBorder: '#ffffff', sideBg: '#60646b', sideBorder: '#9aa0a6', edge: '#4a4d54', edgeHi: '#888d96', font: '#e4e6eb' },
            light: { mainBg: '#21242b', mainBorder: '#000000', sideBg: '#b1b6bd', sideBorder: '#8a8f96', edge: '#a8adb5', edgeHi: '#60646b', font: '#21242b' }
        };
        let currentTheme = localStorage.getItem('gs_theme') || 'dark';

        // Apply theme initially
        if (currentTheme === 'light') document.documentElement.classList.add('gs-theme-light');

        function toggleTheme() {
            currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
            localStorage.setItem('gs_theme', currentTheme);
            if (currentTheme === 'light') {
                document.documentElement.classList.add('gs-theme-light');
                document.documentElement.classList.remove('gs-theme-dark');
            } else {
                document.documentElement.classList.add('gs-theme-dark');
                document.documentElement.classList.remove('gs-theme-light');
            }
            updateNetworkColors();
        }

        // Apply visual differentiation for changes without overloading
        function getEdgeWidth(nCommits) {
            return 1.0 + Math.min((nCommits || 0) * 0.1, 3.5);
        }

        const nodes = new vis.DataSet(nodesData.map(n => {
            const pos = savedPositions[n.id];
            const t = THEMES_CONFIG[currentTheme];
            return {
                ...n, shape: 'dot', size: 13, borderWidth: 2,
                color: { background: n.is_main ? t.mainBg : t.sideBg, border: n.is_main ? t.mainBorder : t.sideBorder, highlight: { background: t.mainBorder, border: t.mainBorder } },
                font: { color: t.font, face: 'Inter', size: 12 },
                x: pos ? pos.x : undefined,
                y: pos ? pos.y : undefined
            };
        }));
        
        const edges = new vis.DataSet(edgesData.map(e => {
            const t = THEMES_CONFIG[currentTheme];
            return {
                ...e, color: { color: t.edge, highlight: t.edgeHi },
                dashes: e.is_parallel ? [4, 4] : false, width: getEdgeWidth(e.n_commits || 0),
                font: { 
                    align: 'horizontal', 
                    size: 10, 
                    color: currentTheme === 'dark' ? '#a0a4ab' : '#666666', 
                    strokeWidth: 3, 
                    strokeColor: currentTheme === 'dark' ? '#181a1f' : '#f4f2ee' 
                }
            };
        }));

        const hasBranchesGlobal = edgesData.some(e => edgesData.filter(e2 => e2.to === e.to).length > 1);
        let baseLevelSep = hasBranchesGlobal ? 160 : 240;
        let baseNodeSpac = hasBranchesGlobal ? 110  : 190;

        const network = new vis.Network(container, { nodes, edges }, {
            edges: {
                smooth: {
                    type: 'continuous',
                    forceDirection: 'vertical',
                    roundness: 0.5
                }
            },
            layout: { hierarchical: { enabled: true, direction: 'UD', sortMethod: 'directed', levelSeparation: baseLevelSep, nodeSpacing: baseNodeSpac } },
            interaction: { hover: true, dragNodes: true, zoomView: true, dragView: true, selectConnectedEdges: false },
            physics: { 
                enabled: true, // Smooth initial loading
                stabilization: { enabled: true, iterations: 60, updateInterval: 10, fit: true },
                hierarchicalRepulsion: { nodeDistance: baseLevelSep, centralGravity: 0.05, springLength: baseLevelSep, springConstant: 0.05, damping: 0.3 },
                solver: 'hierarchicalRepulsion'
            }
        });

        // Event for smooth settling visually
        network.once("stabilizationIterationsDone", function () {
            if (nodesLocked) {
                network.setOptions({ physics: { enabled: false } }); // Lock into place
            }
        });

        function updateNetworkColors() {
            const t = THEMES_CONFIG[currentTheme];
            nodes.forEach(n => {
                if(n.is_expanded_commit) {
                    nodes.update({id: n.id, color: { background: currentTheme === 'dark' ? '#2a2a2a' : '#dfdbd4', border: currentTheme === 'dark' ? '#555555' : '#b1b6bd' }, font: { color: t.font }});
                } else {
                    nodes.update({id: n.id, color: { background: n.is_main ? t.mainBg : t.sideBg, border: n.is_main ? t.mainBorder : t.sideBorder }, font: { color: t.font }});
                }
            });
            edges.forEach(e => {
                edges.update({
                    id: e.id, 
                    color: { color: t.edge, highlight: t.edgeHi },
                    font: { 
                        color: currentTheme === 'dark' ? '#a0a4ab' : '#666666', 
                        strokeColor: currentTheme === 'dark' ? '#181a1f' : '#f4f2ee' 
                    }
                });
            });
            if (lastHighlightedNode) highlightNode(lastHighlightedNode);
        }

        // Feedback de cursor para "Comodidad" al mover nodos
        network.on("hoverNode", () => container.style.cursor = 'grab');
        network.on("blurNode",  () => container.style.cursor = 'default');
        network.on("dragStart", (p) => { if(p.nodes.length > 0) container.style.cursor = 'grabbing'; });
        network.on("dragEnd",   (params) => { 
            container.style.cursor = 'grab'; 
            if (params.nodes.length > 0) {
                const pos = network.getPositions(params.nodes);
                Object.assign(savedPositions, pos);
                try { localStorage.setItem('gitsearch_positions', JSON.stringify(savedPositions)); } catch(e){}
            }
        });

        function updateLockBtn() {
            const btn = document.getElementById('btn-lock');
            btn.textContent = nodesLocked ? '🧊 Modo Estricto' : '🌊 Modo Dinámico';
            btn.title = nodesLocked ? "Modo Estricto: Nodos fijos sin físicas (más estable)" : "Modo Dinámico: Físicas suaves al mover ramas";
        }
        updateLockBtn();

        function toggleNodeLock() {
            nodesLocked = !nodesLocked;
            localStorage.setItem('gitsearch_locked', nodesLocked);
            updateLockBtn();
            
            if (nodesLocked) {
                // Modo Fijo/Estricto: desactiva físicas para que no se reacomode violentamente
                network.setOptions({ 
                    layout: { hierarchical: { enabled: true, direction: 'UD', sortMethod: 'directed' } },
                    physics: { enabled: false }
                });
            } else {
                // Modo Dinámico: jerárquico + solver repulsion
                network.setOptions({ 
                    layout: { hierarchical: { enabled: false } },
                    physics: { 
                        enabled: true, 
                        solver: 'repulsion', 
                        repulsion: { nodeDistance: 130, springLength: 200, damping: 0.2 }
                    }
                });
            }
        }
        
        // Exponer función para obtener posiciones actuales (útil para ajustes o guardado manual)
        window.getNodesPosition = () => {
            const pos = network.getPositions();
            return nodes.get().map(n => ({ id: n.id, label: n.label, x: pos[n.id].x, y: pos[n.id].y }));
        };

        if (globalSearchData && globalSearchData.total > 0) {
            document.getElementById('nav-search').style.display = 'block';
            setTimeout(() => {
                setPanelTab('search');
                openPanel();
            }, 500);
        }

        let expandedTagId = null;
        let expandedNodes = [];
        let expandedEdges = [];
        let originalEdgeId = null;
        let savedCameraState = null;

        function collapseCommits() {
            if (expandedNodes.length > 0) nodes.remove(expandedNodes);
            if (expandedEdges.length > 0) edges.remove(expandedEdges);
            if (originalEdgeId) {
                try { edges.update({id: originalEdgeId, hidden: false}); } catch(e) {}
            }
            expandedNodes = [];
            expandedEdges = [];
            expandedTagId = null;
            originalEdgeId = null;

            if (savedCameraState) {
                // Restore purely to the exact saved state
                network.moveTo({
                    position: savedCameraState.position,
                    scale: savedCameraState.scale,
                    animation: { duration: 350, easingFunction: 'easeInOutQuad' }
                });
                savedCameraState = null;
            }
        }

        network.on("click", (params) => {
            if (params.nodes.length > 0) {
                const tagSha = params.nodes[0];
                const node = nodes.get(tagSha);
                
                // Si es un commit intermedio expandido
                if (node.is_expanded_commit) {
                    selectCommitByHash(node.commit_hash, node.id);
                    return;
                }
                
                selectedNode = node;
                // Por defecto cargamos el commit del tag
                const commit = historyData.find(c => c.full_hash === tagSha || c.hash === node.hash);
                if (commit) {
                    selectedCommit = commit;
                    openPanel();
                    highlightNode(tagSha);
                }

                // --------- EXPANDIR NODO ---------
                if (expandedTagId === tagSha) {
                    collapseCommits();
                } else {
                    // Si habia otro nodo abierto, guardar su estado viejo es redundante 
                    // porque ya regresaremos a la base, pero queremos tomar snapshot de DONDE esta AHORA
                    // antes de abrir el nuevo nodo si el grafo estaba colapsado.
                    let currentCam = { position: network.getViewPosition(), scale: network.getScale() };
                    
                    collapseCommits();
                    
                    if (node && node.stats && node.stats.commits_list && node.stats.commits_list.length > 0) {
                        savedCameraState = currentCam;
                        expandedTagId = tagSha;
                        
                        // Buscar el edge original desde el padre
                        let parentEdg = null;
                        const connectedEdges = network.getConnectedEdges(tagSha);
                        for (let eId of connectedEdges) {
                            const e = edges.get(eId);
                            if (e && e.to === tagSha && e.from !== tagSha && !e.hidden) {
                                parentEdg = e;
                                break;
                            }
                        }
                        
                        let startSha = tagSha;
                        let isAttachedToParent = false;
                        if (parentEdg) {
                            originalEdgeId = parentEdg.id;
                            edges.update({id: originalEdgeId, hidden: true});
                            startSha = parentEdg.from;
                            isAttachedToParent = true;
                        }
                        
                        const commits = [...node.stats.commits_list].reverse(); // oldest to newest
                        const newNodes = [];
                        const newEdges = [];
                        
                        const parentPos = network.getPositions([tagSha])[tagSha] || {x: 0, y: 0};
                        const commitHashes = new Set(commits.map(c => c.hash));
                        let groupHasBranches = commits.some(c => c.parents && c.parents.length > 1);
                        
                        // Adaptive layout: increase spacing to prevent ALL overlapping
                        let isGraphCurrentlyBranched = hasBranchesGlobal || groupHasBranches;
                        let adaptLevelSep = isGraphCurrentlyBranched ? 180 : 260;
                        let adaptNodeSpac = isGraphCurrentlyBranched ? 140  : 220;
                        
                        network.setOptions({
                            layout: { hierarchical: { levelSeparation: adaptLevelSep, nodeSpacing: adaptNodeSpac } },
                            physics: { hierarchicalRepulsion: { nodeDistance: adaptLevelSep, springLength: adaptLevelSep } }
                        });
                        
                        // Pre-calcular tamanos de nodos para spacing optimo
                        const nodeSizes = commits.map((c) => {
                            const msgLines = (c.mensaje_full || c.mensaje || c.hash).split('\\n');
                            let labelTxt = msgLines[0];
                            if (msgLines.length > 1) {
                                const descs = msgLines.slice(1).filter(l => l.trim() !== '');
                                for (let j = 0; j < Math.min(descs.length, 4); j++) {
                                    labelTxt += '\\n- ' + descs[j].trim();
                                }
                                if (descs.length > 4) labelTxt += '\\n...';
                            }
                            const labelLength = labelTxt.length;
                            const lines = labelTxt.split('\\n').length;
                            const width = Math.max(150, Math.min(380, 80 + labelLength * 4.2));
                            const height = Math.max(40, 20 + lines * 13);
                            return { labelTxt, width, height };
                        });
                        
                        // Espaciado basado en nodos mas grandes
                        const maxWidth = Math.max(...nodeSizes.map(n => n.width));
                        const maxHeight = Math.max(...nodeSizes.map(n => n.height));
                        const hSpacing = maxWidth + 70;
                        const vSpacing = maxHeight + 90;
                        
                        // Grid distribution
                        const cols = Math.max(2, Math.ceil(Math.sqrt(commits.length * 1.2)));
                        
                        for (let i = 0; i < commits.length; i++) {
                            const c = commits[i];
                            const cId = "exp_" + c.hash;
                            
                            const { labelTxt, width, height } = nodeSizes[i];
                            const titleTxt = `Hash: ${c.hash}\\nAutor: ${c.autor}\\nFecha: ${c.fecha}\\n\\n${c.mensaje_full || c.mensaje}`;
                            
                            const pos = savedPositions[cId];
                            
                            // Grid positioning with stagger
                            const col = i % cols;
                            const row = Math.floor(i / cols);
                            const xOffset = (col - Math.floor(cols / 2)) * hSpacing;
                            const yOffset = row * vSpacing;
                            
                            let initialX = pos ? pos.x : (parentPos.x + xOffset);
                            let initialY = pos ? pos.y : (parentPos.y + 100 + yOffset);
                            
                            newNodes.push({
                                id: cId,
                                is_expanded_commit: true,
                                commit_hash: c.full_hash || c.hash,
                                label: labelTxt,
                                title: titleTxt,
                                shape: 'box',
                                widthConstraint: width + 15,
                                heightConstraint: height + 10,
                                color: { background: currentTheme === 'dark' ? '#2a2a2a' : '#dfdbd4', border: currentTheme === 'dark' ? '#555555' : '#b1b6bd' },
                                font: { color: THEMES_CONFIG[currentTheme].font, size: 10, face: 'Inter', align: 'left' },
                                x: initialX,
                                y: initialY
                            });
                            
                            let parents = c.parents || [];
                            if (parents.length === 0 && i === 0 && isAttachedToParent) {
                                newEdges.push({ 
                                    id: `exp_edge_start_${c.hash}`, 
                                    from: startSha, 
                                    to: cId, 
                                    arrows: "to", 
                                    smooth: { enabled: true, type: "continuous" },
                                    color: { color: THEMES_CONFIG[currentTheme].edgeHi },
                                    width: 1.5
                                });
                            } else {
                                let linkedToStart = false;
                                for (let p of parents) {
                                    if (commitHashes.has(p)) {
                                        newEdges.push({
                                            id: `exp_edge_${p}_${c.hash}`,
                                            from: "exp_" + p,
                                            to: cId,
                                            arrows: "to",
                                            smooth: { enabled: true, type: "continuous" },
                                            color: { color: THEMES_CONFIG[currentTheme].edgeHi },
                                            width: 1.5
                                        });
                                    } else {
                                        // Parent not in expanded group, link from startSha tag if appropriate
                                        if (isAttachedToParent && !linkedToStart) {
                                            newEdges.push({ 
                                                id: `exp_edge_start_${p}_${c.hash}`, 
                                                from: startSha, 
                                                to: cId, 
                                                arrows: "to", 
                                                smooth: { enabled: true, type: "continuous" },
                                                color: { color: THEMES_CONFIG[currentTheme].edgeHi },
                                                width: 1.5
                                            });
                                            linkedToStart = true;
                                        }
                                    }
                                }
                            }
                        }
                        
                        // Childless commits in the group (leaves) re-connect to the parent Tag
                        const childCounts = {};
                        for (let c of commits) childCounts[c.hash] = 0;
                        for (let c of commits) {
                            for (let p of (c.parents || [])) {
                                if (childCounts[p] !== undefined) childCounts[p]++;
                            }
                        }
                        
                        let hasLeafLinkedToTag = false;
                        for (let c of commits) {
                            if (childCounts[c.hash] === 0) {
                                newEdges.push({
                                    id: `exp_edge_end_${c.hash}`,
                                    from: "exp_" + c.hash,
                                    to: tagSha,
                                    arrows: "to",
                                    smooth: { enabled: true, type: "continuous" },
                                    color: { color: THEMES_CONFIG[currentTheme].edgeHi },
                                    dashes: [4, 4],
                                    width: 1.5
                                });
                                hasLeafLinkedToTag = true;
                            }
                        }
                        
                        // Fallback just in case
                        if (!hasLeafLinkedToTag && commits.length > 0) {
                             newEdges.push({
                                 id: `exp_edge_end_fallback`,
                                 from: "exp_" + commits[commits.length-1].hash,
                                 to: tagSha,
                                 arrows: "to",
                                 smooth: { enabled: true, type: "continuous" },
                                 color: { color: THEMES_CONFIG[currentTheme].edgeHi },
                                 dashes: [4, 4],
                                 width: 1.5
                             });
                        }
                        
                        nodes.add(newNodes);
                        edges.add(newEdges);
                        
                        expandedNodes = newNodes.map(n => n.id);
                        expandedEdges = newEdges.map(e => e.id);
                        
                        // Temporarily turn on a very gentle, constrained physics simulation ONLY if nodes weren't saved
                        // Allows the graph structure to naturally untangle itself without shooting across the screen
                        const hasUnsavedPos = newNodes.some(n => !savedPositions[n.id]);
                        if (hasUnsavedPos && !nodesLocked) {
                            network.setOptions({
                                physics: { 
                                    enabled: true,
                                    hierarchicalRepulsion: { nodeDistance: adaptLevelSep, centralGravity: 0.05, springLength: adaptLevelSep, springConstant: 0.03, damping: 0.3 }
                                }
                            });
                            // Turn physics back off shortly to freeze them in the new clean layout
                            setTimeout(() => {
                                network.setOptions({ physics: { enabled: false } });
                                const finalPos = network.getPositions(expandedNodes);
                                Object.assign(savedPositions, finalPos);
                                try { localStorage.setItem('gitsearch_positions', JSON.stringify(savedPositions)); } catch(e){}
                            }, 1200);
                        }
                    }
                }
            } else {
                closePanel();
                collapseCommits();
            }
        });

        function performSearch() {
            const query = document.getElementById('commit-input').value.toLowerCase().trim();
            if (!query) return;

            const matches = historyData.filter(c => 
                c.full_hash.toLowerCase().includes(query) || 
                c.hash.toLowerCase().includes(query) || 
                c.mensaje.toLowerCase().includes(query)
            );

            if (matches.length > 0) {
                const found = matches[0];
                selectedCommit = found;
                
                // Determinar a qué nodo pertenece este commit
                const ownerNodeSha = commitToTag[found.full_hash] || commitToTag[found.hash];
                
                // Si el commit pertenece a un nodo DIFERENTE al actual (ej. un nodo anterior)
                if (ownerNodeSha && ownerNodeSha !== selectedNode.id) {
                    highlightNode(ownerNodeSha);
                    // Enfocar el nodo encontrado de manera robusta y sin animaciones conflictivas
                    network.focus(ownerNodeSha, { scale: 1.2, animation: false });
                }
                
                renderPanel();
            } else {
                alert("Commit no encontrado en el historial.");
            }
        }
        
        // ── Utilidades UI: Copiar y Monstrar Modal ─────────────────────────
        const iconCopySVG = `<svg viewBox="0 0 16 16" version="1.1"><path fill-rule="evenodd" d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 010 1.5h-1.5a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 00.25-.25v-1.5a.75.75 0 011.5 0v1.5A1.75 1.75 0 019.25 16h-7.5A1.75 1.75 0 010 14.25v-7.5z"></path><path fill-rule="evenodd" d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0114.25 11h-7.5A1.75 1.75 0 015 9.25v-7.5zm1.75-.25a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 00.25-.25v-7.5a.25.25 0 00-.25-.25h-7.5z"></path></svg>`;

        function getCopyBtnHtml(text) {
            return `<div class="copy-icon" onclick="copyToClipboard('${text}', event)" title="Copiar">${iconCopySVG}</div>`;
        }

        function copyToClipboard(text, event) {
            if (event) event.stopPropagation();
            if (navigator.clipboard) {
                navigator.clipboard.writeText(text).then(() => { mostrarTooltipCopiado(event); });
            } else {
                const ta = document.createElement('textarea');
                ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
                mostrarTooltipCopiado(event);
            }
        }

        // [VISUAL ONLY] Tooltip copiado — paleta monocromática
        function mostrarTooltipCopiado(event) {
            const tt = document.createElement('div');
            tt.textContent = 'Copiado';
            Object.assign(tt.style, {
                position: 'fixed', background: '#1a1a1a', border: '1px solid rgba(255,255,255,0.15)',
                color: '#e0e0e0', padding: '4px 10px', borderRadius: '4px',
                fontSize: '11px', fontFamily: 'Inter, sans-serif', fontWeight: '600',
                letterSpacing: '0.03em', zIndex: '10000',
                left: (event.clientX + 10) + 'px', top: (event.clientY + 10) + 'px',
                pointerEvents: 'none', animation: 'modalFadeIn 0.15s'
            });
            document.body.appendChild(tt);
            setTimeout(() => tt.remove(), 1000);
        }

        function showCommitModal(hash) {
            let commit = historyData.find(c => c.full_hash === hash || c.hash === hash);
            if (!commit && typeof globalSearchData !== 'undefined' && globalSearchData && globalSearchData.resultados) {
                commit = globalSearchData.resultados.find(c => c.full_hash === hash || c.hash === hash);
            }
            if (!commit) return;
            
            // Guardar estado visual antes de abrir el modal
            if (typeof network !== 'undefined') {
                savedCameraState = {
                    position: network.getViewPosition(),
                    scale: network.getScale()
                };
            }
            
            const msgList = (commit.mensaje_full || commit.mensaje || '').split('\\n');
            document.getElementById('modal-title').textContent = msgList[0];
            // [VISUAL ONLY] Metadatos del modal con paleta monocromática
            document.getElementById('modal-meta').innerHTML = `👤 <strong style="color:var(--text-primary);">${escapeHtml(commit.autor)}</strong> &nbsp;•&nbsp; 📅 ${commit.fecha}`;
            
            document.getElementById('modal-hash-container').innerHTML = `
                <div class="hash-code" style="font-size:0.95rem;">${commit.full_hash || commit.hash}</div>
                ${getCopyBtnHtml(commit.full_hash || commit.hash)}
            `;
            
            const pContainer = document.getElementById('modal-parents-container');
            if (commit.parents && commit.parents.length > 0) {
                // [VISUAL ONLY] Padres con estilos monocromáticos
                pContainer.innerHTML = commit.parents.map(ph => `
                    <div style="display:flex; align-items:center;">
                        <span style="font-family:'JetBrains Mono',monospace; font-size:0.80rem; color:#888888;
                              background:#111111; border:1px solid rgba(255,255,255,0.10); border-radius:4px;
                              padding:2px 8px; cursor:pointer; transition:color 0.15s;"
                              onclick="hideCommitModal(); if(typeof gsNavParent==='function'){gsNavParent('${ph}');}else{selectCommitByHash('${ph}');}">↑ ${ph}</span>
                        ${getCopyBtnHtml(ph)}
                    </div>
                `).join('');
            } else {
                pContainer.innerHTML = '<span style="color:var(--text-muted); font-size:0.82rem;">Ninguno (Raíz)</span>';
            }
            
            let rawDiff = commit.diff && commit.diff.length > 5 ? commit.diff : "No se detectaron cambios en archivos o diff no disponible.";
            document.getElementById('modal-diff').innerHTML = formatDiff(rawDiff);
            
            document.getElementById('commit-modal').style.display = 'flex';
        }

        // Función para cerrar el modal y restaurar la vista
        function hideCommitModal() {
            document.getElementById('commit-modal').style.display = 'none';
            // Restaurar estado visual cuando se cierra el modal
            if (savedCameraState && typeof network !== 'undefined') {
                network.moveTo({
                    position: savedCameraState.position,
                    scale: savedCameraState.scale,
                    animation: { duration: 300, easingFunction: 'easeInOutQuad' }
                });
                savedCameraState = null;
            }
        }


        function highlightNode(nodeId) {
            const t = THEMES_CONFIG[currentTheme];
            if (lastHighlightedNode) {
                const old = nodes.get(lastHighlightedNode);
                if (old) {
                    if (old.is_expanded_commit) {
                        nodes.update({ id: lastHighlightedNode, color: { background: currentTheme === 'dark' ? '#2a2a2a' : '#dfdbd4', border: currentTheme === 'dark' ? '#555555' : '#b1b6bd' } });
                    } else {
                        nodes.update({ id: lastHighlightedNode, color: { background: old.is_main ? t.mainBg : t.sideBg, border: old.is_main ? t.mainBorder : t.sideBorder } });
                    }
                }
            }
            nodes.update({ id: nodeId, color: { background: currentTheme === 'dark' ? '#ffffff' : '#000000', border: currentTheme === 'dark' ? '#ffffff' : '#000000' } });
            lastHighlightedNode = nodeId;
        }

        function openPanel() {
            // Guardar estado visual actual antes de abrir el panel
            if (typeof network !== 'undefined') {
                savedCameraState = {
                    position: network.getViewPosition(),
                    scale: network.getScale()
                };
            }
            document.getElementById('side-panel').classList.add('open');
            renderPanel();
        }

        function closePanel() {
            document.getElementById('side-panel').classList.remove('open');
            // Restaurar estado visual cuando se cierra el panel
            if (savedCameraState && typeof network !== 'undefined') {
                network.moveTo({
                    position: savedCameraState.position,
                    scale: savedCameraState.scale,
                    animation: { duration: 300, easingFunction: 'easeInOutQuad' }
                });
                savedCameraState = null;
            }
            if (lastHighlightedNode) {
                const t = THEMES_CONFIG[currentTheme];
                const old = nodes.get(lastHighlightedNode);
                if (old) {
                    if (old.is_expanded_commit) {
                        nodes.update({ id: lastHighlightedNode, color: { background: currentTheme === 'dark' ? '#2a2a2a' : '#dfdbd4', border: currentTheme === 'dark' ? '#555555' : '#b1b6bd' } });
                    } else {
                        nodes.update({ id: lastHighlightedNode, color: { background: old.is_main ? t.mainBg : t.sideBg, border: old.is_main ? t.mainBorder : t.sideBorder } });
                    }
                }
                lastHighlightedNode = null;
            }
        }

        function setPanelTab(tab) {
            currentTab = tab;
            document.getElementById('nav-info').classList.toggle('active', tab === 'info');
            document.getElementById('nav-history').classList.toggle('active', tab === 'history');
            const navSearch = document.getElementById('nav-search');
            if (navSearch) navSearch.classList.toggle('active', tab === 'search');
            renderPanel();
        }

        function renderPanel() {
            const content = document.getElementById('panel-content');
            if (currentTab === 'info') {
                if (!selectedCommit) return;
                
                let tagMarkup = "";
                const tagSha = commitToTag[selectedCommit.full_hash] || commitToTag[selectedCommit.hash];
                if (tagSha) {
                    const node = nodes.get(tagSha);
                    tagMarkup = `<div class="tag-badge">${node.label}</div>`;
                }

                content.innerHTML = `
                    <div class="search-area">
                        <input type="text" id="commit-input" placeholder="Buscar Hash en este flujo..." onkeyup="if(event.key=='Enter') performSearch()">
                        <button onclick="performSearch()">Buscar</button>
                    </div>

                    <div class="section-title">Información del Commit ${tagMarkup}</div>
                    <div style="margin-bottom:12px">
                        <div style="font-size:0.9rem; font-weight:600; line-height:1.4;">${escapeHtml(selectedCommit.mensaje_full)}</div>
                        <div style="color:var(--text-secondary); font-size:0.8rem; margin-top:8px;">
                            👤 <strong>${escapeHtml(selectedCommit.autor)}</strong><br>
                            📅 ${selectedCommit.fecha}
                        </div>
                    </div>
                    <div class="section-title">Identificador (SHA)</div>
                    <div style="display:flex; align-items:center; margin-bottom:12px;">
                        <div class="hash-code">${selectedCommit.full_hash}</div>
                        ${getCopyBtnHtml(selectedCommit.full_hash)}
                    </div>

                    <div class="section-title">Commit Padre</div>
                    <!-- [VISUAL] Commit parent links monocromáticos -->
                    <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:20px;">
                        ${(selectedCommit.parents && selectedCommit.parents.length > 0)
                            ? selectedCommit.parents.map((ph, i) => {
                                const pFull = (selectedCommit.parents[i] || ph);
                                return `<div style="display:flex; align-items:center;">
                                    <span style="font-family:'JetBrains Mono',monospace; font-size:0.72rem; color:#aaaaaa;
                                    background:#1a1a1a; border:1px solid #333333;
                                    border-radius:4px; padding:3px 8px; cursor:pointer;"
                                    onclick="gsNavParent && gsNavParent('${ph}')"
                                    title="Ir al commit padre ${ph}">↑ ${ph}</span>
                                    ${getCopyBtnHtml(ph)}
                                    </div>`;
                              }).join('')
                            : '<span style="font-size:0.72rem;color:var(--text-muted);">Raíz — sin padre</span>'
                        }
                    </div>

                    <!-- [VISUAL] Sección analizar diff — monocromática -->
                    <div style="background:#141414; padding:14px 16px; border-radius:8px; border:1px solid var(--border-subtle);">
                        <div class="section-title" style="margin-top:0;">Analizar Cambios Reales</div>
                        <div style="font-size:0.78rem; color:var(--text-muted); margin-bottom:12px; line-height:1.5;">
                            Visualice los archivos modificados, adiciones y supresiones de este commit.
                        </div>
                        <button onclick="showCommitModal('${selectedCommit.full_hash}')"
                                style="background:#1a1a1a; border:1px solid var(--border-normal); color:var(--text-primary); padding:9px 14px; border-radius:6px; cursor:pointer; font-weight:600; font-size:0.80rem; width:100%; display:flex; justify-content:center; align-items:center; gap:8px; transition:background 0.15s, border-color 0.15s; font-family:inherit;"
                                onmouseover="this.style.background='#222222'; this.style.borderColor='#555555'" onmouseout="this.style.background='#1a1a1a'; this.style.borderColor='rgba(255,255,255,0.10)'">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M1.75 2.5a.25.25 0 0 0-.25.25v10.5c0 .138.112.25.25.25h12.5a.25.25 0 0 0 .25-.25v-8.5h-4a2 2 0 0 1-2-2v-4H1.75ZM7.5 4.51V1.535a.25.25 0 0 1 .427-.177l4.683 4.683A.25.25 0 0 1 12.433 6.5H9.5a2 2 0 0 1-2-1.99ZM10.5 8h-5a.75.75 0 0 0 0 1.5h5a.75.75 0 0 0 0-1.5Zm-5 3.5h5a.75.75 0 0 0 0-1.5h-5a.75.75 0 0 0 0 1.5Z"/></svg>
                            Explorar Diffs y Archivos Afectados
                        </button>
                    </div>
                `;
            } else if (currentTab === 'history') {
                // Lista de commits exclusivos de este NODO (tag)
                const nodeCommits = selectedNode.stats.commits_list || [];
                content.innerHTML = `
                    <div class="section-title">Commits introducidos en esta versión (${nodeCommits.length})</div>
                    <div class="commit-explorer-list">
                        ${nodeCommits.map(c => `
                            <div class="ce-item ${selectedCommit.hash == c.hash ? 'active' : ''}" onclick='selectCommitByHash("${c.full_hash || c.hash}")'>
                                <div class="ce-hash">${c.hash}</div>
                                <div class="ce-msg-container">
                                    <div class="ce-msg">${escapeHtml(c.mensaje)}</div>
                                    <div class="ce-meta">${c.fecha} • ${escapeHtml(c.autor)}</div>
                                </div>
                            </div>
                        `).join('') || '<p style="color:var(--text-secondary); font-size:0.8rem;">No hay commits exclusivos en este nodo.</p>'}
                    </div>
                `;
            } else if (currentTab === 'search') {
                if (!globalSearchData) return;
                content.innerHTML = `
                    <div class="search-area">
                        <input type="text" id="commit-input" placeholder="Buscar Hash en este flujo..." onkeyup="if(event.key=='Enter') performSearch()">
                        <button onclick="performSearch()">Buscar local</button>
                    </div>
                    <div class="section-title">Resultados de Búsqueda Global: "${escapeHtml(globalSearchData.criterio)}" (${globalSearchData.total})</div>
                    <div class="commit-explorer-list">
                        ${globalSearchData.resultados.map(r => `
                            <!-- [VISUAL] border-left monocromático en resultados -->
                            <div class="ce-item ${selectedCommit && selectedCommit.hash == r.hash ? 'active' : ''}" onclick='selectCommitByHash("${r.full_hash}")' style="border-left: 2px solid #555555;">
                                <div>
                                    <div class="ce-hash">${r.hash} <span style="font-size:0.62rem; background:#1a1a1a; border:1px solid #333333; padding:1px 5px; border-radius:3px; color:#999999; margin-left:4px;">${escapeHtml(r.tipo)}</span></div>
                                    <div class="ce-msg" style="margin-top:4px; font-weight:600;">${escapeHtml(r.mensaje)}</div>
                                    <div class="ce-meta">${r.fecha} • ${escapeHtml(r.autor)}</div>
                                    ${r.tags && r.tags.length > 0 ? `<div style="margin-top:4px;"><span style="font-size:0.7rem; color:var(--text-secondary);">Versión/Tag:</span> <span class="tag-badge" style="margin-left:2px; font-size:0.65rem;">${escapeHtml(r.tags[0])}${r.tags.length>1?' (+' + (r.tags.length-1) + ')':''}</span></div>` : '<div style="margin-top:4px;"><span style="font-size:0.7rem; color:var(--text-secondary);">Versión/Tag: Ninguno</span></div>'}
                                    ${r.archivos && r.archivos.length > 0 ? `<div class="ce-meta" style="margin-top:4px; color:#8b949e;">Archivos: ${escapeHtml(r.archivos.length > 2 ? r.archivos.slice(0,2).join(', ') + '... (+'+(r.archivos.length-2)+')' : r.archivos.join(', '))}</div>` : ''}
                                </div>
                            </div>
                        `).join('') || '<p style="color:var(--text-secondary); font-size:0.8rem;">No se encontraron resultados para la búsqueda.</p>'}
                    </div>
                `;
            }
        }

        function selectCommitByHash(hash, clickedNodeId = null) {
            // Primero buscar en el historial global para obtener metadatos completos
            let c = historyData.find(x => x.full_hash === hash || x.hash === hash);
            
            // Si no está (truncado por rendimiento offline), creamos un dummy desde globalSearchData
            if (!c && globalSearchData) {
                const sr = globalSearchData.resultados.find(x => x.full_hash === hash || x.hash === hash);
                if (sr) {
                    c = {
                        hash: sr.hash,
                        full_hash: sr.full_hash,
                        autor: sr.autor,
                        fecha: sr.fecha,
                        mensaje: sr.mensaje.split('\\n')[0],
                        mensaje_full: sr.mensaje + "\\n\\n[!] Resultado de búsqueda profunda.\\n[!] Detalles exhaustivos de diff no disponibles offline para ahorrar memoria pero el commit reside en el historial.",
                        diff: "Cambio detectado de forma silenciosa en diffs o commit message.\\nArchivos afectados documentados:\\n" + (sr.archivos.length > 0 ? sr.archivos.map(a => "+ " + a).join("\\n") : "  (Desconocidos / Sin archivos)")
                    };
                }
            }

            if (c) {
                selectedCommit = c;
                setPanelTab('info');
                
                let targetNodeId = clickedNodeId;
                if (!targetNodeId) {
                    const expandedId = "exp_" + c.hash;
                    if (nodes.get(expandedId)) {
                        targetNodeId = expandedId;
                    } else {
                        targetNodeId = commitToTag[c.full_hash] || commitToTag[c.hash];
                    }
                }
                
                if (targetNodeId) {
                    highlightNode(targetNodeId);
                    network.focus(targetNodeId, { scale: 1.2, animation: true });
                    try { network.selectNodes([targetNodeId]); } catch(e){}
                }
            }
        }

        // [VISUAL ONLY] formatDiff usa paleta monocromática — sin azules ni verdes brillantes
        function formatDiff(txt) {
            return txt.split('\\n').map(line => {
                const escaped = escapeHtml(line);
                if (line.startsWith('diff --git')) return `\\n<div style="background:#141414; padding:9px 14px; border-radius:4px; font-weight:600; border-left:3px solid #555555; color:#dddddd; margin-top:18px; font-size:0.80rem;">■ ${escaped.replace('diff --git ', '')}</div>`;
                if (line.match(/^index [0-9a-f]+\\.\\.[0-9a-f]+/)) return `<div style="color:#555555; font-size:0.72rem; padding-left:14px; margin-bottom:6px;">${escaped}</div>`;
                if (line.startsWith('--- a/') || line.startsWith('+++ b/')) return `<div style="color:#666666; font-size:0.72rem; padding-left:14px;">${escaped}</div>`;
                if (line.startsWith('+') && !line.startsWith('+++')) return `<div class="diff-added" style="padding:1px 14px;">${escaped}</div>`;
                if (line.startsWith('-') && !line.startsWith('---')) return `<div class="diff-removed" style="padding:1px 14px;">${escaped}</div>`;
                if (line.startsWith('@@')) return `<div class="diff-info" style="margin:10px 0 4px; padding:5px 14px; background:#141414; border-radius:3px; font-weight:600;">${escaped}</div>`;
                return `<div style="padding:1px 14px; color:#aaaaaa;">${escaped}</div>`;
            }).join('');
        }

        function escapeHtml(u) { return (u||"").toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
    </script>
<!-- GITSEARCH_PANEL -->
</body>
</html>"""
    html = html_template.replace("__NODES_DATA__", json.dumps(nodes))
    html = html.replace("__EDGES_DATA__", json.dumps(edges))
    html = html.replace("__HISTORY_DATA__", json.dumps(historial["commits"] if historial else []))
    html = html.replace("__COMMIT_MAP__", json.dumps(commit_to_tag))
    html = html.replace("__GLOBAL_SEARCH__", json.dumps(busqueda) if busqueda else "null")
    return html

# ──────────────────────────────────────────────
# SECCIÓN 3.5 — BÚSQUEDA PROFUNDA DE COMMIT / CÓDIGO
# ──────────────────────────────────────────────

def ejecutar_busqueda(repo: Repo, criterio: str, topologia: dict) -> dict:
    """
    Busca un hash, mensaje de commit, o línea de código (diff) en todo el repositorio.
    Utiliza -G (regex flexible) para diffs y --grep para mensajes.
    Devuelve un diccionario estructurado con los resultados para integrar en reporte y HTML.
    """
    import re
    print(f"[INFO] Ejecutando búsqueda profunda para: '{criterio}'...")
    
    shas_encontrados = {}  # sha -> tipo_match
    
    # 1. ¿Es un hash de commit?
    es_posible_hash = re.match(r'^[0-9a-fA-F]{4,40}$', criterio.strip())
    if es_posible_hash:
        try:
            c = repo.commit(criterio.strip())
            shas_encontrados[c.hexsha] = "Hash de commit"
        except Exception:
            pass

    # 2. Buscar por mensaje de commit descriptivo
    try:
        raw_grep = repo.git.log("--all", f"--grep={criterio}", "-i", "--format=%H")
        for sha in raw_grep.splitlines():
            if sha and sha not in shas_encontrados:
                shas_encontrados[sha] = "Texto descriptivo (Mensaje)"
    except Exception:
        pass

    # 3. Buscar por fragmento de línea de código (diff)
    # Permite encontrar combinaciones de palabras clave dispersas o ajustadas interactuando con git grep/log flexible
    partes = str(criterio).strip().split()
    if len(partes) > 1:
        # escapamos para regex y permitimos caracteres intermedios.
        regex_flexible = ".*".join(re.escape(p) for p in partes)
    else:
        regex_flexible = re.escape(criterio)

    try:
        raw_diff = repo.git.log("--all", f"-G{regex_flexible}", "-i", "--format=%H")
        for sha in raw_diff.splitlines():
            if sha and sha not in shas_encontrados:
                shas_encontrados[sha] = "Línea de código (Diff)"
    except Exception:
        pass

    resultados = []
    
    # Mapeo rápido de commits a tags usando la topología pre-calculada
    commit_to_tags = {}
    for tag_sha, info in topologia.items():
        nombres = info.get("all_tags", [])
        if nombres:
            commit_to_tags[tag_sha] = nombres
            for c_meta in info.get("stats", {}).get("commits_list", []):
                commit_to_tags[c_meta["hash"]] = nombres

    for sha, tipo in shas_encontrados.items():
        try:
            c = repo.commit(sha)
            hash_corto = c.hexsha[:7]
            
            tags_del_commit = commit_to_tags.get(hash_corto) or commit_to_tags.get(c.hexsha)
            if not tags_del_commit:
                try:
                    out_tags = repo.git.tag("--contains", c.hexsha).splitlines()
                    tags_del_commit = [t.strip() for t in out_tags if t.strip()]
                except Exception:
                    tags_del_commit = []
            
            archivos = []
            try:
                if c.parents:
                    for d in c.parents[0].diff(c):
                        if d.a_path: archivos.append(d.a_path)
                        elif d.b_path: archivos.append(d.b_path)
                else:
                    for d in c.tree.diff(None):
                        pass
            except Exception:
                pass
            
            resultados.append({
                "hash": hash_corto,
                "full_hash": c.hexsha,
                "tipo": tipo,
                "mensaje": c.message.splitlines()[0][:100] if c.message else "Sin mensaje",
                "autor": c.author.name,
                "fecha": datetime.fromtimestamp(c.committed_date).strftime("%Y-%m-%d %H:%M"),
                "tags": tags_del_commit,
                "archivos": sorted(list(set(archivos)))
            })
        except Exception:
            continue
            
    resultados.sort(key=lambda x: x["fecha"], reverse=True)
    
    print(f"[INFO] Búsqueda finalizada. {len(resultados)} coincidencias encontradas.")
    return {
        "criterio": criterio,
        "total": len(resultados),
        "resultados": resultados
    }


# ──────────────────────────────────────────────
# SECCIÓN 4 — GENERACIÓN DEL REPORTE
# ──────────────────────────────────────────────

def generar_reporte(repo_path: str, historial: dict, tags: list, comparacion: Optional[dict], busqueda: dict = None) -> str:
    lineas = []

    def separador(titulo: str):
        lineas.append(f"\n{'=' * 60}")
        lineas.append(f"  {titulo}")
        lineas.append(f"{'=' * 60}")

    lineas.append("╔══════════════════════════════════════════════════════════╗")
    lineas.append("║         REPORTE TÉCNICO DEL REPOSITORIO GIT              ║")
    lineas.append("╚══════════════════════════════════════════════════════════╝")
    lineas.append(f"  Repositorio : {repo_path}")
    lineas.append(f"  Generado    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Sección 1
    separador("SECCIÓN 1 — HISTORIAL COMPLETO")
    if historial["total"] == 0:
        lineas.append("  [!] No se encontraron commits en este repositorio.")
    else:
        lineas.append(f"  Total de commits : {historial['total']}")
        lineas.append(f"  Primer commit    : {historial['fecha_inicio']}")
        lineas.append(f"  Último commit    : {historial['fecha_fin']}")

        lineas.append("\n  📊 Ranking de Autores:")
        for autor, cantidad in historial["autores"].items():
            lineas.append(f"    {'•':2} {autor:<30} {cantidad} commit(s)")

        lineas.append("\n  📋 Lista de Commits (más recientes primero):")
        lineas.append(f"    {'HASH':<8} {'FECHA':<17} {'AUTOR':<25} MENSAJE")
        lineas.append(f"    {'-'*8} {'-'*17} {'-'*25} {'-'*40}")
        for c in historial["commits"]:
            lineas.append(f"    {c['hash']:<8} {c['fecha']:<17} {c['autor']:<25} {c['mensaje']}")

    # ── Sección 2
    separador("SECCIÓN 2 — TAGS Y VERSIONADO")
    if not tags:
        lineas.append("  [!] No se encontraron tags en este repositorio.")
    else:
        lineas.append(f"  Total de tags: {len(tags)}")
        semver_tags = [t for t in tags if t["es_semver"]]
        if semver_tags:
            lineas.append(f"  Tags semver (vX.Y.Z) detectados: {len(semver_tags)}")
        lineas.append("")
        lineas.append(f"    {'TAG':<20} {'FECHA':<12} {'AUTOR':<25} HASH")
        lineas.append(f"    {'-'*20} {'-'*12} {'-'*25} {'-'*8}")
        for t in tags:
            marca = " ✔" if t["es_semver"] else ""
            lineas.append(f"    {t['nombre']:<20} {t['fecha']:<12} {t['autor']:<25} {t['hash']}{marca}")

    # ── Sección 3
    separador("SECCIÓN 3 — COMPARACIÓN ENTRE TAGS")
    if comparacion is None:
        lineas.append("  [!] Se necesitan al menos 2 tags para comparar versiones.")
    elif "error" in comparacion:
        lineas.append(f"  [ERROR] No se pudo comparar tags: {comparacion['error']}")
    else:
        lineas.append(f"  Comparando: {comparacion['tag_anterior']}  →  {comparacion['tag_actual']}")
        lineas.append(f"  Total de commits nuevos : {comparacion['total_commits']}")
        lineas.append(f"  Archivos modificados    : {comparacion['total_archivos']}")
        lineas.append(f"  Autores involucrados    : {', '.join(comparacion['autores']) or 'N/A'}")

        if comparacion["archivos_modificados"]:
            lineas.append("\n  📁 Archivos Modificados:")
            for archivo in comparacion["archivos_modificados"]:
                lineas.append(f"    • {archivo}")

        if comparacion["commits"]:
            lineas.append("\n  📋 Commits Nuevos:")
            lineas.append(f"    {'HASH':<8} {'FECHA':<17} {'AUTOR':<25} MENSAJE")
            lineas.append(f"    {'-'*8} {'-'*17} {'-'*25} {'-'*40}")
            for c in comparacion["commits"]:
                lineas.append(f"    {c['hash']:<8} {c['fecha']:<17} {c['autor']:<25} {c['mensaje']}")

    # ── Sección 4 Búsqueda
    if busqueda:
        separador("SECCIÓN 4 — RESULTADOS DE BÚSQUEDA PROFUNDA")
        lineas.append(f"  Criterio buscado : '{busqueda['criterio']}'")
        lineas.append(f"  Total encontrados: {busqueda['total']}")
        lineas.append("")
        if busqueda['total'] > 0:
            for i, r in enumerate(busqueda["resultados"], 1):
                lineas.append(f"  {i}. {r['hash']} | Coincidencia: {r['tipo']}")
                lineas.append(f"     Mensaje : {r['mensaje']}")
                lineas.append(f"     Autor   : {r['autor']} | {r['fecha']}")
                lineas.append(f"     Versión : {', '.join(r['tags']) if r['tags'] else 'Ninguno (Commit volátil/reciente)'}")
                lineas.append(f"     Archivos: {', '.join(r['archivos']) if r['archivos'] else 'Desconocidos'}")
                lineas.append("")
        else:
            lineas.append("  [!] No se encontraron commits que coincidieran con el criterio.")

    lineas.append(f"\n{'=' * 60}")
    lineas.append("  FIN DEL REPORTE")
    lineas.append(f"{'=' * 60}\n")

    return "\n".join(lineas)


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Analizador técnico offline de repositorio Git local."
    )
    parser.add_argument("repo_path", help="Ruta al repositorio Git local")
    parser.add_argument("--output", "-o", help="Guardar reporte en archivo (.md o .txt)", default=None)
    parser.add_argument("--search", "-s", help="Criterio de búsqueda (hash, texto descriptivo o fragmento de código)", default=None)
    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()

    try:
        repo = Repo(str(repo_path))
    except InvalidGitRepositoryError:
        print(f"[ERROR] La ruta '{repo_path}' no es un repositorio Git válido.")
        sys.exit(1)
    except NoSuchPathError:
        print(f"[ERROR] La ruta '{repo_path}' no existe.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] No se pudo abrir el repositorio: {e}")
        sys.exit(1)

    print(f"[INFO] Analizando repositorio: {repo_path}")

    historial   = obtener_historial(repo)
    tags        = obtener_tags(repo)
    comparacion = comparar_tags(repo, tags)

    # ── Análisis topológico (nuevo motor)
    topologia = analizar_topologia_tags(repo, tags)

    # ── Ejecutar búsqueda si fue solicitada mediante argumentos CLI
    busqueda = None
    if args.search:
        busqueda = ejecutar_busqueda(repo, args.search, topologia)

    reporte = generar_reporte(str(repo_path), historial, tags, comparacion, busqueda)

    # Generar grafo interactivo con topología real y búsqueda integrada
    print("[INFO] Generando grafo de tags y explorador de historial...")
    grafo_html = generar_grafo_html(repo, tags, topologia, historial, busqueda)

    print(reporte)

    # ── Configurar estructura de carpetas de resultados ──
    base_results_dir = Path(__file__).parent / "results"
    project_name = repo_path.name
    project_dir = base_results_dir / project_name
    
    project_dir.mkdir(parents=True, exist_ok=True)
    
    analisis_count = 1
    while (project_dir / f"analisis_{analisis_count}").exists():
        analisis_count += 1
        
    analysis_dir = project_dir / f"analisis_{analisis_count}"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    
    # Determinar nombre del archivo de reporte
    if args.output:
        output_filename = Path(args.output).name
    else:
        output_filename = "reporte.txt"
        
    output_path = analysis_dir / output_filename
    grafo_path = analysis_dir / "reporte_grafo.html"

    # Guardar reporte de texto
    output_path.write_text(reporte, encoding="utf-8", errors="replace")
    print(f"[INFO] Reporte guardado en: {output_path.resolve()}")

    # ── GitSearch: inyectar panel de búsqueda avanzada (aditivo, sin riesgo) ──
    if _GITSEARCH_OK:
        try:
            t_gs_inicio = datetime.now()
            panel_busqueda = _gs_generar_panel(historial["commits"])
            grafo_html = grafo_html.replace("<!-- GITSEARCH_PANEL -->", panel_busqueda)
            delta_ms = int((datetime.now() - t_gs_inicio).total_seconds() * 1000)
            print(f"[GitSearch] Panel de búsqueda inyectado en HTML ({delta_ms} ms).")
        except Exception as _gs_err:
            print(f"[WARN] GitSearch panel no pudo generarse: {_gs_err}")
            grafo_html = grafo_html.replace("<!-- GITSEARCH_PANEL -->", "")
    else:
        grafo_html = grafo_html.replace("<!-- GITSEARCH_PANEL -->", "")

    grafo_path.write_text(grafo_html, encoding="utf-8", errors="replace")
    print(f"[INFO] Grafo interactivo guardado en: {grafo_path.resolve()}")


if __name__ == "__main__":
    main()

