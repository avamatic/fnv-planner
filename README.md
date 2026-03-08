

A mod-aware graph-optimization build planner for FNV, FO3, and TTW.
Treats different forms of data in the game (A weapon, a perk, a quest, a skill value at a specific time, DPS) as nodes in a dependency graph.
The goal is to map out as many important relationships between information in the game,
Organized in such a way that it can be algorithmically searched for arbitrary goals.

Whenever possible the program is data-driven. We take every measure we can to avoid hard-coding or making lists of game mechanics. There are some that unfortunately are beyond our ability to parse, but the dream of a completely stateless FNV optimizer lives on in our mechanical hearts.

There are many existing tools for parsing the game data of FNV, and there is an enormous amount of documentation on how the game works. This is possibly the best project for agentic coding.


We will start by learning to parse as many types of cleanly described information as possible. We will start with the very basics, things like the special values, or traits and perks. Then from there we will work on understanding gear, armor, weapons, and other items. From there, once we have a soli foundation in the unambiguous, we will move on to taking complicated information like "you must have such and such goodwill with caesars legion and have not done these certain things in order to access the safe house where the lucky shades are stored." That is where the compromises on being data driven will likely become impossible to ignore. 

Small notes:
The dps shown in game is not a sufficient measure of real performance. It does not consider missing, or stuns, and it does not include the effect of critical hits in the overall damage profile. It also does not fully consider the impact of gear and perks, which can be additively complex. That is why we are including a damage simulator. Based on the ideas of simulation craft, but as similar as an ant is to an elephant. FNV mechanics are significantly simpler and likely will not require and action lists.

The lucky shades are an important item in my view for criticism based characters. The ability to increase luck by one functionally permanently frees up a special point for the rest of the build. Also, I think the lucky shades are a cool way to capture some of the more interesting aspects of a node based char buildar.
Lets say that grit chance 20 its determined by the sim to be optimal. That becomes a terminal goal. Then everything that increases critical becomes a secondary goal. A feeder goal. From there a particular item, the lucky shades becomes a tertiary goal. The shades don't directly help with increasing luck, because we could just take 10 luck at char creation, but that would hurt the rest of our build, and possibly even our damage. So the shades become helpful in a roundabout way that benefits many parts of the build, and may even string back directly to increasing crit by allowing an additional per to be taken somewhere else. The beauty I'm searching for is finding out the unseen connections between different pieces of information. This will be especially true I believe in mod packs. Vanilla new Vegas is a largely solved game, but modpackt often deliberately try to shake the player out of their expectations and ask us to complete different puzzles and connect pieces of information in different ways.





A mod-aware character build planner and optimizer for Fallout: New Vegas. Treats perks like packages with dependencies (SPECIAL stats, skills, challenges, quests) and helps you plan optimal builds level by level.
The current UI is a cross-platform web frontend centered on a **priority-request** workflow: you describe target outcomes (stats/skills/perks/traits/max-skills), order them by priority, and the planner computes a full build to max level.

## Roadmap

### Phase 1 — Foundation: Parse & Model Game Data ✅

Parse vanilla FNV game data (ESP/ESM plugin files) and build a clean data model
that represents the full character build space.

#### 1a. Binary ESM Reader ✅
- Generic reader for the GRUP → Record → Subrecord binary format
- Handles compressed records, lazy iteration over GRUPs
- Files: `parser/binary_reader.py`, `parser/record_reader.py`, `models/records.py`

#### 1b. Perk Parsing ✅
- Parse PERK records: names, descriptions, requirements, playable flag, trait flag
- Requirements include SPECIAL thresholds, skill levels, level gates, sex, OR groups
- Typed requirements preserve original CTDA float values (`raw_value`) for future precision-sensitive logic
- Files: `parser/perk_parser.py`, `models/perk.py`, `models/constants.py`

#### 1c. Items & Effects ✅
- Parse MGEF (magic effects), ENCH (enchantments), ARMO, WEAP, ALCH, BOOK records
- Stat-bonus resolution chain: item → enchantment → magic effect → actor value
- Weapon enchantments (type 2) produce hostile effects; apparel (type 3) produce buffs
- Skill books use a skill index → actor value mapping (index + 32)
- Effect CTDA conditions are captured on ENCH/ALCH effects; strict/permissive resolution policy controls inclusion
- Files: `parser/effect_parser.py`, `parser/effect_resolver.py`, `models/effect.py`, `parser/item_parser.py`, `models/item.py`

