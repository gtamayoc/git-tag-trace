#!/usr/bin/env python3
"""
Analizador Técnico Offline de Repositorio Git
Uso: python main.py <ruta_repositorio> [--output archivo.md]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from git import Commit, Repo

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from git import Commit, Repo
except ImportError:
    print("[ERROR] GitPython no está instalado. Ejecuta start.bat para configurar el entorno.")
    sys.exit(1)

from gitsearch.incremental import (
    cargar_estado,
    detectar_cambios,
    generar_info_incremental,
    guardar_estado,
    ruta_data_json,
    ruta_reporte_html,
    ruta_reporte_md,
)

_GITSEARCH_OK: bool = False
_gs_generar_panel: Any = None

try:
    from gitsearch.html_builder import generar_panel_busqueda as _gs_generar_panel

    _GITSEARCH_OK = True
except ImportError:
    pass


# ──────────────────────────────────────────────
# SECCIÓN 1 — HISTORIAL
# ──────────────────────────────────────────────


MAX_DIFF_CACHE_SIZE = 1000


def _fetch_diff_batch(shas: list[str], repo_path: str) -> dict[str, str]:
    """Fetch diffs for multiple commits in a single git command using git log -p."""
    from git import Repo

    diff_map: dict[str, str] = {}
    try:
        repo_local = Repo(repo_path)
        batch_size = 150
        max_diffs = min(len(shas), MAX_DIFF_CACHE_SIZE)
        for i in range(0, max_diffs, batch_size):
            batch = shas[i : i + batch_size]
            try:
                raw = repo_local.git.log(
                    "--all", "--no-walk", *batch, "-p", "--stat", "--no-color", "--format="
                )
                commits_in_batch = raw.split("commit ")
                for commit_block in commits_in_batch[1:]:
                    lines = commit_block.split("\n")
                    if not lines:
                        continue
                    sha = lines[0].strip()
                    if len(sha) >= 7:
                        sha = sha[:7]
                    diff_content = "commit " + commit_block
                    if len(diff_content) > 4000:
                        diff_content = (
                            diff_content[:4000] + "\n\n... (diff truncado por tamaño) ..."
                        )
                    if len(diff_map) < MAX_DIFF_CACHE_SIZE:
                        diff_map[sha] = diff_content
            except Exception:
                pass
    except Exception:
        pass
    return diff_map


def obtener_historial(repo: Repo, max_commits: int = 1500) -> dict[str, Any]:
    STASH_PREFIXES = (
        "On ",
        "index on ",
        "WIP on ",
        "untracked files on ",
    )

    def es_stash(commit: Any) -> bool:
        msg = commit.message.strip().lower()
        return any(msg.startswith(p.lower()) for p in STASH_PREFIXES)

    try:
        refs = list(repo.heads) + list(repo.remotes[0].refs if repo.remotes else [])
        seen: set[str] = set()
        commits = []
        for ref in refs:
            for c in repo.iter_commits(ref, max_count=max_commits):
                if c.hexsha not in seen and not es_stash(c):
                    seen.add(c.hexsha)
                    commits.append(c)
                    if len(commits) >= max_commits:
                        break
            if len(commits) >= max_commits:
                break
        commits.sort(key=lambda c: c.committed_date, reverse=True)
        if len(commits) > max_commits:
            commits = commits[:max_commits]
    except Exception:
        commits = [c for c in repo.iter_commits(max_count=max_commits) if not es_stash(c)]

    if not commits:
        return {"commits": [], "total": 0, "autores": {}, "fecha_inicio": None, "fecha_fin": None}

    autores = Counter(c.author.name for c in commits)
    fechas = sorted(c.committed_datetime for c in commits)

    total_commits = len(commits)
    print(f"[INFO] Procesando {total_commits} commits (diffs en paralelo)...")

    shas_all = [c.hexsha for c in commits]

    repo_path = str(repo.working_dir)
    diff_cache: dict[str, str] = {}

    max_workers = min(8, (os.cpu_count() or 4))
    batch_size = 100
    diff_futures = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i in range(0, len(shas_all), batch_size):
            batch = shas_all[i : i + batch_size]
            future = executor.submit(_fetch_diff_batch, batch, repo_path)
            diff_futures.append(future)

        for completed, future in enumerate(as_completed(diff_futures), start=1):
            try:
                result = future.result()
                diff_cache.update(result)
            except Exception:
                pass
            if completed % 5 == 0 or completed == len(diff_futures):
                pct = int(completed / len(diff_futures) * 100)
                print(
                    f"\r[INFO] Diffs: {completed}/{len(diff_futures)} ({pct}%)", end="", flush=True
                )

    print()

    from_timestamp = datetime.fromtimestamp
    strftime_fmt = "%Y-%m-%d %H:%M"

    lista: list[dict[str, Any]] = []
    for idx, c in enumerate(commits):
        if idx % 1000 == 0 and idx > 0:
            print(
                f"[INFO] Progreso commits: {idx}/{total_commits} ({int(idx / total_commits * 100)}%)"
            )

        msg_lines = c.message.strip().splitlines()
        first_line = msg_lines[0][:80] if msg_lines else "Sin mensaje"

        commit_hexsha = c.hexsha
        parents_hashes = [p.hexsha for p in c.parents]

        diff_preview = diff_cache.get(commit_hexsha[:7], "")
        if not diff_preview and len(lista) < 50:
            try:
                diff_preview = repo.git.show(
                    commit_hexsha, "-p", "--stat", "--no-color", "--format=", max_count=1
                )
                if len(diff_preview) > 4000:
                    diff_preview = diff_preview[:4000] + "\n\n... (diff truncado por tamaño) ..."
            except Exception:
                diff_preview = "(Error cargando diff)"

        lista.append(
            {
                "hash": commit_hexsha[:7],
                "full_hash": commit_hexsha,
                "autor": c.author.name,
                "fecha": from_timestamp(c.committed_date).strftime(strftime_fmt),
                "mensaje": first_line,
                "mensaje_full": c.message.strip(),
                "parents": parents_hashes,
                "diff": diff_preview,
            }
        )

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


def obtener_tags(repo: Repo) -> list[dict[str, Any]]:
    """Obtiene todos los tags del repositorio con su metadata."""
    tags = []
    for tag in repo.tags:
        try:
            # Formato ISO para ordenamiento interno
            fecha_iso = ""
            if tag.tag:  # tag anotado
                commit = tag.tag.object
                fecha = datetime.fromtimestamp(tag.tag.tagged_date).strftime("%Y-%m-%d")
                fecha_iso = datetime.fromtimestamp(tag.tag.tagged_date).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                autor = tag.tag.tagger.name
            else:  # tag ligero
                commit = tag.commit
                fecha = datetime.fromtimestamp(commit.committed_date).strftime("%Y-%m-%d")
                fecha_iso = datetime.fromtimestamp(commit.committed_date).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                autor = commit.author.name

            tags.append(
                {
                    "nombre": tag.name,
                    "fecha": fecha,
                    "fecha_iso": fecha_iso,
                    "autor": autor,
                    "hash": commit.hexsha[:7] if hasattr(commit, "hexsha") else "N/A",
                    "hash_completo": commit.hexsha if hasattr(commit, "hexsha") else "N/A",
                    "es_semver": tag.name.startswith("v") and tag.name[1:2].isdigit(),
                }
            )
        except Exception:
            tags.append(
                {
                    "nombre": tag.name,
                    "fecha": "N/A",
                    "fecha_iso": "",
                    "autor": "N/A",
                    "hash": "N/A",
                    "hash_completo": "N/A",
                    "es_semver": False,
                }
            )

    return sorted(tags, key=lambda t: t["fecha_iso"] if t["fecha_iso"] else t["fecha"])


# ──────────────────────────────────────────────
# SECCIÓN 3 — ANÁLISIS TOPOLÓGICO DEL GRAFO GIT
# ──────────────────────────────────────────────


def comparar_tags(repo: Repo, tags: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compara los dos últimos tags (topológicamente) y retorna diferencias."""
    if len(tags) < 2:
        return None

    tag_anterior = tags[-2]["nombre"]
    tag_actual = tags[-1]["nombre"]

    try:
        c_actual = repo.commit(tags[-1]["hash_completo"])
        c_anterior = repo.commit(tags[-2]["hash_completo"])
        bases = repo.merge_base(c_anterior, c_actual)
        base = bases[0] if bases else c_anterior

        # Commits exclusivos de tag_actual respecto al punto de divergencia
        commits_entre = list(repo.iter_commits(f"{base.hexsha}..{c_actual.hexsha}", max_count=2000))
        autores = list({c.author.name for c in commits_entre})

        archivos_modificados = set()
        try:
            diff = base.diff(c_actual)
            for d in diff:
                if d.a_path:
                    archivos_modificados.add(d.a_path)
                if d.b_path:
                    archivos_modificados.add(d.b_path)
        except Exception:
            pass

        lista_commits = [
            {
                "hash": c.hexsha[:7],
                "autor": c.author.name,
                "fecha": datetime.fromtimestamp(c.committed_date).strftime("%Y-%m-%d %H:%M"),
                "mensaje": c.message.strip().splitlines()[0][:80],
            }
            for c in commits_entre
        ]

        return {
            "tag_anterior": tag_anterior,
            "tag_actual": tag_actual,
            "total_commits": len(commits_entre),
            "autores": autores,
            "archivos_modificados": sorted(archivos_modificados),
            "total_archivos": len(archivos_modificados),
            "commits": lista_commits,
        }

    except Exception as e:
        return {"error": str(e)}


