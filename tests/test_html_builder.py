"""Tests for gitsearch.html_builder module."""

from typing import Any

from gitsearch.html_builder import generar_panel_busqueda


class TestGenerarPanelBusqueda:
    """Tests for generar_panel_busqueda function."""

    def test_retorna_string(self) -> None:
        """Test returns a string."""
        commits: list[dict[str, Any]] = []
        result = generar_panel_busqueda(commits)
        assert isinstance(result, str)

    def test_contiene_panel_html(self) -> None:
        """Test result contains panel HTML elements."""
        commits: list[dict[str, Any]] = []
        result = generar_panel_busqueda(commits)
        assert "gs-panel" in result

    def test_contiene_boton_toggle(self) -> None:
        """Test result contains toggle button."""
        commits: list[dict[str, Any]] = []
        result = generar_panel_busqueda(commits)
        assert 'id="gs-toggle-btn"' in result

    def test_contiene_formulario(self) -> None:
        """Test result contains search form."""
        commits: list[dict[str, Any]] = []
        result = generar_panel_busqueda(commits)
        assert 'id="gs-form"' in result

    def test_contiene_input_texto(self) -> None:
        """Test result contains text input."""
        commits: list[dict[str, Any]] = []
        result = generar_panel_busqueda(commits)
        assert 'id="gs-text"' in result

    def test_contiene_modos_de_busqueda(self) -> None:
        """Test result contains search mode buttons."""
        commits: list[dict[str, Any]] = []
        result = generar_panel_busqueda(commits)
        assert "Mensaje" in result
        assert "Exacto" in result
        assert "Regex" in result

    def test_contiene_filtros_fecha(self) -> None:
        """Test result contains date filter inputs."""
        commits: list[dict[str, Any]] = []
        result = generar_panel_busqueda(commits)
        assert 'id="gs-desde"' in result
        assert 'id="gs-hasta"' in result

    def test_contiene_filtro_autor(self) -> None:
        """Test result contains author filter."""
        commits: list[dict[str, Any]] = []
        result = generar_panel_busqueda(commits)
        assert 'id="gs-autor"' in result

    def test_contiene_resultados_container(self) -> None:
        """Test result contains results container."""
        commits: list[dict[str, Any]] = []
        result = generar_panel_busqueda(commits)
        assert 'id="gs-results-wrap"' in result

    def test_commits_son_serializados(self) -> None:
        """Test commits data is serialized in result."""
        commits: list[dict[str, Any]] = [
            {"hash": "abc123", "autor": "John", "fecha": "2024-01-01", "mensaje": "Test commit"}
        ]
        result = generar_panel_busqueda(commits)
        assert "abc123" in result

    def test_commits_multiples(self) -> None:
        """Test multiple commits are included."""
        commits: list[dict[str, Any]] = [
            {"hash": "abc123", "autor": "John", "fecha": "2024-01-01", "mensaje": "First"},
            {"hash": "def456", "autor": "Jane", "fecha": "2024-01-02", "mensaje": "Second"},
        ]
        result = generar_panel_busqueda(commits)
        assert "abc123" in result
        assert "def456" in result

    def test_contiene_funciones_js(self) -> None:
        """Test result contains JavaScript functions."""
        commits: list[dict[str, Any]] = []
        result = generar_panel_busqueda(commits)
        assert "gsRunSearch" in result
        assert "gsTogglePanel" in result

    def test_lista_vacia_no_falla(self) -> None:
        """Test empty list doesn't raise error."""
        commits: list[dict[str, object]] = []
        result = generar_panel_busqueda(commits)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_datos_son_json_valido(self) -> None:
        """Test commit data is valid JSON format."""
        commits: list[dict[str, Any]] = [
            {"hash": "abc123", "autor": "John", "fecha": "2024-01-01", "mensaje": "Test"}
        ]
        result = generar_panel_busqueda(commits)
        assert "gsCommitsData" in result
        assert '{"hash":"abc123"' in result
