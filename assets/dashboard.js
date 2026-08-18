let currentTab = 'home';
let rendaFixaSort = { key: 'rank', ascending: true };
const tableSortState = {};

        function getScoreRangeClass(score) {
            if (score >= 8.0) return 'score-premium';
            if (score >= 6.0) return 'score-good';
            if (score >= 4.0) return 'score-alert';
            return 'score-risk';
        }

        function formatScore(score) {
            return (score || 0).toFixed(2);
        }

        function formatTdYield(td, includePercent) {
            const value = Number(td && td.buy_yield);
            if (!Number.isFinite(value)) return '—';
            const suffix = includePercent === false ? '' : '%';
            if (td.yield_kind === 'selic_spread') {
                return 'Selic ' + (value >= 0 ? '+' : '') + (value * 100).toFixed(4) + suffix;
            }
            return (value * 100).toFixed(2) + suffix;
        }

        // ── Sparkline SVG Generator (ultraleve para tabelas) ──
        function generateSparklineSvg(historyJson) {
            if (!historyJson) return '<span style="color:var(--text-muted);font-size:0.75rem;">—</span>';
            let history = [];
            try {
                history = typeof historyJson === 'string' ? JSON.parse(historyJson) : historyJson;
            } catch (e) {
                return '<span style="color:var(--text-muted);font-size:0.75rem;">—</span>';
            }
            if (!Array.isArray(history) || history.length < 2) return '<span style="color:var(--text-muted);font-size:0.75rem;">—</span>';

            const prices = history.map(h => typeof h.price === 'number' ? h.price : (parseFloat(h.price) || 0)).filter(p => p > 0);
            if (prices.length < 2) return '<span style="color:var(--text-muted);font-size:0.75rem;">—</span>';

            const sampled = prices.length > 14 ? prices.slice(-14) : prices;
            const min = Math.min(...sampled);
            const max = Math.max(...sampled);
            const range = max - min || 1;

            const w = 52, h = 16, padY = 2;
            const pts = sampled.map((p, idx) => {
                const x = (idx / (sampled.length - 1)) * w;
                const y = h - padY - ((p - min) / range) * (h - padY * 2);
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            });

            const isPositive = sampled[sampled.length - 1] >= sampled[0];
            const trendClass = isPositive ? 'up' : 'down';
            const polylinePts = pts.join(' ');
            const lastPt = pts[pts.length - 1].split(',');
            const areaPts = `0,${h} ` + polylinePts + ` ${w},${h}`;

            return `<svg class="sparkline-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" title="${isPositive ? 'Tendência 12m: Alta' : 'Tendência 12m: Queda'}">
                <polygon class="sparkline-area ${trendClass}" points="${areaPts}" />
                <polyline class="sparkline-line ${trendClass}" points="${polylinePts}" />
                <circle class="sparkline-dot ${trendClass}" cx="${lastPt[0]}" cy="${lastPt[1]}" />
            </svg>`;
        }

        // ── v2.5 Continuous scoring helpers (replicate Python analyzer logic) ──

        function clamp(val, min, max) {
            return Math.min(Math.max(val, min), max);
        }

        // Stock criteria (each 0-2)
        function scoreDYStock(dy) {
            if (dy == null || dy < 0.06) return 0.0;
            var bonus = (dy - 0.06) * 11.111;
            return clamp(1.0 + bonus, 0.0, 2.0);
        }
        function scorePEStock(pe) {
            if (pe == null || pe <= 0 || pe > 15) return 0.0;
            var proportion = (15 - pe) / 15;
            return clamp(1.0 + proportion * 1.0, 0.0, 2.0);
        }
        function scorePBStock(pb) {
            if (pb == null || pb < 0.50 || pb > 1.50) return 0.0;
            return clamp(2.0 * (1.50 - pb), 0.0, 2.0);
        }
        function scoreROEStock(roe) {
            if (roe == null || roe < 0.10) return 0.0;
            var bonus = (roe - 0.10) * 5.0;
            return clamp(1.0 + bonus, 0.0, 2.0);
        }
        function scoreGrahamStock(price, graham) {
            if (price == null || graham == null || graham <= 0) return 0.0;
            if (price >= graham) return 0.0;
            var margin = (graham - price) / price;
            return clamp(1.0 + margin, 0.0, 2.0);
        }

        // FII/FIAGRO criteria (each 0-2) — legacy (preserved for compatibility)
        function scorePBFiiIdeal(pb) {
            if (pb == null || pb < 0.70 || pb > 1.05) return 0.0;
            var proportion = (1.05 - pb) / (1.05 - 0.70);
            return clamp(proportion * 2.0, 0.0, 2.0);
        }
        function scorePBFiiLimite(pb) {
            if (pb == null) return 0.0;
            if (pb >= 0.60 && pb < 0.70) {
                var proportion = (pb - 0.60) / (0.70 - 0.60);
                return clamp(proportion * 2.0, 0.0, 2.0);
            }
            if (pb > 1.05 && pb <= 1.15) {
                var proportion = (1.15 - pb) / (1.15 - 1.05);
                return clamp(proportion * 2.0, 0.0, 2.0);
            }
            return 0.0;
        }
        function scoreDYFii(dy, isFiagro) {
            var minDY = isFiagro ? 0.10 : 0.08;
            var capDY = isFiagro ? 0.165 : 0.145;
            var factor = 1.0 / (capDY - minDY);
            if (dy == null || dy < minDY) return 0.0;
            var bonus = (dy - minDY) * factor;
            return clamp(1.0 + bonus, 0.0, 2.0);
        }
        function scoreYieldCap(dy, isFiagro) {
            var capDY = isFiagro ? 0.165 : 0.145;
            if (dy == null || dy > capDY) return 0.0;
            var proportion = 1.0 - (dy / capDY);
            return clamp(proportion * 2.0, 0.0, 2.0);
        }
        function scoreConsistency(consistency) {
            if (consistency == null) return 1.0;
            if (consistency >= 0.95) return 2.0;
            if (consistency <= 0) return 0.0;
            return clamp(consistency / 0.95 * 2.0, 0.0, 2.0);
        }

        // FII/FIAGRO v2.5.1 — 3 criteria (recalibrated weights)
        function scorePBFii(pb) {
            // Unified P/VP: MAX(ideal, limite) × 1.75 → 0-3.5
            return clamp(Math.max(scorePBFiiIdeal(pb), scorePBFiiLimite(pb)) * 1.75, 0.0, 3.5);
        }
        function scoreDYFiiV2(dy, isFiagro) {
            // DY (0-4.0 pts) with hard ceiling (Cap)
            var minDY = isFiagro ? 0.10 : 0.08;
            var capDY = isFiagro ? 0.165 : 0.145;
            if (dy == null || dy < minDY) return 0.0;
            if (dy >= capDY) return 4.0;
            var proportion = (dy - minDY) / (capDY - minDY);
            return clamp(proportion * 4.0, 0.0, 4.0);
        }
        function scoreConsistencyV2(consistency) {
            // Consistência: neutro = 1.5, escala 0-2.5
            if (consistency == null) return 1.5;
            if (consistency >= 0.95) return 2.5;
            if (consistency <= 0) return 0.0;
            return clamp(consistency / 0.95 * 2.5, 0.0, 2.5);
        }

        function switchTab(tab) {
            currentTab = tab;
            // Atualizar label do PDF
            const pdfLabel = document.getElementById('pdf-label');
            if (pdfLabel) {
                const names = {
                    home: 'Home',
                    global: 'Top Brasil',
                    stocks: 'Ações',
                    fiis: 'FIIs',
                    fiagros: 'FIAGROs',
                    compare: 'Comparador',
                    calculator: 'Calculadora de Investimentos',
                    macro: 'Previsor Macro',
                    sectors: 'Setores',
                    rendafixa: 'Tesouro Direto',
                    glossary: 'Glossário & Educação'
                };
                pdfLabel.textContent = names[tab] || tab;
            }
            const allBtns = document.querySelectorAll('.tab-btn');
            const panelHome = document.getElementById('panel-home');
            const panelGlobal = document.getElementById('panel-global');
            const panelStocks = document.getElementById('panel-stocks');
            const panelFiis = document.getElementById('panel-fiis');
            const panelFiagros = document.getElementById('panel-fiagros');
            const panelCompare = document.getElementById('panel-compare');
            const panelCalculator = document.getElementById('panel-calculator');
            const panelMacro = document.getElementById('panel-macro');
            const panelSectors = document.getElementById('panel-sectors');
            const panelRendaFixa = document.getElementById('panel-rendafixa');
            const panelGlossary = document.getElementById('panel-glossary');
            const filtersRow = document.querySelector('.filters-row');

            allBtns.forEach(b => {
                const onclick = b.getAttribute('onclick') || '';
                b.classList.toggle('active', onclick.includes(`'${tab}'`));
            });

            [panelHome, panelGlobal, panelStocks, panelFiis, panelFiagros, panelCompare, panelCalculator, panelMacro, panelSectors, panelRendaFixa, panelGlossary].forEach(p => {
                if (p) p.classList.add('hidden');
            });
            if (filtersRow) filtersRow.classList.toggle('hidden', !['stocks', 'fiis', 'fiagros'].includes(tab));

            if (tab === 'home') {
                if (panelHome) panelHome.classList.remove('hidden');
            } else if (tab === 'global') {
                if (panelGlobal) panelGlobal.classList.remove('hidden');
                if (window.dashboardData) {
                    renderGlobalPanel(window.dashboardData);
                }
            } else if (tab === 'stocks') {
                if (panelStocks) panelStocks.classList.remove('hidden');
            } else if (tab === 'fiis') {
                if (panelFiis) panelFiis.classList.remove('hidden');
            } else if (tab === 'fiagros') {
                if (panelFiagros) panelFiagros.classList.remove('hidden');
            } else if (tab === 'compare') {
                if (panelCompare) panelCompare.classList.remove('hidden');
                if (window.dashboardData) renderComparePanel();
            } else if (tab === 'calculator') {
                if (panelCalculator) panelCalculator.classList.remove('hidden');
                if (window.dashboardData) renderCalculatorPanel();
            } else if (tab === 'macro') {
                if (panelMacro) panelMacro.classList.remove('hidden');
                runMacroForecastSimulation();
            } else if (tab === 'sectors') {
                if (panelSectors) panelSectors.classList.remove('hidden');
            } else if (tab === 'rendafixa') {
                if (panelRendaFixa) panelRendaFixa.classList.remove('hidden');
                // O Chart.js precisa medir um painel visível. Esperar o próximo frame
                // evita canvas com largura/altura incorretas após a troca de aba.
                if (window.dashboardData) {
                    requestAnimationFrame(function() {
                        renderRendaFixaPanel(window.dashboardData);
                    });
                }
            } else if (tab === 'glossary') {
                if (panelGlossary) panelGlossary.classList.remove('hidden');
            }

            const indexFilter = document.getElementById('index-filter');
            const sectorFilter = document.getElementById('sector-filter');
            const scoreFilter = document.getElementById('score-range-filter');
            const discountFilter = document.getElementById('discount-filter');

            if (tab === 'stocks') {
                if (indexFilter) indexFilter.classList.remove('hidden');
                if (sectorFilter) sectorFilter.classList.remove('hidden');
                if (scoreFilter) scoreFilter.classList.remove('hidden');
                if (discountFilter) discountFilter.classList.remove('hidden');
            } else if (tab === 'fiis' || tab === 'fiagros') {
                if (indexFilter) indexFilter.classList.add('hidden');
                if (sectorFilter) sectorFilter.classList.add('hidden');
                if (scoreFilter) scoreFilter.classList.remove('hidden');
                if (discountFilter) discountFilter.classList.remove('hidden');
            } else { // home, compare, calculator, sectors, rendafixa
                if (indexFilter) indexFilter.classList.add('hidden');
                if (sectorFilter) sectorFilter.classList.add('hidden');
                if (scoreFilter) scoreFilter.classList.add('hidden');
                if (discountFilter) discountFilter.classList.add('hidden');
            }

            filterTable();
            if (typeof syncUrlFromState === 'function') syncUrlFromState();
            if (typeof initTableColumnResizers === 'function') {
                setTimeout(initTableColumnResizers, 60);
            }
        }

        function filterTable() {
            if (currentTab === 'home' || currentTab === 'rendafixa') {
                return;
            }
            if (currentTab === 'sectors') {
                const tbody = document.getElementById('sectors-tbody');
                let count = 0;
                if (tbody) {
                    const rows = tbody.getElementsByTagName('tr');
                    for (let row of rows) {
                        row.classList.remove('hidden');
                        count++;
                    }
                }
                const sectorsCountEl = document.getElementById('sectors-count');
                if (sectorsCountEl) {
                    sectorsCountEl.textContent = `${count} ${count === 1 ? 'setor' : 'setores'}`;
                }
                return;
            }

            const query = document.getElementById('search-bar').value.toLowerCase();
            let tbodyId = 'stocks-tbody';
            if (currentTab === 'fiis') tbodyId = 'fiis-tbody';
            if (currentTab === 'fiagros') tbodyId = 'fiagros-tbody';
            if (currentTab === 'sectors') tbodyId = 'sectors-tbody';

            const rows = document.getElementById(tbodyId).getElementsByTagName('tr');

            const indexFilterVal = document.getElementById('index-filter') ? document.getElementById('index-filter').value : 'all';
            const sectorFilterVal = document.getElementById('sector-filter') ? document.getElementById('sector-filter').value : 'all';
            const discountFilterVal = document.getElementById('discount-filter') ? document.getElementById('discount-filter').value : 'all';

            let visibleCount = 0;
            for (let row of rows) {
                const ticker = (row.getAttribute('data-ticker') || row.cells[0].textContent).toLowerCase();
                const name = (row.getAttribute('data-name') || (row.cells[1] ? row.cells[1].textContent : '')).toLowerCase();

                // 1. Search filter
                const matchesSearch = ticker.includes(query) || name.includes(query);

                // 2. Index filter (only for stocks)
                let matchesIndex = true;
                if (currentTab === 'stocks' && indexFilterVal !== 'all') {
                    const rowIndices = row.getAttribute('data-indices') || '';
                    const indicesList = rowIndices.split(',').map(idx => idx.trim());
                    matchesIndex = indicesList.includes(indexFilterVal);
                }

                // 3. Sector filter (only for stocks)
                let matchesSector = true;
                if (currentTab === 'stocks' && sectorFilterVal !== 'all') {
                    const rowSector = row.getAttribute('data-sector') || '';
                    matchesSector = (rowSector === sectorFilterVal);
                }

                // 4. Quality/Score range filter (for stocks, fiis, fiagros)
                let matchesScore = true;
                const scoreRangeVal = document.getElementById('score-range-filter') ? document.getElementById('score-range-filter').value : 'all';
                if (scoreRangeVal !== 'all') {
                    const rowScore = parseFloat(row.getAttribute('data-score')) || 0;
                    if (scoreRangeVal === 'premium') matchesScore = (rowScore >= 8.0);
                    else if (scoreRangeVal === 'good') matchesScore = (rowScore >= 6.0 && rowScore < 8.0);
                    else if (scoreRangeVal === 'alert') matchesScore = (rowScore >= 4.0 && rowScore < 6.0);
                    else if (scoreRangeVal === 'risk') matchesScore = (rowScore < 4.0);
                }

                // 5. Discount/Price filter
                let matchesDiscount = true;
                if (discountFilterVal !== 'all') {
                    if (currentTab === 'stocks') {
                        const price = parseFloat(row.getAttribute('data-price')) || 0;
                        const bazin = parseFloat(row.getAttribute('data-bazin')) || 0;
                        const graham = parseFloat(row.getAttribute('data-graham')) || 0;

                        // Stock is discounted if Price < Graham OR Price < Bazin
                        const discounted = (graham > 0 && price < graham) || (bazin > 0 && price < bazin);
                        matchesDiscount = discounted;
                    } else if (currentTab === 'fiis' || currentTab === 'fiagros') {
                        const pbRaw = row.getAttribute('data-pb');
                        const pb = (pbRaw !== null && pbRaw !== 'null' && pbRaw !== '') ? parseFloat(pbRaw) : null;
                        // FII/FIAGRO is discounted if P/VP <= 1.00
                        matchesDiscount = (pb !== null && pb > 0 && pb <= 1.00);
                    }
                }

                if (matchesSearch && matchesIndex && matchesSector && matchesScore && matchesDiscount) {
                    row.classList.remove('hidden');
                    visibleCount++;
                } else {
                    row.classList.add('hidden');
                }
            }

            // Update counters
            const countId = `${currentTab}-count`;
            const countEl = document.getElementById(countId);
            if (countEl) {
                countEl.textContent = `${visibleCount} ${visibleCount === 1 ? 'ativo' : 'ativos'}`;
            }
        }

        function sortTable(type, colIdx) {
            let tbodyId = 'stocks-tbody';
            if (type === 'fiis') tbodyId = 'fiis-tbody';
            if (type === 'fiagros') tbodyId = 'fiagros-tbody';
            if (type === 'sectors') tbodyId = 'sectors-tbody';

            const tbody = document.getElementById(tbodyId);
            if (!tbody) return;
            const rows = Array.from(tbody.getElementsByTagName('tr'));

            let isNumeric = true;
            if (type === 'stocks' && (colIdx === 0 || colIdx === 1 || colIdx === 2 || colIdx === 4)) isNumeric = false;
            else if ((type === 'fiis' || type === 'fiagros') && (colIdx === 0 || colIdx === 1 || colIdx === 3)) isNumeric = false;
            else if (type === 'sectors' && colIdx === 0) isNumeric = false;

            const previous = tableSortState[type] || {};
            const ascending = previous.column === colIdx ? !previous.ascending : true;
            tableSortState[type] = { column: colIdx, ascending: ascending };

            rows.sort((a, b) => {
                let valA = a.cells[colIdx].textContent.trim();
                let valB = b.cells[colIdx].textContent.trim();

                if (isNumeric) {
                    // Clean money/percentage signs
                    valA = parseFloat(valA.replace(/[R$\s%]/g, '').replace(',', '.')) || 0;
                    valB = parseFloat(valB.replace(/[R$\s%]/g, '').replace(',', '.')) || 0;
                    return ascending ? valA - valB : valB - valA;
                } else {
                    return ascending ? valA.localeCompare(valB, 'pt-BR') : valB.localeCompare(valA, 'pt-BR');
                }
            });

            // Re-append sorted rows
            rows.forEach(row => tbody.appendChild(row));
            const headers = tbody.closest('table').querySelectorAll('thead th');
            headers.forEach((header, index) => {
                header.setAttribute('aria-sort', index === colIdx ? (ascending ? 'ascending' : 'descending') : 'none');
            });
        }

        function sortRendaFixaTable(key) {
            if (!['rank', 'title', 'group', 'yield', 'percentile', 'maturity', 'score', 'badge'].includes(key)) return;
            rendaFixaSort.ascending = rendaFixaSort.key === key ? !rendaFixaSort.ascending : true;
            rendaFixaSort.key = key;
            if (window.dashboardData) renderRendaFixaPanel(window.dashboardData);
        }

        function initializeSortableHeaders() {
            document.querySelectorAll('th[onclick*="sortTable"], th[data-td-sort-key]').forEach(function(header) {
                header.classList.add('sortable-header');
                header.tabIndex = 0;
                header.setAttribute('role', 'button');
                if (!header.hasAttribute('aria-sort')) header.setAttribute('aria-sort', 'none');
                header.addEventListener('keydown', function(event) {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        header.click();
                    }
                });
            });
        }

        function openSectorDetailModal(sectorName) {
            const nameEl = document.getElementById('sector-modal-name');
            const statsEl = document.getElementById('sector-modal-stats');
            const tbody = document.getElementById('sector-modal-tbody');
            if (nameEl) nameEl.textContent = sectorName;
            if (tbody) tbody.innerHTML = '';

            let foundStocks = [];
            const data = window.dashboardData || {};

            if (Array.isArray(data.stocks) && data.stocks.length > 0) {
                foundStocks = data.stocks.filter(s => s.sector === sectorName).map(s => ({
                    ticker: s.ticker,
                    name: s.name || s.ticker,
                    price: Number(s.price) || 0,
                    pe: s.pe_ratio != null ? Number(s.pe_ratio) : null,
                    pb: s.pb_ratio != null ? Number(s.pb_ratio) : null,
                    dy: Number(s.dividend_yield) || 0,
                    score: Number(s.score) || 0,
                    indices: s.indices || []
                }));
            } else {
                const stockRows = document.querySelectorAll('#stocks-tbody tr');
                stockRows.forEach(row => {
                    const rowSector = row.getAttribute('data-sector');
                    if (rowSector === sectorName) {
                        const ticker = row.getAttribute('data-ticker');
                        const name = row.getAttribute('data-name');
                        const price = parseFloat(row.getAttribute('data-price')) || 0;
                        const peRaw = row.getAttribute('data-pe');
                        const pe = (peRaw !== null && peRaw !== 'null' && peRaw !== '') ? parseFloat(peRaw) : null;
                        const pbRaw = row.getAttribute('data-pb');
                        const pb = (pbRaw !== null && pbRaw !== 'null' && pbRaw !== '') ? parseFloat(pbRaw) : null;
                        const dy = parseFloat(row.getAttribute('data-dy')) || 0;
                        const score = parseFloat(row.getAttribute('data-score')) || 0;

                        foundStocks.push({ ticker, name, price, pe, pb, dy, score, indices: [] });
                    }
                });
            }

            // Sort by Score desc, then by Dividend Yield desc
            foundStocks.sort((a, b) => (b.score - a.score) || (b.dy - a.dy));

            if (statsEl) {
                const count = foundStocks.length;
                const avgScore = count > 0 ? (foundStocks.reduce((acc, s) => acc + s.score, 0) / count) : 0;
                const avgDy = count > 0 ? (foundStocks.reduce((acc, s) => acc + s.dy, 0) / count * 100) : 0;
                const profStocks = foundStocks.filter(s => s.pe !== null && s.pe > 0);
                const avgPeStr = profStocks.length > 0 ? (profStocks.reduce((acc, s) => acc + s.pe, 0) / profStocks.length).toFixed(2) + 'x' : 'N/A';

                statsEl.innerHTML = `
                    <span style="background:var(--surface); padding:0.25rem 0.6rem; border-radius:4px; border:1px solid var(--card-border);"><strong>${count}</strong> empresas</span>
                    <span style="background:var(--surface); padding:0.25rem 0.6rem; border-radius:4px; border:1px solid var(--card-border);">Score Médio: <strong>${avgScore.toFixed(2)}</strong></span>
                    <span style="background:var(--surface); padding:0.25rem 0.6rem; border-radius:4px; border:1px solid var(--card-border); color:var(--positive);">DY Médio: <strong>${avgDy.toFixed(2)}%</strong></span>
                    <span style="background:var(--surface); padding:0.25rem 0.6rem; border-radius:4px; border:1px solid var(--card-border);">P/L Médio: <strong>${avgPeStr}</strong></span>
                `;
            }

            if (foundStocks.length === 0) {
                if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-secondary); padding: 1.5rem;">Nenhuma empresa cadastrada neste setor.</td></tr>';
            } else if (tbody) {
                tbody.innerHTML = foundStocks.map(stock => {
                    const peFormatted = stock.pe !== null ? stock.pe.toFixed(2) : 'N/A';
                    const pbFormatted = stock.pb !== null ? stock.pb.toFixed(2) : 'N/A';
                    const dyFormatted = (stock.dy * 100).toFixed(2) + '%';
                    const peClass = (stock.pe !== null && stock.pe > 0 && stock.pe <= 15) ? 'positive' : 'warning';
                    const pbClass = (stock.pb !== null && stock.pb > 0 && stock.pb <= 1.5) ? 'positive' : 'warning';
                    const dyClass = stock.dy >= 0.06 ? 'positive' : 'negative';

                    return `
                    <tr onclick="closeSectorDetailModal(); openDetailModal('${stock.ticker}', 'stock');" style="cursor: pointer;">
                        <td class="ticker-cell" style="font-weight:700;">${stock.ticker}</td>
                        <td class="name-cell" title="${(stock.name || '').replace(/"/g, '&quot;')}" style="font-size:0.78rem; max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; cursor:help;">${stock.name}</td>
                        <td style="font-weight:600;">R$ ${stock.price.toFixed(2)}</td>
                        <td class="${peClass}">${peFormatted}</td>
                        <td class="${pbClass}">${pbFormatted}</td>
                        <td class="${dyClass}" style="font-weight:600;">${dyFormatted}</td>
                        <td style="text-align:center;">
                            <span class="score-pill ${getScoreRangeClass(stock.score)}">${formatScore(stock.score)}</span>
                        </td>
                    </tr>`;
                }).join('');
            }

            const modal = document.getElementById('sector-detail-modal');
            if (modal) modal.classList.remove('hidden');
        }

        function closeSectorDetailModal() {
            const modal = document.getElementById('sector-detail-modal');
            if (modal) modal.classList.add('hidden');
        }

        function closeSectorModalOnOutsideClick(event) {
            const modal = document.getElementById('sector-detail-modal');
            if (modal && event.target === modal) {
                closeSectorDetailModal();
            }
        }

        function switchSectorIndexView(view) {
            const btnSectors = document.getElementById('btn-view-sectors');
            const btnIndices = document.getElementById('btn-view-indices');
            const containerSectors = document.getElementById('view-sectors-container');
            const containerIndices = document.getElementById('view-indices-container');

            if (btnSectors) btnSectors.classList.toggle('active', view === 'sectors');
            if (btnIndices) btnIndices.classList.toggle('active', view === 'indices');
            if (containerSectors) containerSectors.classList.toggle('hidden', view !== 'sectors');
            if (containerIndices) containerIndices.classList.toggle('hidden', view !== 'indices');
        }

        function renderIndicesSummaryTable(data) {
            const tbody = document.getElementById('indices-tbody');
            const countEl = document.getElementById('indices-count');
            if (!tbody || !data) return;

            const stocks = Array.isArray(data.stocks) ? data.stocks : [];
            const fiis = Array.isArray(data.fiis) ? data.fiis : [];
            const fiagros = Array.isArray(data.fiagros) ? data.fiagros : [];

            const indexDefs = [
                { code: 'IBOV', label: 'IBOV · Ibovespa', desc: 'Ações monitoradas do principal índice de liquidez e peso da B3', type: 'stock' },
                { code: 'IDIV', label: 'IDIV · Índice de Dividendos', desc: 'Ações com melhor histórico e consistência de dividendos', type: 'stock' },
                { code: 'SMLL', label: 'SMLL · Small Caps (SMAL11)', desc: 'Empresas de menor e média capitalização com alto potencial', type: 'stock' },
                { code: 'IFIX', label: 'IFIX · Fundos Imobiliários', desc: 'Carteira dos principais FIIs listados e acompanhados no radar', type: 'fii' },
                { code: 'IFNC', label: 'IFNC · Índice Financeiro', desc: 'Bancos, seguradoras e empresas de intermediação financeira', type: 'stock' },
                { code: 'IEE', label: 'IEE · Energia Elétrica', desc: 'Geradoras, transmissoras e distribuidoras de energia elétrica', type: 'stock' },
                { code: 'IAGRO', label: 'IAGRO · Agronegócio & FIAGROs', desc: 'Cadeia agroindustrial e fundos de investimento do agronegócio', type: 'fiagro' }
            ];

            const summaries = indexDefs.map(def => {
                let items = [];
                if (def.code === 'IFIX') {
                    items = fiis;
                } else if (def.code === 'IAGRO') {
                    items = [
                        ...fiagros,
                        ...stocks.filter(s => (s.sector || '').toLowerCase().includes('agro') || (s.sector || '').toLowerCase().includes('alimentos'))
                    ];
                } else {
                    items = stocks.filter(s => Array.isArray(s.indices) && s.indices.includes(def.code));
                }

                const count = items.length;
                const avgScore = count > 0 ? (items.reduce((acc, i) => acc + (Number(i.score) || 0), 0) / count) : 0;
                const avgDy = count > 0 ? (items.reduce((acc, i) => acc + (Number(i.dividend_yield) || 0), 0) / count * 100) : 0;
                
                let avgMultiple = 'N/A';
                if (def.type === 'fii' || def.type === 'fiagro') {
                    const validPb = items.filter(i => i.pb_ratio != null && i.pb_ratio > 0);
                    avgMultiple = validPb.length > 0 ? 'P/VP ' + (validPb.reduce((acc, i) => acc + Number(i.pb_ratio), 0) / validPb.length).toFixed(2) : 'N/A';
                } else {
                    const validPe = items.filter(i => i.pe_ratio != null && i.pe_ratio > 0);
                    avgMultiple = validPe.length > 0 ? 'P/L ' + (validPe.reduce((acc, i) => acc + Number(i.pe_ratio), 0) / validPe.length).toFixed(1) + 'x' : 'N/A';
                }

                return {
                    ...def,
                    count,
                    avgScore,
                    avgDy,
                    avgMultiple
                };
            });

            if (countEl) countEl.textContent = `${summaries.length} índices`;

            tbody.innerHTML = summaries.map(idx => {
                return `
                <tr onclick="openIndexDetailModal('${idx.code}')" style="cursor: pointer;">
                    <td class="name-cell" style="font-weight: 600;" title="${idx.desc}">
                        <div style="font-weight: 700; color: var(--text-primary);">${idx.label}</div>
                        <div style="font-size: 0.72rem; color: var(--text-muted);">${idx.desc}</div>
                    </td>
                    <td style="text-align: center; font-weight: 700;">${idx.count}</td>
                    <td style="text-align: center;">
                        <span class="score-pill ${getScoreRangeClass(idx.avgScore)}">${formatScore(idx.avgScore)}</span>
                    </td>
                    <td class="positive" style="text-align: right; font-weight: 700;">${idx.avgDy.toFixed(2)}%</td>
                    <td style="text-align: right; font-size: 0.82rem; font-weight: 600;">${idx.avgMultiple}</td>
                </tr>`;
            }).join('');
        }

        function openIndexDetailModal(indexCode) {
            const data = window.dashboardData || {};
            const stocks = Array.isArray(data.stocks) ? data.stocks : [];
            const fiis = Array.isArray(data.fiis) ? data.fiis : [];
            const fiagros = Array.isArray(data.fiagros) ? data.fiagros : [];

            const indexInfo = {
                'IBOV': { name: 'Índice Bovespa (IBOV)', desc: 'Ações monitoradas do principal índice de liquidez da B3' },
                'IDIV': { name: 'Índice de Dividendos (IDIV)', desc: 'Empresas com histórico sólido e consistência de proventos' },
                'SMLL': { name: 'Índice Small Caps (SMLL / SMAL11)', desc: 'Empresas de menor e média capitalização com alto potencial' },
                'IFIX': { name: 'Índice de Fundos Imobiliários (IFIX)', desc: 'Fundos Imobiliários acompanhados no radar e listados na B3' },
                'IFNC': { name: 'Índice Financeiro (IFNC)', desc: 'Bancos, seguradoras e empresas do setor financeiro' },
                'IEE': { name: 'Índice de Energia Elétrica (IEE)', desc: 'Empresas geradoras, transmissoras e distribuidoras de energia' },
                'IAGRO': { name: 'Cadeia do Agronegócio (IAGRO)', desc: 'FIAGROs e empresas ligadas ao agronegócio brasileiro' }
            }[indexCode] || { name: `Índice ${indexCode}`, desc: 'Carteira teórica de ativos' };

            let foundItems = [];

            if (indexCode === 'IFIX') {
                foundItems = fiis.map(f => ({
                    ticker: f.ticker,
                    name: f.name || f.ticker,
                    price: Number(f.price) || 0,
                    pe: null,
                    pb: f.pb_ratio != null ? Number(f.pb_ratio) : null,
                    dy: Number(f.dividend_yield) || 0,
                    score: Number(f.score) || 0,
                    type: 'fii'
                }));
            } else if (indexCode === 'IAGRO') {
                foundItems = [
                    ...fiagros.map(fg => ({
                        ticker: fg.ticker,
                        name: fg.name || fg.ticker,
                        price: Number(fg.price) || 0,
                        pe: null,
                        pb: fg.pb_ratio != null ? Number(fg.pb_ratio) : null,
                        dy: Number(fg.dividend_yield) || 0,
                        score: Number(fg.score) || 0,
                        type: 'fiagro'
                    })),
                    ...stocks.filter(s => (s.sector || '').toLowerCase().includes('agro') || (s.sector || '').toLowerCase().includes('alimentos')).map(s => ({
                        ticker: s.ticker,
                        name: s.name || s.ticker,
                        price: Number(s.price) || 0,
                        pe: s.pe_ratio != null ? Number(s.pe_ratio) : null,
                        pb: s.pb_ratio != null ? Number(s.pb_ratio) : null,
                        dy: Number(s.dividend_yield) || 0,
                        score: Number(s.score) || 0,
                        type: 'stock'
                    }))
                ];
            } else {
                foundItems = stocks.filter(s => Array.isArray(s.indices) && s.indices.includes(indexCode)).map(s => ({
                    ticker: s.ticker,
                    name: s.name || s.ticker,
                    price: Number(s.price) || 0,
                    pe: s.pe_ratio != null ? Number(s.pe_ratio) : null,
                    pb: s.pb_ratio != null ? Number(s.pb_ratio) : null,
                    dy: Number(s.dividend_yield) || 0,
                    score: Number(s.score) || 0,
                    type: 'stock'
                }));
            }

            foundItems.sort((a, b) => (b.score - a.score) || (b.dy - a.dy));

            const nameEl = document.getElementById('sector-modal-name');
            const statsEl = document.getElementById('sector-modal-stats');
            const tbody = document.getElementById('sector-modal-tbody');

            if (nameEl) nameEl.textContent = indexInfo.name;
            if (statsEl) {
                const count = foundItems.length;
                const avgScore = count > 0 ? (foundItems.reduce((acc, s) => acc + s.score, 0) / count) : 0;
                const avgDy = count > 0 ? (foundItems.reduce((acc, s) => acc + s.dy, 0) / count * 100) : 0;
                const profStocks = foundItems.filter(s => s.pe !== null && s.pe > 0);
                const avgPeStr = profStocks.length > 0 ? (profStocks.reduce((acc, s) => acc + s.pe, 0) / profStocks.length).toFixed(2) + 'x' : (indexCode === 'IFIX' ? 'FIIs' : 'N/A');

                statsEl.innerHTML = `
                    <span style="background:var(--surface); padding:0.25rem 0.6rem; border-radius:4px; border:1px solid var(--card-border);"><strong>${count}</strong> ativos</span>
                    <span style="background:var(--surface); padding:0.25rem 0.6rem; border-radius:4px; border:1px solid var(--card-border);">Score Médio: <strong>${avgScore.toFixed(2)}</strong></span>
                    <span style="background:var(--surface); padding:0.25rem 0.6rem; border-radius:4px; border:1px solid var(--card-border); color:var(--positive);">DY Médio: <strong>${avgDy.toFixed(2)}%</strong></span>
                    <span style="background:var(--surface); padding:0.25rem 0.6rem; border-radius:4px; border:1px solid var(--card-border);">Múltiplo: <strong>${avgPeStr}</strong></span>
                `;
            }

            if (tbody) {
                if (foundItems.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-secondary); padding: 1.5rem;">Nenhum ativo cadastrado para este índice.</td></tr>';
                } else {
                    tbody.innerHTML = foundItems.map(item => {
                        const peFormatted = item.pe !== null ? item.pe.toFixed(2) : 'N/A';
                        const pbFormatted = item.pb !== null ? item.pb.toFixed(2) : 'N/A';
                        const dyFormatted = (item.dy * 100).toFixed(2) + '%';
                        const peClass = (item.pe !== null && item.pe > 0 && item.pe <= 15) ? 'positive' : 'warning';
                        const pbClass = (item.pb !== null && item.pb > 0 && item.pb <= 1.5) ? 'positive' : 'warning';
                        const dyClass = item.dy >= 0.06 ? 'positive' : 'negative';

                        return `
                        <tr onclick="closeSectorDetailModal(); openDetailModal('${item.ticker}', '${item.type || 'stock'}');" style="cursor: pointer;">
                            <td class="ticker-cell" style="font-weight:700;">${item.ticker}</td>
                            <td class="name-cell" title="${(item.name || '').replace(/"/g, '&quot;')}" style="font-size:0.78rem; max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; cursor:help;">${item.name}</td>
                            <td style="font-weight:600;">R$ ${item.price.toFixed(2)}</td>
                            <td class="${peClass}">${peFormatted}</td>
                            <td class="${pbClass}">${pbFormatted}</td>
                            <td class="${dyClass}" style="font-weight:600;">${dyFormatted}</td>
                            <td style="text-align:center;">
                                <span class="score-pill ${getScoreRangeClass(item.score)}">${formatScore(item.score)}</span>
                            </td>
                        </tr>`;
                    }).join('');
                }
            }

            const modal = document.getElementById('sector-detail-modal');
            if (modal) modal.classList.remove('hidden');
        }

        let activeChart = null;
        let currentAssetHistory = [];
        let currentAssetType = '';
        let currentAssetMetrics = {};
        let currentAssetRange = 10;
        function formatBreakdownDesc(item, metrics, type) {
            if (!item || !item.desc) return 'N/A';
            let desc = String(item.desc).trim();

            if (desc === 'N/A' || desc === 'N/D' || desc === 'null') {
                const labelLower = (item.label || '').toLowerCase();
                
                if (labelLower.includes('p/l') || labelLower.includes('lucro')) {
                    if (metrics && metrics.eps !== null && metrics.eps !== undefined && metrics.eps <= 0) {
                        return `N/A — Prejuízo recente (LPA R$ ${metrics.eps.toFixed(2)}; P/L inaplicável)`;
                    } else if (metrics && metrics.roe !== null && metrics.roe !== undefined && metrics.roe <= 0) {
                        return `N/A — Prejuízo contábil no período (ROE: ${(metrics.roe * 100).toFixed(1)}%)`;
                    } else {
                        return 'N/A — Histórico de lucros deficitário ou indisponível';
                    }
                }
                
                if (labelLower.includes('graham') || labelLower.includes('peg')) {
                    if (metrics && metrics.eps !== null && metrics.eps !== undefined && metrics.eps <= 0) {
                        return 'N/A — Inaplicável (Fórmula de Graham exige LPA > 0)';
                    } else if (metrics && metrics.vpa !== null && metrics.vpa !== undefined && metrics.vpa <= 0) {
                        return 'N/A — Inaplicável (Patrimônio Líquido negativo)';
                    } else {
                        return 'N/A — Graham requer lucros e patrimônio positivos';
                    }
                }
                
                if (labelLower.includes('yield') || labelLower.includes('dy')) {
                    return 'N/A — Sem distribuição de proventos no período';
                }
                
                if (labelLower.includes('p/vp') || labelLower.includes('patrimonial')) {
                    return 'N/A — Patrimônio Líquido negativo ou não informado';
                }
                
                if (labelLower.includes('roe') || labelLower.includes('rentabilidade')) {
                    return 'N/A — Lucro líquido ou patrimônio indisponível';
                }
                
                if (labelLower.includes('consistência') || labelLower.includes('proventos')) {
                    return 'N/A — Histórico de pagamentos recente (< 3 anos) ou irregular';
                }
            }
            
            return desc;
        }

        function openDetailModal(ticker, type) {
            const rows = document.querySelectorAll(`[data-ticker="${ticker}"]`);
            let row = rows.length > 0 ? rows[0] : null;

            const data = window.dashboardData || {};
            let asset = null;
            if (!type) {
                if (data.stocks && data.stocks.some(s => s.ticker === ticker)) type = 'stock';
                else if (data.fiis && data.fiis.some(f => f.ticker === ticker)) type = 'fii';
                else if (data.fiagros && data.fiagros.some(fa => fa.ticker === ticker)) type = 'fiagro';
                else type = 'stock';
            }

            if (type === 'stock') asset = (data.stocks || []).find(s => s.ticker === ticker);
            else if (type === 'fii') asset = (data.fiis || []).find(f => f.ticker === ticker);
            else if (type === 'fiagro') asset = (data.fiagros || []).find(fa => fa.ticker === ticker);

            if (!row && !asset) return;

            if (!row && asset) {
                row = {
                    getAttribute: function(attr) {
                        if (attr === 'data-name') return asset.name || ticker;
                        if (attr === 'data-sector') return asset.sector || '';
                        if (attr === 'data-price') return asset.price != null ? String(asset.price) : '0';
                        if (attr === 'data-pe') return asset.pe_ratio != null ? String(asset.pe_ratio) : (asset.pe != null ? String(asset.pe) : null);
                        if (attr === 'data-pb') return asset.pb_ratio != null ? String(asset.pb_ratio) : (asset.pb != null ? String(asset.pb) : null);
                        if (attr === 'data-dy') return asset.dividend_yield != null ? String(asset.dividend_yield) : (asset.dy != null ? String(asset.dy) : '0');
                        if (attr === 'data-roe') return asset.roe != null ? String(asset.roe) : null;
                        if (attr === 'data-score') return asset.score != null ? String(asset.score) : '0';
                        if (attr === 'data-bazin') return asset.bazin_price != null ? String(asset.bazin_price) : (asset.bazin != null ? String(asset.bazin) : '0');
                        if (attr === 'data-graham') return asset.graham_price != null ? String(asset.graham_price) : (asset.graham != null ? String(asset.graham) : '0');
                        if (attr === 'data-eps') return asset.eps != null ? String(asset.eps) : (asset.lpa != null ? String(asset.lpa) : null);
                        if (attr === 'data-vpa') return asset.vpa != null ? String(asset.vpa) : null;
                        if (attr === 'data-rate') return asset.dividend_rate != null ? String(asset.dividend_rate) : (asset.rate != null ? String(asset.rate) : '0');
                        if (attr === 'data-breakdown') return typeof asset.score_breakdown === 'string' ? asset.score_breakdown : JSON.stringify(asset.score_breakdown || []);
                        if (attr === 'data-history') return typeof asset.history_json === 'string' ? asset.history_json : JSON.stringify(asset.history_json || []);
                        return null;
                    }
                };
            }

            // Configure dropdown options based on asset type
            const selectEl = document.getElementById('chart-indicator-select');
            if (selectEl) {
                Array.from(selectEl.options).forEach(opt => {
                    opt.disabled = false;
                    opt.style.display = 'block';
                });
                if (type === 'stock') {
                    const opt = selectEl.querySelector('option[value="consistency"]');
                    if (opt) {
                        opt.disabled = true;
                        opt.style.display = 'none';
                    }
                } else {
                    const hiddenOpts = ['pe', 'pe_5y', 'dy_3y', 'roe', 'graham'];
                    hiddenOpts.forEach(val => {
                        const opt = selectEl.querySelector(`option[value="${val}"]`);
                        if (opt) {
                            opt.disabled = true;
                            opt.style.display = 'none';
                        }
                    });
                }
            }

            // Populate Header
            document.getElementById('modal-ticker').textContent = ticker;
            document.getElementById('modal-name').textContent = row.getAttribute('data-name');

            // Clear previous scorecard and load details
            const scoreContainer = document.getElementById('modal-score-badge-container');
            const scorecard = document.getElementById('modal-scorecard-breakdown');
            scoreContainer.innerHTML = '';
            scorecard.innerHTML = '';

            const price = parseFloat(row.getAttribute('data-price')) || 0;

            if (type === 'stock') {
                const peRaw = row.getAttribute('data-pe');
                const pe = (peRaw !== null && peRaw !== 'null' && peRaw !== '') ? parseFloat(peRaw) : null;
                const pbRaw = row.getAttribute('data-pb');
                const pb = (pbRaw !== null && pbRaw !== 'null' && pbRaw !== '') ? parseFloat(pbRaw) : null;
                const dy = parseFloat(row.getAttribute('data-dy')) || 0;
                const roeRaw = row.getAttribute('data-roe');
                const roe = (roeRaw !== null && roeRaw !== 'null' && roeRaw !== '') ? parseFloat(roeRaw) : null;
                const score = parseFloat(row.getAttribute('data-score')) || 0;
                const bazin = parseFloat(row.getAttribute('data-bazin')) || 0;
                const graham = parseFloat(row.getAttribute('data-graham')) || 0;
                const epsRaw = row.getAttribute('data-eps');
                const eps = (epsRaw !== null && epsRaw !== 'null' && epsRaw !== '') ? parseFloat(epsRaw) : null;
                const vpaRaw = row.getAttribute('data-vpa');
                const vpa = (vpaRaw !== null && vpaRaw !== 'null' && vpaRaw !== '') ? parseFloat(vpaRaw) : null;

                currentAssetMetrics = {
                    price: price,
                    dy: dy,
                    eps: eps,
                    vpa: vpa,
                    dividendRate: price * dy,
                    graham_price: graham,
                    roe: roe
                };

                // Render breakdown
                const scoreVal = parseFloat(row.getAttribute('data-score')) || 0;
                const breakdown = JSON.parse(row.getAttribute('data-breakdown') || '[]');
                scoreContainer.innerHTML = `<span class="score-pill ${getScoreRangeClass(scoreVal)}" style="width: auto; height: auto; border-radius: 12px; padding: 0.5rem 1.2rem; font-size: 1.05rem;">Score: ${formatScore(scoreVal)}</span>`;

                breakdown.forEach(function(item) {
                    // Compatibilidade: dados antigos podem carregar o bônus macro removido.
                    if (item.label === 'Moderadores Macro (v3)') return;
                    var pct = Math.round((item.score / item.max) * 100);
                    var barColor = item.score >= (item.max * 0.75) ? '#10b981' : item.score >= (item.max * 0.40) ? '#f59e0b' : '#ef4444';
                    var contextualDesc = formatBreakdownDesc(item, currentAssetMetrics, 'stock');
                    var el = document.createElement('div');
                    el.className = 'breakdown-item';
                    el.innerHTML = [
                        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">',
                        '  <span class="hint" tabindex="0" data-tip="', item.tip, '" style="font-weight:700;font-size:0.85rem;">', item.label, ' ⓘ</span>',
                        '  <span style="font-size:0.85rem;color:var(--text-secondary);font-weight:600;">', item.score.toFixed(2), ' / ', item.max.toFixed(1), '</span>',
                        '</div>',
                        '<div class="bar-container">',
                        '  <div class="bar-fill" style="width:', pct, '%;background:', barColor, ';"></div>',
                        '</div>',
                        '<small style="color:var(--text-secondary);display:block;margin-top:0.15rem;font-size:0.8rem;">', contextualDesc, '</small>'
                    ].join('');
                    scorecard.appendChild(el);
                });
                // Inicializa tooltips nos novos hints do breakdown
                if (window.initHints) window.initHints(scorecard);
                // Value investing disclaimer
                var disc = document.createElement('div');
                disc.style.cssText = 'margin-top:0.75rem;padding:0.7rem;background:var(--surface);border-radius:4px;font-size:0.8rem;color:var(--text-muted);line-height:1.4;border:1px solid var(--card-border);';
                disc.textContent = '⚡ Esta é uma avaliação sob a ótica do value investing: busca por empresas lucrativas, saudáveis e negociadas com desconto. Uma nota baixa não significa que a empresa seja ruim, apenas que não atende aos critérios rigorosos de oportunidade value no momento.';
                scorecard.appendChild(disc);


            } else {
                // For FII / FIAGRO
                const pbRaw = row.getAttribute('data-pb');
                const pb = (pbRaw !== null && pbRaw !== 'null' && pbRaw !== '') ? parseFloat(pbRaw) : null;
                const dy = parseFloat(row.getAttribute('data-dy')) || 0;
                const rate = parseFloat(row.getAttribute('data-rate')) || 0;
                const vpaRaw = row.getAttribute('data-vpa');
                const vpa = (vpaRaw !== null && vpaRaw !== 'null' && vpaRaw !== '') ? parseFloat(vpaRaw) : (pb && pb > 0 ? (price / pb) : null);
                const score = parseFloat(row.getAttribute('data-score')) || 0;

                currentAssetMetrics = {
                    price: price,
                    dy: dy,
                    vpa: vpa,
                    dividendRate: rate || (price * dy)
                };

                // Render breakdown
                const scoreVal = parseFloat(row.getAttribute('data-score')) || 0;
                const breakdown = JSON.parse(row.getAttribute('data-breakdown') || '[]');
                scoreContainer.innerHTML = `<span class="score-pill ${getScoreRangeClass(scoreVal)}" style="width: auto; height: auto; border-radius: 12px; padding: 0.5rem 1.2rem; font-size: 1.05rem;">Score: ${formatScore(scoreVal)}</span>`;

                breakdown.forEach(function(item) {
                    var pct = Math.round((item.score / item.max) * 100);
                    var barColor = item.score >= (item.max * 0.75) ? '#10b981' : item.score >= (item.max * 0.40) ? '#f59e0b' : '#ef4444';
                    var contextualDesc = formatBreakdownDesc(item, currentAssetMetrics, type);
                    var el = document.createElement('div');
                    el.className = 'breakdown-item';
                    el.innerHTML = [
                        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">',
                        '  <span class="hint" tabindex="0" data-tip="', item.tip, '" style="font-weight:700;font-size:0.85rem;">', item.label, ' ⓘ</span>',
                        '  <span style="font-size:0.85rem;color:var(--text-secondary);font-weight:600;">', item.score.toFixed(2), ' / ', item.max.toFixed(1), '</span>',
                        '</div>',
                        '<div class="bar-container">',
                        '  <div class="bar-fill" style="width:', pct, '%;background:', barColor, ';"></div>',
                        '</div>',
                        '<small style="color:var(--text-secondary);display:block;margin-top:0.15rem;font-size:0.8rem;">', contextualDesc, '</small>'
                    ].join('');
                    scorecard.appendChild(el);
                });
                // Inicializa tooltips nos novos hints do breakdown
                if (window.initHints) window.initHints(scorecard);
                // Value investing disclaimer
                var disc = document.createElement('div');
                disc.style.cssText = 'margin-top:0.75rem;padding:0.7rem;background:var(--surface);border-radius:4px;font-size:0.8rem;color:var(--text-muted);line-height:1.4;border:1px solid var(--card-border);';
                disc.textContent = '⚡ Esta é uma avaliação sob a ótica do value investing: busca por ativos com bom retorno em dividendos, preço justo e consistência. Uma nota baixa não significa que o fundo seja ruim, apenas que não atende aos critérios rigorosos de oportunidade value no momento.';
                scorecard.appendChild(disc);


            }

            // Handle History Chart
            currentAssetHistory = JSON.parse(row.getAttribute('data-history') || '[]');
            currentAssetType = type;
            currentAssetRange = 10;

            // Reset range selector button states
            document.querySelectorAll('.range-btn').forEach(btn => btn.classList.remove('active'));
            const activeRangeBtn = document.getElementById('btn-range-10');
            if (activeRangeBtn) activeRangeBtn.classList.add('active');

            // Reset dropdown to "score"
            document.getElementById('chart-indicator-select').value = 'score';

            renderChart(currentAssetHistory, 'score');

            // Populate modal asset data for export
            const peRaw = row.getAttribute('data-pe');
            const pbRaw = row.getAttribute('data-pb');
            const roeRaw = row.getAttribute('data-roe');
            const epsRaw = row.getAttribute('data-eps');
            const vpaRaw = row.getAttribute('data-vpa');
            window.currentModalAssetData = {
                ticker: ticker,
                name: row.getAttribute('data-name') || ticker,
                type: type,
                sector: row.getAttribute('data-sector') || '',
                price: price,
                pe: (peRaw !== null && peRaw !== 'null' && peRaw !== '') ? parseFloat(peRaw) : null,
                pb: (pbRaw !== null && pbRaw !== 'null' && pbRaw !== '') ? parseFloat(pbRaw) : null,
                dy: parseFloat(row.getAttribute('data-dy')) || 0,
                roe: (roeRaw !== null && roeRaw !== 'null' && roeRaw !== '') ? parseFloat(roeRaw) : null,
                score: parseFloat(row.getAttribute('data-score')) || 0,
                bazin: parseFloat(row.getAttribute('data-bazin')) || 0,
                graham: parseFloat(row.getAttribute('data-graham')) || 0,
                eps: (epsRaw !== null && epsRaw !== 'null' && epsRaw !== '') ? parseFloat(epsRaw) : null,
                vpa: (vpaRaw !== null && vpaRaw !== 'null' && vpaRaw !== '') ? parseFloat(vpaRaw) : null,
                rate: parseFloat(row.getAttribute('data-rate')) || 0,
                breakdown: JSON.parse(row.getAttribute('data-breakdown') || '[]'),
                history: currentAssetHistory
            };

            // Show Modal
            document.getElementById('detail-modal').classList.remove('hidden');
            if (typeof syncUrlFromState === 'function') syncUrlFromState();
        }

        function closeDetailModal() {
            document.getElementById('detail-modal').classList.add('hidden');
            if (activeChart) {
                activeChart.destroy();
                activeChart = null;
            }
            currentAssetHistory = [];
            currentAssetType = '';
            currentAssetMetrics = {};
            if (typeof syncUrlFromState === 'function') syncUrlFromState();
        }

        function closeModalOnOutsideClick(event) {
            if (event.target === document.getElementById('detail-modal')) {
                closeDetailModal();
            }
        }

        function updateChartRange(years) {
            currentAssetRange = years;

            // Update range button active state
            document.querySelectorAll('.range-btn').forEach(btn => {
                btn.classList.remove('active');
            });

            const btn = document.getElementById(`btn-range-${years}`);
            if (btn) {
                btn.classList.add('active');
            }

            updateChartIndicator();
        }

        function updateChartIndicator() {
            const select = document.getElementById('chart-indicator-select');
            const indicator = select.value;
            renderChart(currentAssetHistory, indicator);
        }

        function roundValue(value, decimals) {
            if (value === null || isNaN(value)) return null;
            return Number(Math.round(value + 'e' + decimals) + 'e-' + decimals);
        }

        /* Bloco duplicado e incompleto isolado; a implementação íntegra está abaixo. */
        /* function renderChart(history, indicator = 'price') {
            const ctx = document.getElementById('history-chart').getContext('2d');

            if (activeChart) {
                activeChart.destroy();
            }

            if (!history || history.length === 0) {
                ctx.clearRect(0, 0, 400, 250);
                ctx.fillStyle = '#9ca3af';
                ctx.font = '14px Inter';
                ctx.textAlign = 'center';
                ctx.fillText('Nenhum histórico disponível', 200, 125);
                return;
            }

            // Filter history based on currentAssetRange
            let filteredHistory = history;
            if (currentAssetRange < 10) {
                const latestDateStr = history[history.length - 1].date;
                const parts = latestDateStr.split('-');
                const cutoffYear = parseInt(parts[0]) - currentAssetRange;
                const cutoffDateStr = `${cutoffYear}-${parts[1]}-${parts[2]}`;
                filteredHistory = history.filter(h => h.date >= cutoffDateStr);
            }

            // Reduz a quantidade de pontos pela metade para evitar poluição visual no gráfico (mantendo o último ponto)
            if (filteredHistory.length > 6) {
                const sampled = [];
                for (let i = 0; i < filteredHistory.length - 1; i += 2) {
                    sampled.push(filteredHistory[i]);
                }
                sampled.push(filteredHistory[filteredHistory.length - 1]);
                filteredHistory = sampled;
            }

            if (filteredHistory.length === 0) {
                ctx.clearRect(0, 0, 400, 250);
                ctx.fillStyle = '#9ca3af';
                ctx.font = '14px Inter';
                ctx.textAlign = 'center';
                ctx.fillText('Nenhum dado no período selecionado', 200, 125);
                return;
            }

            const labels = filteredHistory.map(h => {
                const parts = h.date.split('-');
                return `${parts[1]}/${parts[0]}`; // MM/AAAA
            });

            let data = [];
            let label = '';
            let borderColor = '#3b82f6';
            let backgroundColor = 'rgba(59, 130, 246, 0.05)';

            if (indicator === 'score') {
                data = filteredHistory.map(h => h.score !== undefined ? h.score : null);
                label = 'Score Radar';
                borderColor = '#10b981';
                backgroundColor = 'rgba(16, 185, 129, 0.05)';
            } else if (indicator === 'price') {
                data = filteredHistory.map(h => h.price);
                label = 'Preço (R$)';
                borderColor = '#3b82f6';
                backgroundColor = 'rgba(59, 130, 246, 0.05)';
            } else if (indicator === 'dy') {
                data = filteredHistory.map(h => {
                    if (h.dy !== undefined && h.dy !== null) return h.dy;
                    const divRate = currentAssetMetrics.dividendRate;
                    return (divRate !== null && divRate > 0) ? roundValue((divRate / h.price) * 100, 2) : 0;
                });
                label = 'Dividend Yield (12m) (%)';
                borderColor = '#10b981';
                backgroundColor = 'rgba(16, 185, 129, 0.05)';
            } else if (indicator === 'dy_3y') {
                data = filteredHistory.map(h => h.dy_3y !== undefined ? h.dy_3y : null);
                label = 'DY Médio (3 Anos) (%)';
                borderColor = '#059669';
                backgroundColor = 'rgba(5, 150, 105, 0.05)';
            } else if (indicator === 'pe') {
                data = filteredHistory.map(h => {
                    if (h.pe !== undefined && h.pe !== null) return h.pe;
                    const eps = currentAssetMetrics.eps;
                    return (eps !== null && eps !== 0) ? roundValue(h.price / eps, 2) : null;
                });
                label = 'P/L';
                borderColor = '#a855f7';
                backgroundColor = 'rgba(168, 85, 247, 0.05)';
            } else if (indicator === 'pe_5y') {
                data = filteredHistory.map(h => h.pe_5y !== undefined ? h.pe_5y : null);
                label = 'P/L Médio (5 Anos)';
                borderColor = '#7c3aed';
                backgroundColor = 'rgba(124, 58, 237, 0.05)';
            } else if (indicator === 'pb') {
                data = filteredHistory.map(h => {
                    if (h.pb !== undefined && h.pb !== null) return h.pb;
                    const vpa = currentAssetMetrics.vpa;
                    return (vpa !== null && vpa > 0) ? roundValue(h.price / vpa, 2) : null;
                });
                label = 'P/VP';
                borderColor = '#eab308';
                backgroundColor = 'rgba(234, 179, 8, 0.05)';
            } else if (indicator === 'roe') {
                data = filteredHistory.map(h => h.roe !== undefined ? h.roe : null);
                label = 'ROE (%)';
                borderColor = '#f59e0b';
                backgroundColor = 'rgba(245, 158, 11, 0.05)';
            } else if (indicator === 'graham') {
                // Return Graham Fair Price
                data = filteredHistory.map(h => {
                    if (h.graham !== undefined && h.graham !== null && h.graham > 2.0) {
                        return h.graham;
                    }
                    return currentAssetMetrics.graham_price || null;
                });
                label = 'Preço Justo (Graham)';
                borderColor = '#ef4444';
                backgroundColor = 'rgba(239, 68, 68, 0.05)';
            } else if (indicator === 'consistency') {
                data = filteredHistory.map(h => h.consistency !== undefined ? h.consistency : null);
                label = 'Consistência de proventos (6m/6m) (%)';
                borderColor = '#3b82f6';
                backgroundColor = 'rgba(59, 130, 246, 0.05)';
            }

            let chartDatasets = [];
            if (indicator === 'graham') {
                chartDatasets = [
                    {
                        label: 'Preço de Mercado (R$)',
                        data: filteredHistory.map(h => h.price),
                        borderColor: '#3b82f6',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: filteredHistory.length > 30 ? 0 : 3,
                        pointHoverRadius: 5,
                        fill: false,
                        tension: 0.1
                    },
                    {
                        label: 'Preço Justo de Graham (R$)',
                        data: data,
            // Reset dropdown to "score"
            document.getElementById('chart-indicator-select').value = 'score';

            renderChart(currentAssetHistory, 'score');

            // Show Modal
            document.getElementById('detail-modal').classList.remove('hidden');
        }

        function closeDetailModal() {
            document.getElementById('detail-modal').classList.add('hidden');
            if (activeChart) {
                activeChart.destroy();
                activeChart = null;
            }
            currentAssetHistory = [];
            currentAssetType = '';
            currentAssetMetrics = {};
        }

        function closeModalOnOutsideClick(event) {
            if (event.target === document.getElementById('detail-modal')) {
                closeDetailModal();
            }
        }

        function updateChartRange(years) {
            currentAssetRange = years;

            // Update range button active state
            document.querySelectorAll('.range-btn').forEach(btn => {
                btn.classList.remove('active');
            });

            const btn = document.getElementById(`btn-range-${years}`);
            if (btn) {
                btn.classList.add('active');
            }

            updateChartIndicator();
        }

        function updateChartIndicator() {
            const select = document.getElementById('chart-indicator-select');
            const indicator = select.value;
            renderChart(currentAssetHistory, indicator);
        }

        function roundValue(value, decimals) {
            if (value === null || isNaN(value)) return null;
            return Number(Math.round(value + 'e' + decimals) + 'e-' + decimals);
        }

        */
        function renderChart(history, indicator = 'price') {
            const ctx = document.getElementById('history-chart').getContext('2d');

            if (activeChart) {
                activeChart.destroy();
            }

            if (!history || history.length === 0) {
                ctx.clearRect(0, 0, 400, 250);
                ctx.fillStyle = '#9ca3af';
                ctx.font = '14px Inter';
                ctx.textAlign = 'center';
                ctx.fillText('Nenhum histórico disponível', 200, 125);
                return;
            }

            // Filter history based on currentAssetRange
            let filteredHistory = history;
            if (currentAssetRange < 10) {
                const latestDateStr = history[history.length - 1].date;
                const parts = latestDateStr.split('-');
                const cutoffYear = parseInt(parts[0]) - currentAssetRange;
                const cutoffDateStr = `${cutoffYear}-${parts[1]}-${parts[2]}`;
                filteredHistory = history.filter(h => h.date >= cutoffDateStr);
            }

            // Reduz a quantidade de pontos pela metade para evitar poluição visual no gráfico (mantendo o último ponto)
            if (filteredHistory.length > 6) {
                const sampled = [];
                for (let i = 0; i < filteredHistory.length - 1; i += 2) {
                    sampled.push(filteredHistory[i]);
                }
                sampled.push(filteredHistory[filteredHistory.length - 1]);
                filteredHistory = sampled;
            }

            if (filteredHistory.length === 0) {
                ctx.clearRect(0, 0, 400, 250);
                ctx.fillStyle = '#9ca3af';
                ctx.font = '14px Inter';
                ctx.textAlign = 'center';
                ctx.fillText('Nenhum dado no período selecionado', 200, 125);
                return;
            }

            const labels = filteredHistory.map(h => {
                const parts = h.date.split('-');
                return `${parts[1]}/${parts[0]}`; // MM/AAAA
            });

            let data = [];
            let label = '';
            let borderColor = '#3b82f6';
            let backgroundColor = 'rgba(59, 130, 246, 0.05)';

            if (indicator === 'score') {
                data = filteredHistory.map(h => h.score !== undefined ? h.score : null);
                label = 'Score Radar';
                borderColor = '#10b981';
                backgroundColor = 'rgba(16, 185, 129, 0.05)';
            } else if (indicator === 'price') {
                data = filteredHistory.map(h => h.price);
                label = 'Preço (R$)';
                borderColor = '#3b82f6';
                backgroundColor = 'rgba(59, 130, 246, 0.05)';
            } else if (indicator === 'dy') {
                data = filteredHistory.map(h => {
                    if (h.dy !== undefined && h.dy !== null) return h.dy;
                    const divRate = currentAssetMetrics.dividendRate;
                    return (divRate !== null && divRate > 0) ? roundValue((divRate / h.price) * 100, 2) : 0;
                });
                label = 'Dividend Yield (12m) (%)';
                borderColor = '#10b981';
                backgroundColor = 'rgba(16, 185, 129, 0.05)';
            } else if (indicator === 'dy_3y') {
                data = filteredHistory.map(h => h.dy_3y !== undefined ? h.dy_3y : null);
                label = 'DY Médio (3 Anos) (%)';
                borderColor = '#059669';
                backgroundColor = 'rgba(5, 150, 105, 0.05)';
            } else if (indicator === 'pe') {
                data = filteredHistory.map(h => {
                    if (h.pe !== undefined && h.pe !== null) return h.pe;
                    const eps = currentAssetMetrics.eps;
                    return (eps !== null && eps !== 0) ? roundValue(h.price / eps, 2) : null;
                });
                label = 'P/L';
                borderColor = '#a855f7';
                backgroundColor = 'rgba(168, 85, 247, 0.05)';
            } else if (indicator === 'pe_5y') {
                data = filteredHistory.map(h => h.pe_5y !== undefined ? h.pe_5y : null);
                label = 'P/L Médio (5 Anos)';
                borderColor = '#7c3aed';
                backgroundColor = 'rgba(124, 58, 237, 0.05)';
            } else if (indicator === 'pb') {
                data = filteredHistory.map(h => {
                    if (h.pb !== undefined && h.pb !== null) return h.pb;
                    const vpa = currentAssetMetrics.vpa;
                    return (vpa !== null && vpa > 0) ? roundValue(h.price / vpa, 2) : null;
                });
                label = 'P/VP';
                borderColor = '#eab308';
                backgroundColor = 'rgba(234, 179, 8, 0.05)';
            } else if (indicator === 'roe') {
                data = filteredHistory.map(h => h.roe !== undefined ? h.roe : null);
                label = 'ROE (%)';
                borderColor = '#f59e0b';
                backgroundColor = 'rgba(245, 158, 11, 0.05)';
            } else if (indicator === 'graham') {
                // Return Graham Fair Price
                data = filteredHistory.map(h => {
                    if (h.graham !== undefined && h.graham !== null && h.graham > 2.0) {
                        return h.graham;
                    }
                    return currentAssetMetrics.graham_price || null;
                });
                label = 'Preço Justo (Graham)';
                borderColor = '#ef4444';
                backgroundColor = 'rgba(239, 68, 68, 0.05)';
            } else if (indicator === 'consistency') {
                data = filteredHistory.map(h => h.consistency !== undefined ? h.consistency : null);
                label = 'Consistência de proventos (6m/6m) (%)';
                borderColor = '#3b82f6';
                backgroundColor = 'rgba(59, 130, 246, 0.05)';
            }

            let chartDatasets = [];
            if (indicator === 'graham') {
                chartDatasets = [
                    {
                        label: 'Preço de Mercado (R$)',
                        data: filteredHistory.map(h => h.price),
                        borderColor: '#3b82f6',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: filteredHistory.length > 30 ? 0 : 3,
                        pointHoverRadius: 5,
                        fill: false,
                        tension: 0.1
                    },
                    {
                        label: 'Preço Justo de Graham (R$)',
                        data: data,
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.05)',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        pointRadius: 0,
                        pointHoverRadius: 0,
                        fill: true,
                        tension: 0
                    }
                ];
            } else {
                chartDatasets = [{
                    label: label,
                    data: data,
                    borderColor: borderColor,
                    backgroundColor: backgroundColor,
                    borderWidth: 2,
                    pointRadius: filteredHistory.length > 30 ? 0 : 3,
                    pointHoverRadius: 5,
                    fill: true,
                    tension: 0.1
                }];
            }

            const isLight = !document.body.classList.contains('dark');
            const gridColor = isLight ? '#e2e4ea' : '#282c38';
            const tickColor = isLight ? '#6b7084' : '#8b8fa3';

            // Plugin customizado: desenha labels nos picos e vales (máx/min locais) sem colisão e com posicionamento dinâmico
            if (!Chart.registry.plugins.get('valueLabels')) {
                Chart.register({
                    id: 'valueLabels',
                    afterDatasetsDraw(chart) {
                        const options = chart.options.plugins?.valueLabels;
                        if (!options || options === false || options.enabled === false) return;
                        if (chart.config.type === 'bar') return;
                        if (!options.indicator) return;

                        const indicator = options.indicator;
                        const borderColor = options.borderColor || '#3b82f6';
                        const isLight = (options.isLight !== undefined) ? options.isLight : !document.body.classList.contains('dark');

                        const c = chart.ctx;

                        const candidates = [];
                        const seenIdx = new Set();
                        const padX = 6;  // margem de segurança horizontal
                        const padY = 3;  // margem de segurança vertical

                        chart.data.datasets.forEach((dataset, datasetIndex) => {
                            const meta = chart.getDatasetMeta(datasetIndex);
                            if (meta.hidden) return;
                            const pts = meta.data;
                            const ds = dataset.data;
                            if (!pts || pts.length < 2) return;

                            // Índices válidos (ignora null/undefined)
                            const valid = [];
                            for (let i = 0; i < ds.length; i++) {
                                if (ds[i] !== null && ds[i] !== undefined && pts[i]) {
                                    valid.push({ idx: i, val: ds[i] });
                                }
                            }
                            if (valid.length < 2) return;

                            // 1. Encontrar máximo e mínimo global do dataset
                            let maxVal = valid[0].val, maxIdx = valid[0].idx;
                            let minVal = valid[0].val, minIdx = valid[0].idx;
                            for (let i = 1; i < valid.length; i++) {
                                const { idx, val } = valid[i];
                                if (val > maxVal) { maxVal = val; maxIdx = idx; }
                                if (val < minVal) { minVal = val; minIdx = idx; }
                            }

                            function addCandidate(idx, priority, type) {
                                const key = `${datasetIndex}_${idx}`;
                                if (seenIdx.has(key)) return;
                                seenIdx.add(key);
                                candidates.push({ datasetIndex, idx, priority, type });
                            }

                            // Prioridade 1: Máximo e Mínimo Global
                            addCandidate(maxIdx, 1, 'peak');
                            addCandidate(minIdx, 1, 'valley');

                            // Prioridade 2: Último ponto (valor recente)
                            const lastItem = valid[valid.length - 1];
                            let lastType = 'peak';
                            if (valid.length > 1 && lastItem.val < valid[valid.length - 2].val) {
                                lastType = 'valley';
                            }
                            addCandidate(lastItem.idx, 2, lastType);

                            // Prioridade 3: Primeiro ponto
                            const firstItem = valid[0];
                            let firstType = 'valley';
                            if (valid.length > 1 && firstItem.val > valid[1].val) {
                                firstType = 'peak';
                            }
                            addCandidate(firstItem.idx, 3, firstType);

                            // Consistência já é uma razão móvel: rótulos locais em excesso
                            // transformavam pequenas oscilações em poluição visual. Nesse
                            // indicador, mantemos apenas início, mínimo, máximo e valor atual.
                            const showLocalExtrema = indicator !== 'consistency';
                            // Prioridade 4: Picos e vales locais intermediários
                            if (showLocalExtrema && valid.length > 2) {
                                for (let i = 1; i < valid.length - 1; i++) {
                                    const prev = valid[i - 1].val;
                                    const curr = valid[i].val;
                                    const next = valid[i + 1].val;
                                    if (curr > prev && curr > next) {
                                        addCandidate(valid[i].idx, 4, 'peak');
                                    } else if (curr < prev && curr < next) {
                                        addCandidate(valid[i].idx, 4, 'valley');
                                    }
                                }
                            }
                        });

                        // Ordenar candidatos por maior prioridade
                        candidates.sort((a, b) => a.priority - b.priority);

                        const drawnBoxes = [];
                        c.save();
                        c.font = 'bold 10px Inter, sans-serif';
                        c.textAlign = 'center';

                        for (const cand of candidates) {
                            const datasetIndex = cand.datasetIndex;
                            const i = cand.idx;
                            const meta = chart.getDatasetMeta(datasetIndex);
                            const pt = meta.data[i];
                            const ds = chart.data.datasets[datasetIndex].data;
                            const val = ds[i];
                            if (!pt || val === null || val === undefined) continue;

                            // Formata o texto apropriadamente
                            let txt;
                            if (indicator === 'price') txt = `R$ ${val.toFixed(2)}`;
                            else if (indicator === 'dy') txt = `${val.toFixed(2)}%`;
                            else if (indicator === 'score') txt = val.toFixed(1);
                            else txt = val.toFixed(2);

                            const tw = c.measureText(txt).width;
                            const boxH = 14;

                            let boxX1, boxY1, boxX2, boxY2;
                            let textY;
                            let textBaseline;

                            if (cand.type === 'peak') {
                                boxX1 = pt.x - tw / 2 - 3;
                                boxY1 = pt.y - 17;
                                boxX2 = pt.x + tw / 2 + 3;
                                boxY2 = pt.y - 3;
                                textY = pt.y - 5;
                                textBaseline = 'bottom';
                                // Se estourar o topo, inverte pra baixo
                                if (boxY1 < chart.chartArea.top) {
                                    boxY1 = pt.y + 3;
                                    boxY2 = pt.y + 17;
                                    textY = pt.y + 5;
                                    textBaseline = 'top';
                                }
                            } else {
                                boxX1 = pt.x - tw / 2 - 3;
                                boxY1 = pt.y + 3;
                                boxX2 = pt.x + tw / 2 + 3;
                                boxY2 = pt.y + 17;
                                textY = pt.y + 5;
                                textBaseline = 'top';
                                // Se estourar a base, inverte pra cima
                                if (boxY2 > chart.chartArea.bottom) {
                                    boxY1 = pt.y - 17;
                                    boxY2 = pt.y - 3;
                                    textY = pt.y - 5;
                                    textBaseline = 'bottom';
                                }
                            }
                            // Garante que a caixa e o texto não ultrapassem as bordas LATERAIS do gráfico
                            let textX = pt.x;
                            if (boxX1 < chart.chartArea.left) {
                                const dx = chart.chartArea.left - boxX1;
                                boxX1 += dx; boxX2 += dx; textX += dx;
                            } else if (boxX2 > chart.chartArea.right) {
                                const dx = boxX2 - chart.chartArea.right;
                                boxX1 -= dx; boxX2 -= dx; textX -= dx;
                            }

                            // Define caixa de colisão expandida com padding
                            const collisionBox = {
                                x1: boxX1 - padX,
                                y1: boxY1 - padY,
                                x2: boxX2 + padX,
                                y2: boxY2 + padY
                            };

                            // Verifica colisão
                            let collides = false;
                            for (const box of drawnBoxes) {
                                if (collisionBox.x1 < box.x2 &&
                                    collisionBox.x2 > box.x1 &&
                                    collisionBox.y1 < box.y2 &&
                                    collisionBox.y2 > box.y1) {
                                    collides = true;
                                    break;
                                }
                            }

                            if (collides) continue;

                            // Mantém os labels claros no tema claro; a cor da série fica na
                            // borda e no texto, sem os cards escuros que prejudicavam contraste.
                            const labelColor = chart.data.datasets[datasetIndex].borderColor || borderColor;
                            c.globalAlpha = 1;
                            c.fillStyle = isLight ? 'rgba(255, 255, 255, 0.98)' : 'rgba(15, 23, 42, 0.96)';
                            c.strokeStyle = labelColor;
                            c.lineWidth = 1;
                            if (c.roundRect) {
                                c.beginPath();
                                c.roundRect(boxX1, boxY1, boxX2 - boxX1, boxY2 - boxY1, 3);
                                c.fill();
                                c.stroke();
                            } else {
                                c.fillRect(boxX1, boxY1, boxX2 - boxX1, boxY2 - boxY1);
                                c.strokeRect(boxX1, boxY1, boxX2 - boxX1, boxY2 - boxY1);
                            }

                            // Desenha o texto (usa a cor do dataset correspondente ou a geral)
                            c.fillStyle = labelColor;
                            c.textBaseline = textBaseline;
                            c.fillText(txt, textX, textY);

                            // Registra o box desenhado
                            drawnBoxes.push(collisionBox);
                        }
                        c.restore();
                    }
                });
            }

            activeChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: chartDatasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: (indicator === 'graham'),
                            labels: {
                                color: tickColor,
                                font: { size: 10, family: 'Inter, sans-serif' }
                            }
                        },
                        tooltip: {
                            intersect: false,
                            mode: 'index',
                            backgroundColor: 'rgba(15, 23, 42, 0.9)',
                            titleFont: { size: 11, weight: '600' },
                            bodyFont: { size: 13, weight: '700' },
                            padding: 8,
                            cornerRadius: 4,
                            callbacks: {
                                title: function (items) {
                                    return items[0] ? items[0].label : '';
                                },
                                label: function (context) {
                                    let val = context.parsed.y;
                                    if (val === null || isNaN(val)) return 'N/A';
                                    if (indicator === 'graham') {
                                        return `${context.dataset.label}: R$ ${val.toFixed(2)}`;
                                    }
                                    if (indicator === 'price') return `Preço: R$ ${val.toFixed(2)}`;
                                    if (indicator === 'pe') return `P/L: ${val.toFixed(2)}`;
                                    if (indicator === 'pe_5y') return `P/L Médio (5 Anos): ${val.toFixed(2)}`;
                                    if (indicator === 'pb') return `P/VP: ${val.toFixed(2)}`;
                                    if (indicator === 'dy') return `DY (12m): ${val.toFixed(2)}%`;
                                    if (indicator === 'dy_3y') return `DY Médio (3 Anos): ${val.toFixed(2)}%`;
                                    if (indicator === 'roe') return `ROE: ${val.toFixed(2)}%`;
                                    if (indicator === 'consistency') return `Consistência: ${val.toFixed(2)}%`;
                                    return `Valor: ${val.toFixed(2)}`;
                                }
                            }
                        },
                        valueLabels: {
                            indicator: indicator,
                            borderColor: borderColor,
                            isLight: isLight
                        }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { color: tickColor, maxTicksLimit: 6, maxRotation: 30 }
                        },
                        y: {
                            grid: { color: gridColor },
                            ticks: { color: tickColor },
                            grace: '20%'
                        }
                    }
                }
            });
        }

        function toggleTheme() {
            const isDark = document.body.classList.toggle('dark');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');

            const themeIcon = document.getElementById('theme-toggle-icon');
            if (themeIcon) {
                if (isDark) {
                    themeIcon.innerHTML = `<circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>`;
                } else {
                    themeIcon.innerHTML = `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>`;
                }
            }

            if (activeChart && currentAssetHistory && currentAssetHistory.length > 0) {
                updateChartIndicator();
            }
            if (window.ettjChartInstance) {
                window.ettjChartInstance.destroy();
                window.ettjChartInstance = null;
                renderRendaFixaPanel(window.dashboardData);
            }
        }

        function loadDashboardData() {
            fetch('data.json')
                .then(response => response.json())
                .then(data => {
                    window.dashboardData = data; // store for export downloads
                    // 1. Timestamp
                    document.getElementById('timestamp-container').textContent = data.timestamp;

                    // 2. Render Home Panel (v3)
                    renderHomePanel(data);

                    // 3. Render Renda Fixa Panel (v3)
                    renderRendaFixaPanel(data);

                    // 4. Unique Sectors Filter
                    const sectorFilter = document.getElementById('sector-filter');
                    data.unique_sectors.forEach(sector => {
                        const opt = document.createElement('option');
                        opt.value = sector;
                        opt.textContent = sector;
                        sectorFilter.appendChild(opt);
                    });

                    // 5. Stocks Table
                    const stocksTbody = document.getElementById('stocks-tbody');
                    stocksTbody.innerHTML = data.stocks.map(stock => {
                        const indices = stock.indices || [];
                        // Agrupa os selos: linha1 = ticker + 1o indice, demais = pares
                        function tickerHtml(ticker, idxArr) {
                            let h = `<div class="ticker-line"><span class="ticker-symbol">${ticker}</span>`;
                            if (idxArr.length > 0) {
                                h += `<span class="index-pill ${idxArr[0].toLowerCase()}">${idxArr[0]}</span>`;
                            }
                            h += `</div>`;
                            for (let i = 1; i < idxArr.length; i += 2) {
                                h += `<div class="ticker-line">`;
                                h += `<span class="index-pill ${idxArr[i].toLowerCase()}">${idxArr[i]}</span>`;
                                if (i + 1 < idxArr.length) {
                                    h += `<span class="index-pill ${idxArr[i+1].toLowerCase()}">${idxArr[i+1]}</span>`;
                                }
                                h += `</div>`;
                            }
                            return h;
                        }
                        
                        const priceFormatted = stock.price ? `R$ ${stock.price.toFixed(2)}` : 'N/A';
                        const peFormatted = stock.pe_ratio ? stock.pe_ratio.toFixed(2) : 'N/A';
                        const pbFormatted = stock.pb_ratio !== null && stock.pb_ratio !== undefined ? stock.pb_ratio.toFixed(2) : 'N/A';
                        const dyFormatted = stock.dividend_yield ? `${(stock.dividend_yield * 100).toFixed(2)}%` : '0.00%';
                        const roeFormatted = stock.roe ? `${(stock.roe * 100).toFixed(2)}%` : 'N/A';
                        const bazinFormatted = stock.bazin_price ? `R$ ${stock.bazin_price.toFixed(2)}` : 'N/A';
                        const grahamFormatted = stock.graham_price ? `R$ ${stock.graham_price.toFixed(2)}` : 'N/A';
                        
                        const peClass = (stock.pe_ratio && stock.pe_ratio > 0 && stock.pe_ratio <= 15) ? 'positive' : 'warning';
                        const pbClass = (stock.pb_ratio !== null && stock.pb_ratio !== undefined && stock.pb_ratio > 0 && stock.pb_ratio <= 1.5) ? 'positive' : 'warning';
                        const dyClass = (stock.dividend_yield && stock.dividend_yield >= 0.06) ? 'positive' : 'negative';
                        const roeClass = (stock.roe && stock.roe >= 0.10) ? 'positive' : 'negative';
                        const bazinClass = (stock.price && stock.bazin_price && stock.price < stock.bazin_price) ? 'positive' : '';
                        const grahamClass = (stock.price && stock.graham_price && stock.price < stock.graham_price) ? 'positive' : '';
                        
                        return `
                        <tr onclick="openDetailModal('${stock.ticker}', 'stock')" data-ticker="${stock.ticker}"
                            data-name="${stock.name}" data-sector="${stock.sector}"
                            data-indices="${(stock.indices || []).join(',')}"
                            data-price="${stock.price || 0}"
                            data-pe="${stock.pe_ratio !== null ? stock.pe_ratio : 'null'}"
                            data-pb="${stock.pb_ratio !== null ? stock.pb_ratio : 'null'}"
                            data-dy="${stock.dividend_yield || 0}"
                            data-roe="${stock.roe !== null ? stock.roe : 'null'}"
                            data-bazin="${stock.bazin_price || 0}"
                            data-graham="${stock.graham_price || 0}"
                            data-score="${stock.score || 0}"
                            data-eps="${stock.eps !== null ? stock.eps : 'null'}"
                            data-vpa="${stock.book_value !== null ? stock.book_value : 'null'}"
                            data-breakdown='${JSON.stringify(stock.score_breakdown || []).replace(/'/g, "&apos;")}'
                            data-history='${stock.history_json || "[]"}'>
                            <td class="ticker-cell">
                                ${tickerHtml(stock.ticker, indices)}
                            </td>
                            <td class="name-cell" title="${(stock.name || '').replace(/"/g, '&quot;')}">${stock.name}</td>
                            <td title="${(stock.sector || '').replace(/"/g, '&quot;')}">${stock.sector}</td>
                            <td>${priceFormatted}</td>
                            <td class="sparkline-cell">${generateSparklineSvg(stock.history_json)}</td>
                            <td>${stock.book_value ? `R$ ${stock.book_value.toFixed(2)}` : 'N/A'}</td>
                            <td class="${peClass}">${peFormatted}</td>
                            <td class="${pbClass}">${pbFormatted}</td>
                            <td class="${dyClass}">${dyFormatted}</td>
                            <td class="${roeClass}">${roeFormatted}</td>
                            <td class="${bazinClass}">${bazinFormatted}</td>
                            <td class="${grahamClass}">${grahamFormatted}</td>
                            <td>
                        <span class="score-pill ${getScoreRangeClass(stock.score)}">${formatScore(stock.score)}</span>
                            </td>
                        </tr>`;
                    }).join('');

                    // 6. FIIs Table
                    const fiisTbody = document.getElementById('fiis-tbody');
                    fiisTbody.innerHTML = data.fiis.map(fii => {
                        const priceFormatted = fii.price ? `R$ ${fii.price.toFixed(2)}` : 'N/A';
                        const pbFormatted = fii.pb_ratio !== null && fii.pb_ratio !== undefined ? fii.pb_ratio.toFixed(2) : 'N/A';
                        const dyFormatted = fii.dividend_yield ? `${(fii.dividend_yield * 100).toFixed(2)}%` : '0.00%';
                        const rateFormatted = fii.dividend_rate ? `R$ ${fii.dividend_rate.toFixed(2)}` : '0.00';
                        
                        const pbClass = (fii.pb_ratio !== null && fii.pb_ratio !== undefined && fii.pb_ratio >= 0.7 && fii.pb_ratio <= 1.05) ? 'positive' : 'warning';
                        const dyClass = (fii.dividend_yield && fii.dividend_yield >= 0.08) ? 'positive' : 'warning';
                        
                        return `
                        <tr onclick="openDetailModal('${fii.ticker}', 'fii')" data-ticker="${fii.ticker}"
                            data-name="${fii.name}" data-price="${fii.price || 0}"
                            data-pb="${fii.pb_ratio !== null ? fii.pb_ratio : 'null'}"
                            data-dy="${fii.dividend_yield || 0}"
                            data-rate="${fii.dividend_rate || 0}"
                            data-score="${fii.score || 0}"
                            data-vpa="${fii.book_value !== null ? fii.book_value : 'null'}"
                            data-consistency="${fii.dividend_consistency !== null && fii.dividend_consistency !== undefined ? fii.dividend_consistency : ''}"
                            data-breakdown='${JSON.stringify(fii.score_breakdown || []).replace(/'/g, "&apos;")}'
                            data-history='${fii.history_json || "[]"}'>
                            <td class="ticker-cell">${fii.ticker}</td>
                            <td class="name-cell" title="${(fii.name || '').replace(/"/g, '&quot;')}">${fii.name}</td>
                            <td>${priceFormatted}</td>
                            <td class="sparkline-cell">${generateSparklineSvg(fii.history_json)}</td>
                            <td>${fii.book_value ? `R$ ${fii.book_value.toFixed(2)}` : 'N/A'}</td>
                            <td class="${pbClass}">${pbFormatted}</td>
                            <td class="${dyClass}">${dyFormatted}</td>
                            <td>${rateFormatted}</td>
                            <td>
                                <span class="score-pill ${getScoreRangeClass(fii.score)}">${formatScore(fii.score)}</span>
                            </td>
                        </tr>`;
                    }).join('');

                    // 7. FIAGROs Table
                    const fiagrosTbody = document.getElementById('fiagros-tbody');
                    fiagrosTbody.innerHTML = data.fiagros.map(fiagro => {
                        const priceFormatted = fiagro.price ? `R$ ${fiagro.price.toFixed(2)}` : 'N/A';
                        const pbFormatted = fiagro.pb_ratio !== null && fiagro.pb_ratio !== undefined ? fiagro.pb_ratio.toFixed(2) : 'N/A';
                        const dyFormatted = fiagro.dividend_yield ? `${(fiagro.dividend_yield * 100).toFixed(2)}%` : '0.00%';
                        const rateFormatted = fiagro.dividend_rate ? `R$ ${fiagro.dividend_rate.toFixed(2)}` : '0.00';
                        
                        const pbClass = (fiagro.pb_ratio !== null && fiagro.pb_ratio !== undefined && fiagro.pb_ratio >= 0.7 && fiagro.pb_ratio <= 1.05) ? 'positive' : 'warning';
                        const dyClass = (fiagro.dividend_yield && fiagro.dividend_yield >= 0.10) ? 'positive' : 'warning';
                        
                        return `
                        <tr onclick="openDetailModal('${fiagro.ticker}', 'fiagro')" data-ticker="${fiagro.ticker}"
                            data-name="${fiagro.name}" data-price="${fiagro.price || 0}"
                            data-pb="${fiagro.pb_ratio !== null ? fiagro.pb_ratio : 'null'}"
                            data-dy="${fiagro.dividend_yield || 0}"
                            data-rate="${fiagro.dividend_rate || 0}"
                            data-score="${fiagro.score || 0}"
                            data-vpa="${fiagro.book_value !== null ? fiagro.book_value : 'null'}"
                            data-consistency="${fiagro.dividend_consistency !== null && fiagro.dividend_consistency !== undefined ? fiagro.dividend_consistency : ''}"
                            data-breakdown='${JSON.stringify(fiagro.score_breakdown || []).replace(/'/g, "&apos;")}'
                            data-history='${fiagro.history_json || "[]"}'>
                            <td class="ticker-cell">${fiagro.ticker}</td>
                            <td class="name-cell" title="${(fiagro.name || '').replace(/"/g, '&quot;')}">${fiagro.name}</td>
                            <td>${priceFormatted}</td>
                            <td class="sparkline-cell">${generateSparklineSvg(fiagro.history_json)}</td>
                            <td>${fiagro.book_value ? `R$ ${fiagro.book_value.toFixed(2)}` : 'N/A'}</td>
                            <td class="${pbClass}">${pbFormatted}</td>
                            <td class="${dyClass}">${dyFormatted}</td>
                            <td>${rateFormatted}</td>
                            <td>
                                <span class="score-pill ${getScoreRangeClass(fiagro.score)}">${formatScore(fiagro.score)}</span>
                            </td>
                        </tr>`;
                    }).join('');

                    // 8. Sectors Summary Table
                    const sectorsTbody = document.getElementById('sectors-tbody');
                    sectorsTbody.innerHTML = data.sectors_summary.map(sector => {
                        const avgPeFormatted = sector.avg_pe ? sector.avg_pe.toFixed(2) : 'N/A';
                        
                        return `
                        <tr onclick="openSectorDetailModal('${sector.name}')" style="cursor: pointer;">
                            <td class="name-cell" style="font-weight: 600;" title="${(sector.name || '').replace(/"/g, '&quot;')}">${sector.name}</td>
                            <td>${sector.count}</td>
                            <td>
                                <span class="score-pill ${getScoreRangeClass(sector.avg_score)}">${formatScore(sector.avg_score)}</span>
                            </td>
                            <td class="positive">${sector.avg_dy}%</td>
                            <td>${avgPeFormatted}</td>
                        </tr>`;
                    }).join('');

                    renderIndicesSummaryTable(data);

                    // Initialize optional modules without blocking the rest of the UI.
                    // The compare module is not present in every generated artifact;
                    // a missing optional initializer must not prevent URL deep links
                    // (for example #tab=glossary) from being applied.
                    if (typeof initCompareModule === 'function') {
                        initCompareModule();
                    }
                    populateCalculatorSelects();
                    renderGlobalPanel(data);
                    if (typeof checkRefreshStatus === 'function') checkRefreshStatus();
                    filterTable();
                    syncStateFromUrl();
                });
        }

        /* ── v3 Helper Functions ── */

        function getTrendIcon(trend) {
            if (!trend) return '→';
            var t = String(trend).toLowerCase();
            if (t === 'up' || t === 'subindo' || t === 'alta') return '↑';
            if (t === 'down' || t === 'baixa' || t === 'queda') return '↓';
            return '→';
        }

        function formatPercent(value) {
            if (value == null || isNaN(value)) return '—';
            return Number(value).toFixed(2) + '%';
        }

        function formatFocusArray(arr, isPercent, isCurrency, currentYear) {
            if (!arr || arr.length === 0) return '—';
            return arr.map((v, i) => {
                if (v == null) return '—';
                const year = currentYear + i;
                const formattedVal = isPercent ? (v * 100).toFixed(2) + '%' : isCurrency ? 'R$ ' + v.toFixed(2) : v;
                return `${year}: <strong>${formattedVal}</strong>`;
            }).join(' · ');
        }

        /**
         * Renderiza a lista de Top Picks em um container, a partir de itens normalizados.
         * Cada item pode ter _type: 'stock' | 'fii' | 'fiagro' | 'tesouro'.
         * Stocks/FIIs/FIAGROs exibem DY e P/VP (se disponível).
         * Tesouro exibe yield e maturity.
         * O score é SEMPRE exibido no badge .home-pick-score, nunca no detail text.
         */
        function renderTopPicks(container, items) {
            if (!container) return;
            if (!items || items.length === 0) {
                container.innerHTML = '<div style="font-size:0.8rem;color:var(--text-muted);padding:0.3rem 0;">Nenhum destaque</div>';
                return;
            }
            container.innerHTML = items.map(function(item) {
                var ticker = item.ticker || item.symbol || '—';
                var score = item.score != null ? item.score : 0;
                var detail = '';
                var onclick = '';
                var extraStyle = '';

                if (item._type === 'tesouro') {
                    ticker = item.name || item.ticker || '—';
                    var maturity = item.days_to_maturity ? (item.days_to_maturity + 'd') : (item.maturity_date || '');
                    detail = formatTdYield(item, false) + '% a.a. \u00B7 ' + maturity;
                    var safeName = ticker.replace(/'/g, "\\'");
                    onclick = "openTdDetailFromHome('" + safeName + "')";
                    extraStyle = 'cursor:pointer;';
                } else {
                    var dy = item.dividend_yield || 0;
                    var pb = item.pb_ratio;
                    detail = 'DY ' + (dy * 100).toFixed(2) + '%';
                    if (pb != null) detail += ' \u00B7 P/VP ' + pb.toFixed(2);
                    var type = item._type || 'stock';
                    onclick = "openDetailModal('" + ticker + "', '" + type + "')";
                }

                return '<div class="home-pick-item home-pick-' + (item._type || 'stock') + '" onclick="' + onclick + '" style="' + extraStyle + '">' +
                    '<span class="home-pick-ticker">' + ticker + '</span>' +
                    '<span class="home-pick-detail">' + detail + '</span>' +
                    '<span class="home-pick-score score-pill ' + getScoreRangeClass(score) + '" style="font-size:0.75rem;height:1.5rem;min-width:1.5rem;">' + formatScore(score) + '</span>' +
                '</div>';
            }).join('');
        }

        function renderHomePanel(data) {
            // ---- Macro State ----
            const macro = data.macro_state;
            if (macro) {
                let currentYear = new Date().getFullYear();
                if (macro.fetched_at) {
                    const yr = parseInt(macro.fetched_at.substring(0, 4), 10);
                    if (!isNaN(yr)) currentYear = yr;
                }

                // ── Helper: current value from history ──
                function _currentFromHistory(historyKey, indicator) {
                    const rows = macro[historyKey];
                    if (!rows || rows.length === 0) return null;
                    // IPCA (SIDRA v/2265): cada valor já é acumulado 12 meses — pega o último
                    // Selic Meta (SGS 432): último valor da meta vigente
                    // Câmbio (SGS 1): última cotação
                    const last = rows[rows.length - 1];
                    return last ? last.value : null;
                }
                function _fmtFocusYear(arr, i, isPct, isCur) {
                    if (!arr || arr[i] == null) return '—';
                    const v = isPct ? (arr[i] * 100).toFixed(2) + '%' : isCur ? 'R$ ' + arr[i].toFixed(2) : arr[i];
                    return v;
                }

                // ── Selic ──
                const selicEl = document.getElementById('macro-selic');
                const selicTrendEl = document.getElementById('macro-selic-trend');
                const selicFocusEl = document.getElementById('macro-selic-focus');
                const selicExpectEl = document.getElementById('macro-selic-expect');
                // Big value: Selic Meta (COPOM). Fallback: Selic Over efetiva.
                const selicMeta = macro.selic_meta || macro.selic;
                if (selicEl) selicEl.textContent = selicMeta != null ? (selicMeta * 100).toFixed(2) + '%' : '—';
                if (selicTrendEl) {
                    var selicTrend = 'stable';
                    if (macro.focus_selic && macro.focus_selic[0] != null && selicMeta != null) {
                        selicTrend = macro.focus_selic[0] > selicMeta ? 'up' : macro.focus_selic[0] < selicMeta ? 'down' : 'stable';
                    }
                    var icon = getTrendIcon(selicTrend);
                    selicTrendEl.textContent = icon + ' Selic';
                    selicTrendEl.className = 'macro-trend ' + selicTrend;
                }
                if (selicExpectEl && macro.focus_selic && macro.focus_selic[0] != null) {
                    selicExpectEl.textContent = '→ Focus ' + currentYear + ': ' + (macro.focus_selic[0] * 100).toFixed(2) + '%';
                }
                // Sub: mostra Selic Over efetiva + Focus array
                if (selicFocusEl) {
                    var selicOverStr = macro.selic != null ? 'Over ' + (macro.selic * 100).toFixed(2) + '%' : '';
                    var focusHtml = formatFocusArray(macro.focus_selic, true, false, currentYear);
                    selicFocusEl.innerHTML = selicOverStr ? selicOverStr + ' · ' + focusHtml : focusHtml;
                }

                // ── IPCA ──
                const ipcaEl = document.getElementById('macro-ipca');
                const ipcaTrendEl = document.getElementById('macro-ipca-trend');
                const ipcaFocusEl = document.getElementById('macro-ipca-focus');
                const ipcaExpectEl = document.getElementById('macro-ipca-expect');
                const ipcaCurrent = _currentFromHistory('IPCA_HISTORY', 'ipca');
                const ipcaFocusVal = macro.focus_ipca && macro.focus_ipca.length > 0 ? macro.focus_ipca[0] : null;
                // Big value: IPCA acum. 12m real (se disponível), senão Focus
                if (ipcaEl) {
                    ipcaEl.textContent = ipcaCurrent != null ? (ipcaCurrent * 100).toFixed(2) + '%' :
                                         ipcaFocusVal != null ? (ipcaFocusVal * 100).toFixed(2) + '%' : '—';
                }
                if (ipcaTrendEl) {
                    var trend = macro.focus_ipca_trend || 'stable';
                    var icon = getTrendIcon(trend);
                    var trendClass = trend === 'up' || trend === 'subindo' || trend === 'alta' ? 'up' :
                                     trend === 'down' || trend === 'baixa' || trend === 'queda' ? 'down' : 'stable';
                    ipcaTrendEl.textContent = icon + ' IPCA';
                    ipcaTrendEl.className = 'macro-trend ' + trendClass;
                }
                if (ipcaExpectEl && ipcaFocusVal != null) {
                    ipcaExpectEl.textContent = '→ Focus ' + currentYear + ': ' + (ipcaFocusVal * 100).toFixed(2) + '%';
                }
                if (ipcaFocusEl) {
                    // Mostra YTD + Focus no subtítulo
                    var ipcaYtdVal = null;
                    if (macro.IPCA_YTD_HISTORY && macro.IPCA_YTD_HISTORY.length > 0) {
                        ipcaYtdVal = macro.IPCA_YTD_HISTORY[macro.IPCA_YTD_HISTORY.length - 1].value;
                    }
                    var ytdHtml = ipcaYtdVal != null ? 'YTD: <strong>' + (ipcaYtdVal * 100).toFixed(2) + '%</strong> · ' : '';
                    var focusHtml = formatFocusArray(macro.focus_ipca, true, false, currentYear);
                    ipcaFocusEl.innerHTML = ytdHtml + 'Focus: ' + focusHtml;
                }

                // ── Câmbio ──
                const cambioEl = document.getElementById('macro-cambio');
                const cambioFocusEl = document.getElementById('macro-cambio-focus');
                const cambioExpectEl = document.getElementById('macro-cambio-expect');
                const cambioCurrent = _currentFromHistory('CAMBIO_HISTORY', 'cambio');
                const cambioFocusVal = macro.focus_cambio && macro.focus_cambio.length > 0 ? macro.focus_cambio[0] : null;
                // Big value: câmbio atual (se disponível), senão Focus
                if (cambioEl) {
                    cambioEl.textContent = cambioCurrent != null ? 'R$ ' + cambioCurrent.toFixed(2) :
                                           cambioFocusVal != null ? 'R$ ' + cambioFocusVal.toFixed(2) : '—';
                }
                if (cambioExpectEl && cambioFocusVal != null) {
                    cambioExpectEl.textContent = '→ Focus ' + currentYear + ': R$ ' + cambioFocusVal.toFixed(2);
                }
                if (cambioFocusEl) {
                    cambioFocusEl.innerHTML = formatFocusArray(macro.focus_cambio, false, true, currentYear);
                }

                // Timestamp
                const homeTs = document.getElementById('home-timestamp');
                if (homeTs && macro.fetched_at) {
                    const focusOfficial = macro.data_sources?.focus === 'bcb_expectativas_odata';
                    let formattedMacroTs = macro.fetched_at;
                    try {
                        const d = new Date(macro.fetched_at);
                        if (!isNaN(d.getTime())) {
                            formattedMacroTs = d.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });
                        }
                    } catch (e) {}
                    homeTs.textContent = 'Atualizado em: ' + formattedMacroTs +
                        (focusOfficial ? ' · Focus: BCB/OData' : ' · ⚠️ Focus indisponível');
                }
            }

            // ---- Top Picks ----
            const home = data.home || {};

            // Top Global Interclasses (Top 5 Absoluto de Todas as Classes)
            var allGlobalItems = []
                .concat((data.stocks || []).map(function(s) { return Object.assign({}, s, { _type: 'stock' }); }))
                .concat((data.fiis || []).map(function(f) { return Object.assign({}, f, { _type: 'fii' }); }))
                .concat((data.fiagros || []).map(function(g) { return Object.assign({}, g, { _type: 'fiagro' }); }))
                .concat((data.tesouro_direto || []).filter(function(td) { return isTdAvailableForPurchase(td, true); }).map(function(t) { return Object.assign({}, t, { _type: 'tesouro' }); }));

            allGlobalItems.sort(function(a, b) { return (b.score || 0) - (a.score || 0); });

            renderTopPicks(document.getElementById('home-top-global'),
                allGlobalItems.slice(0, 5)
            );

            // Top Stocks
            renderTopPicks(document.getElementById('home-top-stocks'),
                (home.top_stocks || data.top_stocks || []).slice(0, 5).map(function(s) {
                    return Object.assign({}, s, { _type: 'stock' });
                })
            );

            // Top FIIs
            renderTopPicks(document.getElementById('home-top-fiis'),
                (home.top_fiis || data.top_fiis || []).slice(0, 5).map(function(s) {
                    return Object.assign({}, s, { _type: 'fii' });
                })
            );

            // Top FIAGROs (with card visibility)
            var fiagroItems = (home.top_fiagros || data.top_fiagros || []).slice(0, 5).map(function(s) {
                return Object.assign({}, s, { _type: 'fiagro' });
            });
            var homeFiagrosCard = document.getElementById('home-top-fiagros-card');
            if (homeFiagrosCard) {
                homeFiagrosCard.style.display = fiagroItems.length === 0 ? 'none' : '';
            }
            renderTopPicks(document.getElementById('home-top-fiagros'), fiagroItems);

            // Top Tesouro Direto
            renderTopPicks(document.getElementById('home-top-tesouro'),
                (home.top_tesouro || []).filter(function(td) { return isTdAvailableForPurchase(td, true); }).slice(0, 5).map(function(s) {
                    return Object.assign({}, s, { _type: 'tesouro' });
                })
            );
        }

        let globalSortKey = 'score';
        let globalSortAsc = false;
        let currentGlobalFilter = 'all';

        function filterGlobalClass(filterType) {
            currentGlobalFilter = filterType;
            const btnIds = ['all', 'premium', 'tesouro', 'fii', 'fiagro', 'stock'];
            btnIds.forEach(id => {
                const btn = document.getElementById(`btn-global-filter-${id}`);
                if (btn) {
                    if (id === filterType) btn.classList.add('active');
                    else btn.classList.remove('active');
                }
            });
            if (window.dashboardData) {
                renderGlobalPanel(window.dashboardData);
            }
        }

        function sortGlobalTable(key) {
            if (globalSortKey === key) {
                globalSortAsc = !globalSortAsc;
            } else {
                globalSortKey = key;
                globalSortAsc = key === 'ticker' || key === 'rank';
            }
            if (window.dashboardData) {
                renderGlobalPanel(window.dashboardData);
            }
        }

        function renderGlobalPanel(data) {
            if (!data) return;
            const tbody = document.getElementById('global-tbody');
            const countEl = document.getElementById('global-count');
            if (!tbody) return;

            let items = [];

            // 1. Stocks
            (data.stocks || []).forEach(s => {
                const pe = s.pe_ratio != null ? s.pe_ratio.toFixed(1) + 'x' : 'N/A';
                const pb = s.pb_ratio != null ? s.pb_ratio.toFixed(2) : 'N/A';
                const roe = s.roe != null ? (s.roe * 100).toFixed(1) + '%' : 'N/A';
                const dy = s.dividend_yield != null ? (s.dividend_yield * 100).toFixed(1) + '%' : '0.0%';
                const graham = s.graham_price ? 'R$ ' + s.graham_price.toFixed(2) : '';
                const highlight = graham ? `Graham ${graham} · ROE ${roe}` : `ROE ${roe}`;

                items.push({
                    ticker: s.ticker,
                    name: s.name,
                    type: 'stock',
                    typeLabel: '📈 Ação',
                    priceOrRate: s.price ? 'R$ ' + s.price.toFixed(2) : 'N/A',
                    priceVal: s.price || 0,
                    yield: 'DY ' + dy,
                    yieldVal: s.dividend_yield || 0,
                    metric: `P/VP ${pb} · P/L ${pe}`,
                    metricVal: s.pb_ratio || 0,
                    highlight: highlight,
                    score: s.score || 0,
                    badge: s.score >= 8.0 ? 'premium' : (s.score >= 6.0 ? 'bom' : (s.score >= 4.0 ? 'regular' : 'risco')),
                    raw: s
                });
            });

            // 2. FIIs
            (data.fiis || []).forEach(f => {
                const pb = f.pb_ratio != null ? f.pb_ratio.toFixed(2) : 'N/A';
                const dy = f.dividend_yield != null ? (f.dividend_yield * 100).toFixed(1) + '%' : '0.0%';
                const cons = f.dividend_consistency != null ? (f.dividend_consistency * 100).toFixed(0) + '%' : 'N/D';
                const highlight = `P/VP ${pb} · Retenção ${cons}`;

                items.push({
                    ticker: f.ticker,
                    name: f.name,
                    type: 'fii',
                    typeLabel: '🏢 FII',
                    priceOrRate: f.price ? 'R$ ' + f.price.toFixed(2) : 'N/A',
                    priceVal: f.price || 0,
                    yield: 'DY ' + dy,
                    yieldVal: f.dividend_yield || 0,
                    metric: `P/VP ${pb}`,
                    metricVal: f.pb_ratio || 0,
                    highlight: highlight,
                    score: f.score || 0,
                    badge: f.score >= 8.0 ? 'premium' : (f.score >= 6.0 ? 'bom' : (f.score >= 4.0 ? 'regular' : 'risco')),
                    raw: f
                });
            });

            // 3. FIAGROs
            (data.fiagros || []).forEach(g => {
                const pb = g.pb_ratio != null ? g.pb_ratio.toFixed(2) : 'N/A';
                const dy = g.dividend_yield != null ? (g.dividend_yield * 100).toFixed(1) + '%' : '0.0%';
                const cons = g.dividend_consistency != null ? (g.dividend_consistency * 100).toFixed(0) + '%' : 'N/D';
                const highlight = `Spread Agro · Retenção ${cons}`;

                items.push({
                    ticker: g.ticker,
                    name: g.name,
                    type: 'fiagro',
                    typeLabel: '🌱 FIAGRO',
                    priceOrRate: g.price ? 'R$ ' + g.price.toFixed(2) : 'N/A',
                    priceVal: g.price || 0,
                    yield: 'DY ' + dy,
                    yieldVal: g.dividend_yield || 0,
                    metric: `P/VP ${pb}`,
                    metricVal: g.pb_ratio || 0,
                    highlight: highlight,
                    score: g.score || 0,
                    badge: g.score >= 8.0 ? 'premium' : (g.score >= 6.0 ? 'bom' : (g.score >= 4.0 ? 'regular' : 'risco')),
                    raw: g
                });
            });

            // 4. Tesouro Direto
            (data.tesouro_direto || []).filter(td => isTdAvailableForPurchase(td, true)).forEach(t => {
                const isSelic = t.type === 'Selic' || t.type === 'Reserva';
                const rateFmt = isSelic ? ('Selic ' + (t.buy_yield >= 0 ? '+' : '') + (t.buy_yield * 100).toFixed(4) + '%') : (t.type === 'Prefixado' ? (t.buy_yield * 100).toFixed(2) + '% a.a.' : 'IPCA + ' + (t.buy_yield * 100).toFixed(2) + '%');
                const yieldFmt = isSelic ? 'Pós-fixado Selic' : (t.type === 'Prefixado' ? 'Prefixado Nominal' : 'Juro Real ' + (t.buy_yield * 100).toFixed(2) + '%');
                const perc = t.historical_yield_percentile != null ? 'P' + t.historical_yield_percentile + ' STN' : 'STN';
                const days = t.days_to_maturity ? t.days_to_maturity + 'd' : '';
                const highlight = isSelic ? 'Reserva de Liquidez' : `VNA Soberano · ${perc} · ${days}`;

                items.push({
                    ticker: t.name,
                    name: t.name,
                    type: 'tesouro',
                    typeLabel: '🪙 Tesouro',
                    priceOrRate: rateFmt,
                    priceVal: t.buy_yield || 0,
                    yield: yieldFmt,
                    yieldVal: t.buy_yield || 0,
                    metric: perc,
                    metricVal: t.historical_yield_percentile || 0,
                    highlight: highlight,
                    score: t.score || 0,
                    badge: t.badge || (t.score >= 8.0 ? 'premium' : (t.score >= 6.0 ? 'bom' : (t.score >= 4.0 ? 'regular' : 'risco'))),
                    raw: t
                });
            });

            // Filter
            if (currentGlobalFilter === 'premium') {
                items = items.filter(i => i.score >= 8.0);
            } else if (currentGlobalFilter !== 'all') {
                items = items.filter(i => i.type === currentGlobalFilter);
            }

            // Sort
            items.sort((a, b) => {
                let valA, valB;
                if (globalSortKey === 'rank' || globalSortKey === 'score') {
                    valA = a.score;
                    valB = b.score;
                } else if (globalSortKey === 'ticker') {
                    valA = a.ticker;
                    valB = b.ticker;
                    return globalSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
                } else if (globalSortKey === 'type') {
                    valA = a.type;
                    valB = b.type;
                    return globalSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
                } else if (globalSortKey === 'price') {
                    valA = a.priceVal;
                    valB = b.priceVal;
                } else if (globalSortKey === 'yield') {
                    valA = a.yieldVal;
                    valB = b.yieldVal;
                } else if (globalSortKey === 'metric') {
                    valA = a.metricVal;
                    valB = b.metricVal;
                } else if (globalSortKey === 'badge') {
                    valA = a.score;
                    valB = b.score;
                } else {
                    valA = a.score;
                    valB = b.score;
                }
                return globalSortAsc ? valA - valB : valB - valA;
            });

            if (countEl) {
                countEl.textContent = `${items.length} ${items.length === 1 ? 'ativo' : 'ativos'}`;
            }

            tbody.innerHTML = items.map((item, idx) => {
                const rank = idx + 1;
                const badgeClass = getScoreRangeClass(item.score);
                const badgeLabel = item.badge === 'premium' || item.score >= 8.0 ? 'PREMIUM' : (item.badge === 'bom' || item.score >= 6.0 ? 'BOM' : (item.badge === 'regular' || item.score >= 4.0 ? 'REGULAR' : 'RISCO'));
                let onclick = '';
                if (item.type === 'tesouro') {
                    const safeName = item.name.replace(/'/g, "\\'");
                    onclick = `openTdDetailFromHome('${safeName}')`;
                } else {
                    onclick = `openDetailModal('${item.ticker}', '${item.type}')`;
                }

                const typeBadgeStyle = item.type === 'stock' ? 'background:rgba(59,130,246,0.15);color:var(--primary);' :
                    item.type === 'fii' ? 'background:rgba(16,185,129,0.15);color:var(--accent-green);' :
                    item.type === 'fiagro' ? 'background:rgba(245,158,11,0.15);color:var(--accent-gold);' :
                    'background:rgba(139,92,246,0.15);color:#a78bfa;';

                return `
                <tr onclick="${onclick}" style="cursor:pointer;">
                    <td style="font-weight:700; color:var(--text-muted); width:45px;">#${rank}</td>
                    <td>
                        <div style="font-weight:700; color:var(--text-primary);">${item.ticker}</div>
                        <div class="name-cell" title="${(item.name || '').replace(/"/g, '&quot;')}" style="font-size:0.75rem; color:var(--text-muted); max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; cursor:help;">${item.name}</div>
                    </td>
                    <td>
                        <span style="font-size:0.75rem; padding:0.2rem 0.5rem; border-radius:6px; font-weight:600; display:inline-block; ${typeBadgeStyle}">
                            ${item.typeLabel}
                        </span>
                    </td>
                    <td style="font-weight:600;">${item.priceOrRate}</td>
                    <td class="positive" style="font-weight:600;">${item.yield}</td>
                    <td style="font-size:0.85rem;">${item.metric}</td>
                    <td style="font-size:0.8rem; color:var(--text-secondary);">${item.highlight}</td>
                    <td>
                        <span class="score-pill ${badgeClass}">${formatScore(item.score)}</span>
                    </td>
                    <td>
                        <span class="td-badge ${item.badge || 'regular'}">${badgeLabel}</span>
                    </td>
                </tr>`;
            }).join('');
        }

        function isTdAvailableForPurchase(td, allowSummary) {
            if (!td || td.purchase_available === false || td.availability_status === 'unavailable') return false;
            if (td.availability_status && td.availability_status !== 'available') return false;
            return Number.isFinite(Number(td.buy_yield)) &&
                Number(td.days_to_maturity) > 0 &&
                (Number.isFinite(Number(td.buy_price)) || Boolean(allowSummary && td.buy_price === undefined));
        }

        function renderRendaFixaPanel(data) {
            // ---- Macro Cards (rendafixa) ----
            const macro = data.macro_state;
            if (macro) {
                let currentYear = new Date().getFullYear();
                if (macro.fetched_at) {
                    const yr = parseInt(macro.fetched_at.substring(0, 4), 10);
                    if (!isNaN(yr)) currentYear = yr;
                }
                function _rfCurrentFromHistory(historyKey, indicator) {
                    const rows = macro[historyKey];
                    if (!rows || rows.length === 0) return null;
                    // IPCA (SIDRA v/2265): cada valor já é acumulado 12 meses
                    const last = rows[rows.length - 1];
                    return last ? last.value : null;
                }
                const selicEl = document.getElementById('rendafixa-macro-selic');
                const selicTrendEl = document.getElementById('rendafixa-macro-selic-trend');
                const selicFocusEl = document.getElementById('rendafixa-macro-selic-focus');
                const selicExpectEl = document.getElementById('rendafixa-macro-selic-expect');
                const selicMeta = macro.selic_meta || macro.selic;
                if (selicEl) selicEl.textContent = selicMeta != null ? (selicMeta * 100).toFixed(2) + '%' : '—';
                if (selicTrendEl) {
                    var selicTrend = 'stable';
                    if (macro.focus_selic && macro.focus_selic[0] != null && selicMeta != null) {
                        selicTrend = macro.focus_selic[0] > selicMeta ? 'up' : macro.focus_selic[0] < selicMeta ? 'down' : 'stable';
                    }
                    var icon = getTrendIcon(selicTrend);
                    selicTrendEl.textContent = icon + ' Selic';
                    selicTrendEl.className = 'macro-trend ' + selicTrend;
                }
                if (selicExpectEl && macro.focus_selic && macro.focus_selic[0] != null) {
                    selicExpectEl.textContent = '→ Focus ' + currentYear + ': ' + (macro.focus_selic[0] * 100).toFixed(2) + '%';
                }
                if (selicFocusEl) {
                    var selicOverStr = macro.selic != null ? 'Over ' + (macro.selic * 100).toFixed(2) + '%' : '';
                    var focusHtml = formatFocusArray(macro.focus_selic, true, false, currentYear);
                    selicFocusEl.innerHTML = selicOverStr ? selicOverStr + ' · ' + focusHtml : focusHtml;
                }
                const ipcaEl = document.getElementById('rendafixa-macro-ipca');
                const ipcaTrendEl = document.getElementById('rendafixa-macro-ipca-trend');
                const ipcaFocusEl = document.getElementById('rendafixa-macro-ipca-focus');
                const ipcaExpectEl = document.getElementById('rendafixa-macro-ipca-expect');
                const ipcaCurrent = _rfCurrentFromHistory('IPCA_HISTORY', 'ipca');
                const ipcaFocusVal = macro.focus_ipca && macro.focus_ipca.length > 0 ? macro.focus_ipca[0] : null;
                if (ipcaEl) {
                    ipcaEl.textContent = ipcaCurrent != null ? (ipcaCurrent * 100).toFixed(2) + '%' :
                                         ipcaFocusVal != null ? (ipcaFocusVal * 100).toFixed(2) + '%' : '—';
                }
                if (ipcaTrendEl) {
                    var trend = macro.focus_ipca_trend || 'stable';
                    var icon = getTrendIcon(trend);
                    var trendClass = trend === 'up' || trend === 'subindo' || trend === 'alta' ? 'up' :
                                     trend === 'down' || trend === 'baixa' || trend === 'queda' ? 'down' : 'stable';
                    ipcaTrendEl.textContent = icon + ' IPCA';
                    ipcaTrendEl.className = 'macro-trend ' + trendClass;
                }
                if (ipcaExpectEl && ipcaFocusVal != null) {
                    ipcaExpectEl.textContent = '→ Focus ' + currentYear + ': ' + (ipcaFocusVal * 100).toFixed(2) + '%';
                }
                if (ipcaFocusEl) {
                    // Mostra YTD + Focus no subtítulo
                    var ipcaYtdVal = null;
                    if (macro.IPCA_YTD_HISTORY && macro.IPCA_YTD_HISTORY.length > 0) {
                        ipcaYtdVal = macro.IPCA_YTD_HISTORY[macro.IPCA_YTD_HISTORY.length - 1].value;
                    }
                    var ytdHtml = ipcaYtdVal != null ? 'YTD: <strong>' + (ipcaYtdVal * 100).toFixed(2) + '%</strong> · ' : '';
                    var focusHtml = formatFocusArray(macro.focus_ipca, true, false, currentYear);
                    ipcaFocusEl.innerHTML = ytdHtml + 'Focus: ' + focusHtml;
                }
                const cambioEl = document.getElementById('rendafixa-macro-cambio');
                const cambioFocusEl = document.getElementById('rendafixa-macro-cambio-focus');
                const cambioExpectEl = document.getElementById('rendafixa-macro-cambio-expect');
                const cambioCurrent = _rfCurrentFromHistory('CAMBIO_HISTORY', 'cambio');
                const cambioFocusVal = macro.focus_cambio && macro.focus_cambio.length > 0 ? macro.focus_cambio[0] : null;
                if (cambioEl) {
                    cambioEl.textContent = cambioCurrent != null ? 'R$ ' + cambioCurrent.toFixed(2) :
                                           cambioFocusVal != null ? 'R$ ' + cambioFocusVal.toFixed(2) : '—';
                }
                if (cambioExpectEl && cambioFocusVal != null) {
                    cambioExpectEl.textContent = '→ Focus ' + currentYear + ': R$ ' + cambioFocusVal.toFixed(2);
                }
                if (cambioFocusEl) {
                    cambioFocusEl.innerHTML = formatFocusArray(macro.focus_cambio, false, true, currentYear);
                }
            }

            // ---- Tesouro Direto Table ----
            const tdData = (data.tesouro_direto || []).filter(isTdAvailableForPurchase).slice();
            tdData.sort(function(a, b) {
                const badgeOrder = { premium: 4, bom: 3, regular: 2, baixa_oportunidade: 1 };
                const sortable = {
                    rank: function(item) { return Number(item.general_rank) || Number.MAX_SAFE_INTEGER; },
                    title: function(item) { return item.name || ''; },
                    group: function(item) { return item.group || item.type || ''; },
                    yield: function(item) { return Number(item.buy_yield); },
                    percentile: function(item) { return Number(item.historical_yield_percentile); },
                    maturity: function(item) { return item.maturity_date || ''; },
                    score: function(item) { return Number(item.score); },
                    badge: function(item) { return badgeOrder[item.badge] || 0; }
                };
                const valueA = sortable[rendaFixaSort.key](a);
                const valueB = sortable[rendaFixaSort.key](b);
                const comparison = typeof valueA === 'string'
                    ? valueA.localeCompare(valueB, 'pt-BR')
                    : (Number.isFinite(valueA) ? valueA : -Infinity) - (Number.isFinite(valueB) ? valueB : -Infinity);
                return rendaFixaSort.ascending ? comparison : -comparison;
            });
            document.querySelectorAll('[data-td-sort-key]').forEach(function(header) {
                const active = header.dataset.tdSortKey === rendaFixaSort.key;
                header.setAttribute('aria-sort', active ? (rendaFixaSort.ascending ? 'ascending' : 'descending') : 'none');
            });
            const tbody = document.getElementById('rendafixa-tbody');
            const countEl = document.getElementById('rendafixa-count');
            const sourceEl = document.getElementById('rendafixa-source');
            if (sourceEl) {
                const source = data.macro_state?.data_sources?.tesouro_direto;
                const availabilitySource = tdData[0]?.purchase_availability_source;
                sourceEl.textContent = source === 'demo_fallback'
                    ? '⚠️ Dados demonstrativos: a fonte do Tesouro Direto não respondeu nesta atualização.'
                    : availabilitySource === 'tesouro_investir_endpoint'
                        ? 'Fonte: Tesouro Direto. Disponibilidade validada pelo endpoint da página de investir e cotação oficial mais recente.'
                        : 'Fonte: Tesouro Direto. Exibidos apenas títulos com taxa e preço de compra na cotação oficial mais recente.';
            }
            if (tbody) {
                if (tdData.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-secondary);padding:2rem;">Nenhum título disponível</td></tr>';
                    if (countEl) countEl.textContent = '0 títulos';
                } else {
                    tbody.innerHTML = tdData.map(td => {
                        const name = td.name || '—';
                        const tipo = td.type || '—';
                        const yieldStr = formatTdYield(td);
                        const yieldPercentile = td.historical_yield_percentile != null ? 'P' + td.historical_yield_percentile : '—';
                        const maturity = td.maturity_date || (td.days_to_maturity ? td.days_to_maturity + ' dias' : '—');
                        const score = td.score != null ? td.score : 0;
                        const badge = td.badge || '';
                        // Normalize badge to capitalize first letter for display
                        const badgeDisplay = badge.charAt(0).toUpperCase() + badge.slice(1);
                        const badgeLower = badge.toLowerCase();
                        const badgeClass = badgeLower === 'premium' ? 'badge-premium' :
                                           badgeLower === 'bom' ? 'badge-bom' :
                                           badgeLower === 'regular' ? 'badge-regular' :
                                           badgeLower === 'baixa_oportunidade' ? 'badge-alto_risco' : '';
                        const badgeText = { premium: 'Premium', bom: 'Bom', regular: 'Regular', baixa_oportunidade: 'Baixa oportunidade' }[badgeLower] || badgeDisplay;

                        // Score breakdown tooltip
                        let breakdownTip = '';
                        if (td.score_breakdown && td.score_breakdown.length > 0) {
                            breakdownTip = td.score_breakdown.map(function(b) { return b.label + ': ' + b.score.toFixed(2) + '/' + b.max.toFixed(1); }).join(' | ');
                        }

                        const tdJson = encodeURIComponent(JSON.stringify(td));
                        const generalRank = td.general_rank ? '#' + td.general_rank : (td.planning_rank ? 'P' + td.planning_rank : '');
                        const group = td.group || tipo;
                        const groupRank = (td.group_rank ? '<br><small>#' + td.group_rank + ' no grupo</small>' : '') +
                            (td.risk_profile ? '<br><small title="Risco de oscilação em venda antecipada; separado do score de oportunidade.">Risco: ' + td.risk_profile + '</small>' : '');
                        return '<tr onclick="openTdDetailModal(\'' + tdJson + '\')" style="cursor:pointer;" title="' + breakdownTip.replace(/"/g, '&quot;') + '">' +
                            '<td class="font-mono tabular td-rank-cell" style="font-weight:600;">' + generalRank + '</td>' +
                            '<td class="name-cell" style="font-weight:600;" title="' + (name || '').replace(/"/g, '&quot;') + '">' + name + '</td>' +
                            '<td class="td-tipo">' + group + groupRank + '</td>' +
                            '<td class="font-mono tabular" style="font-weight:600;color:var(--positive);">' + yieldStr + '</td>' +
                            '<td class="font-mono tabular" title="Percentil da taxa atual no histórico do título">' + yieldPercentile + '</td>' +
                            '<td class="font-mono tabular" style="font-size:0.8rem;">' + maturity + '</td>' +
                            '<td><span class="score-pill ' + getScoreRangeClass(score) + '" style="font-size:0.75rem;height:1.5rem;min-width:1.5rem;">' + formatScore(score) + '</span></td>' +
                            '<td>' + (badgeClass ? '<span class="' + badgeClass + '">' + badgeText + '</span>' : '—') + '</td>' +
                        '</tr>';
                    }).join('');
                    if (countEl) countEl.textContent = tdData.length + ' título' + (tdData.length !== 1 ? 's' : '');
                }
                if (typeof initTableColumnResizers === 'function') {
                    setTimeout(initTableColumnResizers, 30);
                }
            }

            // ---- ETTJ: cria somente quando o painel puder ser medido ----
            const rendaFixaPanel = document.getElementById('panel-rendafixa');
            if (!rendaFixaPanel || rendaFixaPanel.classList.contains('hidden')) {
                return;
            }
            // A instância é a fonte de verdade. Ao retornar à aba, o Chart.js
            // recalcula o canvas sem recriar nem depender de uma flag antecipada.
            if (window.ettjChartInstance) {
                requestAnimationFrame(function() { window.ettjChartInstance.resize(); });
                return;
            }
            if (macro && macro.ettj_curve) {
                const curveObj = macro.ettj_curve;
                const order = ['1m', '3m', '6m', '1y', '2y', '3y', '5y', '10y', '20y', '30y'];
                const keys = order.filter(function(k) {
                    return curveObj[k] != null && Number.isFinite(Number(curveObj[k]));
                });
                if (keys.length >= 2) {
                    const canvas = document.getElementById('ettj-chart');
                    if (canvas) {
                        const ctx = canvas.getContext('2d');
                        ensureKeyValueLabelsPlugin();
                        const labelMap = { '1m': '1 mês', '3m': '3 meses', '6m': '6 meses', '1y': '1 ano', '2y': '2 anos', '3y': '3 anos', '5y': '5 anos', '10y': '10 anos', '20y': '20 anos', '30y': '30 anos' };
                        const labels = keys.map(function(k) { return labelMap[k] || k; });
                        const values = keys.map(function(k) { return Number(curveObj[k]) * 100; });
                        const minVal = Math.min(...values);
                        const maxVal = Math.max(...values);
                        const range = maxVal - minVal;
                        const padding = Math.max(range * 0.25, 0.4);
                        const yMin = Math.max(0, minVal - padding);
                        const yMax = maxVal + padding;

                        const isLight = !document.body.classList.contains('dark');
                        const gridColor = isLight ? 'rgba(15, 23, 42, 0.06)' : 'rgba(255, 255, 255, 0.05)';
                        const tickColor = isLight ? '#475569' : '#9ca3af';

                        window.ettjChartInstance = new Chart(ctx, {
                            type: 'line',
                            data: {
                                labels: labels,
                                datasets: [{
                                    label: 'Taxa (% a.a.)',
                                    data: values,
                                    borderColor: '#8b5cf6',
                                    backgroundColor: 'rgba(139, 92, 246, 0.08)',
                                    borderWidth: 2.5,
                                    pointRadius: 5,
                                    pointHoverRadius: 7,
                                    pointBackgroundColor: '#8b5cf6',
                                    fill: true,
                                    tension: 0.25
                                }]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                resize: { delay: 50 },
                                plugins: {
                                    legend: { display: false },
                                    tooltip: {
                                        intersect: false,
                                        mode: 'index',
                                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                                        titleFont: { size: 11, weight: '600' },
                                        bodyFont: { size: 13, weight: '700' },
                                        padding: 8,
                                        cornerRadius: 4,
                                        callbacks: {
                                            label: function(context) {
                                                return context.parsed.y.toFixed(2) + '% a.a.';
                                            }
                                        }
                                    },
                                    keyValueLabels: {
                                        format: 'percent',
                                        color: '#8b5cf6',
                                        isLight: isLight,
                                        maxLocalExtrema: 0
                                    },
                                    valueLabels: false
                                },
                                scales: {
                                    x: {
                                        grid: { display: false },
                                        ticks: {
                                            color: tickColor,
                                            maxTicksLimit: 8,
                                            maxRotation: 0,
                                            font: { size: 10, weight: '500', family: 'Inter, sans-serif' }
                                        }
                                    },
                                    y: {
                                        min: parseFloat(yMin.toFixed(2)),
                                        max: parseFloat(yMax.toFixed(2)),
                                        grid: { color: gridColor },
                                        ticks: {
                                            color: tickColor,
                                            maxTicksLimit: 5,
                                            font: { size: 10, family: 'Inter, sans-serif' },
                                            callback: function(value) { return value.toFixed(1) + '%'; }
                                        }
                                    }
                                }
                            }
                        });
                        requestAnimationFrame(function() { window.ettjChartInstance.resize(); });
                    }
                }
            }
        }


        document.addEventListener('DOMContentLoaded', () => {
            initializeSortableHeaders();
            const isDark = document.body.classList.contains('dark');
            const themeIcon = document.getElementById('theme-toggle-icon');
            if (themeIcon) {
                if (isDark) {
                    themeIcon.innerHTML = `<circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>`;
                } else {
                    themeIcon.innerHTML = `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>`;
                }
            }
            // Inicializar label do PDF
            const pdfLabel = document.getElementById('pdf-label');
            if (pdfLabel) {
                const names = { home: 'Home', stocks: 'Ações', fiis: 'FIIs', fiagros: 'FIAGROs', sectors: 'Setores', rendafixa: 'Tesouro Direto' };
                pdfLabel.textContent = names[currentTab] || 'Home';
            }
            loadDashboardData();
        });

        function closeExportMenu() {
            const allMenuIds = ['export-menu', 'modal-export-menu', 'td-modal-export-menu'];
            allMenuIds.forEach(id => {
                const m = document.getElementById(id);
                if (m) {
                    m.style.display = 'none';
                    m.classList.add('hidden');
                }
            });
        }

        function toggleExportMenu(event, menuId) {
            if (event) {
                event.stopPropagation();
            }
            const targetId = menuId || 'export-menu';
            const menu = document.getElementById(targetId);
            if (!menu) return;

            // Close all other export menus first
            const allMenuIds = ['export-menu', 'modal-export-menu', 'td-modal-export-menu'];
            allMenuIds.forEach(id => {
                if (id !== targetId) {
                    const m = document.getElementById(id);
                    if (m) {
                        m.style.display = 'none';
                        m.classList.add('hidden');
                    }
                }
            });

            const isHidden = menu.style.display === 'none' || menu.classList.contains('hidden');
            if (isHidden) {
                menu.style.display = 'block';
                menu.classList.remove('hidden');
            } else {
                menu.style.display = 'none';
                menu.classList.add('hidden');
            }
        }

        // Close export menus on outside click
        document.addEventListener('click', function(e) {
            if (!e.target.closest('.export-dropdown-container') && !e.target.closest('#export-btn') && !e.target.closest('.btn-export-modal')) {
                closeExportMenu();
            }
        });

        function downloadFile(content, fileName, mimeType) {
            const blob = new Blob([content], { type: mimeType });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }

        function showToast(message) {
            let toast = document.getElementById('radar-global-toast');
            if (!toast) {
                toast = document.createElement('div');
                toast.id = 'radar-global-toast';
                toast.className = 'radar-toast';
                document.body.appendChild(toast);
            }
            toast.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                <span>${message}</span>
            `;
            toast.style.display = 'flex';

            if (window._toastTimeout) clearTimeout(window._toastTimeout);
            window._toastTimeout = setTimeout(() => {
                toast.style.display = 'none';
            }, 3500);
        }

        function copyTextToClipboard(text, successMsg) {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    showToast(successMsg || 'Copiado para a área de transferência!');
                }).catch(() => {
                    fallbackCopy(text, successMsg);
                });
            } else {
                fallbackCopy(text, successMsg);
            }
        }

        function fallbackCopy(text, successMsg) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                showToast(successMsg || 'Copiado para a área de transferência!');
            } catch (e) {
                alert('Não foi possível copiar automaticamente.');
            }
            document.body.removeChild(textarea);
        }

        function exportModalData(format) {
            closeExportMenu();

            const ticker = document.getElementById('modal-ticker')?.textContent || 'ATIVO';
            const name = document.getElementById('modal-name')?.textContent || '';
            const asset = window.currentModalAssetData || { ticker: ticker, name: name };

            const typeLabel = asset.type === 'stock' ? 'Ação' : (asset.type === 'fii' ? 'Fundo Imobiliário' : (asset.type === 'fiagro' ? 'FIAGRO' : 'Ativo'));
            const nowStr = new Date().toLocaleDateString('pt-BR');

            if (format === 'json') {
                const jsonData = {
                    ticker: asset.ticker,
                    name: asset.name,
                    type: asset.type,
                    sector: asset.sector || '',
                    export_date: new Date().toISOString(),
                    price: asset.price || 0,
                    score: asset.score || 0,
                    indicators: {
                        pe_ratio: asset.pe,
                        pb_ratio: asset.pb,
                        dividend_yield: asset.dy,
                        roe: asset.roe,
                        graham_price: asset.graham,
                        bazin_price: asset.bazin,
                        eps: asset.eps,
                        vpa: asset.vpa
                    },
                    scorecard_breakdown: asset.breakdown || [],
                    history: asset.history || []
                };
                downloadFile(JSON.stringify(jsonData, null, 2), `${asset.ticker}_radar_fundamentalista.json`, 'application/json;charset=utf-8');
                showToast(`JSON de ${asset.ticker} baixado com sucesso!`);
            } else if (format === 'csv') {
                let csv = [];
                csv.push(`"Métrica","Valor"`);
                csv.push(`"Ticker","${asset.ticker}"`);
                csv.push(`"Nome","${(asset.name || '').replace(/"/g, '""')}"`);
                csv.push(`"Tipo","${typeLabel}"`);
                csv.push(`"Setor","${(asset.sector || '').replace(/"/g, '""')}"`);
                csv.push(`"Data Exportação","${nowStr}"`);
                csv.push(`"Preço Atual (R$)","${asset.price ? asset.price.toFixed(2) : '0.00'}"`);
                csv.push(`"Score Radar","${asset.score ? asset.score.toFixed(2) : '0.00'}"`);
                if (asset.type === 'stock') {
                    csv.push(`"P/L","${asset.pe !== null && asset.pe !== undefined ? asset.pe.toFixed(2) : 'N/A'}"`);
                    csv.push(`"P/VP","${asset.pb !== null && asset.pb !== undefined ? asset.pb.toFixed(2) : 'N/A'}"`);
                    csv.push(`"Dividend Yield (12m)","${asset.dy ? (asset.dy * 100).toFixed(2) + '%' : '0.00%'}"`);
                    csv.push(`"ROE","${asset.roe !== null && asset.roe !== undefined ? (asset.roe * 100).toFixed(2) + '%' : 'N/A'}"`);
                    csv.push(`"LPA (Lucro por Ação)","${asset.eps !== null && asset.eps !== undefined ? asset.eps.toFixed(2) : 'N/A'}"`);
                    csv.push(`"VPA (Valor Patrimonial)","${asset.vpa !== null && asset.vpa !== undefined ? asset.vpa.toFixed(2) : 'N/A'}"`);
                    csv.push(`"Preço Justo Graham (R$)","${asset.graham ? asset.graham.toFixed(2) : 'N/A'}"`);
                    csv.push(`"Preço Justo Bazin (R$)","${asset.bazin ? asset.bazin.toFixed(2) : 'N/A'}"`);
                } else {
                    csv.push(`"P/VP","${asset.pb !== null && asset.pb !== undefined ? asset.pb.toFixed(2) : 'N/A'}"`);
                    csv.push(`"Dividend Yield (12m)","${asset.dy ? (asset.dy * 100).toFixed(2) + '%' : '0.00%'}"`);
                    csv.push(`"Rendimento Médio Mensal (R$)","${asset.rate ? asset.rate.toFixed(2) : 'N/A'}"`);
                    csv.push(`"VPA (Valor Patrimonial)","${asset.vpa !== null && asset.vpa !== undefined ? asset.vpa.toFixed(2) : 'N/A'}"`);
                }

                csv.push('');
                csv.push(`"DETALHAMENTO DO SCORE"`);
                csv.push(`"Critério","Pontuação Obtida","Pontuação Máxima","Descrição"`);
                (asset.breakdown || []).forEach(b => {
                    csv.push(`"${(b.label || '').replace(/"/g, '""')}","${b.score ? b.score.toFixed(2) : '0.00'}","${b.max ? b.max.toFixed(1) : '0.0'}","${(b.desc || '').replace(/"/g, '""')}"`);
                });

                if (asset.history && asset.history.length > 0) {
                    csv.push('');
                    csv.push(`"HISTÓRICO DE DADOS"`);
                    csv.push(`"Data","Preço (R$)","DY (12m)","Score"`);
                    asset.history.forEach(h => {
                        const date = h.date || h.month || '';
                        const p = h.price != null ? h.price.toFixed(2) : '';
                        const dyVal = h.dy != null ? (h.dy * 100).toFixed(2) + '%' : '';
                        const s = h.score != null ? h.score.toFixed(2) : '';
                        csv.push(`"${date}","${p}","${dyVal}","${s}"`);
                    });
                }

                downloadFile(csv.join('\n'), `${asset.ticker}_radar_fundamentalista.csv`, 'text/csv;charset=utf-8');
                showToast(`CSV de ${asset.ticker} baixado com sucesso!`);
            } else if (format === 'copy') {
                let lines = [];
                lines.push(`=== RADAR FUNDAMENTALISTA B3 ===`);
                lines.push(`Ativo: ${asset.ticker} — ${asset.name}`);
                lines.push(`Tipo: ${typeLabel} | Setor: ${asset.sector || 'N/I'} | Score Radar: ${asset.score ? asset.score.toFixed(2) : '0.00'} / 10`);
                lines.push(``);
                lines.push(`📊 INDICADORES FUNDAMENTALISTAS:`);
                lines.push(`- Preço Atual: R$ ${asset.price ? asset.price.toFixed(2) : '0,00'}`);
                lines.push(`- Dividend Yield (12m): ${asset.dy ? (asset.dy * 100).toFixed(2).replace('.', ',') + '%' : '0,00%'}`);
                if (asset.type === 'stock') {
                    lines.push(`- P/L (Preço / Lucro): ${asset.pe !== null && asset.pe !== undefined ? asset.pe.toFixed(2).replace('.', ',') + 'x' : 'N/A'}`);
                    lines.push(`- P/VP (Preço / Valor Patrimonial): ${asset.pb !== null && asset.pb !== undefined ? asset.pb.toFixed(2).replace('.', ',') + 'x' : 'N/A'}`);
                    lines.push(`- ROE (Retorno s/ Patrimônio): ${asset.roe !== null && asset.roe !== undefined ? (asset.roe * 100).toFixed(2).replace('.', ',') + '%' : 'N/A'}`);
                    lines.push(`- LPA (Lucro por Ação): ${asset.eps !== null && asset.eps !== undefined ? 'R$ ' + asset.eps.toFixed(2).replace('.', ',') : 'N/A'}`);
                    lines.push(`- VPA (Valor Patrimonial p/ Ação): ${asset.vpa !== null && asset.vpa !== undefined ? 'R$ ' + asset.vpa.toFixed(2).replace('.', ',') : 'N/A'}`);
                    lines.push(`- Preço Justo Graham: ${asset.graham ? 'R$ ' + asset.graham.toFixed(2).replace('.', ',') : 'N/A'}`);
                    lines.push(`- Preço Justo Bazin: ${asset.bazin ? 'R$ ' + asset.bazin.toFixed(2).replace('.', ',') : 'N/A'}`);
                } else {
                    lines.push(`- P/VP (Preço / Valor Patrimonial): ${asset.pb !== null && asset.pb !== undefined ? asset.pb.toFixed(2).replace('.', ',') + 'x' : 'N/A'}`);
                    lines.push(`- Rendimento Médio Mensal: ${asset.rate ? 'R$ ' + asset.rate.toFixed(2).replace('.', ',') : 'N/A'}`);
                    lines.push(`- VPA (Valor Patrimonial p/ Cota): ${asset.vpa !== null && asset.vpa !== undefined ? 'R$ ' + asset.vpa.toFixed(2).replace('.', ',') : 'N/A'}`);
                }

                if (asset.breakdown && asset.breakdown.length > 0) {
                    lines.push(``);
                    lines.push(`🎯 DETALHAMENTO DO SCORE:`);
                    asset.breakdown.forEach(b => {
                        if (b.label === 'Moderadores Macro (v3)') return;
                        lines.push(`• ${b.label}: ${b.score.toFixed(2)} / ${b.max.toFixed(1)} (${b.desc || ''})`);
                    });
                }

                lines.push(``);
                lines.push(`Fonte: Radar Fundamentalista B3 (Exportado em ${nowStr})`);

                copyTextToClipboard(lines.join('\n'), `Resumo de ${asset.ticker} copiado para a área de transferência!`);
            }
        }

        function exportTdData(format) {
            closeExportMenu();

            const bond = window.currentTdBond || {
                name: document.getElementById('td-modal-name')?.textContent || 'Título',
                type: document.getElementById('td-modal-type')?.textContent || 'Tesouro'
            };
            const nowStr = new Date().toLocaleDateString('pt-BR');
            const bondName = bond.name || 'Tesouro';

            if (format === 'json') {
                const jsonData = {
                    title: bond.name,
                    group: bond.group || bond.type || 'Tesouro Direto',
                    type: bond.type,
                    risk_profile: bond.risk_profile || '',
                    buy_yield: bond.buy_yield,
                    buy_price: bond.buy_price,
                    sell_price: bond.sell_price,
                    maturity_date: bond.maturity_date,
                    score: bond.score,
                    export_date: new Date().toISOString(),
                    score_breakdown: bond.score_breakdown || [],
                    history: bond.history || []
                };
                downloadFile(JSON.stringify(jsonData, null, 2), `${bondName.replace(/\s+/g, '_')}_tesouro.json`, 'application/json;charset=utf-8');
                showToast(`JSON de ${bondName} baixado com sucesso!`);
            } else if (format === 'csv') {
                let csv = [];
                csv.push(`"Métrica","Valor"`);
                csv.push(`"Título","${bondName.replace(/"/g, '""')}"`);
                csv.push(`"Tipo","${(bond.type || '').replace(/"/g, '""')}"`);
                csv.push(`"Grupo","${(bond.group || '').replace(/"/g, '""')}"`);
                csv.push(`"Perfil de Risco","${(bond.risk_profile || '').replace(/"/g, '""')}"`);
                csv.push(`"Data Exportação","${nowStr}"`);
                csv.push(`"Taxa Atual (a.a.)","${bond.buy_yield != null ? bond.buy_yield.toFixed(2) + '%' : 'N/A'}"`);
                csv.push(`"Preço de Compra (R$)","${bond.buy_price != null ? bond.buy_price.toFixed(2) : 'N/A'}"`);
                csv.push(`"Preço de Venda (R$)","${bond.sell_price != null ? bond.sell_price.toFixed(2) : 'N/A'}"`);
                csv.push(`"Vencimento","${bond.maturity_date || 'N/A'}"`);
                csv.push(`"Score Radar","${bond.score != null ? bond.score.toFixed(1) : 'N/A'}"`);

                if (bond.score_breakdown && bond.score_breakdown.length > 0) {
                    csv.push('');
                    csv.push(`"DETALHAMENTO DO SCORE"`);
                    csv.push(`"Critério","Pontuação Obtida","Pontuação Máxima"`);
                    bond.score_breakdown.forEach(b => {
                        csv.push(`"${(b.label || '').replace(/"/g, '""')}","${b.score != null ? b.score.toFixed(1) : '0.0'}","${b.max != null ? (b.max % 1 === 0 ? b.max.toFixed(0) : b.max.toFixed(1)) : '0'}"`);
                    });
                }

                downloadFile(csv.join('\n'), `${bondName.replace(/\s+/g, '_')}_tesouro.csv`, 'text/csv;charset=utf-8');
                showToast(`CSV de ${bondName} baixado com sucesso!`);
            } else if (format === 'copy') {
                let lines = [];
                lines.push(`=== RADAR FUNDAMENTALISTA B3 — TESOURO DIRETO ===`);
                lines.push(`Título: ${bondName}`);
                lines.push(`Tipo: ${bond.type || 'Tesouro'} | Perfil de Risco: ${bond.risk_profile || 'Normal'} | Score Radar: ${bond.score != null ? bond.score.toFixed(1) : 'N/A'} / 10`);
                lines.push(``);
                lines.push(`📊 INDICADORES DO TÍTULO:`);
                lines.push(`- Taxa Atual: ${bond.buy_yield != null ? bond.buy_yield.toFixed(2).replace('.', ',') + '% a.a.' : 'N/A'}`);
                lines.push(`- Preço de Compra: ${bond.buy_price != null ? 'R$ ' + bond.buy_price.toFixed(2).replace('.', ',') : 'N/A'}`);
                lines.push(`- Preço de Venda: ${bond.sell_price != null ? 'R$ ' + bond.sell_price.toFixed(2).replace('.', ',') : 'N/A'}`);
                lines.push(`- Vencimento: ${bond.maturity_date || 'N/A'}`);

                if (bond.score_breakdown && bond.score_breakdown.length > 0) {
                    lines.push(``);
                    lines.push(`🎯 DETALHAMENTO DO SCORE:`);
                    bond.score_breakdown.forEach(b => {
                        lines.push(`• ${b.label}: ${b.score.toFixed(1)} / ${(b.max % 1 === 0 ? b.max.toFixed(0) : b.max.toFixed(1))}`);
                    });
                }

                lines.push(``);
                lines.push(`Fonte: Radar Fundamentalista B3 (Exportado em ${nowStr})`);

                copyTextToClipboard(lines.join('\n'), `Resumo de ${bondName} copiado para a área de transferência!`);
            }
        }

        function exportPDF() {
            // Fechar menu de export
            document.getElementById('export-menu').style.display = 'none';

            // Garantir que a página não está scrollada para não deslocar a captura
            window.scrollTo(0, 0);

            const btn = document.querySelector('#export-btn');
            const originalText = btn.innerHTML;
            btn.innerHTML = '⏳ Gerando PDF...';
            btn.disabled = true;

            const container = document.querySelector('.container');

            // ── Cabeçalho temporário com data ──
            const now = new Date();
            const dateStr = now.toLocaleDateString('pt-BR', {
                day: '2-digit', month: 'long', year: 'numeric',
                hour: '2-digit', minute: '2-digit'
            });

            let visibleCount = 0;
            const currentTbody = document.querySelector(
                currentTab === 'stocks' ? '#stocks-tbody' :
                    currentTab === 'fiis' ? '#fiis-tbody' :
                        currentTab === 'fiagros' ? '#fiagros-tbody' :
                            currentTab === 'sectors' ? '#sectors-tbody' : null
            );
            if (currentTbody) {
                visibleCount = currentTbody.querySelectorAll('tr:not(.hidden)').length;
            }

            const filterInfo = [];
            const indexVal = document.getElementById('index-filter').value;
            if (indexVal !== 'all') filterInfo.push('Índice: ' + indexVal.toUpperCase());
            const sectorVal = document.getElementById('sector-filter').value;
            if (sectorVal !== 'all') filterInfo.push('Setor: ' + sectorVal);
            const scoreRangeEl = document.getElementById('score-range-filter');
            const scoreRangeVal = scoreRangeEl ? scoreRangeEl.value : 'all';
            if (scoreRangeVal !== 'all') filterInfo.push('Score: ' + scoreRangeVal);
            const filterStr = filterInfo.length ? ' &mdash; ' + filterInfo.join(', ') : '';
            const tabName = currentTab === 'stocks' ? 'acoes' : currentTab === 'fiis' ? 'fiis' : currentTab === 'fiagros' ? 'fiagros' : 'setores';
            const pdfFilename = `radar-b3-${tabName}-${scoreRangeVal}-${now.toISOString().slice(0, 10)}.pdf`;

            const pdfHeader = document.createElement('div');
            pdfHeader.id = 'pdf-temp-header';
            pdfHeader.innerHTML = `
            <div style="text-align:center;padding:4px 0 6px 0;border-bottom:2px solid #334155;margin-bottom:6px;">
                <h1 style="margin:0;font-size:16px;font-weight:700;color:#1e293b;">Radar Fundamentalista B3</h1>
                <p style="margin:2px 0 0 0;font-size:10px;color:#64748b;">
                    ${dateStr} &mdash; 
                    Aba: ${currentTab.charAt(0).toUpperCase() + currentTab.slice(1)} &mdash; 
                    ${visibleCount} ativos visíveis${filterStr}
                </p>
            </div>
        `;
            container.insertBefore(pdfHeader, container.firstChild);

            // ── Forçar largura A4 landscape no container (corrige mobile: tabela não fica cortada) ──
            const scrollContainers = document.querySelectorAll('.table-scroll');
            const scrollOrigins = [];
            scrollContainers.forEach(el => {
                scrollOrigins.push({
                    el: el,
                    overflowX: el.style.overflowX,
                    overflowY: el.style.overflowY,
                    maxWidth: el.style.maxWidth
                });
                el.style.overflowX = 'visible';
                el.style.overflowY = 'visible';
                el.style.maxWidth = 'none';
            });

            const origContainerWidth = container.style.width;
            const origContainerMaxWidth = container.style.maxWidth;
            container.style.width = '1080px';    // ~297mm (A4 landscape) a ~96dpi
            container.style.maxWidth = '1080px';

            // ── Compactar layout para PDF ──
            document.body.classList.add('pdf-export');
            container.classList.add('pdf-export');

            // ── Forçar estilos inline para captura sem whitespace ──
            const headerEl = container.querySelector('header');
            const logoH1 = container.querySelector('.logo-text h1');
            const logoP = container.querySelector('.logo-text p');

            // Aplicar compactação DIRETAMENTE nos elementos (inline, sem depender de classe CSS)
            document.body.style.padding = '0';
            document.body.style.margin = '0';
            document.body.style.background = 'none';
            if (headerEl) {
                headerEl.style.display = 'none';
            }

            // Esconder botões
            document.querySelectorAll('#export-btn, #help-toggle-btn, #theme-toggle-btn, .header-ts').forEach(el => {
                if (el) el.style.display = 'none';
            });

            const LANDSCAPE_WIDTH = 1080; // px para windowWidth do html2canvas

            const opt = {
                margin: [0.15, 0.15, 0.3, 0.15],   // top, right, bottom, left (inches)
                filename: pdfFilename,
                image: { type: 'jpeg', quality: 0.9 },
                html2canvas: {
                    scale: 2, useCORS: true, letterRendering: true,
                    scrollX: 0, scrollY: 0,
                    x: 0, y: 0,
                    width: LANDSCAPE_WIDTH,
                    windowWidth: LANDSCAPE_WIDTH
                },
                jsPDF: { unit: 'in', format: 'a4', orientation: 'landscape' },
                pagebreak: { mode: ['avoid-all', 'css', 'legacy'], avoid: 'tr, .summary-card' }
            };

            function restoreStyles() {
                // Restaurar scroll containers
                scrollContainers.forEach((el, i) => {
                    const orig = scrollOrigins[i];
                    el.style.overflowX = orig.overflowX;
                    el.style.overflowY = orig.overflowY;
                    el.style.maxWidth = orig.maxWidth;
                });
                // Restaurar largura do container
                container.style.width = origContainerWidth;
                container.style.maxWidth = origContainerMaxWidth;
                // Restaurar body
                document.body.style.padding = '';
                document.body.style.margin = '';
                document.body.style.background = '';
                if (headerEl) {
                    headerEl.style.display = '';
                }
                document.querySelectorAll('#export-btn, #help-toggle-btn, #theme-toggle-btn, .timestamp').forEach(el => {
                    if (el) el.style.display = '';
                });
                document.body.classList.remove('pdf-export');
                container.classList.remove('pdf-export');
                pdfHeader.remove();
                btn.innerHTML = originalText;
                btn.disabled = false;
            }

            html2pdf().set(opt).from(container).save().then(restoreStyles).catch(err => {
                restoreStyles();
                console.error('PDF error:', err);
                alert('Erro ao gerar PDF. Tente novamente.');
            });
        }

        // Close export menu on outside click
        document.addEventListener('click', function (event) {
            const btn = document.getElementById('export-btn');
            const menu = document.getElementById('export-menu');
            if (btn && menu && !btn.contains(event.target) && !menu.contains(event.target)) {
                menu.style.display = 'none';
            }
        });

        function openHelpModal() {
            document.getElementById('help-modal').classList.remove('hidden');
        }

        function closeHelpModal() {
            document.getElementById('help-modal').classList.add('hidden');
        }

        function closeHelpModalOnOutsideClick(event) {
            if (event.target === document.getElementById('help-modal')) {
                closeHelpModal();
            }
        }

        // ── TD Detail Modal ──

        window.currentTdBond = null;
        window.currentTdChartType = 'tax';

        function onTdRangeChange(value) {
            if (!window.currentTdBond) return;
            let days = parseInt(value, 10);
            if (value === 'max') {
                days = 1800; // 5 anos
            }
            updateTdChart(window.currentTdBond, days, value, window.currentTdChartType);
        }

        function onTdChartTypeChange(value) {
            window.currentTdChartType = value;
            if (!window.currentTdBond) return;
            const rangeSelect = document.getElementById('td-chart-range');
            let rangeValue = rangeSelect ? rangeSelect.value : '360';
            let days = parseInt(rangeValue, 10);
            if (rangeValue === 'max') days = 1800;
            updateTdChart(window.currentTdBond, days, rangeValue, value);
        }

        function ensureKeyValueLabelsPlugin() {
            if (Chart.registry.plugins.get('keyValueLabels')) return;

            Chart.register({
                id: 'keyValueLabels',
                afterDatasetsDraw(chart) {
                    const options = chart.options.plugins?.keyValueLabels;
                    if (!options || options === false || options.enabled === false) return;
                    if (chart.config.type === 'bar') return;
                    if (!options.format) return;

                    const isLight = (options.isLight !== undefined) ? options.isLight : !document.body.classList.contains('dark');

                    const labels = [];
                    const globalSeen = new Set();
                    chart.data.datasets.forEach(function(dataset, datasetIndex) {
                        if (dataset.skipKeyValueLabels) return;
                        const meta = chart.getDatasetMeta(datasetIndex);
                        if (meta.hidden) return;
                        const valid = dataset.data
                            .map(function(value, index) { return { value: value, index: index }; })
                            .filter(function(point) {
                                return Number.isFinite(point.value) && meta.data[point.index];
                            });
                        if (!valid.length) return;

                        const min = valid.reduce(function(best, point) {
                            return point.value < best.value ? point : best;
                        });
                        const max = valid.reduce(function(best, point) {
                            return point.value > best.value ? point : best;
                        });
                        const seen = new Set();
                        function addLabel(point, priority, type) {
                            if (seen.has(point.index) || globalSeen.has(point.index)) return;
                            seen.add(point.index);
                            globalSeen.add(point.index);
                            labels.push({
                                datasetIndex: datasetIndex,
                                index: point.index,
                                value: point.value,
                                priority: priority,
                                type: type
                            });
                        }

                        const first = valid[0];
                        const last = valid[valid.length - 1];
                        addLabel(max, 1, 'peak');
                        addLabel(min, 1, 'valley');
                        addLabel(last, 2, last.value < valid[Math.max(0, valid.length - 2)].value ? 'valley' : 'peak');
                        addLabel(first, 3, first.value > valid[Math.min(1, valid.length - 1)].value ? 'peak' : 'valley');

                        const localExtrema = [];
                        if (options.maxLocalExtrema > 0) {
                            for (let i = 1; i < valid.length - 1; i++) {
                                const previous = valid[i - 1].value;
                                const current = valid[i].value;
                                const next = valid[i + 1].value;
                                const prominence = Math.min(Math.abs(current - previous), Math.abs(current - next));
                                if (current > previous && current > next) {
                                    localExtrema.push({ point: valid[i], type: 'peak', prominence: prominence });
                                } else if (current < previous && current < next) {
                                    localExtrema.push({ point: valid[i], type: 'valley', prominence: prominence });
                                }
                            }
                            localExtrema
                                .sort(function(a, b) { return b.prominence - a.prominence; })
                                .slice(0, options.maxLocalExtrema)
                                .forEach(function(extremum) { addLabel(extremum.point, 4, extremum.type); });
                        }
                    });

                    labels.sort(function(a, b) { return a.priority - b.priority; });

                    const drawn = [];
                    const ctx = chart.ctx;
                    ctx.save();
                    ctx.font = '700 10px Inter, sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';

                    labels.forEach(function(label) {
                        const point = chart.getDatasetMeta(label.datasetIndex).data[label.index];
                        if (!point) return;
                        let text;
                        if (options.format === 'currency') text = 'R$ ' + label.value.toFixed(2);
                        else if (options.format === 'score') text = label.value.toFixed(1);
                        else text = label.value.toFixed(2) + '%';

                        const width = ctx.measureText(text).width + 10;
                        const height = 17;
                        let x = point.x - width / 2;
                        let y = label.type === 'valley' ? point.y + 5 : point.y - height - 5;
                        if (y < chart.chartArea.top) y = point.y + 5;
                        x = Math.max(chart.chartArea.left, Math.min(x, chart.chartArea.right - width));
                        if (y + height > chart.chartArea.bottom) y = point.y - height - 5;

                        const box = { x: x - 4, y: y - 3, width: width + 8, height: height + 6 };
                        const collides = drawn.some(function(other) {
                            return box.x < other.x + other.width && box.x + box.width > other.x &&
                                box.y < other.y + other.height && box.y + box.height > other.y;
                        });
                        if (collides) return;

                        const labelColor = chart.data.datasets[label.datasetIndex].borderColor || options.color;
                        ctx.globalAlpha = 1;
                        ctx.fillStyle = options.isLight ? 'rgba(255, 255, 255, 0.98)' : 'rgba(15, 23, 42, 0.96)';
                        ctx.strokeStyle = labelColor;
                        ctx.lineWidth = 1;
                        if (ctx.roundRect) {
                            ctx.beginPath();
                            ctx.roundRect(x, y, width, height, 3);
                            ctx.fill();
                            ctx.stroke();
                        } else {
                            ctx.fillRect(x, y, width, height);
                            ctx.strokeRect(x, y, width, height);
                        }
                        ctx.fillStyle = labelColor;
                        ctx.fillText(text, x + width / 2, y + height / 2);
                        drawn.push(box);
                    });
                    ctx.restore();
                }
            });
        }

        function updateTdChart(td, days, rangeValue, chartType) {
            ensureKeyValueLabelsPlugin();
            // Destrói instância anterior antes de recriar
            if (window.tdChartInstance) {
                window.tdChartInstance.destroy();
                window.tdChartInstance = null;
            }

            // Define texto do período nos títulos
            let periodText = days + ' dias';
            if (rangeValue === '30') periodText = '30 dias';
            else if (rangeValue === '60') periodText = '60 dias';
            else if (rangeValue === '90') periodText = '90 dias';
            else if (rangeValue === '180') periodText = '180 dias';
            else if (rangeValue === '360') periodText = '12 meses';
            else if (rangeValue === '720') periodText = '2 anos';
            else if (rangeValue === '1080') periodText = '3 anos';
            else if (rangeValue === 'max') periodText = 'Máx';

            const chartTitleEl = document.getElementById('td-chart-title');
            const canvas = document.getElementById('td-detail-chart');
            if (!canvas) return;
            prepareTdHistoryCanvas(canvas);

            const ctx = canvas.getContext('2d');
            const isLight = !document.body.classList.contains('dark');
            const gridColor = isLight ? 'rgba(15, 23, 42, 0.06)' : 'rgba(255, 255, 255, 0.05)';
            const tickColor = isLight ? '#475569' : '#9ca3af';

            // Point radius behavior matching Stock/FII charts
            const pointRadius = days > 90 ? 0 : 3;
            const pointHoverRadius = 5;

            if (chartType === 'tax') {
                const isSelicSpread = td.yield_kind === 'selic_spread';
                if (chartTitleEl) chartTitleEl.textContent = (isSelicSpread ? '📈 ÁGIO/DESÁGIO HISTÓRICO' : '📈 TAXA HISTÓRICA') + ' (' + periodText + ')';
                const taxHist = getTdHistory(td, 'buy_yield', days);
                if (taxHist.length === 0) {
                    renderTdHistoryUnavailable(canvas, 'Histórico real de taxa ainda indisponível para este título.');
                    return;
                }

                window.tdChartInstance = new Chart(ctx, {
                    type: 'line',
                    data: {
                            labels: taxHist.map(point => point.label),
                        datasets: [{
                            label: isSelicSpread ? 'Spread sobre Selic (% a.a.)' : 'Taxa (% a.a.)',
                            data: taxHist.map(point => point.value * 100),
                            borderColor: '#8b5cf6',
                            backgroundColor: 'rgba(139, 92, 246, 0.08)',
                            borderWidth: 2,
                            pointRadius: pointRadius,
                            pointHoverRadius: pointHoverRadius,
                            fill: true,
                            tension: 0.3
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        resize: { delay: 0 },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                mode: 'index',
                                intersect: false,
                                backgroundColor: 'rgba(15, 23, 42, 0.9)',
                                padding: 8,
                                cornerRadius: 4,
                                callbacks: {
                                    label: function(context) {
                                        return (isSelicSpread ? 'Selic ' + (context.parsed.y >= 0 ? '+' : '') : '') + context.parsed.y.toFixed(isSelicSpread ? 4 : 2) + '% a.a.';
                                    }
                                }
                            },
                            keyValueLabels: {
                                format: 'percent',
                                color: '#8b5cf6',
                                isLight: isLight,
                                maxLocalExtrema: 3
                            },
                            valueLabels: false
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: { color: tickColor, maxTicksLimit: 5, maxRotation: 0, font: { size: 8 } }
                            },
                            y: {
                                grid: { color: gridColor },
                                ticks: {
                                    color: tickColor,
                                    font: { size: 8 },
                                    callback: function(value) { return value.toFixed(1) + '%'; }
                                },
                                grace: '20%'
                            }
                        }
                    }
                });
            } else if (chartType === 'pu') {
                if (chartTitleEl) chartTitleEl.textContent = '💰 PU Histórico (' + periodText + ')';
                const puHist = getTdHistory(td, 'buy_price', days);
                if (puHist.length === 0) {
                    renderTdHistoryUnavailable(canvas, 'Histórico real de PU ainda indisponível para este título.');
                    return;
                }

                window.tdChartInstance = new Chart(ctx, {
                    type: 'line',
                    data: {
                            labels: puHist.map(point => point.label),
                        datasets: [{
                            label: 'PU (R$)',
                            data: puHist.map(point => point.value),
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.08)',
                            borderWidth: 2,
                            pointRadius: pointRadius,
                            pointHoverRadius: pointHoverRadius,
                            fill: true,
                            tension: 0.3
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        resize: { delay: 0 },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                mode: 'index',
                                intersect: false,
                                backgroundColor: 'rgba(15, 23, 42, 0.9)',
                                padding: 8,
                                cornerRadius: 4,
                                callbacks: {
                                    label: function(context) {
                                        return 'R$ ' + context.parsed.y.toFixed(2);
                                    }
                                }
                            },
                            keyValueLabels: {
                                format: 'currency',
                                color: '#10b981',
                                isLight: isLight,
                                maxLocalExtrema: 3
                            },
                            valueLabels: false
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: { color: tickColor, maxTicksLimit: 5, maxRotation: 0, font: { size: 8 } }
                            },
                            y: {
                                grid: { color: gridColor },
                                ticks: {
                                    color: tickColor,
                                    font: { size: 8 },
                                    callback: function(value) { return 'R$ ' + value.toFixed(0); }
                                },
                                grace: '20%'
                            }
                        }
                    }
                });
            } else if (chartType === 'score') {
                if (chartTitleEl) chartTitleEl.textContent = '🎯 Score Histórico (' + periodText + ')';
                const scoreHist = getTdHistory(td, 'score', days);
                if (scoreHist.length === 0) {
                    renderTdHistoryUnavailable(canvas, 'O histórico de score começa a ser formado nas próximas atualizações diárias.');
                    return;
                }

                window.tdChartInstance = new Chart(ctx, {
                    type: 'line',
                    data: {
                            labels: scoreHist.map(point => point.label),
                        datasets: [{
                            label: 'Score do dia',
                            data: scoreHist.map(point => point.value),
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59, 130, 246, 0.08)',
                            borderWidth: 2,
                            pointRadius: pointRadius,
                            pointHoverRadius: pointHoverRadius,
                            fill: true,
                            tension: 0.3
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        resize: { delay: 0 },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                mode: 'index',
                                intersect: false,
                                backgroundColor: 'rgba(15, 23, 42, 0.9)',
                                padding: 8,
                                cornerRadius: 4,
                                callbacks: {
                                    label: function(context) {
                                        return 'Score: ' + context.parsed.y.toFixed(1);
                                    }
                                }
                            },
                            keyValueLabels: {
                                format: 'score',
                                color: '#3b82f6',
                                isLight: isLight,
                                maxLocalExtrema: 3
                            },
                            valueLabels: false
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: { color: tickColor, maxTicksLimit: 5, maxRotation: 0, font: { size: 8 } }
                            },
                            y: {
                                min: 0,
                                max: 10,
                                grid: { color: gridColor },
                                ticks: {
                                    color: tickColor,
                                    font: { size: 8 },
                                    stepSize: 2,
                                    callback: function(value) { return value.toFixed(0); }
                                }
                            }
                        }
                    }
                });
            }
        }

        function openTdDetailFromHome(name) {
            const data = window.dashboardData || {};
            const tdData = data.tesouro_direto || [];
            let bond = tdData.find(function(b) { return b.name === name; });
            if (!bond && name) {
                const normName = name.toLowerCase().replace(/\+/g, '').trim();
                bond = tdData.find(function(b) {
                    const bNorm = (b.name || '').toLowerCase().replace(/\+/g, '').trim();
                    return bNorm.includes(normName) || normName.includes(bNorm);
                });
            }
            if (!bond && name) {
                // Fallback: busca por tipo de titulo se nao encontrar pelo ano
                const typeTerms = ['selic', 'ipca', 'prefixado', 'renda', 'educa'];
                for (let i = 0; i < typeTerms.length; i++) {
                    if (name.toLowerCase().includes(typeTerms[i])) {
                        bond = tdData.find(function(b) {
                            return (b.type || '').toLowerCase().includes(typeTerms[i]) || (b.name || '').toLowerCase().includes(typeTerms[i]);
                        });
                        if (bond) break;
                    }
                }
            }
            if (bond) {
                const tdJson = encodeURIComponent(JSON.stringify(bond));
                openTdDetailModal(tdJson);
            }
        }

        function openTdDetailModal(tdJson) {
            const td = JSON.parse(decodeURIComponent(tdJson));
            window.currentTdBond = td;

            // Reset selectors
            const rangeSelect = document.getElementById('td-chart-range');
            if (rangeSelect) {
                rangeSelect.value = '360';
            }
            const typeSelect = document.getElementById('td-chart-type');
            if (typeSelect) {
                typeSelect.value = 'tax';
            }
            window.currentTdChartType = 'tax';

            // Destrói instâncias anteriores
            if (window.tdChartInstance) {
                window.tdChartInstance.destroy();
                window.tdChartInstance = null;
            }

            // Preenche informações textuais
            document.getElementById('td-modal-name').textContent = td.name || 'Título';
            document.getElementById('td-modal-subtitle').textContent = (td.group || td.type || 'Tesouro Direto') + (td.risk_profile ? ' · Risco: ' + td.risk_profile : '');
            document.getElementById('td-modal-type').textContent = td.type || '—';
            document.getElementById('td-modal-yield-label').textContent = td.yield_kind === 'selic_spread' ? 'Spread sobre Selic' : 'Taxa Atual';
            document.getElementById('td-modal-yield').textContent = td.buy_yield != null ? formatTdYield(td) + ' a.a.' : '—';
            document.getElementById('td-modal-maturity').textContent = td.maturity_date || (td.days_to_maturity ? td.days_to_maturity + ' dias' : '—');
            document.getElementById('td-modal-score').textContent = td.score != null ? td.score.toFixed(1) + '/10' : '—';
            document.getElementById('td-modal-buy-price').textContent = td.buy_price != null ? 'R$ ' + td.buy_price.toFixed(2) : '—';
            document.getElementById('td-modal-sell-price').textContent = td.sell_price != null ? 'R$ ' + td.sell_price.toFixed(2) : '—';
            renderTdHistoryStatus(td);

            // Score breakdown
            const breakdownEl = document.getElementById('td-modal-score-breakdown');
            if (breakdownEl) {
                breakdownEl.innerHTML = '';
                if (td.score_breakdown && td.score_breakdown.length > 0) {
                    const titleEl = document.createElement('div');
                    titleEl.className = 'section-title';
                    titleEl.textContent = 'Detalhamento do Score';
                    breakdownEl.appendChild(titleEl);

                    td.score_breakdown.forEach(function(b) {
                        const pct = b.max > 0 ? Math.round((b.score / b.max) * 100) : 0;
                        const barColor = b.score >= (b.max * 0.75) ? '#10b981' : b.score >= (b.max * 0.40) ? '#f59e0b' : '#ef4444';

                        const itemEl = document.createElement('div');
                        itemEl.className = 'breakdown-item';
                        itemEl.innerHTML = [
                            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">',
                            '  <span class="hint" tabindex="0" data-tip="', b.tip || '', '" style="font-weight:700;font-size:0.85rem;">', b.label, ' ⓘ</span>',
                            '  <span style="font-size:0.85rem;color:var(--text-secondary);font-weight:600;">', b.score.toFixed(1), ' / ', (b.max % 1 === 0 ? b.max.toFixed(0) : b.max.toFixed(1)), '</span>',
                            '</div>',
                            '<div class="bar-container">',
                            '  <div class="bar-fill" style="width:', pct, '%;background:', barColor, ';"></div>',
                            '</div>',
                            '<small style="color:var(--text-secondary);display:block;margin-top:0.15rem;font-size:0.8rem;">', b.desc || '', '</small>'
                        ].join('');
                        breakdownEl.appendChild(itemEl);
                    });
                    if (window.initHints) window.initHints(breakdownEl);
                }
            }

            // Mostra o modal PRIMEIRO
            document.getElementById('td-detail-modal').classList.remove('hidden');

            // Cria o chart DEPOIS que o modal estiver visível no DOM
            requestAnimationFrame(function() {
                updateTdChart(td, 360, '360', 'tax');
            });
        }

        function renderTdHistoryStatus(td) {
            const el = document.getElementById('td-history-status');
            if (!el) return;
            const meta = td.history_meta || {};
            const formatDate = function(value) {
                if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return 'data indisponível';
                const parts = value.split('-');
                return parts[2] + '/' + parts[1] + '/' + parts[0];
            };
            const lastDate = formatDate(meta.last_history_date);
            const quoteDate = formatDate(meta.current_quote_date);
            const gap = meta.gap_days;
            const gapText = Number.isInteger(gap) ? ' · defasagem: ' + gap + ' dia' + (gap === 1 ? '' : 's') : '';

            if (meta.freshness === 'current_quote_demo') {
                el.textContent = '⚠️ Histórico real até ' + lastDate + '. Cotação atual demonstrativa (' + quoteDate + ') não foi incorporada ao gráfico.';
            } else if (meta.freshness === 'history_unavailable') {
                el.textContent = 'Histórico real indisponível para este título.';
            } else if (meta.freshness === 'pending_update' || meta.freshness === 'stale') {
                el.textContent = '⚠️ Histórico até ' + lastDate + ' · cotação atual em ' + quoteDate + gapText + '. Série aguardando atualização oficial.';
            } else if (meta.freshness === 'informative_gap') {
                el.textContent = 'Histórico até ' + lastDate + ' · cotação atual em ' + quoteDate + gapText + '.';
            } else {
                el.textContent = 'Histórico e cotação atualizados em ' + lastDate + '.';
            }
        }

        function closeTdDetailModal() {
            document.getElementById('td-detail-modal').classList.add('hidden');
            if (window.tdChartInstance) {
                window.tdChartInstance.destroy();
                window.tdChartInstance = null;
            }
        }

        function closeTdModalOnOutsideClick(event) {
            if (event.target === document.getElementById('td-detail-modal')) {
                closeTdDetailModal();
            }
        }

        function getTdHistory(td, field, days) {
            const cutoff = new Date();
            cutoff.setDate(cutoff.getDate() - days);
            return (td.history || []).filter(point => {
                return point.date && point[field] != null && !Number.isNaN(Number(point[field])) &&
                    (field !== 'score' || !td.score_method || point.score_method === td.score_method) &&
                    new Date(point.date + 'T00:00:00') >= cutoff;
            }).map(point => ({
                label: new Date(point.date + 'T00:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' }),
                value: Number(point[field])
            }));
        }

        function renderTdHistoryUnavailable(canvas, message) {
            canvas.style.display = 'none';
            const container = canvas.parentElement;
            let empty = container.querySelector('.td-history-unavailable');
            if (!empty) {
                empty = document.createElement('p');
                empty.className = 'td-history-unavailable';
                empty.style.cssText = 'padding:2rem 1rem;text-align:center;color:var(--text-secondary);font-size:.9rem;';
                container.appendChild(empty);
            }
            empty.textContent = message;
        }

        function prepareTdHistoryCanvas(canvas) {
            canvas.style.display = '';
            const empty = canvas.parentElement.querySelector('.td-history-unavailable');
            if (empty) empty.remove();
        }

        window.focusChartInstance = null;
        let currentFocusIndicator = 'selic';
        let currentFocusLookback = 5;

        function setFocusLookback(years) {
            currentFocusLookback = parseInt(years, 10) || 5;
            const selectEl = document.getElementById('focus-lookback-select');
            if (selectEl) selectEl.value = String(currentFocusLookback);
            ['3', '5', '10'].forEach(y => {
                const btn = document.getElementById(`focus-range-btn-${y}`);
                if (btn) btn.classList.toggle('active', parseInt(y, 10) === currentFocusLookback);
            });
            if (currentFocusIndicator) {
                renderFocusModalContent(currentFocusIndicator, currentFocusLookback);
            }
        }

        function openFocusDetailModal(indicator) {
            currentFocusIndicator = indicator || 'selic';
            setFocusLookback(5);
            document.getElementById('focus-detail-modal').classList.remove('hidden');
        }

        function renderFocusModalContent(indicator, lookbackYears) {
            const data = window.dashboardData;
            if (!data || !data.macro_state) return;
            const macro = data.macro_state;

            let title = '';
            let subtitle = '';
            let focusValues = [];
            let isPercent = false;
            let isCurrency = false;
            let historyKey = '';

            let colorFuture = '#3b82f6';
            let bgFuture = 'rgba(59, 130, 246, 0.08)';
            let colorHistory = '#6b7280';
            let bgHistory = 'rgba(107, 114, 128, 0.08)';

            let currentYear = new Date().getFullYear();
            let currentMonth = new Date().getMonth() + 1; // 1-12
            if (macro.fetched_at) {
                const yr = parseInt(macro.fetched_at.substring(0, 4), 10);
                if (!isNaN(yr)) currentYear = yr;
                const mo = parseInt(macro.fetched_at.substring(5, 7), 10);
                if (!isNaN(mo) && mo >= 1 && mo <= 12) currentMonth = mo;
            }

            const monthNamesShort = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
            const currentMonthName = monthNamesShort[currentMonth - 1];
            const yearShort = String(currentYear).slice(-2);
            const currentProgressPct = Math.round((currentMonth / 12) * 100);

            if (indicator === 'selic') {
                title = 'Taxa Selic — Realizado vs Projeção Focus';
                subtitle = 'Realizado (BCB SGS 432 - Meta COPOM) · Projeção (Boletim Focus)';
                focusValues = (macro.focus_selic || []).map(v => v == null ? null : v * 100);
                historyKey = 'SELIC_HISTORY';
                isPercent = true;
                colorFuture = '#10b981';
                bgFuture = 'rgba(16, 185, 129, 0.08)';
                colorHistory = '#ef4444';
                bgHistory = 'rgba(239, 68, 68, 0.08)';
            } else if (indicator === 'ipca') {
                title = 'IPCA — Realizado vs Projeção Focus';
                subtitle = 'Realizado (IBGE SIDRA - Acum. 12m) · Projeção (Boletim Focus)';
                focusValues = (macro.focus_ipca || []).map(v => v == null ? null : v * 100);
                historyKey = 'IPCA_HISTORY';
                isPercent = true;
                colorFuture = '#f59e0b';
                bgFuture = 'rgba(245, 158, 11, 0.08)';
                colorHistory = '#8b5cf6';
                bgHistory = 'rgba(139, 92, 246, 0.08)';
            } else if (indicator === 'cambio') {
                title = 'Câmbio (R$/US$) — Realizado vs Projeção Focus';
                subtitle = 'Realizado (BCB SGS 1 - PTAX venda) · Projeção (Boletim Focus)';
                focusValues = macro.focus_cambio || [];
                historyKey = 'CAMBIO_HISTORY';
                isCurrency = true;
                colorFuture = '#3b82f6';
                bgFuture = 'rgba(59, 130, 246, 0.08)';
                colorHistory = '#f59e0b';
                bgHistory = 'rgba(245, 158, 11, 0.08)';
            }

            // ── Extrair histórico e agregar por ano ──
            const rawHistory = macro[historyKey] || [];
            const histByYear = {};
            rawHistory.forEach(pt => {
                let yr = null;
                if (pt.date) {
                    const parts = pt.date.split('/');
                    if (parts.length === 3) {
                        yr = parseInt(parts[2], 10);
                    } else {
                        yr = parseInt(pt.date.substring(0, 4), 10);
                    }
                }
                if (yr && !isNaN(yr)) {
                    if (!histByYear[yr]) histByYear[yr] = [];
                    histByYear[yr].push(pt.value);
                }
            });

            // Anos históricos fechados conforme lookback selecionado (3, 5 ou 10 anos)
            const histYears = [];
            for (let y = currentYear - lookbackYears; y < currentYear; y++) {
                histYears.push(y);
            }
            const histValues = histYears.map(yr => {
                const pts = histByYear[yr];
                if (!pts || pts.length === 0) return null;
                const last = pts[pts.length - 1];
                if (indicator === 'ipca') return Math.round(last * 10000) / 100;
                if (indicator === 'selic') return Math.round(last * 10000) / 100;
                return Math.round(last * 100) / 100;
            });

            // Valor atual ("Você está aqui")
            let todayValue = null;
            if (indicator === 'selic') {
                let rawSelic = macro.selic_meta ?? macro.selic ?? macro.SELIC_META ?? macro.CURRENT_SELIC;
                if (rawSelic == null && rawHistory.length > 0) {
                    rawSelic = rawHistory[rawHistory.length - 1].value;
                }
                if (rawSelic != null) {
                    todayValue = rawSelic < 1 ? Math.round(rawSelic * 10000) / 100 : rawSelic;
                }
            } else {
                let rawVal = null;
                if (indicator === 'ipca') {
                    rawVal = macro.ipca_12m ?? macro.ipca;
                } else if (indicator === 'cambio') {
                    rawVal = macro.cambio;
                }
                if (rawVal == null && rawHistory.length > 0) {
                    rawVal = rawHistory[rawHistory.length - 1].value;
                }
                if (rawVal != null) {
                    todayValue = indicator === 'ipca'
                        ? (rawVal < 1 ? Math.round(rawVal * 10000) / 100 : rawVal)
                        : Math.round(rawVal * 100) / 100;
                }
            }

            const formatVal = (v) => {
                if (v == null || isNaN(v)) return '—';
                if (isPercent) return v.toFixed(2) + '%';
                if (isCurrency) return 'R$ ' + v.toFixed(2);
                return v.toFixed(2);
            };

            const todayValStr = formatVal(todayValue);
            const focusEndYearStr = formatVal(focusValues[0]);

            // Labels da Timeline
            const todayLabel = `Hoje (${currentMonthName}/${yearShort})`;
            const allLabels = histYears.map(String).concat([
                todayLabel,
                `${currentYear} (Focus)`,
                String(currentYear + 1),
                String(currentYear + 2),
                String(currentYear + 3)
            ]);

            const todayIndex = histYears.length;
            const nullsPrefix = new Array(histYears.length).fill(null);

            // Datasets
            const histDataset = histValues.concat([todayValue, null, null, null, null]);
            const focusDataset = nullsPrefix.concat([todayValue, focusValues[0], focusValues[1], focusValues[2], focusValues[3]]);

            document.getElementById('focus-modal-title').textContent = title;
            document.getElementById('focus-modal-subtitle').textContent = subtitle;

            // Status Pill (Despoluído & Direto)
            const statusPill = document.getElementById('focus-modal-status-pill');
            if (statusPill) {
                statusPill.classList.remove('hidden');
                statusPill.innerHTML = `
                    <div style="display: flex; align-items: center; justify-content: space-between; width: 100%; font-size: 0.84rem; flex-wrap: wrap; gap: 6px;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span style="font-weight:700; color:${colorHistory};">📍 Hoje (${currentMonthName}/${yearShort}):</span> 
                            <strong style="color:${colorHistory}; font-size: 0.92rem; font-weight:800;">${todayValStr}</strong>
                            <span style="color:var(--text-secondary); font-size:0.78rem; font-weight:500;">(Mês ${currentMonth}/12)</span>
                        </div>
                        <div style="font-size:0.82rem; color:var(--text-secondary); font-weight:500;">
                            Meta Focus ${currentYear}: <strong style="color:${colorFuture}; font-weight:700;">${focusEndYearStr}</strong>
                        </div>
                    </div>
                `;
            }

            // Tabela: histórico + Você está aqui + projeções
            const tbody = document.getElementById('focus-modal-tbody');
            if (tbody) {
                const tableRows = [];
                histYears.forEach((yr, i) => {
                    const val = histValues[i];
                    const valStr = formatVal(val);
                    tableRows.push(`<tr>
                        <td style="font-weight:600;">${yr}</td>
                        <td style="font-size:0.85rem;color:var(--text-secondary);font-weight:500;">Realizado</td>
                        <td class="font-mono tabular" style="font-weight:700;color:${colorHistory};">${valStr}</td>
                    </tr>`);
                });

                // Linha "Você está aqui"
                tableRows.push(`<tr style="background: rgba(59, 130, 246, 0.08); border-left: 3px solid ${colorHistory};">
                    <td style="font-weight:700; color:${colorHistory};">${todayLabel}</td>
                    <td style="font-size:0.85rem; color:${colorHistory}; font-weight:700;">📍 Você está aqui (${currentMonth}/12 meses)</td>
                    <td class="font-mono tabular" style="font-weight:800; color:${colorHistory};">${todayValStr}</td>
                </tr>`);

                // 4 anos projeção Focus
                for (let i = 0; i < 4; i++) {
                    const yr = currentYear + i;
                    const val = focusValues[i];
                    const valStr = formatVal(val);
                    const isFuture = (i === 0) ? `Projeção Focus (Fim de ${yr})` : 'Projeção Focus';
                    tableRows.push(`<tr>
                        <td style="font-weight:600;">${yr}</td>
                        <td style="font-size:0.85rem;color:var(--text-secondary);font-weight:500;">${isFuture}</td>
                        <td class="font-mono tabular" style="font-weight:700;color:${colorFuture};">${valStr}</td>
                    </tr>`);
                }
                tbody.innerHTML = tableRows.join('');
            }

            // Renderizar Gráfico Chart.js
            requestAnimationFrame(() => {
                const canvas = document.getElementById('focus-detail-chart');
                if (canvas) {
                    const ctx = canvas.getContext('2d');
                    ensureKeyValueLabelsPlugin();
                    if (window.focusChartInstance) {
                        window.focusChartInstance.destroy();
                    }

                    const tickColor = !document.body.classList.contains('dark') ? '#475569' : '#9ca3af';
                    const gridColor = !document.body.classList.contains('dark') ? 'rgba(15, 23, 42, 0.06)' : 'rgba(255, 255, 255, 0.05)';

                    window.focusChartInstance = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: allLabels,
                            datasets: [
                                {
                                    label: 'Realizado (Histórico)',
                                    data: histDataset,
                                    borderColor: colorHistory,
                                    backgroundColor: bgHistory,
                                    borderWidth: 2.5,
                                    pointRadius: function(c) { return c.dataIndex === todayIndex ? 7 : 5; },
                                    pointHoverRadius: function(c) { return c.dataIndex === todayIndex ? 9 : 7; },
                                    pointBackgroundColor: colorHistory,
                                    pointBorderColor: colorHistory,
                                    fill: true,
                                    tension: 0.3,
                                    spanGaps: false
                                },
                                {
                                    label: 'Projeção (Focus)',
                                    data: focusDataset,
                                    borderColor: colorFuture,
                                    backgroundColor: bgFuture,
                                    borderWidth: 3,
                                    borderDash: [6, 3],
                                    pointRadius: function(c) { return c.dataIndex === todayIndex ? 0 : 6; },
                                    pointHoverRadius: function(c) { return c.dataIndex === todayIndex ? 0 : 8; },
                                    pointBackgroundColor: colorFuture,
                                    pointBorderColor: colorFuture,
                                    fill: true,
                                    tension: 0.2,
                                    spanGaps: false
                                }
                            ]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: {
                                    display: true,
                                    labels: {
                                        color: tickColor,
                                        font: { size: 11, weight: '600', family: 'Inter, sans-serif' }
                                    }
                                },
                                tooltip: {
                                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                                    padding: 10,
                                    filter: function(tooltipItem) {
                                        if (tooltipItem.dataIndex === todayIndex) {
                                            return tooltipItem.datasetIndex === 0;
                                        }
                                        return true;
                                    },
                                    callbacks: {
                                        title: function(tooltipItems) {
                                            if (!tooltipItems || !tooltipItems.length) return '';
                                            const item = tooltipItems[0];
                                            if (item.dataIndex === todayIndex) {
                                                return `📍 Posição Atual (${currentMonthName}/${yearShort})`;
                                            }
                                            return item.label;
                                        },
                                        label: function(context) {
                                            const val = context.parsed.y;
                                            if (val === null || isNaN(val)) return '';
                                            if (context.dataIndex === todayIndex) {
                                                return `Valor Atual: ${formatVal(val)} (Mês ${currentMonth}/12 decorridos)`;
                                            }
                                            return context.dataset.label + ': ' + formatVal(val);
                                        }
                                    }
                                },
                                keyValueLabels: {
                                    format: isCurrency ? 'currency' : 'percent',
                                    color: colorFuture,
                                    isLight: !document.body.classList.contains('dark')
                                }
                            },
                            scales: {
                                x: {
                                    grid: { display: false },
                                    ticks: {
                                        color: tickColor,
                                        font: function(context) {
                                            if (context.tick && context.tick.label && context.tick.label.startsWith('Hoje')) {
                                                return { size: 11, weight: 'bold', family: 'Inter, sans-serif' };
                                            }
                                            return { size: 11, weight: '500', family: 'Inter, sans-serif' };
                                        }
                                    }
                                },
                                y: {
                                    grid: { color: gridColor },
                                    ticks: {
                                        color: tickColor,
                                        font: { size: 11, family: 'Inter, sans-serif' },
                                        callback: function(v) {
                                            return isPercent ? v.toFixed(1) + '%' : isCurrency ? 'R$ ' + v.toFixed(2) : v;
                                        }
                                    }
                                }
                            }
                        }
                    });
                }
            });
        }

        function closeFocusDetailModal() {
            document.getElementById('focus-detail-modal').classList.add('hidden');
            if (window.focusChartInstance) {
                window.focusChartInstance.destroy();
                window.focusChartInstance = null;
            }
        }

        function closeFocusModalOnOutsideClick(event) {
            if (event.target === document.getElementById('focus-detail-modal')) {
                closeFocusDetailModal();
            }
        }

        /* ── Tooltip dinâmico via JS (evita clipping por overflow dos containers) ── */
        (function() {
            var tip = document.createElement('div');
            tip.id = 'hint-tooltip-el';
            tip.style.display = 'none';
            document.body.appendChild(tip);

            var activeEl = null;
            var hideTimeout = null;

            function positionTooltip(target) {
                var text = target.getAttribute('data-tip');
                if (!text) return;
                tip.textContent = text;
                tip.style.display = 'block';
                tip.classList.add('visible');

                var rect = target.getBoundingClientRect();
                var tipW = tip.offsetWidth;
                var tipH = tip.offsetHeight;
                var pad = 8;

                var left = rect.left + (rect.width / 2) - (tipW / 2);
                left = Math.max(pad, Math.min(left, window.innerWidth - tipW - pad));

                var top = rect.top - tipH - 6;
                if (top < pad) {
                    top = rect.bottom + 6;
                }

                tip.style.left = left + 'px';
                tip.style.top = top + 'px';
            }

            function hideTooltip() {
                tip.classList.remove('visible');
                tip.style.display = 'none';
                activeEl = null;
            }

            function onMouseEnter(e) {
                var target = e.target.closest('.hint');
                if (!target) return;
                if (hideTimeout) { clearTimeout(hideTimeout); hideTimeout = null; }
                activeEl = target;
                positionTooltip(target);
            }

            function onMouseLeave(e) {
                var target = e.target.closest('.hint');
                if (!target) return;
                hideTimeout = setTimeout(function() {
                    hideTooltip();
                }, 80);
            }

            function onFocus(e) {
                var target = e.target.closest ? e.target.closest('.hint') : null;
                if (target) {
                    positionTooltip(target);
                }
            }

            function onBlur(e) {
                var target = e.target.closest ? e.target.closest('.hint') : null;
                if (target) {
                    hideTooltip();
                }
            }

            function onClick(e) {
                var target = e.target.closest('.hint');
                if (target) {
                    if (activeEl === target && tip.classList.contains('visible')) {
                        hideTooltip();
                    } else {
                        activeEl = target;
                        positionTooltip(target);
                    }
                } else if (!e.target.closest('#hint-tooltip-el')) {
                    hideTooltip();
                }
            }

            document.addEventListener('mouseover', onMouseEnter);
            document.addEventListener('mouseout', onMouseLeave);
            document.addEventListener('focusin', onFocus);
            document.addEventListener('focusout', onBlur);
            document.addEventListener('click', onClick);

            window.initHints = function(container) {
                // Delegation handles new elements automatically
            };
        })();

        /* ── Comparador Head-to-Head (2 a 4 ativos) ── */
        let selectedCompareTickers = [];
        let compareChartInstance = null;
        let currentCompareClassFilter = 'all';

        function loadCompareTickersFromStorage() {
            try {
                const raw = localStorage.getItem('radar_compare_tickers');
                if (raw) selectedCompareTickers = JSON.parse(raw);
            } catch (e) {
                selectedCompareTickers = [];
            }
        }

        function findAssetByTicker(ticker) {
            if (!window.dashboardData || !ticker) return null;
            const cleanTick = String(ticker).toUpperCase().replace('.SA', '').trim();
            const data = window.dashboardData;

            if (data.stocks) {
                const s = data.stocks.find(a => (a.ticker || '').toUpperCase() === cleanTick);
                if (s) return { ...s, _class: 'stock', _classLabel: 'Ação' };
            }
            if (data.fiis) {
                const f = data.fiis.find(a => (a.ticker || '').toUpperCase() === cleanTick);
                if (f) return { ...f, _class: 'fii', _classLabel: 'FII' };
            }
            if (data.fiagros) {
                const g = data.fiagros.find(a => (a.ticker || '').toUpperCase() === cleanTick);
                if (g) return { ...g, _class: 'fiagro', _classLabel: 'FIAGRO' };
            }
            if (data.tesouro_direto) {
                const normTick = cleanTick.replace(/\s+/g, ' ');
                let t = data.tesouro_direto.find(a => {
                    const normName = (a.name || '').toUpperCase().replace(/\s+/g, ' ');
                    const normT = (a.ticker || '').toUpperCase().replace(/\s+/g, ' ');
                    return normName === normTick || normT === normTick;
                });
                if (!t) {
                    t = data.tesouro_direto.find(a => {
                        const normName = (a.name || '').toUpperCase().replace(/\s+/g, ' ');
                        return normName && normTick && (normName.includes(normTick) || normTick.includes(normName));
                    });
                }
                if (t) return { ...t, ticker: t.name, _class: 'tesouro', _classLabel: 'Tesouro' };
            }
            return null;
        }

        function getAllSearchableAssets() {
            if (!window.dashboardData) return [];
            const list = [];
            const data = window.dashboardData;
            if (data.stocks) data.stocks.forEach(s => list.push({ ticker: s.ticker, name: s.name, type: 'stock', classLabel: 'Ação', score: s.score }));
            if (data.fiis) data.fiis.forEach(f => list.push({ ticker: f.ticker, name: f.name, type: 'fii', classLabel: 'FII', score: f.score }));
            if (data.fiagros) data.fiagros.forEach(g => list.push({ ticker: g.ticker, name: g.name, type: 'fiagro', classLabel: 'FIAGRO', score: g.score }));
            if (data.tesouro_direto) data.tesouro_direto.forEach(t => list.push({ ticker: t.name, name: t.group || t.name, type: 'tesouro', classLabel: 'Tesouro', score: t.score }));
            return list;
        }

        function addTickerToCompare(ticker) {
            if (!ticker) return;
            const clean = ticker.trim().toUpperCase();
            if (selectedCompareTickers.includes(clean)) return;
            if (selectedCompareTickers.length >= 4) {
                selectedCompareTickers.shift();
            }
            selectedCompareTickers.push(clean);
            try {
                localStorage.setItem('radar_compare_tickers', JSON.stringify(selectedCompareTickers));
            } catch (e) {}
            renderComparePanel();
            if (typeof syncUrlFromState === 'function') syncUrlFromState();
        }

        function removeTickerFromCompare(ticker) {
            selectedCompareTickers = selectedCompareTickers.filter(t => t !== ticker);
            try {
                localStorage.setItem('radar_compare_tickers', JSON.stringify(selectedCompareTickers));
            } catch (e) {}
            renderComparePanel();
            if (typeof syncUrlFromState === 'function') syncUrlFromState();
        }

        function addCurrentAssetToCompare() {
            const tickerEl = document.getElementById('modal-ticker');
            if (!tickerEl) return;
            const ticker = tickerEl.textContent.trim();
            if (!ticker || ticker === 'TICKER') return;
            addTickerToCompare(ticker);
            closeDetailModal();
            switchTab('compare');
        }

        function onCompareClassFilterChange(filterValue) {
            currentCompareClassFilter = filterValue || 'all';
            const data = window.dashboardData || {};
            
            if (currentCompareClassFilter !== 'all') {
                // Filter selection to assets matching chosen class
                selectedCompareTickers = selectedCompareTickers.filter(t => {
                    const a = findAssetByTicker(t);
                    return a && a._class === currentCompareClassFilter;
                });
                
                // If fewer than 2 remain, preload Top 3 of chosen class
                if (selectedCompareTickers.length < 2) {
                    if (currentCompareClassFilter === 'stock') {
                        selectedCompareTickers = (data.top_stocks || data.stocks || []).slice(0, 3).map(s => s.ticker);
                    } else if (currentCompareClassFilter === 'fii') {
                        selectedCompareTickers = (data.top_fiis || data.fiis || []).slice(0, 3).map(f => f.ticker);
                    } else if (currentCompareClassFilter === 'fiagro') {
                        selectedCompareTickers = (data.top_fiagros || data.fiagros || []).slice(0, 3).map(fa => fa.ticker);
                    } else if (currentCompareClassFilter === 'tesouro') {
                        const tdList = (data.tesouro_direto || []).filter(function(td) {
                            return (typeof isTdAvailableForPurchase === 'function') ? isTdAvailableForPurchase(td, true) : true;
                        });
                        selectedCompareTickers = (tdList.length >= 3 ? tdList : (data.tesouro_direto || [])).slice(0, 3).map(t => t.name);
                    }
                }
            }
            
            try {
                localStorage.setItem('radar_compare_tickers', JSON.stringify(selectedCompareTickers));
            } catch (e) {}
            renderComparePanel();
            if (typeof syncUrlFromState === 'function') syncUrlFromState();
        }

        function onCompareSearchInput(query) {
            const listEl = document.getElementById('compare-autocomplete-list');
            if (!listEl) return;
            const q = (query || '').trim().toLowerCase();
            if (!q) {
                listEl.classList.add('hidden');
                listEl.innerHTML = '';
                return;
            }
            let all = getAllSearchableAssets();
            if (currentCompareClassFilter && currentCompareClassFilter !== 'all') {
                all = all.filter(a => a.type === currentCompareClassFilter);
            }
            const filtered = all.filter(a => a.ticker.toLowerCase().includes(q) || (a.name || '').toLowerCase().includes(q)).slice(0, 8);
            if (filtered.length === 0) {
                listEl.innerHTML = '<div style="padding:0.5rem 0.75rem;font-size:0.8rem;color:var(--text-muted);">Nenhum ativo encontrado</div>';
                listEl.classList.remove('hidden');
                return;
            }
            listEl.innerHTML = filtered.map(item => `
                <button type="button" class="export-option" style="display:flex;justify-content:space-between;align-items:center;width:100%;text-align:left;padding:0.45rem 0.75rem;" onclick="addTickerToCompare('${item.ticker.replace(/'/g, "\\'")}'); document.getElementById('compare-search-input').value=''; document.getElementById('compare-autocomplete-list').classList.add('hidden');">
                    <div>
                        <strong style="color:var(--text-primary);font-size:0.85rem;">${item.ticker}</strong>
                        <span style="font-size:0.75rem;color:var(--text-secondary);margin-left:0.35rem;">${item.name || ''}</span>
                    </div>
                    <span class="index-pill" style="font-size:0.65rem;">${item.classLabel}</span>
                </button>
            `).join('');
            listEl.classList.remove('hidden');
        }

        function setComparePreset(type) {
            const data = window.dashboardData || {};
            if (type === 'top_stocks') {
                const list = (data.top_stocks || data.stocks || []).slice(0, 3).map(s => s.ticker);
                selectedCompareTickers = list.length >= 2 ? list : ['BBAS3', 'PETR4', 'VALE3'];
                currentCompareClassFilter = 'stock';
            } else if (type === 'top_fiis') {
                const list = (data.top_fiis || data.fiis || []).slice(0, 3).map(f => f.ticker);
                selectedCompareTickers = list.length >= 2 ? list : ['HGLG11', 'KNCR11', 'XPML11'];
                currentCompareClassFilter = 'fii';
            } else if (type === 'top_tesouro') {
                const tdList = (data.tesouro_direto || []).filter(function(td) {
                    return (typeof isTdAvailableForPurchase === 'function') ? isTdAvailableForPurchase(td, true) : true;
                });
                const list = (tdList.length >= 3 ? tdList : (data.tesouro_direto || [])).slice(0, 3).map(t => t.name);
                selectedCompareTickers = list.length >= 2 ? list : ['Tesouro Prefixado 2029', 'Tesouro IPCA+ 2032', 'Tesouro Selic 2031'];
                currentCompareClassFilter = 'tesouro';
            } else if (type === 'mixed') {
                const stock = (data.top_stocks && data.top_stocks[0]) ? data.top_stocks[0].ticker : (data.stocks && data.stocks[0] ? data.stocks[0].ticker : 'BBAS3');
                const fii = (data.top_fiis && data.top_fiis[0]) ? data.top_fiis[0].ticker : (data.fiis && data.fiis[0] ? data.fiis[0].ticker : 'HGLG11');
                const tdList = (data.tesouro_direto || []).filter(function(td) {
                    return (typeof isTdAvailableForPurchase === 'function') ? isTdAvailableForPurchase(td, true) : true;
                });
                const td = tdList[0] ? tdList[0].name : (data.tesouro_direto && data.tesouro_direto[0] ? data.tesouro_direto[0].name : 'Tesouro IPCA+ 2040');
                selectedCompareTickers = [stock, fii, td];
                currentCompareClassFilter = 'all';
            }
            const filterEl = document.getElementById('compare-class-filter');
            if (filterEl) filterEl.value = currentCompareClassFilter;

            try {
                localStorage.setItem('radar_compare_tickers', JSON.stringify(selectedCompareTickers));
            } catch (e) {}
            renderComparePanel();
            if (typeof syncUrlFromState === 'function') syncUrlFromState();
        }

        function renderComparePanel() {
            const chipsContainer = document.getElementById('compare-selected-chips');
            const contentContainer = document.getElementById('compare-content');
            if (!chipsContainer || !contentContainer) return;

            if (selectedCompareTickers.length === 0) {
                if (window.dashboardData && window.dashboardData.top_stocks && window.dashboardData.top_stocks.length >= 3) {
                    selectedCompareTickers = [
                        window.dashboardData.top_stocks[0].ticker,
                        window.dashboardData.top_stocks[1].ticker,
                        window.dashboardData.top_stocks[2].ticker
                    ];
                } else if (window.dashboardData && window.dashboardData.stocks && window.dashboardData.stocks.length >= 3) {
                    selectedCompareTickers = [
                        window.dashboardData.stocks[0].ticker,
                        window.dashboardData.stocks[1].ticker,
                        window.dashboardData.stocks[2].ticker
                    ];
                }
            }

            chipsContainer.innerHTML = selectedCompareTickers.map(t => `
                <div class="compare-chip">
                    <span>${t}</span>
                    <button type="button" class="compare-chip-remove" onclick="removeTickerFromCompare('${t.replace(/'/g, "\\'")}')" aria-label="Remover ${t}">&times;</button>
                </div>
            `).join('');

            const assets = selectedCompareTickers.map(t => findAssetByTicker(t)).filter(Boolean);

            const presetButtonsHtml = `
                <div style="display:flex; align-items:center; gap:0.4rem; flex-wrap:wrap; margin-bottom:1rem; padding:0.65rem 0.85rem; background:var(--surface); border:1px solid var(--card-border); border-radius:var(--radius-sm);">
                    <span style="font-size:0.76rem; font-weight:700; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.04em;">⚡ Presets Rápidos:</span>
                    <button type="button" class="preset-scenario-btn" onclick="setComparePreset('top_stocks')">👑 Top 3 Ações</button>
                    <button type="button" class="preset-scenario-btn" onclick="setComparePreset('top_fiis')">🏢 Top 3 FIIs</button>
                    <button type="button" class="preset-scenario-btn" onclick="setComparePreset('top_tesouro')">🏛️ Top 3 Tesouro</button>
                    <button type="button" class="preset-scenario-btn" onclick="setComparePreset('mixed')">⚖️ Misto (Ação + FII + Tesouro)</button>
                </div>
            `;

            if (assets.length < 2) {
                contentContainer.innerHTML = `
                    ${presetButtonsHtml}
                    <div class="compare-table-card" style="padding:2.5rem 1.5rem; text-align:center;">
                        <div style="font-size:2rem;margin-bottom:0.5rem;">⚖️</div>
                        <h3 style="font-size:1.1rem;font-weight:700;color:var(--text-primary);margin-bottom:0.35rem;">Selecione ao menos 2 ativos para comparar</h3>
                        <p style="font-size:0.85rem;color:var(--text-secondary);max-width:500px;margin:0 auto 1.25rem;">Use o campo de busca acima ou os presets rápidos para comparar ações, fundos imobiliários, FIAGROs ou títulos públicos do Tesouro Direto.</p>
                        <div style="display:flex;gap:0.5rem;justify-content:center;flex-wrap:wrap;">
                            <button type="button" class="action-btn" onclick="addTickerToCompare('PETR4');addTickerToCompare('PRIO3');">PETR4 vs PRIO3</button>
                            <button type="button" class="action-btn" onclick="addTickerToCompare('BBAS3');addTickerToCompare('ITUB4');">BBAS3 vs ITUB4</button>
                            <button type="button" class="action-btn" onclick="addTickerToCompare('HGLG11');addTickerToCompare('BTLG11');">HGLG11 vs BTLG11</button>
                        </div>
                    </div>
                `;
                if (compareChartInstance) {
                    compareChartInstance.destroy();
                    compareChartInstance = null;
                }
                return;
            }

            function getWinnerIdx(vals, higherIsBetter = true) {
                let bestVal = null;
                let bestIdx = -1;
                vals.forEach((v, idx) => {
                    if (v === null || v === undefined || isNaN(v)) return;
                    if (bestVal === null) {
                        bestVal = v;
                        bestIdx = idx;
                    } else if (higherIsBetter && v > bestVal) {
                        bestVal = v;
                        bestIdx = idx;
                    } else if (!higherIsBetter && v < bestVal && v > 0) {
                        bestVal = v;
                        bestIdx = idx;
                    }
                });
                return bestIdx;
            }

            const prices = assets.map(a => a.price || a.buy_price || null);
            const vpas = assets.map(a => a.book_value || null);
            const pes = assets.map(a => a._class === 'stock' && a.pe_ratio !== null && a.pe_ratio !== undefined ? a.pe_ratio : null);
            const pbs = assets.map(a => (a._class === 'stock' || a._class === 'fii' || a._class === 'fiagro') && a.pb_ratio !== null && a.pb_ratio !== undefined ? a.pb_ratio : null);
            const dys = assets.map(a => a.dividend_yield !== null && a.dividend_yield !== undefined ? a.dividend_yield : (a.buy_yield || null));
            const roes = assets.map(a => a._class === 'stock' && a.roe !== null && a.roe !== undefined ? a.roe : null);
            const scores = assets.map(a => a.score || 0);

            const winPe = getWinnerIdx(pes, false);
            const winPb = getWinnerIdx(pbs, false);
            const winDy = getWinnerIdx(dys, true);
            const winRoe = getWinnerIdx(roes, true);
            const winScore = getWinnerIdx(scores, true);

            function renderCell(val, idx, winIdx, formatFn) {
                const isWin = (idx === winIdx && val !== null && val !== undefined);
                const text = formatFn ? formatFn(val) : (val !== null && val !== undefined ? val : '—');
                return `<td class="${isWin ? 'winner' : ''}">${text}</td>`;
            }

            // Check if mixed asset classes are being compared
            const hasMultipleClasses = new Set(assets.map(a => a._class)).size > 1;

            // Filtros de aplicabilidade de metricas
            const hasAnyPvP = assets.some(a => (a._class === 'stock' || a._class === 'fii' || a._class === 'fiagro') && a.pb_ratio !== null && a.pb_ratio !== undefined);
            const hasAnyPe = assets.some(a => a._class === 'stock' && a.pe_ratio !== null && a.pe_ratio !== undefined);
            const hasAnyRoe = assets.some(a => a._class === 'stock' && a.roe !== null && a.roe !== undefined);
            const hasAnyVpa = assets.some(a => a.book_value !== null && a.book_value !== undefined);
            const hasAnyBazin = assets.some(a => a.bazin_price !== null && a.bazin_price !== undefined);
            const hasAnyGraham = assets.some(a => a._class === 'stock' && a.graham_price !== null && a.graham_price !== undefined);
            const hasValuationSection = hasAnyPvP || hasAnyPe || hasAnyRoe || hasAnyVpa || hasAnyBazin || hasAnyGraham;

            const hasAnyTesouro = assets.some(a => a._class === 'tesouro');
            const hasAnyMaturity = assets.some(a => a._class === 'tesouro' || a.maturity);
            const hasFixedIncomeSection = hasAnyTesouro || hasAnyMaturity || hasMultipleClasses;

            let tbodyHtml = `
                <tr>
                    <th colspan="${assets.length + 1}" style="background:var(--surface-2); text-align:left; font-size:0.76rem; text-transform:uppercase; letter-spacing:0.05em; padding:0.45rem 1rem; color:var(--text-secondary);">📊 Métricas Universais de Retorno & Risco</th>
                </tr>
                <tr>
                    <td><strong>Preço / Cotação / PU</strong></td>
                    ${assets.map((a, i) => renderCell(prices[i], i, -1, v => v ? `R$ ${Number(v).toFixed(2)}` : '—')).join('')}
                </tr>
                <tr>
                    <td><strong>Score Radar (0 a 10)</strong></td>
                    ${assets.map((a, i) => renderCell(scores[i], i, winScore, v => `<span class="score-pill ${getScoreRangeClass(v)}" style="display:inline-block;padding:0.2rem 0.6rem;font-size:0.85rem;">${formatScore(v)}</span>`)).join('')}
                </tr>
                <tr>
                    <td><strong>Rendimento Anual (DY / Taxa)</strong></td>
                    ${assets.map((a, i) => renderCell(dys[i], i, winDy, v => v ? `${(v * 100).toFixed(2)}% a.a.` : '—')).join('')}
                </tr>
                <tr>
                    <td><strong>Liquidez & Negociação</strong></td>
                    ${assets.map(a => `<td>${a._class === 'tesouro' ? '<span style="font-size:0.8rem;color:var(--positive);">D+0 / D+1 (Tesouro Nacional)</span>' : '<span style="font-size:0.8rem;color:var(--text-secondary);">D+2 (Mercado B3)</span>'}</td>`).join('')}
                </tr>
            `;

            if (hasValuationSection) {
                tbodyHtml += `
                    <tr>
                        <th colspan="${assets.length + 1}" style="background:var(--surface-2); text-align:left; font-size:0.76rem; text-transform:uppercase; letter-spacing:0.05em; padding:0.45rem 1rem; color:var(--text-secondary);">📈 Valuation & Renda Variável (Ações & FIIs)</th>
                    </tr>
                `;
                if (hasAnyPvP) {
                    tbodyHtml += `
                        <tr>
                            <td><strong>P/VP (Preço / Valor Patr.)</strong></td>
                            ${assets.map((a, i) => {
                                if (a._class === 'tesouro') return `<td style="color:var(--text-muted);font-size:0.76rem;">—</td>`;
                                return renderCell(pbs[i], i, winPb, v => v !== null ? Number(v).toFixed(2) : '—');
                            }).join('')}
                        </tr>
                    `;
                }
                if (hasAnyPe) {
                    tbodyHtml += `
                        <tr>
                            <td><strong>P/L (Preço / Lucro)</strong></td>
                            ${assets.map((a, i) => {
                                if (a._class !== 'stock') return `<td style="color:var(--text-muted);font-size:0.76rem;">—</td>`;
                                return renderCell(pes[i], i, winPe, v => v !== null && v > 0 ? Number(v).toFixed(2) : (v !== null ? 'Negativo' : '—'));
                            }).join('')}
                        </tr>
                    `;
                }
                if (hasAnyRoe) {
                    tbodyHtml += `
                        <tr>
                            <td><strong>ROE (Rentabilidade PL)</strong></td>
                            ${assets.map((a, i) => {
                                if (a._class !== 'stock') return `<td style="color:var(--text-muted);font-size:0.76rem;">—</td>`;
                                return renderCell(roes[i], i, winRoe, v => v !== null ? `${(v * 100).toFixed(2)}%` : '—');
                            }).join('')}
                        </tr>
                    `;
                }
                if (hasAnyVpa) {
                    tbodyHtml += `
                        <tr>
                            <td><strong>VPA (Valor Patr. / Cota)</strong></td>
                            ${assets.map((a, i) => {
                                if (a._class === 'tesouro') return `<td style="color:var(--text-muted);font-size:0.76rem;">—</td>`;
                                return renderCell(vpas[i], i, -1, v => v ? `R$ ${Number(v).toFixed(2)}` : '—');
                            }).join('')}
                        </tr>
                    `;
                }
                if (hasAnyBazin) {
                    tbodyHtml += `
                        <tr>
                            <td><strong>Preço Teto (Bazin)</strong></td>
                            ${assets.map((a, i) => {
                                if (a._class === 'tesouro') return `<td style="color:var(--text-muted);font-size:0.76rem;">—</td>`;
                                return renderCell(a.bazin_price, i, -1, v => v ? `R$ ${Number(v).toFixed(2)}` : '—');
                            }).join('')}
                        </tr>
                    `;
                }
                if (hasAnyGraham) {
                    tbodyHtml += `
                        <tr>
                            <td><strong>Preço Justo (Graham)</strong></td>
                            ${assets.map((a, i) => {
                                if (a._class !== 'stock') return `<td style="color:var(--text-muted);font-size:0.76rem;">—</td>`;
                                return renderCell(a.graham_price, i, -1, v => v ? `R$ ${Number(v).toFixed(2)}` : '—');
                            }).join('')}
                        </tr>
                    `;
                }
            }

            if (hasFixedIncomeSection) {
                tbodyHtml += `
                    <tr>
                        <th colspan="${assets.length + 1}" style="background:var(--surface-2); text-align:left; font-size:0.76rem; text-transform:uppercase; letter-spacing:0.05em; padding:0.45rem 1rem; color:var(--text-secondary);">🏛️ Renda Fixa & Títulos Públicos</th>
                    </tr>
                    <tr>
                        <td><strong>Indexador / Motor de Retorno</strong></td>
                        ${assets.map(a => {
                            if (a._class === 'tesouro') return `<td style="font-weight:600;color:var(--gold);font-size:0.82rem;">${a.type || 'Público Federal'}</td>`;
                            if (a._class === 'fii') return `<td style="font-size:0.8rem;color:var(--text-secondary);">Aluguéis / CRI</td>`;
                            if (a._class === 'fiagro') return `<td style="font-size:0.8rem;color:var(--text-secondary);">Crédito Agro (CRA)</td>`;
                            return `<td style="font-size:0.8rem;color:var(--text-secondary);">Lucros & Dividendos</td>`;
                        }).join('')}
                    </tr>
                `;
                if (hasAnyMaturity) {
                    tbodyHtml += `
                        <tr>
                            <td><strong>Vencimento / Prazo</strong></td>
                            ${assets.map(a => {
                                if (a._class === 'tesouro') return `<td style="font-weight:600;color:var(--text-primary);font-size:0.82rem;">${a.maturity || 'Data Contratual'}</td>`;
                                return `<td style="font-size:0.8rem;color:var(--text-secondary);">Perpétua (Sem Vencimento)</td>`;
                            }).join('')}
                        </tr>
                    `;
                }
            }

            contentContainer.innerHTML = `
                ${presetButtonsHtml}

                ${hasMultipleClasses ? `
                <div style="margin-bottom:1rem; padding:0.75rem 1rem; background:rgba(59, 130, 246, 0.08); border-left:4px solid var(--primary-accent); border-radius:var(--radius-sm); font-size:0.8rem; color:var(--text-secondary); line-height:1.45;">
                    💡 <strong>Comparação Multi-Classes:</strong> Indicadores universais (Preço, Score, Yield) são comparados diretamente. Métricas específicas de empresas (P/L, ROE, Graham) trazem observações contextuais para os títulos de Renda Fixa e FIIs.
                </div>
                ` : ''}

                <div class="compare-table-card">
                    <div class="table-scroll">
                        <table class="compare-table">
                            <thead>
                                <tr>
                                    <th>Indicador / Métrica</th>
                                    ${assets.map(a => `
                                        <th>
                                            <div style="display:flex;flex-direction:column;align-items:center;gap:0.2rem;">
                                                <strong style="font-size:1.05rem;color:var(--text-primary);cursor:pointer;" onclick="${a._class === 'tesouro' ? `openTdDetailFromHome('${a.name.replace(/'/g, "\\'")}')` : `openDetailModal('${a.ticker}', '${a._class}')`}">${a.ticker || a.name} ↗</strong>
                                                <span style="font-size:0.75rem;color:var(--text-secondary);font-weight:normal;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${a.name || ''}</span>
                                                <span class="index-pill" style="font-size:0.65rem;">${a._classLabel}</span>
                                            </div>
                                        </th>
                                    `).join('')}
                                </tr>
                            </thead>
                            <tbody>
                                ${tbodyHtml}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="compare-chart-card" style="margin-top:1.25rem;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;">
                        <div>
                            <h3 style="font-size:0.95rem;font-weight:700;color:var(--text-primary);">Desempenho Relativo de Preço (% nos últimos 12 meses)</h3>
                            <p style="font-size:0.78rem;color:var(--text-muted);">Variação percentual normalizada base 0% para comparar a trajetória de rentabilidade.</p>
                        </div>
                    </div>
                    <div style="position:relative;height:260px;width:100%;">
                        <canvas id="compare-chart-canvas"></canvas>
                    </div>
                </div>
            `;

            renderCompareChart(assets);
        }

        function renderCompareChart(assets) {
            const canvas = document.getElementById('compare-chart-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            if (compareChartInstance) {
                compareChartInstance.destroy();
                compareChartInstance = null;
            }

            const palette = ['#3b82f6', '#10b981', '#f59e0b', '#a855f7'];
            const datasets = [];
            let commonDates = [];

            assets.forEach((asset, idx) => {
                let history = [];
                try {
                    if (asset.history && Array.isArray(asset.history)) {
                        history = asset.history;
                    } else if (asset.history_json) {
                        history = typeof asset.history_json === 'string' ? JSON.parse(asset.history_json) : asset.history_json;
                    }
                } catch (e) {
                    history = [];
                }
                if (!history || history.length < 2) return;

                const sampled = history.length > 14 ? history.slice(-14) : history;
                if (commonDates.length === 0) {
                    commonDates = sampled.map(h => {
                        const parts = (h.date || '').split('-');
                        return parts.length >= 2 ? `${parts[1]}/${parts[0]}` : h.date;
                    });
                }

                const basePrice = (sampled[0].price != null ? Number(sampled[0].price) : (Number(sampled[0].buy_price) || 1));
                const dataPct = sampled.map(h => {
                    const p = (h.price != null ? Number(h.price) : (Number(h.buy_price) || basePrice));
                    return Number((((p - basePrice) / basePrice) * 100).toFixed(2));
                });

                const color = palette[idx % palette.length];
                datasets.push({
                    label: asset.ticker || asset.name,
                    data: dataPct,
                    borderColor: color,
                    backgroundColor: 'transparent',
                    borderWidth: 2.5,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    tension: 0.2
                });
            });

            if (datasets.length === 0) return;

            const isLight = !document.body.classList.contains('dark');
            const gridColor = isLight ? '#e2e4ea' : '#282c38';
            const tickColor = isLight ? '#6b7084' : '#8b8fa3';

            compareChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: commonDates,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: {
                            display: true,
                            labels: { color: tickColor, font: { size: 11, weight: '600', family: 'Inter, sans-serif' } }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return ` ${context.dataset.label}: ${context.parsed.y >= 0 ? '+' : ''}${context.parsed.y.toFixed(2)}%`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { color: tickColor, font: { size: 10, family: 'Inter, sans-serif' } }
                        },
                        y: {
                            grid: { color: gridColor },
                            ticks: {
                                color: tickColor,
                                font: { size: 10, family: 'Inter, sans-serif' },
                                callback: v => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
                            }
                        }
                    }
                }
            });
        }

        /* ── Calculadora / Simulador de Renda Passiva & Bola de Neve ── */
        let snowballChartInstance = null;
        let previdenciaChartInstance = null;
        let currentCalcMode = 'goal';

        function switchCalcMode(mode) {
            currentCalcMode = mode;
            const btnGoal = document.getElementById('btn-calc-mode-goal');
            const btnSnow = document.getElementById('btn-calc-mode-snowball');
            const btnRf = document.getElementById('btn-calc-mode-compare-rf');
            const btnPrev = document.getElementById('btn-calc-mode-previdencia');
            const btnFire = document.getElementById('btn-calc-mode-fire');
            const btnRules = document.getElementById('btn-calc-mode-rules');

            const gridGoal = document.getElementById('calc-grid-goal');
            const gridSnow = document.getElementById('calc-grid-snowball');
            const gridRf = document.getElementById('calc-grid-compare-rf');
            const gridPrev = document.getElementById('calc-grid-previdencia');
            const gridFire = document.getElementById('calc-grid-fire');
            const gridRules = document.getElementById('calc-grid-rules');

            if (btnGoal) btnGoal.classList.toggle('active', mode === 'goal');
            if (btnSnow) btnSnow.classList.toggle('active', mode === 'snowball');
            if (btnRf) btnRf.classList.toggle('active', mode === 'compare_rf');
            if (btnPrev) btnPrev.classList.toggle('active', mode === 'previdencia');
            if (btnFire) btnFire.classList.toggle('active', mode === 'fire');
            if (btnRules) btnRules.classList.toggle('active', mode === 'rules');

            if (gridGoal) gridGoal.classList.toggle('hidden', mode !== 'goal');
            if (gridSnow) gridSnow.classList.toggle('hidden', mode !== 'snowball');
            if (gridRf) gridRf.classList.toggle('hidden', mode !== 'compare_rf');
            if (gridPrev) gridPrev.classList.toggle('hidden', mode !== 'previdencia');
            if (gridFire) gridFire.classList.toggle('hidden', mode !== 'fire');
            if (gridRules) gridRules.classList.toggle('hidden', mode !== 'rules');

            if (mode === 'goal') calculateIncomeGoal();
            else if (mode === 'snowball') calculateSnowball();
            else if (mode === 'compare_rf') calculateRfComparison();
            else if (mode === 'previdencia') {
                updatePrevidenciaDiagnostic();
                calculatePrevidencia();
            }
            else if (mode === 'fire') calculateFireRetirement();
            else if (mode === 'rules') calculateAllRules();
        }

        function setGoalPreset(val) {
            const input = document.getElementById('calc-goal-target');
            if (input) {
                input.value = val;
                const buttons = document.querySelectorAll('#calc-grid-goal .calc-preset-btn');
                buttons.forEach(b => b.classList.toggle('active', b.textContent.includes(val.toLocaleString('pt-BR'))));
                calculateIncomeGoal();
            }
        }

        function setSnowMonthlyPreset(val) {
            const input = document.getElementById('calc-snow-monthly');
            if (input) {
                input.value = val;
                const buttons = document.querySelectorAll('#calc-grid-snowball .calc-preset-btn');
                buttons.forEach(b => b.classList.toggle('active', b.textContent.includes(val.toLocaleString('pt-BR'))));
                calculateSnowball();
            }
        }

        function setRfAmountPreset(val) {
            const input = document.getElementById('calc-rf-amount');
            if (input) {
                input.value = val;
                const buttons = document.querySelectorAll('#calc-grid-compare-rf .calc-preset-btn');
                buttons.forEach(b => b.classList.toggle('active', b.textContent.includes(val.toLocaleString('pt-BR'))));
                calculateRfComparison();
            }
        }

        function setPrevIncomePreset(val) {
            const input = document.getElementById('calc-prev-income');
            if (input) {
                input.value = val;
                const buttons = document.querySelectorAll('#calc-grid-previdencia .calc-preset-btn');
                buttons.forEach(b => b.classList.toggle('active', b.textContent.includes(`${val / 1000}k`)));
                calculatePrevidencia();
            }
        }

        function onPrevPctChange(val) {
            const badge = document.getElementById('calc-prev-pct-badge');
            if (badge) {
                badge.textContent = `${val}% ${val == 12 ? '(Teto Legal PGBL)' : ''}`;
            }
            calculatePrevidencia();
        }

        function setFireCapitalPreset(val) {
            const input = document.getElementById('calc-fire-capital');
            if (input) {
                input.value = val;
                const buttons = document.querySelectorAll('#calc-grid-fire .calc-preset-btn');
                buttons.forEach(b => b.classList.toggle('active', b.textContent.includes(val >= 1000000 ? `${val / 1000000} Milh` : `${val / 1000}k`)));
                calculateFireRetirement();
            }
        }

        function getCalculatorAssetCatalog() {
            const data = window.dashboardData || {};
            const macro = data.macro_state || {};
            const selicMeta = macro.selic_meta != null ? macro.selic_meta : (macro.selic != null ? macro.selic : 0.14);
            const ipcaFocus = (macro.focus_ipca && macro.focus_ipca[0] != null) ? macro.focus_ipca[0] : 0.045;

            const catalog = [];

            // 1. Estratégias Diversificadas
            catalog.push(
                { id: 'custom', category: 'strategies', label: 'Estratégia Customizada (DY manual)', dy: 9.0, price: 0, taxType: 'exempt' },
                { id: 'top_brasil', category: 'strategies', label: 'Top Brasil Diversificado (DY ~9.5%)', dy: 9.5, price: 0, taxType: 'exempt' },
                { id: 'top_stocks', category: 'strategies', label: 'Top Ações Dividendos (DY ~8.5%)', dy: 8.5, price: 0, taxType: 'stock' },
                { id: 'top_fiis', category: 'strategies', label: 'Top FIIs Imobiliários (DY ~10.5%)', dy: 10.5, price: 0, taxType: 'exempt' },
                { id: 'top_tesouro', category: 'strategies', label: 'Top Tesouro IPCA+ / Selic (Yield ~12.5%)', dy: 12.5, price: 1000, taxType: 'tesouro' }
            );

            // 2. Ações B3
            if (Array.isArray(data.stocks)) {
                data.stocks.slice(0, 30).forEach(s => {
                    const dy = (Number(s.dividend_yield) || 0) * 100;
                    if (dy > 0) {
                        catalog.push({
                            id: s.ticker,
                            category: 'stocks',
                            label: `${s.ticker} - ${s.name || ''} (DY ${dy.toFixed(1)}%)`,
                            dy: dy,
                            price: Number(s.price) || 0,
                            taxType: 'stock'
                        });
                    }
                });
            }

            // 3. FIIs
            if (Array.isArray(data.fiis)) {
                data.fiis.slice(0, 30).forEach(f => {
                    const dy = (Number(f.dividend_yield) || 0) * 100;
                    if (dy > 0) {
                        catalog.push({
                            id: f.ticker,
                            category: 'fiis',
                            label: `${f.ticker} - ${f.name || ''} (DY ${dy.toFixed(1)}%)`,
                            dy: dy,
                            price: Number(f.price) || 0,
                            taxType: 'exempt'
                        });
                    }
                });
            }

            // 4. FIAGROs
            if (Array.isArray(data.fiagros)) {
                data.fiagros.slice(0, 20).forEach(fg => {
                    const dy = (Number(fg.dividend_yield) || 0) * 100;
                    if (dy > 0) {
                        catalog.push({
                            id: fg.ticker,
                            category: 'fiagros',
                            label: `${fg.ticker} - ${fg.name || ''} (DY ${dy.toFixed(1)}%)`,
                            dy: dy,
                            price: Number(fg.price) || 0,
                            taxType: 'exempt'
                        });
                    }
                });
            }

            // 5. Tesouro Direto
            const tdList = Array.isArray(data.tesouro_direto) ? data.tesouro_direto : [];
            tdList.forEach(td => {
                const buyYield = Number(td.buy_yield) || 0;
                let nominalYield = buyYield * 100;
                const tipo = (td.type || td.group || '').toLowerCase();
                const name = (td.name || td.ticker || '').toLowerCase();
                const hasCoupon = name.includes('juros semestrais') || name.includes('com juros') || tipo.includes('com juros') || tipo.includes('renda+') || tipo.includes('educa+');
                if (tipo.includes('selic') || td.yield_kind === 'selic_spread') {
                    nominalYield = (selicMeta + buyYield) * 100;
                } else if (tipo.includes('ipca')) {
                    nominalYield = (((1 + ipcaFocus) * (1 + buyYield) - 1)) * 100;
                }
                const price = Number(td.buy_price || td.unit_price || td.price) || 1000;
                catalog.push({
                    id: td.name || td.ticker,
                    category: 'tesouro',
                    label: `${td.name || td.ticker} (Yield ~${nominalYield.toFixed(2)}% a.a.)`,
                    dy: nominalYield,
                    price: price,
                    taxType: 'tesouro',
                    hasCoupon: hasCoupon
                });
            });

            return catalog;
        }

        function populateCalculatorSelects() {
            if (!window.dashboardData) return;
            filterCalculatorAssets('goal');
            filterCalculatorAssets('snow');
        }

        function filterCalculatorAssets(mode) {
            const categorySelect = document.getElementById(mode === 'goal' ? 'calc-goal-category' : 'calc-snow-category');
            const assetSelect = document.getElementById(mode === 'goal' ? 'calc-goal-asset' : 'calc-snow-asset');
            if (!categorySelect || !assetSelect) return;

            const selectedCat = categorySelect.value || 'all';
            const catalog = getCalculatorAssetCatalog();
            const filtered = selectedCat === 'all' ? catalog : catalog.filter(item => item.category === selectedCat);

            assetSelect.innerHTML = filtered.map(item => {
                return `<option value="${item.id}" data-category="${item.category}" data-dy="${item.dy.toFixed(2)}" data-price="${item.price.toFixed(2)}" data-tax="${item.taxType}" data-has-coupon="${item.hasCoupon ? 'true' : 'false'}">${item.label}</option>`;
            }).join('');

            if (mode === 'goal') {
                onGoalAssetChange();
            } else {
                onSnowballAssetChange();
            }
        }

        function onGoalCategoryChange() {
            filterCalculatorAssets('goal');
        }

        function onSnowCategoryChange() {
            filterCalculatorAssets('snow');
        }

        function onGoalAssetChange() {
            const select = document.getElementById('calc-goal-asset');
            const dyInput = document.getElementById('calc-goal-custom-dy');
            if (!select || !dyInput) return;
            const opt = select.selectedOptions[0];
            if (opt && opt.dataset.dy) {
                dyInput.value = parseFloat(opt.dataset.dy).toFixed(1);
            }
            calculateIncomeGoal();
        }

        function onSnowballAssetChange() {
            const select = document.getElementById('calc-snow-asset');
            const dyInput = document.getElementById('calc-snow-dy');
            if (!select || !dyInput) return;
            const opt = select.selectedOptions[0];
            if (opt && opt.dataset.dy) {
                dyInput.value = parseFloat(opt.dataset.dy).toFixed(1);
            }
            calculateSnowball();
        }

        function _getEffectiveTaxRate(taxSelectorVal, assetTaxType) {
            if (taxSelectorVal === 'exempt') return 0;
            if (taxSelectorVal === 'stock_jcp') return 0.0375; // ~25% JCP tributado a 15%
            if (taxSelectorVal === 'fixed_15') return 0.15;
            if (taxSelectorVal === 'fixed_22_5') return 0.225;
            // auto
            if (assetTaxType === 'exempt') return 0;
            if (assetTaxType === 'stock') return 0.0375; // Estimativa média ponderada B3
            if (assetTaxType === 'tesouro') return 0.15; // Regressiva longo prazo > 2 anos
            return 0;
        }

        function calculateIncomeGoal() {
            const targetEl = document.getElementById('calc-goal-target');
            const dyEl = document.getElementById('calc-goal-custom-dy');
            const taxSelect = document.getElementById('calc-goal-tax');
            const assetSelect = document.getElementById('calc-goal-asset');

            const totalEl = document.getElementById('calc-goal-result-total');
            const netEl = document.getElementById('calc-goal-result-net');
            const grossEl = document.getElementById('calc-goal-result-gross');
            const taxEl = document.getElementById('calc-goal-result-tax');
            const netYieldEl = document.getElementById('calc-goal-result-net-yield');
            const sharesRow = document.getElementById('calc-goal-shares-row');
            const sharesEl = document.getElementById('calc-goal-result-shares');
            const dailyEl = document.getElementById('calc-goal-result-daily');
            const magicDescEl = document.getElementById('calc-goal-magic-desc');

            if (!targetEl || !dyEl || !totalEl) return;

            const monthlyNetTarget = parseFloat(targetEl.value) || 0;
            const grossDyAnnual = (parseFloat(dyEl.value) || 9.0) / 100;

            const opt = assetSelect ? assetSelect.selectedOptions[0] : null;
            const assetTaxType = opt ? (opt.dataset.tax || 'exempt') : 'exempt';
            const taxMode = taxSelect ? taxSelect.value : 'auto';
            const taxRate = _getEffectiveTaxRate(taxMode, assetTaxType);

            const netDyAnnual = grossDyAnnual * (1 - taxRate);
            const annualNetTarget = monthlyNetTarget * 12;
            const totalRequired = netDyAnnual > 0 ? (annualNetTarget / netDyAnnual) : 0;
            const annualGross = (1 - taxRate) > 0 ? (annualNetTarget / (1 - taxRate)) : annualNetTarget;
            const monthlyGross = annualGross / 12;
            const annualTax = annualGross - annualNetTarget;
            const dailyNet = annualNetTarget / 365;

            totalEl.textContent = `R$ ${totalRequired.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (netEl) netEl.textContent = `R$ ${monthlyNetTarget.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / mês`;
            if (grossEl) grossEl.textContent = `R$ ${monthlyGross.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / mês (R$ ${annualGross.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / ano)`;
            if (taxEl) {
                const taxPctStr = (taxRate * 100).toFixed(2);
                taxEl.textContent = taxRate > 0 ? `R$ ${annualTax.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / ano (${taxPctStr}%)` : `R$ 0,00 (Isento)`;
            }
            if (netYieldEl) netYieldEl.textContent = `${(netDyAnnual * 100).toFixed(2)}% a.a. (Bruto: ${(grossDyAnnual * 100).toFixed(2)}%)`;
            if (dailyEl) dailyEl.textContent = `R$ ${dailyNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / dia líquido`;

            let price = 0;
            let cat = 'stocks';
            let hasCoupon = true;
            if (opt) {
                price = parseFloat(opt.dataset.price) || 0;
                cat = opt.dataset.category || 'stocks';
                hasCoupon = opt.dataset.hasCoupon !== 'false';
            }

            if (price > 0 && sharesEl && sharesRow) {
                const unitCount = Math.ceil(totalRequired / price);
                const unitName = cat === 'tesouro' ? 'títulos' : (cat === 'stocks' ? 'ações' : 'cotas');
                sharesRow.classList.remove('hidden');
                sharesEl.textContent = `${unitCount.toLocaleString('pt-BR')} ${unitName} (a R$ ${price.toFixed(2)})`;
            } else if (sharesRow) {
                sharesRow.classList.add('hidden');
            }

            if (magicDescEl) {
                if (cat === 'tesouro') {
                    if (!hasCoupon) {
                        magicDescEl.textContent = `⚠️ Título sem cupom: os rendimentos não caem mensalmente na conta e são pagos integralmente no vencimento/resgate. Para renda periódica, utilize títulos com Juros Semestrais, FIIs ou Ações de dividendos.`;
                    } else {
                        magicDescEl.textContent = `Títulos do Tesouro com juros semestrais pagam cupons diretamente na conta com retenção de IR na fonte (15% após 2 anos).`;
                    }
                } else if (cat === 'fiis' || cat === 'fiagros') {
                    magicDescEl.textContent = `Rendimentos mensais de FIIs e FIAGROs são 100% isentos de Imposto de Renda para pessoas físicas.`;
                } else {
                    magicDescEl.textContent = `Ações distribuem dividendos isentos e JCP tributado em 15% na fonte, com alíquota média combinada de ~3,75%.`;
                }
            }
        }

        function calculateSnowball() {
            const initialEl = document.getElementById('calc-snow-initial');
            const monthlyEl = document.getElementById('calc-snow-monthly');
            const dyEl = document.getElementById('calc-snow-dy');
            const yearsEl = document.getElementById('calc-snow-years');
            const taxSelect = document.getElementById('calc-snow-tax');
            const assetSelect = document.getElementById('calc-snow-asset');

            const totalEl = document.getElementById('calc-snow-result-total');
            const investedEl = document.getElementById('calc-snow-result-invested');
            const divEl = document.getElementById('calc-snow-result-dividends');
            const taxEl = document.getElementById('calc-snow-result-tax');
            const monthlyIncomeEl = document.getElementById('calc-snow-result-monthly-income');
            const magicTitleEl = document.getElementById('calc-magic-number-title');
            const magicDescEl = document.getElementById('calc-magic-number-desc');
            const magicIconEl = document.getElementById('calc-snow-magic-icon');
            const magicCardTitleEl = document.getElementById('calc-snow-card-title');
            const monthlyIncomeLabelEl = document.getElementById('calc-snow-monthly-income-label');
            const divLabelEl = document.getElementById('calc-snow-result-dividends-label');

            if (!initialEl || !monthlyEl || !dyEl || !yearsEl) return;

            const initialCapital = parseFloat(initialEl.value) || 0;
            const monthlyContribution = parseFloat(monthlyEl.value) || 0;
            const grossAnnualDy = (parseFloat(dyEl.value) || 10.0) / 100;

            const opt = assetSelect ? assetSelect.selectedOptions[0] : null;
            const assetTaxType = opt ? (opt.dataset.tax || 'exempt') : 'exempt';
            const taxMode = taxSelect ? taxSelect.value : 'auto';
            const taxRate = _getEffectiveTaxRate(taxMode, assetTaxType);

            const netAnnualDy = grossAnnualDy * (1 - taxRate);
            const monthlyNetRate = Math.pow(1 + netAnnualDy, 1 / 12) - 1;
            const years = parseInt(yearsEl.value, 10) || 5;
            const months = years * 12;

            let balance = initialCapital;
            let totalInvested = initialCapital;
            let historyPoints = [];

            for (let m = 1; m <= months; m++) {
                const netDividend = balance * monthlyNetRate;
                balance = balance + netDividend + monthlyContribution;
                totalInvested += monthlyContribution;

                if (m % 12 === 0 || m === months) {
                    historyPoints.push({
                        year: `Ano ${Math.round(m / 12)}`,
                        invested: Math.round(totalInvested),
                        balance: Math.round(balance),
                        dividends: Math.round(balance - totalInvested)
                    });
                }
            }

            const finalDividendsNet = Math.max(0, balance - totalInvested);
            const finalDividendsGross = (1 - taxRate) > 0 ? (finalDividendsNet / (1 - taxRate)) : finalDividendsNet;
            const finalTaxEstimated = finalDividendsGross - finalDividendsNet;
            const finalMonthlyNetIncome = balance * monthlyNetRate;

            if (totalEl) totalEl.textContent = `R$ ${balance.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (investedEl) investedEl.textContent = `R$ ${totalInvested.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (divEl) divEl.textContent = `R$ ${finalDividendsNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (taxEl) {
                taxEl.textContent = taxRate > 0 ? `R$ ${finalTaxEstimated.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${(taxRate * 100).toFixed(1)}% retido)` : `R$ 0,00 (Isento)`;
            }

            let price = 0;
            let cat = 'stocks';
            let hasCoupon = true;
            if (opt) {
                price = parseFloat(opt.dataset.price) || 0;
                cat = opt.dataset.category || 'stocks';
                hasCoupon = opt.dataset.hasCoupon !== 'false';
            }

            const isNonCouponTreasury = (cat === 'tesouro' && !hasCoupon);

            if (isNonCouponTreasury) {
                if (magicCardTitleEl) magicCardTitleEl.textContent = 'Acumulação de Capital & Juros Compostos';
                if (magicIconEl) magicIconEl.textContent = '🏛️';
                if (magicTitleEl) magicTitleEl.textContent = 'Título sem Cupom (Capitalização no PU)';
                if (magicDescEl) {
                    magicDescEl.textContent = `Este título capitaliza juros e correção diretamente no Preço Unitário (PU). Não há distribuição periódica em conta corrente: o rendimento total apurado (R$ ${finalDividendsNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}) é creditado no resgate ou vencimento.`;
                }
                if (divLabelEl) divLabelEl.textContent = 'Rentabilidade Acumulada em Juros/Correção (Líquida):';
                if (monthlyIncomeLabelEl) monthlyIncomeLabelEl.textContent = 'Rendimento Médio Mensal Equivalente (no Vencimento):';
                if (monthlyIncomeEl) monthlyIncomeEl.textContent = `R$ ${finalMonthlyNetIncome.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / mês (acumulado)`;
            } else {
                if (magicCardTitleEl) magicCardTitleEl.textContent = 'Projeção de Acúmulo & Reinvestimento Autossustentável';
                if (magicIconEl) magicIconEl.textContent = '';
                if (divLabelEl) divLabelEl.textContent = 'Rendimento Gerado por Juros/Dividendos (Líquido):';
                if (monthlyIncomeLabelEl) monthlyIncomeLabelEl.textContent = 'Renda Mensal Líquida no Final do Período:';
                if (monthlyIncomeEl) monthlyIncomeEl.textContent = `R$ ${finalMonthlyNetIncome.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / mês líquido`;

                const unitName = cat === 'tesouro' ? 'títulos' : (cat === 'stocks' ? 'ações' : 'cotas');
                const singleUnitName = cat === 'tesouro' ? 'novo título' : (cat === 'stocks' ? 'nova ação' : 'nova cota');

                if (price > 0 && monthlyNetRate > 0) {
                    const magicNumber = Math.ceil(1 / monthlyNetRate);
                    const magicCapital = magicNumber * price;
                    if (magicTitleEl) magicTitleEl.textContent = `Ponto de Reinvestimento Automático: ${magicNumber.toLocaleString('pt-BR')} ${unitName}`;
                    if (magicDescEl) magicDescEl.textContent = `Com patrimônio de R$ ${magicCapital.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} alocado, os proventos mensais líquidos financiam a compra de 1 ${singleUnitName}/mês de forma autossuficiente.`;
                } else if (monthlyNetRate > 0) {
                    const magicNumber = Math.ceil(1 / monthlyNetRate);
                    if (magicTitleEl) magicTitleEl.textContent = `Fator de Autossuficiência: ~${magicNumber}x`;
                    if (magicDescEl) magicDescEl.textContent = `À taxa líquida de ${(netAnnualDy * 100).toFixed(2)}% a.a., cada R$ ${(1 / monthlyNetRate * 100).toFixed(0)} alocados geram R$ 100 de fluxo mensal para novos aportes.`;
                }
            }

            // Atualiza barra de progresso visual
            const pctInvested = balance > 0 ? Math.min(100, Math.max(0, Math.round((totalInvested / balance) * 100))) : 50;
            const pctReturns = 100 - pctInvested;
            const barInvested = document.getElementById('calc-snow-bar-invested');
            const barReturns = document.getElementById('calc-snow-bar-returns');
            const textInvested = document.getElementById('calc-snow-pct-invested');
            const textReturns = document.getElementById('calc-snow-pct-returns');

            if (barInvested) barInvested.style.width = `${pctInvested}%`;
            if (barReturns) barReturns.style.width = `${pctReturns}%`;
            if (textInvested) textInvested.textContent = `${pctInvested}% (R$ ${totalInvested.toLocaleString('pt-BR', { maximumFractionDigits: 0 })})`;
            if (textReturns) textReturns.textContent = `${pctReturns}% (R$ ${finalDividendsNet.toLocaleString('pt-BR', { maximumFractionDigits: 0 })})`;

            renderSnowballChart(historyPoints);
        }

        function renderSnowballChart(points) {
            const canvas = document.getElementById('snowball-chart');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            if (snowballChartInstance) {
                snowballChartInstance.destroy();
                snowballChartInstance = null;
            }
            if (!points || points.length === 0) return;

            const isLight = !document.body.classList.contains('dark');
            const gridColor = isLight ? '#e2e4ea' : '#282c38';
            const tickColor = isLight ? '#6b7084' : '#8b8fa3';

            snowballChartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: points.map(p => p.year),
                    datasets: [
                        {
                            label: 'Total Aportado',
                            data: points.map(p => p.invested),
                            backgroundColor: isLight ? 'rgba(100, 116, 139, 0.4)' : 'rgba(148, 163, 184, 0.4)',
                            borderColor: isLight ? '#64748b' : '#94a3b8',
                            borderWidth: 1,
                            borderRadius: 4
                        },
                        {
                            label: 'Patrimônio Total (c/ Dividendos)',
                            data: points.map(p => p.balance),
                            backgroundColor: '#10b981',
                            borderColor: '#059669',
                            borderWidth: 1,
                            borderRadius: 4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        valueLabels: false,
                        keyValueLabels: false,
                        legend: {
                            display: true,
                            labels: { color: tickColor, font: { size: 10, weight: '600', family: 'Inter, sans-serif' } }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return ` ${context.dataset.label}: R$ ${context.parsed.y.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { color: tickColor, font: { size: 10, family: 'Inter, sans-serif' } }
                        },
                        y: {
                            grid: { color: gridColor },
                            ticks: {
                                color: tickColor,
                                maxTicksLimit: 5,
                                font: { size: 10, family: 'Inter, sans-serif' },
                                callback: v => `R$ ${(v / 1000).toFixed(0)}k`
                            }
                        }
                    }
                }
            });
        }

        function calculateRfComparison() {
            const amountInput = document.getElementById('calc-rf-amount');
            const daysSelect = document.getElementById('calc-rf-days');
            const cdiInput = document.getElementById('calc-rf-cdi');
            const cdbPctInput = document.getElementById('calc-rf-cdb-pct');
            const lciPctInput = document.getElementById('calc-rf-lci-pct');
            const tdYieldInput = document.getElementById('calc-rf-td-yield');

            const amount = Math.max(100, parseFloat(amountInput?.value) || 10000);
            const days = parseInt(daysSelect?.value) || 720;
            const years = days / 365.0;
            const cdiRate = (parseFloat(cdiInput?.value) || 13.0) / 100.0;
            const cdbPct = (parseFloat(cdbPctInput?.value) || 100.0) / 100.0;
            const lciPct = (parseFloat(lciPctInput?.value) || 90.0) / 100.0;
            const tdYield = (parseFloat(tdYieldInput?.value) || 13.25) / 100.0;

            // Alíquota regressiva de IR Renda Fixa
            let taxRate = 0.15;
            if (days <= 180) taxRate = 0.225;
            else if (days <= 360) taxRate = 0.20;
            else if (days <= 720) taxRate = 0.175;
            else taxRate = 0.15;

            // 0. Poupança (Isenta de IR: 70% Selic se <= 8.5% ou 0.5% a.m. + TR se > 8.5%)
            let poupancaAnnualRate = 0.0617;
            if (cdiRate > 0.085) {
                poupancaAnnualRate = 0.0617 + 0.005; // 0.5% a.m. (~6.17% a.a.) + ~0.5% TR
            } else {
                poupancaAnnualRate = cdiRate * 0.70;
            }
            const poupancaNet = amount * Math.pow(1 + poupancaAnnualRate, years);

            // 1. CDB (Tributado)
            const cdbGrossAnnual = cdiRate * cdbPct;
            const cdbTotalGross = amount * Math.pow(1 + cdbGrossAnnual, years);
            const cdbProfitGross = cdbTotalGross - amount;
            const cdbTax = cdbProfitGross * taxRate;
            const cdbNet = cdbTotalGross - cdbTax;

            // 2. LCI / LCA (Isento de IR)
            const lciNetAnnual = cdiRate * lciPct;
            const lciNet = amount * Math.pow(1 + lciNetAnnual, years);

            // 3. Tesouro Direto (Tributado)
            const tdTotalGross = amount * Math.pow(1 + tdYield, years);
            const tdProfitGross = tdTotalGross - amount;
            const tdTax = tdProfitGross * taxRate;
            const tdNet = tdTotalGross - tdTax;

            // Atualiza UI
            const poupancaRateInfoEl = document.getElementById('calc-poupanca-rate-info');
            const poupancaNetValEl = document.getElementById('calc-poupanca-net-val');
            const cdbGrossTaxEl = document.getElementById('calc-cdb-gross-tax');
            const cdbNetValEl = document.getElementById('calc-cdb-net-val');
            const lciGrossTaxEl = document.getElementById('calc-lci-gross-tax');
            const lciNetValEl = document.getElementById('calc-lci-net-val');
            const tdGrossTaxEl = document.getElementById('calc-td-gross-tax');
            const tdNetValEl = document.getElementById('calc-td-net-val');

            if (poupancaRateInfoEl) poupancaRateInfoEl.textContent = `${(poupancaAnnualRate * 100).toFixed(2)}% a.a. (0.0% Isento)`;
            if (poupancaNetValEl) poupancaNetValEl.textContent = `R$ ${poupancaNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

            if (cdbGrossTaxEl) cdbGrossTaxEl.textContent = `${(cdbGrossAnnual * 100).toFixed(2)}% a.a. (IR ${(taxRate * 100).toFixed(1)}%)`;
            if (cdbNetValEl) cdbNetValEl.textContent = `R$ ${cdbNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

            if (lciGrossTaxEl) lciGrossTaxEl.textContent = `${(lciNetAnnual * 100).toFixed(2)}% a.a. (0.0% Isento)`;
            if (lciNetValEl) lciNetValEl.textContent = `R$ ${lciNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

            if (tdGrossTaxEl) tdGrossTaxEl.textContent = `${(tdYield * 100).toFixed(2)}% a.a. (IR ${(taxRate * 100).toFixed(1)}%)`;
            if (tdNetValEl) tdNetValEl.textContent = `R$ ${tdNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

            // Identifica o Vencedor
            const cardCdb = document.getElementById('calc-card-cdb');
            const cardLci = document.getElementById('calc-card-lci');
            const cardTd = document.getElementById('calc-card-td');
            const badgeCdb = document.getElementById('badge-winner-cdb');
            const badgeLci = document.getElementById('badge-winner-lci');
            const badgeTd = document.getElementById('badge-winner-td');

            const maxNet = Math.max(cdbNet, lciNet, tdNet);

            if (cardCdb) cardCdb.classList.toggle('winner', Math.abs(cdbNet - maxNet) < 0.01);
            if (badgeCdb) badgeCdb.classList.toggle('hidden', Math.abs(cdbNet - maxNet) >= 0.01);

            if (cardLci) cardLci.classList.toggle('winner', Math.abs(lciNet - maxNet) < 0.01);
            if (badgeLci) badgeLci.classList.toggle('hidden', Math.abs(lciNet - maxNet) >= 0.01);

            if (cardTd) cardTd.classList.toggle('winner', Math.abs(tdNet - maxNet) < 0.01);
            if (badgeTd) badgeTd.classList.toggle('hidden', Math.abs(tdNet - maxNet) >= 0.01);

            // Alerta Custo de Oportunidade da Poupança
            const lossVsBest = Math.max(0, maxNet - poupancaNet);
            const lossDescEl = document.getElementById('calc-poupanca-loss-desc');
            if (lossDescEl) {
                lossDescEl.textContent = `A alocação na Poupança resulta em uma renúncia de rendimento líquido estimada em R$ ${lossVsBest.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} no período em comparação à alternativa mais rentável de Renda Fixa.`;
            }

            // Ponto de Equilíbrio (Break-Even)
            const cdbEquiv = (lciPct / (1 - taxRate)) * 100;
            const equivDescEl = document.getElementById('calc-rf-equiv-desc');
            if (equivDescEl) {
                equivDescEl.textContent = `Para o prazo de ${days} dias (alíquota regressiva de IR: ${(taxRate * 100).toFixed(1)}%), um título isento a ${(lciPct * 100).toFixed(0)}% do CDI equivale a um ativo tributado a ${cdbEquiv.toFixed(1)}% do CDI.`;
            }
        }

        /* ── Módulo de Previdência Privada: PGBL x VGBL ── */

        function updatePrevidenciaDiagnostic() {
            const declSelect = document.getElementById('calc-prev-diag-decl');
            const inssSelect = document.getElementById('calc-prev-diag-inss');
            const horizonSelect = document.getElementById('calc-prev-diag-horizon');

            const isCompleta = declSelect?.value === 'completa';
            const hasInss = inssSelect?.value === 'sim';
            const isLongo = horizonSelect?.value === 'longo';

            const bannerEl = document.getElementById('calc-prev-diag-banner');
            const titleEl = document.getElementById('calc-prev-diag-title');
            const planBadgeEl = document.getElementById('calc-prev-diag-plan-badge');
            const regimeBadgeEl = document.getElementById('calc-prev-diag-regime-badge');
            const descEl = document.getElementById('calc-prev-diag-desc');

            let recommendedPlan = 'PGBL';
            let recommendedRegime = isLongo ? 'Regressivo' : 'Progressivo';
            let rationale = '';

            if (isCompleta && hasInss) {
                recommendedPlan = 'PGBL';
                if (isLongo) {
                    recommendedRegime = 'Tabela Regressiva (10% IR Mínimo)';
                    rationale = 'Perfil ideal para <strong>PGBL com Regime Regressivo</strong>: você abate até 12% da renda bruta hoje (reinvestindo a restituição) e usufrui da alíquota definitiva de 10% no resgate de longo prazo.';
                } else {
                    recommendedRegime = 'Tabela Progressiva (Compensável no IRPF)';
                    rationale = 'Como o prazo é curto (≤ 5 anos), a tabela regressiva cobraria entre 25% e 35% de IR. A <strong>Tabela Progressiva</strong> pode ser mais vantajosa caso sua renda no momento do resgate seja baixa ou isenta.';
                }
            } else {
                recommendedPlan = 'VGBL';
                const motive = !isCompleta ? 'utiliza Declaração Simplificada' : 'não contribui para a previdência oficial (INSS/RPPS)';
                if (isLongo) {
                    recommendedRegime = 'Tabela Regressiva (10% s/ Lucro)';
                    rationale = `Como você ${motive}, o <strong>PGBL não traz dedução no IRPF</strong> e cobraria IR sobre o principal. O <strong>VGBL é a melhor escolha</strong> porque tributa apenas os rendimentos (lucro). Para longo prazo, a Tabela Regressiva garante a alíquota mínima de 10%.`;
                } else {
                    recommendedRegime = 'Tabela Progressiva (Compensável)';
                    rationale = `Como você ${motive}, o plano correto é o <strong>VGBL</strong> (tributação restrita ao lucro). Para curto prazo, avalie a Tabela Progressiva para evitar as alíquotas iniciais de 35% a 25% da Regressiva.`;
                }
            }

            if (bannerEl) {
                bannerEl.classList.toggle('pgbl-rec', recommendedPlan === 'PGBL');
                bannerEl.classList.toggle('vgbl-rec', recommendedPlan === 'VGBL');
            }
            if (titleEl) titleEl.textContent = `Recomendação: ${recommendedPlan} + ${recommendedRegime}`;
            if (planBadgeEl) {
                planBadgeEl.textContent = `Plano Ideal: ${recommendedPlan}`;
                planBadgeEl.className = recommendedPlan === 'PGBL' ? 'badge badge-green' : 'badge badge-blue';
            }
            if (regimeBadgeEl) {
                regimeBadgeEl.textContent = `Regime: ${recommendedRegime.split(' ')[0]}`;
                regimeBadgeEl.className = 'badge';
            }
            if (descEl) descEl.innerHTML = rationale;
        }

        function applyDiagnosticToSimulation() {
            const declSelect = document.getElementById('calc-prev-diag-decl');
            const inssSelect = document.getElementById('calc-prev-diag-inss');
            const horizonSelect = document.getElementById('calc-prev-diag-horizon');

            const isCompleta = declSelect?.value === 'completa';
            const hasInss = inssSelect?.value === 'sim';
            const isLongo = horizonSelect?.value === 'longo';

            const regimeSelect = document.getElementById('calc-prev-regime');
            const yearsSelect = document.getElementById('calc-prev-years');

            if (regimeSelect) {
                regimeSelect.value = isLongo ? 'regressive' : 'progressive';
                onPrevRegimeChange();
            }
            if (yearsSelect) {
                yearsSelect.value = isLongo ? '30' : '5';
            }
            calculatePrevidencia();
        }

        function onPrevRegimeChange() {
            const regimeSelect = document.getElementById('calc-prev-regime');
            const progTaxGroup = document.getElementById('calc-prev-prog-tax-group');
            const isProgressive = regimeSelect?.value === 'progressive';
            if (progTaxGroup) {
                progTaxGroup.classList.toggle('hidden', !isProgressive);
            }
            calculatePrevidencia();
        }

        function calculatePrevidencia() {
            const incomeInput = document.getElementById('calc-prev-income');
            const pctInput = document.getElementById('calc-prev-pct');
            const yearsSelect = document.getElementById('calc-prev-years');
            const regimeSelect = document.getElementById('calc-prev-regime');
            const progTaxSelect = document.getElementById('calc-prev-prog-tax');
            const returnInput = document.getElementById('calc-prev-return');
            const reinvestTaxSelect = document.getElementById('calc-prev-reinvest-tax');

            const annualIncome = Math.max(1000, parseFloat(incomeInput?.value) || 120000);
            const investPct = Math.min(12, Math.max(1, parseFloat(pctInput?.value) || 12)) / 100.0;
            const years = parseInt(yearsSelect?.value) || 30;
            const regime = regimeSelect?.value || 'regressive';
            const progTaxRate = parseFloat(progTaxSelect?.value) || 0.15;
            const annualReturn = (parseFloat(returnInput?.value) || 10.0) / 100.0;
            const reinvestTaxRate = parseFloat(reinvestTaxSelect?.value) || 0.15;

            // 1. Benefício Fiscal Anual (IRPF Completo)
            const annualInvest = annualIncome * investPct;
            const monthlyInvest = annualInvest / 12.0;
            const newTaxBase = Math.max(0, annualIncome - annualInvest);

            function calcIrpfTax(income) {
                if (income <= 22847.76) return { rate: 0.0, deduction: 0, tax: 0 };
                if (income <= 33919.80) return { rate: 0.075, deduction: 1713.58, tax: Math.max(0, income * 0.075 - 1713.58) };
                if (income <= 45012.60) return { rate: 0.15, deduction: 4257.57, tax: Math.max(0, income * 0.15 - 4257.57) };
                if (income <= 55976.16) return { rate: 0.225, deduction: 7633.51, tax: Math.max(0, income * 0.225 - 7633.51) };
                return { rate: 0.275, deduction: 10432.32, tax: Math.max(0, income * 0.275 - 10432.32) };
            }

            const taxWithoutPgbl = calcIrpfTax(annualIncome).tax;
            const taxWithPgbl = calcIrpfTax(newTaxBase).tax;
            const annualTaxSavings = Math.max(0, taxWithoutPgbl - taxWithPgbl);
            const totalTaxSavingsNoInterest = annualTaxSavings * years;
            const monthlyReinvestAmount = annualTaxSavings / 12.0;

            // 2. Projeção de Acúmulo no Longo Prazo
            const monthlyRate = Math.pow(1.0 + annualReturn, 1.0 / 12.0) - 1.0;
            const months = years * 12;

            function calcFutureValue(pmt, mRate, mCount) {
                if (mRate <= 0) return pmt * mCount;
                return pmt * (Math.pow(1.0 + mRate, mCount) - 1.0) / mRate;
            }

            // Plano Principal (VGBL / PGBL)
            const mainTotalGross = calcFutureValue(monthlyInvest, monthlyRate, months);
            const mainTotalInvested = monthlyInvest * months;
            const mainTotalEarnings = Math.max(0, mainTotalGross - mainTotalInvested);

            // Alíquota de IR no Resgate
            let effectiveRedemptionTax = 0.10;
            if (regime === 'progressive') {
                effectiveRedemptionTax = progTaxRate;
            } else {
                if (years <= 2) effectiveRedemptionTax = 0.35;
                else if (years <= 4) effectiveRedemptionTax = 0.30;
                else if (years <= 6) effectiveRedemptionTax = 0.25;
                else if (years <= 8) effectiveRedemptionTax = 0.20;
                else if (years <= 10) effectiveRedemptionTax = 0.15;
                else effectiveRedemptionTax = 0.10;
            }

            // Cenário 1: VGBL (IR incide apenas sobre o Lucro)
            const vgblTax = mainTotalEarnings * effectiveRedemptionTax;
            const vgblNet = mainTotalGross - vgblTax;

            // Cenário 2: PGBL Simples (IR incide sobre o Total, mas soma a economia não reinvestida)
            const pgblPlanTax = mainTotalGross * effectiveRedemptionTax;
            const pgblPlanNet = mainTotalGross - pgblPlanTax;
            const pgblSimpleTotalNet = pgblPlanNet + totalTaxSavingsNoInterest;
            const pgblSimpleAdvantage = pgblSimpleTotalNet - vgblNet;

            // Cenário 3: PGBL Otimizado (Reinvestindo a Economia de IR mês a mês)
            const reinvestTotalGross = calcFutureValue(monthlyReinvestAmount, monthlyRate, months);
            const reinvestTotalInvested = monthlyReinvestAmount * months;
            const reinvestTotalEarnings = Math.max(0, reinvestTotalGross - reinvestTotalInvested);
            const reinvestTax = reinvestTotalEarnings * reinvestTaxRate;
            const reinvestNet = reinvestTotalGross - reinvestTax;
            const pgblOptTotalNet = pgblPlanNet + reinvestNet;
            const pgblOptAdvantage = pgblOptTotalNet - vgblNet;
            const pgblOptPctAdvantage = vgblNet > 0 ? (pgblOptAdvantage / vgblNet) * 100 : 0;

            // Atualiza UI
            const annualInvestEl = document.getElementById('calc-prev-annual-invest');
            const newTaxBaseEl = document.getElementById('calc-prev-new-tax-base');
            const taxDiffEl = document.getElementById('calc-prev-tax-diff');
            const taxSavingsAnnualEl = document.getElementById('calc-prev-tax-savings-annual');
            const taxSavingsTotalEl = document.getElementById('calc-prev-tax-savings-total');

            if (annualInvestEl) annualInvestEl.textContent = `R$ ${annualInvest.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (R$ ${monthlyInvest.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mês)`;
            if (newTaxBaseEl) newTaxBaseEl.textContent = `R$ ${newTaxBase.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (taxDiffEl) taxDiffEl.textContent = `R$ ${taxWithoutPgbl.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} → R$ ${taxWithPgbl.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (taxSavingsAnnualEl) taxSavingsAnnualEl.textContent = `+ R$ ${annualTaxSavings.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / ano`;
            if (taxSavingsTotalEl) taxSavingsTotalEl.textContent = `R$ ${totalTaxSavingsNoInterest.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

            // VGBL Elements
            const vgblGrossEl = document.getElementById('calc-prev-vgbl-gross');
            const vgblTaxEl = document.getElementById('calc-prev-vgbl-tax');
            const vgblNetEl = document.getElementById('calc-prev-vgbl-net');
            if (vgblGrossEl) vgblGrossEl.textContent = `R$ ${mainTotalGross.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (vgblTaxEl) vgblTaxEl.textContent = `R$ ${vgblTax.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${(effectiveRedemptionTax * 100).toFixed(1)}%)`;
            if (vgblNetEl) vgblNetEl.textContent = `R$ ${vgblNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

            // PGBL Simples Elements
            const pgblPlanNetEl = document.getElementById('calc-prev-pgbl-plan-net');
            const pgblSimpleSavingsEl = document.getElementById('calc-prev-pgbl-simple-savings');
            const pgblSimpleNetEl = document.getElementById('calc-prev-pgbl-simple-net');
            if (pgblPlanNetEl) pgblPlanNetEl.textContent = `R$ ${pgblPlanNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (pgblSimpleSavingsEl) pgblSimpleSavingsEl.textContent = `R$ ${totalTaxSavingsNoInterest.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (pgblSimpleNetEl) {
                const diffSign = pgblSimpleAdvantage >= 0 ? '+' : '';
                pgblSimpleNetEl.textContent = `R$ ${pgblSimpleTotalNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${diffSign}R$ ${(pgblSimpleAdvantage / 1000).toFixed(1)}k)`;
            }

            // PGBL Otimizado Elements
            const optPlanEl = document.getElementById('calc-prev-opt-plan');
            const optReinvestEl = document.getElementById('calc-prev-opt-reinvest');
            const optTotalNetEl = document.getElementById('calc-prev-opt-total-net');
            if (optPlanEl) optPlanEl.textContent = `R$ ${pgblPlanNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (optReinvestEl) optReinvestEl.textContent = `R$ ${reinvestNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (optTotalNetEl) optTotalNetEl.textContent = `R$ ${pgblOptTotalNet.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

            // Veredito
            const verdictDescEl = document.getElementById('calc-prev-verdict-desc');
            if (verdictDescEl) {
                verdictDescEl.textContent = `O reinvestimento contínuo da restituição fiscal anual (R$ ${annualTaxSavings.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/ano) no PGBL acumula um saldo líquido R$ ${pgblOptAdvantage.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} superior (+${pgblOptPctAdvantage.toFixed(1)}%) ao VGBL ao final do período para o mesmo desembolso financeiro total.`;
            }

            renderPrevidenciaChart(vgblNet, pgblSimpleTotalNet, pgblOptTotalNet);
        }

        function renderPrevidenciaChart(vgblVal, pgblSimpleVal, pgblOptVal) {
            const ctx = document.getElementById('previdencia-chart')?.getContext('2d');
            if (!ctx || typeof Chart === 'undefined') return;

            if (previdenciaChartInstance) {
                previdenciaChartInstance.destroy();
                previdenciaChartInstance = null;
            }

            const isLight = document.body.classList.contains('light-theme');
            const tickColor = isLight ? '#6b7084' : '#8b8fa3';
            const gridColor = isLight ? '#e2e4ea' : '#282c38';

            previdenciaChartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: ['VGBL', 'PGBL Simples', 'PGBL c/ Reinvestimento'],
                    datasets: [{
                        label: 'Patrimônio Líquido Final',
                        data: [vgblVal, pgblSimpleVal, pgblOptVal],
                        backgroundColor: [
                            'rgba(59, 130, 246, 0.7)',
                            'rgba(245, 158, 11, 0.7)',
                            'rgba(16, 185, 129, 0.85)'
                        ],
                        borderColor: [
                            '#3b82f6',
                            '#f59e0b',
                            '#10b981'
                        ],
                        borderWidth: 1.5,
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        valueLabels: false,
                        keyValueLabels: false,
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return ` Líquido: R$ ${context.parsed.y.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { color: tickColor, font: { size: 10, weight: '600', family: 'Inter, sans-serif' } }
                        },
                        y: {
                            grid: { color: gridColor },
                            ticks: {
                                color: tickColor,
                                maxTicksLimit: 4,
                                font: { size: 10, family: 'Inter, sans-serif' },
                                callback: v => `R$ ${(v / 1000000).toFixed(1)}M`
                            }
                        }
                    }
                }
            });
        }

        function calculateFireRetirement() {
            const capitalInput = document.getElementById('calc-fire-capital');
            const swrSelect = document.getElementById('calc-fire-swr');
            const strategySelect = document.getElementById('calc-fire-strategy');

            const capital = Math.max(1000, parseFloat(capitalInput?.value) || 500000);
            const swr = parseFloat(swrSelect?.value) || 0.04;
            const strategy = strategySelect?.value || 'mixed';

            const annualWithdrawal = capital * swr;
            const monthlyWithdrawal = annualWithdrawal / 12.0;
            const dailyWithdrawal = annualWithdrawal / 365.0;

            const monthlyEl = document.getElementById('calc-fire-monthly');
            const annualEl = document.getElementById('calc-fire-annual');
            const dailyEl = document.getElementById('calc-fire-daily');
            const statusEl = document.getElementById('calc-fire-status');
            const insightDescEl = document.getElementById('calc-fire-insight-desc');

            if (monthlyEl) monthlyEl.textContent = `R$ ${monthlyWithdrawal.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / mês`;
            if (annualEl) annualEl.textContent = `R$ ${annualWithdrawal.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / ano`;
            if (dailyEl) dailyEl.textContent = `R$ ${dailyWithdrawal.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / dia`;

            if (statusEl) {
                if (swr <= 0.04) {
                    statusEl.textContent = '100% Perpétuo (Capital Intacto)';
                    statusEl.style.color = 'var(--positive)';
                } else if (swr <= 0.05) {
                    statusEl.textContent = 'Muito Seguro (30+ Anos)';
                    statusEl.style.color = 'var(--positive)';
                } else {
                    statusEl.textContent = 'Moderado (Requer Monitoramento)';
                    statusEl.style.color = 'var(--gold)';
                }
            }

            if (insightDescEl) {
                const swrPct = (swr * 100).toFixed(1);
                insightDescEl.textContent = `Com R$ ${capital.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} investidos e uma taxa de retirada de ${swrPct}% a.a., você saca R$ ${monthlyWithdrawal.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} todo mês reajustado pela inflação sem esgotar o patrimônio principal.`;
            }
        }

        function calculateRule200() {
            const input = document.getElementById('rule-200-income');
            const resEl = document.getElementById('rule-200-result');
            const income = Math.max(10, parseFloat(input?.value) || 5000);
            const target = income * 200;
            if (resEl) resEl.textContent = `R$ ${target.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        }

        function calculateRule300() {
            const input = document.getElementById('rule-300-income');
            const resEl = document.getElementById('rule-300-result');
            const expense = Math.max(10, parseFloat(input?.value) || 5000);
            const target = expense * 300;
            if (resEl) resEl.textContent = `R$ ${target.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        }

        function calculateRule72() {
            const input = document.getElementById('rule-72-rate');
            const resEl = document.getElementById('rule-72-result');
            const descEl = document.getElementById('rule-72-desc');
            const rate = Math.max(0.1, parseFloat(input?.value) || 12.0);
            const yearsToDouble = 72.0 / rate;
            if (resEl) resEl.textContent = `${yearsToDouble.toFixed(1).replace('.', ',')} anos`;
            if (descEl) descEl.textContent = `Seu capital dobra a cada ${yearsToDouble.toFixed(1)} anos a uma taxa composta de ${rate.toFixed(1)}% ao ano.`;
        }

        function calculateRule503020() {
            const input = document.getElementById('rule-503020-salary');
            const needsEl = document.getElementById('rule-503020-res-needs');
            const wantsEl = document.getElementById('rule-503020-res-wants');
            const savingsEl = document.getElementById('rule-503020-res-savings');
            const salary = Math.max(100, parseFloat(input?.value) || 6000);

            const needs = salary * 0.50;
            const wants = salary * 0.30;
            const savings = salary * 0.20;

            if (needsEl) needsEl.textContent = `R$ ${needs.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (wantsEl) wantsEl.textContent = `R$ ${wants.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (savingsEl) savingsEl.textContent = `R$ ${savings.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / mês`;
        }

        function calculateRuleGraham() {
            const lpaInput = document.getElementById('rule-graham-lpa');
            const vpaInput = document.getElementById('rule-graham-vpa');
            const priceInput = document.getElementById('rule-graham-price');
            const resEl = document.getElementById('rule-graham-result');
            const marginEl = document.getElementById('rule-graham-margin');

            const lpa = Math.max(0.01, parseFloat(lpaInput?.value) || 3.50);
            const vpa = Math.max(0.01, parseFloat(vpaInput?.value) || 25.00);
            const price = Math.max(0.01, parseFloat(priceInput?.value) || 32.00);

            const grahamVal = Math.sqrt(22.5 * lpa * vpa);
            const marginPct = ((grahamVal - price) / price) * 100;

            if (resEl) resEl.textContent = `R$ ${grahamVal.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (marginEl) {
                if (marginPct >= 0) {
                    marginEl.textContent = `+${marginPct.toFixed(1)}% de Margem (Desconto)`;
                    marginEl.style.color = 'var(--positive)';
                } else {
                    marginEl.textContent = `${marginPct.toFixed(1)}% (Negociando com Ágio)`;
                    marginEl.style.color = 'var(--negative)';
                }
            }
        }

        function calculateRuleBazin() {
            const input = document.getElementById('rule-bazin-dpa');
            const priceInput = document.getElementById('rule-bazin-price');
            const resEl = document.getElementById('rule-bazin-result');
            const marginEl = document.getElementById('rule-bazin-margin');

            const dpa = Math.max(0.01, parseFloat(input?.value) || 2.40);
            const price = Math.max(0.01, parseFloat(priceInput?.value) || 30.00);
            const ceilingPrice = dpa / 0.06;
            const marginPct = ((ceilingPrice - price) / price) * 100;

            if (resEl) resEl.textContent = `R$ ${ceilingPrice.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (marginEl) {
                if (marginPct >= 0) {
                    marginEl.textContent = `+${marginPct.toFixed(1)}% abaixo do Teto`;
                    marginEl.style.color = 'var(--positive)';
                } else {
                    marginEl.textContent = `${marginPct.toFixed(1)}% acima do Teto (Caro p/ 6% DY)`;
                    marginEl.style.color = 'var(--negative)';
                }
            }
        }

        function calculateRulePeg() {
            const peInput = document.getElementById('rule-peg-pe');
            const growthInput = document.getElementById('rule-peg-growth');
            const resEl = document.getElementById('rule-peg-result');
            const descEl = document.getElementById('rule-peg-desc');

            const pe = Math.max(0.1, parseFloat(peInput?.value) || 8.5);
            const growth = Math.max(0.1, parseFloat(growthInput?.value) || 15.0);
            const peg = pe / growth;

            if (resEl) {
                if (peg < 1.0) {
                    resEl.textContent = `${peg.toFixed(2)} (Excelente Oportunidade)`;
                    resEl.style.color = 'var(--positive)';
                } else if (peg <= 1.5) {
                    resEl.textContent = `${peg.toFixed(2)} (Valuation Justo)`;
                    resEl.style.color = 'var(--gold)';
                } else {
                    resEl.textContent = `${peg.toFixed(2)} (P/L Esticado)`;
                    resEl.style.color = 'var(--negative)';
                }
            }
            if (descEl) {
                if (peg < 1.0) descEl.textContent = 'Ação em fase de alto crescimento negociando com valuation muito atrativo!';
                else if (peg <= 1.5) descEl.textContent = 'Preço alinhado ao ritmo de expansão dos lucros da empresa.';
                else descEl.textContent = 'Múltiplo P/L elevado exige aceleração substancial de lucros futuros.';
            }
        }

        function calculateRuleFii() {
            const distribInput = document.getElementById('rule-fii-distrib');
            const priceInput = document.getElementById('rule-fii-price');
            const resEl = document.getElementById('rule-fii-result');
            const yieldEl = document.getElementById('rule-fii-yield');

            const distrib = Math.max(0.01, parseFloat(distribInput?.value) || 0.90);
            const price = Math.max(0.1, parseFloat(priceInput?.value) || 105.00);

            const ceilingPrice = distrib / 0.0075;
            const monthlyYield = (distrib / price) * 100;
            const annualYield = monthlyYield * 12;

            if (resEl) resEl.textContent = `R$ ${ceilingPrice.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            if (yieldEl) {
                yieldEl.textContent = `${monthlyYield.toFixed(2)}% a.m. (${annualYield.toFixed(1)}% a.a. isento)`;
                yieldEl.style.color = monthlyYield >= 0.75 ? 'var(--positive)' : 'var(--gold)';
            }
        }

        function calculateRuleAge() {
            const input = document.getElementById('rule-age-val');
            const stocksEl = document.getElementById('rule-age-stocks');
            const bondsEl = document.getElementById('rule-age-bonds');
            const age = Math.min(100, Math.max(0, parseInt(input?.value) || 35));

            const stocksPct = Math.max(0, 100 - age);
            const bondsPct = 100 - stocksPct;

            if (stocksEl) stocksEl.textContent = `${stocksPct}%`;
            if (bondsEl) bondsEl.textContent = `${bondsPct}%`;
        }

        function calculateAllRules() {
            calculateRuleGraham();
            calculateRuleBazin();
            calculateRulePeg();
            calculateRuleFii();
            calculateRule200();
            calculateRule300();
            calculateRule72();
            calculateRule503020();
            calculateRuleAge();
        }

        function renderCalculatorPanel() {
            populateCalculatorSelects();
            if (currentCalcMode === 'goal') calculateIncomeGoal();
            else if (currentCalcMode === 'snowball') calculateSnowball();
            else if (currentCalcMode === 'compare_rf') calculateRfComparison();
            else if (currentCalcMode === 'previdencia') calculatePrevidencia();
            else if (currentCalcMode === 'fire') calculateFireRetirement();
            else if (currentCalcMode === 'rules') calculateAllRules();
        }

        /* ── Macro Forecaster & Scenario Simulator ── */

        function applyMacroScenario(scenarioKey) {
            const selicEl = document.getElementById('macro-sim-selic');
            const ipcaEl = document.getElementById('macro-sim-ipca');
            const fiscalEl = document.getElementById('macro-sim-fiscal');
            const debtEl = document.getElementById('macro-sim-debt');
            const buttons = document.querySelectorAll('#macro-preset-buttons .preset-scenario-btn');

            buttons.forEach(b => {
                const onclick = b.getAttribute('onclick') || '';
                b.classList.toggle('active', onclick.includes(`'${scenarioKey}'`));
            });

            if (scenarioKey === 'rate_cut') {
                if (selicEl) selicEl.value = '-200';
                if (ipcaEl) ipcaEl.value = 'low';
                if (fiscalEl) fiscalEl.value = 'surplus';
                if (debtEl) debtEl.value = 'easy';
            } else if (scenarioKey === 'fiscal_crisis') {
                if (selicEl) selicEl.value = '200';
                if (ipcaEl) ipcaEl.value = 'high';
                if (fiscalEl) fiscalEl.value = 'deficit';
                if (debtEl) debtEl.value = 'tight';
            } else if (scenarioKey === 'fiscal_consolidation') {
                if (selicEl) selicEl.value = '-100';
                if (ipcaEl) ipcaEl.value = 'target';
                if (fiscalEl) fiscalEl.value = 'surplus';
                if (debtEl) debtEl.value = 'easy';
            } else if (scenarioKey === 'rate_hike') {
                if (selicEl) selicEl.value = '200';
                if (ipcaEl) ipcaEl.value = 'high';
                if (fiscalEl) fiscalEl.value = 'neutral';
                if (debtEl) debtEl.value = 'tight';
            } else if (scenarioKey === 'debt_stress') {
                if (selicEl) selicEl.value = '100';
                if (ipcaEl) ipcaEl.value = 'target';
                if (fiscalEl) fiscalEl.value = 'neutral';
                if (debtEl) debtEl.value = 'tight';
            } else if (scenarioKey === 'flight_to_quality') {
                if (selicEl) selicEl.value = '0';
                if (ipcaEl) ipcaEl.value = 'high';
                if (fiscalEl) fiscalEl.value = 'deficit';
                if (debtEl) debtEl.value = 'neutral';
            }

            runMacroForecastSimulation();
        }

        function runMacroForecastSimulation() {
            const selicEl = document.getElementById('macro-sim-selic');
            const ipcaEl = document.getElementById('macro-sim-ipca');
            const fiscalEl = document.getElementById('macro-sim-fiscal');
            const debtEl = document.getElementById('macro-sim-debt');

            const selicDelta = selicEl ? parseInt(selicEl.value, 10) : 0;
            const ipcaLevel = ipcaEl ? ipcaEl.value : 'target';
            const fiscalLevel = fiscalEl ? fiscalEl.value : 'neutral';
            const debtLevel = debtEl ? debtEl.value : 'neutral';

            // 1. Diagnostic Summary Banner
            const bannerEl = document.getElementById('macro-forecast-banner');
            if (bannerEl) {
                let summaryTitle = '';
                let summaryText = '';
                let borderColor = 'var(--primary-accent)';

                if (fiscalLevel === 'deficit') {
                    summaryTitle = 'Descontrole Fiscal, Dívida Pública em Alta & Abertura da Curva Longa';
                    summaryText = 'A expansão dos gastos públicos eleva a relação Dívida/PIB e o prêmio de risco soberano. O mercado passa a exigir taxas reais elevadas nos títulos longos (IPCA+ 6.8% a 7.5%). Isso gera volatilidade temporária de marcação a mercado nos papéis longos, mas abre janelas estratégicas de aporte para carregamento até o vencimento.';
                    borderColor = 'var(--negative)';
                } else if (fiscalLevel === 'surplus' && selicDelta <= 0) {
                    summaryTitle = 'Consolidação Fiscal, Queda de Juros & Rali de Ativos (Bull Market)';
                    summaryText = 'Contas públicas com superávit reduzem o prêmio de risco, ancoram as expectativas de inflação e possibilitam cortes estruturais na Selic. A Curva de Juros (ETTJ) fecha com consistência, destravando valorização no Tesouro IPCA+ e expansão de múltiplos em Ações e FIIs de Tijolo.';
                    borderColor = 'var(--positive)';
                } else if (selicDelta > 0 || ipcaLevel === 'high') {
                    summaryTitle = 'Aperto Monetário, Custo de Dívida Elevado & Foco em Renda';
                    summaryText = 'Com juros e inflação elevados, ativos de duration longa sofrem reprecificação. O fluxo institucional prioriza a liquidez do Tesouro Selic (LFT), FIIs de papel (CRI) com yields indexados e ações com baixo endividamento e dividendos imediatos.';
                    borderColor = 'var(--gold)';
                } else {
                    summaryTitle = 'Cenário Macroeconômico de Equilíbrio';
                    summaryText = 'Condições de estabilidade. Alocação balanceada entre a proteção inflacionária do Tesouro IPCA+, a rentabilidade de caixa do Tesouro Selic e o valuation atrativo em ações de valor.';
                    borderColor = 'var(--primary-accent)';
                }

                bannerEl.style.borderLeftColor = borderColor;
                bannerEl.innerHTML = `
                    <div style="font-size: 1.05rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.35rem;">${summaryTitle}</div>
                    <div style="font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5;">${summaryText}</div>
                `;
            }

            // 2. Raio-X & Marcação a Mercado do Tesouro Direto
            const tesouroTbody = document.getElementById('macro-tesouro-table-tbody');
            const tesouroVerdictBadge = document.getElementById('macro-tesouro-verdict-badge');

            if (tesouroVerdictBadge) {
                if (fiscalLevel === 'surplus' && selicDelta < 0) {
                    tesouroVerdictBadge.textContent = 'Rali de Marcação a Mercado (+20% a +45%)';
                    tesouroVerdictBadge.className = 'macro-impact-badge macro-impact-high-pos';
                } else if (fiscalLevel === 'deficit') {
                    tesouroVerdictBadge.textContent = 'Prêmio de Risco Elevado (Oportunidade para Vencimento)';
                    tesouroVerdictBadge.className = 'macro-impact-badge macro-impact-mod-neg';
                } else if (selicDelta > 0) {
                    tesouroVerdictBadge.textContent = 'Proteção no Tesouro Selic';
                    tesouroVerdictBadge.className = 'macro-impact-badge macro-impact-mod-pos';
                } else {
                    tesouroVerdictBadge.textContent = 'Curva Equilibrada';
                    tesouroVerdictBadge.className = 'macro-impact-badge macro-impact-neutral';
                }
            }

            if (tesouroTbody) {
                let mtmIpcaShort = '';
                let mtmIpcaLong = '';
                let mtmPre = '';

                if (fiscalLevel === 'surplus' && selicDelta <= -100) {
                    mtmIpcaShort = '<span class="positive font-mono" style="font-weight:700;">+8% a +16% (Forte Alta no PU)</span>';
                    mtmIpcaLong = '<span class="positive font-mono" style="font-weight:700;">+25% a +50% (Explosão de MtM)</span>';
                    mtmPre = '<span class="positive font-mono" style="font-weight:700;">+15% a +30% (Rali Expressivo)</span>';
                } else if (fiscalLevel === 'deficit') {
                    mtmIpcaShort = '<span class="warning font-mono">-3% a -8% (Oscilação temporária)</span>';
                    mtmIpcaLong = '<span class="negative font-mono" style="font-weight:700;">-15% a -30% (Deságio de curto prazo)</span>';
                    mtmPre = '<span class="negative font-mono" style="font-weight:700;">-12% a -25% (Risco de corrosão)</span>';
                } else if (selicDelta > 0) {
                    mtmIpcaShort = '<span class="warning font-mono">-2% a -5% (Leve oscilação)</span>';
                    mtmIpcaLong = '<span class="warning font-mono">-8% a -15% (Queda no PU)</span>';
                    mtmPre = '<span class="negative font-mono">-6% a -14% (Perda de atratividade)</span>';
                } else {
                    mtmIpcaShort = '<span class="font-mono">Estável / Rentabilidade Contratada</span>';
                    mtmIpcaLong = '<span class="font-mono">Estável / Rentabilidade Contratada</span>';
                    mtmPre = '<span class="font-mono">Estável / Rentabilidade Contratada</span>';
                }

                tesouroTbody.innerHTML = `
                    <tr>
                        <td>
                            <div style="font-weight:700; color:var(--text-primary); margin-bottom: 0.25rem;">Tesouro Selic (LFT)</div>
                            <div style="display:flex; flex-wrap:wrap; gap:0.25rem;">
                                <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro Selic 2029')">Tesouro Selic 2029 ↗</span>
                                <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro Selic 2031')">Tesouro Selic 2031 ↗</span>
                            </div>
                        </td>
                        <td><span style="font-weight:600;">100% Selic + Ágio</span></td>
                        <td><span class="macro-impact-badge macro-impact-high-pos" style="font-size:0.7rem;">Duration Zero (1 Dia)</span></td>
                        <td><span class="positive" style="font-weight:700;">Volatilidade Nula (Imune a MtM)</span></td>
                        <td style="font-size:0.78rem; color:var(--text-secondary);">
                            ${selicDelta >= 0 || fiscalLevel === 'deficit'
                                ? '<strong>Reserva de Oportunidade:</strong> Máxima segurança para aguardar os picos de juros sem risco de oscilação negativa.'
                                : 'Excelente para liquidez imediata e reserva de emergência.'}
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <div style="font-weight:700; color:var(--text-primary); margin-bottom: 0.25rem;">Tesouro IPCA+ Médio</div>
                            <div style="display:flex; flex-wrap:wrap; gap:0.25rem;">
                                <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro IPCA+ 2029')">Tesouro IPCA+ 2029 ↗</span>
                                <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro IPCA+ 2035')">Tesouro IPCA+ 2035 ↗</span>
                            </div>
                        </td>
                        <td><span style="font-weight:600; color:var(--gold);">IPCA + Juro Real</span></td>
                        <td><span class="macro-impact-badge macro-impact-neutral" style="font-size:0.7rem;">Média (4 a 8 Anos)</span></td>
                        <td>${mtmIpcaShort}</td>
                        <td style="font-size:0.78rem; color:var(--text-secondary);">
                            ${fiscalLevel === 'deficit'
                                ? '<strong>Oportunidade Histórica:</strong> Travar taxas acima de IPCA + 6.5% garante riqueza real no vencimento.'
                                : 'Excelente equilíbrio entre proteção contra inflação e potencial de valorização.'}
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <div style="font-weight:700; color:var(--text-primary); margin-bottom: 0.25rem;">Tesouro IPCA+ Longo & RendA+</div>
                            <div style="display:flex; flex-wrap:wrap; gap:0.25rem;">
                                <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro IPCA+ 2045')">Tesouro IPCA+ 2045 ↗</span>
                                <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro RendA+')">Tesouro RendA+ ↗</span>
                                <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro Educa+')">Tesouro Educa+ ↗</span>
                            </div>
                        </td>
                        <td><span style="font-weight:600; color:var(--gold);">IPCA + Juro Real</span></td>
                        <td><span class="macro-impact-badge macro-impact-mod-neg" style="font-size:0.7rem;">Ultra-Longa (12 a 20+ Anos)</span></td>
                        <td>${mtmIpcaLong}</td>
                        <td style="font-size:0.78rem; color:var(--text-secondary);">
                            ${fiscalLevel === 'surplus' && selicDelta < 0
                                ? '<strong>Venda Antecipada:</strong> Momento ideal para realizar lucros de marcação a mercado e embolsar o rali.'
                                : '<strong>Aposentadoria:</strong> Foco exclusivo no carregamento até o vencimento com juros compostos reais.'}
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <div style="font-weight:700; color:var(--text-primary); margin-bottom: 0.25rem;">Tesouro Prefixado</div>
                            <div style="display:flex; flex-wrap:wrap; gap:0.25rem;">
                                <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro Prefixado 2027')">Tesouro Prefixado 2027 ↗</span>
                                <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro Prefixado 2031')">Tesouro Prefixado 2031 ↗</span>
                            </div>
                        </td>
                        <td><span style="font-weight:600;">Taxa Nominal Fixa</span></td>
                        <td><span class="macro-impact-badge macro-impact-neutral" style="font-size:0.7rem;">Média (2 a 6 Anos)</span></td>
                        <td>${mtmPre}</td>
                        <td style="font-size:0.78rem; color:var(--text-secondary);">
                            ${fiscalLevel === 'deficit' || ipcaLevel === 'high'
                                ? '<strong>Alerta de Risco:</strong> Evitar; descontrole fiscal pode gerar inflação acima da taxa fixa contratada.'
                                : '<strong>Trade de Ciclo:</strong> Excelente se houver certeza de corte de juros e controle fiscal.'}
                        </td>
                    </tr>
                `;
            }

            // 3. Asset Classes Impact Cards
            const classesGrid = document.getElementById('macro-asset-classes-grid');
            if (classesGrid) {
                const isBullMarket = selicDelta < 0 && fiscalLevel === 'surplus';
                const isFiscalStress = fiscalLevel === 'deficit';

                const classesData = [
                    {
                        title: 'Ações Cíclicas & Consumo',
                        sub: 'Varejo, Construção Civil, Shopping Centers',
                        impact: isBullMarket ? 'high-pos' : isFiscalStress ? 'high-neg' : (selicDelta > 0 ? 'mod-neg' : 'neutral'),
                        badgeText: isBullMarket ? 'Forte Valorização (+20% a +40%)' : isFiscalStress ? 'Risco de Compressão Severa' : 'Desempenho Regular',
                        mechanism: isBullMarket
                            ? 'A queda dos juros combinada à solvência fiscal destrava o crédito imobiliário, reduz drasticamente as despesas financeiras das empresas e expande os lucros.'
                            : isFiscalStress
                            ? 'O descontrole da dívida pública pressiona as taxas de juros de mercado, encarece os financiamentos e retrai as vendas a prazo.'
                            : 'Depende do crescimento orgânico das vendas e eficiência de custos operacionais.',
                        examples: [
                            { ticker: 'CYRE3', type: 'stock' },
                            { ticker: 'DIRR3', type: 'stock' },
                            { ticker: 'MULT3', type: 'stock' },
                            { ticker: 'LREN3', type: 'stock' }
                        ]
                    },
                    {
                        title: 'Utilidade Pública & Elétricas',
                        sub: 'Transmissão, Geração e Saneamento',
                        impact: isBullMarket ? 'high-pos' : (ipcaLevel === 'high' || isFiscalStress ? 'mod-pos' : 'neutral'),
                        badgeText: isBullMarket ? 'Expansão de Múltiplos' : (ipcaLevel === 'high' || isFiscalStress ? 'Blindagem Inflacionária' : 'Fluxo de Caixa Perene'),
                        mechanism: 'Contratos de concessão reajustados por IPCA/IGP-M e monopólios naturais garantem receita corrigida. No descontrole fiscal, funcionam como refúgio seguro.',
                        examples: [
                            { ticker: 'EGIE3', type: 'stock' },
                            { ticker: 'TAEE11', type: 'stock' },
                            { ticker: 'CPLE3', type: 'stock' },
                            { ticker: 'SBSP3', type: 'stock' }
                        ]
                    },
                    {
                        title: 'Setor Financeiro & Bancos',
                        sub: 'Grandes Bancos e Seguradoras',
                        impact: selicDelta > 0 || isFiscalStress ? 'mod-pos' : 'mod-pos',
                        badgeText: selicDelta > 0 || isFiscalStress ? 'Margens com Juros Elevadas' : 'Expansão da Carteira de Crédito',
                        mechanism: 'Bancos conseguem repassar juros e manter ROE elevado; seguradoras lucram alto com a aplicação do floating em CDI.',
                        examples: [
                            { ticker: 'ITUB4', type: 'stock' },
                            { ticker: 'BBAS3', type: 'stock' },
                            { ticker: 'BBSE3', type: 'stock' },
                            { ticker: 'PSSA3', type: 'stock' }
                        ]
                    },
                    {
                        title: 'Exportadoras & Commodities',
                        sub: 'Minério de Ferro, Petróleo, Papel & Celulose',
                        impact: isFiscalStress || ipcaLevel === 'high' ? 'high-pos' : 'neutral',
                        badgeText: isFiscalStress ? 'Hedge Cambial / Dólar Forte' : 'Demanda Global',
                        mechanism: 'Receitas em moeda forte (USD) descorrelacionadas do risco Brasil. Atuam como escudo patrimonial direto se a dívida pública desvalorizar o Real.',
                        examples: [
                            { ticker: 'VALE3', type: 'stock' },
                            { ticker: 'PETR4', type: 'stock' },
                            { ticker: 'SUZB3', type: 'stock' }
                        ]
                    },
                    {
                        title: 'FIIs de Tijolo (Imóveis Físicos)',
                        sub: 'Galpões Logísticos, Shoppings e Lajes Corporativas',
                        impact: isBullMarket ? 'high-pos' : isFiscalStress ? 'mod-neg' : 'neutral',
                        badgeText: isBullMarket ? 'Rali de Cotas (Fechamento da ETTJ)' : isFiscalStress ? 'Cotas com Desconto (P/VP < 0.90)' : 'Rendimento Regular',
                        mechanism: isBullMarket
                            ? 'O fechamento da taxa de desconto no mercado secundário valoriza as cotas e reaquece a demanda por locação física.'
                            : 'Juros altos forçam as cotas a negociar com desconto sobre o valor patrimonial.',
                        examples: [
                            { ticker: 'HGLG11', type: 'fii' },
                            { ticker: 'KNRI11', type: 'fii' },
                            { ticker: 'XPML11', type: 'fii' }
                        ]
                    },
                    {
                        title: 'FIIs de Papel & FIAGROs',
                        sub: 'Crédito Imobiliário e Agropecuário (CRI/CRA)',
                        impact: (ipcaLevel === 'high' || selicDelta > 0 || isFiscalStress) && debtLevel !== 'tight' ? 'high-pos' : 'neutral',
                        badgeText: (ipcaLevel === 'high' || isFiscalStress) ? 'Dividendos Mensais Elevados' : 'Renda Recorrente',
                        mechanism: 'Repasse integral e mensal do IPCA e do CDI aos cotistas com isenção de Imposto de Renda.',
                        examples: [
                            { ticker: 'KNCR11', type: 'fii' },
                            { ticker: 'KNSC11', type: 'fii' },
                            { ticker: 'RURA11', type: 'fiagro' }
                        ]
                    }
                ];

                classesGrid.innerHTML = classesData.map(c => {
                    const badgeClass = `macro-impact-${c.impact}`;
                    const examplesHtml = (c.examples || []).map(ex => {
                        return `<span class="macro-clickable-ticker" onclick="openDetailModal('${ex.ticker}', '${ex.type}')">${ex.ticker} ↗</span>`;
                    }).join(' ');

                    return `
                    <div class="macro-forecast-card">
                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.4rem;">
                                <div style="font-weight: 700; font-size: 0.95rem; color: var(--text-primary);">
                                    ${c.title}
                                </div>
                            </div>
                            <div style="font-size: 0.74rem; color: var(--text-muted); margin-bottom: 0.6rem;">${c.sub}</div>
                            <div class="macro-impact-badge ${badgeClass}" style="margin-bottom: 0.75rem;">${c.badgeText}</div>
                            <div style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.45;">${c.mechanism}</div>
                        </div>
                        <div style="margin-top: 0.85rem; padding-top: 0.6rem; border-top: 1px dashed var(--card-border); font-size: 0.74rem; color: var(--text-muted); display: flex; align-items: center; flex-wrap: wrap; gap: 0.35rem;">
                            <span style="font-weight: 600;">Ativos Relacionados:</span>
                            ${examplesHtml}
                        </div>
                    </div>`;
                }).join('');
            }

            // 4. Top Winners & Vulnerable Assets Lists
            const winnersList = document.getElementById('macro-winners-list');
            const vulnerableList = document.getElementById('macro-vulnerable-list');

            if (winnersList) {
                let winners = [];
                if (fiscalLevel === 'surplus' && selicDelta <= 0) {
                    winners = [
                        { ticker: 'CYRE3', name: 'Cyrela Brazil Realty', reason: 'Vendas e lançamentos imobiliários aceleram com crédito barato', type: 'stock' },
                        { ticker: 'MULT3', name: 'Multiplan Shoppings', reason: 'Vendas de lojistas em alta e taxa de desconto de valuation em queda', type: 'stock' },
                        { ticker: 'HGLG11', name: 'CSHG Logística FII', reason: 'Fechamento da curva de juros impulsiona o valor de mercado das cotas', type: 'fii' },
                        { ticker: 'DIRR3', name: 'Direcional Engenharia', reason: 'Forte demanda habitacional com crédito acessível e alto ROE', type: 'stock' },
                        { ticker: 'LREN3', name: 'Lojas Renner', reason: 'Recuperação do consumo discricionário e despesas financeiras em queda', type: 'stock' }
                    ];
                } else if (fiscalLevel === 'deficit' || ipcaLevel === 'high') {
                    winners = [
                        { ticker: 'VALE3', name: 'Vale S.A.', reason: 'Hedge em dólar e zero dependência de orçamento público ou Selic interna', type: 'stock' },
                        { ticker: 'BBSE3', name: 'BB Seguridade', reason: 'Resultado financeiro com floating alto em CDI e zero endividamento', type: 'stock' },
                        { ticker: 'EGIE3', name: 'Engie Brasil Energia', reason: 'Contratos indexados a IPCA/IGP-M protegem fluxo de caixa real', type: 'stock' },
                        { ticker: 'KNCR11', name: 'Kinea Rendimentos FII', reason: '100% CDI+ distribui dividendos extraordinários livres de IR', type: 'fii' },
                        { ticker: 'BBAS3', name: 'Banco do Brasil', reason: 'Spread bancário elevado e crédito agro subsidiado/protegido', type: 'stock' }
                    ];
                } else {
                    winners = [
                        { ticker: 'ITUB4', name: 'Itaú Unibanco', reason: 'Balanço conservador, ROE > 21% e diversificação de receitas', type: 'stock' },
                        { ticker: 'TAEE11', name: 'Taesa Transmissão', reason: 'Contratos longos de transmissão e previsibilidade absoluta', type: 'stock' },
                        { ticker: 'PSSA3', name: 'Porto Seguro', reason: 'Excelente combinação de seguro com rendimento financeiro', type: 'stock' },
                        { ticker: 'XPML11', name: 'XP Malls FII', reason: 'Portfólio de shoppings com dominância regional e fluxo estável', type: 'fii' }
                    ];
                }

                winnersList.innerHTML = winners.map(w => {
                    return `
                    <div onclick="openDetailModal('${w.ticker}', '${w.type}')" style="background: var(--surface); border: 1px solid var(--card-border); padding: 0.65rem 0.85rem; border-radius: var(--radius-sm); cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; transition: background 0.15s;">
                        <div>
                            <div style="font-weight: 700; font-size: 0.88rem; color: var(--text-primary); display: flex; align-items: center; gap: 0.4rem;">
                                <span>${w.ticker}</span>
                                <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: 400;">(${w.name})</span>
                            </div>
                            <div style="font-size: 0.76rem; color: var(--positive); margin-top: 0.2rem;">✓ ${w.reason}</div>
                        </div>
                        <span style="font-size: 0.72rem; font-weight: 700; color: var(--primary-accent); background: var(--surface-2); padding: 0.2rem 0.45rem; border-radius: 4px;">Ver Ficha →</span>
                    </div>`;
                }).join('');
            }

            if (vulnerableList) {
                let vulnerable = [];
                if (fiscalLevel === 'deficit' || debtLevel === 'tight') {
                    vulnerable = [
                        { ticker: 'AZUL4 / GOLL4', tickers: ['AZUL4', 'GOLL4'], name: 'Aéreas & Alavancadas', reason: 'Endividamento maciço em dólar/CDI e margens operacionais sensíveis a combustível', type: 'stock' },
                        { ticker: 'CASH3 / LWSA3', tickers: ['CASH3', 'LWSA3'], name: 'Tecnologia / Growth Sem Lucro', reason: 'Taxa de desconto alta reduz drasticamente o valor presente dos lucros futuros', type: 'stock' },
                        { ticker: 'Empresas Dív/EBITDA > 3.0x', tickers: [], name: 'Empresas Altamente Endividadas', reason: 'Custo de rolagem da dívida consome a maior parte do lucro operacional', type: 'stock' }
                    ];
                } else if (selicDelta < 0 && ipcaLevel === 'low') {
                    vulnerable = [
                        { ticker: 'Fundos FII CDI+ pós-fixados', tickers: ['KNCR11'], name: 'FIIs de Papel indexados a CDI', reason: 'Com a queda da Selic, o valor absoluto dos dividendos distribuídos diminui', type: 'fii' },
                        { ticker: 'Empresas de Caixa Líquido Excessivo', tickers: [], name: 'Exportadoras sem Dívida', reason: 'Deixam de auferir rendimentos financeiros extraordinários de CDI na conta', type: 'stock' }
                    ];
                } else {
                    vulnerable = [
                        { ticker: 'Ativos com P/L > 25x', tickers: [], name: 'Empresas sem Margem de Segurança', reason: 'Múltiplos esticados sem crescimento correspondente de lucros', type: 'stock' },
                        { ticker: 'FIIs com Vacância > 20%', tickers: [], name: 'Fundos com Imóveis Desocupados', reason: 'Risco de custos de condomínio e perda de poder de repasse de aluguel', type: 'fii' }
                    ];
                }

                vulnerableList.innerHTML = vulnerable.map(v => {
                    const chips = (v.tickers || []).map(t => `<span class="macro-clickable-ticker" onclick="openDetailModal('${t}', '${v.type}')">${t} ↗</span>`).join(' ');
                    return `
                    <div style="background: var(--surface); border: 1px solid var(--card-border); padding: 0.65rem 0.85rem; border-radius: var(--radius-sm); display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                        <div style="flex: 1; min-width: 200px;">
                            <div style="font-weight: 700; font-size: 0.88rem; color: var(--text-primary); display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                                <span>${v.ticker}</span>
                                <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: 400;">(${v.name})</span>
                            </div>
                            <div style="font-size: 0.76rem; color: var(--negative); margin-top: 0.2rem;">⚠️ ${v.reason}</div>
                        </div>
                        ${chips ? `<div>${chips}</div>` : ''}
                    </div>`;
                }).join('');
            }

            // 5. Playbook Content
            const playbookEl = document.getElementById('macro-playbook-content');
            if (playbookEl) {
                if (fiscalLevel === 'deficit') {
                    playbookEl.innerHTML = `
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem;">
                            <div>
                                <strong style="color: var(--primary-accent); display: block; margin-bottom: 0.25rem;">1. Travar Juros Reais Históricos no Tesouro IPCA+</strong>
                                Em momentos de pânico fiscal, as taxas superam IPCA + 6.8%. Aporte no <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro IPCA+ 2029')">Tesouro IPCA+ 2029 ↗</span> ou <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro IPCA+ 2035')">IPCA+ 2035 ↗</span> para carregar até o vencimento.
                            </div>
                            <div>
                                <strong style="color: var(--primary-accent); display: block; margin-bottom: 0.25rem;">2. Manter Reserva Robusta em Tesouro Selic</strong>
                                Garante liquidez imediata com <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro Selic 2029')">Tesouro Selic 2029 ↗</span> sem sofrer oscilações negativas no curto prazo.
                            </div>
                            <div>
                                <strong style="color: var(--primary-accent); display: block; margin-bottom: 0.25rem;">3. Blindagem com Ações Dolarizadas & Exportadoras</strong>
                                Aumente a exposição em <span class="macro-clickable-ticker" onclick="openDetailModal('VALE3', 'stock')">VALE3 ↗</span>, <span class="macro-clickable-ticker" onclick="openDetailModal('PETR4', 'stock')">PETR4 ↗</span> e <span class="macro-clickable-ticker" onclick="openDetailModal('SUZB3', 'stock')">SUZB3 ↗</span> para proteger o patrimônio contra desvalorizações cambiais do Real.
                            </div>
                        </div>
                    `;
                } else if (fiscalLevel === 'surplus' && selicDelta <= 0) {
                    playbookEl.innerHTML = `
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem;">
                            <div>
                                <strong style="color: var(--primary-accent); display: block; margin-bottom: 0.25rem;">1. Capturar Rali de Marcação a Mercado no Tesouro</strong>
                                Títulos como <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro IPCA+ 2045')">Tesouro IPCA+ 2045 ↗</span> e <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro Prefixado 2031')">Prefixado 2031 ↗</span> apresentam valorizações expressivas de PU que podem ser realizadas para reinvestimento.
                            </div>
                            <div>
                                <strong style="color: var(--primary-accent); display: block; margin-bottom: 0.25rem;">2. Aumentar Posições em FIIs de Tijolo & Small Caps</strong>
                                Ativos como <span class="macro-clickable-ticker" onclick="openDetailModal('HGLG11', 'fii')">HGLG11 ↗</span>, <span class="macro-clickable-ticker" onclick="openDetailModal('XPML11', 'fii')">XPML11 ↗</span> e <span class="macro-clickable-ticker" onclick="openDetailModal('CYRE3', 'stock')">CYRE3 ↗</span> possuem a maior assimetria positiva no ciclo de corte de juros.
                            </div>
                            <div>
                                <strong style="color: var(--primary-accent); display: block; margin-bottom: 0.25rem;">3. Reduzir Caixa Ocioso em Renda Fixa Pós-Fixada</strong>
                                Com a taxa Selic recuando, o custo de oportunidade de ficar fora da bolsa aumenta consideravelmente.
                            </div>
                        </div>
                    `;
                } else {
                    playbookEl.innerHTML = `
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem;">
                            <div>
                                <strong style="color: var(--primary-accent); display: block; margin-bottom: 0.25rem;">1. Estratégia Triangular de Alocação</strong>
                                Mantenha o portfólio dividido entre Ações de Dividendos (<span class="macro-clickable-ticker" onclick="openDetailModal('BBSE3', 'stock')">BBSE3 ↗</span>, <span class="macro-clickable-ticker" onclick="openDetailModal('TAEE11', 'stock')">TAEE11 ↗</span>) + FIIs (<span class="macro-clickable-ticker" onclick="openDetailModal('KNCR11', 'fii')">KNCR11 ↗</span>) + <span class="macro-clickable-ticker" onclick="openTdDetailFromHome('Tesouro IPCA+ 2029')">Tesouro IPCA+ ↗</span>.
                            </div>
                            <div>
                                <strong style="color: var(--primary-accent); display: block; margin-bottom: 0.25rem;">2. Aportes Mensais pelo Preço Teto de Bazin</strong>
                                Aproveite as cotações estáveis para comprar ativos de alta qualidade com margem de segurança.
                            </div>
                            <div>
                                <strong style="color: var(--primary-accent); display: block; margin-bottom: 0.25rem;">3. Reinvestimento Total de Proventos</strong>
                                Acelere o efeito dos juros compostos reinvestindo imediatamente os dividendos e cupons recebidos.
                            </div>
                        </div>
                    `;
                }
            }
        }

        /* ── Deep Linking / URL State Sync ── */
        let isSyncingFromUrl = false;

        function syncUrlFromState() {
            if (isSyncingFromUrl) return;
            const params = new URLSearchParams();
            if (currentTab && currentTab !== 'home') {
                params.set('tab', currentTab);
            }
            const searchInput = document.getElementById('search-bar');
            if (searchInput && searchInput.value.trim()) {
                params.set('q', searchInput.value.trim());
            }
            const sectorFilter = document.getElementById('sector-filter');
            if (sectorFilter && sectorFilter.value !== 'all') {
                params.set('sector', sectorFilter.value);
            }
            const indexFilter = document.getElementById('index-filter');
            if (indexFilter && indexFilter.value !== 'all') {
                params.set('index', indexFilter.value);
            }
            const scoreFilter = document.getElementById('score-range-filter');
            if (scoreFilter && scoreFilter.value !== 'all') {
                params.set('score', scoreFilter.value);
            }
            const discountFilter = document.getElementById('discount-filter');
            if (discountFilter && discountFilter.value !== 'all') {
                params.set('discount', discountFilter.value);
            }
            if (selectedCompareTickers && selectedCompareTickers.length > 0 && currentTab === 'compare') {
                params.set('compare', selectedCompareTickers.join(','));
            }

            const hashStr = params.toString();
            const newHash = hashStr ? `#${hashStr}` : '';
            if (window.location.hash !== newHash) {
                try {
                    history.replaceState(null, '', newHash || window.location.pathname);
                } catch (e) {
                    window.location.hash = newHash;
                }
            }
        }

        function syncStateFromUrl() {
            const rawHash = window.location.hash.replace(/^#/, '');
            if (!rawHash) return;
            isSyncingFromUrl = true;

            try {
                const params = new URLSearchParams(rawHash);
                const tab = params.get('tab');
                const q = params.get('q');
                const sector = params.get('sector');
                const index = params.get('index');
                const score = params.get('score');
                const discount = params.get('discount');
                const compare = params.get('compare');
                const asset = params.get('asset');
                const assetType = params.get('type') || 'stock';

                if (compare) {
                    selectedCompareTickers = compare.split(',').map(t => t.trim().toUpperCase()).filter(Boolean).slice(0, 4);
                }

                if (q) {
                    const sEl = document.getElementById('search-bar');
                    if (sEl) sEl.value = q;
                }
                if (sector) {
                    const secEl = document.getElementById('sector-filter');
                    if (secEl) secEl.value = sector;
                }
                if (index) {
                    const idxEl = document.getElementById('index-filter');
                    if (idxEl) idxEl.value = index;
                }
                if (score) {
                    const scrEl = document.getElementById('score-range-filter');
                    if (scrEl) scrEl.value = score;
                }
                if (discount) {
                    const discEl = document.getElementById('discount-filter');
                    if (discEl) discEl.value = discount;
                }

                if (tab) {
                    switchTab(tab);
                }

                if (asset) {
                    setTimeout(() => {
                        if (assetType === 'tesouro') openTdDetailFromHome(asset);
                        else openDetailModal(asset, assetType);
                    }, 100);
                }
            } finally {
                isSyncingFromUrl = false;
            }
        }

        window.addEventListener('hashchange', syncStateFromUrl);

        // ══════════════════════════════════════════════════════════════════════════════
        // RECURSO DE REDIMENSIONAMENTO DE COLUNAS ESTILO EXCEL
        // ══════════════════════════════════════════════════════════════════════════════
        function initTableColumnResizers() {
            const tables = document.querySelectorAll('.table-scroll > table, .table-wrap table, .compare-table, .macro-tesouro-table');
            tables.forEach((table, tableIdx) => {
                const thead = table.querySelector('thead');
                if (!thead) return;
                const headers = thead.querySelectorAll('th');
                const tableId = table.id || table.closest('.table-wrap')?.id || `tbl_${tableIdx}`;

                headers.forEach((th, colIdx) => {
                    // Restaura largura salva se existir
                    try {
                        const savedWidth = localStorage.getItem(`radar_col_w_${tableId}_${colIdx}`);
                        if (savedWidth && Number(savedWidth) >= 40) {
                            th.style.width = savedWidth + 'px';
                            th.style.minWidth = savedWidth + 'px';
                        }
                    } catch (e) {}

                    // Evita duplicar resizers
                    if (th.querySelector('.col-resizer')) return;

                    const resizer = document.createElement('div');
                    resizer.className = 'col-resizer';
                    resizer.title = 'Arraste para redimensionar a coluna (duplo clique para auto-ajustar)';

                    // Impede que clique no divisor ative a ordenação da tabela
                    resizer.addEventListener('click', function(e) {
                        e.stopPropagation();
                    });

                    // Duplo clique: Auto-fit ao conteúdo (estilo Excel)
                    resizer.addEventListener('dblclick', function(e) {
                        e.stopPropagation();
                        e.preventDefault();
                        autoFitColumn(table, th, colIdx, tableId);
                    });

                    // Mousedown: Inicia o arrasto
                    resizer.addEventListener('mousedown', function(e) {
                        e.stopPropagation();
                        e.preventDefault();
                        startColumnResize(e.pageX, table, th, resizer, colIdx, tableId);
                    });

                    // Touch: Suporte para tablets / touchscreens
                    resizer.addEventListener('touchstart', function(e) {
                        if (e.touches && e.touches[0]) {
                            e.stopPropagation();
                            startColumnResize(e.touches[0].pageX, table, th, resizer, colIdx, tableId);
                        }
                    }, { passive: false });

                    th.appendChild(resizer);
                });
            });
        }

        function startColumnResize(startX, table, th, resizer, colIdx, tableId) {
            resizer.classList.add('resizing');
            document.body.classList.add('is-col-resizing');

            const startWidth = th.getBoundingClientRect().width;
            const minWidth = 45; // Largura mínima em pixels

            // Fixa larguras atuais dos outros cabeçalhos para evitar colapso de layout
            const allHeaders = table.querySelectorAll('thead th');
            allHeaders.forEach(h => {
                if (!h.style.width) {
                    const w = Math.round(h.getBoundingClientRect().width);
                    h.style.width = w + 'px';
                    h.style.minWidth = w + 'px';
                }
            });

            function onMouseMove(e) {
                const currentX = e.pageX !== undefined ? e.pageX : (e.touches ? e.touches[0].pageX : startX);
                const delta = currentX - startX;
                const newWidth = Math.max(minWidth, Math.round(startWidth + delta));
                th.style.width = newWidth + 'px';
                th.style.minWidth = newWidth + 'px';
            }

            function onMouseUp(e) {
                resizer.classList.remove('resizing');
                document.body.classList.remove('is-col-resizing');

                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                document.removeEventListener('touchmove', onMouseMove);
                document.removeEventListener('touchend', onMouseUp);

                // Salva a preferência de largura do usuário no localStorage
                try {
                    const finalW = Math.round(th.getBoundingClientRect().width);
                    localStorage.setItem(`radar_col_w_${tableId}_${colIdx}`, finalW);
                } catch (err) {}
            }

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
            document.addEventListener('touchmove', onMouseMove, { passive: true });
            document.addEventListener('touchend', onMouseUp);
        }

        function autoFitColumn(table, th, colIndex, tableId) {
            const tempCanvas = document.createElement('canvas');
            const context = tempCanvas.getContext('2d');
            const computedStyle = window.getComputedStyle(th);
            context.font = `${computedStyle.fontWeight} ${computedStyle.fontSize} ${computedStyle.fontFamily}`;

            // Largura do texto do cabeçalho
            let maxWidth = context.measureText(th.innerText || th.textContent).width + 36;

            // Largura dos textos das linhas no corpo da tabela
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(tr => {
                const td = tr.children[colIndex];
                if (td) {
                    const tdStyle = window.getComputedStyle(td);
                    context.font = `${tdStyle.fontWeight} ${tdStyle.fontSize} ${tdStyle.fontFamily}`;
                    const textWidth = context.measureText(td.innerText || td.textContent).width + 28;
                    if (textWidth > maxWidth) maxWidth = textWidth;
                }
            });

            const finalWidth = Math.min(650, Math.max(50, Math.ceil(maxWidth)));
            th.style.width = finalWidth + 'px';
            th.style.minWidth = finalWidth + 'px';

            try {
                localStorage.setItem(`radar_col_w_${tableId}_${colIndex}`, finalWidth);
            } catch (err) {}
        }

        // Inicializa resizers após carga do DOM e nas trocas de aba
        window.initTableColumnResizers = initTableColumnResizers;
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => setTimeout(initTableColumnResizers, 150));
        } else {
            setTimeout(initTableColumnResizers, 150);
        }
        window.addEventListener('load', () => setTimeout(initTableColumnResizers, 200));

        // ── Funções da Base de Conhecimento & Glossário Educativo ──
        let currentGlossaryCategory = 'all';

        function setGlossaryCategory(category, btn) {
            currentGlossaryCategory = category;
            const pills = document.querySelectorAll('.learn-filter-pill');
            pills.forEach(p => p.classList.remove('active'));
            if (btn) btn.classList.add('active');
            filterGlossary();
        }

        function filterGlossary() {
            const searchInput = document.getElementById('learn-search');
            const term = (searchInput ? searchInput.value : '').toLowerCase().trim();
            const cards = document.querySelectorAll('.learn-card');

            cards.forEach(card => {
                const category = card.getAttribute('data-category') || '';
                const keywords = (card.getAttribute('data-keywords') || '').toLowerCase();
                const text = (card.textContent || '').toLowerCase();

                const matchesCat = (currentGlossaryCategory === 'all' || category === currentGlossaryCategory);
                const matchesSearch = (!term || keywords.includes(term) || text.includes(term));

                if (matchesCat && matchesSearch) {
                    card.style.display = 'flex';
                } else {
                    card.style.display = 'none';
                }
            });
        }
        window.setGlossaryCategory = setGlossaryCategory;
        window.filterGlossary = filterGlossary;

