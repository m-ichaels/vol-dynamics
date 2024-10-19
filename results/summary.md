# Results summary

Generated from `results/*.json` by `scripts/summarize.py`.

## Data built

- BTC: 12,218,677 near-the-money prints into 3,406 days of implied term structure (2017-02-14 to 2026-09-18); 2,956 days of 5-minute realised variance, annualised 67 % (close-to-close 64 %); BNS jump days 32% at 5 %, 26% at 1 %, jump variation 6% of RV; 30-day print-implied against DVOL: corr 0.985, mean gap -4.03 pts on 2,005 days; SSVI slices 3,459 days, median RMSE 1.77 vol points, butterfly-free 100 %.
- ETH: 7,153,447 near-the-money prints into 2,738 days of implied term structure (2019-03-21 to 2026-09-18); 2,744 days of 5-minute realised variance, annualised 85 % (close-to-close 83 %); BNS jump days 27% at 5 %, 22% at 1 %, jump variation 4% of RV; 30-day print-implied against DVOL: corr 0.986, mean gap -4.94 pts on 2,005 days; SSVI slices 2,739 days, median RMSE 1.57 vol points, butterfly-free 100 %.
- SPY: 1,267 daily SSVI slices (2019-02-09 to 2026-09-17), median RMSE 0.98 vol points, butterfly-free 100 %, mean 25-delta skew 5.8 points.
- US daily estimators for 13 underlyings, 65,403 rows; mean ratio of each estimator to close-to-close: park 0.579, gk 0.567, rs 0.571, yz21 0.928.

## The variance risk premium

30-day premium by asset: implied (the Cboe index or, for crypto, the print-implied 30-day vol) against the vol realised over the following 21 trading days (30 calendar days for crypto). Intervals are circular block bootstraps with the horizon as block length. Slope: realised variance regressed on implied variance (Newey-West s.e.).

| implied index | underlying | class | from | to | n days | mean implied | mean realised | gap (vol pts) | 95 % CI | share positive | RV-on-IV slope (s.e.) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DVOLX_BTC | Bitcoin (DVOL index, 2021+) | crypto | 2021 | 2026 | 1,974 | 63.1 | 55.4 | 8.16 | [5.20, 11.05] | 71 % | 0.51 (0.08) |
| OVX | crude oil (USO) | commodity | 2009 | 2026 | 4,248 | 41.7 | 36.7 | 5.91 | [4.35, 7.33] | 79 % | 0.42 (0.16) |
| DVOLX_ETH | Ether (DVOL index, 2021+) | crypto | 2021 | 2026 | 1,974 | 77.7 | 75.3 | 4.03 | [-0.25, 8.20] | 63 % | 0.63 (0.13) |
| VXAZN | Amazon | single name | 2011 | 2026 | 3,919 | 35.4 | 32.9 | 3.85 | [2.81, 4.91] | 74 % | 0.87 (0.06) |
| VXAPL | Apple | single name | 2011 | 2026 | 3,919 | 30.7 | 28.3 | 3.72 | [2.63, 4.74] | 74 % | 0.76 (0.10) |
| VXEEM | EM equities (EEM) | equity index | 2011 | 2026 | 3,873 | 24.1 | 21.5 | 3.57 | [2.62, 4.30] | 81 % | 0.64 (0.06) |
| DVOL_BTC | Bitcoin (30d ATM from prints) | crypto | 2018 | 2026 | 2,926 | 64.7 | 64.0 | 3.53 | [-0.63, 7.30] | 66 % | 0.48 (0.08) |
| RVX | Russell 2000 | equity index | 2009 | 2026 | 4,249 | 24.9 | 22.7 | 3.53 | [2.47, 4.37] | 82 % | 0.89 (0.15) |
| VIX | S&P 500 | equity index | 2006 | 2026 | 5,007 | 21.5 | 19.6 | 3.51 | [2.58, 4.33] | 83 % | 0.90 (0.12) |
| VXGS | Goldman Sachs | single name | 2011 | 2026 | 3,919 | 31.2 | 29.0 | 3.46 | [2.21, 4.54] | 77 % | 0.73 (0.11) |
| VXD | Dow Jones | equity index | 2009 | 2026 | 4,249 | 18.4 | 16.5 | 3.41 | [2.46, 4.15] | 85 % | 0.99 (0.31) |
| VXN | Nasdaq-100 | equity index | 2009 | 2026 | 4,256 | 22.6 | 20.8 | 3.00 | [2.06, 3.80] | 79 % | 0.83 (0.13) |
| VXGOG | Alphabet | single name | 2011 | 2026 | 3,919 | 29.4 | 27.9 | 2.67 | [1.70, 3.64] | 71 % | 0.79 (0.08) |
| VXIBM | IBM | single name | 2011 | 2026 | 3,919 | 26.1 | 25.7 | 2.64 | [1.45, 3.76] | 74 % | 1.19 (0.27) |
| GVZ | gold (GLD) | commodity | 2009 | 2026 | 4,248 | 18.6 | 16.9 | 2.36 | [1.76, 2.91] | 79 % | 0.72 (0.11) |
| VXTLT | 20y+ Treasuries (TLT) | rates | 2006 | 2026 | 4,997 | 16.1 | 14.9 | 1.48 | [1.03, 1.89] | 72 % | 0.70 (0.08) |
| DVOL_ETH | Ether (30d ATM from prints) | crypto | 2019 | 2026 | 2,707 | 77.9 | 83.0 | -1.75 | [-6.79, 2.65] | 55 % | 0.65 (0.12) |

