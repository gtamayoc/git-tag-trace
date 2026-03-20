"""
incremental.py — Sistema de análisis incremental para repositorios Git.

Proporciona detección de cambios y persistencia de estado para optimizar
análisis posteriores, evitando reprocesamiento cuando no hay cambios.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from git import Repo

from gitsearch import __version__

DATA_FILENAME = "data.json"
REPORTE_HTML = "reporte.html"
REPORTE_MD = "reporte.md"


def _limpiar_string(valor: Any) -> Any:
    """Limpia strings de caracteres surrogados que causan errores de codificación."""
    if isinstance(valor, str):
        return valor.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    if isinstance(valor, list):
        return [_limpiar_string(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _limpiar_string(v) for k, v in valor.items()}
    return valor


def _calcular_hash_contenido(datos: Any) -> str:
    """Genera un hash determinista del contenido para comparaciones."""
    contenido = json.dumps(datos, sort_keys=True, default=str)
    return hashlib.sha256(contenido.encode()).hexdigest()[:16]


def obtener_hash_estado_repo(repo: Repo) -> str:
    """
    Calcula un hash que representa el estado actual del repositorio.
    Incluye HEAD, refs y estado de tags.
    """
    try:
        estado = {
            "head": repo.head.commit.hexsha if repo.head.is_valid() else None,
            "heads": sorted([h.commit.hexsha for h in repo.heads if h.is_valid()]),
            "tags": sorted([t.commit.hexsha for t in repo.tags if hasattr(t.commit, "hexsha")]),
        }
        return _calcular_hash_contenido(estado)
    except Exception:
        return ""


def cargar_estado(repo_path: Path) -> dict[str, Any] | None:
    """
    Carga el estado previamente guardado desde data.json.

    Returns:
        dict con estado previo o None si no existe el archivo.
    """
    data_file = repo_path / DATA_FILENAME
    if not data_file.exists():
        return None

    try:
        with data_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def detectar_cambios(repo: Repo, estado_anterior: dict[str, Any] | None) -> dict[str, Any]:
    """
    Detecta qué tipo de cambios existen entre el estado actual y el anterior.

    Returns:
        dict con:
            - hay_cambios: bool
            - tipo_cambios: list[str] (commits, tags, ramas)
            - hash_actual: str
            - hash_tags_actual: str
            - commits_nuevos: list[str] (SHAs de commits nuevos)
    """
    hash_actual = obtener_hash_estado_repo(repo)

    if estado_anterior is None or estado_anterior.get("version") != __version__:
        tipo = ["primera_ejecucion"] if estado_anterior is None else ["nueva_version_analizador"]
        return {
            "hay_cambios": True,
            "tipo_cambios": tipo,
            "hash_actual": hash_actual,
            "hash_tags_actual": hash_actual,
            "commits_nuevos": [],
        }

    hash_anterior = estado_anterior.get("hash_estado_repo", "")
    hash_tags_anterior = estado_anterior.get("hash_tags", "")

    cambios: list[str] = []
    commits_nuevos: list[str] = []

    if hash_actual != hash_anterior:
        cambios.append("commits")

        if estado_anterior.get("head_sha"):
            try:
                head_anterior = repo.commit(estado_anterior["head_sha"])
                for c in repo.iter_commits(max_count=1000):
                    if c.hexsha == head_anterior.hexsha:
                        break
                    commits_nuevos.append(c.hexsha)
            except Exception:
                commits_nuevos = []

    hash_tags_actual = hash_actual

    if hash_tags_actual != hash_tags_anterior and "tags" not in cambios:
        cambios.append("tags")

    return {
        "hay_cambios": len(cambios) > 0,
        "tipo_cambios": cambios,
        "hash_actual": hash_actual,
        "hash_tags_actual": hash_tags_actual,
        "commits_nuevos": commits_nuevos,
    }


def guardar_estado(
    repo_path: Path,
    datos: dict[str, Any],
    hash_estado_repo: str,
    hash_tags: str,
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Guarda el estado completo en data.json.

    Returns:
        True si se guardó correctamente, False en caso de error.
    """
    data_file = repo_path / DATA_FILENAME

    historial = datos.get("historial", {})
    commits_data = datos.get("commits_data", [])

    tags_data = datos.get("tags", [])
    comparacion_data = datos.get("comparacion")

    nodes_limpios = _limpiar_string(nodes or [])
    edges_limpios = _limpiar_string(edges or [])
    commits_limpios = _limpiar_string(commits_data)
    tags_limpios = _limpiar_string(tags_data)

    estado = {
        "version": __version__,
        "fecha_ultimo_analisis": datetime.now().isoformat(),
        "hash_estado_repo": hash_estado_repo,
        "hash_tags": hash_tags,
        "nodes": nodes_limpios,
        "edges": edges_limpios,
        "history": commits_limpios,
        "commitMap": {},
        "globalSearch": None,
        "metadata": {
            "tags": tags_limpios,
            "historial_resumen": {
                "total": historial.get("total", 0),
                "fecha_inicio": historial.get("fecha_inicio"),
                "fecha_fin": historial.get("fecha_fin"),
                "autores": historial.get("autores", {}),
            },
            "comparacion": _limpiar_string(comparacion_data),
        },
    }

    try:
        tmp_file = data_file.with_suffix(".json.tmp")
        with tmp_file.open("w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
        
        tmp_file.replace(data_file)
        return True
    except OSError as e:
        print(f"[ERROR] No se pudo guardar estado: {e}")
        try:
            if "tmp_file" in locals() and tmp_file.exists():
                tmp_file.unlink()
        except OSError:
            pass
        return False


def obtener_ruta_resultados(repo_path: Path) -> Path:
    """Retorna la ruta del directorio de resultados para el repositorio."""
    return repo_path / DATA_FILENAME


def ruta_data_json(repo_path: Path) -> Path:
    """Retorna la ruta completa al archivo data.json."""
    return repo_path / DATA_FILENAME


def ruta_reporte_html(repo_path: Path) -> Path:
    """Retorna la ruta completa al archivo reporte.html."""
    return repo_path / REPORTE_HTML


def ruta_reporte_md(repo_path: Path) -> Path:
    """Retorna la ruta completa al archivo reporte.md."""
    return repo_path / REPORTE_MD


def generar_info_incremental(cambios: dict[str, Any]) -> str:
    """Genera un mensaje informativo sobre los cambios detectados."""
    if not cambios["hay_cambios"]:
        return "No hay ningún cambio nuevo en el repositorio."

    tipos = cambios.get("tipo_cambios", [])
    commits_nuevos = cambios.get("commits_nuevos", [])

    partes = []
    if "primera_ejecucion" in tipos:
        return "Primera ejecución. Realizando análisis completo."

    if "commits" in tipos:
        n = len(commits_nuevos)
        partes.append(f"{n} commit(s) nuevo(s)")

    if "tags" in tipos:
        partes.append("Tags modificados")

    return f"Cambios detectados: {', '.join(partes)}"
