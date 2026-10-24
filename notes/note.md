# Project notes

Last edited: 2026-10-21

## Project purpose

- Compare companies with their competitors.
- Organize company and segment records into components and value chains.
- See [structure.md](structure.md) for model terminology, [process.md](process.md) for the current workflow, and [plan.md](plan.md) for the proposed company-report workflow.

## Model terminology

- **Profile** represents a listed company or a tracked business record.
- **Segment** represents part of a company and applies a `FinancialsAdjuster` to the parent profile's financial data.
- **Component** groups `ListedCompany` records. Each record refers to a profile or segment by `key` and includes a display `name`.
- **ValueChain** groups components. Its persisted references are `component_keys`, which are component names/keys.
- `ValueChain.get_item()` accepts either `component_keys=[...]` or `components=[...]` containing `Component` instances. The component instances are used in memory; the value-chain JSON stores only `component_keys`. Pass one argument, not both.
- A value chain checks that referenced component JSON files exist and validate before loading them. Missing or invalid files are reported by component name.

## Running local services

- Start the Node report server from `data/node` with `node server.js`; it serves the shared data directory on port 3000.
- Profile generation and news summarization use the LLM modes configured in `build/models/settings.py`. The default Ollama mode calls Ollama Cloud directly; the separate `local` mode uses the local Ollama server. OpenAI mode reads credentials from the project-level config file; keep that file private.

## Data and text handling

- FnGuide company summaries are the current profile-generation input. News articles are crawled and stored locally before summarization.
- Normalize Korean text to NFC when comparing or searching names. NFC and NFD can represent the same visible Hangul with different Unicode sequences, especially across macOS filenames and application APIs.
- Keep report claims tied to their article or source references; crawled files retain source URLs and publication dates.

## Typed LLM output

Use Pydantic models as structured output schemas with `pydantic_ai`. A schema validates and may coerce generated values; it does not establish that the content is factually correct. Review and source checks remain necessary.

Current configured Ollama model names are in `models/settings.py`; avoid relying on cached model details or machine-specific download paths in project documentation.
