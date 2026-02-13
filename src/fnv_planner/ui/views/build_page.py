"""Build page view."""

from collections.abc import Callable

from gi.repository import Gtk

from fnv_planner.ui.controllers.build_controller import BuildController


class BuildPage(Gtk.Box):
    """Build screen with priority goals and diagnostics."""

    def __init__(self, controller: BuildController) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._controller = controller
        self._updating = False
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        title = Gtk.Label(label="Build")
        title.add_css_class("title-2")
        title.set_xalign(0)
        self.append(title)

        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        pane.set_wide_handle(True)
        pane.set_hexpand(True)
        pane.set_vexpand(True)
        pane.set_shrink_start_child(False)
        pane.set_shrink_end_child(False)
        self.append(pane)

        left_scroller = Gtk.ScrolledWindow()
        left_scroller.set_min_content_width(340)
        left_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        pane.set_start_child(left_scroller)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        left_scroller.set_child(left)

        requests_frame = Gtk.Frame(label="Priority Requests")
        left.append(requests_frame)
        requests_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        requests_box.set_margin_top(10)
        requests_box.set_margin_bottom(10)
        requests_box.set_margin_start(10)
        requests_box.set_margin_end(10)
        requests_frame.set_child(requests_box)

        request_columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        requests_box.append(request_columns)

        primary_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        primary_col.set_hexpand(True)
        request_columns.append(primary_col)

        meta_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        meta_col.set_hexpand(True)
        request_columns.append(meta_col)

        av_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._av_combo = Gtk.ComboBoxText()
        for av, name in self._controller.actor_value_options():
            self._av_combo.append(str(av), name)
        self._av_value = Gtk.SpinButton.new_with_range(1, 100, 1)
        self._av_value.set_value(100)
        self._av_combo.connect("changed", self._on_actor_value_changed)
        self._av_combo.set_active(0)
        av_row.append(self._av_combo)
        av_row.append(self._av_value)
        add_av = Gtk.Button(label="Add Stat/Skill Request")
        add_av.connect("clicked", self._on_add_actor_value_request)
        av_row.append(add_av)
        primary_col.append(av_row)

        perk_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_perk = Gtk.Button(label="Open Perk Picker")
        add_perk.connect("clicked", self._on_add_perk_request)
        perk_row.append(add_perk)
        primary_col.append(perk_row)

        trait_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_trait = Gtk.Button(label="Open Trait Picker")
        add_trait.connect("clicked", self._on_add_trait_request)
        trait_row.append(add_trait)
        trait_row.append(Gtk.Label(label=f"Max traits: {self._controller.max_traits}", xalign=0))
        primary_col.append(trait_row)

        meta_header = Gtk.Label(label="Meta Requests or Bundle Requests", xalign=0)
        meta_header.add_css_class("heading")
        meta_col.append(meta_header)
        max_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        max_row.set_halign(Gtk.Align.START)
        add_max = Gtk.Button(label="Add Max Skills Request")
        add_max.connect("clicked", self._on_add_max_skills_request)
        max_row.append(add_max)
        meta_col.append(max_row)

        request_scroll = Gtk.ScrolledWindow()
        request_scroll.set_min_content_height(260)
        request_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        requests_box.append(request_scroll)
        self._requests_list = Gtk.ListBox()
        request_scroll.set_child(self._requests_list)

        stats_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        left.append(stats_row)

        special_frame = Gtk.Frame(label="SPECIAL")
        special_frame.set_hexpand(True)
        stats_row.append(special_frame)
        special_grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        special_grid.set_margin_top(10)
        special_grid.set_margin_bottom(10)
        special_grid.set_margin_start(10)
        special_grid.set_margin_end(10)
        special_frame.set_child(special_grid)

        self._special_values: dict[int, Gtk.Label] = {}
        for idx, (av, name, _value) in enumerate(self._controller.special_rows()):
            special_grid.attach(Gtk.Label(label=name, xalign=0), 0, idx, 1, 1)
            value_label = Gtk.Label(xalign=1)
            value_label.add_css_class("numeric")
            special_grid.attach(value_label, 1, idx, 1, 1)
            self._special_values[av] = value_label

        traits_frame = Gtk.Frame(label="Traits")
        traits_frame.set_hexpand(True)
        stats_row.append(traits_frame)
        traits_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        traits_box.set_margin_top(10)
        traits_box.set_margin_bottom(10)
        traits_box.set_margin_start(10)
        traits_box.set_margin_end(10)
        traits_frame.set_child(traits_box)
        self._traits_list = Gtk.ListBox()
        traits_box.append(self._traits_list)

        self._budget_label = Gtk.Label(xalign=0)
        left.append(self._budget_label)

        books_frame = Gtk.Frame(label="Skill Books")
        left.append(books_frame)
        books_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        books_box.set_margin_top(10)
        books_box.set_margin_bottom(10)
        books_box.set_margin_start(10)
        books_box.set_margin_end(10)
        books_frame.set_child(books_box)
        self._books_totals_label = Gtk.Label(xalign=0)
        self._books_totals_label.set_wrap(True)
        books_box.append(self._books_totals_label)
        self._books_list = Gtk.ListBox()
        books_box.append(self._books_list)

        options_frame = Gtk.Frame(label="Perk Planning")
        left.append(options_frame)
        options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        options_box.set_margin_top(10)
        options_box.set_margin_bottom(10)
        options_box.set_margin_start(10)
        options_box.set_margin_end(10)
        options_frame.set_child(options_box)
        options_box.append(
            Gtk.Label(
                label="Challenge perks are shown and tagged as [challenge] in perk pickers.",
                xalign=0,
                wrap=True,
            )
        )
        options_box.append(
            Gtk.Label(
                label="SPECIAL and skill allocation are computed from selected goals and priorities.",
                xalign=0,
                wrap=True,
            )
        )
        options_box.append(
            Gtk.Label(
                label=(
                    "Skill book copies detected from plugins (placed refs + inventory templates): "
                    f"{self._controller.total_skill_books()} "
                    "(used as fallback for Max Skills requests)."
                ),
                xalign=0,
                wrap=True,
            )
        )

        self._status_label = Gtk.Label(xalign=0)
        self._status_label.add_css_class("error")
        self._status_label.set_wrap(True)
        left.append(self._status_label)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        pane.set_end_child(right)

        snapshot_frame = Gtk.Frame(label="Snapshot")
        right.append(snapshot_frame)
        snapshot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        snapshot_box.set_margin_top(10)
        snapshot_box.set_margin_bottom(10)
        snapshot_box.set_margin_start(10)
        snapshot_box.set_margin_end(10)
        snapshot_frame.set_child(snapshot_box)

        self._valid_label = Gtk.Label(xalign=0)
        snapshot_box.append(self._valid_label)
        self._feasibility_label = Gtk.Label(xalign=0)
        self._feasibility_label.set_wrap(True)
        snapshot_box.append(self._feasibility_label)
        self._now_label = Gtk.Label(xalign=0)
        self._now_label.set_wrap(True)
        snapshot_box.append(self._now_label)
        self._target_label = Gtk.Label(xalign=0)
        self._target_label.set_wrap(True)
        snapshot_box.append(self._target_label)
        self._delta_label = Gtk.Label(xalign=0)
        self._delta_label.set_wrap(True)
        snapshot_box.append(self._delta_label)
        self._book_dependency_label = Gtk.Label(xalign=0)
        self._book_dependency_label.set_wrap(True)
        snapshot_box.append(self._book_dependency_label)

        rationale_frame = Gtk.Frame(label="Perk Rationale")
        right.append(rationale_frame)
        rationale_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        rationale_box.set_margin_top(10)
        rationale_box.set_margin_bottom(10)
        rationale_box.set_margin_start(10)
        rationale_box.set_margin_end(10)
        rationale_frame.set_child(rationale_box)
        self._rationale_list = Gtk.ListBox()
        rationale_box.append(self._rationale_list)

        diagnostics_frame = Gtk.Frame(label="Diagnostics")
        right.append(diagnostics_frame)
        diagnostics_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        diagnostics_box.set_margin_top(10)
        diagnostics_box.set_margin_bottom(10)
        diagnostics_box.set_margin_start(10)
        diagnostics_box.set_margin_end(10)
        diagnostics_frame.set_child(diagnostics_box)
        self._diag_list = Gtk.ListBox()
        diagnostics_box.append(self._diag_list)

        self.refresh()

    def refresh(self) -> None:
        self._updating = True
        try:
            for av, _name, value in self._controller.special_rows():
                self._special_values[av].set_text(str(value))

            used, remaining = self._controller.special_totals()
            self._budget_label.set_text(
                f"SPECIAL used {used}/{self._controller.special_budget}  remaining {remaining}"
            )
            self._render_traits()
            self._render_skill_books()
            self._render_priority_requests()

            now, target, delta, valid = self._controller.summary()
            self._valid_label.set_text(f"Build valid: {'yes' if valid else 'no'}")
            feasible, warning = self._controller.feasibility_warning()
            self._feasibility_label.set_text(
                f"{'Possible' if feasible else 'Not possible'}: {warning}"
            )
            self._now_label.set_text(
                "Now: "
                f"HP {now.hit_points} | AP {now.action_points} | "
                f"Carry {now.carry_weight:.0f} | Crit {now.crit_chance:.0f}"
            )
            self._target_label.set_text(
                "Target: "
                f"HP {target.hit_points} | AP {target.action_points} | "
                f"Carry {target.carry_weight:.0f} | Crit {target.crit_chance:.0f}"
            )
            self._delta_label.set_text(
                "Delta: "
                f"HP {delta['hit_points']:+.0f} | AP {delta['action_points']:+.0f} | "
                f"Carry {delta['carry_weight']:+.0f} | Crit {delta['crit_chance']:+.0f}"
            )
            warning = self._controller.book_dependency_warning()
            self._book_dependency_label.set_text(
                f"Book dependency: {warning}" if warning else "Book dependency: none."
            )
            self._render_rationale()

            self._render_diagnostics()
        finally:
            self._updating = False

    def _render_traits(self) -> None:
        child = self._traits_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._traits_list.remove(child)
            child = next_child

        rows = self._controller.selected_traits_rows()
        if not rows:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label="No traits selected.", xalign=0))
            self._traits_list.append(row)
            return

        for name, source in rows:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label=f"{name}  [{source}]", xalign=0))
            self._traits_list.append(row)

    def _render_rationale(self) -> None:
        child = self._rationale_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._rationale_list.remove(child)
            child = next_child

        rows = self._controller.perk_reason_rows()
        if not rows:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label="No perk rationale available.", xalign=0))
            self._rationale_list.append(row)
            return

        for text in rows:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label=text, xalign=0, wrap=True))
            self._rationale_list.append(row)

    def _on_add_actor_value_request(self, _button: Gtk.Button) -> None:
        av_id = self._av_combo.get_active_id()
        if av_id is None:
            self._status_label.set_text("Select a stat or skill first")
            return
        ok, message = self._controller.add_actor_value_request(
            actor_value=int(av_id),
            value=int(self._av_value.get_value()),
            operator=">=",
            reason="Priority request",
        )
        self._status_label.set_text("" if ok else (message or "Could not add request"))
        self.refresh()

    def _on_actor_value_changed(self, _combo: Gtk.ComboBoxText) -> None:
        if not hasattr(self, "_av_value"):
            return
        av_id = self._av_combo.get_active_id()
        if av_id is None:
            return
        max_value = self._controller.actor_value_request_max(int(av_id))
        self._av_value.set_range(1, max_value)
        self._av_value.set_value(max_value)

    def _on_add_perk_request(self, _button: Gtk.Button) -> None:
        items = [
            (pid, f"{name} [{category}]")
            for pid, name, category in self._controller.perk_options()
        ]
        self._open_multi_select_dialog(
            title="Select Perk Requests",
            items=items,
            selected=self._controller.selected_perk_ids(),
            on_apply=self._apply_perk_picker_selection,
        )

    def _on_add_trait_request(self, _button: Gtk.Button) -> None:
        items = [(tid, name) for tid, name in self._controller.trait_options()]
        self._open_multi_select_dialog(
            title="Select Trait Requests",
            items=items,
            selected=self._controller.selected_trait_ids(),
            on_apply=self._apply_trait_picker_selection,
        )

    def _on_add_max_skills_request(self, _button: Gtk.Button) -> None:
        self._controller.add_max_skills_request()
        self._status_label.set_text("")
        self.refresh()

    def _on_move_request(self, _button: Gtk.Button, index: int, delta: int) -> None:
        self._controller.move_priority_request(index, delta)
        self.refresh()

    def _on_remove_request(self, _button: Gtk.Button, index: int) -> None:
        self._controller.remove_priority_request(index)
        self.refresh()

    def _render_priority_requests(self) -> None:
        child = self._requests_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._requests_list.remove(child)
            child = next_child

        rows = self._controller.priority_request_rows()
        if not rows:
            row = Gtk.ListBoxRow()
            row.set_child(
                Gtk.Label(
                    label="No requests yet. Add goals like Barter 100, Speech 100, Strength 9, Laser Commander, Crit 10.",
                    xalign=0,
                    wrap=True,
                )
            )
            self._requests_list.append(row)
            return

        for index, text in rows:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            label = Gtk.Label(label=f"{index + 1}. {text}", xalign=0)
            label.set_wrap(True)
            label.set_hexpand(True)
            box.append(label)

            up = Gtk.Button(label="Up")
            up.connect("clicked", self._on_move_request, index, -1)
            box.append(up)
            down = Gtk.Button(label="Down")
            down.connect("clicked", self._on_move_request, index, 1)
            box.append(down)
            remove = Gtk.Button(label="Remove")
            remove.connect("clicked", self._on_remove_request, index)
            box.append(remove)

            row.set_child(box)
            self._requests_list.append(row)

    def _render_skill_books(self) -> None:
        self._books_totals_label.set_text(
            "Books needed / available: "
            f"{self._controller.needed_skill_books()} / {self._controller.total_skill_books()}"
        )
        child = self._books_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._books_list.remove(child)
            child = next_child

        rows = self._controller.skill_book_rows()
        if not rows:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label="No skill book usage currently required.", xalign=0))
            self._books_list.append(row)
            return

        for name, needed, available in rows:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label=f"{name}: {needed} / {available}", xalign=0))
            self._books_list.append(row)

    def _apply_perk_picker_selection(self, selected: set[int]) -> None:
        self._controller.set_perk_requests(selected)
        self._status_label.set_text("")
        self.refresh()

    def _apply_trait_picker_selection(self, selected: set[int]) -> None:
        ok, message = self._controller.set_trait_requests(selected)
        self._status_label.set_text("" if ok else (message or "Trait request limit applied"))
        self.refresh()

    def _open_multi_select_dialog(
        self,
        *,
        title: str,
        items: list[tuple[int, str]],
        selected: set[int],
        on_apply: Callable[[set[int]], None],
    ) -> None:
        root = self.get_root()
        dialog = Gtk.Dialog(title=title, transient_for=root if isinstance(root, Gtk.Window) else None, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Apply", Gtk.ResponseType.OK)
        dialog.set_default_size(900, 640)

        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_margin_top(10)
        content.set_margin_bottom(10)
        content.set_margin_start(10)
        content.set_margin_end(10)

        search = Gtk.SearchEntry()
        search.set_placeholder_text("Filter...")
        content.append(search)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        content.append(scroll)

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_activate_on_single_click(True)
        flow.set_max_children_per_line(3)
        flow.set_min_children_per_line(3)
        flow.set_column_spacing(10)
        flow.set_row_spacing(6)
        scroll.set_child(flow)

        checks: dict[int, Gtk.CheckButton] = {}
        rows: dict[int, Gtk.FlowBoxChild] = {}
        row_ids: dict[Gtk.FlowBoxChild, int] = {}
        labels: dict[int, str] = {}
        for item_id, label in items:
            check = Gtk.CheckButton(label=label)
            check.set_active(item_id in selected)
            check.set_hexpand(True)
            check.set_halign(Gtk.Align.FILL)
            child = Gtk.FlowBoxChild()
            child.set_child(check)
            flow.insert(child, -1)
            checks[item_id] = check
            rows[item_id] = child
            row_ids[child] = item_id
            labels[item_id] = label.lower()

        def _on_child_activated(_flow: Gtk.FlowBox, child: Gtk.FlowBoxChild) -> None:
            item_id = row_ids.get(child)
            if item_id is None:
                return
            check = checks.get(item_id)
            if check is None:
                return
            check.set_active(not check.get_active())

        flow.connect("child-activated", _on_child_activated)

        def _apply_filter(_entry: Gtk.SearchEntry) -> None:
            q = search.get_text().strip().lower()
            for item_id, child in rows.items():
                child.set_visible((not q) or (q in labels[item_id]))

        search.connect("search-changed", _apply_filter)

        def _on_response(_dialog: Gtk.Dialog, response: int) -> None:
            if response == Gtk.ResponseType.OK:
                chosen = {item_id for item_id, check in checks.items() if check.get_active()}
                on_apply(chosen)
            dialog.destroy()

        dialog.connect("response", _on_response)
        dialog.present()

    def _render_diagnostics(self) -> None:
        child = self._diag_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._diag_list.remove(child)
            child = next_child

        diagnostics = self._controller.diagnostics()
        if not diagnostics:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label="No diagnostics.", xalign=0))
            self._diag_list.append(row)
            return

        for diag in diagnostics:
            row = Gtk.ListBoxRow()
            message = f"[{diag.severity}] {diag.code}: {diag.message}"
            row.set_child(Gtk.Label(label=message, xalign=0, wrap=True))
            self._diag_list.append(row)
