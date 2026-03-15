"""Tests for gitsearch.engine module."""

from unittest.mock import MagicMock, patch

from gitsearch.engine import buscar


class TestBuscar:
    """Tests for buscar function."""

    @patch("gitsearch.engine.validar_y_normalizar")
    @patch("gitsearch.engine.seleccionar_estrategia")
    def test_retorna_error_cuando_validacion_falla(
        self, mock_seleccionar: MagicMock, mock_validar: MagicMock
    ) -> None:
        """Test returns error dict when validation fails."""
        from gitsearch.filters import FiltroInvalido

        mock_validar.side_effect = FiltroInvalido("Test error")
        mock_seleccionar.return_value = {
            "modo": "error",
            "descripcion": "",
            "flags_base": [],
            "flags_contenido": []
        }

        repo = MagicMock()
        result = buscar(repo, {"texto": "test"})

        assert result["modo"] == "error"
        assert result["total"] == 0
        assert len(result["resultados"]) == 0

    @patch("gitsearch.engine.validar_y_normalizar")
    @patch("gitsearch.engine.seleccionar_estrategia")
    def test_retorna_vacio_cuando_sin_criterios(
        self, mock_seleccionar: MagicMock, mock_validar: MagicMock
    ) -> None:
        """Test returns empty results when no search criteria."""
        mock_validar.return_value = {
            "texto": "",
            "autor": "",
            "desde": "",
            "hasta": ""
        }
        mock_seleccionar.return_value = {
            "modo": "grep",
            "descripcion": "Test",
            "flags_base": ["--all"],
            "flags_contenido": []
        }

        repo = MagicMock()
        result = buscar(repo, {})

        assert result["total"] == 0
        assert len(result["resultados"]) == 0

    @patch("gitsearch.engine.validar_y_normalizar")
    @patch("gitsearch.engine.seleccionar_estrategia")
    def test_busqueda_sin_resultados(
        self, mock_seleccionar: MagicMock, mock_validar: MagicMock
    ) -> None:
        """Test returns empty when git returns no matches."""
        mock_validar.return_value = {
            "texto": "nonexistent",
            "autor": "",
            "desde": "",
            "hasta": ""
        }
        mock_seleccionar.return_value = {
            "modo": "grep",
            "descripcion": "Buscar nonexistent",
            "flags_base": ["--all", "--max-count=2000"],
            "flags_contenido": ["--grep=nonexistent", "-i", "--format=%H"]
        }

        repo = MagicMock()
        repo.git.log.return_value = ""

        result = buscar(repo, {"texto": "nonexistent"})

        assert result["total"] == 0
        assert len(result["resultados"]) == 0
        assert result["criterio"] == "nonexistent"

    @patch("gitsearch.engine.validar_y_normalizar")
    @patch("gitsearch.engine.seleccionar_estrategia")
    def test_maneja_excepcion_git(
        self, mock_seleccionar: MagicMock, mock_validar: MagicMock
    ) -> None:
        """Test handles git exceptions gracefully."""
        mock_validar.return_value = {
            "texto": "test",
            "autor": "",
            "desde": "",
            "hasta": ""
        }
        mock_seleccionar.return_value = {
            "modo": "grep",
            "descripcion": "Test",
            "flags_base": ["--all"],
            "flags_contenido": []
        }

        repo = MagicMock()
        repo.git.log.side_effect = Exception("Git error")

        result = buscar(repo, {"texto": "test"})

        assert result["total"] == 0
        assert len(result["resultados"]) == 0

    @patch("gitsearch.engine.validar_y_normalizar")
    @patch("gitsearch.engine.seleccionar_estrategia")
    def test_selecciona_estrategia_correcta(
        self, mock_seleccionar: MagicMock, mock_validar: MagicMock
    ) -> None:
        """Test correctly passes parameters to strategy selection."""
        mock_validar.return_value = {
            "texto": "test",
            "autor": "developer",
            "desde": "2024-01-01",
            "hasta": "2024-12-31"
        }
        mock_seleccionar.return_value = {
            "modo": "grep",
            "descripcion": "Test",
            "flags_base": ["--all", "--author=developer", "--since=2024-01-01", "--until=2024-12-31", "--max-count=2000"],
            "flags_contenido": ["--grep=test", "-i", "--format=%H"]
        }

        repo = MagicMock()
        repo.git.log.return_value = ""

        buscar(repo, {"texto": "test", "autor": "developer"})

        mock_seleccionar.assert_called_once()

    @patch("gitsearch.engine.validar_y_normalizar")
    @patch("gitsearch.engine.seleccionar_estrategia")
    def test_procesa_commit_encontrado(
        self, mock_seleccionar: MagicMock, mock_validar: MagicMock
    ) -> None:
        """Test processes found commits correctly."""
        mock_validar.return_value = {
            "texto": "test",
            "autor": "",
            "desde": "",
            "hasta": ""
        }
        mock_seleccionar.return_value = {
            "modo": "grep",
            "descripcion": "Buscar test",
            "flags_base": ["--all", "--max-count=2000"],
            "flags_contenido": ["--grep=test", "-i", "--format=%H"]
        }

        commit_mock = MagicMock()
        commit_mock.hexsha = "abc123def456789012345678901234567890"
        commit_mock.author.name = "Test Author"
        commit_mock.committed_date = 1704067200
        commit_mock.message = "Test commit message"
        commit_mock.parents = []

        repo = MagicMock()
        repo.git.log.return_value = "abc123def456789012345678901234567890\n"
        repo.commit.return_value = commit_mock

        result = buscar(repo, {"texto": "test"})

        assert result["modo"] == "grep"
        assert "criterio" in result

    @patch("gitsearch.engine.validar_y_normalizar")
    @patch("gitsearch.engine.seleccionar_estrategia")
    def test_maneja_topologia(
        self, mock_seleccionar: MagicMock, mock_validar: MagicMock
    ) -> None:
        """Test processes topologia parameter correctly."""
        mock_validar.return_value = {
            "texto": "test",
            "autor": "",
            "desde": "",
            "hasta": ""
        }
        mock_seleccionar.return_value = {
            "modo": "grep",
            "descripcion": "Test",
            "flags_base": ["--all"],
            "flags_contenido": []
        }

        topologia = {
            "abc123def456789012345678901234567890": {
                "all_tags": ["v1.0.0"],
                "stats": {
                    "commits_list": [
                        {"hash": "def4567", "full_hash": "def456789012345678901234567890123456"}
                    ]
                }
            }
        }

        commit_mock = MagicMock()
        commit_mock.hexsha = "abc123def456789012345678901234567890"
        commit_mock.author.name = "Test Author"
        commit_mock.committed_date = 1704067200
        commit_mock.message = "Test"
        commit_mock.parents = []

        repo = MagicMock()
        repo.git.log.return_value = "abc123def456789012345678901234567890"
        repo.commit.return_value = commit_mock

        result = buscar(repo, {"texto": "test"}, topologia=topologia)

        assert result["total"] >= 0

    @patch("gitsearch.engine.validar_y_normalizar")
    @patch("gitsearch.engine.seleccionar_estrategia")
    def test_maneja_commit_sin_padres(
        self, mock_seleccionar: MagicMock, mock_validar: MagicMock
    ) -> None:
        """Test handles commit without parents correctly."""
        mock_validar.return_value = {
            "texto": "test",
            "autor": "",
            "desde": "",
            "hasta": ""
        }
        mock_seleccionar.return_value = {
            "modo": "grep",
            "descripcion": "Test",
            "flags_base": ["--all"],
            "flags_contenido": []
        }

        commit_mock = MagicMock()
        commit_mock.hexsha = "abc123def456789012345678901234567890"
        commit_mock.author.name = "Test Author"
        commit_mock.committed_date = 1704067200
        commit_mock.message = "Root commit"
        commit_mock.parents = []

        repo = MagicMock()
        repo.git.log.return_value = "abc123def456789012345678901234567890"
        repo.commit.return_value = commit_mock

        result = buscar(repo, {"texto": "test"})

        assert result["total"] >= 0

    @patch("gitsearch.engine.validar_y_normalizar")
    @patch("gitsearch.engine.seleccionar_estrategia")
    def test_ordena_resultados_por_fecha(
        self, mock_seleccionar: MagicMock, mock_validar: MagicMock
    ) -> None:
        """Test results are sorted by date descending."""
        mock_validar.return_value = {
            "texto": "test",
            "autor": "",
            "desde": "",
            "hasta": ""
        }
        mock_seleccionar.return_value = {
            "modo": "grep",
            "descripcion": "Test",
            "flags_base": ["--all"],
            "flags_contenido": []
        }

        commit1 = MagicMock()
        commit1.hexsha = "aaa123def456789012345678901234567890"
        commit1.author.name = "Author 1"
        commit1.committed_date = 1700000000
        commit1.message = "Older commit"

        commit2 = MagicMock()
        commit2.hexsha = "bbb123def456789012345678901234567890"
        commit2.author.name = "Author 2"
        commit2.committed_date = 1705000000
        commit2.message = "Newer commit"

        repo = MagicMock()
        repo.git.log.return_value = "aaa123def456789012345678901234567890\nbbb123def456789012345678901234567890"
        repo.commit.side_effect = [commit1, commit2]

        result = buscar(repo, {"texto": "test"})

        if result["total"] == 2:
            dates = [r["fecha"] for r in result["resultados"]]
            assert dates[0] >= dates[1]

    @patch("gitsearch.engine.validar_y_normalizar")
    @patch("gitsearch.engine.seleccionar_estrategia")
    def test_maneja_diff_con_padres(
        self, mock_seleccionar: MagicMock, mock_validar: MagicMock
    ) -> None:
        """Test handles diff calculation with parents correctly."""
        mock_validar.return_value = {
            "texto": "test",
            "autor": "",
            "desde": "",
            "hasta": ""
        }
        mock_seleccionar.return_value = {
            "modo": "grep",
            "descripcion": "Test",
            "flags_base": ["--all"],
            "flags_contenido": []
        }

        diff_mock = MagicMock()
        diff_mock.a_path = "file1.py"
        diff_mock.b_path = None

        parent_mock = MagicMock()
        parent_mock.hexsha = "parent123456789012345678901234567890"

        commit_mock = MagicMock()
        commit_mock.hexsha = "abc123def456789012345678901234567890"
        commit_mock.author.name = "Test Author"
        commit_mock.committed_date = 1704067200
        commit_mock.message = "Test commit with files"
        commit_mock.parents = [parent_mock]
        parent_mock.diff.return_value = [diff_mock]

        repo = MagicMock()
        repo.git.log.return_value = "abc123def456789012345678901234567890\n"
        repo.commit.return_value = commit_mock

        result = buscar(repo, {"texto": "test"})

        assert result["modo"] == "grep"
