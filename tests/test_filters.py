"""Tests for gitsearch.filters module."""

import pytest

from gitsearch.filters import FiltroInvalido, validar_y_normalizar


class TestValidarYNormalizar:
    """Tests for validar_y_normalizar function."""

    def test_validar_texto_vacio(self) -> None:
        """Test with empty texto returns empty string."""
        result = validar_y_normalizar({"texto": ""})
        assert result["texto"] == ""

    def test_validar_texto_con_espacios(self) -> None:
        """Test texto is trimmed."""
        result = validar_y_normalizar({"texto": "  hello  "})
        assert result["texto"] == "hello"

    def test_modo_default_auto(self) -> None:
        """Test default modo is auto."""
        result = validar_y_normalizar({})
        assert result["modo"] == "auto"

    def test_modo_valido_s(self) -> None:
        """Test modo s is valid."""
        result = validar_y_normalizar({"modo": "s"})
        assert result["modo"] == "s"

    def test_modo_valido_g(self) -> None:
        """Test modo g is valid."""
        result = validar_y_normalizar({"modo": "g"})
        assert result["modo"] == "g"

    def test_modo_valido_grep(self) -> None:
        """Test modo grep is valid."""
        result = validar_y_normalizar({"modo": "grep"})
        assert result["modo"] == "grep"

    def test_modo_valido_l(self) -> None:
        """Test modo l is valid."""
        result = validar_y_normalizar({"modo": "l", "archivo": "test.py"})
        assert result["modo"] == "l"

    def test_modo_invalido_lanza_excepcion(self) -> None:
        """Test invalid modo raises FiltroInvalido."""
        with pytest.raises(FiltroInvalido) as exc_info:
            validar_y_normalizar({"modo": "invalid"})
        assert "Modo 'invalid' no válido" in str(exc_info.value)

    def test_modo_l_sin_archivo_lanza_excepcion(self) -> None:
        """Test modo l without archivo raises FiltroInvalido."""
        with pytest.raises(FiltroInvalido) as exc_info:
            validar_y_normalizar({"modo": "l"})
        assert "archivo" in str(exc_info.value)

    def test_autor_se_normaliza(self) -> None:
        """Test autor is trimmed."""
        result = validar_y_normalizar({"autor": "  John Doe  "})
        assert result["autor"] == "John Doe"

    def test_fecha_desde_valida(self) -> None:
        """Test valid desde date passes."""
        result = validar_y_normalizar({"desde": "2024-01-01"})
        assert result["desde"] == "2024-01-01"

    def test_fecha_desde_vacia(self) -> None:
        """Test empty desde returns empty string."""
        result = validar_y_normalizar({"desde": ""})
        assert result["desde"] == ""

    def test_fecha_desde_invalida_lanza_excepcion(self) -> None:
        """Test invalid desde raises FiltroInvalido."""
        with pytest.raises(FiltroInvalido) as exc_info:
            validar_y_normalizar({"desde": "01-01-2024"})
        assert "'desde' debe tener formato YYYY-MM-DD" in str(exc_info.value)

    def test_fecha_hasta_valida(self) -> None:
        """Test valid hasta date passes."""
        result = validar_y_normalizar({"hasta": "2024-12-31"})
        assert result["hasta"] == "2024-12-31"

    def test_fecha_hasta_invalida_lanza_excepcion(self) -> None:
        """Test invalid hasta raises FiltroInvalido."""
        with pytest.raises(FiltroInvalido) as exc_info:
            validar_y_normalizar({"hasta": "31-12-2024"})
        assert "'hasta' debe tener formato YYYY-MM-DD" in str(exc_info.value)

    def test_archivo_se_normaliza(self) -> None:
        """Test archivo is trimmed."""
        result = validar_y_normalizar({"archivo": "  test.py  "})
        assert result["archivo"] == "test.py"

    def test_funcion_se_normaliza(self) -> None:
        """Test funcion is trimmed."""
        result = validar_y_normalizar({"funcion": "  my_func  "})
        assert result["funcion"] == "my_func"

    def test_max_count_default(self) -> None:
        """Test default max_count is 2000."""
        result = validar_y_normalizar({})
        assert result["max_count"] == 2000

    def test_max_count_custom(self) -> None:
        """Test custom max_count."""
        result = validar_y_normalizar({"max_count": 500})
        assert result["max_count"] == 500

    def test_max_count_negativo_vuelve_default(self) -> None:
        """Test negative max_count returns default."""
        result = validar_y_normalizar({"max_count": -1})
        assert result["max_count"] == 2000

    def test_max_count_cero_vuelve_default(self) -> None:
        """Test zero max_count returns default."""
        result = validar_y_normalizar({"max_count": 0})
        assert result["max_count"] == 2000

    def test_max_count_invalido_vuelve_default(self) -> None:
        """Test invalid max_count returns default."""
        result = validar_y_normalizar({"max_count": "invalid"})
        assert result["max_count"] == 2000

    def test_regex_valido_pasa(self) -> None:
        """Test valid regex pattern passes."""
        result = validar_y_normalizar({"texto": r"\d+", "modo": "g"})
        assert result["texto"] == r"\d+"

    def test_regex_invalido_lanza_excepcion(self) -> None:
        """Test invalid regex raises FiltroInvalido."""
        with pytest.raises(FiltroInvalido) as exc_info:
            validar_y_normalizar({"texto": r"[", "modo": "g"})
        assert "patrón regex" in str(exc_info.value)

    def test_retorna_dict_normalizado(self) -> None:
        """Test returns properly normalized dict."""
        result = validar_y_normalizar({
            "texto": "  search  ",
            "modo": "grep",
            "autor": "  developer  ",
            "desde": "2024-01-01",
            "hasta": "2024-12-31",
            "archivo": "  main.py  ",
            "funcion": "  test  ",
            "max_count": 1000
        })
        assert result == {
            "texto": "search",
            "modo": "grep",
            "autor": "developer",
            "desde": "2024-01-01",
            "hasta": "2024-12-31",
            "archivo": "main.py",
            "funcion": "test",
            "max_count": 1000
        }
