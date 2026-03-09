# GitSearch — Guía de Uso

> **Versión:** 1.0 · **Alcance:** Solo lectura sobre el repositorio local.  
> Nunca modifica commits, ramas, tags ni el repositorio remoto.

---

## Cómo usar GitSearch

Al ejecutar `start.bat`, el análisis genera `reporte_grafo.html`. Ese archivo incluye automáticamente el **panel de búsqueda avanzada GitSearch** incrustado.

### Abrir el panel

1. Abrir `reporte_grafo.html` en el navegador.
2. Hacer clic en el botón **🔍 GitSearch** (esquina superior derecha del grafo).

---

## Modos de búsqueda disponibles

### 💬 Mensaje (`grep`)
Busca commits cuyo **mensaje** contiene el texto.  
Más rápido: no analiza diffs.

**Ejemplos:**
```
hotfix
JIRA-4521
```

### 🎯 Exacto `-S` (Pickaxe)
Busca commits donde el **número de ocurrencias** exactas del texto cambió (fue añadido o eliminado).  
Ideal para saber cuándo se introdujo o eliminó una cadena específica.

**Ejemplos:**
```
"throw new Exception"
```

### 🔎 Regex `-G`
Busca commits cuyo diff **contiene** el patrón como expresión regular.  
Útil cuando el texto exacto varía pero el patrón es reconocible.

**Ejemplos:**
```
raise ValueError
\bNIT\b
```

---

## Filtros adicionales

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| **Autor** | Filtra por nombre de autor (parcial) | `garcia`, `tamayo` |
| **Desde** | Fecha mínima del commit | `2025-01-01` |
| **Hasta** | Fecha máxima del commit | `2025-12-31` |

Los filtros de fecha/autor se aplican **antes** del análisis de diffs para maximizar el rendimiento.

---

## Resultados y navegación

Cada resultado muestra:
- **Hash** del commit (7 chars)
- **Modo** con que fue encontrado
- **Mensaje**, autor y fecha
- **Archivos** modificados (hasta 3)
- **Padre ↑** — clic para navegar al commit padre y resaltarlo en el grafo
- **Ver nodo ↗** — clic para resaltar y enfocar el nodo del grafo que contiene ese commit

### Commit padre navegable

En la ficha de cada commit (panel lateral al hacer clic en un nodo) también se muestra el/los commits padre. Hacer clic en el hash del padre navega directamente a ese nodo en el grafo.

---

## Estrategia de selección inteligente

El motor elige automáticamente el comando más eficiente:

```
Texto + modo grep        → git log --grep   (sin análisis de diffs, muy rápido)
Texto + modo -S          → git log -S       (pickaxe, analiza diffs)
Texto + modo -G          → git log -G       (regex en diffs)
Con fechas definidas     → --since/--until aplicados PRIMERO para acotar commits
```

---

## Portabilidad del HTML

El HTML generado es **auto-contenido**: los datos de todos los commits (incluidos mensajes, fechas, autores, padres y diffs parciales) se incrustan como JSON compacto en el propio archivo.

✅ La búsqueda funciona en cualquier equipo sin Git ni Python instalados.  
⚠️ Las búsquedas operan sobre los datos incrustados al momento de la generación. Para incluir nuevos commits, regenerar el HTML con `start.bat`.

---

## Archivos del módulo

| Archivo | Responsabilidad |
|---------|-----------------|
| `gitsearch/__init__.py` | Marcador de paquete |
| `gitsearch/filters.py` | Validación y normalización de parámetros |
| `gitsearch/strategy.py` | Selección inteligente del comando git |
| `gitsearch/engine.py` | Motor de consultas (solo lectura) |
| `gitsearch/html_builder.py` | Generador del panel HTML/JS |
| `docs/gitsearch_guia.md` | Esta guía |
