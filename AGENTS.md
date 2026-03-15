# AGENTS.md - Git Tag Trace

## Project Overview

Git Tag Trace is an offline Git repository analyzer that generates interactive HTML visualizations of tags and commits. It includes a CLI tool for analyzing repository history and generating reports.

**Python**: 3.11+
**Package Manager**: uv
**Build Backend**: hatchling

---

## Commands

### Running the Application

```bash
# Run CLI tool
python -m uv run git-tag-trace <repo_path> [--output <file>]

# Or using the installed script
python -m uv run git-tag-trace C:\path\to\repo --output reporte.md
```

### Development Commands

```bash
# Install all dependencies
python -m uv sync --all-groups

# Install only runtime dependencies
python -m uv sync

# Run tests
python -m uv run pytest

# Run a single test
python -m uv run pytest tests/test_filters.py::test_validar_texto_con_espacios

# Run tests with verbose output
python -m uv run pytest -v

# Run tests with coverage
python -m uv run pytest --cov=gitsearch --cov-report=term-missing

# Lint code
python -m uv run ruff check .

# Format code
python -m uv run ruff format .

# Type check
python -m uv run ty check gitsearch/

# Run lint + type check
python -m uv run ruff check . && python -m uv run ty check gitsearch/

# Build package
python -m uv build
```

### Windows Batch Script

```bash
# Quick start (double-click start.bat)
start.bat
```

---

## Code Style Guidelines

### General Principles

- **Python Version**: 3.11+ (use type hints, dataclasses where appropriate)
- **Line Length**: 100 characters max
- **Formatting**: Use ruff format
- **Linting**: Use ruff check (ALL rules enabled, with specific ignores for legacy code)

### Imports

```python
# Standard library first, then third-party, then local
import os
import sys
from datetime import datetime
from typing import Any

from git import Repo

from gitsearch import filters, strategy
from gitsearch.engine import buscar
```

### Type Hints

```python
# Always use type hints for function signatures
def obtener_tags(repo: Repo) -> list[dict[str, Any]]:
    ...

# Use | instead of Optional for Python 3.11+
def funcion(texto: str | None = None) -> dict[str, Any]:
    ...
```

### Naming Conventions

```python
# Variables and functions: snake_case
def obtener_historial(repo: Repo) -> dict[str, Any]:
    commits_count = 10

# Classes: PascalCase
class FiltroInvalido(ValueError):
    pass

# Constants: UPPER_SNAKE_CASE
MAX_COMMITS = 1000

# Private functions: prefix with underscore
def _helper_function() -> None:
    ...
```

### Error Handling

```python
# Prefer specific exceptions over broad except
try:
    result = repo.commit(sha)
except ValueError:
    return None

# Use logging for production code
import logging
logger = logging.getLogger(__name__)

# For CLI scripts, print errors clearly
print(f"[ERROR] {e}", file=sys.stderr)
sys.exit(1)
```

### Docstrings

```python
def obtener_tags(repo: Repo) -> list[dict[str, Any]]:
    """Obtiene todos los tags del repositorio con su metadata."""
    ...
```

### Testing

```python
# Use pytest with class-based tests
class TestFiltros:
    def test_validar_texto_con_espacios(self) -> None:
        result = validar_y_normalizar({"texto": "  hello  "})
        assert result["texto"] == "hello"

    def test_modo_invalido_lanza_excepcion(self) -> None:
        with pytest.raises(FiltroInvalido) as exc_info:
            validar_y_normalizar({"modo": "invalid"})
        assert "Modo 'invalid' no valido" in str(exc_info.value)
```

### GitPython Usage

```python
# GitPython types may not resolve in type checkers
# This is expected and can be ignored
from git import Repo, Commit  # type: ignore
```

---

## Project Structure

```
git-tag-trace/
├── gitsearch/           # Main package
│   ├── __init__.py
│   ├── __main__.py      # CLI entry point
│   ├── engine.py        # Search engine
│   ├── filters.py       # Parameter validation
│   ├── strategy.py      # Git command strategies
│   └── html_builder.py  # HTML generation
├── tests/               # Test suite
│   ├── test_engine.py
│   ├── test_filters.py
│   ├── test_html_builder.py
│   └── test_strategy.py
├── pyproject.toml       # Project configuration
├── start.bat            # Windows launcher
└── README.md
```

---

## Configuration Files

### pyproject.toml Key Sections

- `[project]`: Package metadata
- `[dependency-groups]`: Dev/test/lint dependencies (PEP 735)
- `[tool.ruff]`: Linting and formatting config
- `[tool.pytest]`: Test configuration
- `[tool.ty]`: Type checking configuration

---

## Notes for Agents

1. **Always use `uv run`** when executing commands in this project
2. **Coverage is disabled** (`--cov-fail-under=0`) - legacy codebase has low coverage
3. **Many ruff rules are ignored** for the existing codebase - new code should follow the guidelines above
4. **GitPython types** may show warnings in ty - these are informational
5. **The main CLI** is in `gitsearch/__main__.py` with ~2000 lines of code
