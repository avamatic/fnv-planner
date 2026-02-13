# UI Spec (Screen-by-Screen)

This spec defines a concrete UI target for the next GUI iteration.
It is implementation-ready: exact widgets, data bindings, and event flows.

## 1) App Shell

### 1.1 Window
- `Adw.ApplicationWindow`
- Default size: `1440x900`
- Min size: `1100x700`
- Layout: `Adw.ToolbarView` + `Adw.TabView`

### 1.2 Header Bar
- Left:
  - `Gtk.MenuButton` (`Project`)
    - `New Build`
    - `Open Build`
    - `Save Build`
    - `Export JSON`
  - `Gtk.Button` (`Reload Plugins`)
- Center:
  - `Gtk.Label` (`Build name + target level`)
- Right:
  - `Gtk.MenuButton` (`Data Source`)
    - `Use default vanilla load order`
    - `Choose plugin stack...`
    - `Show active plugin order`

### 1.3 Primary Tabs
- `Build`
- `Progression`
- `Library`
- `Cool Stuff`

## 2) Build Screen

### 2.1 Layout
- `Gtk.Paned` (horizontal)
  - Left panel (inputs, ~420px)
  - Right panel (summary + diagnostics, fill)

### 2.2 Left Panel Widgets
- Section: `SPECIAL`
  - 7x `Gtk.SpinButton` (range 1..10), one per SPECIAL
- Section: `Tagged Skills`
  - `Gtk.SearchEntry`
  - `Gtk.ListBox` of skill rows
    - each row: label + `Gtk.ToggleButton` (`Tagged`)
- Section: `Traits`
  - `Gtk.SearchEntry`
  - `Gtk.ListBox`
    - row: trait name, short description, `Gtk.ToggleButton` (`Selected`)
- Section: `Perk Selection`
  - `Gtk.SpinButton` (`Level`)
  - `Gtk.SearchEntry`
  - `Gtk.ListBox` of perks
    - row: name, req summary, status chip (`Available`/`Blocked`)
    - actions: `Select`, `Inspect`
- Section: `Gear by Slot`
  - `Gtk.ListBox` of equipment slots
    - row: slot name, selected item label
    - actions: `Choose`, `Clear`

### 2.3 Right Panel Widgets
- Card: `Current Snapshot`
  - key derived stats grid (HP, AP, Carry, Crit, etc.)
- Card: `Selected Entities`
  - `Gtk.SearchEntry`
  - `Gtk.ColumnView`
    - cols: `Type`, `Name`, `At Level`, `Action`
    - action cell: `Remove`
- Card: `Diagnostics`
  - `Gtk.ListBox`
    - severity icon, message, optional level/form id jump link

### 2.4 Event Flows
1. Change SPECIAL
- Widget event: `value-changed`
- Action:
  - call engine special update
  - recompute current + target snapshots
  - refresh diagnostics

2. Select perk at level L
- Widget event: `Select` clicked
- Action:
  - `engine.select_perk(L, perk_id)`
  - if rejected: show inline error in row + diagnostics
  - if accepted: refresh selected entities, progression deltas, graph highlights

3. Remove selected entity
- Widget event: `Remove` clicked
- Action:
  - `ui_model.remove_selected_entity(entity)`
  - refresh all dependent panels

## 3) Progression Screen

### 3.1 Layout
- Vertical box with top controls + main split
- Main split: left `Timeline`, right `Delta Inspector`

### 3.2 Widgets
- Top controls:
  - `Gtk.SpinButton` (`From Level`)
  - `Gtk.SpinButton` (`To Level`)
  - `Gtk.Button` (`Compare`)
- Left:
  - `Gtk.ColumnView` (one row per level)
    - cols: `Level`, `Perk`, `Spent`, `Unspent`, `HP`, `AP`, `Carry`, `Crit`
- Right:
  - `Gtk.ColumnView` for deltas
    - `Stat`, `Delta`
  - `Gtk.ColumnView` for skill deltas
    - `Skill`, `Delta`

### 3.3 Event Flows
1. Select row (level N)
- Action:
  - set active preview level N
  - update right delta inspector (N vs target or compare range)
  - sync to `Cool Stuff` tab highlight (available-at-N)

2. Compare range
- Widget event: `Compare` clicked
- Action:
  - call `compare_levels(from, to)`
  - render stat and skill delta tables

