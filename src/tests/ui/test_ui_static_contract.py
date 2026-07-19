"""
Static contract tests for index-v2.html UI.

Reads index-v2.html as text and validates structural/contractual invariants
defined in docs/UI_UX_SPECIFICATION.md and docs/ANALYSIS_RULES_SPECIFICATION.md.

These tests do NOT use a browser, do NOT make network calls, and do NOT
depend on data.json or the database — they are purely static analysis of the
HTML/JS source code.

Run with:
    python -m pytest src/tests/ui/test_ui_static_contract.py -v
"""
import os
import re
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HTML_PATH = os.path.join(PROJECT_ROOT, "index-v2.html")
CSS_PATH = os.path.join(PROJECT_ROOT, "assets", "dashboard.css")
JS_PATH = os.path.join(PROJECT_ROOT, "assets", "dashboard.js")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def html() -> str:
    """Load the HTML shell and its external UI assets as one source."""
    for path in (HTML_PATH, CSS_PATH, JS_PATH):
        if not os.path.exists(path):
            pytest.fail(f"Required UI source not found: {path}")
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        page = f.read()
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        css = f.read()
    with open(JS_PATH, "r", encoding="utf-8") as f:
        js = f.read()
    return page + "\n<style>\n" + css + "\n</style>\n<script>\n" + js + "\n</script>"


def _extract_render_top_picks_body(html: str) -> str | None:
    """Extract the body of the renderTopPicks function via regex."""
    m = re.search(
        r'function\s+renderTopPicks\s*\([^)]*\)\s*\{(.*?)\}\s+function\s+renderHomePanel',
        html, re.DOTALL,
    )
    return m.group(1) if m else None


class TestTesouroHistoricalDataIntegrity:
    def test_taxa_and_pu_use_distinct_data_fields(self, html):
        assert "getTdHistory(td, 'buy_yield', days)" in html
        assert "getTdHistory(td, 'buy_price', days)" in html

    def test_cached_history_is_not_blocked_by_current_fallback(self, html):
        history_fn = re.search(r"function\s+getTdHistory\s*\([^)]*\)\s*\{(.*?)\n\s*\}", html, re.DOTALL)
        assert history_fn is not None
        assert "td.is_demo" not in history_fn.group(1)

    def test_modal_exposes_history_freshness_without_altering_chart_series(self, html):
        assert 'id="td-history-status"' in html
        assert "function renderTdHistoryStatus(td)" in html
        assert "td.history_meta" in html


# ===================================================================
# 1.  renderTopPicks — unique shared function (UI_UX §4.1 / §1.2)
# ===================================================================

