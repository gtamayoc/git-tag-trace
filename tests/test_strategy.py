"""Tests for gitsearch.strategy module."""


from gitsearch.strategy import seleccionar_estrategia


class TestSeleccionarEstrategia:
    """Tests for seleccionar_estrategia function."""

    def test_sin_criterios_retorna_grep(self) -> None:
        """Test empty params returns grep mode."""
        result = seleccionar_estrategia({})
        assert result["modo"] == "grep"

    def test_modo_explicito_s(self) -> None:
        """Test explicit modo s."""
        result = seleccionar_estrategia({"modo": "s", "texto": "test"})
        assert result["modo"] == "s"
        assert "-Stest" in result["flags_contenido"][0]

    def test_modo_explicito_g(self) -> None:
        """Test explicit modo g."""
        result = seleccionar_estrategia({"modo": "g", "texto": "test"})
        assert result["modo"] == "g"
        assert "-Gtest" in result["flags_contenido"][0]

    def test_modo_explicito_grep(self) -> None:
        """Test explicit modo grep."""
        result = seleccionar_estrategia({"modo": "grep", "texto": "test"})
        assert result["modo"] == "grep"
        assert "--grep=test" in result["flags_contenido"][0]

    def test_modo_auto_con_archivo_sin_funcion(self) -> None:
        """Test modo auto with archivo without funcion uses grep (l requires funcion or digit texto)."""
        result = seleccionar_estrategia({"archivo": "test.py"})
        assert result["modo"] == "grep"

    def test_modo_auto_con_archivo_y_funcion(self) -> None:
        """Test modo auto with archivo and funcion uses modo l."""
        result = seleccionar_estrategia({"archivo": "test.py", "funcion": "my_func"})
        assert result["modo"] == "l"

    def test_modo_auto_con_texto_regex(self) -> None:
        """Test modo auto with regex-like texto uses modo g."""
        result = seleccionar_estrategia({"texto": r"\d+"})
        assert result["modo"] == "g"

    def test_modo_auto_con_texto_sin_regex(self) -> None:
        """Test modo auto with plain texto uses modo grep."""
        result = seleccionar_estrategia({"texto": "hello"})
        assert result["modo"] == "grep"

    def test_flags_base_con_autor(self) -> None:
        """Test autor filter is added to flags_base."""
        result = seleccionar_estrategia({"autor": "developer"})
        assert "--author=developer" in result["flags_base"]

    def test_flags_base_con_desde(self) -> None:
        """Test desde filter is added to flags_base."""
        result = seleccionar_estrategia({"desde": "2024-01-01"})
        assert "--since=2024-01-01" in result["flags_base"]

    def test_flags_base_con_hasta(self) -> None:
        """Test hasta filter is added to flags_base."""
        result = seleccionar_estrategia({"hasta": "2024-12-31"})
        assert "--until=2024-12-31" in result["flags_base"]

    def test_flags_base_con_max_count(self) -> None:
        """Test max_count is added to flags_base."""
        result = seleccionar_estrategia({"max_count": 500})
        assert "--max-count=500" in result["flags_base"]

    def test_flags_base_siempre_tiene_all(self) -> None:
        """Test --all is always in flags_base."""
        result = seleccionar_estrategia({})
        assert "--all" in result["flags_base"]

    def test_flags_contenido_modo_l_con_funcion(self) -> None:
        """Test modo l with funcion generates correct flags."""
        result = seleccionar_estrategia({"modo": "l", "archivo": "test.py", "funcion": "my_func"})
        assert any(":my_func:test.py" in f for f in result["flags_contenido"])

    def test_flags_contenido_modo_l_sin_funcion(self) -> None:
        """Test modo l without funcion uses texto as range."""
        result = seleccionar_estrategia({"modo": "l", "archivo": "test.py", "texto": "10,20"})
        assert any("10,20:test.py" in f for f in result["flags_contenido"])

    def test_descripcion_contiene_texto(self) -> None:
        """Test descripcion contains searched texto."""
        result = seleccionar_estrategia({"texto": "test", "modo": "grep"})
        assert "test" in result["descripcion"]

    def test_retorna_dict_completo(self) -> None:
        """Test returns dict with all expected keys."""
        result = seleccionar_estrategia({"texto": "test"})
        assert "modo" in result
        assert "descripcion" in result
        assert "flags_base" in result
        assert "flags_contenido" in result

    def test_flags_son_strings(self) -> None:
        """Test all flags are strings."""
        result = seleccionar_estrategia({})
        for flag in result["flags_base"]:
            assert isinstance(flag, str)
        for flag in result["flags_contenido"]:
            assert isinstance(flag, str)