# ── 3a. Construcción del mapa completo de commits (DAG) ──────────────────────


MAX_COMMITS_MAP = 3000


def construir_mapa_commits(repo: Repo) -> dict[str, Any]:
    """
    Recorre refs (branches locales, remotas, tags) y construye un dict
    {hexsha_completo: commit_obj} con commits accesibles del repo.
    Excluye refs de stash para no contaminar el grafo.
    Usa límite para evitar consumo excesivo de memoria.
    """
    STASH_PREFIXES = ("refs/stash", "stash@")
    seen: dict[str, Any] = {}

    def _walk(ref_commit: Any) -> None:
        if len(seen) >= MAX_COMMITS_MAP:
            return
        stack = [ref_commit]
        while stack and len(seen) < MAX_COMMITS_MAP:
            c = stack.pop()
            if c.hexsha in seen:
                continue
            seen[c.hexsha] = c
            stack.extend(c.parents)

    for head in repo.heads:
        if len(seen) >= MAX_COMMITS_MAP:
            break
        with suppress(Exception):
            _walk(head.commit)

    for remote in repo.remotes:
        if len(seen) >= MAX_COMMITS_MAP:
            break
        for ref in remote.refs:
            if len(seen) >= MAX_COMMITS_MAP:
                break
            if any(ref.name.startswith(p) for p in STASH_PREFIXES):
                continue
            with suppress(Exception):
                _walk(ref.commit)

    for tag in repo.tags:
        if len(seen) >= MAX_COMMITS_MAP:
            break
        with suppress(Exception):
            _walk(tag.commit)

    return seen