S&P 500 premium by tenor (VIX family):

| index | tenor (days) | n | implied | realised | gap (vol pts) | 95 % CI | share positive |
|---|---|---|---|---|---|---|---|
| VIX9D | 9 | 3,941 | 19.3 | 17.2 | 3.64 | [3.21, 4.01] | 82 % |
| VIX | 30 | 5,007 | 21.5 | 19.6 | 3.51 | [2.58, 4.33] | 83 % |
| VIX3M | 93 | 4,209 | 21.3 | 17.2 | 5.12 | [3.43, 6.50] | 86 % |
| VIX6M | 184 | 4,578 | 23.9 | 19.9 | 5.45 | [2.88, 7.76] | 84 % |

BTC premium by tenor (print-implied term structure; the last row uses 5-minute realised variance as the realised leg):

| tenor | n | implied | realised | gap (vol pts) | 95 % CI | share positive |
|---|---|---|---|---|---|---|
| 7 | 2,949 | 64.0 | 63.8 | 6.21 | [3.52, 8.51] | 69 % |
| 30 | 2,926 | 64.7 | 64.0 | 3.53 | [-0.63, 7.30] | 66 % |
| 60 | 2,896 | 66.0 | 64.1 | 3.67 | [-1.23, 8.27] | 67 % |
| 90 | 2,866 | 67.1 | 64.4 | 4.12 | [-1.32, 8.80] | 68 % |
| 30_rv5min | 2,926 | 64.7 | 67.4 | 0.17 | [-3.78, 3.93] | 61 % |
| 30_dvol | 1,974 | 63.1 | 55.4 | 8.16 | [5.20, 11.05] | 71 % |
| 30_atm_since_2021 | 1,974 | 58.5 | 55.4 | 4.09 | [1.14, 6.92] | 67 % |

ETH premium by tenor (print-implied term structure; the last row uses 5-minute realised variance as the realised leg):

| tenor | n | implied | realised | gap (vol pts) | 95 % CI | share positive |
|---|---|---|---|---|---|---|
| 7 | 2,730 | 77.2 | 82.9 | 2.04 | [-0.97, 5.04] | 61 % |
| 30 | 2,707 | 77.9 | 83.0 | -1.75 | [-6.79, 2.65] | 55 % |
| 60 | 2,677 | 79.3 | 83.1 | -1.66 | [-8.09, 4.04] | 55 % |
| 90 | 2,647 | 80.3 | 83.1 | -1.31 | [-8.20, 4.31] | 54 % |
| 30_rv5min | 2,707 | 77.9 | 85.3 | -4.26 | [-9.16, 0.05] | 52 % |
| 30_dvol | 1,974 | 77.7 | 75.3 | 4.03 | [-0.25, 8.20] | 63 % |
| 30_atm_since_2021 | 1,974 | 72.1 | 75.3 | -0.96 | [-5.27, 3.24] | 56 % |

