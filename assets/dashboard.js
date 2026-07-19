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
                const names = { home: 'Home', stocks: 'Ações', fiis: 'FIIs', fiagros: 'FIAGROs', sectors: 'Setores', rendafixa: 'Tesouro Direto' };
                pdfLabel.textContent = names[tab] || tab;
            }
            const allBtns = document.querySelectorAll('.tab-btn');
            const btnHome = allBtns[0];
            const btnStocks = allBtns[1];
            const btnFiis = allBtns[2];
            const btnFiagros = allBtns[3];
            const btnSectors = allBtns[4];
            const btnRendaFixa = allBtns[5];

            const panelHome = document.getElementById('panel-home');
            const panelStocks = document.getElementById('panel-stocks');
            const panelFiis = document.getElementById('panel-fiis');
            const panelFiagros = document.getElementById('panel-fiagros');
            const panelSectors = document.getElementById('panel-sectors');
            const panelRendaFixa = document.getElementById('panel-rendafixa');
            const filtersRow = document.querySelector('.filters-row');

            allBtns.forEach(b => b.classList.remove('active'));
            [panelHome, panelStocks, panelFiis, panelFiagros, panelSectors, panelRendaFixa].forEach(p => {
                if (p) p.classList.add('hidden');
            });
            if (filtersRow) filtersRow.classList.toggle('hidden', !['stocks', 'fiis', 'fiagros'].includes(tab));

            if (tab === 'home') {
                if (btnHome) btnHome.classList.add('active');
                if (panelHome) panelHome.classList.remove('hidden');
            } else if (tab === 'stocks') {
                if (btnStocks) btnStocks.classList.add('active');
                if (panelStocks) panelStocks.classList.remove('hidden');
            } else if (tab === 'fiis') {
                if (btnFiis) btnFiis.classList.add('active');
                if (panelFiis) panelFiis.classList.remove('hidden');
            } else if (tab === 'fiagros') {
                if (btnFiagros) btnFiagros.classList.add('active');
                if (panelFiagros) panelFiagros.classList.remove('hidden');
            } else if (tab === 'sectors') {
                if (btnSectors) btnSectors.classList.add('active');
                if (panelSectors) panelSectors.classList.remove('hidden');
            } else if (tab === 'rendafixa') {
                if (btnRendaFixa) btnRendaFixa.classList.add('active');
                if (panelRendaFixa) panelRendaFixa.classList.remove('hidden');
                // O Chart.js precisa medir um painel visível. Esperar o próximo frame
                // evita canvas com largura/altura incorretas após a troca de aba.
                if (window.dashboardData) {
                    requestAnimationFrame(function() {
                        renderRendaFixaPanel(window.dashboardData);
                    });
                }
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
            } else { // home, sectors, rendafixa
                if (indexFilter) indexFilter.classList.add('hidden');
                if (sectorFilter) sectorFilter.classList.add('hidden');
                if (scoreFilter) scoreFilter.classList.add('hidden');
                if (discountFilter) discountFilter.classList.add('hidden');
            }

            filterTable();
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
            if (type === 'stocks' && (colIdx === 0 || colIdx === 1 || colIdx === 2)) isNumeric = false;
            else if ((type === 'fiis' || type === 'fiagros') && (colIdx === 0 || colIdx === 1)) isNumeric = false;
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
            document.getElementById('sector-modal-name').textContent = sectorName;

            const tbody = document.getElementById('sector-modal-tbody');
            tbody.innerHTML = '';

            // Get all stock rows in stocks-tbody
            const stockRows = document.querySelectorAll('#stocks-tbody tr');
            let foundStocks = [];

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

                    foundStocks.push({ ticker, name, price, pe, pb, dy, score });
                }
            });

            // Sort by Score desc, then by Dividend Yield desc (Bao opcao filter)
            foundStocks.sort((a, b) => b.score - a.score || b.dy - a.dy);

            if (foundStocks.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-secondary);">Nenhuma empresa cadastrada neste setor.</td></tr>';
            } else {
                foundStocks.forEach(stock => {
                    const tr = document.createElement('tr');
                    tr.style.cursor = 'pointer';
                    tr.onclick = (e) => {
                        closeSectorDetailModal();
                        openDetailModal(stock.ticker, 'stock');
                        e.stopPropagation();
                    };

                    tr.innerHTML = `
                    <td class="ticker-cell">${stock.ticker}</td>
                    <td>${stock.name}</td>
                    <td>R$ ${stock.price.toFixed(2)}</td>
                    <td class="${stock.pe !== null && stock.pe > 0 && stock.pe <= 15 ? 'positive' : 'warning'}">
                        ${stock.pe !== null ? stock.pe.toFixed(2) : 'N/A'}
                    </td>
                    <td class="${stock.pb !== null && stock.pb > 0 && stock.pb <= 1.5 ? 'positive' : 'warning'}">
                        ${stock.pb !== null ? stock.pb.toFixed(2) : 'N/A'}
                    </td>
                    <td class="${stock.dy >= 0.06 ? 'positive' : 'negative'}">
                        ${(stock.dy * 100).toFixed(2)}%
                    </td>
                    <td>
                        <span class="score-pill ${getScoreRangeClass(stock.score)}">${formatScore(stock.score)}</span>
                    </td>
                `;
                    tbody.appendChild(tr);
                });
            }

            document.getElementById('sector-detail-modal').classList.remove('hidden');
        }

        function closeSectorDetailModal() {
            document.getElementById('sector-detail-modal').classList.add('hidden');
        }

        function closeSectorModalOnOutsideClick(event) {
            if (event.target === document.getElementById('sector-detail-modal')) {
                closeSectorDetailModal();
            }
        }

        let activeChart = null;
        let currentAssetHistory = [];
        let currentAssetType = '';
        let currentAssetMetrics = {};
        let currentAssetRange = 10;

        function openDetailModal(ticker, type) {
            const rows = document.querySelectorAll(`[data-ticker="${ticker}"]`);
            if (rows.length === 0) return;
            const row = rows[0];

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
                        '<small style="color:var(--text-secondary);display:block;margin-top:0.15rem;font-size:0.8rem;">', item.desc, '</small>'
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
                        '<small style="color:var(--text-secondary);display:block;margin-top:0.15rem;font-size:0.8rem;">', item.desc, '</small>'
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
                        if (!options) return;

                        const indicator = options.indicator;
                        const borderColor = options.borderColor;
                        const isLight = options.isLight;

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
                            <td class="name-cell">${stock.name}</td>
                            <td>${stock.sector}</td>
                            <td>${priceFormatted}</td>
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
                            <td class="name-cell">${fii.name}</td>
                            <td>${priceFormatted}</td>
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
                            <td class="name-cell">${fiagro.name}</td>
                            <td>${priceFormatted}</td>
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
                            <td class="name-cell" style="font-weight: 600;">${sector.name}</td>
                            <td>${sector.count}</td>
                            <td>
                                <span class="score-pill ${getScoreRangeClass(sector.avg_score)}">${formatScore(sector.avg_score)}</span>
                            </td>
                            <td class="positive">${sector.avg_dy}%</td>
                            <td>${avgPeFormatted}</td>
                        </tr>`;
                    }).join('');

                    // Initialize view and tab filters
                    if (typeof checkRefreshStatus === 'function') checkRefreshStatus();
                    filterTable();
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
                    homeTs.textContent = 'Atualizado em: ' + macro.fetched_at +
                        (focusOfficial ? ' · Focus: BCB/OData' : ' · ⚠️ Focus indisponível');
                }
            }

            // ---- Top Picks ----
            const home = data.home || {};

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
                        const generalRank = td.general_rank ? '#' + td.general_rank : '<small>Planejamento</small>';
                        const group = td.group || tipo;
                        const groupRank = (td.group_rank ? '<br><small>#' + td.group_rank + ' no grupo</small>' : '') +
                            (td.risk_profile ? '<br><small title="Risco de oscilação em venda antecipada; separado do score de oportunidade.">Risco: ' + td.risk_profile + '</small>' : '');
                        return '<tr onclick="openTdDetailModal(\'' + tdJson + '\')" style="cursor:pointer;" title="' + breakdownTip.replace(/"/g, '&quot;') + '">' +
                            '<td class="font-mono tabular td-rank-cell" style="font-weight:600;">' + generalRank + '</td>' +
                            '<td class="name-cell" style="font-weight:600;">' + name + '</td>' +
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
                        const padding = Math.max((maxVal - minVal) * 0.15, 0.5);
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
                                        ticks: { color: tickColor, maxTicksLimit: 8, maxRotation: 0 }
                                    },
                                    y: {
                                        min: parseFloat(yMin.toFixed(2)),
                                        max: parseFloat(yMax.toFixed(2)),
                                        grid: { color: gridColor },
                                        ticks: {
                                            color: tickColor,
                                            callback: function(value) { return value.toFixed(2) + '%'; }
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
            var menu = document.getElementById('export-menu');
            if (menu) menu.style.display = 'none';
        }

        function toggleExportMenu() {
            const menu = document.getElementById('export-menu');
            menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
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
                    if (!options) return;

                    const labels = [];
                    chart.data.datasets.forEach(function(dataset, datasetIndex) {
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
                            if (seen.has(point.index)) return;
                            seen.add(point.index);
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
            const data = window.dashboardData;
            const tdData = data.tesouro_direto || [];
            const bond = tdData.find(function(b) { return b.name === name; });
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
                            '  <span style="font-size:0.85rem;color:var(--text-secondary);font-weight:600;">', b.score.toFixed(1), ' / ', b.max.toFixed(0), '</span>',
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

        function openFocusDetailModal(indicator) {
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
            if (macro.fetched_at) {
                const yr = parseInt(macro.fetched_at.substring(0, 4), 10);
                if (!isNaN(yr)) currentYear = yr;
            }

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
            // Agrupa por ano (pega último valor de cada ano para Selic/Câmbio, ou soma para IPCA)
            const histByYear = {};
            rawHistory.forEach(pt => {
                let yr = null;
                // Tenta extrair ano de formatos dd/mm/aaaa ou aaaa-mm-dd
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

            // Define anos do histórico (5 anos: currentYear-5 até currentYear-1)
            const histYears = [];
            for (let y = currentYear - 5; y < currentYear; y++) {
                histYears.push(y);
            }
            // IPCA (SGS 13522): valor acumulado 12m — pega último do ano (ex: Dez = IPCA oficial)
            // Selic Meta (SGS 432): pega último valor do ano (ex: meta vigente em Dez)
            // Câmbio (SGS 1): pega última cotação do ano
            const histValues = histYears.map(yr => {
                const pts = histByYear[yr];
                if (!pts || pts.length === 0) return null;
                // Todos os indicadores agora usam o último valor do ano
                const last = pts[pts.length - 1];
                if (indicator === 'ipca') return Math.round(last * 10000) / 100; // decimal → %
                if (indicator === 'selic') return Math.round(last * 10000) / 100; // decimal → %
                return Math.round(last * 100) / 100; // câmbio já em R$
            });

            // Labels: 5 anos hist + 4 anos focus
            const allLabels = histYears.concat([
                currentYear, currentYear + 1, currentYear + 2, currentYear + 3
            ]).map(String);

            // Dados: 5 hist + 4 focus (com gap null entre eles para separar visualmente)
            const histDataset = histValues.concat([null, null, null, null]);
            // Focus: nulls para os 5 anos históricos + valores atuais
            const currentYearFocus = focusValues[0]; // pode ser null
            const focusDataset = [null, null, null, null, null]
                .concat([currentYearFocus, focusValues[1], focusValues[2], focusValues[3]]);

            document.getElementById('focus-modal-title').textContent = title;
            document.getElementById('focus-modal-subtitle').textContent = subtitle;

            // Tabela: histórico + projeções
            const tbody = document.getElementById('focus-modal-tbody');
            if (tbody) {
                const tableRows = [];
                // 5 anos históricos
                histYears.forEach((yr, i) => {
                    const val = histValues[i];
                    let valStr = val != null
                        ? (isPercent ? val.toFixed(2) + '%' : isCurrency ? 'R$ ' + val.toFixed(2) : val.toFixed(2))
                        : '—';
                    tableRows.push(`<tr>
                        <td style="font-weight:600;">${yr}</td>
                        <td style="font-size:0.85rem;color:var(--text-secondary);font-weight:500;">Realizado</td>
                        <td class="font-mono tabular" style="font-weight:700;color:${colorHistory};">${valStr}</td>
                    </tr>`);
                });
                // 4 anos projeção
                for (let i = 0; i < 4; i++) {
                    const yr = currentYear + i;
                    const val = focusValues[i];
                    let valStr = '—';
                    if (val != null) {
                        valStr = isPercent ? val.toFixed(2) + '%' : isCurrency ? 'R$ ' + val.toFixed(2) : val.toFixed(2);
                    }
                    const isFuture = (i === 0) ? 'Projeção (ano corrente)' : 'Projeção Focus';
                    tableRows.push(`<tr>
                        <td style="font-weight:600;">${yr}</td>
                        <td style="font-size:0.85rem;color:var(--text-secondary);font-weight:500;">${isFuture}</td>
                        <td class="font-mono tabular" style="font-weight:700;color:${colorFuture};">${valStr}</td>
                    </tr>`);
                }
                tbody.innerHTML = tableRows.join('');
            }

            // Show Modal
            document.getElementById('focus-detail-modal').classList.remove('hidden');

            // Draw Chart
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
                                    label: 'Realizado',
                                    data: histDataset,
                                    borderColor: colorHistory,
                                    backgroundColor: bgHistory,
                                    borderWidth: 2.5,
                                    pointRadius: 5,
                                    pointHoverRadius: 7,
                                    pointBackgroundColor: colorHistory,
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
                                    pointRadius: 6,
                                    pointHoverRadius: 8,
                                    pointBackgroundColor: colorFuture,
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
                                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                                    padding: 8,
                                    callbacks: {
                                        label: function(context) {
                                            const val = context.parsed.y;
                                            if (val === null || isNaN(val)) return '';
                                            return context.dataset.label + ': ' + (isPercent ? val.toFixed(2) + '%' : isCurrency ? 'R$ ' + val.toFixed(2) : val.toFixed(2));
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
                                    ticks: { color: tickColor, font: { weight: '600' } }
                                },
                                y: {
                                    grid: { color: gridColor },
                                    ticks: {
                                        color: tickColor,
                                        callback: function(value) {
                                            return isPercent ? value.toFixed(1) + '%' : isCurrency ? 'R$ ' + value.toFixed(1) : value.toFixed(1);
                                        }
                                    },
                                    grace: '15%'
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

            function showTooltip(el) {
                if (hideTimeout) { clearTimeout(hideTimeout); hideTimeout = null; }
                var text = el.getAttribute('data-tip');
                if (!text) return;
                tip.textContent = '';
                tip.innerHTML = text;
                tip.style.display = 'block';
                tip.classList.add('visible');
                positionTooltip(el);
                activeEl = el;
            }

            function positionTooltip(el) {
                var rect = el.getBoundingClientRect();
                var tipRect = tip.getBoundingClientRect();
                var top = rect.bottom + 10;
                var left = rect.left + rect.width / 2 - tipRect.width / 2;
                if (left < 8) left = 8;
                if (left + tipRect.width > window.innerWidth - 8) {
                    left = window.innerWidth - tipRect.width - 8;
                }
                if (top + tipRect.height > window.innerHeight - 8) {
                    top = rect.top - tipRect.height - 10;
                    tip.style.setProperty('--arrow-rotate', '180deg');
                    tip.style.setProperty('--arrow-top', 'auto');
                    tip.style.setProperty('--arrow-bottom', '-10px');
                } else {
                    tip.style.setProperty('--arrow-rotate', '0deg');
                    tip.style.setProperty('--arrow-top', '-10px');
                    tip.style.setProperty('--arrow-bottom', 'auto');
                }
                var arrowLeft = Math.max(10, Math.min(rect.left + rect.width / 2 - left - 5, tipRect.width - 15));
                tip.style.setProperty('--arrow-left', arrowLeft + 'px');
                tip.style.top = top + 'px';
                tip.style.left = left + 'px';
            }

            function hideTooltip() {
                if (hideTimeout) { clearTimeout(hideTimeout); }
                hideTimeout = setTimeout(function() {
                    tip.classList.remove('visible');
                    tip.style.display = 'none';
                    activeEl = null;
                    hideTimeout = null;
                }, 100);
            }

            function cancelHide() {
                if (hideTimeout) { clearTimeout(hideTimeout); hideTimeout = null; }
            }

            document.querySelectorAll('.hint').forEach(function(el) {
                el.addEventListener('mouseenter', function(e) { cancelHide(); showTooltip(this); });
                el.addEventListener('mouseleave', function(e) { hideTooltip(); });
                el.addEventListener('focus', function(e) { cancelHide(); showTooltip(this); });
                el.addEventListener('blur', function(e) { hideTooltip(); });
                el.addEventListener('click', function(e) {
                    e.stopPropagation();
                    if (document.activeElement === this) { this.blur(); }
                    else { this.focus(); }
                });
            });

            document.addEventListener('touchstart', function(e) {
                if (!e.target.closest('.hint') && activeEl) { activeEl.blur(); hideTooltip(); }
            });
            document.addEventListener('mousedown', function(e) {
                if (!e.target.closest('.hint') && activeEl) { hideTooltip(); }
            });

            window.addEventListener('scroll', function() { if (activeEl) positionTooltip(activeEl); }, true);
            window.addEventListener('resize', function() { if (activeEl) positionTooltip(activeEl); });

            window.initHints = function(root) {
                (root || document).querySelectorAll('.hint').forEach(function(el) {
                    if (!el.dataset.hintInited) {
                        el.dataset.hintInited = '1';
                        el.addEventListener('mouseenter', function(e) { cancelHide(); showTooltip(this); });
                        el.addEventListener('mouseleave', function(e) { hideTooltip(); });
                        el.addEventListener('focus', function(e) { cancelHide(); showTooltip(this); });
                        el.addEventListener('blur', function(e) { hideTooltip(); });
                        el.addEventListener('click', function(e) {
                            e.stopPropagation();
                            if (document.activeElement === this) { this.blur(); }
                            else { this.focus(); }
                        });
                    }
                });
            };
        })();