# ── 3b. Identificar ramas que contienen cada tag ─────────────────────────────


def identificar_ramas_de_tag(
    repo: Repo, commit_sha: str, sha_a_ramas: dict[str, list[str]] | None = None
) -> list[str]:
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
                    nombre = nombre[len("remotes/") :]
                ramas.append(nombre)
    except Exception:
        pass
    return sorted(set(ramas))


def _construir_sha_a_ramas(repo: Repo) -> dict[str, list[str]]:
    """
    Construye un dict {sha: [rama1, rama2, ...]} en UNA SOLA llamada git.
    Lee git log --decorate=full para extraer ref-names de cada commit.
    """
    raw = repo.git.log("--all", "--pretty=format:%H %D")
    sha_a_ramas_direct: dict[str, list[str]] = {}

    for line in raw.splitlines():
        if not line.strip():
            continue
        idx_sep = line.index(" ") if " " in line else -1
        if idx_sep < 0:
            continue
        sha = line[:idx_sep].strip()
        deco = line[idx_sep + 1 :].strip()
        if not deco:
            continue
        ramas = []
        for parte in deco.split(","):
            parte = parte.strip()
            if parte.startswith("HEAD ->"):
                rama = parte[len("HEAD ->") :].strip()
                if rama:
                    ramas.append(rama)
            elif parte.startswith("refs/heads/"):
                ramas.append(parte[len("refs/heads/") :])
            elif parte.startswith("refs/remotes/"):
                ramas.append(parte[len("refs/remotes/") :])
            elif "/" in parte and not parte.startswith("tag:"):
                ramas.append(parte)
        if ramas:
            sha_a_ramas_direct[sha] = ramas

    return sha_a_ramas_direct


# ── 3c. Commits exclusivos por tag (usando merge_base) ───────────────────────


def calcular_commits_exclusivos_tag(
    repo: Repo,
    commit_tag: Commit,
    commit_padre_tag: Commit,
) -> dict[str, Any]:
    """
    Calcula los commits que están en commit_tag pero NO en commit_padre_tag,
    usando merge_base para encontrar el punto de divergencia exacto.
    Esto funciona correctamente con ramas paralelas y merges.
    """
    from_timestamp = datetime.fromtimestamp
    strftime_fmt = "%Y-%m-%d %H:%M"

    try:
        bases = repo.merge_base(commit_padre_tag, commit_tag)
        base = bases[0] if bases else commit_padre_tag

        commits = list(repo.iter_commits(f"{base.hexsha}..{commit_tag.hexsha}", max_count=2000))

        commits_data = []
        autores_set = set()
        archivos_set = set()

        for c in commits:
            autores_set.add(c.author.name)
            message = c.message
            commits_data.append(
                {
                    "hash": c.hexsha[:7],
                    "full_hash": c.hexsha,
                    "autor": c.author.name,
                    "mensaje": message.strip().splitlines()[0][:80] if message else "",
                    "mensaje_full": message.strip() if message else "",
                    "fecha": from_timestamp(c.committed_date).strftime(strftime_fmt),
                    "parents": [p.hexsha[:7] for p in c.parents],
                }
            )

        try:
            diff = base.diff(commit_tag)
            for d in diff:
                if d.a_path:
                    archivos_set.add(d.a_path)
                elif d.b_path:
                    archivos_set.add(d.b_path)
        except Exception:
            pass

        dias = 0
        try:
            delta = from_timestamp(commit_tag.committed_date) - from_timestamp(base.committed_date)
            dias = delta.days
        except Exception:
            pass

        return {
            "num_commits": len(commits),
            "autores": sorted(autores_set),
            "num_archivos": len(archivos_set),
            "archivos": sorted(archivos_set),
            "commits_list": commits_data,
            "dias": dias,
            "merge_base_sha": base.hexsha[:7],
        }

    except Exception as e:
        print(f"[DEBUG] Error en calcular_commits_exclusivos_tag: {e}")
        return {
            "num_commits": 0,
            "autores": [],
            "num_archivos": 0,
            "archivos": [],
            "commits_list": [],
            "dias": 0,
            "merge_base_sha": "N/A",
        }