S&P premium by regime (VIX terciles, then by the sign of VIX3M minus VIX on the day):

| regime | n | mean VIX | gap (vol pts) | VRP (var pts) | 95 % CI | share positive |
|---|---|---|---|---|---|---|
| VIX low | 1,669 | 12.9 | 2.25 | 20 | [-32, 55] | 82 % |
| VIX mid | 1,669 | 17.5 | 3.52 | 70 | [24, 110] | 83 % |
| VIX high | 1,669 | 28.6 | 4.75 | 141 | [-42, 289] | 84 % |
| contango (long above short) | 3,927 | - | 3.76 | 94 | [53, 125] | 85 % |
| backwardation | 325 | - | 4.38 | 63 | [-535, 480] | 83 % |

Skew dynamics from daily SSVI fits of the expiry nearest 30 days:

| surface | slices | mean 25-delta skew (pts) | SSR (s.e.) | R² | mean |change| at fixed strike | at fixed moneyness | on large moves: strike / moneyness | verdict |
|---|---|---|---|---|---|---|---|---|
| BTC | 3,139 | 3.8 | 1.67 (0.08) | 0.13 | 2.22 | 2.28 | 3.57 / 3.74 | closer to sticky strike |
| SPY | 1,267 | 5.8 | 1.27 (0.03) | 0.67 | 0.72 | 1.23 | 1.25 / 2.84 | closer to sticky strike |

## Forecasting realised variance

Walk-forward, refit every 21 days on the trailing window, horizon 21 trading days (30 for crypto). QLIKE and the RMSE of the forecast vol (daily units x 1e4); DM: Diebold-Mariano of HAR+IV against HAR on QLIKE (negative favours adding implied vol); encompassing weights from a log regression of realised on the implied-only and HAR forecasts.

| asset | n | RW QLIKE | GARCH | HAR | HAR+IV | IV only | DM (p) | weight IV / HAR | HAR+IV RMSE vs HAR |
|---|---|---|---|---|---|---|---|---|---|
| S&P 500 | 3,988 | 0.60 | 0.43 | 0.46 | 0.40 | 0.40 | -1.3 (0.184) | 0.80 / 0.06 | 49.1 vs 51.6 |
| Nasdaq-100 | 3,988 | 0.43 | 0.32 | 0.33 | 0.28 | 0.28 | -1.5 (0.146) | 0.76 / 0.19 | 52.2 vs 53.2 |
| Russell 2000 | 3,983 | 0.39 | 0.30 | 0.34 | 0.28 | 0.28 | -1.3 (0.193) | 0.82 / 0.05 | 54.7 vs 58.7 |
| Dow Jones | 3,985 | 0.58 | 0.42 | 0.44 | 0.40 | 0.39 | -1.3 (0.204) | 0.78 / 0.06 | 49.7 vs 51.3 |
| EM equities (EEM) | 3,648 | 0.31 | 0.26 | 0.28 | 0.25 | 0.24 | -1.2 (0.227) | 0.88 / -0.10 | 46.5 vs 50.3 |
| 20y+ Treasuries (TLT) | 3,984 | 0.21 | 0.19 | 0.21 | 0.17 | 0.17 | -1.7 (0.097) | 0.79 / 0.18 | 28.4 vs 30.2 |
| gold (GLD) | 3,984 | 0.35 | 0.26 | 0.26 | 0.22 | 0.21 | -1.9 (0.057) | 1.13 / -0.26 | 34.2 vs 37.6 |
| crude oil (USO) | 3,984 | 0.39 | 0.31 | 0.34 | 0.25 | 0.24 | -3.0 (0.003) | 0.91 / 0.02 | 97.6 vs 101.0 |
| Apple | 3,690 | 0.40 | 0.28 | 0.28 | 0.21 | 0.21 | -3.4 (0.001) | 0.88 / -0.05 | 62.7 vs 67.4 |
| Amazon | 3,690 | 0.53 | 0.32 | 0.30 | 0.19 | 0.19 | -7.4 (0.000) | 0.95 / -0.07 | 61.7 vs 79.1 |
| Alphabet | 3,690 | 0.50 | 0.31 | 0.29 | 0.23 | 0.22 | -4.1 (0.000) | 0.97 / -0.11 | 55.4 vs 63.7 |
| IBM | 3,690 | 0.71 | 0.41 | 0.45 | 0.30 | 0.30 | -4.1 (0.000) | 1.03 / -0.13 | 65.9 vs 77.6 |
| Goldman Sachs | 3,690 | 0.37 | 0.30 | 0.32 | 0.24 | 0.23 | -2.1 (0.033) | 1.05 / -0.35 | 64.4 vs 72.5 |
| Bitcoin | 2,175 | 0.26 | 0.17 | 0.17 | 0.16 | 0.16 | -1.1 (0.260) | 0.77 / 0.09 | 100.6 vs 103.2 |
| Ether | 1,963 | 0.26 | 0.20 | 0.19 | 0.21 | 0.20 | 0.9 (0.374) | 0.67 / 0.07 | 142.8 vs 139.2 |

