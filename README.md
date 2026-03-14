# Git Tag Trace

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/Platform-Windows-lightgrey?style=flat-square" alt="Platform">
</p>

Git Tag Trace (GTT) is an offline Git repository analyzer that generates interactive HTML visualizations of tags and commits. It provides topological analysis of version history, commit search capabilities, and beautiful interactive graphs.

## Features

- **Tag Analysis**: Extract and analyze all Git tags with metadata (date, author, hash)
- **Topological Graph**: Interactive visualization of version relationships
- **Commit Search**: Search commits by message, author, file, or regex pattern
- **Diff Viewing**: View commit changes directly in the HTML interface
- **Offline Operation**: Works completely offline - no external dependencies
- **CLI Interface**: Simple command-line interface for automation

## Screenshots

### Interactive Version Graph

![Version Graph](docs/screenshots/version-graph.png)

*The interactive graph shows tag relationships with branch visualization*

### Commit Details Panel

![Commit Details](docs/screenshots/commit-details.png)

*Click on any node to view commit details, files changed, and diffs*

### Search Interface

![Search Interface](docs/screenshots/search-interface.png)

*Search commits by message, author, file path, or regex pattern*

---

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Git installed and in PATH
- Windows (currently)

### Installation

1. Clone or download this repository
2. Edit `.env` file with your repository path:

```env
REPO_PATH=C:\path\to\your\repository
OUTPUT_FILE=reporte.md
```

3. Run `start.bat` or use uv directly:

```bash
# Install dependencies
python -m uv sync --all-groups

# Run the analyzer
python -m uv run git-tag-trace C:\path\to\repo --output reporte.md
```

## Usage

### Basic Analysis

```bash
# Analyze a repository and generate HTML report
python -m uv run git-tag-trace C:\path\to\repo

# With custom output file
python -m uv run git-tag-trace C:\path\to\repo --output my-report.md

# Generate interactive HTML with graph
python -m uv run git-tag-trace C:\path\to\repo --html
```

### Output Files

- **reporte.md**: Markdown report with tag list and commit history
- **reporte_grafo.html**: Interactive HTML with visualization and search

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Path to the Git repository to analyze
REPO_PATH=C:\path\to\repository

# Output file name (optional)
OUTPUT_FILE=reporte.md

# Tag prefixes to clean from labels (comma-separated)
TAG_PREFIXES=release_,v
```

### Command Line Options

```
git-tag-trace <repo_path> [options]

Options:
  --output FILE      Output markdown file (default: reporte.md)
  --html             Generate interactive HTML report
  --no-graph         Skip graph generation
  --help             Show help message
```

## Project Structure

```
git-tag-trace/
├── gitsearch/           # Main package
│   ├── __main__.py      # CLI entry point
│   ├── engine.py        # Search engine
│   ├── filters.py       # Parameter validation
│   ├── strategy.py      # Git command strategies
│   └── html_builder.py  # HTML generation
├── tests/               # Test suite
├── docs/                # Documentation
│   └── screenshots/     # Project screenshots
├── pyproject.toml       # Project configuration
├── start.bat            # Windows launcher
└── README.md
```

## Development

### Running Tests

```bash
# Run all tests
python -m uv run pytest

# Run single test
python -m uv run pytest tests/test_filters.py::test_validar_texto_con_espacios

# With coverage
python -m uv run pytest --cov=gitsearch --cov-report=term-missing
```

### Linting & Type Checking

```bash
# Lint code
python -m uv run ruff check .

# Format code
python -m uv run ruff format .

# Type check
python -m uv run ty check gitsearch/
```

### Building

```bash
# Build package
python -m uv build
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- [GitPython](https://gitpython.readthedocs.io/) - Git interface for Python
- [vis-network](https://visjs.org/) - Interactive network visualization