def calcular_commits_exclusivos_batch(
    repo_path: str,
    tasks: list[tuple[str, str, str]],
) -> dict[str, dict[str, Any]]:
    """Calculate exclusive commits for multiple tag pairs in parallel."""
    from git import Repo

    from_timestamp = datetime.fromtimestamp
    strftime_fmt = "%Y-%m-%d %H:%M"

    results: dict[str, dict[str, Any]] = {}

    for sha, padre_sha, key in tasks:
        try:
            repo_local = Repo(repo_path)
            commit_tag = repo_local.commit(sha)
            commit_padre_tag = repo_local.commit(padre_sha)

            bases = repo_local.merge_base(commit_padre_tag, commit_tag)
            base = bases[0] if bases else commit_padre_tag

            commits = list(
                repo_local.iter_commits(f"{base.hexsha}..{commit_tag.hexsha}", max_count=2000)
            )

            commits_data = []
            autores_set = set()
            archivos_set = set()

            for c in commits:
                autores_set.add(c.author.name)
                message = c.message
                commits_data.append(
                    {
                        "hash": c.hexsha[:7],
                        "full_hash": c.hexsha,
                        "autor": c.author.name,
                        "mensaje": message.strip().splitlines()[0][:80] if message else "",
                        "mensaje_full": message.strip() if message else "",
                        "fecha": from_timestamp(c.committed_date).strftime(strftime_fmt),
                        "parents": [p.hexsha[:7] for p in c.parents],
                    }
                )

            try:
                diff = base.diff(commit_tag)
                for d in diff:
                    if d.a_path:
                        archivos_set.add(d.a_path)
                    elif d.b_path:
                        archivos_set.add(d.b_path)
            except Exception:
                pass

            dias = 0
            try:
                delta = from_timestamp(commit_tag.committed_date) - from_timestamp(
                    base.committed_date
                )
                dias = delta.days
            except Exception:
                pass

            results[key] = {
                "num_commits": len(commits),
                "autores": sorted(autores_set),
                "num_archivos": len(archivos_set),
                "archivos": sorted(archivos_set),
                "commits_list": commits_data,
                "dias": dias,
                "merge_base_sha": base.hexsha[:7],
            }
        except Exception:
            results[key] = {
                "num_commits": 0,
                "autores": [],
                "num_archivos": 0,
                "archivos": [],
                "commits_list": [],
                "dias": 0,
                "merge_base_sha": "N/A",
            }

    return results


# ── 3d. Análisis topológico: aristas reales entre tags ───────────────────────