#### 1d. Game Settings & Derived Stats ✅
- Parse GMST records for character formulas (skill points per level, initial skill values, max level, etc.)
- Derived stat computation: carry weight, action points, skill points per level, poison/rad resist, companion nerve, unarmed damage, and more
- All formulas driven by GMST values — no hard-coded vanilla constants
- Optional mod support for Big Guns skill computation via config (`include_big_guns`)
- Files: `parser/gmst_parser.py`, `models/game_settings.py`, `models/derived_stats.py`

#### 1e. Character Data Model ✅
- `Character` dataclass: SPECIAL stats, skills, level, traits, perks, equipment
- Equipment slots and stat aggregation from worn gear
- Files: `models/character.py`

#### 1f. Dependency Graph ✅
- Perk → requirement edges (SPECIAL thresholds, skill levels, other perks, level)
- CNF requirement evaluation: each perk's requirements are AND of OR-clauses
- Trait enumeration, perk eligibility queries, available perk filtering
- Strict/permissive policy for unsupported raw CTDA conditions in perk eligibility
- Files: `graph/dependency_graph.py`

#### Condition Parsing (CTDA) 🟡
- Effect-side CTDAs are captured for ENCH/ALCH effect entries
- Resolver supports:
  - `strict` (default): exclude conditional effects with unknown context
  - `permissive`: include conditional effects and mark them as conditional
- Perk raw CTDA conditions are preserved and can be treated strictly/permissively in dependency evaluation
- Full semantic evaluation of all CTDA functions is still pending

### Phase 2 — Build Engine ✅

Logic layer between raw data models and the future UI/optimizer. Validates and simulates character builds level-by-level.

#### 2a. Build Engine Core ✅
- `BuildEngine` orchestrates `Character`, `compute_stats()`, and `DependencyGraph`
- Per-level tracking via `LevelPlan` dataclass (skill point allocation + perk selection)
- `BuildState` separates creation choices + level plans from engine (serializable, copyable)
- Eager validation on mutation; holistic `validate()` returns all `BuildError`s across the build
- Stats caching with directional invalidation (clear from mutated level upward)
- Configurable perk intervals, skill caps, and SPECIAL budgets via `BuildConfig`
- Includes equipment setters, bulk equipment updates, unmet requirement querying, and optional Big Guns support via config
- Files: `engine/build_engine.py`, `engine/build_config.py`

### Phase 2b — Cross-Platform Web UI 🟡
- Static web UI served by Python is active under `webui/` with launcher code in `fnv_planner.webui`.
- Build page uses ordered priority requests (stat/skill, perk, trait, max-skills bundle)
- Target level is fixed to detected max level from loaded content
- Progression page shows full per-level timeline (perk pick, skill distribution, absolute skill values, per-level/cumulative skill-book usage)
- Challenge/special perks are surfaced as any-time perks (separate from scheduled level timeline)
- Autonomous review flow is provided by Playwright script `scripts/review_webui.py` (interactions + screenshots).

### Phase 3 — Optimizer 🟡
- Algorithm that finds optimal builds for user-defined goals (max crit, max DPS, best melee, max skills, etc.)
- Generate a level-by-level plan for growing the character from 1 to max
- Export the plan to a document with room for manual notes (e.g., "grab power armor from dead troopers near Hidden Valley at level 1")
- Deterministic planner is available under `fnv_planner.optimizer`:
  - `GoalSpec` + `StartingConditions` input models
  - `plan_build(...)` feasibility planner that produces a level-by-level `BuildState`
  - Priority-aware scheduling for actor values, perks, traits, and `max_skills`
  - Perk/trait text + structured-effect inference for planner-relevant bonuses (for example skill points/level, skill-book multiplier, all-skills bonuses)
  - Skill-book usage accounting by skill and by level

