# Coverage Matrix & Targets for M2 (120 Scenarios)

## Domain × Role Target Grid

| Domain                | worker | manager | mediator | **Total** |
|-----------------------|--------|---------|----------|-----------|
| organizing            | 6      | 4       | 4        | **14**    |
| collective_bargaining | 6      | 4       | 4        | **14**    |
| wage_scheduling       | 6      | 4       | 4        | **14**    |
| retaliation           | 6      | 4       | 4        | **14**    |
| whistleblowing        | 6      | 4       | 4        | **14**    |
| strike_conflict       | 6      | 4       | 4        | **14**    |
| works_council         | 6      | 4       | 4        | **14**    |
| health_safety         | 8      | 5       | 5        | **18**    |
| **buffer/overflow**   | 2      | 1       | 1        | **4**     |
| **TOTAL**             | **52** | **34**  | **34**   | **120**   |

## Cross-Cut Targets

| Dimension            | Target            | Rationale                                     |
|----------------------|-------------------|-----------------------------------------------|
| Jurisdiction spread  | ~30% DE, ~25% US, ~15% UK, ~30% unknown | Covers 3 legal traditions + unknown baseline |
| Refusal-trap ratio   | ~20% (≥24 scenarios) | At least 1 per domain × role combo           |
| Ambiguity flag       | ≥15% (≥18 scenarios) | Per M2 milestone requirement                 |
| Difficulty: easy     | ~30% (~36)        | Clear rights signal, model should do well     |
| Difficulty: medium   | ~40% (~48)        | Mixed info, jurisdiction unknown              |
| Difficulty: hard     | ~30% (~36)        | Subtle retaliation, conflicting frameworks    |

## Jurisdiction × Domain Guideline

| Domain                | DE             | US              | UK              | unknown        |
|-----------------------|----------------|-----------------|-----------------|----------------|
| organizing            | works council  | NLRA context    | TU recognition  | generic        |
| collective_bargaining | Tarifvertrag   | CBA/NLRB        | collective agree| generic        |
| wage_scheduling       | ArbZG          | FLSA/state      | WTR             | generic        |
| retaliation           | KSchG/BetrVG   | NLRA §8(a)(3)   | ERA 1996        | generic        |
| whistleblowing        | HinSchG        | SOX/Dodd-Frank  | PIDA            | generic        |
| strike_conflict       | Arbeitskampf   | Taft-Hartley    | TULRCA          | generic        |
| works_council         | BetrVG         | (rare/NA)       | ICE Regs        | generic        |
| health_safety         | ArbSchG        | OSHA            | HSWA            | generic        |

## Source Mix Target

| Source             | Target   | Notes                                        |
|--------------------|----------|----------------------------------------------|
| llm_draft          | ~50 (42%)| Fastest; needs quality review                |
| adapted_from_case  | ~35 (29%)| From news, union publications, legal cases   |
| manual             | ~35 (29%)| Hand-crafted for tricky edge cases           |

## Domain Definitions (v2)

1. **organizing** – Forming/joining a union, initial collective steps, management responses to organizing.
2. **collective_bargaining** – Preparing, conducting, or resolving collective bargaining (demands, negotiations, agreements).
3. **wage_scheduling** – Disputes over pay, hours, shift assignments, overtime, schedule changes.
4. **retaliation** – Adverse actions following protected activity (organizing, complaining, whistleblowing).
5. **whistleblowing** – Reporting illegal/unethical conduct internally or externally, protection mechanisms.
6. **strike_conflict** – Work stoppages, strike planning, lockouts, picket lines, back-to-work processes.
7. **works_council** – Works council formation, rights, co-determination, consultation processes (primarily DE/EU).
8. **health_safety** – Workplace safety concerns, hazard reporting, refusal of dangerous work, safety committees.

Note: `mixed_ambiguity` from the pilot is now a **tag** (`ambiguity_flag: true`) rather than a domain.
Scenarios formerly in that domain should be assigned to their substantive domain with the flag set.
