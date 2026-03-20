"""Tests for gitsearch.incremental module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from gitsearch import __version__
from gitsearch.incremental import (
    DATA_FILENAME,
    REPORTE_HTML,
    REPORTE_MD,
    _calcular_hash_contenido,
    _limpiar_string,
    cargar_estado,
    detectar_cambios,
    generar_info_incremental,
    guardar_estado,
    obtener_hash_estado_repo,
    ruta_data_json,
    ruta_reporte_html,
    ruta_reporte_md,
)


class TestLimpiarString:
    """Tests for _limpiar_string function."""

    def test_pasa_string_normal(self) -> None:
        """Test normal string passes through."""
        result = _limpiar_string("hello world")
        assert result == "hello world"

    def test_limpia_lista(self) -> None:
        """Test list is cleaned recursively."""
        result = _limpiar_string(["hello", "world"])
        assert result == ["hello", "world"]

    def test_limpia_dict(self) -> None:
        """Test dict is cleaned recursively."""
        result = _limpiar_string({"key": "value", "num": 42})
        assert result == {"key": "value", "num": 42}

    def test_pasa_numero_sin_cambio(self) -> None:
        """Test numbers pass through unchanged."""
        assert _limpiar_string(42) == 42
        assert _limpiar_string(3.14) == 3.14

    def test_pasa_none_sin_cambio(self) -> None:
        """Test None passes through unchanged."""
        assert _limpiar_string(None) is None


class TestCalcularHashContenido:
    """Tests for _calcular_hash_contenido function."""

    def test_hash_deterministico(self) -> None:
        """Test hash is deterministic for same input."""
        data = {"key": "value", "num": 42}
        hash1 = _calcular_hash_contenido(data)
        hash2 = _calcular_hash_contenido(data)
        assert hash1 == hash2

    def test_hash_diferente_con_datos_diferentes(self) -> None:
        """Test different data produces different hashes."""
        hash1 = _calcular_hash_contenido({"a": 1})
        hash2 = _calcular_hash_contenido({"b": 2})
        assert hash1 != hash2

    def test_hash_longitud_16(self) -> None:
        """Test hash has correct length."""
        hash_result = _calcular_hash_contenido({"test": "data"})
        assert len(hash_result) == 16


class TestObtenerHashEstadoRepo:
    """Tests for obtener_hash_estado_repo function."""

    def test_retorna_hash_cuando_repo_valido(self) -> None:
        """Test returns hash when repo is valid."""
        repo = MagicMock()
        repo.head.is_valid.return_value = True
        repo.head.commit.hexsha = "abc123def456789012345678901234567890abcd"
        repo.heads = []
        repo.tags = []

        result = obtener_hash_estado_repo(repo)
        assert isinstance(result, str)
        assert len(result) == 16

    def test_retorna_hash_vacio_cuando_excepcion(self) -> None:
        """Test returns empty hash on exception."""
        repo = MagicMock()
        repo.head.is_valid.side_effect = Exception("Git error")

        result = obtener_hash_estado_repo(repo)
        assert result == ""


class TestCargarEstado:
    """Tests for cargar_estado function."""

    def test_retorna_none_cuando_archivo_no_existe(self, tmp_path: Path) -> None:
        """Test returns None when file doesn't exist."""
        result = cargar_estado(tmp_path)
        assert result is None

    def test_carga_estado_valido(self, tmp_path: Path) -> None:
        """Test loads valid state file."""
        data_file = tmp_path / DATA_FILENAME
        data_file.write_text('{"version": "1.0", "hash_estado_repo": "abc123"}')

        result = cargar_estado(tmp_path)
        assert result is not None
        assert result["version"] == "1.0"
        assert result["hash_estado_repo"] == "abc123"

    def test_retorna_none_json_invalido(self, tmp_path: Path) -> None:
        """Test returns None for invalid JSON."""
        data_file = tmp_path / DATA_FILENAME
        data_file.write_text("invalid json {")

        result = cargar_estado(tmp_path)
        assert result is None