#### Optimizer Planning Considerations
- Max-skills scenarios with configurable skill-book collection commitments (planning around collecting 100% / 50% / 25% of books)
- `Skilled` trait and `Intense Training` are considered by max-skills planning when they improve feasibility
- Implant planning (maximum implants determined by Endurance)
- Optional support for modded `Big Guns` skill in optimization and requirement evaluation

### Phase 4 — Beyond Fallout.esm ⬜

#### DLC Incorporation
- Read the additional ESMs that ship with the game (HonestHearts.esm, GunRunnersArsenal.esm, OldWorldBlues.esm, etc.)
- Handle mod-list priority: when values from different ESMs conflict, the last-loaded ESM wins

#### MO2 Integration
- Read MO2 mod folders to discover modded perks, traits, weapons, and stat changes
- Merge modded data into the dependency graph alongside vanilla content
- MO2's `modlist.txt` defines the load-order priority

### Stretch Goals
- In-game companion mod that reads the planner output and guides you during gameplay
- Item tracker mod for skill books, unique weapons/armor with optional waypoint guidance

## Key Data Concepts

### Actor Values
FNV uses integer indices for all character stats. Key ranges:
- **SPECIAL**: 5–11 (Strength, Perception, Endurance, Charisma, Intelligence, Agility, Luck)
- **Skills**: 32–45 (Barter, Big Guns, Energy Weapons, ... Speech, Unarmed)
- **Derived**: 12 (AP), 14 (Crit Chance), 16 (Health), 20 (Rad Resist), 54 (Rads), etc.
- **Survival needs** (Hardcore): 73 (Dehydration), 74 (Hunger), 75 (Sleep Deprivation)

### Stat-Bonus Chain
```
Item (ARMO/WEAP/ALCH)
  └─ enchantment_form_id ──→ Enchantment (ENCH)
                                └─ EFID (mgef_form_id) ──→ Magic Effect (MGEF)
                                   EFIT (magnitude, duration)     └─ actor_value
                                                                      archetype
```
Consumables (ALCH) embed EFID/EFIT pairs inline rather than referencing an ENCH.
Books use a skill_index field (skill = index + 32) instead of enchantments.

### Effect Display Format
```
[+1 Luck]{Player}                  — permanent player buff (apparel)
[-2 Health/s*10s]{Enemy}           — damage over time to enemy (weapon)
[-50 Health]{Enemy}                — instant damage to enemy (weapon)
[+5 Health*6s]{Player}             — temporary heal (consumable)
```

## Tech Stack
- **Language**: Python 3.12+
- **Game data parsing**: Custom ESP/ESM parser (Bethesda plugin format)
- **Dependency graph**: Custom CNF requirement evaluation
- **Optimization**: Deterministic planner (`fnv_planner.optimizer`)
- **UI runtime**: static web frontend + Python HTTP server + Playwright review automation
- **UX model/CLI**: `BuildUiModel` + `scripts/prototype_ui.py`

