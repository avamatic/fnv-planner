# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FNV Planner is a mod-aware character build planner/optimizer for Fallout: New Vegas (also FO3 and TTW). It parses binary ESM/ESP plugin files, builds a dependency graph of perks and requirements, and computes optimal level-by-level build plans. Zero runtime dependencies — all parsing uses stdlib `struct` and `zlib`.

## Setup and Commands

```bash
# Install (Python 3.12+ required)
python -m pip install --upgrade pip
pip install -e ".[dev]"

# Full test suite (some tests need FalloutNV.esm in NV_GAME_FILES/)
pytest

# CI-matching fast subset (always works without game data)
pytest -q tests/test_plugin_merge.py tests/test_perk_classification.py

# Single file / single test
pytest tests/test_build_engine.py
pytest tests/test_build_engine.py::test_<name>

# CI mechanics guardrails (must pass before merge)
python -m scripts.check_mechanics_matrix_coverage
python -m scripts.check_mechanics_literals
python -m scripts.audit_mechanics_sources

# Run web UI (opens browser at http://127.0.0.1:4173)
python -m fnv_planner.ui.app

# CLI planner
python -m scripts.plan_build --goal-json '...' --start-json '...'
```

## Architecture

Layered pipeline: **plugin bytes -> parsed domain models -> dependency graph -> build engine -> planner/UI**.

### Layer 1: Parser (`src/fnv_planner/parser/`)
- `binary_reader.py` / `record_reader.py`: low-level GRUP -> Record -> Subrecord iteration with zlib decompression
- Specialized parsers (`perk_parser`, `gmst_parser`, `item_parser`, `effect_parser`, `spell_parser`, `avif_parser`) produce typed domain objects
- `plugin_merge.py`: multi-plugin loading with "last plugin wins" by `form_id`. Default vanilla DLC load order. `resolve_plugins_for_cli()` and `parse_records_merged()` are the key entry points used by scripts and UI bootstrap

### Layer 2: Models (`src/fnv_planner/models/`)
- `constants.py`: `ActorValue` enum (SPECIAL indices 5-11, Skills 32-45), governing attribute map
- `character.py`: `Character` dataclass with SPECIAL, skills, equipment, traits, perks
- `derived_stats.py`: all formulas driven by GMST values from game data, not hardcoded
- `game_settings.py`: parsed GMST records powering derived stat formulas

### Layer 3: Graph (`src/fnv_planner/graph/dependency_graph.py`)
- Perk requirements normalized to CNF: AND of OR-clauses (`RequirementSet` -> `RequirementClause`)
- `is_or` flag on requirements controls AND/OR grouping at parse time
- Strict (default) vs permissive policy for unrecognized CTDA conditions

### Layer 4: Engine (`src/fnv_planner/engine/`)
- `BuildEngine`: central orchestrator — holds `BuildState`, `DependencyGraph`, `GameSettings`, `BuildConfig`
- `BuildState`: serializable snapshot (creation choices + `level_plans` dict)
- `materialize(level)` -> `Character` snapshot; `compute_stats(level)` -> `CharacterStats` (cached)
- Stats cache uses directional invalidation: mutation at level N clears cache for levels >= N
- `validate()` returns all `BuildError`s across the build
- `ui_model.py`: GUI-agnostic `BuildUiModel` adapter

### Layer 5: Optimizer (`src/fnv_planner/optimizer/`)
- `planner.py`: feasibility-first, level-by-level deterministic solver
- Input: `GoalSpec` + `StartingConditions`; output: `PlanResult`
- Priority-ordered requirement specs, deadline-aware skill allocation, trait auto-selection, implant/SPECIAL heuristics

### Layer 6: UI (`src/fnv_planner/ui/`, `src/fnv_planner/webui/`, `webui/`)
- `ui/bootstrap.py`: `bootstrap_default_session()` loads plugins, builds full engine + UI model
- `webui/server.py`: HTTP server — `GET /state.json` returns snapshot, `POST /action/<path>` mutates state
- `webui/`: static vanilla JS frontend (no build step), 4 tabs: Build | Progression | Library | Diagnostics
- **Priority-request workflow**: users describe goals (target stats, perks, traits, max-skills), order by priority; the planner resolves a full schedule

## Key Design Principles

- **Data-driven formulas**: game constants come from GMST records in ESM files. Hardcoded values are tracked in `docs/MECHANICS_SOURCE_MATRIX.md` and enforced by CI guardrail scripts. Do not add hardcoded game constants without updating the matrix.
- **Plugin merge semantics**: "last plugin wins" by `form_id`. Load order matters.
- **Game variant detection**: `detect_game_variant()` distinguishes `fallout-nv`, `fallout-3`, and `ttw` from ESM content.
- **Tests without game data**: many tests use synthetic fixtures. Integration tests requiring `FalloutNV.esm` are skipped gracefully in CI. Prefer synthetic fixtures for new tests.
- **No linter/formatter configured**: no ruff, black, mypy, or flake8 in the project.

## Common Patterns

- Scripts and UI bootstrap both use `resolve_plugins_for_cli()` + `parse_records_merged()` for plugin loading
- `BuildEngine.from_state()` / `replace_state()` for serialization round-trips
- Controllers in `ui/controllers/` are toolkit-neutral; `webui/export_state.py` converts to JSON
- `config/quick_perks.txt` contains the preset perk list for the Build tab's "Apply Quick Perk List" button
