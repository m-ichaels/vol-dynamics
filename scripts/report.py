#!/usr/bin/env python3
"""report.pdf from results/summary.md and results/figures/*.png (fpdf2).   python scripts/report.py"""
import os
import sys

from fpdf import FPDF

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "results")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "report.pdf")

INTRO = """Question. Which volatility dynamics are stable enough to trade? On complete free histories: the gap between implied and subsequently realised variance by asset and tenor, how well realised variance can be forecast and whether implied vol adds to the forecast, the size and persistence of the earnings and FOMC premia, the VIX term structure and the roll of its futures, the calendar of a 24/7 market, and what each of these leaves after bid-ask, hedging costs and margin when turned into a systematic strategy.

Data. Cboe daily histories of nineteen volatility indices (VIX family, VVIX, SKEW, VXN, RVX, VXD, GVZ, OVX, VXTLT, VXEEM and five single-name indices) and every VX futures contract since 2013; every Deribit BTC and ETH option print since the first trade (Nov 2016 / Mar 2019) with the exchange's implied vol, plus 5-minute perpetual candles and DVOL; DoltHub end-of-day option chains and earnings dates for SPY and fifty large caps; Yahoo daily bars; SOFR from the New York Fed; the FOMC calendar. The surface engine (Black, implied vol, SSVI slices, forwards from parity) is Project H's.

Method. Realised variance from OHLC estimators and 5-minute returns with the Barndorff-Nielsen-Shephard jump test. HAR-RV, HAR with implied variance, GARCH(1,1) and a random walk fitted walk-forward and scored by QLIKE with Diebold-Mariano tests. The premium as implied variance minus forward realised variance with circular block-bootstrap intervals, by asset, tenor, year and regime. Skew stickiness from daily SSVI fits. Earnings: the implied move stripped of the diffusion from two expiries against the realised move, and the straddle seller's P&L after the quoted spread. FOMC: the path of the short-dated indices and realised against implied on decision days. The VX curve, roll-down and the short-front roll net of bid-ask. Strategies in an engine that marks Black-Scholes daily, hedges delta daily at a stated cost, settles at intrinsic and quotes return per unit of a scenario margin; parameters chosen on the first half and reported on the second.

Caveats. The DoltHub chains are sparse (about three expiries and twenty strikes a day, weekly before 2023), so the SPY strategies are marked to model between chain dates and settled on the real close. Crypto option spreads are an assumption stated in the code. The OTC vol markets have no free history. Results are stated with the years they cover; a single regime is not allowed to carry an average without saying so."""

FIGS = [("premia.png", "The variance risk premium: by asset with block-bootstrap intervals, by year, and by tenor for the S&P and for BTC and ETH."),
        ("forecast.png", "Forecasting realised variance: QLIKE by model and asset, the Diebold-Mariano statistic of adding implied vol to HAR, and the encompassing weights."),
        ("vix.png", "The VIX complex: index and futures, roll-down along the curve, the short-front roll net of bid-ask, and what follows each term-structure state."),
        ("events.png", "Events: implied vol into and out of FOMC decisions; earnings implied against realised moves and the premium by year."),
        ("crypto.png", "Crypto: print-implied against realised vol and DVOL, realised vol by hour of day with the weekend ratio, and the 30-day skew from daily SSVI fits."),
        ("strategies.png", "Strategies: cumulative net P&L of the delta-hedged straddle programs, the seller's per-trade distribution, and return on margin gross against net.")]


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9); self.set_text_color(120); self.cell(0, 6, "ProjectI - volatility dynamics research and systematic volatility strategies", align="R"); self.ln(8); self.set_text_color(0)

    def footer(self):
        self.set_y(-12); self.set_font("Helvetica", "", 8); self.set_text_color(120); self.cell(0, 6, f"{self.page_no()}", align="C")


def clean(s):
    for a, b in (("–", "-"), ("—", "-"), ("−", "-"), ("×", "x"), ("≥", ">="), ("≤", "<="), ("…", "..."), ("²", "^2"), ("±", "+/-"), ("**", ""), ("`", ""), ("→", "->"), ("≈", "~"), ("é", "e"), ("’", "'"), ("σ", "sigma"), ("Σ", "Sigma"), ("β", "beta"), ("γ", "gamma"), ("λ", "lambda"), ("α", "alpha"), ("τ", "tau"), ("Δ", "d"), ("∑", "sum"), ("√", "sqrt"), ("ρ", "rho"), ("θ", "theta"), ("ψ", "psi"), ("φ", "phi"), ("π", "pi"), ("μ", "mu")):
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


def md_table(pdf, rows):
    cols = [c.strip() for c in rows[0].strip("|").split("|")]
    data = [[clean(c.strip()) for c in r.strip("|").split("|")] for r in rows[2:]]
    n = len(cols); w = (pdf.w - 20) / n; fs = 6.5 if n <= 7 else 4.8; cut = 42 if n <= 7 else 20
    pdf.set_font("Helvetica", "B", fs)
    for c in cols:
        pdf.cell(w, 5, clean(c)[:cut], border=1)
    pdf.ln(5); pdf.set_font("Helvetica", "", fs)
    for r in data[:90]:
        if pdf.get_y() > pdf.h - 20:
            pdf.add_page()
        for c in r[:n]:
            pdf.cell(w, 4.5, c[:cut], border=1)
        pdf.ln(4.5)
    pdf.ln(2)


def main():
    pdf = PDF(); pdf.set_auto_page_break(auto=True, margin=15); pdf.add_page()
    pdf.set_font("Helvetica", "B", 16); pdf.cell(0, 10, "Volatility Dynamics Research and Systematic Vol Strategies", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for para in INTRO.split("\n\n"):
        pdf.multi_cell(0, 4.5, clean(para)); pdf.ln(2)
    for fn, cap in FIGS:
        p = os.path.join(R, "figures", fn)
        if not os.path.exists(p):
            continue
        if pdf.get_y() > pdf.h - 90:
            pdf.add_page()
        pdf.image(p, w=pdf.w - 20); pdf.set_font("Helvetica", "I", 8); pdf.multi_cell(0, 4, clean(cap)); pdf.ln(3); pdf.set_font("Helvetica", "", 9)
    sm = os.path.join(R, "summary.md")
    if os.path.exists(sm):
        pdf.add_page(); lines = open(sm, encoding="utf-8").read().splitlines(); i = 0
        while i < len(lines):
            l = lines[i]
            if l.startswith("## "):
                pdf.set_font("Helvetica", "B", 11); pdf.ln(2); pdf.cell(0, 7, clean(l[3:]), new_x="LMARGIN", new_y="NEXT"); pdf.set_font("Helvetica", "", 9); i += 1
            elif l.startswith("|"):
                j = i
                while j < len(lines) and lines[j].startswith("|"):
                    j += 1
                if j - i >= 2:
                    md_table(pdf, lines[i:j])
                i = j
            elif l.startswith("# "):
                i += 1
            elif l.strip():
                pdf.set_x(pdf.l_margin); pdf.multi_cell(0, 4.5, clean(l.strip())); i += 1
            else:
                i += 1
    pdf.output(OUT); print("wrote", OUT)


if __name__ == "__main__":
    main()
