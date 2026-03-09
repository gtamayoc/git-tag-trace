# -*- coding: utf-8 -*-
"""
html_builder.py — Generador del panel de búsqueda avanzada para el HTML.

Toma los commits ya calculados por main.py (sin llamadas Git adicionales
en Fase 1) y produce:
  - Un bloque JSON compacto incrustado con todos los commits + parents.
  - El markup HTML del panel de búsqueda avanzada.
  - El bloque JS que coordina con el grafo vis-network existente.

El resultado se inyecta en el HTML via el placeholder <!-- GITSEARCH_PANEL -->.
"""

import json


def generar_panel_busqueda(commits_data: list) -> str:
    """
    Genera el bloque completo (CSS + HTML + JS) del panel de búsqueda avanzada.

    Args:
        commits_data: lista de commits ya calculada por obtener_historial()
                      Cada commit tiene: hash, full_hash, autor, fecha,
                      mensaje, mensaje_full, parents, diff.

    Retorna un string HTML que se inyecta en el placeholder <!-- GITSEARCH_PANEL -->.
    """
    # Serializar datos de commits (ya tienen parents desde main.py)
    commits_json = json.dumps(commits_data, ensure_ascii=False, separators=(",", ":"))

    return f"""
<!-- ══════════════════════════════════════════════════════════
     GITSEARCH — Panel de Búsqueda Avanzada
     Generado automáticamente. No editar manualmente.
     ══════════════════════════════════════════════════════════ -->

<style>
  /*
   * ── GitSearch Panel UI — Diseño Monocromático [VISUAL ONLY]
   *    Paleta: negro / blanco / grises. Sin colores de acento fuertes.
   *    Nota: todos los IDs y clases se mantienen idénticos para
   *    compatibilidad con el JS existente.
   */

  /* ── Botón flotante de apertura ── */
  #gs-toggle-btn {{
    position: absolute;
    top: 60px; /* offset respecto a topbar principal */
    right: 530px;
    z-index: 200;
    background: rgba(14, 14, 14, 0.94);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #d0d0d0;
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    backdrop-filter: blur(16px);
    font-family: 'Inter', sans-serif;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
    letter-spacing: 0.01em;
  }}
  #gs-toggle-btn:hover {{
    background: #1a1a1a;
    border-color: rgba(255, 255, 255, 0.25);
    color: #ffffff;
  }}

  /* ── Panel principal ── */
  #gs-panel {{
    position: absolute;
    top: 48px; /* offset topbar */
    right: 0;
    width: 480px;
    height: calc(100% - 48px);
    background: rgba(10, 10, 10, 0.98);
    backdrop-filter: blur(28px);
    border-left: 1px solid rgba(255, 255, 255, 0.07);
    box-shadow: -6px 0 30px rgba(0, 0, 0, 0.7);
    z-index: 1100;
    display: flex;
    flex-direction: column;
    transform: translateX(100%);
    transition: transform 0.32s cubic-bezier(0.4, 0, 0.2, 1);
    font-family: 'Inter', -apple-system, sans-serif;
  }}
  #gs-panel.gs-open {{ transform: translateX(0); }}

  /* ── Cabecera del panel ── */
  #gs-header {{
    padding: 16px 22px 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }}
  #gs-header h2 {{
    margin: 0;
    font-size: 0.82rem;
    font-weight: 700;
    color: #e0e0e0;
    display: flex;
    align-items: center;
    gap: 8px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}
  #gs-close {{
    background: none;
    border: none;
    color: #555555;
    font-size: 18px;
    cursor: pointer;
    line-height: 1;
    padding: 3px 6px;
    border-radius: 4px;
    transition: color 0.15s, background 0.15s;
  }}
  #gs-close:hover {{ color: #e0e0e0; background: #1a1a1a; }}

  /* ── Formulario de búsqueda ── */
  #gs-form {{
    padding: 14px 22px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    flex-shrink: 0;
  }}
  .gs-row {{ display: flex; gap: 8px; margin-bottom: 10px; }}
  .gs-row:last-child {{ margin-bottom: 0; }}

  .gs-input {{
    flex: 1;
    background: #111111;
    border: 1px solid rgba(255, 255, 255, 0.10);
    color: #e0e0e0;
    padding: 8px 12px;
    border-radius: 5px;
    font-size: 0.80rem;
    outline: none;
    font-family: 'Inter', sans-serif;
    transition: border-color 0.15s;
  }}
  .gs-input:focus {{ border-color: rgba(255, 255, 255, 0.25); }}
  .gs-input::placeholder {{ color: #444444; }}

  .gs-btn-search {{
    background: #1a1a1a;
    border: 1px solid rgba(255, 255, 255, 0.14);
    color: #e0e0e0;
    padding: 8px 16px;
    border-radius: 5px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    font-family: 'Inter', sans-serif;
    transition: background 0.15s, border-color 0.15s;
  }}
  .gs-btn-search:hover {{
    background: #242424;
    border-color: rgba(255, 255, 255, 0.26);
  }}

  .gs-btn-clear {{
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: #555555;
    padding: 8px 10px;
    border-radius: 5px;
    font-size: 0.80rem;
    cursor: pointer;
    transition: color 0.15s, border-color 0.15s;
  }}
  .gs-btn-clear:hover {{ color: #aaaaaa; border-color: rgba(255, 255, 255, 0.18); }}

  /* ── Selección de modo ── */
  .gs-modes {{ display: flex; gap: 4px; flex-wrap: wrap; }}
  .gs-mode-btn {{
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: #555555;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.70rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
    font-family: 'Inter', sans-serif;
  }}
  .gs-mode-btn.active, .gs-mode-btn:hover {{
    background: #1a1a1a;
    border-color: rgba(255, 255, 255, 0.20);
    color: #cccccc;
  }}

  /* ── Área de resultados ── */
  #gs-results-wrap {{
    flex: 1;
    overflow-y: auto;
    padding: 14px 22px;
    scrollbar-width: thin;
    scrollbar-color: #2a2a2a transparent;
  }}
  #gs-results-wrap::-webkit-scrollbar {{ width: 4px; }}
  #gs-results-wrap::-webkit-scrollbar-track {{ background: transparent; }}
  #gs-results-wrap::-webkit-scrollbar-thumb {{ background: #2a2a2a; border-radius: 2px; }}

  /* ── Status bar ── */
  #gs-status {{
    font-size: 0.70rem;
    color: #555555;
    margin-bottom: 12px;
    min-height: 16px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}

  /* ── Tarjetas de resultado ── */
  .gs-result-item {{
    padding: 11px 13px;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    margin-bottom: 6px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
    background: transparent;
  }}
  .gs-result-item:hover {{
    border-color: rgba(255, 255, 255, 0.16);
    background: #111111;
  }}
  .gs-result-item.gs-active {{
    border-color: rgba(255, 255, 255, 0.22);
    background: #111111;
  }}

  /* ── Hash en resultado ── */
  .gs-result-hash {{
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    font-size: 0.72rem;
    color: #aaaaaa;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }}

  /* ── Badge de modo ── */
  .gs-badge {{
    background: #1a1a1a;
    border: 1px solid rgba(255, 255, 255, 0.10);
    color: #777777;
    font-size: 0.60rem;
    padding: 1px 6px;
    border-radius: 3px;
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}

  /* ── Mensaje del commit ── */
  .gs-result-msg {{
    font-size: 0.80rem;
    color: #e0e0e0;
    margin: 5px 0 3px;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  /* ── Metadata (autor / fecha) ── */
  .gs-result-meta {{
    font-size: 0.68rem;
    color: #555555;
    margin-bottom: 5px;
  }}

  /* ── Archivos afectados ── */
  .gs-result-files {{
    font-size: 0.65rem;
    color: #555555;
    margin-bottom: 5px;
    font-family: 'JetBrains Mono', monospace;
  }}

  /* ── Links de padres ── */
  .gs-parent-row {{
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 5px;
  }}
  .gs-parent-label {{
    font-size: 0.65rem;
    color: #444444;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .gs-parent-link {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    color: #888888;
    background: #111111;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 3px;
    padding: 1px 7px;
    cursor: pointer;
    text-decoration: none;
    transition: color 0.15s, border-color 0.15s;
  }}
  .gs-parent-link:hover {{
    color: #cccccc;
    border-color: rgba(255, 255, 255, 0.20);
  }}

  /* ── Link "ver nodo ↗" ── */
  .gs-node-link {{
    font-size: 0.65rem;
    color: #666666;
    background: #111111;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 3px;
    padding: 1px 7px;
    cursor: pointer;
    margin-left: auto;
    transition: color 0.15s, border-color 0.15s;
    font-family: 'Inter', sans-serif;
  }}
  .gs-node-link:hover {{
    color: #cccccc;
    border-color: rgba(255, 255, 255, 0.20);
  }}

  /* ── Sin resultados ── */
  .gs-no-results {{
    color: #444444;
    font-size: 0.78rem;
    text-align: center;
    padding: 32px 0;
  }}
</style>

<!-- Botón flotante para abrir GitSearch -->
<button id="gs-toggle-btn" onclick="gsTogglePanel()" title="Búsqueda avanzada en historial">
  🔍 <span>GitSearch</span>
</button>

<!-- Panel de búsqueda avanzada -->
<div id="gs-panel">
  <div id="gs-header">
    <h2>🔍 Búsqueda Avanzada de Historial</h2>
    <button id="gs-close" onclick="gsTogglePanel()" title="Cerrar">✕</button>
  </div>

  <div id="gs-form">
    <!-- Texto + botones -->
    <div class="gs-row">
      <input id="gs-text" class="gs-input" type="text"
             placeholder="Texto, patrón, palabra clave…"
             onkeyup="if(event.key==='Enter') gsRunSearch()">
      <button class="gs-btn-search" onclick="gsRunSearch()">Buscar</button>
      <button class="gs-btn-clear" onclick="gsClearResults()" title="Limpiar">✕</button>
    </div>

    <!-- Modos -->
    <div class="gs-row">
      <div class="gs-modes" id="gs-modes">
        <button class="gs-mode-btn active" data-mode="grep" onclick="gsSetMode(this)">💬 Mensaje</button>
        <button class="gs-mode-btn"        data-mode="s"    onclick="gsSetMode(this)">🎯 Exacto (-S)</button>
        <button class="gs-mode-btn"        data-mode="g"    onclick="gsSetMode(this)">🔎 Regex (-G)</button>
      </div>
    </div>

    <!-- Filtros adicionales -->
    <div class="gs-row">
      <input id="gs-autor"  class="gs-input" type="text"  placeholder="Autor (opcional)">
      <input id="gs-desde"  class="gs-input" type="date"  title="Desde (fecha)">
      <input id="gs-hasta"  class="gs-input" type="date"  title="Hasta (fecha)">
    </div>
  </div>

  <!-- Resultados -->
  <div id="gs-results-wrap">
    <div id="gs-status">Ingresa un criterio para buscar en el historial.</div>
    <div id="gs-results-list"></div>
  </div>
</div>

<script>
// ══════════════════════════════════════════════════════
//  GITSEARCH — lógica del panel de búsqueda avanzada
// ══════════════════════════════════════════════════════

// Datos incrustados en tiempo de generación (solo lectura, ya calculados)
const gsCommitsData = {commits_json};

let gsSelectedMode = 'grep';
let gsActiveItemEl = null;

// ── Abrir / cerrar panel ──────────────────────────────
function gsTogglePanel() {{
  const panel = document.getElementById('gs-panel');
  const btn   = document.getElementById('gs-toggle-btn');
  const isOpen = panel.classList.contains('gs-open');
  panel.classList.toggle('gs-open');
  btn.style.right = isOpen ? '530px' : '20px';
  if (!isOpen) {{
    setTimeout(() => document.getElementById('gs-text').focus(), 350);
  }}
}}

// ── Selección de modo ─────────────────────────────────
function gsSetMode(el) {{
  document.querySelectorAll('.gs-mode-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  gsSelectedMode = el.dataset.mode;
}}

// ── Ejecutar búsqueda sobre datos incrustados ─────────
function gsRunSearch() {{
  const texto = (document.getElementById('gs-text').value || '').trim().toLowerCase();
  const autor = (document.getElementById('gs-autor').value || '').trim().toLowerCase();
  const desde = document.getElementById('gs-desde').value || '';
  const hasta = document.getElementById('gs-hasta').value || '';

  if (!texto && !autor && !desde && !hasta) {{
    gsSetStatus('Ingresa al menos un criterio de búsqueda.');
    return;
  }}

  const modo = gsSelectedMode;
  let resultados = gsCommitsData;

  // Filtro por autor
  if (autor) {{
    resultados = resultados.filter(c =>
      (c.autor || '').toLowerCase().includes(autor)
    );
  }}

  // Filtro por fecha
  if (desde) {{
    resultados = resultados.filter(c => c.fecha && c.fecha.slice(0, 10) >= desde);
  }}
  if (hasta) {{
    resultados = resultados.filter(c => c.fecha && c.fecha.slice(0, 10) <= hasta);
  }}

  // Filtro por texto según modo
  if (texto) {{
    if (modo === 'grep') {{
      // Búsqueda en mensaje de commit
      resultados = resultados.filter(c =>
        (c.mensaje || '').toLowerCase().includes(texto) ||
        (c.mensaje_full || '').toLowerCase().includes(texto)
      );
    }} else if (modo === 's') {{
      // Pickaxe: búsqueda exacta en mensaje o diff (sobre datos incrustados)
      resultados = resultados.filter(c =>
        (c.mensaje || '').toLowerCase().includes(texto) ||
        (c.diff || '').toLowerCase().includes(texto)
      );
    }} else if (modo === 'g') {{
      // Regex en diff
      try {{
        const rx = new RegExp(texto, 'i');
        resultados = resultados.filter(c =>
          rx.test(c.mensaje || '') || rx.test(c.diff || '')
        );
      }} catch(e) {{
        gsSetStatus('⚠️ Patrón regex no válido.');
        return;
      }}
    }}
  }}

  gsRenderResults(resultados, texto, modo);
}}

// ── Renderizar resultados ─────────────────────────────
function gsRenderResults(resultados, texto, modo) {{
  const list = document.getElementById('gs-results-list');

  if (resultados.length === 0) {{
    gsSetStatus('');
    list.innerHTML = '<div class="gs-no-results">Sin resultados para esta búsqueda.</div>';
    gsLimpiarHighlights();
    return;
  }}

  gsSetStatus(`${{resultados.length}} commit${{resultados.length !== 1 ? 's' : ''}} encontrado${{resultados.length !== 1 ? 's' : ''}} · modo: ${{modo}}`);

  // Resaltar todos los nodos del grafo que contengan algún resultado
  gsResaltarNodosDeResultados(resultados);

  list.innerHTML = resultados.slice(0, 300).map((c, idx) => {{
    const padreLinks = (c.parents || []).map((ph, i) => {{
      const pFull = (c.parent_full || [])[i] || ph;
      return `<span class="gs-parent-link" onclick="gsNavParent('${{gsEscape(pFull || ph)}}')">↑ ${{gsEscape(ph)}}</span>`;
    }}).join(' ');

    // Determinar el nodo del grafo al que pertenece
    const tagSha = gsObtenerNodoDe(c.full_hash || c.hash);
    const nodoLink = tagSha
      ? `<span class="gs-node-link" onclick="gsIrANodo('${{gsEscape(tagSha)}}')">ver nodo ↗</span>`
      : '';

    const archivosStr = (c.archivos || []).length > 0
      ? `<div class="gs-result-files">📄 ${{gsEscape((c.archivos || []).slice(0,3).join(', ') + ((c.archivos||[]).length>3?' ...':''))}}</div>`
      : '';

    return `
      <div class="gs-result-item" id="gs-item-${{idx}}" onclick="gsSelectResult(this, '${{gsEscape(c.full_hash || c.hash)}}', '${{gsEscape(tagSha || '')}}')">
        <div class="gs-result-hash" style="display:flex; align-items:center; gap:6px;">
          <span style="cursor:pointer; text-decoration:underline;" title="Abrir detalle" onclick="if(typeof showCommitModal !== 'undefined') {{ event.stopPropagation(); showCommitModal('${{gsEscape(c.full_hash || c.hash)}}'); }}">${{gsEscape(c.hash)}}</span>
          ${{typeof getCopyBtnHtml !== 'undefined' ? getCopyBtnHtml(c.full_hash || c.hash) : ''}}
          <span class="gs-badge">${{gsEscape(modo)}}</span>
          ${{nodoLink}}
        </div>
        <div class="gs-result-msg">${{gsEscape(c.mensaje || '')}}</div>
        <div class="gs-result-meta">👤 ${{gsEscape(c.autor)}} · 📅 ${{gsEscape(c.fecha)}}</div>
        ${{archivosStr}}
        ${{padreLinks ? `<div class="gs-parent-row"><span class="gs-parent-label">padre:</span>${{padreLinks}}</div>` : ''}}
      </div>`;
  }}).join('');
}}

// ── Seleccionar resultado y destacar en grafo ─────────
function gsSelectResult(el, fullHash, tagSha) {{
  if (gsActiveItemEl) gsActiveItemEl.classList.remove('gs-active');
  el.classList.add('gs-active');
  gsActiveItemEl = el;

  // Navegar en el grafo al nodo que contiene este commit
  if (tagSha && typeof network !== 'undefined') {{
    gsIrANodo(tagSha);
  }}

  // Si el panel lateral de commits está disponible, mostrar el commit
  if (typeof selectCommitByHash === 'function') {{
    selectCommitByHash(fullHash);
  }}
  
  // Abrir la vista de detalle
  if (typeof showCommitModal !== 'undefined') {{
    showCommitModal(fullHash);
  }}
}}

// ── Navegar al nodo padre ─────────────────────────────
function gsNavParent(parentFullHash) {{
  const tagSha = gsObtenerNodoDe(parentFullHash);
  if (tagSha) {{
    gsIrANodo(tagSha);
  }}
  if (typeof selectCommitByHash === 'function') {{
    selectCommitByHash(parentFullHash);
  }}
}}

// ── Ir a nodo en el grafo y resaltarlo ───────────────
function gsIrANodo(sha) {{
  if (typeof network === 'undefined' || typeof nodes === 'undefined') return;
  if (typeof highlightNode === 'function') {{
    highlightNode(sha);
  }}
  network.focus(sha, {{ scale: 1.3, animation: false }});
  network.selectNodes([sha]);
  
  // Parche para vis-network: evitar que la cámara quede enganchada al ratón
  network.setOptions({{ interaction: {{ dragView: false }} }});
  network.setOptions({{ interaction: {{ dragView: true }} }});
}}

// ── Resaltar nodos de todos los resultados ────────────
function gsResaltarNodosDeResultados(resultados) {{
  if (typeof network === 'undefined' || typeof nodes === 'undefined') return;
  gsLimpiarHighlights();
  const nodosAfectados = new Set();
  resultados.forEach(c => {{
    const sha = gsObtenerNodoDe(c.full_hash || c.hash);
    if (sha) nodosAfectados.add(sha);
  }});
  nodosAfectados.forEach(sha => {{
    try {{
      const n = nodes.get(sha);
      if (n) {{
        nodes.update({{ id: sha, color: {{ background: '#6e40c9', border: '#a371f7' }} }});
      }}
    }} catch(e) {{}}
  }});
}}

// ── Limpiar highlights del grafo ──────────────────────
function gsLimpiarHighlights() {{
  if (typeof network === 'undefined' || typeof nodes === 'undefined' || typeof nodesData === 'undefined') return;
  nodesData.forEach(n => {{
    try {{
      nodes.update({{ id: n.id, color: {{ background: n.is_main ? '#1f6feb' : '#1a7f37', border: '#ffffff' }} }});
    }} catch(e) {{}}
  }});
}}

// ── Obtener el SHA del nodo del grafo que contiene el commit ──
function gsObtenerNodoDe(hash) {{
  if (typeof commitToTag !== 'undefined' && commitToTag) {{
    return commitToTag[hash] || commitToTag[(hash||'').slice(0,7)] || null;
  }}
  return null;
}}

// ── Limpiar resultados ────────────────────────────────
function gsClearResults() {{
  document.getElementById('gs-text').value  = '';
  document.getElementById('gs-autor').value = '';
  document.getElementById('gs-desde').value = '';
  document.getElementById('gs-hasta').value = '';
  document.getElementById('gs-results-list').innerHTML = '';
  gsSetStatus('Ingresa un criterio para buscar en el historial.');
  gsActiveItemEl = null;
  gsLimpiarHighlights();
}}

// ── Helpers ───────────────────────────────────────────
function gsSetStatus(msg) {{
  document.getElementById('gs-status').textContent = msg;
}}

function gsEscape(s) {{
  return (s || '').toString()
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}}
</script>
<!-- ══════ FIN GITSEARCH ══════ -->
"""