## Events

FOMC (62 decision days, 2019-2026): S&P |move| 0.95 % against 0.79 % on other days; RMS move over implied daily move (VIX / sqrt(252) the day before) 1.02 on FOMC days against 1.00 otherwise; TLT |move| 0.73 % vs 0.71 %, RMS over VXTLT-implied 0.88. VIX change on the day 0.05 pts (down on 56 % of days), VIX9D from the day before to the day after -0.84 pts. VIX1D (35 events since 2022): implied daily move 1.23 %, realised RMS 1.21 %, ratio 0.98.

Earnings (1,093 events): implied move from the front straddle by the 0.8 x straddle rule 5.38 %, stripped of the diffusion 6.01 %; realised |close-to-close| 4.65 % (RMS implied 6.77 vs RMS realised 6.37); implied above realised on 67 % of events, median ratio 1.44; Spearman(implied, |realised|) 0.43; realised² on implied² slope 0.46. Seller of the straddle: mean 0.27 % of spot per event, -0.43 % after the quoted spread, hit rate 55 %, sd 3.11 %, worst -25.52 %.

| year | n | implied (stripped) % | realised % | RMS implied / realised | seller after spread % | hit |
|---|---|---|---|---|---|---|
| 2020 | 135 | 5.29 | 3.83 | 6.04 / 5.53 | -0.51 | 60 % |
| 2021 | 146 | 4.13 | 3.44 | 4.66 / 4.50 | -0.50 | 53 % |
| 2022 | 141 | 6.23 | 4.78 | 6.96 / 6.41 | -0.13 | 57 % |
| 2023 | 167 | 5.77 | 4.49 | 6.68 / 5.84 | 0.03 | 59 % |
| 2024 | 178 | 6.54 | 5.42 | 7.29 / 7.46 | -0.53 | 54 % |
| 2025 | 186 | 6.82 | 4.55 | 7.44 / 6.27 | -0.19 | 56 % |
| 2026 | 140 | 6.99 | 5.89 | 7.55 / 7.80 | -1.32 | 42 % |