def analizar_topologia_tags(repo: Repo, tags: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Determina los ancestros directos (padres de tag) en el DAG real usando
    un recorrido topológico único. Agrupa tags asociados al mismo commit.
    """
    if not tags:
        return {}

    print("[INFO] Resolviendo commits de tags...")
    sha_a_tags_list: dict[str, list[str]] = {}
    tag_to_obj: dict[str, Any] = {}

    for t in tags:
        sha = t.get("hash_completo", "N/A")
        if sha == "N/A":
            continue
        sha_a_tags_list.setdefault(sha, []).append(t["nombre"])
        if t["nombre"] not in tag_to_obj:
            with suppress(Exception):
                tag_to_obj[t["nombre"]] = repo.commit(sha)

    if not sha_a_tags_list:
        return {}

    print(f"[INFO] {len(tags)} tags en {len(sha_a_tags_list)} commits únicos. Leyendo grafo...")

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
        sha = parts[0]
        pars = parts[1:]
        parent_map[sha] = pars
        topo_order.append(sha)

    print("[INFO] Construyendo mapa sha -> ramas...")
    sha_a_ramas_direct = _construir_sha_a_ramas(repo)

    sha_al_rama_activo: dict[str, set[str]] = {}
    for sha in reversed(topo_order):
        ramas_aqui = set(sha_a_ramas_direct.get(sha, []))
        sha_al_rama_activo.setdefault(sha, set()).update(ramas_aqui)
        for p_sha in parent_map.get(sha, []):
            sha_al_rama_activo.setdefault(p_sha, set()).update(sha_al_rama_activo.get(sha, set()))

    sha_a_ramas_completo: dict[str, list[str]] = {
        sha: sorted(ramas) for sha, ramas in sha_al_rama_activo.items()
    }

    commit_cache: dict[str, Any] = {}

    def get_commit_cached(sha: str) -> Any:
        if sha not in commit_cache:
            commit_cache[sha] = repo.commit(sha)
        return commit_cache[sha]

    topo_index = {sha: i for i, sha in enumerate(topo_order)}

    resultado = {}
    for sha, tnames in sha_a_tags_list.items():
        rep_tag = tnames[0]
        commit = tag_to_obj.get(rep_tag)
        if not commit:
            continue
        resultado[sha] = {
            "all_tags": tnames,
            "commit": commit,
            "padres_shas": [],
            "ramas": identificar_ramas_de_tag(repo, sha, sha_a_ramas_completo),
            "stats": {},
        }

    tags_vistos_en_commit: dict[str, set[str]] = {}

    print(f"[INFO] Resolviendo topología de {len(sha_a_tags_list)} tags...")
    processed = 0

    for sha in reversed(topo_order):
        processed += 1
        if processed % 100 == 0:
            print(
                f"\r[INFO] Topología: {processed}/{len(topo_order)} commits procesados",
                end="",
                flush=True,
            )

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
                sha_to_parents = {s: set(parent_map.get(s, [])) for s in candidatos}
                sha_to_idx = {s: topo_index.get(s, -1) for s in candidatos}

                for cand_sha in candidatos:
                    cand_idx = sha_to_idx.get(cand_sha, -1)
                    is_child_of_any_other = False
                    for otro_sha in candidatos:
                        if otro_sha == cand_sha:
                            continue
                        otro_idx = sha_to_idx.get(otro_sha, -1)
                        if (
                            otro_idx >= 0
                            and cand_idx >= 0
                            and cand_idx > otro_idx
                            and otro_sha in sha_to_parents.get(cand_sha, set())
                        ):
                            is_child_of_any_other = True
                            break
                    if not is_child_of_any_other:
                        padres_directos.append(cand_sha)

            resultado[sha]["padres_shas"] = padres_directos
            tags_vistos_en_commit[sha] = {sha}
        else:
            tags_vistos_en_commit[sha] = tags_heredados

    print()

    stats_tasks: list[tuple[str, str, str]] = []
    for sha, info in resultado.items():
        padres = info.get("padres_shas", [])
        if padres:
            stats_tasks.append((sha, padres[0], sha))

    if stats_tasks:
        print(f"[INFO] Calculando stats en paralelo para {len(stats_tasks)} tags...")
        repo_path = str(repo.working_dir)
        max_workers = min(8, (os.cpu_count() or 4))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i in range(0, len(stats_tasks), 20):
                batch = stats_tasks[i : i + 20]
                future = executor.submit(calcular_commits_exclusivos_batch, repo_path, batch)
                futures.append(future)

            for completed, future in enumerate(as_completed(futures), start=1):
                try:
                    batch_results = future.result()
                    for key, stats in batch_results.items():
                        if key in resultado:
                            resultado[key]["stats"] = stats
                except Exception as e:
                    print(f"\n[WARN] Error en batch de stats: {e}")
                if completed % 5 == 0 or completed == len(futures):
                    pct = int(completed / len(futures) * 100)
                    print(
                        f"\r[INFO] Stats: {completed}/{len(futures)} batches ({pct}%)",
                        end="",
                        flush=True,
                    )

        print()
    else:
        for value in resultado.values():
            value["stats"] = {
                "num_commits": 0,
                "autores": [],
                "num_archivos": 0,
                "archivos": [],
                "commits_list": [],
                "dias": 0,
                "merge_base_sha": "(raíz)",
            }

    aristas = sum(len(v["padres_shas"]) for v in resultado.values())
    print(f"[INFO] Topología completa: {aristas} aristas entre {len(resultado)} nodos de versión.")
    return resultado


def generar_grafo_html(
    repo: Repo,
    tags: list[dict[str, Any]],
    topologia: dict[str, Any] | None = None,
    historial: dict[str, Any] | None = None,
    busqueda: dict[str, Any] | None = None,
    panel_busqueda: str = "",
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Genera un archivo HTML con un grafo interactivo de los tags y un explorador de commits."""
    if not tags:
        return (
            "<html><body style='font-family:sans-serif; padding:50px;'><h1>No se encontraron tags</h1><p>El repositorio requiere al menos un tag para generar el grafo.</p></body></html>",
            [],
            [],
        )

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Agrupar tags por SHA
    tags_by_sha: dict[str, list[dict[str, Any]]] = {}
    for t in tags:
        sha = t.get("hash_completo", "N/A")
        if sha == "N/A":
            continue
        tags_by_sha.setdefault(sha, []).append(t)

    shas_ordenados = sorted(
        tags_by_sha.keys(), key=lambda s: tags_by_sha[s][0].get("fecha_iso") or ""
    )

    # Gap #3: Parser semver para categorizar importancia de nodos
    import re as _re

    SEMVER_RE = _re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-.](\w[\w.\-]*))?$")

    def parsear_semver(tag_nombre: str) -> tuple[int, int, int] | None:
        m = SEMVER_RE.match(tag_nombre)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return None

    def calcular_tamano_tag(tags_en_sha: list[dict[str, Any]]) -> float:
        """Mayor tamaño para major versions altos; base 13px, escala con semver."""
        max_major = 0
        for t in tags_en_sha:
            sv = parsear_semver(t.get("nombre", ""))
            if sv:
                max_major = max(max_major, sv[0])
        base = 13.0
        if max_major >= 5:
            return base + 9.0
        if max_major >= 3:
            return base + 6.0
        if max_major >= 1:
            return base + 3.0
        return base

    import re

    # 1. Configurar y limpiar prefijos explícitos del .env (para evitar whitespaces o comillas)
    # Si un tag empieza con alguno de estos, se cortará por completo.
    env_prefixes = os.getenv("TAG_PREFIXES", "")
    PREFIJOS_LIMPIAR: list[str] = [
        p.strip().strip("'\"") for p in env_prefixes.split(",") if p.strip().strip("'\"")
    ]
    # Ordenar de mayor a menor longitud para que el match sea exacto (greedy)
    PREFIJOS_LIMPIAR.sort(key=len, reverse=True)

    # 2. Detectar automáticamente prefijos comunes compartidos para hacer resúmenes (ej: vtr-250812)
    # Busca un patrón tipo "palabra-palabra-", "palabra_palabra_", etc.
    prefix_pattern = re.compile(r"^([a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)*[-_])")
    prefix_counts: dict[str, int] = Counter()
    tag_to_prefix: dict[str, str] = {}

    for t in tags:
        nombre_tag = t.get("nombre", "")
        m = prefix_pattern.search(nombre_tag)
        if m:
            pfx = m.group(1)
            # Validar que el prefijo no es el tag completo
            if len(pfx) < len(nombre_tag):
                prefix_counts[pfx] += 1
                tag_to_prefix[nombre_tag] = pfx

    def generar_acronimo(pfx: str) -> str:
        """Genera un acrónimo del prefijo (ej: 'v-tag-release-' -> 'vtr-')"""
        sep = "-" if "-" in pfx else "_"
        partes = re.split(r"[-_]", pfx)
        acronimo = "".join(parte[0].lower() for parte in partes if parte)
        return acronimo + sep

    def limpiar_label(nombre: str) -> str:
        # A. Prefijos explícitos (.env): se eliminan completamente de forma case-insensitive
        for pfx in PREFIJOS_LIMPIAR:
            if nombre.lower().startswith(pfx.lower()):
                # Mantener el case original del resto de la cadena
                return nombre[len(pfx) :]

        # B. Detección automática de prefijo común (más de 1 tag lo usa)
        pfx = tag_to_prefix.get(nombre)
        if pfx and prefix_counts.get(pfx, 0) > 1:
            acronimo = generar_acronimo(pfx)
            # Reemplazar la parte del prefijo con el acrónimo
            return acronimo + nombre[len(pfx) :]

        return nombre

    RAMAS_PRINCIPALES = {"main", "master", "develop", "trunk"}

    def es_rama_principal(ramas: list[str]) -> bool:
        for r in ramas:
            n = r.split("/")[-1].lower()
            if n in RAMAS_PRINCIPALES:
                return True
        return False

    # Mapeo de commits a tags (para la búsqueda)
    commit_to_tag = {}

    for i, sha in enumerate(shas_ordenados):
        tags_en_sha = tags_by_sha[sha]
        rep_tag = tags_en_sha[0]

        topo_info = topologia.get(sha, {}) if topologia else {}
        ramas = topo_info.get("ramas", [])
        stats = topo_info.get("stats", {})
        padres = topo_info.get("padres_shas", [])
        es_main = es_rama_principal(ramas)

        # Mapear todos los commits exclusivos de este tag a este nodo
        for c_meta in stats.get("commits_list", []):
            commit_to_tag[c_meta["hash"]] = sha
            # También para full hashes si están disponibles
            if "full_hash" in c_meta:
                commit_to_tag[c_meta["full_hash"]] = sha

        label_name = ", ".join([limpiar_label(t["nombre"]) for t in tags_en_sha])
        if len(tags_en_sha) > 2:
            label_name = f"{limpiar_label(tags_en_sha[0]['nombre'])} (+{len(tags_en_sha) - 1})"

        title_txt = f"Tags: {', '.join(t['nombre'] for t in tags_en_sha)}\nFecha: {rep_tag['fecha']}\nAutor: {rep_tag['autor']}\nHash: {rep_tag['hash']}"

        nodes.append(
            {
                "id": sha,
                "label": label_name,
                "title": title_txt,
                "all_tags": tags_en_sha,
                "author": rep_tag["autor"],
                "date": rep_tag["fecha"],
                "hash": rep_tag["hash"],
                "full_hash": sha,
                "is_main": es_main,
                "ramas": ramas,
                "stats": stats,
                "value": i + 1,
                "size": calcular_tamano_tag(tags_en_sha),
            }
        )

        if topologia:
            for padre_sha in padres:
                n_exc = stats.get("num_commits", 0)
                n_arch = stats.get("num_archivos", 0)
                edge_label = ""
                if n_exc > 0:
                    edge_label = f"{n_exc} cmts" + (f" • {n_arch} files" if n_arch else "")

                edges.append(
                    {
                        "id": f"{padre_sha}_{sha}",
                        "from": padre_sha,
                        "to": sha,
                        "arrows": "to",
                        "label": edge_label,
                        "is_parallel": not es_main,
                        "n_archivos": n_arch,
                        "n_commits": n_exc,
                    }
                )
        elif i > 0:
            edges.append(
                {
                    "id": f"{shas_ordenados[i - 1]}_{sha}",
                    "from": shas_ordenados[i - 1],
                    "to": sha,
                    "arrows": "to",
                    "is_parallel": False,
                }
            )

    from gitsearch.template import get_html_template
    html_template = get_html_template()
    html = html_template.replace("__NODES_DATA__", json.dumps(nodes))
    html = html.replace("__EDGES_DATA__", json.dumps(edges))
    html = html.replace("__HISTORY_DATA__", json.dumps(historial["commits"] if historial else []))
    html = html.replace("__COMMIT_MAP__", json.dumps(commit_to_tag))
    html = html.replace("__GLOBAL_SEARCH__", json.dumps(busqueda) if busqueda else "null")
    html = html.replace("<!-- GITSEARCH_PANEL -->", panel_busqueda)
    return html, nodes, edges


