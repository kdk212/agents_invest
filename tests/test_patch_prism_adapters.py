from scripts import patch_prism_adapters as patcher


def test_patch_trigger_batch_wires_profit_adapter(tmp_path, monkeypatch):
    target = tmp_path / "trigger_batch.py"
    target.write_text(
        """
import logging


def select_final_tickers():
    if True:
        for name, scored_df in []:
            if True:
                scored_df[\"final_score\"] = (
                    scored_df[\"composite_score_norm\"] * w_comp +
                    scored_df[\"agent_fit_score\"] * w_agent +
                    scored_df[\"rs_score\"] * w_rs +
                    scored_df[\"extension_score\"] * w_ext
                )

                # Sort by final score
                scored_df = scored_df.sort_values(\"final_score\", ascending=False)

    score_column = \"final_score\" if use_hybrid and trade_date else \"composite_score\"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(patcher, "TRIGGER_BATCH", target)

    result = patcher.patch_trigger_batch()
    text = target.read_text(encoding="utf-8")

    assert result.changed
    assert "from optimization import enrich_trigger_dataframe_with_profit_scores" in text
    assert "enrich_trigger_dataframe_with_profit_scores(" in text
    assert 'score_column = "profit_score"' in text

    second = patcher.patch_trigger_batch()
    assert not second.changed


def test_patch_stock_tracking_wires_risk_governor_and_profit_context(tmp_path, monkeypatch):
    target = tmp_path / "stock_tracking_agent.py"
    target.write_text(
        """
from cores.utils import parse_llm_json


async def _extract_trading_scenario(
    self,
    report_content: str,
    rank_change_msg: str = "",
    ticker: str = None,
    sector: str = None,
    trigger_type: str = "",
    trigger_mode: str = ""
):
    trigger_info_section = ""
    # Prepare prompt based on language
    if self.language == "ko":
        prompt_message = f"""
        {trigger_info_section}
        """
    return {}


async def _analyze_report_core(self, pdf_report_path: str):
    report_content = "report"
    ticker = "005930"
    rank_change_msg = ""
    trigger_info = getattr(self, "trigger_info_map", {}).get(ticker, {})
    trigger_type = trigger_info.get('trigger_type', '')
    trigger_mode = trigger_info.get('trigger_mode', '')
    scenario = await self._extract_trading_scenario(
        report_content,
        rank_change_msg,
        ticker=ticker,
        sector=None,
        trigger_type=trigger_type,
        trigger_mode=trigger_mode
    )
    raw_decision = scenario.get("decision", "No entry")
    return raw_decision


async def process_reports(self):
    for state in analysis_states:
        analysis_result = state["analysis"]
        ticker = analysis_result.get("ticker")
        company_name = analysis_result.get("company_name")
        current_price = analysis_result.get("current_price", 0)
        scenario = analysis_result.get("scenario", {})
        sector = analysis_result.get("sector", "Unknown")
        rank_change_msg = analysis_result.get("rank_change_msg", "")
        current_slots = await self._get_current_slots_count()
        buy_score = scenario.get("buy_score", 0)
        min_score = scenario.get("min_score", 0)
        logger.info(f"Buy score check: {company_name}({ticker}) - Score: {buy_score}")

        if analysis_result.get("decision") == "Enter":
            buy_success = await self.buy_stock(ticker, company_name, current_price, scenario, rank_change_msg)


async def run(self, trigger_results_file: str = None):
    for trigger_type, stocks in trigger_data.items():
        if isinstance(stocks, list):
            for stock in stocks:
                ticker = stock.get('code', '')
                if ticker:
                    self.trigger_info_map[ticker] = {
                        'trigger_type': trigger_type,
                        'trigger_mode': trigger_data.get('metadata', {}).get('trigger_mode', ''),
                        'risk_reward_ratio': stock.get('risk_reward_ratio', 0)
                    }
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(patcher, "STOCK_TRACKING", target)

    result = patcher.patch_stock_tracking()
    text = target.read_text(encoding="utf-8")

    assert result.changed
    assert "from optimization import apply_risk_governor_to_scenario" in text
    assert "'profit_score': stock.get('profit_score', 0)" in text
    assert "### agents_invest Profit Context" in text
    assert "trigger_profit_context" in text
    assert '"profit_score": trigger_info.get("profit_score"' in text
    assert "apply_risk_governor_to_scenario(" in text
    assert "Purchase deferred by RiskGovernor" in text

    second = patcher.patch_stock_tracking()
    assert not second.changed


def test_patch_trading_agents_adds_profit_prompt_addendum(tmp_path, monkeypatch):
    target = tmp_path / "trading_agents.py"
    target.write_text(
        '''
def create_trading_scenario_agent(language="ko"):
    if language == "en":
        instruction = """
        ## Tool Usage
        - use tools

        ## JSON Response Format
        {}
        """
    else:
        instruction = """
        ## 도구 사용
        - 도구를 사용

        ## JSON 응답 형식
        {}
        """
    return instruction
'''.lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(patcher, "TRADING_AGENTS", target)

    result = patcher.patch_trading_agents()
    text = target.read_text(encoding="utf-8")

    assert result.changed
    assert "agents_invest Profit Optimization Addendum" in text
    assert "profit_score" in text
    assert "risk_governor_context" in text

    second = patcher.patch_trading_agents()
    assert not second.changed


def test_patch_missing_upstream_files_is_non_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(patcher, "TRIGGER_BATCH", tmp_path / "missing_trigger.py")
    monkeypatch.setattr(patcher, "STOCK_TRACKING", tmp_path / "missing_stock.py")
    monkeypatch.setattr(patcher, "TRADING_AGENTS", tmp_path / "missing_trading_agents.py")

    assert not patcher.patch_trigger_batch().changed
    assert not patcher.patch_stock_tracking().changed
    assert not patcher.patch_trading_agents().changed