| name | n | implied (stripped) % | realised % | seller after spread % | hit |
|---|---|---|---|---|---|
| ABBV | 27 | 4.26 | 3.56 | -0.86 | 22 % |
| ADBE | 27 | 8.30 | 6.32 | -0.73 | 52 % |
| AMD | 27 | 9.32 | 6.78 | 0.30 | 56 % |
| CSCO | 27 | 6.94 | 5.58 | -1.13 | 37 % |
| HD | 27 | 4.23 | 2.67 | 0.22 | 74 % |
| ORCL | 27 | 9.55 | 7.48 | -0.88 | 44 % |
| PYPL | 27 | 9.82 | 8.07 | -0.24 | 59 % |
| QCOM | 27 | 7.56 | 6.68 | -1.14 | 41 % |
| SBUX | 27 | 7.31 | 4.55 | 0.19 | 63 % |
| XOM | 27 | 3.89 | 2.05 | -0.38 | 67 % |
| BA | 26 | 5.03 | 3.70 | 0.21 | 69 % |
| BAC | 26 | 3.91 | 2.75 | 0.16 | 65 % |
| CAT | 26 | 5.80 | 3.93 | -0.31 | 58 % |
| CRM | 26 | 8.45 | 7.00 | -1.19 | 62 % |
| CVX | 26 | 2.79 | 2.74 | -0.72 | 46 % |
| INTC | 26 | 9.02 | 9.45 | -1.52 | 58 % |
| JNJ | 26 | 2.88 | 1.98 | -0.21 | 58 % |
| JPM | 26 | 3.72 | 2.64 | 0.03 | 58 % |
| LLY | 26 | 5.61 | 5.16 | -1.29 | 38 % |
| MA | 26 | 3.79 | 2.53 | -0.16 | 58 % |
| MCD | 26 | 3.53 | 1.82 | 0.27 | 65 % |
| MRK | 26 | 4.05 | 2.92 | -0.28 | 58 % |
| MSFT | 26 | 5.45 | 4.45 | -0.19 | 58 % |
| MU | 26 | 9.34 | 6.50 | 0.24 | 65 % |
| NKE | 26 | 8.60 | 8.12 | -1.73 | 54 % |
| PFE | 26 | 5.21 | 2.35 | 1.17 | 81 % |
| TXN | 26 | 6.43 | 4.90 | -0.63 | 46 % |
| UNH | 26 | 3.90 | 5.04 | -2.08 | 31 % |
| V | 26 | 4.17 | 2.43 | 0.10 | 73 % |
| VZ | 26 | 3.74 | 3.40 | -0.90 | 50 % |
| DIS | 25 | 7.10 | 5.50 | -0.71 | 44 % |
| IBM | 25 | 6.45 | 5.23 | -1.34 | 40 % |
| KO | 25 | 2.81 | 1.82 | 0.18 | 76 % |
| PEP | 25 | 2.82 | 2.36 | -0.43 | 36 % |
| AAPL | 23 | 5.66 | 2.88 | 0.35 | 70 % |
| GS | 23 | 3.57 | 2.14 | 0.10 | 65 % |
| COST | 19 | 4.06 | 2.27 | 0.41 | 63 % |
| T | 18 | 5.30 | 4.25 | -0.83 | 44 % |
| AMZN | 17 | 8.89 | 6.60 | 0.04 | 53 % |
| GOOGL | 17 | 6.95 | 5.30 | 0.07 | 53 % |
| META | 17 | 10.54 | 9.98 | -2.09 | 47 % |
| TSLA | 16 | 9.30 | 9.16 | -1.40 | 44 % |
| GE | 11 | 8.81 | 5.69 | 0.82 | 36 % |
| UBER | 11 | 9.42 | 5.54 | 1.61 | 82 % |
| WMT | 10 | 6.22 | 5.27 | -0.61 | 40 % |
| AVGO | 9 | 9.12 | 9.81 | -3.36 | 11 % |
| NVDA | 9 | 8.19 | 4.33 | 1.18 | 89 % |

BTC calendar: weekend/weekday variance ratio 0.58 (annualised 55 % vs 72 %), by year 2018: 0.66, 2019: 0.82, 2020: 0.52, 2021: 0.69, 2022: 0.50, 2023: 0.41, 2024: 0.38, 2025: 0.39, 2026: 0.50; the half-hours after the 00/08/16 UTC funding marks run 1.28 x the variance of other hours. Implied: the 7-day vol on Fridays is -3.27 ± 0.45 pts against the following Monday (lower on 69 % of 485 weeks).