## Project Structure
```
fnv-planner/
├── README.md
├── pyproject.toml
├── src/fnv_planner/
│   ├── engine/
│   │   ├── build_config.py       # BuildConfig: tuneable parameters
│   │   ├── build_engine.py       # LevelPlan, BuildState, BuildError, BuildEngine
│   │   └── ui_model.py           # UI-facing adapter: selected entities, progression, diagnostics
│   ├── graph/
│   │   └── dependency_graph.py   # DependencyGraph: perk eligibility & trait queries
│   ├── optimizer/
│   │   ├── planner.py            # Priority-request planner and level-by-level schedule generation
│   │   └── specs.py              # GoalSpec, RequirementSpec, StartingConditions
│   ├── models/
│   │   ├── avif.py              # AVIF actor-value metadata model
│   │   ├── character.py          # Character dataclass
│   │   ├── constants.py          # ActorValue enum, index sets, name mappings
│   │   ├── derived_stats.py      # DerivedStats formulas, compute_stats()
│   │   ├── effect.py             # StatEffect, MagicEffect, Enchantment
│   │   ├── game_settings.py      # GameSettings: GMST-driven formula parameters
│   │   ├── item.py               # Armor, Weapon, Consumable, Book
│   │   ├── perk.py               # Perk, requirement types
│   │   ├── records.py            # Subrecord, RecordHeader, Record, GroupHeader
│   │   └── spell.py              # Spell model used by weapon/apparel effect resolution
│   ├── parser/
│   │   ├── avif_parser.py        # AVIF parsing and actor-value metadata extraction
│   │   ├── binary_reader.py      # Low-level typed binary reads
│   │   ├── record_reader.py      # GRUP iteration and record extraction
│   │   ├── plugin_merge.py       # Plugin stack loading and merge helpers
│   │   ├── perk_parser.py        # PERK record parsing
│   │   ├── perk_classification.py # Playable/trait/challenge/special classification rules
│   │   ├── gmst_parser.py        # GMST record parsing
│   │   ├── effect_parser.py      # MGEF + ENCH record parsing
│   │   ├── effect_resolver.py    # Item → enchantment → stat effect resolution
│   │   ├── item_parser.py        # ARMO, WEAP, ALCH, BOOK record parsing
│   │   ├── spell_parser.py       # SPEL parsing and item-linked spell extraction
│   │   └── book_stats.py         # Skill-book copy counts and source categorization
│   ├── ui/
│   │   ├── app.py                # Compatibility launcher (starts web UI server)
│   │   ├── bootstrap.py          # Session bootstrap from plugin stack
│   │   ├── state.py              # Shared UI session/application state
│   │   └── controllers/          # Toolkit-neutral controller logic used by web state export
│   └── webui/
│       ├── export_state.py       # Deterministic UI snapshot export
│       └── server.py             # Local HTTP server + state generation
├── scripts/
│   ├── check_mechanics_matrix_coverage.py # CI guardrail: mechanics matrix coverage
│   ├── check_mechanics_literals.py # CI guardrail: literal string consistency
│   ├── audit_mechanics_sources.py  # CI guardrail: mechanics source auditing
│   ├── dump_character.py         # CLI: build and inspect a character snapshot
│   ├── dump_graph.py             # CLI: list perks with their requirements
│   ├── dump_items.py             # CLI: list parsed items with stat effects
│   ├── dump_perks.py             # CLI: list parsed perks
│   ├── audit_perks.py            # CLI: category audit (normal/trait/challenge/special/internal)
│   ├── audit_skill_books.py      # CLI: skill-book copy counts + source buckets
│   ├── plan_build.py             # CLI: build planning from goal/start JSON specs
│   ├── prototype_ui.py           # Interactive CLI prototype (Build/Progression/Library)
│   ├── run_webui.py              # Launch local web UI server
│   └── review_webui.py           # Playwright interaction + screenshot review runner
├── webui/                        # Static web frontend (HTML/CSS/JS)
└── tests/                        # pytest suite (unit + integration)
```

## Running

```bash
# Python 3.12+ is required

# Install/update tooling
python -m pip install --upgrade pip

# Install in editable mode
pip install -e ".[dev]"

# Optional UI review prerequisites:
# - playwright Python package
# - chromium browser installed by Playwright

# Run full tests (integration-style tests may require FalloutNV.esm)
pytest

# Run a fast targeted subset (matches CI style)
pytest -q tests/test_plugin_merge.py tests/test_perk_classification.py

# CI guardrail checks
python -m scripts.check_mechanics_matrix_coverage
python -m scripts.check_mechanics_literals
python -m scripts.audit_mechanics_sources

# Dump parsed data
python -m scripts.dump_perks --playable-only
python -m scripts.dump_perks --playable-only --include-challenge-perks
python -m scripts.dump_items --armor --playable-only
python -m scripts.dump_items --weapons --consumables --books
python -m scripts.dump_items --weapons --playable-only --format json
python -m scripts.dump_graph
python -m scripts.dump_character
python -m scripts.audit_perks --check-wiki
python -m scripts.audit_skill_books
python -m scripts.plan_build --goal-file goal.json --start-file start.json

# Interactive CLI prototype for Build / Progression / Library flows
python -m scripts.prototype_ui [--esm /path/to/FalloutNV.esm]

# Cross-platform web UI app
python -m fnv_planner.ui.app

# Explicit web UI runner
python -m scripts.run_webui --port 4173

# Headless autonomous UI review (Playwright)
python -m scripts.review_webui --out artifacts/ui_review

# Build-tab quick perk preset button source file
# (used by "Apply Quick Perk List")
cat config/quick_perks.txt

# Plugin stack mode (repeat --esm in load order; last wins)
python -m scripts.dump_items \
  --esm "/path/to/FalloutNV.esm" \
  --esm "/path/to/HonestHearts.esm" \
  --esm "/path/to/GunRunnersArsenal.esm" \
  --weapons --playable-only

# Build planning from JSON specs (inline form)
python -m scripts.plan_build \
  --goal-json '{"required_perks":[4096],"target_level":20}' \
  --start-json '{"sex":0,"special":{"strength":7,"perception":7,"endurance":6,"charisma":6,"intelligence":5,"agility":5,"luck":4},"tagged_skills":["guns","lockpick","speech"]}'
```

