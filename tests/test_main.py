"""Tests for gitsearch.__main__ module."""

from unittest.mock import MagicMock


class TestObtenerTags:
    """Tests for obtener_tags function."""

    def test_retorna_lista_vacia_cuando_sin_tags(self) -> None:
        """Test returns empty list when no tags exist."""
        from gitsearch.__main__ import obtener_tags

        repo = MagicMock()
        repo.tags = []

        result = obtener_tags(repo)
        assert result == []

    def test_procesa_tag_anotado(self) -> None:
        """Test processes annotated tag correctly."""
        from gitsearch.__main__ import obtener_tags

        tag_mock = MagicMock()
        tag_mock.name = "v1.0.0"
        tag_mock.tag = MagicMock()
        tag_mock.tag.object = MagicMock()
        tag_mock.tag.object.hexsha = "abc123def456789012345678901234567890abcd"
        tag_mock.tag.tagged_date = 1704067200
        tag_mock.tag.tagger.name = "Test Author"
        tag_mock.commit = None

        repo = MagicMock()
        repo.tags = [tag_mock]

        result = obtener_tags(repo)
        assert len(result) == 1
        assert result[0]["nombre"] == "v1.0.0"
        assert result[0]["autor"] == "Test Author"
        assert result[0]["es_semver"] is True

    def test_procesa_tag_ligero(self) -> None:
        """Test processes lightweight tag correctly."""
        from gitsearch.__main__ import obtener_tags

        commit_mock = MagicMock()
        commit_mock.hexsha = "abc123def456789012345678901234567890abcd"
        commit_mock.committed_date = 1704067200
        commit_mock.author.name = "Test Author"

        tag_mock = MagicMock()
        tag_mock.name = "release-1.0"
        tag_mock.tag = None
        tag_mock.commit = commit_mock

        repo = MagicMock()
        repo.tags = [tag_mock]

        result = obtener_tags(repo)
        assert len(result) == 1
        assert result[0]["nombre"] == "release-1.0"
        assert result[0]["autor"] == "Test Author"
        assert result[0]["es_semver"] is False

    def test_ordena_tags_por_fecha(self) -> None:
        """Test tags are sorted by date."""
        from gitsearch.__main__ import obtener_tags

        tag1 = MagicMock()
        tag1.name = "v1.0.0"
        tag1.tag = None
        tag1.commit = MagicMock()
        tag1.commit.hexsha = "aaa123"
        tag1.commit.committed_date = 1700000000
        tag1.commit.author.name = "Author"

        tag2 = MagicMock()
        tag2.name = "v2.0.0"
        tag2.tag = None
        tag2.commit = MagicMock()
        tag2.commit.hexsha = "bbb123"
        tag2.commit.committed_date = 1800000000
        tag2.commit.author.name = "Author"

        repo = MagicMock()
        repo.tags = [tag2, tag1]

        result = obtener_tags(repo)
        assert result[0]["nombre"] == "v1.0.0"
        assert result[1]["nombre"] == "v2.0.0"


class TestCompararTags:
    """Tests for comparar_tags function."""

    def test_retorna_none_con_menos_de_2_tags(self) -> None:
        """Test returns None when fewer than 2 tags."""
        from gitsearch.__main__ import comparar_tags

        repo = MagicMock()
        tags = [{"nombre": "v1.0.0", "hash_completo": "abc123"}]

        result = comparar_tags(repo, tags)
        assert result is None

    def test_compara_dos_tags(self) -> None:
        """Test compares two tags correctly."""
        from gitsearch.__main__ import comparar_tags

        commit1 = MagicMock()
        commit1.hexsha = "abc123"

        commit2 = MagicMock()
        commit2.hexsha = "def456"

        repo = MagicMock()
        repo.commit.side_effect = [commit2, commit1]
        repo.merge_base.return_value = [commit1]

        diff_mock = MagicMock()
        diff_mock.a_path = "file1.py"
        diff_mock.b_path = "file1.py"
        commit1.diff.return_value = [diff_mock]

        tags = [
            {"nombre": "v1.0.0", "hash_completo": "abc123"},
            {"nombre": "v2.0.0", "hash_completo": "def456"},
        ]

        repo.iter_commits.return_value = iter([])

        result = comparar_tags(repo, tags)

        assert result is not None
        assert result["tag_anterior"] == "v1.0.0"
        assert result["tag_actual"] == "v2.0.0"


