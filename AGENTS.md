# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Setup and core commands
- Python: `3.12` (see `pyproject.toml`).
- Install editable + dev deps:
  - `python -m pip install --upgrade pip`
  - `pip install -e ".[dev]"`

## Test commands
- Full test suite: `pytest`
- Quiet targeted tests (matches CI style):
  - `pytest -q tests/test_plugin_merge.py tests/test_perk_classification.py`
- Run one file: `pytest tests/test_build_engine.py`
- Run one test: `pytest tests/test_build_engine.py::test_<name>`

Integration-style tests and many scripts expect Fallout plugin data (`FalloutNV.esm`). If not available locally, prefer unit tests that use synthetic fixtures.

## Validation/guardrail commands used by CI
- `python -m scripts.check_mechanics_matrix_coverage`
- `python -m scripts.check_mechanics_literals`
- `python -m scripts.audit_mechanics_sources`

## Running the project
- GTK app: `python -m fnv_planner.ui.app`
- Headless UI smoke test: `python -m scripts.smoke_ui --timeout 2.0`
- Planner CLI from JSON specs:
  - `python -m scripts.plan_build --goal-file goal.json --start-file start.json`
  - `python -m scripts.plan_build --goal-json '{"required_perks":[4096],"target_level":20}' --start-json '{"sex":0,"special":{"strength":7,"perception":7,"endurance":6,"charisma":6,"intelligence":5,"agility":5,"luck":4},"tagged_skills":["guns","lockpick","speech"]}'`

## Architecture overview
The codebase is a layered pipeline: **plugin bytes → parsed domain models → dependency/validation engine → planner and UI adapters**.

### 1) Data ingestion and merge (`src/fnv_planner/parser`)
- Low-level Bethesda plugin parsing is handled by record/binary readers, then specialized parsers build typed models (perks, items, effects, GMST, spells, AVIF).
- Multi-plugin load order behavior is centralized in `parser/plugin_merge.py`:
  - Explicit `--esm` paths are strict (must exist).
  - Default mode loads known vanilla/DLC plugin order.
  - Merge policy is “last plugin wins” by key (`form_id` by default).
- `parse_records_merged(...)` is the key utility many entrypoints use to combine records across plugins while tolerating missing GRUPs where appropriate.

### 2) Core domain models (`src/fnv_planner/models`)
- Dataclasses define stable, serializable game/build concepts (`Character`, `Perk`, `Item`, `GameSettings`, derived stats, parser record structures).
- Actor value constants/index mappings are the backbone for requirements and stat math.

### 3) Requirement graph and rules (`src/fnv_planner/graph/dependency_graph.py`)
- Perk requirements are normalized into CNF:
  - AND across clauses
  - OR within each clause
- Supports skill/SPECIAL thresholds, perk dependencies, level, and sex requirements.
- Raw CTDA condition handling is policy-driven (`strict` vs `permissive`), which affects perk availability and diagnostics.

### 4) Build simulation engine (`src/fnv_planner/engine/build_engine.py`)
- `BuildEngine` is the central stateful orchestrator over:
  - `BuildState` (creation + per-level plans),
  - dependency graph checks,
  - derived stat computation.
- It validates mutations eagerly, materializes character snapshots by level, and caches stats with directional invalidation for performance.
- This is the canonical API for selecting perks, allocating skill/SPECIAL points, equipment, and checking unmet requirements.

### 5) UI-facing adapter and GTK app (`src/fnv_planner/engine/ui_model.py`, `src/fnv_planner/ui`)
- `BuildUiModel` is intentionally GUI-agnostic and exposes stable view data (selected entities, progression snapshots, comparisons, diagnostics, gear catalog).
- GTK app bootstrapping (`ui/bootstrap.py`) builds a full session by:
  - resolving/loading plugin stack,
  - parsing/merging perks/items/books/spells/AVIF,
  - constructing `DependencyGraph`, `BuildEngine`, and `BuildUiModel`.
- Controllers/views/widgets in `src/fnv_planner/ui` consume this session/state split.

### 6) Deterministic planner (`src/fnv_planner/optimizer`)
- `optimizer/planner.py` runs a feasibility-first, level-by-level solver around a copied `BuildEngine`.
- Inputs are `GoalSpec` + optional `StartingConditions`; output is `PlanResult` with success flag, unmet requirements, selected perks, and skill-book usage timelines.
- Planner logic includes priority ordering, deadline-aware skill allocation, trait auto-selection, and implant/SPECIAL heuristics.

## Script entrypoints (`scripts/`)
- Scripts are the main developer-facing tools for parsing audits, graph/item/perk dumps, and plan generation.
- Most script entrypoints follow the same plugin resolution path (`resolve_plugins_for_cli` + merged parsing), so behavior should stay consistent between CLI tools and UI bootstrap.
