# Build process

## Data locations

`tools/settings.py` locates the shared data directory as a sibling of the `build` project:

- `data/build/profiles`: company profiles and their segment records
- `data/build/components`: component definitions and generated analysis files
- `data/build/valuechains`: value-chain definitions and generated analysis files
- `data/build/news`: crawled article files, grouped by company

Python model JSON, charts, and HTML reports are written into these directories. The Node app in `data/node` serves the shared `data` directory on port 3000.

## Model hierarchy

- **Profile** (`key`/`code`): company identity, generated or reviewed `Business` info, source `Overview`, and `News` summary. A profile's financial-analysis end key is its own company key.
- **Segment** (`key` like `005930(A)`): a virtual part of a company. It points to the parent company's profile data and applies a `FinancialsAdjuster` to that company's financial series.
- **Component** (`key`): a group of `Member` records. A member has a company or segment key and display name. Component end keys are the member keys.
- **ValueChain** (`key`): an ordered list of component keys. Its end keys are the union of the component members' keys.

Each persisted model has one JSON file, an `info_section`, and optional generated `financials`. Components serialize their members under `members`; value chains serialize their component references under `component_keys`.

## `JsonModel.get_item(key, **kwargs)` lifecycle

1. Find a JSON file by key prefix in the model's directory.
2. If it validates, model initialization rebuilds in-memory `_sub_items`; then `_update(**kwargs)` applies requested input changes or refreshes eligible data.
3. Save the JSON only if `_update` reports a change.
4. If the existing file cannot be validated, try to recover its `info_section` only when that section has `reviewed: true`. Build a replacement from the supplied arguments and recovered section, then save it. The current recovery path does not preserve the old `financials` object.
5. If no file exists, build and save a new model.

`_sub_items` is an in-memory relationship map, not a serialized field. Loading a value chain loads its components; loading a component resolves its member profiles and segments. Profile segment reconciliation runs only when the business info is reviewed and `create_segments` is true; it removes profile-prefixed files that are not part of the currently declared segment set.

## Profile refresh

- Overview content is fetched from FnGuide when its saved timestamp is at least 30 days old or invalid.
- If the business info has not been reviewed, a language model regenerates it from the overview. Reviewed business info is retained.
- News is crawled from Google News result links and the selected local articles are summarized by a language model. News refreshes after its 3-day threshold.
- Segment files are created/reconciled only for reviewed profiles with `create_segments` enabled.

## Financial analysis and artifacts

`SectorAnalysis.process(model)` obtains the model's end keys, loads price/volume and quarterly financial series for those keys, aggregates the series, and writes analysis results into the model JSON's `financials` field. It then produces a PNG chart and an HTML page. When a model has sub-items, it recursively analyzes those and adds relative share/rank fields to the child results.

Assessment metrics are computed only when at least five quarterly points are available after the configured start date. The analysis also uses current membership for component/value-chain aggregates; the historical meaning of membership and missing periods is a known interpretation choice.

## Node app and qualitative editing

- `data/node/server.js` serves static files from `data` and lists report HTML files from `data/build`.
- Relationship endpoints read component and value-chain JSON from disk and use the current Python fields (`key`, `members[].key`, `component_keys`). `lookup.js` also accepts the older `name`/`companies`/`component_names` fields while old JSON is being renewed.
- Relationship JSON is reloaded for each relationship request, so file updates do not require a Node restart.
- Qualitative editing uses a password check to issue a short-lived, single-use token. The browser posts edited info-section values to Node; Node starts `build/tools/update_info.py`; Python validates and saves the section, then reruns `SectorAnalysis.process()` to refresh the report artifacts.

## Current implementation note

`dataset_generation.py` still imports `ProfileManager`, `ComponentManager`, and `ValueChainManager`, but those classes are not currently defined in the model files. The script therefore needs its orchestration calls updated to the current `Profile`, `Component`, and `ValueChain` class methods (or the manager classes restored) before it can run as written.
