"""generate_stock_fundamentals.py — produces two paired fixture files:

  raw_fundamentals.json      — what a raw data source (e.g. yfinance .info) would hand back.
                                Used by M5 (to test cache_manager.get_fundamentals) and by M3
                                (as the INPUT to fundamentals_formatter.py's own tests).
  stock_fundamentals.json    — the fully-formatted StockFundamentals objects (26 badged KpiCards
                                per stock), i.e. the OUTPUT fundamentals_formatter.py should
                                produce. Used directly by M1 as its stock-detail mock data, and
                                usable by M3 as an expected-output fixture for its own tests.

Values are deliberately spread across good/fair/weak so the badge variety is visible in the UI
mock -- not everything is green. All figures are dummy, in crore units already (no unit
conversion applied downstream), and dated to a fixed "as_of" so output is reproducible.
"""
import json
from datetime import date

THRESHOLDS = json.load(open("kpi_thresholds.json"))
AS_OF = "2026-08-01"

# Raw fundamentals per ticker, in crore units, sector-flavored so badges vary realistically.
RAW = {
    "TCS.NS": dict(net_profit_margin=0.19, gross_margin=0.52, ebitda=18500, revenue_growth=0.09,
                   total_revenue=64000, net_income=12200, operating_margin=0.24, earnings_growth=0.08,
                   current_ratio=2.1, quick_ratio=2.0, de_ratio=8.5, working_capital=32000,
                   total_cash=28000, total_debt=2400, roe=0.42, roa=0.28,
                   operating_cf=15200, free_cf=13800,
                   pe_ratio=27.3, price_to_book=11.4, ev_to_ebitda=19.8, dividend_yield=0.032,
                   beta=0.68, peg_ratio=1.8, rev_per_employee=1.15, payout_ratio=0.72),
    "INFY.NS": dict(net_profit_margin=0.17, gross_margin=0.48, ebitda=11200, revenue_growth=0.06,
                    total_revenue=39000, net_income=6600, operating_margin=0.21, earnings_growth=0.04,
                    current_ratio=2.4, quick_ratio=2.3, de_ratio=6.0, working_capital=19500,
                    total_cash=15000, total_debt=900, roe=0.31, roa=0.19,
                    operating_cf=8600, free_cf=7300,
                    pe_ratio=24.1, price_to_book=7.9, ev_to_ebitda=15.2, dividend_yield=0.028,
                    beta=0.72, peg_ratio=2.1, rev_per_employee=0.98, payout_ratio=0.68),
    "HDFCBANK.NS": dict(net_profit_margin=0.24, gross_margin=0.55, ebitda=52000, revenue_growth=0.13,
                         total_revenue=210000, net_income=50400, operating_margin=0.29, earnings_growth=0.12,
                         current_ratio=1.1, quick_ratio=1.0, de_ratio=680, working_capital=45000,
                         total_cash=95000, total_debt=620000, roe=0.17, roa=0.019,
                         operating_cf=61000, free_cf=52000,
                         pe_ratio=19.4, price_to_book=2.8, ev_to_ebitda=11.5, dividend_yield=0.011,
                         beta=1.05, peg_ratio=1.4, rev_per_employee=2.4, payout_ratio=0.21),
    "ICICIBANK.NS": dict(net_profit_margin=0.22, gross_margin=0.53, ebitda=41000, revenue_growth=0.15,
                          total_revenue=165000, net_income=36300, operating_margin=0.27, earnings_growth=0.16,
                          current_ratio=1.1, quick_ratio=1.0, de_ratio=710, working_capital=38000,
                          total_cash=82000, total_debt=510000, roe=0.18, roa=0.021,
                          operating_cf=48000, free_cf=41000,
                          pe_ratio=18.2, price_to_book=3.1, ev_to_ebitda=10.8, dividend_yield=0.009,
                          beta=1.12, peg_ratio=1.1, rev_per_employee=2.1, payout_ratio=0.18),
    "RELIANCE.NS": dict(net_profit_margin=0.08, gross_margin=0.31, ebitda=48000, revenue_growth=0.07,
                         total_revenue=900000, net_income=72000, operating_margin=0.13, earnings_growth=0.05,
                         current_ratio=1.2, quick_ratio=0.9, de_ratio=42, working_capital=28000,
                         total_cash=190000, total_debt=310000, roe=0.09, roa=0.045,
                         operating_cf=98000, free_cf=-12000,
                         pe_ratio=24.8, price_to_book=2.1, ev_to_ebitda=12.1, dividend_yield=0.004,
                         beta=1.18, peg_ratio=3.2, rev_per_employee=1.6, payout_ratio=0.09),
    "ITC.NS": dict(net_profit_margin=0.27, gross_margin=0.61, ebitda=21000, revenue_growth=0.06,
                   total_revenue=70000, net_income=19000, operating_margin=0.35, earnings_growth=0.07,
                   current_ratio=3.2, quick_ratio=2.6, de_ratio=2.1, working_capital=18000,
                   total_cash=8500, total_debt=180, roe=0.28, roa=0.24,
                   operating_cf=17500, free_cf=16200,
                   pe_ratio=22.6, price_to_book=6.2, ev_to_ebitda=16.4, dividend_yield=0.041,
                   beta=0.58, peg_ratio=2.8, rev_per_employee=0.42, payout_ratio=0.85),
    "SUNPHARMA.NS": dict(net_profit_margin=0.16, gross_margin=0.68, ebitda=8200, revenue_growth=0.11,
                          total_revenue=48000, net_income=7700, operating_margin=0.19, earnings_growth=0.09,
                          current_ratio=1.9, quick_ratio=1.5, de_ratio=15, working_capital=9200,
                          total_cash=6100, total_debt=2900, roe=0.14, roa=0.10,
                          operating_cf=8900, free_cf=6400,
                          pe_ratio=34.2, price_to_book=5.1, ev_to_ebitda=21.3, dividend_yield=0.008,
                          beta=0.61, peg_ratio=2.5, rev_per_employee=0.71, payout_ratio=0.19),
    "MARUTI.NS": dict(net_profit_margin=0.06, gross_margin=0.24, ebitda=9800, revenue_growth=0.04,
                       total_revenue=145000, net_income=8700, operating_margin=0.08, earnings_growth=-0.03,
                       current_ratio=0.9, quick_ratio=0.6, de_ratio=5, working_capital=-3200,
                       total_cash=42000, total_debt=650, roe=0.13, roa=0.09,
                       operating_cf=11200, free_cf=3100,
                       pe_ratio=28.9, price_to_book=3.6, ev_to_ebitda=17.9, dividend_yield=0.007,
                       beta=1.24, peg_ratio=4.6, rev_per_employee=1.3, payout_ratio=0.24),
}


