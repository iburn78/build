## Key Differentiators
- should also focus on competitors 
- identify value chains for companies

<br><br>

## Envs
- Chrome downloaded to /Users/andy/Library/Caches/ms-playwright/chromium-1223
- Scrapping from fnguide is easier

<br><br>

## ollama 
> show gemma4

#### Model core
- architecture (gemma4)
    → the transformer design + multimodal extensions (vision/audio/tools support)

- parameters (8.0B)
    → number of learned weights (~8 billion fixed values)

- context length (131072)
    → maximum tokens the model can “see” at once (prompt + history + output)

- embedding length (2560)
    → size of internal vector representation per token

<br>

#### Compression
Capabilities are supported interfaces, not always active features.
- quantization (Q4_K_M)
    → weights stored in compressed 4-bit format with scaling
    → reduces RAM + bandwidth usage → faster inference on local hardware
- Capabilities (important correction)
- completion → text generation (core function)
- vision/audio → input understanding only (not generation)
- tools → model can request external functions (you must implement them)
- thinking → model supports reasoning mode, but not always explicitly separate unless enabled

<br>

#### Sampling parameters (runtime behavior)
These control style and variability, not intelligence.
- temperature → randomness level
- top_p → probability cutoff sampling
- top_k → restrict candidate tokens

<br>

#### Runtime
Model = (weights + architecture)
1. Prefill (fast parallel GPU pass over input)
    - Prefill: parallel matrix operations → very fast (thousands tokens/sec)
2. KV cache creation
    - storing intermediate calc values (used in a single request, many vectors per token (layer × heads × dimensions))
3. Decode loop:
    - Decode (generation): sequential token-by-token → slow (tens tokens/sec)
    - read weights from memory
    - compute next token
    - repeat (slow, sequential)


<br><br>

## Pydantic - typechecking
Pydantic will:
- validate input types
- coerce types when possible
- raise ValidationError if invalid

Example usage:

    from pydantic import BaseModel, computed_field

    class Rectangle(BaseModel):
        width: int
        height: int

        @computed_field         # lets included in dump
        @property               # lets accessible as property
        def area(self) -> int:  # return type required
            return self.width * self.height

    r = Rectangle(width=3, height=4)

    print(r.area)
    print(r.model_dump())
    print(r.model_dump_json())
    # {'width': 3, 'height': 4, 'area': 12}

Connecting with Local LLM model

    from typing import Literal
    from typing import Annotated
    from pydantic import BaseModel, StringConstraints
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from openai import AsyncOpenAI

    TickerStr = Annotated[
        str,
        StringConstraints(pattern=r'^[A-Z]{1,5}$')
    ]

    class StockAnalysis(BaseModel):
        ticker: TickerStr
        sentiment: Literal['bullish', 'bearish', 'neutral'] # or 'str' 
        confidence: float

    client = AsyncOpenAI(
        base_url='http://localhost:11434/v1',
        api_key='-'
    )

    model = OpenAIChatModel(
        model_name='gemma4',
        provider=OpenAIProvider(openai_client=client),
    )

    agent = Agent(
        model=model,
        output_type=StockAnalysis,
    )

    request_text = 'Analyze NVDA stock sentiment.'

    # result = await agent.run(request_text) # when run in notebook:
    result = agent.run_sync(request_text) # run in terminal
    print(result.output)

## Sentence Transformers
Converts sentences to vectors

    from sentence_transformers import SentenceTransformer
    from sentence_transformers.util import cos_sim

    # LLM model downloaded in ~/.cache/huggingface/
    model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
    titles = []
    vecs = model.encode(titles)
    score = cos_sim(vecs[0], vecs[1]).item()