# ──────────────────────────────────────────────
# SECCIÓN 3.5 — BÚSQUEDA PROFUNDA DE COMMIT / CÓDIGO
# ──────────────────────────────────────────────


def ejecutar_busqueda(repo: Repo, criterio: str, topologia: dict[str, Any]) -> dict[str, Any]:
    """
    Busca un hash, mensaje de commit, o línea de código (diff) en todo el repositorio.
    Utiliza -G (regex flexible) para diffs y --grep para mensajes.
    Devuelve un diccionario estructurado con los resultados para integrar en reporte y HTML.
    """
    import re

    print(f"[INFO] Ejecutando búsqueda profunda para: '{criterio}'...")

    shas_encontrados: dict[str, str] = {}

    # 1. ¿Es un hash de commit?
    es_posible_hash = re.match(r"^[0-9a-fA-F]{4,40}$", criterio.strip())
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
    regex_flexible = (
        ".*".join(re.escape(p) for p in partes) if len(partes) > 1 else re.escape(criterio)
    )

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
                        if d.a_path:
                            archivos.append(d.a_path)
                        elif d.b_path:
                            archivos.append(d.b_path)
                else:
                    for _d in c.tree.diff(None):
                        pass
            except Exception:
                pass

            resultados.append(
                {
                    "hash": hash_corto,
                    "full_hash": c.hexsha,
                    "tipo": tipo,
                    "mensaje": c.message.splitlines()[0][:100] if c.message else "Sin mensaje",
                    "autor": c.author.name,
                    "fecha": datetime.fromtimestamp(c.committed_date).strftime("%Y-%m-%d %H:%M"),
                    "tags": tags_del_commit,
                    "archivos": sorted(set(archivos)),
                }
            )
        except Exception:
            continue

    resultados.sort(key=lambda x: str(x["fecha"]), reverse=True)

    print(f"[INFO] Búsqueda finalizada. {len(resultados)} coincidencias encontradas.")
    return {"criterio": criterio, "total": len(resultados), "resultados": resultados}


