# gitsearch/template.py

def get_html_template() -> str:
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitSearch — Reactive Explorer</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #181a1f; --surface: rgba(33, 36, 43, 0.95);
            --border: rgba(255, 255, 255, 0.1); --text: #e4e6eb;
            --text-muted: #7a7e85; --shadow: 0 8px 32px rgba(0,0,0,0.5);
            --radius: 12px;
        }
        .gs-theme-light {
            --bg: #f4f2ee; --surface: rgba(233, 230, 224, 0.95);
            --border: rgba(0,0,0,0.15); --text: #1a1a1a;
            --text-muted: #666666; --shadow: 0 8px 32px rgba(0,0,0,0.15);
        }
        body {
            margin: 0; padding: 0;
            font-family: 'Inter', sans-serif;
            background: var(--bg); color: var(--text);
            overflow: hidden;
            transition: background 0.3s ease, color 0.3s ease;
        }
        #network {
            width: 100vw; height: 100vh;
            position: absolute; top: 0; left: 0; z-index: 1;
        }
        .overlay-ui {
            position: absolute; z-index: 10;
            top: 0; left: 0; width: 100%; height: 100%;
            pointer-events: none;
        }
        .panel {
            pointer-events: auto;
            background: var(--surface);
            border: 1px solid var(--border);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            transition: all 0.2s ease;
        }
        .gs-btn {
            background: transparent; border: 1px solid var(--border);
            color: var(--text); padding: 8px 12px; border-radius: 6px;
            cursor: pointer; font-weight: 500; font-family: inherit;
            transition: all 0.2s ease;
            display: inline-flex; align-items: center; justify-content: center; gap: 6px;
        }
        .gs-btn:hover { background: rgba(128,128,128,0.15); border-color: rgba(128,128,128,0.4); }
        .ce-item {
            padding: 10px; border-radius: 6px; cursor: pointer;
            border: 1px solid transparent; margin-bottom: 4px;
            transition: background 0.1s ease;
        }
        .ce-item:hover { background: rgba(128,128,128,0.1); border-color: var(--border); }
        
        #loading-overlay {
            position: fixed; top:0; left:0; width:100%; height:100%;
            background: var(--bg); z-index: 9999;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            transition: opacity 0.5s ease;
        }
        .spinner {
            width: 40px; height: 40px; border: 3px solid var(--border);
            border-top-color: var(--text); border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div id="loading-overlay">
        <div class="spinner"></div><div style="margin-top:20px; font-weight:500;">Esculpiendo grafo...</div>
    </div>

    <div id="network"></div>
    <div id="ui-root" class="overlay-ui"></div>
    
    <!-- GITSEARCH_PANEL -->

    <script>
        // Data injected by Python template engine
        const rawNodes = __NODES_DATA__;
        const rawEdges = __EDGES_DATA__;
        const commitHistory = __HISTORY_DATA__;
        const mapCommitTag = __COMMIT_MAP__;
        const searchRes = __GLOBAL_SEARCH__;

        // --- THEME ENGINE ---
        const THEMES = {
            dark: { bg: '#181a1f', nodeMain: '#e4e6eb', nodeSide: '#60646b', edge: '#4a4d54' },
            light: { bg: '#f4f2ee', nodeMain: '#21242b', nodeSide: '#b1b6bd', edge: '#a8adb5' }
        };

        // --- UNIFIED STATE MANAGER (Flux-like) ---
        const State = {
            theme: localStorage.getItem('gs_theme') || 'dark',
            mode: 'EXPLORING', // EXPLORING, INSPECTING
            focusedNodeId: null, 
            expandedTagId: null,
            expandedCommitsMap: {}, // Maps a tagID to array of generated expanded commit IDs
            cameraStack: [],
            sidebarOpen: false,
            initialized: false
        };

        let network = null;
        let nodesDS = new vis.DataSet();
        let edgesDS = new vis.DataSet();

        // --- DISPATCHER ---
        function dispatch(action, payload) {
            console.log("INTENT:", action, payload);
            switch(action) {
                case 'TOGGLE_THEME':
                    State.theme = State.theme === 'dark' ? 'light' : 'dark';
                    localStorage.setItem('gs_theme', State.theme);
                    if(State.theme === 'light') document.body.classList.add('gs-theme-light');
                    else document.body.classList.remove('gs-theme-light');
                    break;
                case 'FOCUS_NODE':
                    if (State.focusedNodeId && State.focusedNodeId !== payload) {
                        ActionLib.pushCamera();
                    }
                    State.focusedNodeId = payload;
                    State.sidebarOpen = true;
                    ActionLib.focusCamera([payload]);
                    break;
                case 'EXPAND_TAG':
                    if (State.expandedTagId === payload) {
                        dispatch('COLLAPSE_TAG');
                        return;
                    }
                    if (State.expandedTagId) dispatch('COLLAPSE_TAG');
                    
                    ActionLib.pushCamera();
                    State.expandedTagId = payload;
                    ActionLib.expandCommitsFor(payload);
                    break;
                case 'COLLAPSE_TAG':
                    ActionLib.collapseCurrent();
                    State.expandedTagId = null;
                    if(State.cameraStack.length > 0) ActionLib.popCamera();
                    break;
                case 'CLOSE_SIDEBAR':
                    State.sidebarOpen = false;
                    State.focusedNodeId = null;
                    if(State.cameraStack.length > 0) ActionLib.popCamera();
                    else network.fit({animation: {duration: 600, easingFunction: 'easeInOutQuart'}});
                    break;
                case 'NAVIGATE_BACK':
                    ActionLib.popCamera();
                    // Restore previous focus if any mapped to this camera state
                    State.focusedNodeId = State.cameraStack.length > 0 ? State.cameraStack[State.cameraStack.length-1].focusedNodeId : null;
                    if(!State.focusedNodeId) State.sidebarOpen = false;
                    break;
                case 'ZOOM_FIT':
                    State.cameraStack = [];
                    State.focusedNodeId = null;
                    State.sidebarOpen = false;
                    ActionLib.collapseCurrent();
                    State.expandedTagId = null;
                    network.fit({animation: {duration: 800, easingFunction: 'easeInOutQuart'}});
                    break;
                case 'INIT':
                    State.initialized = true;
                    if(State.theme === 'light') document.body.classList.add('gs-theme-light');
                    setTimeout(() => document.getElementById('loading-overlay').style.opacity = '0', 300);
                    setTimeout(() => document.getElementById('loading-overlay').style.display = 'none', 800);
                    break;
            }
            render();
        }

        // --- ACTION LIBRARY (Side Effects & Maths) ---
        const ActionLib = {
            pushCamera() {
                State.cameraStack.push({
                    pos: network.getViewPosition(),
                    scale: network.getScale(),
                    focusedNodeId: State.focusedNodeId
                });
            },
            popCamera() {
                if (State.cameraStack.length > 0) {
                    const cam = State.cameraStack.pop();
                    network.moveTo({ 
                        position: cam.pos, 
                        scale: cam.scale, 
                        animation: { duration: 600, easingFunction: 'easeInOutQuart' } 
                    });
                }
            },
            focusCamera(boxNodeIds) {
                // Cinematic Enframing by calculating bounding box payload
                network.fit({ 
                    nodes: boxNodeIds, 
                    padding: 80, 
                    animation: { duration: 700, easingFunction: 'easeInOutQuart' } 
                });
            },
            expandCommitsFor(tagId) {
                const tagNode = rawNodes.find(n => n.id === tagId);
                // Fallback to searching all nodes if missing
                if (!tagNode || !tagNode.stats?.commits_list) return;
                
                const commits = tagNode.stats.commits_list;
                if (commits.length === 0) return;

                // Deterministic visual injection algorithm
                const tagPos = network.getPositions([tagId])[tagId];
                let currentY = tagPos.y + 100;
                let newNodes = [];
                let newEdges = [];

                // Simple linear descent layout (Vertical timeline)
                // Eliminates chaos of force-directed expansion overlap
                commits.slice().reverse().forEach((c, idx) => {
                    const cid = "exp_" + c.hash;
                    newNodes.push({
                        id: cid,
                        isExpanded: true,
                        commitHash: c.full_hash || c.hash,
                        label: (c.mensaje_full || c.mensaje).split('\\n')[0].slice(0, 50) + (c.mensaje_full && c.mensaje_full.length>50?'...':''),
                        shape: 'box',
                        margin: { top: 10, bottom: 10, left: 15, right: 15 },
                        borderWidth: 1.5,
                        x: tagPos.x,
                        y: currentY,
                        font: { face: 'Inter', size: 12, multi: 'html' }
                    });
                    
                    if (idx === 0) {
                        newEdges.push({ id: `e_${tagId}_${cid}_v`, from: tagId, to: cid, dashes: [4,6], width: 2, arrows: "from" });
                    } else {
                        const prevId = "exp_" + commits.slice().reverse()[idx-1].hash;
                        newEdges.push({ id: `e_${prevId}_${cid}_v`, from: prevId, to: cid, width: 2, arrows: "to" });
                    }
                    currentY += 75; // strict deterministic spacing
                });
                
                nodesDS.add(newNodes);
                edgesDS.add(newEdges);
                State.expandedCommitsMap[tagId] = newNodes.map(n => n.id);
                
                // Cinematic focus on bounding box of [tag + all generated expanded commits]
                const enframingNodes = [tagId, ...State.expandedCommitsMap[tagId]];
                setTimeout(() => ActionLib.focusCamera(enframingNodes), 50);
            },
            collapseCurrent() {
                if (State.expandedTagId && State.expandedCommitsMap[State.expandedTagId]) {
                    const ids = State.expandedCommitsMap[State.expandedTagId];
                    nodesDS.remove(ids); // Edges auto-removed by vis
                    delete State.expandedCommitsMap[State.expandedTagId];
                }
            }
        };

        // --- RENDER ENGINE (Visual Synchronization) ---
        function render() {
            const themeConfig = THEMES[State.theme];

            // 1. Sync Network semantic depth-of-field
            const allNodes = nodesDS.get();
            const nodeUpdates = [];
            
            // Determine focal cluster
            let activeClusterIds = new Set();
            if (State.focusedNodeId) activeClusterIds.add(State.focusedNodeId);
            if (State.expandedTagId) {
                activeClusterIds.add(State.expandedTagId);
                (State.expandedCommitsMap[State.expandedTagId] || []).forEach(id => activeClusterIds.add(id));
            }

            allNodes.forEach(n => {
                const isFocal = activeClusterIds.size === 0 || activeClusterIds.has(n.id);
                const opacity = isFocal ? 1.0 : 0.15; // Extreme depth of field
                
                let bgColor, bdColor, fontColor;
                
                if (n.isExpanded) {
                    bgColor = State.theme === 'dark' ? '#2a2a2a' : '#ffffff';
                    bdColor = State.theme === 'dark' ? '#555' : '#ccc';
                    fontColor = State.theme === 'dark' ? '#eee' : '#111';
                } else {
                    bgColor = n.is_main ? themeConfig.nodeMain : themeConfig.nodeSide;
                    bdColor = n.is_main ? themeConfig.nodeMain : themeConfig.nodeSide;
                    fontColor = isFocal ? (State.theme === 'dark' ? '#eee' : '#111') : 'transparent';
                }
                
                if (activeClusterIds.has(n.id) && !n.isExpanded) {
                    // Highlight specific active node
                    bgColor = '#8660dd'; bdColor = '#a371f7';
                }

                nodeUpdates.push({
                    id: n.id,
                    color: { background: bgColor, border: bdColor, opacity },
                    font: { color: fontColor }
                });
            });
            nodesDS.update(nodeUpdates);

            const allEdges = edgesDS.get();
            const edgeUpdates = allEdges.map(e => ({
                id: e.id,
                color: { color: themeConfig.edge, opacity: activeClusterIds.size > 0 && !e.id.includes('_v') ? 0.1 : 1.0 }
            }));
            edgesDS.update(edgeUpdates);

            // 2. Render HTML Overlays (React-like)
            renderHTMLOverlay();
        }

        function renderHTMLOverlay() {
            const root = document.getElementById('ui-root');
            
            // Topbar
            let html = `
                <div class="panel" style="position: absolute; top:0; left:0; right:0; height: 52px; border-radius: 0; padding: 0 24px; display: flex; align-items: center; justify-content: space-between; border-top:none; border-left:none; border-right:none;">
                    <strong style="letter-spacing:-0.03em; font-size:16px;">GitTrace ✨ <span style="font-weight:400;color:var(--text-muted)">Reactive Workspace</span></strong>
                    <div style="display:flex; gap:12px;">
                        <button class="gs-btn" onclick="dispatch('ZOOM_FIT')" title="Reset View">⛶ Fit</button>
                        <button class="gs-btn" onclick="dispatch('TOGGLE_THEME')" title="Cambiar Tema">🌓 Tema</button>
                    </div>
                </div>
            `;

            // Sidebar
            if (State.sidebarOpen && State.focusedNodeId) {
                let nodeMeta = rawNodes.find(n => n.id === State.focusedNodeId);
                let isCommit = false;
                
                if (!nodeMeta) { // is expanded commit
                    const expandId = State.focusedNodeId.replace('exp_', '');
                    nodeMeta = commitHistory.find(c => c.hash === expandId || c.full_hash === expandId);
                    isCommit = !!nodeMeta;
                }
                
                if (nodeMeta) {
                    html += `
                        <div class="panel" style="position:absolute; top: 72px; right: 20px; width: min(380px, calc(100vw - 40px)); bottom: 20px; display: flex; flex-direction: column; border-radius: var(--radius); box-shadow: var(--shadow);">
                            
                            <!-- Header -->
                            <div style="padding: 16px 20px; border-bottom: 1px solid var(--border); display:flex; justify-content:space-between; align-items:flex-start;">
                                <div>
                                    <h3 style="margin:0; font-size:13px; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-muted);">${isCommit ? 'Inspección de Commit' : 'Análisis de Tags'}</h3>
                                    ${!isCommit ? `<div style="font-size:18px; font-weight:700; margin-top:4px;">${nodeMeta.label}</div>` : ''}
                                </div>
                                <div style="display:flex; gap:4px; margin-top:-4px; margin-right:-8px;">
                                    ${State.cameraStack.length > 0 ? `<button class="gs-btn" onclick="dispatch('NAVIGATE_BACK')" style="padding:6px; font-size:16px; border:none;" title="Volver">⮌</button>` : ''}
                                    <button class="gs-btn" onclick="dispatch('CLOSE_SIDEBAR')" style="padding:6px; font-size:18px; border:none;" title="Cerrar">✕</button>
                                </div>
                            </div>
                            
                            <!-- Body -->
                            <div style="padding: 20px; flex:1; overflow-y:auto; font-size: 14px; line-height: 1.6;">
                                ${isCommit ? `
                                    <div style="font-family:'JetBrains Mono', monospace; color:var(--text-muted); font-size:12px; margin-bottom:12px; background:var(--bg); padding:4px 8px; border-radius:4px; display:inline-block;">${nodeMeta.full_hash || nodeMeta.hash}</div>
                                    <div style="font-weight:600; font-size:16px; margin-bottom:16px; color:var(--text);">${escapeHtml(nodeMeta.mensaje_full || nodeMeta.mensaje).replace(/\\n/g, '<br>')}</div>
                                    <div style="display:flex; gap:16px; color:var(--text-muted); margin-bottom:24px; font-size:13px;">
                                        <div>👤 <span style="color:var(--text);font-weight:500;">${escapeHtml(nodeMeta.autor)}</span></div>
                                        <div>📅 <span style="color:var(--text);font-weight:500;">${nodeMeta.fecha.split(' ')[0]}</span></div>
                                    </div>
                                    ${nodeMeta.parents ? `
                                        <div style="margin-top:20px; font-size:12px; color:var(--text-muted); text-transform:uppercase; font-weight:600;">Padres</div>
                                        <div style="display:flex; gap:8px; margin-top:8px;">
                                            ${nodeMeta.parents.map(p => `<div style="font-family:'JetBrains Mono'; background:rgba(128,128,128,0.1); padding:4px 8px; border-radius:4px; font-size:11px;">${p}</div>`).join('')}
                                        </div>
                                    ` : ''}
                                ` : `
                                    <div style="display:flex; gap:16px; color:var(--text-muted); margin-bottom:24px; font-size:13px;">
                                        <div>👤 <span style="color:var(--text);font-weight:500;">${escapeHtml(nodeMeta.author)}</span></div>
                                        <div>📅 <span style="color:var(--text);font-weight:500;">${nodeMeta.date}</span></div>
                                    </div>
                                    <div style="background:rgba(128,128,128,0.08); padding:16px; border-radius:8px; border:1px solid rgba(128,128,128,0.15); margin-bottom:24px;">
                                        <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                                            <span style="color:var(--text-muted);">Nuevos Commits</span>
                                            <strong style="color:var(--text); font-size:16px;">${nodeMeta.stats?.num_commits || 0}</strong>
                                        </div>
                                        <div style="display:flex; justify-content:space-between;">
                                            <span style="color:var(--text-muted);">Archivos Alterados</span>
                                            <strong style="color:var(--text); font-size:16px;">${nodeMeta.stats?.num_archivos || 0}</strong>
                                        </div>
                                    </div>
                                    <button class="gs-btn" onclick="dispatch('EXPAND_TAG', '${nodeMeta.id}')" style="width:100%; padding: 12px; font-size:14px; background:var(--text); color:var(--bg); border:none; ${State.expandedTagId === nodeMeta.id ? 'background:#8660dd; color:#fff;' : ''}">
                                        ${State.expandedTagId === nodeMeta.id ? '⮟ Colapsar Exploración' : '⮞ Explorar Commits Contextuales'}
                                    </button>
                                `}
                            </div>
                        </div>
                    `;
                }
            }
            root.innerHTML = html;
        }

        // Util
        function escapeHtml(s) {
            return (s||'').toString().replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        // --- BOOTSTRAP ---
        function initApp() {
            // Load Initial Topology Layout
            nodesDS.add(rawNodes.map(n => ({
                id: n.id,
                label: n.label,
                is_main: n.is_main,
                shape: 'dot',
                size: n.size || 15,
                font: { face: 'Inter', size: 12 }
            })));

            edgesDS.add(rawEdges.map((e, idx) => ({
                ...e,
                smooth: { type: 'continuous', forceDirection: 'vertical', roundness: 0.5 }
            })));

            const container = document.getElementById('network');
            network = new vis.Network(container, { nodes: nodesDS, edges: edgesDS }, {
                layout: { 
                    hierarchical: { enabled: true, direction: 'UD', sortMethod: 'directed', levelSeparation: 150, nodeSpacing: 180, shakeStability: 'position' }
                },
                physics: { enabled: false }, // Zero gravity, deterministic only
                interaction: { dragNodes: false, hover: true, tooltipDelay: 200 }
            });

            // Map Intent Event Bindings
            network.on('click', (params) => {
                if (params.nodes.length > 0) {
                    dispatch('FOCUS_NODE', params.nodes[0]);
                } else {
                    if (State.sidebarOpen || State.expandedTagId) dispatch('CLOSE_SIDEBAR');
                }
            });

            network.on('doubleClick', (params) => {
                if (params.nodes.length > 0) {
                    const nid = params.nodes[0];
                    if (!nid.startsWith('exp_')) {
                        dispatch('EXPAND_TAG', nid);
                    }
                }
            });

            // Start lifecycle
            network.once('stabilizationIterationsDone', () => {
                dispatch('INIT');
                network.fit({ animation: { duration: 1500, easingFunction: 'easeOutQuint' }});
            });
            // Force init if very fast or empty
            setTimeout(() => { if(!State.initialized) dispatch('INIT'); }, 1500);
        }

        window.addEventListener('DOMContentLoaded', initApp);
    </script>
</body>
</html>
"""
