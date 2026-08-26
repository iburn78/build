## Models

### CompanyProfile
---
- ProfileManager access key: code
- filename: code_filename.json
- Overview: auto-update (outside THRESHOLD)
- Business(InfoSection): auto-update (AI-summary using Overview) if not reviewed
- News: crawl and AI summary, auto-update (outside THRESHOLD)
- financials: generated from "financials"

### Component
---
- ComponentManager access key: name 
- filename: name.json
- companies: list(Company(code, name): a class separately created to represent a company)
- Traits(InfoSection): auto-update not yet implemented
- financials: generated from "financials"

#### Component info to fill
- 제품
- 경쟁사: 순위(leader), M/S, 경쟁력
- 상대적, 전체적 Economics (individual company vs whole component)
- Key drivers (기술, innovation, 수요동인)
- 변화의 원인, 변화의 추이

### ValueChain
---
- ValueChainManager access key: name 
- filename: name.json
- components: list(str: component_names)
    - to get component objects, use get_components()
- Landscape(InfoSection): auto-update not yet implemented
- financials: generated from "financials"

#### ValueChain info to fill
- components: 공급관계, key component
- 상대적, 전체적 Economics (individual component vs between components)
- Key drivers (key component, 최종제품의 수요동인)
- 변화의 원인, 변화의 추이

#### Valuechain structure
- Operational chain: 원재료(2차) -> 소재사(1차, components, consumerables) -> 제조사 -> 소비자
- Capex chain; infra(건설사, 장비사, modifications) -> 제조사 <- 협력업체 (maintenances, outsourcings)