# ──────────────────────────────────────────────
# SECCIÓN 4 — GENERACIÓN DEL REPORTE
# ──────────────────────────────────────────────


def generar_reporte(
    repo_path: str,
    historial: dict[str, Any],
    tags: list[dict[str, Any]],
    comparacion: dict[str, Any] | None,
    busqueda: dict[str, Any] | None = None,
) -> str:
    lineas = []

    def separador(titulo: str) -> None:
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
        lineas.append(f"    {'-' * 8} {'-' * 17} {'-' * 25} {'-' * 40}")
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
        lineas.append(f"    {'-' * 20} {'-' * 12} {'-' * 25} {'-' * 8}")
        for t in tags:
            marca = " ✔" if t["es_semver"] else ""
            lineas.append(
                f"    {t['nombre']:<20} {t['fecha']:<12} {t['autor']:<25} {t['hash']}{marca}"
            )

    # ── Sección 3
    separador("SECCIÓN 3 — COMPARACIÓN ENTRE TAGS")
    if comparacion is None:
        lineas.append("  [!] Se necesitan al menos 2 tags para comparar versiones.")
    elif "error" in comparacion:
        lineas.append(f"  [ERROR] No se pudo comparar tags: {comparacion['error']}")
    else:
        lineas.append(
            f"  Comparando: {comparacion['tag_anterior']}  →  {comparacion['tag_actual']}"
        )
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
            lineas.append(f"    {'-' * 8} {'-' * 17} {'-' * 25} {'-' * 40}")
            for c in comparacion["commits"]:
                lineas.append(
                    f"    {c['hash']:<8} {c['fecha']:<17} {c['autor']:<25} {c['mensaje']}"
                )

    # ── Sección 4 Búsqueda
    if busqueda:
        separador("SECCIÓN 4 — RESULTADOS DE BÚSQUEDA PROFUNDA")
        lineas.append(f"  Criterio buscado : '{busqueda['criterio']}'")
        lineas.append(f"  Total encontrados: {busqueda['total']}")
        lineas.append("")
        if busqueda["total"] > 0:
            for i, r in enumerate(busqueda["resultados"], 1):
                lineas.append(f"  {i}. {r['hash']} | Coincidencia: {r['tipo']}")
                lineas.append(f"     Mensaje : {r['mensaje']}")
                lineas.append(f"     Autor   : {r['autor']} | {r['fecha']}")
                lineas.append(
                    f"     Versión : {', '.join(r['tags']) if r['tags'] else 'Ninguno (Commit volátil/reciente)'}"
                )
                lineas.append(
                    f"     Archivos: {', '.join(r['archivos']) if r['archivos'] else 'Desconocidos'}"
                )
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