class TestRenderTopPicksUniqueness:
    """UI_UX §4.1: a mesma funcao renderTopPicks deve atender toda
    ocorrencia visual de Top Picks — nao manter renderizador paralelo
    para Home e outro para Renda Fixa."""

    def test_defined_exactly_once(self, html):
        """Deve haver exatamente uma definicao de renderTopPicks."""
        matches = re.findall(r'function\s+renderTopPicks\s*\(', html)
        assert len(matches) == 1, (
            f"Expected exactly 1 definition of renderTopPicks, found {len(matches)}. "
            "UI_UX §4.1 requires a single shared function for all Top Picks."
        )

    def test_called_only_by_home_containers(self, html):
        """Top Picks pertencem exclusivamente à Home."""
        # Count calls (exclude the function definition itself)
        calls = re.findall(r'renderTopPicks\s*\(', html)
        assert len(calls) == 5, (     # 1 definition + 4 calls
            f"Expected 5 matches (1 def + 4 calls), found {len(calls)}. "
            "Top Picks must be rendered only in Home."
        )

    def test_home_containers_present(self, html):
        """Home chama renderTopPicks para stocks, fiis, fiagros, tesouro."""
        for cid in ["home-top-stocks", "home-top-fiis",
                     "home-top-fiagros", "home-top-tesouro"]:
            # calls use single quotes: getElementById('home-top-stocks')
            pattern = (
                r'renderTopPicks\s*\(\s*document\.getElementById\s*\(\s*'
                + re.escape(f"'{cid}'") + r'\s*\)'
            )
            assert re.search(pattern, html), (
                f"Missing renderTopPicks call for #{cid} in Home panel."
            )

    def test_home_top_tesouro_is_limited_to_five(self, html):
        assert re.search(
            r"home\.top_tesouro\s*\|\|\s*\[\]\s*\)\.filter\([\s\S]*?\)\.slice\(0,\s*5\)",
            html,
        ), "Top Tesouro must request up to five items."

    def test_rendafixa_has_no_top_picks(self, html):
        """Renda Fixa não pode conter containers nem chamadas de Top Picks."""
        for cid in ["rendafixa-top-stocks", "rendafixa-top-fiis",
                     "rendafixa-top-fiagros", "rendafixa-top-tesouro"]:
            assert cid not in html, f"#{cid} must not exist outside Home."

    def test_no_dead_code_in_rendafixa_stocks_map(self, html):
        """Nao deve haver codigo morto de FIIs/FIAGROs dentro do .map()
        de acoes em renderRendaFixaPanel."""
        # The dead code pattern was: after a `return`, additional unreachable
        # `const detail = 'DY '...` and `return...fii` / `return...fiagro`.
        # After refactoring, such patterns must not exist.
        dead_patterns = [
            r"const\s+detail\s*=\s*'DY\s+'\s*\+\s*\(dy\s*\*\s*100\)",
            r"return.*openDetailModal.*fi[iagro].*return.*openDetailModal",
        ]
        for dp in dead_patterns:
            matches = re.findall(dp, html)
            assert len(matches) == 0, (
                f"Dead code pattern found {len(matches)} time(s): {dp!r}. "
                "Unreachable FII/FIAGRO rendering inside stocks .map() must be removed."
            )


# ===================================================================
# 2.  Score nao aparece no detail text (UI_UX §4.1)
# ===================================================================

class TestScoreNotInDetail:
    """UI_UX §4.1: Nenhum texto de detalhe pode conter Score, score
    ou repetir seu valor. Score aparece exclusivamente em .home-pick-score."""

    def test_render_top_picks_detail_no_score(self, html):
        """A variavel detail em renderTopPicks nunca recebe 'Score'."""
        body = _extract_render_top_picks_body(html)
        assert body is not None, "Could not extract renderTopPicks body."
        # Check that detail is never assigned a string containing Score
        bad_assign = re.findall(r'detail\s*\+?=\s*["\'][^"\']*[Ss]core', body)
        assert len(bad_assign) == 0, (
            f"Found {len(bad_assign)} assignment(s) of Score to detail variable. "
            "UI_UX §4.1 forbids Score in detail text."
        )

    def test_home_pick_detail_no_score_between_tags(self, html):
        """Nao deve haver texto 'Score' entre tags home-pick-detail."""
        # Look for text nodes containing "Score" inside home-pick-detail spans
        bad = re.findall(
            r'home-pick-detail[^>]*>[^<]*[Ss]core[^<]*<',
            html,
        )
        # Filter out CSS false positives (class definitions)
        bad = [b for b in bad if 'class=\"' not in b]
        assert len(bad) == 0, (
            f"Found {len(bad)} occurrence(s) of 'Score' inside home-pick-detail text: {bad}. "
            "Score must only appear in .home-pick-score (UI_UX §4.1)."
        )

    def test_score_badge_exists_per_item(self, html):
        """Cada home-pick-item contem exatamente um .home-pick-score."""
        score_badges = re.findall(r'class="[^"]*home-pick-score[^"]*"', html)
        detail_spans = re.findall(r'class="[^"]*home-pick-detail[^"]*"', html)
        # Each item has one detail and one score badge
        assert len(score_badges) >= len(detail_spans), (
            f"Found {len(detail_spans)} detail spans but only {len(score_badges)} score badges. "
            "Every Top Pick item needs exactly one score badge."
        )


