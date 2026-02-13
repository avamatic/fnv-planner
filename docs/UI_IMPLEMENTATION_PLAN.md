# UI Implementation Plan

This plan defines how we will implement the app UI with a GNOME-native first approach while keeping the core code portable for a future cross-platform frontend.

## 1) Decision Summary

- Primary UI stack: `GTK4 + Libadwaita + PyGObject`
- Primary packaging/distribution: `Flatpak`
- Product scope: Linux-first (GNOME-native UX), cross-platform later if needed
- Architecture rule: planner logic remains UI-agnostic and reusable

## 2) Why This Direction

- Matches current user environment and preference (GNOME desktop).
- Best fit for a polished Linux desktop app and Flatpak distribution.
- Fastest path to a coherent UI because Libadwaita provides strong patterns.
- Keeps options open by separating UI from parser/engine logic.

## 3) Constraints and Tradeoffs

- GTK/Libadwaita is excellent on Linux, but not ideal for polished Windows/macOS distribution.
- We should not promise first-class multiplatform support in v1.
- We can still preserve multiplatform potential by isolating all domain logic from UI code.

## 4) Architecture Plan

### 4.1 Layers

1. `Core domain` (already exists): parser, models, dependency graph, build engine.
2. `UI adapter layer`: maps engine state into UI-friendly view models/events.
3. `GTK frontend`: widgets, navigation, event wiring, persistence actions.

### 4.2 Hard Separation Rules

- No GTK imports in `src/fnv_planner/models`, `src/fnv_planner/engine`, or parser modules.
- UI state mutations go through explicit adapter/controller methods.
- UI widgets render adapter outputs; widgets do not hold gameplay business logic.

### 4.3 Suggested Package Layout

```text
src/fnv_planner/
  ui/
    app.py
    state.py
    controllers/
      build_controller.py
      progression_controller.py
      library_controller.py
      graph_controller.py
    views/
      window.py
      build_page.py
      progression_page.py
      library_page.py
      graph_page.py
    widgets/
      diagnostics_list.py
      selected_entities.py
      gear_slot_row.py
```

## 5) MVP Scope (First Shippable GUI)

The MVP should cover:

1. Build page:
   - SPECIAL editing
   - tagged skills
   - trait toggles
   - perk selection by level
   - per-slot gear selection
   - selected entity removal
   - diagnostics
2. Progression page:
   - level timeline
   - compare range and delta table
3. Library page:
   - search/filter across perks and gear
   - inspect and add/remove
4. Plugin loading:
   - default vanilla plugin order (with graceful missing-DLC handling)
   - drag-and-drop plugin files into app window

Perk graph (`Cool Stuff`) is phase 2 after MVP stability.

## 6) Flatpak Plan

### 6.1 Runtime and SDK

- Runtime: `org.gnome.Platform`
- SDK: `org.gnome.Sdk`
- Target branch: choose latest stable GNOME branch used by distribution baseline.

### 6.2 Flatpak Manifest Milestone

1. Add `flatpak/` with manifest and app metadata.
2. Build/install in dev mode.
3. Add CI job to verify manifest builds.

### 6.3 Filesystem Access Policy

- Default: no broad host filesystem access.
- Use file chooser + drag-and-drop portal for plugin selection.
- Keep permissions minimal (`--filesystem=home` only if truly needed).

## 7) Cross-Platform Strategy (Deferred)

If cross-platform becomes a hard requirement:

1. Keep current core unchanged.
2. Add a second frontend that reuses the same adapter contract.
3. Candidate stacks to evaluate later: `Qt/PySide` or `Web/Tauri`.

Decision gate for second frontend:

- We only proceed if there is clear user demand and maintenance budget.

## 8) Milestones and Exit Criteria

### M1: UI Foundation

- App shell and tabs render.
- Core state loads from default plugin stack.
- Mutations trigger global refresh contract.

Exit: prototype parity for Build/Progression workflows.

### M2: Library + Gear Workflow

- Per-slot gear selection + removal is complete.
- Full library browsing and search is usable.
- Add/remove from inspector works reliably.

Exit: user can create and edit a full build without CLI.

### M3: Stability + Packaging

- Error handling and diagnostics are consistent.
- Keyboard navigation works for core flows.
- Flatpak dev build/install docs are complete.

Exit: local flatpak package runs end-to-end.

### M4: Cool Stuff Graph

- Perk graph visualization with level-aware availability states.
- Node inspection and dependency path highlight.

Exit: graph tab is informative and performant on full vanilla+DLC data.

## 9) Immediate Next Actions

1. Create `src/fnv_planner/ui/` skeleton and app bootstrap (`app.py`).
2. Implement Build page first using the existing `BuildUiModel` contracts.
3. Add plugin source service that reuses default load-order logic.
4. Add Flatpak manifest once M1 app shell is in place.