ETH calendar: weekend/weekday variance ratio 0.61 (annualised 70 % vs 90 %), by year 2019: 0.68, 2020: 0.70, 2021: 0.61, 2022: 0.59, 2023: 0.51, 2024: 0.45, 2025: 0.55, 2026: 0.59; the half-hours after the 00/08/16 UTC funding marks run 1.41 x the variance of other hours. Implied: the 7-day vol on Fridays is -3.53 ± 0.52 pts against the following Monday (lower on 69 % of 391 weeks).

## The VIX complex

| state (VIX9D / VIX / VIX3M) | share of days | mean VIX | realised next 21 days | premium (pts) | VIX change over 21 days |
|---|---|---|---|---|---|
| backwardation | 6.9 % | 30.7 | 27.3 | 3.42 | -5.91 |
| contango | 72.7 % | 16.5 | 12.9 | 3.67 | 0.87 |
| front kink (9D > VIX < 3M) | 19.7 % | 19.4 | 16.2 | 3.16 | -0.87 |
| hump (9D < VIX > 3M) | 0.7 % | 30.0 | 21.0 | 8.99 | -7.65 |

VX curve 2013-05-20 to 2026-09-17, 3,356 days, in contango (F2 > F1) 85 % of days. Roll-down in index points per 30 days, mean (median): VIX→F1 1.15 (1.78), F1 0.89 (1.02), F2 0.51 (0.64), F3 0.35 (0.43), F4 0.28 (0.32).

Short front-month roll, one contract, 13.33 years: gross 12.1 pts/yr, bid-ask 0.54 pts/yr, net 11.6 pts/yr ($11,584 a contract-year), Sharpe 0.58, max drawdown 64.6 pts, worst day -19.2 on 2020-03-16. Net per day when yesterday's curve was in contango 0.034 against 0.111 in backwardation; shorting only after contango days: 7.2 pts/yr, Sharpe 0.54.

| year | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| net pts | 4.7 | 1.4 | 6.1 | 18.6 | 17.6 | -16.8 | 31.0 | -3.0 | 33.9 | 6.6 | 30.6 | 4.3 | 9.0 | 10.3 |

VVIX: mean 95.5; realised vol of the 30-day constant-maturity future over the next 21 days 64.0 (vol-of-vol premium 33.1 pts, CI [29.0, 37.0]); of the spot index 114.6. Correlation with the VIX level 0.64, with the 3M-1M slope -0.35; VVIX by slope tercile: backwardated 101.0, flat 90.0, steep 95.5.

## Strategies

All programs: one unit (one straddle on one share / one coin), daily delta hedge, spread paid at entry (and exit where closed early), scenario margin = worst loss over ±15 % spot × ±30 % vol. Return on margin is net P&L per year over the average margin.