class TestDetectarCambios:
    """Tests for detectar_cambios function."""

    def test_detecta_primera_ejecucion(self) -> None:
        """Test detects first run when no previous state."""
        repo = MagicMock()
        repo.head.is_valid.return_value = True
        repo.head.commit.hexsha = "abc123"
        repo.heads = []
        repo.tags = []

        result = detectar_cambios(repo, None)

        assert result["hay_cambios"] is True
        assert "primera_ejecucion" in result["tipo_cambios"]

    def test_detecta_cambios_en_head(self) -> None:
        """Test detects changes when head SHA differs."""
        repo = MagicMock()
        repo.head.is_valid.return_value = True
        repo.head.commit.hexsha = "abc123"
        repo.heads = []
        repo.tags = []
        repo.iter_commits.return_value = iter([])

        estado_anterior = {
            "version": __version__,
            "head_sha": "xyz789",
            "hash_estado_repo": "xyz789",
            "hash_tags": "xyz789",
        }

        result = detectar_cambios(repo, estado_anterior)

        assert result["hay_cambios"] is True
        assert "commits" in result["tipo_cambios"]

    def test_sin_cambios_cuando_hash_igual(self) -> None:
        """Test no changes when hashes match."""
        with patch("gitsearch.incremental.obtener_hash_estado_repo") as mock_hash:
            mock_hash.return_value = "abcd1234efgh5678"
            repo = MagicMock()

            estado_anterior = {
                "version": __version__,
                "head_sha": "abc123",
                "hash_estado_repo": "abcd1234efgh5678",
                "hash_tags": "abcd1234efgh5678",
            }

            result = detectar_cambios(repo, estado_anterior)

            assert result["hay_cambios"] is False
            assert len(result["tipo_cambios"]) == 0


class TestGuardarEstado:
    """Tests for guardar_estado function."""

    def test_guarda_estado_exitoso(self, tmp_path: Path) -> None:
        """Test successfully saves state."""
        datos = {
            "historial": {"total": 10},
            "commits_data": [],
            "tags": [],
            "comparacion": None,
        }

        result = guardar_estado(
            tmp_path,
            datos,
            "hash_repo_123",
            "hash_tags_456",
            nodes=None,
            edges=None,
        )

        assert result is True
        assert (tmp_path / DATA_FILENAME).exists()

    def test_retorna_false_en_error(self) -> None:
        """Test returns False when path is invalid."""
        datos = {"historial": {}, "commits_data": [], "tags": [], "comparacion": None}

        invalid_path = Path("//invalid//path//that//does//not//exist")
        result = guardar_estado(invalid_path, datos, "hash1", "hash2", None, None)
        assert result is False


class TestGenerarInfoIncremental:
    """Tests for generar_info_incremental function."""

    def test_sin_cambios(self) -> None:
        """Test message when no changes."""
        cambios = {"hay_cambios": False, "tipo_cambios": [], "commits_nuevos": []}
        result = generar_info_incremental(cambios)
        assert "No hay ningún cambio" in result

    def test_primera_ejecucion(self) -> None:
        """Test message for first run."""
        cambios = {
            "hay_cambios": True,
            "tipo_cambios": ["primera_ejecucion"],
            "commits_nuevos": [],
        }
        result = generar_info_incremental(cambios)
        assert "Primera ejecución" in result

    def test_commits_nuevos(self) -> None:
        """Test message with new commits."""
        cambios = {
            "hay_cambios": True,
            "tipo_cambios": ["commits"],
            "commits_nuevos": ["sha1", "sha2", "sha3"],
        }
        result = generar_info_incremental(cambios)
        assert "3 commit(s) nuevo(s)" in result

    def test_tags_modificados(self) -> None:
        """Test message with modified tags."""
        cambios = {
            "hay_cambios": True,
            "tipo_cambios": ["tags"],
            "commits_nuevos": [],
        }
        result = generar_info_incremental(cambios)
        assert "Tags modificados" in result


class TestRutas:
    """Tests for path utility functions."""

    def test_ruta_data_json(self) -> None:
        """Test data.json path resolution."""
        repo_path = Path("/test/repo")
        result = ruta_data_json(repo_path)
        assert result == repo_path / DATA_FILENAME

    def test_ruta_reporte_html(self) -> None:
        """Test HTML report path resolution."""
        repo_path = Path("/test/repo")
        result = ruta_reporte_html(repo_path)
        assert result == repo_path / REPORTE_HTML

    def test_ruta_reporte_md(self) -> None:
        """Test Markdown report path resolution."""
        repo_path = Path("/test/repo")
        result = ruta_reporte_md(repo_path)
        assert result == repo_path / REPORTE_MD