# ===================================================================
# 3.  Modal correto por tipo (UI_UX §4.1 / §6)
# ===================================================================

class TestCorrectModalOpening:
    """UI_UX §4.1: Cada tipo de Top Pick abre o modal correto."""

    def test_stock_type_uses_open_detail_modal(self, html):
        """Stock items must call openDetailModal with 'stock'."""
        assert re.search(
            r'openDetailModal\s*\(\s*["\'].*?["\']\s*,\s*["\']stock["\']\s*\)',
            html,
        ), "Missing openDetailModal('...', 'stock') call in renderTopPicks."

    def test_fii_type_uses_open_detail_modal(self, html):
        """FII items must call openDetailModal with 'fii'."""
        assert re.search(
            r'openDetailModal\s*\(\s*["\'].*?["\']\s*,\s*["\']fii["\']\s*\)',
            html,
        ), "Missing openDetailModal('...', 'fii') call in renderTopPicks."

    def test_fiagro_type_uses_open_detail_modal(self, html):
        """FIAGRO items must call openDetailModal with 'fiagro'."""
        assert re.search(
            r'openDetailModal\s*\(\s*["\'].*?["\']\s*,\s*["\']fiagro["\']\s*\)',
            html,
        ), "Missing openDetailModal('...', 'fiagro') call in renderTopPicks."

    def test_tesouro_type_uses_open_td_detail(self, html):
        """Tesouro items must call openTdDetailFromHome."""
        body = _extract_render_top_picks_body(html)
        assert body is not None
        assert "openTdDetailFromHome" in body, (
            "Tesouro Top Picks must use openTdDetailFromHome (UI_UX §4.1)."
        )
        # The tesouro branch must NOT use openDetailModal; extract tesouro branch
        tesouro_match = re.search(
            r"if\s*\(item\._type\s*===\s*'tesouro'\)\s*\{(.*?)\}",
            body, re.DOTALL,
        )
        assert tesouro_match is not None, "Tesouro branch not found."
        tesouro_body = tesouro_match.group(1)
        assert "openDetailModal" not in tesouro_body, (
            "Tesouro branch must NOT use openDetailModal."
        )


# ===================================================================
# 4.  Preservacao de zero (UI_UX §2.2 / ANALYSIS_RULES)
# ===================================================================

