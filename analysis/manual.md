# Financial Analysis Reference

This manual describes the units, calculations, and assessment rules used in generated financial analyses.

## Shared metadata

- `meta.unit` is the scale used for monetary financial values. For example, with the default unit of ₩1 billion, a value of `1` represents ₩1 billion.
- `meta.start_date` is the first date used for quarterly operating-income trend calculations.
- `MEASURE_PERIOD` is the recent comparison window. `BASE_PERIOD` is the maximum number of valid observations considered, including the recent window.
- Zero and non-finite observations are omitted by `calc_increment()`.

## Financial data

### `shape`

- `shape.financials` contains monetary values scaled by `meta.unit`.
- `shape.share` contains each member's share of the group's latest market capitalization and quarterly revenue, plus its rank.
- Operating-income share uses only positive member operating income in its denominator. Operating-income ranks still include negative values.

### `assess_data.opincome`

Quarterly financial data may be forward-filled when a new quarter has not yet been reported.

- `positive_ltm`: true when each of the latest four quarterly operating-income values is positive.
- `higher(comp)`: true when the latest quarter is at least `100 - ALLOWED_FLUCTUATION_PERCENT` percent of the greater of the previous quarter and the same quarter a year earlier.
- `slope`: linear-regression slope of quarterly operating income from `meta.start_date`, in `meta.unit` per quarter.
- `growth(%)`: `slope / mean quarterly operating income × 100` over that same period. This is a percentage per quarter.

### `assess_data.opmargin`

- The quarterly entries are operating margins for the latest four quarters, stored as percentage values.
- `ltm(%)` is the total operating income divided by total revenue for the latest four quarters, multiplied by 100.

### `assess_data.volatility` and `assess_data.amount`

Both use `measure_to_base(%)` to compare a recent mean with the preceding baseline mean:

```text
measure_to_base(%) = recent-window mean / preceding-baseline mean × 100
```

A result of `100` means the recent mean equals the baseline mean.

- Volatility uses the absolute daily percentage change in market capitalization.
- Amount uses daily trading amount, scaled by `meta.unit`.
- The latest `MEASURE_PERIOD` valid non-zero observations form the recent window. The preceding observations within `BASE_PERIOD` form the baseline.

### `assess_data.alpha_beta`

- `alpha(%)` is the estimated daily excess return, expressed in percentage points.
- `beta` is the dimensionless market sensitivity estimated from daily returns.
- `from_start_date`, `base_period`, and `measure_period` contain estimates using the corresponding history windows.
- `indplot_period` compares each member's recent `INDIVIDUAL_PLOT_DAYS` market-cap returns with the return of the group's summed market capitalization. The group sum does not deduplicate profiles or segments.

### `assess_data.PER`

- `PER_ltm`: current market capitalization divided by operating income for the latest four quarters.
- `PER_qx4`: current market capitalization divided by the latest quarter's operating income annualized by multiplying by four.
- `PER_fwd`: current market capitalization divided by projected operating income for the next four quarters, based on the quarterly operating-income regression slope. The latest reported quarter is excluded from the projection.

## Assessment rules

### Basics

`basics` is true when all three conditions hold:

- Operating income was positive in each of the latest four quarters.
- Latest quarterly operating income meets the `higher(comp)` comparison.
- The quarterly operating-income slope is positive.

### Financial soundness

`financially_sound` is true when either condition holds:

- `opincome.growth(%)` is at least `OPINCOME_GROWTH_PERCENT`.
- Each of the latest four quarterly operating margins and the LTM operating margin is at least `OPMARGIN_THRESHOLD_PERCENT`.

### Movement labels

- Volatility is `Up` or `Dn` when `measure_to_base(%)` is more than `VOLATILITY_THRESHOLD_PERCENT` above or below `100`, respectively.
- Trading amount uses the same comparison with `AMOUNT_DAILY_THRESHOLD_PERCENT`.
- `alpha_level` compares daily `alpha(%)` with `±ALPHA_DAILY_THRESHOLD_PERCENT`.

### Valuation and category

`PER_level` is determined by `PER_ltm`:

- `Low`: below `PER_LOW`.
- `Mid`: from `PER_LOW` up to, but not including, `PER_MED`.
- `High`: at least `PER_MED`.

### Market sentiment

Market sentiment combines the movement labels:

| Trading amount | Volatility | Sentiment |
| --- | --- | --- |
| Up | Dn | `confidence` |
| Up | Up | `unstable` |
| Dn | Dn | `consumed` |
| Dn | Up | `speculators` |

Other combinations are labeled `-`.

### Categorization

The final category is assigned as follows:

- If both `basics` and `financially_sound` are true: `A` for Low PER, `B` for Mid PER, and `C` for High PER.
- Otherwise: `D`.