## 4) Library Screen

### 4.1 Layout
- Top search/filter bar + content split
- Left: category filters
- Center: item list
- Right: inspector panel

### 4.2 Widgets
- Top:
  - `Gtk.SearchEntry` (`Search perks/gear`)
  - `Gtk.ToggleButton` (`Player-facing only`)
  - `Gtk.ToggleButton` (`Include challenge/special/internal`)
- Left filters:
  - `Gtk.CheckButton`: `Perks`, `Weapons`, `Armor`
  - `Gtk.CheckButton`: `Challenge`, `Special`, `Trait`
- Center:
  - `Gtk.ColumnView`
    - cols: `Name`, `Kind`, `Category`, `Weight`, `Value`
    - row actions: `Add`, `Inspect`
- Right inspector:
  - title + source plugin + form id/editor id
  - requirements
  - resolved effects
  - impact preview (`Now`, `At max level`)
  - `Add` / `Remove`

### 4.3 Event Flows
1. Add from library
- Action:
  - perk: assign to currently focused level
  - gear: open slot chooser if ambiguous, else equip directly
  - show toast with delta summary

2. Remove from inspector
- Action:
  - route through selected-entity removal logic
  - refresh Build + Progression + Cool Stuff

## 5) Cool Stuff Screen (Perk Graph)

### 5.1 Layout
- `Gtk.Overlay`
  - Base: graph canvas
  - Overlay top-left: filter controls
  - Overlay right: node inspector drawer

### 5.2 Widgets
- Graph canvas:
  - custom `Gtk.DrawingArea` or graph widget
  - nodes = perks
  - edges = requirement dependencies
- Filters:
  - `Gtk.DropDown` (`View Mode`)
    - `All`
    - `Current Build`
    - `Reachable by Level N`
    - `Blocked`
  - `Gtk.SpinButton` (`Level N`) for reachable mode
  - `Gtk.CheckButton` per category color layer
- Inspector drawer:
  - node title + category chip
  - requirement list
  - unmet reasons at active level
  - actions: `Select at Level`, `Find Path`, `Open in Library`

### 5.3 Graph Visual Rules
- Node color:
  - normal = blue
  - trait = orange
  - challenge = green
  - special = gray
  - internal = dark gray
- Edge style:
  - solid = direct prerequisite
  - dashed = OR-clause relation
- Node ring state:
  - selected in build = thick ring
  - available at active level = glow
  - blocked = red border

### 5.4 Event Flows
1. Click node
- Action:
  - open inspector drawer with full perk detail
  - highlight incoming requirement path

2. Ctrl+click second node
- Action:
  - compute shortest dependency path
  - animate path emphasis for 2s

3. Sync from Progression
- Trigger: active level changes
- Action:
  - recompute available/blocked node states for that level
  - update graph highlight

## 6) Shared Interaction Contracts

### 6.1 Global Refresh Contract
Any successful mutation (special/tag/trait/perk/gear):
1. Recompute current + target snapshots
2. Recompute diagnostics
3. Refresh selected entities
4. Refresh progression deltas
5. Refresh graph highlight state

### 6.2 Error Contract
- Rejected action must surface:
  - inline message at source widget
  - diagnostic entry with machine-readable code
  - no partial state mutation

## 7) Data Binding Map (Current Backend)

- Build snapshot/progression/deltas:
  - `BuildUiModel.level_snapshot()`
  - `BuildUiModel.progression()`
  - `BuildUiModel.compare_levels()`
- Selection list/remove:
  - `BuildUiModel.selected_entities()`
  - `BuildUiModel.remove_selected_entity()`
- Gear catalog:
  - `BuildUiModel.gear_catalog()`
- Diagnostics:
  - `BuildUiModel.diagnostics()`

Perk graph data source (new adapter needed):
- Nodes: all parsed perks + categories
- Edges: `DependencyGraph` requirement relations
- Availability/blocked state: `BuildEngine` at active level

## 8) Delivery Phases

1. `Phase UI-1`: Build + Progression parity with CLI prototype
2. `Phase UI-2`: Library + inspector + remove flows
3. `Phase UI-3`: Cool Stuff graph tab (all interactions above)
4. `Phase UI-4`: keyboard navigation, performance tuning, accessibility