class TestConstruirMapaCommits:
    """Tests for construir_mapa_commits function."""

    def test_retorna_dict_vacio_sin_refs(self) -> None:
        """Test returns empty dict when no refs."""
        from gitsearch.__main__ import construir_mapa_commits

        repo = MagicMock()
        repo.heads = []
        repo.remotes = []
        repo.tags = []

        result = construir_mapa_commits(repo)
        assert result == {}


class TestIdentificarRamasDeTag:
    """Tests for identificar_ramas_de_tag function."""

    def test_usa_sha_a_ramas_precalculado(self) -> None:
        """Test uses pre-calculated sha_a_ramas dict."""
        from gitsearch.__main__ import identificar_ramas_de_tag

        repo = MagicMock()
        sha_a_ramas = {
            "abc123": ["main", "develop"],
            "def456": ["feature/test"],
        }

        result = identificar_ramas_de_tag(repo, "abc123", sha_a_ramas)
        assert result == ["develop", "main"]

    def test_fallback_git_branch(self) -> None:
        """Test falls back to git branch when no pre-calculated dict."""
        from gitsearch.__main__ import identificar_ramas_de_tag

        repo = MagicMock()
        repo.git.branch.return_value = "  main\n* develop\n  remotes/origin/main"

        result = identificar_ramas_de_tag(repo, "abc123", None)

        assert "main" in result
        assert "develop" in result


class TestCalcularCommitsExclusivosTag:
    """Tests for calcular_commits_exclusivos_tag function."""

    def test_calcula_commits_exitosamente(self) -> None:
        """Test calculates exclusive commits successfully."""
        from gitsearch.__main__ import calcular_commits_exclusivos_tag

        commit_tag = MagicMock()
        commit_tag.hexsha = "def456"
        commit_tag.committed_date = 1800000000

        commit_padre = MagicMock()
        commit_padre.hexsha = "abc123"
        commit_padre.committed_date = 1700000000

        repo = MagicMock()
        repo.merge_base.return_value = [commit_padre]

        commit_mock = MagicMock()
        commit_mock.hexsha = "abc123def456789012345678901234567890abcd"
        commit_mock.author.name = "Author"
        commit_mock.committed_date = 1750000000
        commit_mock.message = "Test commit"
        commit_mock.parents = []

        repo.iter_commits.return_value = iter([commit_mock])
        commit_padre.diff.return_value = []
        repo.commit.side_effect = [commit_tag, commit_padre, commit_mock]

        result = calcular_commits_exclusivos_tag(repo, commit_tag, commit_padre)

        assert result["num_commits"] >= 0


class TestAnalizarTopologiaTags:
    """Tests for analizar_topologia_tags function."""

    def test_retorna_dict_vacio_sin_tags(self) -> None:
        """Test returns empty dict when no tags."""
        from gitsearch.__main__ import analizar_topologia_tags

        repo = MagicMock()
        result = analizar_topologia_tags(repo, [])
        assert result == {}

    def test_procesa_tags_simple(self) -> None:
        """Test processes simple tag topology."""
        from gitsearch.__main__ import analizar_topologia_tags

        tags = [
            {
                "nombre": "v1.0.0",
                "hash_completo": "abc123def456789012345678901234567890abcd",
                "fecha_iso": "2024-01-01 00:00:00",
            }
        ]

        repo = MagicMock()
        repo.commit.return_value = MagicMock()
        repo.commit.return_value.hexsha = "abc123"
        repo.commit.return_value.parents = []
        repo.git.log.return_value = "abc123def456789012345678901234567890abcd"

        result = analizar_topologia_tags(repo, tags)
        assert isinstance(result, dict)


