# Domain Model V1

This document organizes the model defined normatively in [Engine Contract V1](ENGINE_CONTRACT_V1.md). If a field or rule here appears ambiguous, §§1–12 of the canonical contract prevail.

## Bounded contexts

| Context | Owns | Must not own |
|---|---|---|
| Import/adapters | workbook/UI parsing, source mapping, normalization diagnostics | business feasibility or optimization |
| Domain contracts | scenario, demand, lock, block, timetable, fleet, result records | Plotly, Streamlit, openpyxl objects |
| Validation | input, parameter, schedule, turnaround, fleet, reconciliation rules | solver search strategy |
| Planning | demand blocks, block supply plan, headway regimes | rendering |
| Solver adapter | candidate construction and solver-specific diagnostics | final conformance decision or UI objects |
| Evaluation | B/C dispositions, block statuses, explanations | source parsing |
| Presentation/export | views and workbook serialization | authoritative demand/supply calculations |

## Aggregate roots

### `ScenarioAInput` and `ScenarioBInput`

Each is an immutable normalized aggregate composed of route identity, `OperatingPlan`, exact `Timetable`, `FleetDeclaration`, operating-day type, and `SourceMetadata`. A and B are distinct even when their values happen to match.

### `ObservedDemandInput`

Contains observation provenance, normalization classification, demand-response mode, and source observations. It is explicitly associated with A. A normalized average-day value retains the original count and denominator for audit.

### `ScheduleProblemV1`

The complete solver-neutral problem: normalized B, authoritative demand blocks, block requirements, operating locks, solver policy, and source fingerprints. A is included for comparison/provenance but is not a mutable solver input.

### `ScheduleSolutionV1`

The authoritative accepted solution. A raw solver candidate is never a solution until the independent validator passes and reconciliation checks in Contract V1 §14 succeed.

## Core value objects and entities

| Model | Identity | Purpose |
|---|---|---|
| `RouteIdentity` | route ID | route name/type and terminal identities |
| `OperatingWindow` | scenario + terminal | first/last departure and service-day semantics |
| `TurnaroundRule` | scenario + terminal | configured and regulatory minimum |
| `FleetDeclaration` | scenario | approved active, available limit, and lock mode |
| `TimetableTrip` | scenario + trip ID | exact directional departure and optional assignment |
| `ObservedDemandRecord` | observation ID | source-grain passenger observation |
| `DemandResolutionContract` | demand dataset ID | source grain and block-construction policy |
| `DemandAnalysisBlock` | block ID | authoritative analysis interval and provenance |
| `BlockSupplyPlan` | scenario + direction + block ID | Level 1 allocation/evaluation |
| `HeadwayRegime` | regime ID | continuous Level 2 service pattern |
| `TripTrace` | C trip ID | one-to-one B→C trace and explanation |
| `OperatingParameterLock` | field name | inherited B value and lock evidence |
| `FleetAssignment` | C trip ID | vehicle chain and readiness evidence |
| `EvaluationDimension` | scenario + dimension | status, issues, evidence, confidence |

## Relationships

```mermaid
flowchart LR
  A["Scenario A"] --> D["Observed demand under A"]
  D --> DB["Demand analysis blocks"]
  B["Scenario B"] --> L["Operating parameter locks"]
  B --> P["ScheduleProblemV1"]
  DB --> P
  L --> P
  P --> CAND["ScheduleSolutionCandidate"]
  CAND --> VAL["Independent domain validator"]
  VAL --> SOL["ScheduleSolutionV1"]
  SOL --> EVAL["Evaluation outputs"]
  SOL --> VIZ["Diagrams"]
  SOL --> XLSX["XLSX"]
```

## Identity and immutability

- A and B normalized inputs are immutable during an analysis run.
- C holds the B source fingerprint and one trace per B trip in `fixed_by_direction` mode.
- Block IDs and regime IDs are stable within a solution fingerprint.
- Presentation objects may be regenerated, but authoritative values and the solution fingerprint must remain identical.

## Invariants

The complete normative set is in Contract V1 §§3, 4, 8–10, and 14. The aggregate boundary must enforce, at minimum: B parameter locks, total/directional counts, first/last departures, vehicle location/readiness, planned-versus-actual block counts, and one-to-one traceability.

## Domain services

- `InputNormalizer`: legacy shape → normalized contracts plus diagnostics.
- `BusinessValidator`: validates inputs and B parameter consistency.
- `DemandBlockBuilder`: source observations → authoritative blocks.
- `ScheduleEvaluator`: exact timetable + blocks → dimensioned evaluation.
- `ProblemBuilder`: validated inputs → `ScheduleProblemV1`.
- `ScheduleSolver`: problem → raw candidate.
- `DomainSolutionValidator`: raw candidate → accepted/rejected result.
- `SolutionFingerprintService`: canonical serialization → fingerprint.

All services above are framework-neutral. Adapters translate their outputs for UI and export.