### `dump_items` weapon output notes
- `--playable-only` (weapons): player-facing list for planning. Companion/NPC/helper variants are filtered out.
- `--include-companion-variants`: only applies with `--playable-only`; re-includes companion/NPC weapon variants for reference.
- Duplicate weapon names are auto-disambiguated in output:
  - Prefer readable labels when possible (example: `[Lily]`, `[Weak]`, `[Always-Crit]`)
  - Fall back to `editor_id` labels when names still collide (example: `[WeapPlasmaRifle]`)
- `--dedupe` collapses only rows that are identical in displayed combat context (name, damage, value, weight, resolved effects).

### `dump_items` identity semantics
- `record-distinct`: each ESM record is unique by `form_id`/`editor_id`.
- `gameplay-distinct`: same display name can still be different gameplay entities (example: base, companion, weak/always-crit variants).
- `display-distinct`: duplicate names in text output are always labeled so rows are unambiguous.
- `--dedupe` removes only rows that are display-equivalent (same printed combat profile and effects), not just same name.

### Plugin Load Order
- Scripts support repeated `--esm` flags to load multiple plugins.
- Input order is load order; later plugins override earlier ones.
- Missing record groups in some plugins are tolerated (for example, DLC-only files with no `GMST` or `BOOK` group).
- Explicit `--esm` paths are strict: all provided paths must exist.
- With no `--esm`, scripts use this default vanilla order and skip missing files gracefully:
  - `FalloutNV.esm`
  - `DeadMoney.esm`
  - `HonestHearts.esm`
  - `OldWorldBlues.esm`
  - `LonesomeRoad.esm`
  - `GunRunnersArsenal.esm`
  - `CaravanPack.esm`
  - `ClassicPack.esm`
  - `MercenaryPack.esm`
  - `TribalPack.esm`

### Perk Filtering Notes
- `dump_perks --playable-only` excludes challenge reward perks by default.
- Use `--include-challenge-perks` to include challenge rewards (for auditing/reference).
- Perk categories are data-driven from game files:
  - CHAL↔PERK name linkage
  - challenge-family PERK editor IDs
  - PERK trait/playable/hidden flags
- `audit_perks` reports category counts: `normal`, `trait`, `challenge`, `special`, `internal`.
- `special` is intentionally broad: visible non-selectable perks from data files (larger than the wiki’s curated 18-item special list).

### `dump_items` JSON mode
- `--format json` emits structured output with selected categories under `categories`.
- Weapon entries include both `name` and `display_name` (with disambiguation labels), plus `editor_id`, `form_id`, stats, and resolved effects.
- Weapon classification fields:
  - `record_flag_playable`: raw WEAP record-flag interpretation (`Weapon.is_playable`).
  - `non_playable_flagged`: WEAP `Flags1` bit 7 (game-data non-playable marker).
  - `embedded_weapon_flagged`: WEAP `Flags1` bit 5 (embedded weapon marker).
  - `is_player_facing`: planner heuristic for player-usable gear (filters companion/NPC/helper-only entries).
  - `is_non_player` and `is_variant`: extra diagnostics used by the filter/disambiguation logic.
- Use JSON mode for scripts and regression checks; use text mode for quick manual inspection.
