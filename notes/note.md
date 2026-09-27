# Project notes

## Project purpose

- Compare companies with their competitors.
- Connect companies to components and value chains.
- See [process.md](process.md) for the current data and report workflow.
- See [plan.md](plan.md) for the proposed evidence-based company-report workflow.

## Running the local services

- Start the Node report server from `data/node` with `node server.js`; it serves the shared data directory on port 3000.
- Profile generation and news summarization use the LLM modes configured in `build/tools/settings.py`. The default is Ollama, which must be running locally. OpenAI mode reads credentials from the project-level config file; keep that file private.

## Data and text handling

- FnGuide company summaries are the current profile-generation input; news articles are crawled and stored locally before summarization.
- Normalize Korean text to NFC when comparing or searching names. NFC and NFD can represent the same visible Hangul with different Unicode sequences, especially across macOS filenames and application APIs.
- Keep report claims tied to their article or source references; crawled files retain source URLs and publication dates.

## Typed LLM output

Use Pydantic models as structured output schemas with `pydantic_ai`. A schema validates and may coerce generated values; it does not establish that the content is factually correct. Review and source checks remain necessary.

Current configured Ollama model names are in `tools/settings.py`; avoid relying on cached model details or machine-specific download paths in project documentation.