class TestZeroPreservation:
    """UI_UX §2.2: P/VP, P/L, EPS, VPA = 0 sao valores validos e nao
    podem ser removidos por checagem falsy ou parseFloat || null."""

    def test_no_parsefloat_or_null_remaining(self, html):
        """Nao deve restar nenhum parseFloat(...) || null no JS."""
        bad = re.findall(r'parseFloat\s*\([^)]*\)\s*\|\|\s*null', html)
        assert len(bad) == 0, (
            f"Found {len(bad)} remaining parseFloat(...) || null pattern(s): {bad}. "
            "All must use the safe triplet pattern to preserve 0."
        )

    def test_safe_pattern_for_pe(self, html):
        """PE deve usar pattern: const peRaw = ...; const pe = (peRaw...)."""
        assert re.search(
            r'const\s+peRaw\s*=\s*row\.getAttribute\(\s*[\'"]data-pe[\'"]\s*\)',
            html,
        ), "Missing safe 'peRaw' pattern for PE."

    def test_safe_pattern_for_eps(self, html):
        """EPS deve usar pattern: const epsRaw = ...; const eps = (epsRaw...)."""
        assert re.search(
            r'const\s+epsRaw\s*=\s*row\.getAttribute\(\s*[\'"]data-eps[\'"]\s*\)',
            html,
        ), "Missing safe 'epsRaw' pattern for EPS."

    def test_safe_pattern_for_vpa(self, html):
        """VPA deve usar pattern: const vpaRaw = ...; const vpa = (vpaRaw...)."""
        assert re.search(
            r'const\s+vpaRaw\s*=\s*row\.getAttribute\(\s*[\'"]data-vpa[\'"]\s*\)',
            html,
        ), "Missing safe 'vpaRaw' pattern for VPA."

    def test_pb_uses_not_null_in_render_top_picks(self, html):
        """renderTopPicks usa 'pb != null' em vez de 'if (pb)'."""
        body = _extract_render_top_picks_body(html)
        assert body is not None
        assert 'pb != null' in body, (
            "renderTopPicks must use 'pb != null' to preserve pb=0 (UI_UX §2.2)."
        )
        assert not re.search(r'\bif\s*\(\s*pb\s*\)', body), (
            "renderTopPicks must NOT use 'if (pb)' which would hide pb=0."
        )

    def test_null_values_stay_null(self, html):
        """Valores ausentes ('null' string) devem permanecer null,
        nao virar 0. Pattern: (raw !== null && raw !== 'null' && raw !== '') ? parseFloat(raw) : null."""
        # Verify pe uses safe ternary (not '|| null')
        assert re.search(
            r'const\s+pe\s*=\s*\(peRaw\s*!==\s*null\s*&&\s*peRaw\s*!==\s*\'null\'\s*&&\s*peRaw\s*!==\s*\'\'\)\s*\?\s*parseFloat\(peRaw\)\s*:\s*null',
            html,
        ), "PE must use safe ternary (raw !== null && raw !== 'null' && raw !== '')"
        # Verify eps uses safe ternary
        assert re.search(
            r'const\s+eps\s*=\s*\(epsRaw\s*!==\s*null\s*&&\s*epsRaw\s*!==\s*\'null\'\s*&&\s*epsRaw\s*!==\s*\'\'\)\s*\?\s*parseFloat\(epsRaw\)\s*:\s*null',
            html,
        ), "EPS must use safe ternary"
        # Verify vpa (stock context) uses safe ternary
        assert re.search(
            r'const\s+vpa\s*=\s*\(vpaRaw\s*!==\s*null\s*&&\s*vpaRaw\s*!==\s*\'null\'\s*&&\s*vpaRaw\s*!==\s*\'\'\)\s*\?\s*parseFloat\(vpaRaw\)\s*:\s*null',
            html,
        ), "VPA must use safe ternary (or safe ternary + fallback for FII context)"


# ===================================================================
# 5.  Tabs-row unico e posicionado (UI_UX §3.1)
# ===================================================================

class TestTabsRow:
    """UI_UX §3.1: .tabs-row existe uma unica vez, apos header,
    antes de filtros/paineis."""

    def test_tabs_row_element_exists_once(self, html):
        """Exatamente um elemento <nav class=\"tabs-row\"> no HTML."""
        matches = re.findall(r'<nav\s+class="tabs-row"\s+aria-label="Navegação principal"\s*>', html)
        assert len(matches) == 1, (
            f"Expected exactly 1 <nav class=\"tabs-row\"> element, found {len(matches)}. "
            "UI_UX §3.1 requires a single navigation bar."
        )

    def test_tabs_row_after_header(self, html):
        """DOM order: <header> ... <nav class=\"tabs-row\"> ..."""
        # Find the actual DOM elements (not CSS class references)
        header_end = html.find('>', html.find('<header'))
        tabs_div = html.find('<nav class="tabs-row"')
        assert header_end > 0 and tabs_div > 0, (
            "Could not locate <header> or <nav class=\"tabs-row\"> in DOM."
        )
        assert header_end < tabs_div, (
            "tabs-row must appear AFTER header in the DOM (UI_UX §3.1). "
            f"Header ends at {header_end}, tabs-row starts at {tabs_div}."
        )

    def test_tabs_are_sticky(self, html):
        css = re.search(r'\.tabs-row\s*\{(.*?)\}', html, re.DOTALL)
        assert css and 'position: sticky' in css.group(1) and 'top: 0' in css.group(1)