| program | trades | years | hit | gross / trade (% spot) | cost / trade | net / trade | worst trade | opt / hedge share of gross | return on margin (%/yr) | max DD (% margin) | daily Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SPY short straddle, all | 697 | 7.61 | 61 % | 0.11 | 0.06 | 0.05 | -10.5 | 0.62 / 0.38 | 4.0 | 68 | 0.24 |
| SPY straddle, VIX3M > VIX at entry | 643 | 7.61 | 61 % | 0.16 | 0.05 | 0.10 | -3.7 | 1.26 / -0.26 | 6.5 | 61 | 0.42 |
| SPY straddle, VIX3M <= VIX at entry | 54 | 6.28 | 59 % | -0.47 | 0.12 | -0.59 | -10.5 | -4.17 / 3.17 | -7.0 | 86 | -0.83 |
| SPY straddle, none, in sample (to 2021-12-31) | 349 | 2.97 | 66 % | 0.20 | 0.07 | 0.13 | -10.5 | 0.81 / 0.19 | 8.9 | 44 | 0.67 |
| SPY straddle, none, out of sample | 348 | 4.71 | 55 % | 0.02 | 0.05 | -0.03 | -5.1 | 0.17 / 0.83 | 0.7 | 56 | 0.05 |
| SPY straddle, stop_0.5x_premium, in sample (to 2021-12-31) | 349 | 2.97 | 66 % | 0.25 | 0.08 | 0.17 | -7.3 | 1.72 / -0.72 | 11.5 | 35 | 0.88 |
| SPY straddle, stop_0.5x_premium, out of sample | 348 | 4.71 | 55 % | 0.04 | 0.05 | -0.01 | -4.4 | 0.10 / 0.90 | 2.1 | 47 | 0.16 |
| SPY straddle, stop_1.0x_premium, in sample (to 2021-12-31) | 349 | 2.97 | 66 % | 0.20 | 0.07 | 0.13 | -11.3 | 0.81 / 0.19 | 8.9 | 44 | 0.67 |
| SPY straddle, stop_1.0x_premium, out of sample | 348 | 4.71 | 55 % | 0.02 | 0.05 | -0.03 | -4.7 | 0.00 / 1.00 | 0.8 | 55 | 0.06 |
| SPY straddle, stop_2.0x_premium, in sample (to 2021-12-31) | 349 | 2.97 | 66 % | 0.20 | 0.07 | 0.13 | -10.5 | 0.81 / 0.19 | 8.9 | 44 | 0.67 |
| SPY straddle, stop_2.0x_premium, out of sample | 348 | 4.71 | 55 % | 0.02 | 0.05 | -0.03 | -5.1 | 0.17 / 0.83 | 0.7 | 56 | 0.05 |
| SPY calendar (short front, long second, vega-neutral) | 667 | 7.61 | 47 % | 0.01 | 0.08 | -0.07 | -3.4 | -10.71 / 11.71 | -4.0 | 48 | -0.49 |
| BTC short 30-day straddle, all | 95 | 8.06 | 62 % | 1.61 | 0.54 | 1.07 | -15.1 | 0.78 / 0.22 | 49.4 | 121 | 0.74 |
| BTC straddle, iv60 > iv30 at entry | 71 | 8.06 | 59 % | 1.20 | 0.54 | 0.66 | -15.1 | 1.14 / -0.14 | 38.1 | 81 | 0.81 |
| BTC straddle, iv60 <= iv30 at entry | 24 | 7.72 | 71 % | 2.82 | 0.53 | 2.28 | -8.7 | -0.65 / 1.65 | 11.5 | 103 | 0.54 |
| BTC straddle, costless | 95 | 8.06 | 64 % | 1.61 | 0.20 | 1.41 | -14.8 | 0.78 / 0.22 | 69.3 | 118 | 1.04 |
| ETH short 30-day straddle, all | 88 | 7.47 | 51 % | 0.18 | 0.54 | -0.37 | -23.6 | 0.57 / 0.43 | -13.9 | 277 | -0.12 |
| ETH straddle, iv60 > iv30 at entry | 64 | 7.04 | 55 % | 0.49 | 0.54 | -0.05 | -14.5 | -0.85 / 1.85 | 17.6 | 225 | 0.23 |
| ETH straddle, iv60 <= iv30 at entry | 24 | 7.3 | 42 % | -0.65 | 0.55 | -1.20 | -23.6 | 1.95 / -2.95 | -35.3 | 375 | -0.85 |
| ETH straddle, costless | 88 | 7.47 | 53 % | 0.18 | 0.20 | -0.03 | -23.3 | 0.57 / 0.43 | 6.1 | 260 | 0.06 |

Stop-loss chosen in sample: stop_0.5x_premium.

spy_straddle net by entry year: 2019: 34.4 (47, hit 74 %), 2020: 29.6 (153, hit 59 %), 2021: 108.2 (150, hit 69 %), 2022: -211.9 (139, hit 36 %), 2023: 77.9 (51, hit 78 %), 2024: -51.0 (58, hit 52 %), 2025: 81.1 (58, hit 74 %), 2026: 126.5 (41, hit 71 %)

btc_straddle net by entry year: 2018: 1138.0 (5, hit 60 %), 2019: 1613.6 (12, hit 50 %), 2020: 489.3 (12, hit 50 %), 2021: 10869.9 (11, hit 82 %), 2022: 844.7 (12, hit 67 %), 2023: -1933.9 (12, hit 58 %), 2024: 17901.3 (12, hit 75 %), 2025: 5376.0 (11, hit 55 %), 2026: -2558.1 (8, hit 62 %)
