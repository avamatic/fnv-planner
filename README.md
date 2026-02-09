# fnv-planner — Fallout: New Vegas Character Build Optimizer

## Overview
A mod-aware character build planner and optimizer for Fallout: New Vegas. Treats perks like packages with dependencies (SPECIAL stats, skills, challenges, quests) and helps you plan optimal builds level by level.

## Roadmap

### Phase 1 — Foundation: Parse & Model Game Data

Parse vanilla FNV game data (ESP/ESM plugin files) and build a clean data model
that represents the full character build space.

#### 1a. Binary ESM Reader ✅
- Generic reader for the GRUP → Record → Subrecord binary format
- Handles compressed records, lazy iteration over GRUPs
- Files: `binary_reader.py`, `record_reader.py`, `records.py`

#### 1b. Perk Parsing ✅
- Parse PERK records: names, descriptions, requirements, playable flag, trait flag
- Requirements include SPECIAL thresholds, skill levels, level gates, sex, OR groups
- Files: `perk_parser.py`, `perk.py`, `constants.py`

#### 1c. Items & Effects ✅
- Parse MGEF (magic effects), ENCH (enchantments), ARMO, WEAP, ALCH, BOOK records
- Stat-bonus resolution chain: item → enchantment → magic effect → actor value
- Weapon enchantments (type 2) produce hostile effects; apparel (type 3) produce buffs
- Skill books use a skill index → actor value mapping (index + 32)
- Files: `effect_parser.py`, `effect_resolver.py`, `effect.py`, `item_parser.py`, `item.py`

#### 1d. Condition Parsing (CTDA) ⬚
- CTDA subrecords gate when effects apply (e.g., "only vs Robots", "only vs Power Armor")
- Also used in perk requirements for complex conditions
- Currently skipped in `effect_parser.py` — effects with conditions are parsed
  but the conditions themselves are discarded
- Key condition functions discovered so far:
  - `func 438` — GetIsCreatureType (e.g., param 6 = Robot)
  - `func 182` — HasEquippedItemType (checks target's equipped armor)

#### 1e. Character Data Model ⬚
- `Character` / `Build` class: SPECIAL stats, skills, level, traits, perks, equipment
- Derived stat formulas (carry weight, action points, skill points per level, etc.)
- Equipment slots and stat aggregation from worn gear
- (human note) Because we want this tool to be mod aware, it's important that we are extracting the formulas for SPECIAL available at character creation from the game     
  files, and do not hard-code the formulas. We can explore together if that's reasonable and if so how to achieve it.

#### 1f. Dependency Graph ⬚
- Perk → requirement edges (SPECIAL thresholds, skill levels, other perks, level)
- Equipment → stat effect edges
- Used by the optimizer to determine valid perk orderings per level

### Phase 2 — Character Builder
- Interactive character builder UI styled after the in-game interface
- Calculate derived/secondary stats: DPS, DT, crit chance, crit bonus damage, carry weight, etc.
- Real-time feedback as you assign SPECIAL points, pick traits, and select perks

### Phase 3 — Optimizer
- Algorithm that finds optimal builds for user-defined goals (max crit, max DPS, best melee, max skills, etc.)
- Generate a level-by-level plan for growing the character from 1 to max
- Export the plan to a document with room for manual notes (e.g., "grab power armor from dead troopers near Hidden Valley at level 1")

### Phase 4 — Beyond Fallout.esm
#### 1d. Incorporation of DLC
- (human note) Read the rest of the ESMs that ship with the game (e.g. HonestHearts.esm, GunRunnersArsenal.esm, OldWorldBlues.esm)
- (human note) Understand mod-list: mod-list is a general term to describe how when values from different ESMs conflict, the value from the ESM with the lowest mod-list priority is chosen.
 
#### 1d. MO2 Integration
- Read MO2 mod folders to discover modded perks, traits, weapons, and stat changes
- Merge modded data into the dependency graph alongside vanilla content
- (human note) MO2 has a file called modlist.txt which explicitly defines the priority of different mod packages.

### Stretch Goals
- In-game companion mod that reads the planner output and guides you during gameplay
- Item tracker mod for skill books, unique weapons/armor with optional waypoint guidance
- (human note) Section for interesting tricks and tips in the GUI (e.g. locations/strategies for easy power scaling (e.g. looting dead brotherhood palidins north of Hidden Valley))

## Key Data Concepts

### Actor Values
FNV uses integer indices for all character stats. Key ranges:
- **SPECIAL**: 0–6 (Strength, Perception, Endurance, Charisma, Intelligence, Agility, Luck)
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
[+5 Health/s*6s]{Player}           — temporary heal (consumable)
```

## Tech Stack
- **Language**: Python 3.12+
- **Game data parsing**: Custom ESP/ESM parser (Bethesda plugin format)
- **Dependency graph**: networkx (or similar)
- **Optimization**: scipy/numpy
- **UI** (later): Web frontend (HTML/CSS/JS) with Python backend (FastAPI), styled like a Pip-Boy

## Project Structure
```
fnv-planner/
├── README.md
├── pyproject.toml
├── src/fnv_planner/
│   ├── models/
│   │   ├── constants.py       # ActorValue, enums, name mappings
│   │   ├── effect.py          # StatEffect, MagicEffect, Enchantment
│   │   ├── item.py            # Armor, Weapon, Consumable, Book
│   │   ├── perk.py            # Perk, requirements
│   │   └── records.py         # Subrecord, RecordHeader, Record, GroupHeader
│   └── parser/
│       ├── binary_reader.py   # Low-level typed binary reads
│       ├── record_reader.py   # GRUP iteration and record extraction
│       ├── perk_parser.py     # PERK record parsing
│       ├── effect_parser.py   # MGEF + ENCH record parsing
│       ├── effect_resolver.py # Item → enchantment → stat effect resolution
│       └── item_parser.py     # ARMO, WEAP, ALCH, BOOK record parsing
├── scripts/
│   ├── dump_perks.py          # CLI: list parsed perks
│   └── dump_items.py          # CLI: list parsed items with stat effects
└── tests/                     # 71 tests (pytest)
```

## Running

```bash
# Install in editable mode
pip install -e ".[dev]"

# Run tests (requires FalloutNV.esm for integration tests)
pytest

# Dump parsed data
python -m scripts.dump_perks --playable-only
python -m scripts.dump_items --armor --playable-only
python -m scripts.dump_items --weapons --consumables --books
```