def main() -> None:
    """Función principal del analizador de repositorios Git."""
    parser = argparse.ArgumentParser(
        description="Analizador técnico offline de repositorio Git local."
    )
    parser.add_argument("repo_path", help="Ruta al repositorio Git local")
    parser.add_argument(
        "--output", "-o", help="Guardar reporte en archivo (.md o .txt)", default=None
    )
    parser.add_argument(
        "--search",
        "-s",
        help="Criterio de búsqueda (hash, texto descriptivo o fragmento de código)",
        default=None,
    )
    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()
    if not repo_path.exists():
        print(f"[ERROR] La ruta no existe: {repo_path}")
        sys.exit(1)

    base_results_dir = Path(__file__).parent / "results"
    project_name = repo_path.name
    results_dir = base_results_dir / project_name
    results_dir.mkdir(parents=True, exist_ok=True)

    with Repo(str(repo_path)) as repo:
        print(f"[INFO] Analizando repositorio: {repo_path}")

        estado_anterior = cargar_estado(results_dir)
        cambios = detectar_cambios(repo, estado_anterior)

        html_file = ruta_reporte_html(results_dir)
        output_filename = Path(args.output).name if args.output else "reporte.md"
        output_path = results_dir / output_filename if args.output else ruta_reporte_md(results_dir)
        data_file = ruta_data_json(results_dir)

        archivos_faltantes = (
            not html_file.exists() or not output_path.exists() or not data_file.exists()
        )

        if archivos_faltantes and not cambios["hay_cambios"]:
            cambios["hay_cambios"] = True
            cambios["tipo_cambios"].append("archivos_faltantes")

        info_cambios = generar_info_incremental(cambios)

        if not cambios["hay_cambios"]:
            print(
                f"[INFO] Repositorio no modificado. Resultados actuales válidos en: {html_file.resolve()}"
            )
            return

        print(f"[INFO] {info_cambios}")
        print("[INFO] Analizando repositorio y generando artefactos...")

        t_inicio = time.perf_counter()

        t0 = time.perf_counter()
        historial = obtener_historial(repo)
        print(f"[TIMER] obtener_historial: {time.perf_counter() - t0:.2f}s")

        t0 = time.perf_counter()
        tags = obtener_tags(repo)
        print(f"[TIMER] obtener_tags: {time.perf_counter() - t0:.2f}s")

        t0 = time.perf_counter()
        comparacion = comparar_tags(repo, tags)
        print(f"[TIMER] comparar_tags: {time.perf_counter() - t0:.2f}s")

        t0 = time.perf_counter()
        topologia = analizar_topologia_tags(repo, tags)
        print(f"[TIMER] analizar_topologia_tags: {time.perf_counter() - t0:.2f}s")

        busqueda = None
        if args.search:
            t0 = time.perf_counter()
            busqueda = ejecutar_busqueda(repo, args.search, topologia)
            print(f"[TIMER] ejecutar_busqueda: {time.perf_counter() - t0:.2f}s")

        t0 = time.perf_counter()
        reporte = generar_reporte(str(repo_path), historial, tags, comparacion, busqueda)
        print(f"[TIMER] generar_reporte: {time.perf_counter() - t0:.2f}s")

        print("[INFO] Generando grafo de tags y explorador de historial...")

        commits_data = historial["commits"]
        hash_estado = cambios["hash_actual"]
        hash_tags = cambios["hash_tags_actual"]

        datos_estado = {
            "tags": tags,
            "historial": historial,
            "topologia": topologia,
            "commits_data": commits_data,
            "comparacion": comparacion,
        }

        if _GITSEARCH_OK and _gs_generar_panel is not None:
            try:
                t_gs_inicio = datetime.now()
                panel_busqueda = _gs_generar_panel(commits_data)
                delta_ms = int((datetime.now() - t_gs_inicio).total_seconds() * 1000)
                print(f"[GitSearch] Panel de búsqueda preparado ({delta_ms} ms).")
            except Exception as _gs_err:
                print(f"[WARN] GitSearch panel no pudo generarse: {_gs_err}")
                panel_busqueda = ""
        else:
            panel_busqueda = ""

        t0 = time.perf_counter()
        grafo_html, nodes, edges = generar_grafo_html(
            repo, tags, topologia, historial, busqueda, panel_busqueda
        )
        print(f"[TIMER] generar_grafo_html: {time.perf_counter() - t0:.2f}s")

        guardar_estado(results_dir, datos_estado, hash_estado, hash_tags, nodes, edges)
        print(f"[INFO] Estado guardado en: {ruta_data_json(results_dir).resolve()}")

        output_filename = Path(args.output).name if args.output else "reporte.md"
        output_path = ruta_reporte_md(results_dir)
        if args.output:
            output_path = results_dir / output_filename

        with output_path.open("w", encoding="utf-8", errors="replace") as f:
            f.write(reporte)
        print(f"[INFO] Reporte guardado en: {output_path.resolve()}")

        grafo_path = ruta_reporte_html(results_dir)
        with grafo_path.open("w", encoding="utf-8", errors="replace") as f:
            f.write(grafo_html)
        print(f"[INFO] Grafo interactivo guardado en: {grafo_path.resolve()}")

        print(f"[TIMER] TOTAL: {time.perf_counter() - t_inicio:.2f}s")

        print(reporte)


if __name__ == "__main__":
    main()