def eval_rule(value, rule):
    ok = True
    if "gt" in rule: ok = ok and value > rule["gt"]
    if "gte" in rule: ok = ok and value >= rule["gte"]
    if "lt" in rule: ok = ok and value < rule["lt"]
    if "lte" in rule: ok = ok and value <= rule["lte"]
    return ok


def fmt_value(value, fmt):
    if fmt == "pct": return f"{value*100:.1f}%"
    if fmt == "cr": return f"\u20b9{value:,.0f} Cr"
    if fmt == "x": return f"{value:.2f}x"
    if fmt == "pctx": return f"{value:.1f}%"
    return f"{value:.2f}"


def badge_for(value, metric_cfg, colors):
    for rule in metric_cfg["rules"]:
        if eval_rule(value, rule):
            return rule["label"], colors[rule["color"]]
    d = metric_cfg["default"]
    return d["label"], colors[d["color"]]


def build_kpi_cards(raw: dict, group: list) -> list:
    cards = []
    for cfg in group:
        key = cfg["metric_key"]
        value = raw[key]
        label, color = badge_for(value, cfg, THRESHOLDS["colors"])
        cards.append({
            "label": cfg["label"],
            "value_str": fmt_value(value, cfg["format"]),
            "badge_label": label,
            "badge_color": color,
            "tooltip": f"{cfg['label']} for this stock, most recent reported figures.",
        })
    return cards


def main():
    raw_out = {}
    formatted_out = {}
    for ticker, raw in RAW.items():
        raw_out[ticker] = {"as_of": AS_OF, "source": "yfinance (dummy fixture)", **raw}
        formatted_out[ticker] = {
            "ticker": ticker,
            "as_of": AS_OF,
            "income_statement": build_kpi_cards(raw, THRESHOLDS["income_statement"]),
            "balance_sheet": build_kpi_cards(raw, THRESHOLDS["balance_sheet"]),
            "cash_flow": build_kpi_cards(raw, THRESHOLDS["cash_flow"]),
            "valuation": build_kpi_cards(raw, THRESHOLDS["valuation"]),
            "source": "yfinance (dummy fixture)",
        }

    with open("raw_fundamentals.json", "w") as f:
        json.dump(raw_out, f, indent=2, ensure_ascii=False)
    with open("stock_fundamentals.json", "w") as f:
        json.dump(formatted_out, f, indent=2, ensure_ascii=False)

    print(f"Wrote raw_fundamentals.json and stock_fundamentals.json for {len(RAW)} tickers.")


if __name__ == "__main__":
    main()
