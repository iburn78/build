# Analysis and reporting plan

This is a proposed extension to the current profile, news, and financial-analysis pipeline. The report-generation workflow described here is not yet implemented.

## Goal

Produce a company report that explains its business, recent performance, competitive position, and risks. Include segment and value-chain context where the available evidence supports it. Cite the source articles and dates used in the report.

## Evidence workflow

1. Gather current profile, financial, segment, and news information.
2. Extract article-level insights with topic, factual points, financial signal, business segment, sentiment, publication date, and source reference.
3. Identify questions that remain unanswered, such as performance drivers or competitor differences.
4. Run targeted follow-up searches using company, segment, competitor, and issue terms. Example queries:
   - `{company} 실적`
   - `{company} 전망`
   - `{company} {segment} 수익성`
   - `{company} 경쟁사 {competitor}`
5. Repeat retrieval while important gaps remain and the retrieval budget allows.
6. Generate the report with references attached to factual claims.

Treat prior reports as historical hypotheses, not current evidence. Recheck their claims against current sources; newer reporting does not automatically invalidate a claim unless it addresses the same fact or period.

## Proposed report structure

- Main businesses (up to three)
- Recent overall and segment performance, with stated reasons
- Competitor comparison: performance differences and competitive advantages
- Key issues and risks, overall and by segment where possible
- Source references for factual claims

Possible structured types:

- `ArticleInsight`: topic, key points, financial signal, business segment, sentiment, publication date, source URL
- `QualitativeReport`: main businesses, performance summary, segment analyses, competitor analysis, key issues, references
- `QualitativeRating`: profitability, growth, and competitiveness

Before using rating labels such as `best`, `top-tier`, `2nd-tier`, and `else`, define the peer group, comparison period, and rubric. Ratings should be supported by cited evidence and kept separate from the narrative report.

## Human review

Keep the existing `reviewed` field as the human approval boundary for editable profile information. Generated reports should retain source references so reviewers can inspect and revise claims.
