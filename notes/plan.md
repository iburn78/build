queries = [
 f"{name} 실적",
 f"{name} 전망",
 f"{name} {seg}",
 f"{name} {seg} 수익성",
 f"{name} 경쟁사 {competitor}",
]

class ArticleInsight(BaseModel):
    topic: str
    key_points: list[str]
    financial_signal: str | None
    business_segment: str | None
    sentiment: Literal[
        "positive",
        "neutral",
        "negative"
    ]

-------------

feed previous report might be risky: model repeats old conclusions

class HistoricalFinding(BaseModel):
    statement: str
    confidence: float
    evidence_date: str

prompt: 
Treat previous reports as historical hypotheses. Current news overrides old conclusions.

-------------

Report generation

[qualitative]
- explanation on the main businesses (top 3)
- recent financial performance (overall and/or for each business segs) and reasons behind
- main competitor and compared to the competitor on (1) why financial performances are differ and (2) what are differences in competitve advantages
- key issues that this company is facing: overall and/or for each business segs

class QualitativeReport(BaseModel):
    main_businesses: list[str]
    performance_summary: str
    business_analysis: list[
        BusinessSegment
    ]
    competitor_analysis: str
    key_issues: list[str]

[rating]

class QualitativeRating(BaseModel):
    profitability:
        Literal[
            "best",
            "top-tier",
            "2nd-tier",
            "else"
        ]
    growth:
        Literal[
            "best",
            "top-tier",
            "2nd-tier",
            "else"
        ]
    competitiveness:
        Literal[
            "best",
            "top-tier",
            "2nd-tier",
            "else"
        ]

--------------

make retrieval iterative

extract
↓
crawl
↓
summarize
↓
missing information?
↓
extra retrieval
↓
report


-------------

leave references clearly in the report
(as crawled news articles are all stored locally)