class TestPanelIsolation:
    def test_home_exists_and_stocks_start_hidden(self, html):
        assert 'id="panel-home"' in html
        assert re.search(r'id="panel-stocks"\s+class="table-wrap hidden"', html)
        assert re.search(r'class="filters-row hidden"', html)

    def test_rendafixa_contains_ettj_and_table(self, html):
        start = html.find('id="panel-rendafixa"')
        end = html.find('id="sector-detail-modal"')
        section = html[start:end]
        assert start > 0 and 'id="ettj-chart"' in section
        assert 'id="rendafixa-tbody"' in section

    def test_ettj_waits_for_visible_panel_and_reuses_instance(self, html):
        """ETTJ não pode ser bloqueado por flag antes de o painel aparecer."""
        start = html.find('function renderRendaFixaPanel')
        end = html.find('function formatFocusArray', start)
        section = html[start:end] if end > start else html[start:]
        assert '_rendafixaChartsCreated' not in section
        visibility_guard = section.find("rendaFixaPanel.classList.contains('hidden')")
        instance_guard = section.find('if (window.ettjChartInstance)')
        chart_create = section.find('new Chart(ctx')
        assert 0 <= visibility_guard < instance_guard < chart_create
        assert 'window.ettjChartInstance.resize()' in section

    def test_history_chart_has_one_active_implementation(self, html):
        """Uma duplicação parcial de renderChart invalida todo o dashboard."""
        implementations = re.findall(
            r'^\s*function\s+renderChart\s*\(', html, re.MULTILINE
        )
        assert len(implementations) == 1


# ===================================================================
# 6.  Isolamento de dominios (UI_UX §6.1)
# ===================================================================

class TestModalIsolation:
    """UI_UX §6 / §6.1: Modais tem conteudo isolado por dominio."""

    def test_no_tesouro_methodology_in_detail_modal(self, html):
        """#detail-modal nao deve conter 'Scorecard de Renda Fixa' ou
        qualquer texto/metodologia do Tesouro."""
        start = html.find('id="detail-modal"')
        end = html.find('id="td-detail-modal"')
        if end < 0:
            # fallback: find next section after detail-modal
            end = html.find('<section', start + 100)
        if end < 0:
            end = start + 3000  # reasonable bound
        section = html[start:end]

        forbidden = [
            "Scorecard de Renda Fixa",
            "Premio Real",
            "aliquota de IR",
            "indexador",
            "Tesouro",
            "Renda Fixa",
        ]
        for term in forbidden:
            if term in ["Tesouro", "Renda Fixa"]:
                # These might appear in legitimate context (e.g. "Tesouro Direto" in
                # the breadcrumb/label). Check more precisely.
                if re.search(r'(?:metodologia|crit[eé]rios|scorecard)\s+do\s+Tesouro', section, re.IGNORECASE):
                    pytest.fail(f"Tesouro methodology found inside #detail-modal: '{term}'")
            else:
                assert term not in section, (
                    f"Forbidden term '{term}' found inside #detail-modal. "
                    "UI_UX §6.1 prohibits Tesouro methodology in the asset detail modal."
                )

    def test_td_modal_has_only_tesouro_content(self, html):
        """#td-detail-modal existe e nao contem dados de renda variavel."""
        td_start = html.find('id="td-detail-modal"')
        assert td_start > 0, "#td-detail-modal element not found."

        # Check for Tesouro-specific labels in the modal template
        section = html[td_start:td_start + 2000]
        tesouro_labels = ["Taxa Atual", "Vencimento", "Preço Compra", "Preço Venda"]
        for label in tesouro_labels:
            assert label in section, (
                f"Expected Tesouro-specific label '{label}' in #td-detail-modal."
            )

        # Verify NO stock/FII-specific labels are in this modal
        stock_labels = ["P/L", "P/VP", "ROE", "DY", "Graham", "Bazin", "Scorecard"]
        for label in stock_labels:
            assert label not in section, (
                f"Stock-specific label '{label}' must NOT appear in #td-detail-modal. "
                "UI_UX §6.2 requires Tesouro-only content."
            )

        # Verify Tesouro label is NOT in #detail-modal (already covered by
        # test_no_tesouro_methodology_in_detail_modal)

    def test_legacy_macro_breakdown_is_not_rendered(self, html):
        assert "item.label === 'Moderadores Macro (v3)') return" in html


