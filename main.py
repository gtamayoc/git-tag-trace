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
    # Limitamos a los últimos 1500 para el explorador interactivo por rendimiento del navegador
    # pero mantenemos la capacidad de buscar cualquier hash si se conoce.
    for i, c in enumerate(commits):
        msg_lines = c.message.strip().splitlines()
        first_line = msg_lines[0][:80] if msg_lines else "Sin mensaje"
        
        # Obtenemos diff para TODOS (removido límite offline) para que la vista
        # detallada pueda mostrar el contenido real de los cambios.
        diff_preview = ""
        try:
             diff_preview = repo.git.show(c.hexsha, "-p", "--stat", "--no-color", "--format=", max_count=1)
             if len(diff_preview) > 6000:
                 diff_preview = diff_preview[:6000] + "\n\n... (diff truncado por tamaño, mostrando primeros 6000 caracteres) ..."
        except:
             diff_preview = "(Error cargando diff)"

        lista.append({
            "hash": c.hexsha[:7],
            "full_hash": c.hexsha,
            "autor": c.author.name,
            "fecha": datetime.fromtimestamp(c.committed_date).strftime("%Y-%m-%d %H:%M"),
            "mensaje": first_line,
            "mensaje_full": c.message.strip(),
            "parents": [p.hexsha for p in c.parents],
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
    commit_tag: object,       # commit del tag actual
    commit_padre_tag: object, # commit del tag ancestro
) -> dict:
    """
    Calcula los commits que están en commit_tag pero NO en commit_padre_tag,
    usando merge_base para encontrar el punto de divergencia exacto.
    Esto funciona correctamente con ramas paralelas y merges.
    """
    try:
        bases = repo.merge_base(commit_padre_tag, commit_tag)
        base  = bases[0] if bases else commit_padre_tag

        # Commits exclusivos: ancestros de tag_actual que no son de base
        commits = list(repo.iter_commits(
            f"{base.hexsha}..{commit_tag.hexsha}", max_count=5000
        ))

        autores = {c.author.name for c in commits}

        # Archivos cambiados entre base y tag (diff topológicamente correcto)
        archivos = set()
        try:
            diff = base.diff(commit_tag)
            for d in diff:
                if d.a_path: archivos.add(d.a_path)
                if d.b_path: archivos.add(d.b_path)
        except Exception:
            pass

        # Días desde el punto de divergencia hasta este tag
        dias = 0
        try:
            delta = (
                datetime.fromtimestamp(commit_tag.committed_date)
                - datetime.fromtimestamp(base.committed_date)
            )
            dias = delta.days
        except Exception:
            pass

        commits_data = [
            {
                "hash":    c.hexsha[:7],
                "autor":   c.author.name,
                "mensaje": c.message.strip().splitlines()[0][:80],
                "fecha":   datetime.fromtimestamp(c.committed_date).strftime("%Y-%m-%d %H:%M"),
            }
            for c in commits
        ]

        return {
            "num_commits":  len(commits),
            "autores":      sorted(autores),
            "num_archivos": len(archivos),
            "archivos":     sorted(archivos),
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

    print("[INFO] Construyendo mapa sha → ramas...")
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

    # tags_vistos_en_commit[sha] = {sha_del_tag_ancestro, ...}
    tags_vistos_en_commit: dict[str, set] = {}

    # reversed(topo_order) itera desde los commits SIN PADRES (más antiguos) a los MÁS NUEVOS.
    for sha in reversed(topo_order):
        tags_heredados = set()
        for p_sha in parent_map.get(sha, []):
            tags_heredados.update(tags_vistos_en_commit.get(p_sha, set()))

        if sha in sha_a_tags_list:
            candidatos = list(tags_heredados)
            padres_directos = []
            if len(candidatos) == 1:
                padres_directos = candidatos
            elif len(candidatos) > 1:
                for cand_sha in candidatos:
                    es_superado = any(
                        otro_sha != cand_sha
                        and es_ancestro_rapido(cand_sha, otro_sha)
                        for otro_sha in candidatos
                    )
                    if not es_superado:
                        padres_directos.append(cand_sha)

            resultado[sha]["padres_shas"] = padres_directos

            # Los commits descendientes de este punto verán ÚNICAMENTE a este punto.
            tags_vistos_en_commit[sha] = {sha}

            # Procesar estadisticas solo del ancestro más directo
            if padres_directos:
                padre_commit = repo.commit(padres_directos[0])
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
    PREFIJOS_LIMPIAR: list[str] = []

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
                n_exc = stats.get("num_commits", "")
                edges.append({
                    "from": padre_sha, "to": sha, "arrows": "to",
                    "label": f"{n_exc} commits" if n_exc else "",
                    "is_parallel": not es_main
                })
        elif i > 0:
            edges.append({"from": shas_ordenados[i-1], "to": sha, "arrows": "to", "is_parallel": False})

    html_template = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Git Version Traceability - Search & History Explorer</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0d1117; 
            --panel-bg: rgba(22, 27, 34, 0.95);
            --text-primary: #e6edf3;
            --text-secondary: #7d8590;
            --accent-primary: #2f81f7;
            --accent-secondary: #58a6ff;
            --border-color: rgba(255, 255, 255, 0.1);
            --border-panel: rgba(255, 255, 255, 0.15);
            --diff-added: #2ea043;
            --diff-removed: #f85149;
            --shadow-subtle: 0 8px 32px rgba(0, 0, 0, 0.5);
            --panel-width: 500px;
        }

        body, html {
            margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden;
            background-color: var(--bg-color); color: var(--text-primary);
            font-family: 'Inter', -apple-system, sans-serif;
        }

        #mynetwork { width: 100%; height: 100%; }

        /* Search (Inside Panel) */
        .search-area {
            background: rgba(255, 255, 255, 0.03); padding: 16px; border-radius: 8px;
            border: 1px solid var(--border-color); margin-bottom: 16px; display: flex; gap: 8px;
        }
        .search-area input {
            flex: 1; background: #0d1117; border: 1px solid var(--border-color); color: white;
            padding: 8px 12px; border-radius: 6px; font-size: 0.85rem; outline: none;
        }
        .search-area button {
            background: var(--accent-primary); border: none; color: white;
            padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: 600;
        }

        /* Side Panel */
        .side-panel {
            position: absolute; top: 0; right: 0; width: var(--panel-width); height: 100%;
            background: var(--panel-bg); backdrop-filter: blur(20px); border-left: 1px solid var(--border-panel);
            box-shadow: var(--shadow-subtle); z-index: 1000; transform: translateX(100%);
            transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1); display: flex; flex-direction: column;
        }

        .side-panel.open { transform: translateX(0); }

        .panel-header { padding: 24px 32px; border-bottom: 1px solid var(--border-color); position: relative; }
        .close-btn { position: absolute; top: 24px; right: 24px; background: none; border: none; color: var(--text-secondary); font-size: 24px; cursor: pointer; }

        .panel-nav { display: flex; border-bottom: 1px solid var(--border-color); }
        .nav-item { flex: 1; padding: 12px; text-align: center; cursor: pointer; color: var(--text-secondary); font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; transition: 0.2s; }
        .nav-item.active { color: var(--accent-secondary); border-bottom: 2px solid var(--accent-secondary); background: rgba(88, 166, 255, 0.05); }

        .panel-content { flex: 1; overflow-y: auto; padding: 24px 32px; scrollbar-width: thin; }
        
        .section-title { font-size: 0.75rem; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; margin: 24px 0 12px 0; }
        
        /* Commit List */
        .commit-explorer-list { display: flex; flex-direction: column; gap: 4px; }
        .ce-item { 
            padding: 10px 14px; border-radius: 6px; cursor: pointer; transition: 0.2s; border: 1px solid transparent;
            display: grid; grid-template-columns: 80px 1fr; gap: 12px; align-items: start;
        }
        .ce-item:hover { background: rgba(255, 255, 255, 0.05); }
        .ce-item.active { background: rgba(47, 129, 247, 0.1); border-color: var(--accent-primary); }
        .ce-hash { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: var(--accent-secondary); font-weight: 600; }
        .ce-msg { font-size: 0.85rem; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .ce-meta { font-size: 0.7rem; color: var(--text-secondary); margin-top: 4px; }

        /* Diff */
        .diff-container {
            font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; background: #010409;
            border: 1px solid var(--border-color); border-radius: 8px; margin-top: 12px;
            white-space: pre-wrap; word-break: break-all; overflow-x: auto; padding: 12px;
            color: #d1d5db; line-height: 1.4;
        }
        .diff-added { color: var(--diff-added); background: rgba(46, 160, 67, 0.1); display: block; }
        .diff-removed { color: var(--diff-removed); background: rgba(248, 81, 73, 0.1); display: block; }
        .diff-info { color: #8b949e; font-style: italic; }

        .intro-panel {
            position: absolute; top: 24px; left: 24px; width: 300px; background: var(--panel-bg);
            border: 1px solid var(--border-panel); border-radius: 12px; padding: 20px; z-index: 100;
        }

        .tag-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; background: var(--accent-primary); color: white; font-size: 0.75rem; margin-left: 8px; font-family: 'JetBrains Mono'; }
        
        .controls { position: absolute; bottom: 24px; left: 24px; display: flex; gap: 8px; z-index: 100; }
        .btn-round { width: 40px; height: 40px; border-radius: 10px; background: var(--panel-bg); border: 1px solid var(--border-panel); color: white; cursor: pointer; display: flex; align-items: center; justify-content: center; }
        .btn-round:hover { background: var(--accent-primary); }

        .hash-code { font-family: 'JetBrains Mono'; background: rgba(255,255,255,0.05); padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; border: 1px solid var(--border-color); }
        
        /* Highlight specific node */
        .node-highlighted { outline: 2px solid #ffca28; outline-offset: 4px; }
        
        /* Modal Commit Detail */
        .modal-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.7); backdrop-filter: blur(5px);
            z-index: 2000; display: none; align-items: center; justify-content: center;
        }
        .modal-content {
            background: #0d1117; width: 85%; max-width: 1000px; height: 85%;
            border-radius: 12px; border: 1px solid var(--border-panel);
            display: flex; flex-direction: column; box-shadow: 0 16px 64px rgba(0,0,0,0.8);
            font-family: 'Inter', sans-serif;
            animation: modalFadeIn 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        @keyframes modalFadeIn { from { opacity: 0; transform: scale(0.98); } to { opacity: 1; transform: scale(1); } }
        
        .modal-header {
            padding: 20px 24px; border-bottom: 1px solid var(--border-color);
            display: flex; justify-content: space-between; align-items: flex-start;
            flex-shrink: 0;
        }
        .modal-body {
            padding: 24px; overflow-y: auto; flex: 1; background: #010409;
            scrollbar-width: thin; scrollbar-color: #30363d transparent;
            border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;
        }
        .copy-icon {
            cursor: pointer; opacity: 0.7; transition: 0.2s; vertical-align: middle;
            display: inline-flex; align-items: center; justify-content: center;
            width: 24px; height: 24px; border-radius: 4px; background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.12); margin-left: 6px; color: #8b949e;
        }
        .copy-icon:hover { opacity: 1; background: rgba(47,129,247,0.2); border-color: #2f81f7; color: #58a6ff; }
        .copy-icon svg { width: 14px; height: 14px; fill: currentColor; }
    </style>
</head>
<body>
    <div id="mynetwork"></div>

    <div class="intro-panel">
        <h2 style="margin:0; font-size:1.2rem;">Git Inspector</h2>
        <div style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px;">Mapa de Versiones y Commits</div>
        <div style="margin-top:16px; font-size:0.75rem; color:var(--text-secondary);">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:5px;">
                <div style="width:10px; height:10px; border-radius:50%; background:#1f6feb;"></div> Rama Principal
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <div style="width:10px; height:10px; border-radius:50%; background:#1a7f37;"></div> Rama Lateral
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
    </div>

    <!-- Modal Commit Detail -->
    <div id="commit-modal" class="modal-overlay" onclick="if(event.target===this) this.style.display='none'">
        <div class="modal-content">
            <div class="modal-header">
                <div style="flex:1;">
                    <h2 id="modal-title" style="margin:0; font-size:1.3rem; color:#e6edf3; margin-bottom:8px; line-height:1.4;"></h2>
                    <div id="modal-meta" style="color:var(--text-secondary); font-size:0.9rem;"></div>
                </div>
                <button class="close-btn" style="position:static; margin-left:16px; font-size:28px;" onclick="document.getElementById('commit-modal').style.display='none'">&times;</button>
            </div>
            <div class="modal-body">
                <div style="display:flex; gap:32px; margin-bottom: 24px; flex-wrap:wrap; background:rgba(255,255,255,0.03); padding:16px; border-radius:8px; border:1px solid var(--border-color);">
                    <div>
                        <div class="section-title" style="margin-top:0; color:#8b949e;">Identificador (SHA)</div>
                        <div id="modal-hash-container" style="display:flex; align-items:center;"></div>
                    </div>
                    <div>
                        <div class="section-title" style="margin-top:0; color:#8b949e;">Padres</div>
                        <div id="modal-parents-container" style="display:flex; align-items:center; gap:8px;"></div>
                    </div>
                </div>
                <div class="section-title" style="font-size:0.9rem; color:#8b949e; margin-bottom:12px;">Archivos Modificados y Cambios Reales (Diff)</div>
                <div id="modal-diff" class="diff-container" style="margin-top:0; border:none; padding:0;"></div>
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
        const nodes = new vis.DataSet(nodesData.map(n => ({
            ...n, shape: 'dot', size: 14, borderWidth: 2,
            color: { background: n.is_main ? '#1f6feb' : '#1a7f37', border: '#ffffff' },
            font: { color: '#e6edf3', face: 'Inter', size: 13 }
        })));
        const edges = new vis.DataSet(edgesData.map(e => ({
            ...e, color: { color: '#30363d', highlight: '#58a6ff' },
            dashes: e.is_parallel ? [5, 5] : false, width: 2
        })));

        const network = new vis.Network(container, { nodes, edges }, {
            layout: { hierarchical: { direction: 'UD', sortMethod: 'directed', levelSeparation: 150 } },
            interaction: { hover: false, dragNodes: false, zoomView: true, dragView: true },
            physics: { enabled: false }
        });

        // PARCHE: Evitar que el mapa siga el movimiento del cursor si el ratón se suelta fuera o si el DOM pierde el enfoque del click.
        // Esto desactiva el 'stuck drag' de vis-network soltando manualmente la cámara.
        window.addEventListener("pointerup", () => {
            if (typeof network !== 'undefined') {
                network.setOptions({ interaction: { dragView: false } });
                network.setOptions({ interaction: { dragView: true } });
            }
        });

        if (globalSearchData && globalSearchData.total > 0) {
            document.getElementById('nav-search').style.display = 'block';
            setTimeout(() => {
                setPanelTab('search');
                openPanel();
            }, 500);
        }

        network.on("click", (params) => {
            // Desenlazar un posible enganche del drag después de click
            network.setOptions({ interaction: { dragView: false } });
            network.setOptions({ interaction: { dragView: true } });
            
            if (params.nodes.length > 0) {
                const tagSha = params.nodes[0];
                const node = nodes.get(tagSha);
                selectedNode = node;
                // Por defecto cargamos el commit del tag
                const commit = historyData.find(c => c.full_hash === tagSha || c.hash === node.hash);
                if (commit) {
                    selectedCommit = commit;
                    openPanel();
                }
            } else {
                closePanel();
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

        function mostrarTooltipCopiado(event) {
            const tt = document.createElement('div');
            tt.textContent = '¡Copiado!';
            Object.assign(tt.style, {
                position: 'fixed', background: '#2ea043', color: '#fff', padding: '4px 8px', borderRadius: '4px',
                fontSize: '12px', zIndex: '10000', left: (event.clientX + 10) + 'px', top: (event.clientY + 10) + 'px',
                pointerEvents: 'none', animation: 'modalFadeIn 0.2s'
            });
            document.body.appendChild(tt);
            setTimeout(() => tt.remove(), 1200);
        }

        function showCommitModal(hash) {
            let commit = historyData.find(c => c.full_hash === hash || c.hash === hash);
            if (!commit && typeof globalSearchData !== 'undefined' && globalSearchData && globalSearchData.resultados) {
                commit = globalSearchData.resultados.find(c => c.full_hash === hash || c.hash === hash);
            }
            if (!commit) return;
            
            const msgList = (commit.mensaje_full || commit.mensaje || '').split('\\n');
            document.getElementById('modal-title').textContent = msgList[0];
            document.getElementById('modal-meta').innerHTML = `👤 <strong style="color:#e6edf3;">${escapeHtml(commit.autor)}</strong> &nbsp;•&nbsp; 📅 ${commit.fecha}`;
            
            document.getElementById('modal-hash-container').innerHTML = `
                <div class="hash-code" style="font-size:0.95rem;">${commit.full_hash || commit.hash}</div>
                ${getCopyBtnHtml(commit.full_hash || commit.hash)}
            `;
            
            const pContainer = document.getElementById('modal-parents-container');
            if (commit.parents && commit.parents.length > 0) {
                pContainer.innerHTML = commit.parents.map(ph => `
                    <div style="display:flex; align-items:center;">
                        <span class="gs-node-link" style="margin:0; font-family:'JetBrains Mono',monospace; font-size:0.85rem;" onclick="document.getElementById('commit-modal').style.display='none'; if(typeof gsNavParent==='function'){gsNavParent('${ph}');}else{selectCommitByHash('${ph}');}">↑ ${ph}</span>
                        ${getCopyBtnHtml(ph)}
                    </div>
                `).join('');
            } else {
                pContainer.innerHTML = '<span style="color:var(--text-secondary); font-size:0.85rem;">Ninguno (Raíz)</span>';
            }
            
            let rawDiff = commit.diff && commit.diff.length > 5 ? commit.diff : "No se detectaron cambios en archivos o diff no disponible.";
            document.getElementById('modal-diff').innerHTML = formatDiff(rawDiff);
            
            document.getElementById('commit-modal').style.display = 'flex';
        }


        function highlightNode(nodeId) {
            // Limpiar highlight anterior
            if (lastHighlightedNode) {
                const old = nodes.get(lastHighlightedNode);
                if (old) {
                    nodes.update({ id: lastHighlightedNode, color: { background: old.is_main ? '#1f6feb' : '#1a7f37', border: '#ffffff' } });
                }
            }
            // Aplicar nuevo highlight (color dorado/ámbar para indicar "este es el origen")
            nodes.update({ id: nodeId, color: { background: '#ffa000', border: '#ffd54f' } });
            lastHighlightedNode = nodeId;
        }

        function openPanel() {
            document.getElementById('side-panel').classList.add('open');
            renderPanel();
        }

        function closePanel() {
            document.getElementById('side-panel').classList.remove('open');
            // Limpiar highlights al cerrar
            if (lastHighlightedNode) {
                const old = nodes.get(lastHighlightedNode);
                if (old) nodes.update({ id: lastHighlightedNode, color: { background: old.is_main ? '#1f6feb' : '#1a7f37', border: '#ffffff' } });
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
                    <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:24px;">
                        ${(selectedCommit.parents && selectedCommit.parents.length > 0)
                            ? selectedCommit.parents.map((ph, i) => {
                                const pFull = (selectedCommit.parents[i] || ph);
                                return `<div style="display:flex; align-items:center;">
                                    <span style="font-family:'JetBrains Mono',monospace; font-size:0.75rem; color:#58a6ff;
                                    background:rgba(88,166,255,0.08); border:1px solid rgba(88,166,255,0.2);
                                    border-radius:4px; padding:3px 8px; cursor:pointer;"
                                    onclick="gsNavParent && gsNavParent('${ph}')"
                                    title="Ir al commit padre ${ph}">↑ ${ph} ↗</span>
                                    ${getCopyBtnHtml(ph)}
                                    </div>`;
                              }).join('')
                            : '<span style="font-size:0.75rem;color:var(--text-secondary);">Raíz — sin padre</span>'
                        }
                    </div>

                    <div style="background:rgba(47,129,247,0.1); padding:16px; border-radius:8px; border:1px solid rgba(47,129,247,0.2);">
                        <div class="section-title" style="margin-top:0; color:#58a6ff;">Analizar Cambios Reales</div>
                        <div style="font-size:0.8rem; color:#8b949e; margin-bottom:12px; line-height:1.4;">
                            Visualice gráficamente los archivos modificados, adiciones y supresiones que generó este commit.
                        </div>
                        <button onclick="showCommitModal('${selectedCommit.full_hash}')" 
                                style="background:#238636; border:1px solid rgba(240,246,252,0.1); color:#fff; padding:10px; border-radius:6px; cursor:pointer; font-weight:600; font-size:0.85rem; width:100%; display:flex; justify-content:center; align-items:center; gap:8px; transition:0.2s;"
                                onmouseover="this.style.background='#2ea043'" onmouseout="this.style.background='#238636'">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M1.75 2.5a.25.25 0 0 0-.25.25v10.5c0 .138.112.25.25.25h12.5a.25.25 0 0 0 .25-.25v-8.5h-4a2 2 0 0 1-2-2v-4H1.75ZM7.5 4.51V1.535a.25.25 0 0 1 .427-.177l4.683 4.683A.25.25 0 0 1 12.433 6.5H9.5a2 2 0 0 1-2-1.99ZM10.5 8h-5a.75.75 0 0 0 0 1.5h5a.75.75 0 0 0 0-1.5Zm-5 3.5h5a.75.75 0 0 0 0-1.5h-5a.75.75 0 0 0 0 1.5Z"/></svg>
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
                            <div class="ce-item ${selectedCommit && selectedCommit.hash == r.hash ? 'active' : ''}" onclick='selectCommitByHash("${r.full_hash}")' style="border-left: 3px solid #58a6ff;">
                                <div>
                                    <div class="ce-hash">${r.hash} <span style="font-size:0.65rem; background:var(--accent-primary); padding:2px 4px; border-radius:3px; color:white; margin-left:4px;">${escapeHtml(r.tipo)}</span></div>
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

        function selectCommitByHash(hash) {
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
                
                // Destacar nodo en que habita (si está asociado a uno)
                const ownerNodeSha = commitToTag[c.full_hash] || commitToTag[c.hash];
                if (ownerNodeSha) {
                    highlightNode(ownerNodeSha);
                    network.focus(ownerNodeSha, { scale: 1.2, animation: true });
                }
            }
        }

        function formatDiff(txt) {
            return txt.split('\\n').map(line => {
                const escaped = escapeHtml(line);
                if (line.startsWith('diff --git')) return `\\n<div style="background:#161b22; padding:10px 14px; border-radius:6px; font-weight:600; border-left:4px solid #2f81f7; color:#e6edf3; margin-top:20px; font-size:0.85rem; box-shadow:0 4px 12px rgba(0,0,0,0.5);">📄 Archivo: <span style="color:#58a6ff;">${escaped.replace('diff --git ', '')}</span></div>`;
                if (line.match(/^index [0-9a-f]+\\.\\.[0-9a-f]+/)) return `<div style="color:#7d8590; font-size:0.75rem; padding-left:14px; margin-bottom:8px;">${escaped}</div>`;
                if (line.startsWith('--- a/') || line.startsWith('+++ b/')) return `<div style="color:#8b949e; font-size:0.78rem; padding-left:14px;">${escaped}</div>`;
                if (line.startsWith('+') && !line.startsWith('+++')) return `<div class="diff-added" style="padding:1px 14px; background:rgba(46,160,67,0.15); color:#3FB950;">${escaped}</div>`;
                if (line.startsWith('-') && !line.startsWith('---')) return `<div class="diff-removed" style="padding:1px 14px; background:rgba(248,81,73,0.15); color:#F85149;">${escaped}</div>`;
                if (line.startsWith('@@')) return `<div class="diff-info" style="margin:12px 0 6px; padding:6px 14px; background:rgba(88,166,255,0.1); border-radius:4px; font-weight:600; color:#58a6ff;">${escaped}</div>`;
                return `<div style="padding:1px 14px;">${escaped}</div>`;
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