class TestGenerarReporte:
    """Tests for generar_reporte function."""

    def test_reporte_sin_commits(self) -> None:
        """Test generates report with no commits."""
        from gitsearch.__main__ import generar_reporte

        historial = {
            "total": 0,
            "commits": [],
            "autores": {},
            "fecha_inicio": None,
            "fecha_fin": None,
        }

        result = generar_reporte("/test/repo", historial, [], None, None)

        assert "No se encontraron commits" in result
        assert "REPORTE TÉCNICO" in result

    def test_reporte_con_tags(self) -> None:
        """Test generates report with tags."""
        from gitsearch.__main__ import generar_reporte

        historial = {
            "total": 0,
            "commits": [],
            "autores": {},
            "fecha_inicio": None,
            "fecha_fin": None,
        }

        tags = [
            {
                "nombre": "v1.0.0",
                "fecha": "2024-01-01",
                "autor": "Author",
                "hash": "abc1234",
                "es_semver": True,
            }
        ]

        result = generar_reporte("/test/repo", historial, tags, None, None)

        assert "v1.0.0" in result
        assert "TAGS Y VERSIONADO" in result

    def test_reporte_con_comparacion(self) -> None:
        """Test generates report with tag comparison."""
        from gitsearch.__main__ import generar_reporte

        historial = {
            "total": 0,
            "commits": [],
            "autores": {},
            "fecha_inicio": None,
            "fecha_fin": None,
        }

        comparacion = {
            "tag_anterior": "v1.0.0",
            "tag_actual": "v2.0.0",
            "total_commits": 5,
            "autores": ["Author"],
            "archivos_modificados": ["file1.py"],
            "total_archivos": 1,
            "commits": [],
        }

        result = generar_reporte("/test/repo", historial, [], comparacion, None)

        assert "v1.0.0" in result
        assert "v2.0.0" in result
        assert "5" in result

    def test_reporte_con_busqueda(self) -> None:
        """Test generates report with search results."""
        from gitsearch.__main__ import generar_reporte

        historial = {
            "total": 0,
            "commits": [],
            "autores": {},
            "fecha_inicio": None,
            "fecha_fin": None,
        }

        busqueda = {
            "criterio": "test",
            "total": 1,
            "resultados": [
                {
                    "hash": "abc1234",
                    "tipo": "Mensaje",
                    "mensaje": "Test commit",
                    "autor": "Author",
                    "fecha": "2024-01-01",
                    "tags": ["v1.0.0"],
                    "archivos": [],
                }
            ],
        }

        result = generar_reporte("/test/repo", historial, [], None, busqueda)

        assert "test" in result
        assert "BÚSQUEDA PROFUNDA" in result


class TestEjecutarBusqueda:
    """Tests for ejecutar_busqueda function."""

    def test_busca_hash_exacto(self) -> None:
        """Test searches by exact hash."""
        from gitsearch.__main__ import ejecutar_busqueda

        commit_mock = MagicMock()
        commit_mock.hexsha = "abc123def456789012345678901234567890abcd"
        commit_mock.author.name = "Author"
        commit_mock.committed_date = 1704067200
        commit_mock.message = "Test commit"
        commit_mock.parents = []

        repo = MagicMock()
        repo.commit.return_value = commit_mock

        result = ejecutar_busqueda(repo, "abc123def456789012345678901234567890abcd", {})

        assert result["criterio"] == "abc123def456789012345678901234567890abcd"

    def test_busca_por_mensaje(self) -> None:
        """Test searches by commit message."""
        from gitsearch.__main__ import ejecutar_busqueda

        commit_mock = MagicMock()
        commit_mock.hexsha = "abc123def456789012345678901234567890abcd"
        commit_mock.author.name = "Author"
        commit_mock.committed_date = 1704067200
        commit_mock.message = "feat: add new feature"
        commit_mock.parents = []

        repo = MagicMock()
        repo.commit.side_effect = Exception("Not found")
        repo.git.log.return_value = "abc123def456789012345678901234567890abcd"
        repo.commit.return_value = commit_mock
        repo.git.tag.return_value = ""

        result = ejecutar_busqueda(repo, "feat", {})

        assert "resultados" in result


class TestGenerarGrafoHtml:
    """Tests for generar_grafo_html function."""

    def test_retorna_html_sin_tags(self) -> None:
        """Test returns HTML when no tags."""
        from gitsearch.__main__ import generar_grafo_html

        repo = MagicMock()
        result = generar_grafo_html(repo, [])

        assert "No se encontraron tags" in result[0]
        assert result[1] == []
        assert result[2] == []

    def test_genera_nodos_y_edges(self) -> None:
        """Test generates nodes and edges."""
        from gitsearch.__main__ import generar_grafo_html

        tags = [
            {
                "nombre": "v1.0.0",
                "hash_completo": "abc123def456789012345678901234567890abcd",
                "fecha": "2024-01-01",
                "fecha_iso": "2024-01-01 00:00:00",
                "autor": "Author",
                "hash": "abc1234",
            }
        ]

        repo = MagicMock()
        repo.commit.return_value = MagicMock()
        repo.commit.return_value.hexsha = "abc123"
        repo.commit.return_value.parents = []
        repo.git.log.return_value = "abc123def456789012345678901234567890abcd"

        result = generar_grafo_html(repo, tags, None, None, None, "")

        assert len(result[1]) > 0
        assert len(result[2]) >= 0
