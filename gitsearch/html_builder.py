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
  /* ── GitSearch: botón flotante ── */
  #gs-toggle-btn {{
    position: absolute;
    top: 24px;
    right: 530px;
    z-index: 200;
    background: rgba(22,27,34,0.92);
    border: 1px solid rgba(255,255,255,0.15);
    color: #e6edf3;
    border-radius: 10px;
    padding: 8px 14px;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    backdrop-filter: blur(12px);
    transition: background 0.2s, border-color 0.2s;
  }}
  #gs-toggle-btn:hover {{ background: #2f81f7; border-color: #2f81f7; }}

  /* ── GitSearch: panel principal ── */
  #gs-panel {{
    position: absolute;
    top: 0;
    right: 0;
    width: 500px;
    height: 100%;
    background: rgba(13,17,23,0.98);
    backdrop-filter: blur(24px);
    border-left: 1px solid rgba(255,255,255,0.12);
    box-shadow: -8px 0 32px rgba(0,0,0,0.6);
    z-index: 1100;
    display: flex;
    flex-direction: column;
    transform: translateX(100%);
    transition: transform 0.35s cubic-bezier(0.4,0,0.2,1);
    font-family: 'Inter', sans-serif;
  }}
  #gs-panel.gs-open {{ transform: translateX(0); }}

  /* ── Cabecera ── */
  #gs-header {{
    padding: 20px 24px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }}
  #gs-header h2 {{
    margin: 0; font-size: 1rem; font-weight: 700; color: #e6edf3;
    display: flex; align-items: center; gap: 8px;
  }}
  #gs-close {{
    background: none; border: none; color: #7d8590;
    font-size: 22px; cursor: pointer; line-height: 1; padding: 0 4px;
  }}
  #gs-close:hover {{ color: #e6edf3; }}

  /* ── Formulario de búsqueda ── */
  #gs-form {{
    padding: 16px 24px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    flex-shrink: 0;
  }}
  .gs-row {{ display: flex; gap: 8px; margin-bottom: 10px; }}
  .gs-row:last-child {{ margin-bottom: 0; }}
  .gs-input {{
    flex: 1;
    background: #0d1117;
    border: 1px solid rgba(255,255,255,0.12);
    color: #e6edf3;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 0.82rem;
    outline: none;
    font-family: 'Inter', sans-serif;
  }}
  .gs-input:focus {{ border-color: #2f81f7; }}
  .gs-input::placeholder {{ color: #4d5566; }}
  .gs-btn-search {{
    background: #2f81f7;
    border: none;
    color: white;
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }}
  .gs-btn-search:hover {{ background: #388bfd; }}
  .gs-btn-clear {{
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    color: #7d8590;
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 0.8rem;
    cursor: pointer;
  }}
  .gs-btn-clear:hover {{ color: #e6edf3; }}

  /* Radios de modo */
  .gs-modes {{ display: flex; gap: 4px; flex-wrap: wrap; }}
  .gs-mode-btn {{
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    color: #7d8590;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    cursor: pointer;
    transition: 0.15s;
  }}
  .gs-mode-btn.active, .gs-mode-btn:hover {{
    background: rgba(47,129,247,0.15);
    border-color: #2f81f7;
    color: #58a6ff;
  }}

  /* ── Resultados ── */
  #gs-results-wrap {{
    flex: 1;
    overflow-y: auto;
    padding: 16px 24px;
    scrollbar-width: thin;
    scrollbar-color: #30363d transparent;
  }}
  #gs-status {{
    font-size: 0.75rem;
    color: #7d8590;
    margin-bottom: 12px;
    min-height: 18px;
  }}
  .gs-result-item {{
    padding: 12px 14px;
    border-radius: 7px;
    border: 1px solid rgba(255,255,255,0.07);
    margin-bottom: 8px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
  }}
  .gs-result-item:hover {{ border-color: #2f81f7; background: rgba(47,129,247,0.05); }}
  .gs-result-item.gs-active {{ border-color: #58a6ff; background: rgba(88,166,255,0.08); }}
  .gs-result-hash {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: #58a6ff;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }}
  .gs-badge {{
    background: #1f6feb;
    color: white;
    font-size: 0.62rem;
    padding: 1px 5px;
    border-radius: 3px;
    font-family: 'Inter', sans-serif;
    font-weight: 600;
  }}
  .gs-result-msg {{
    font-size: 0.83rem;
    color: #e6edf3;
    margin: 5px 0 3px;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .gs-result-meta {{
    font-size: 0.7rem;
    color: #7d8590;
    margin-bottom: 6px;
  }}
  .gs-result-files {{
    font-size: 0.68rem;
    color: #7d8590;
    margin-bottom: 6px;
    font-family: 'JetBrains Mono', monospace;
  }}
  .gs-parent-row {{
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 4px;
  }}
  .gs-parent-label {{
    font-size: 0.68rem;
    color: #4d5566;
  }}
  .gs-parent-link {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: #58a6ff;
    background: rgba(88,166,255,0.08);
    border: 1px solid rgba(88,166,255,0.2);
    border-radius: 4px;
    padding: 1px 6px;
    cursor: pointer;
    text-decoration: none;
  }}
  .gs-parent-link:hover {{ background: rgba(88,166,255,0.2); }}
  .gs-node-link {{
    font-size: 0.68rem;
    color: #ffa000;
    background: rgba(255,160,0,0.08);
    border: 1px solid rgba(255,160,0,0.2);
    border-radius: 4px;
    padding: 1px 6px;
    cursor: pointer;
    margin-left: auto;
  }}
  .gs-node-link:hover {{ background: rgba(255,160,0,0.2); }}
  .gs-no-results {{
    color: #4d5566;
    font-size: 0.82rem;
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
