# Build process

Last edited: 2026-10-21

## Data locations

`tools/settings.py` locates the shared data directory as a sibling of the `build` project:

- `data/build/profiles`: company profiles and segment records
- `data/build/components`: component definitions and generated analysis files
- `data/build/valuechains`: value-chain definitions and generated analysis files
- `data/build/news`: crawled article files

Python model JSON, charts, and HTML reports are written into these directories. The Node app in `data/node` serves the shared `data` directory on port 3000.

## Model relationships

- **Profile** (`key`/`code`): company identity, generated or reviewed `Business` information, source `Overview`, and `News`. Its financial-analysis end key is the company key.
- **Segment** (key such as `005930(A)`): a virtual part of a company. It uses the parent profile's financial data and applies a `FinancialsAdjuster`.
- **Component** (`key`): a group of `ListedCompany` records. Each record points to a company profile or segment by `key` and carries a display `name`. Component financial-analysis end keys are the listed-company keys.
- **ValueChain** (`key`): an ordered list of components. Its end keys are the union of the listed-company keys in its components.

Each persisted model has a JSON file, an `info_section`, and optional generated `financials`. Components store references in `listed_companies`; value chains store component names/keys in `component_keys`. The in-memory `_sub_items` map is not serialized.

## Creating or refreshing models

`Profile.get_item()`, `Component.get_item()`, and `ValueChain.get_item()` load, refresh, or create model records. `dataset_generation.py` uses these class methods directly; it does not rely on the old manager classes.

Value chains accept either of these inputs:

- `component_keys=[...]` to provide component names/keys
- `components=[...]` to provide `Component` instances

Pass one argument, not both. The `components` form uses the supplied instances in memory and derives the persisted `component_keys` from their keys. On load, the value chain checks that every referenced component JSON exists and validates before loading components; missing or invalid components are reported by name.

The common `JsonModel.get_item(key, **kwargs)` lifecycle is:

1. Find a JSON file by key prefix in the model's directory.
2. Load a valid file and call `_update(**kwargs)` to apply requested changes and refresh eligible data.
3. Save the JSON when `_update` reports a change.
4. If an existing file fails validation, try to recover its `info_section` only when that section has `reviewed: true`, then create a replacement using the supplied arguments. The current recovery path does not preserve the old `financials` object.
5. If no file exists, create and save a new model.

Loading a value chain populates its component sub-items. Loading a component resolves its listed-company profiles and segments. Profile segment reconciliation runs when the business information is reviewed and `create_segments` is enabled; obsolete profile-prefixed files are removed.

## Profile refresh

- Overview content is fetched from FnGuide when its saved timestamp is at least 30 days old or invalid.
- If the business information has not been reviewed, a language model regenerates it from the overview. Reviewed business information is retained.
- News is crawled from Google News result links and selected local articles are summarized by a language model. News refreshes after the configured three-day threshold.
- Segment files are created/reconciled only for reviewed profiles with `create_segments` enabled.

## Financial analysis and artifacts

`SectorAnalysis.process()` obtains each model's financial-analysis end keys, loads price, volume, and quarterly financial series, aggregates the series, and writes analysis results into the model JSON's `financials` field. It also produces a PNG chart and an HTML page. For models with sub-items, it recursively analyzes them and adds relative share/rank fields to child results.

Assessment metrics are computed only when at least five quarterly points are available after the configured start date. Component and value-chain aggregates use current membership; the historical interpretation of membership and missing periods remains a known choice.

## Node app and qualitative editing

- `data/node/server.js` serves static files from `data` and lists report HTML files from `data/build`.
- Relationship endpoints read component and value-chain JSON using `key`, `listed_companies[].key`, and `component_keys`. The lookup UI uses the same fields.
- Relationship JSON is reloaded for each request, so data-file updates do not require a Node restart.
- Qualitative editing uses a password check to issue a short-lived, single-use token. The browser posts edited `info_section` values to Node; Node starts `build/tools/update_info.py`; Python validates and saves the section, then reruns `SectorAnalysis.process()` to refresh report artifacts.

## Current implementation status

Profile, segment, component, and value-chain models, their JSON lifecycle, financial analysis, news collection, HTML editing, and Node relationship views are implemented. Value chains now validate referenced component JSON before loading and accept either component instances or keys as input. The evidence-driven, cited company-report workflow in [plan.md](plan.md) remains a proposal.