# ===================================================================
# 7.  Detail format by type (UI_UX §4.1)
# ===================================================================

class TestDetailFormat:
    """UI_UX §4.1: O detalhe de cada tipo segue formato especifico."""

    def test_stock_detail_has_dy_pb(self, html):
        """Top Acoes detail: DY xx.xx% * P/VP x.xx (sem setor)."""
        body = _extract_render_top_picks_body(html)
        assert body is not None
        assert 'DY ' in body, "Stock detail missing DY"
        assert 'P/VP ' in body, "Stock detail missing P/VP"
        # Sector nao deve aparecer no detail de nenhum tipo
        assert 'item.sector' not in body, (
            "Sector must NOT appear in renderTopPicks detail. "
            "Top Acoes detail is only DY and P/VP."
        )

    def test_fii_fiagro_detail_has_dy_pb_no_sector(self, html):
        """Top FIIs/FIAGROs detail: DY xx.xx% * P/VP x.xx."""
        body = _extract_render_top_picks_body(html)
        assert body is not None
        assert 'DY ' in body, "FII/FIAGRO detail missing DY"
        assert 'P/VP ' in body, "FII/FIAGRO detail missing P/VP"
        # Detail nao tem setor para nenhum tipo
        assert 'item.sector' not in body, "Sector must not appear in any Top Pick detail."

    def test_tesouro_detail_has_yield_and_maturity(self, html):
        """Top Tesouro detail: xx.xx% a.a. * vencimento/prazo."""
        body = _extract_render_top_picks_body(html)
        assert body is not None
        assert '% a.a.' in body, "Tesouro detail missing '% a.a.'"
        assert 'maturity' in body, "Tesouro detail missing maturity variable"

    def test_tesouro_no_dy_or_pb(self, html):
        """Top Tesouro nao deve conter DY ou P/VP no detail."""
        body = _extract_render_top_picks_body(html)
        assert body is not None
        # The tesouro branch (item._type === 'tesouro') should not set DY or P/VP
        tesouro_branch = re.search(
            r"if\s*\(item\._type\s*===\s*'tesouro'\)\s*\{(.*?)\}",
            body, re.DOTALL,
        )
        assert tesouro_branch is not None, "Tesouro branch not found in renderTopPicks"
        tesouro_body = tesouro_branch.group(1)
        assert 'DY' not in tesouro_body, "Tesouro must not contain DY in detail"
        assert 'P/VP' not in tesouro_body, "Tesouro must not contain P/VP in detail"


# ===================================================================
# 8.  Campos do generator no home_top_stocks (ANALYSIS_RULES)
# ===================================================================

class TestGeneratorFieldsInUI:
    """Verifica se os campos esperados do generator sao referenciados
    no template HTML dos Top Picks."""

    def test_pb_ratio_referenced_in_top_picks(self, html):
        """pb_ratio deve ser referenciado no renderTopPicks."""
        body = _extract_render_top_picks_body(html)
        assert body is not None
        assert 'pb_ratio' in body, (
            "pb_ratio must be referenced in renderTopPicks. "
            "Generator includes it in home_top_stocks."
        )

    def test_dividend_yield_referenced_in_top_picks(self, html):
        """dividend_yield deve ser referenciado no renderTopPicks."""
        body = _extract_render_top_picks_body(html)
        assert body is not None
        assert 'dividend_yield' in body, (
            "dividend_yield must be referenced in renderTopPicks."
        )

    def test_sector_not_in_detail_render(self, html):
        """sector nao deve estar no renderTopPicks (detail so DY e P/VP)."""
        body = _extract_render_top_picks_body(html)
        assert body is not None
        assert 'item.sector' not in body, (
            "sector must NOT be in renderTopPicks. Detail is only DY and P/VP."
        )
