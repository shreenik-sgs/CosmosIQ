"""Tests for the Infinite Canvas static-HTML renderer (IMPLEMENTATION-008B).

These tests prove the PRESENTATION discipline INDEPENDENTLY of the implementation:

* the renderer reads ONLY the assembled view -- it imports no reasoning layer;
* ``render_cockpit_html`` is a pure function of the view (no mutation, deterministic);
* every one of the nine panels renders, plus provenance and data gaps;
* speculative rumors and negative catalysts render in SEPARATE labelled sections,
  and the rumor block is flagged "not confirmed";
* the personalized section exposes a sizing RANGE / max-exposure % only -- no exact
  size, no order type, no broker, no buy/sell action;
* the manual section is manual-only and shows the user-selected size;
* the whole document carries NO action affordance (no button/form/onclick/submit/
  place order, no buy/sell action element);
* the technical section uses timing-confirmation language, never "action-ready".
"""

from __future__ import annotations

import os as _os, sys as _sys
_SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src")
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

import ast
import copy
import unittest

from runtime.vertical_slice_runner import run_iren_slice

from infinite_canvas import (
    from_slice,
    render_cockpit_html,
    render_slice_to_html,
    write_cockpit_html,
)
import infinite_canvas.render_html as render_html


_REASONING_ROOTS = (
    "reality_intelligence", "genesis", "prometheus", "personal_cio", "execution_manual",
)


def _section(doc, name):
    """Slice one section out of the document by its stable BEGIN/END markers."""
    a = "<!-- BEGIN-SECTION:{0} -->".format(name)
    b = "<!-- END-SECTION:{0} -->".format(name)
    return doc[doc.index(a):doc.index(b)]


class TestCanvasRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slice = run_iren_slice()
        cls.cockpit = from_slice(cls.slice)
        cls.doc = render_cockpit_html(cls.cockpit)

    # --- the renderer reads ONLY the view (no reasoning import) ------------- #
    def test_renderer_imports_no_reasoning_layer(self):
        src = _os.path.join(_SRC, "infinite_canvas", "render_html.py")
        with open(src, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    imported_roots.add(node.module.split(".")[0])
        for root in _REASONING_ROOTS:
            self.assertNotIn(root, imported_roots,
                             "renderer must not import reasoning layer {0!r}".format(root))
        # It may only import the view (relative) + stdlib (html/typing/__future__).
        self.assertEqual(imported_roots, {"html", "typing", "__future__"})

    # --- pure function of the view ----------------------------------------- #
    def test_returns_non_empty_string(self):
        self.assertIsInstance(self.doc, str)
        self.assertTrue(self.doc.strip())
        self.assertIn("<!DOCTYPE html>", self.doc)

    def test_render_does_not_mutate_view(self):
        before = copy.deepcopy(self.cockpit)
        _ = render_cockpit_html(self.cockpit)
        self.assertEqual(before, self.cockpit)

    def test_deterministic_byte_identical(self):
        self.assertEqual(render_cockpit_html(self.cockpit),
                         render_cockpit_html(self.cockpit))

    def test_render_slice_to_html_matches_from_slice(self):
        self.assertEqual(render_slice_to_html(self.slice),
                         render_cockpit_html(from_slice(self.slice)))

    def test_write_cockpit_html_is_deterministic(self):
        import tempfile
        d = tempfile.mkdtemp()
        p1 = _os.path.join(d, "a.html")
        p2 = _os.path.join(d, "b.html")
        write_cockpit_html(self.cockpit, p1)
        write_cockpit_html(self.cockpit, p2)
        with open(p1, encoding="utf-8") as f1, open(p2, encoding="utf-8") as f2:
            c1, c2 = f1.read(), f2.read()
        self.assertEqual(c1, c2)
        self.assertEqual(c1, self.doc)

    # --- all nine panels render -------------------------------------------- #
    def test_all_nine_panels_render(self):
        self.assertEqual(len(self.cockpit.panels), 9)
        for panel in self.cockpit.panels:
            self.assertIn(panel.panel_id, self.doc)

    # --- provenance drawer -------------------------------------------------- #
    def test_provenance_section_renders(self):
        prov = _section(self.doc, "provenance")
        self.assertIn("Provenance chain", prov)
        # a real source object id from the chain appears as a chain entry.
        first = self.cockpit.provenance_chain[0]
        self.assertIn(first.object_id, prov)
        self.assertIn(first.kind, prov)

    # --- data gaps are visible, not hidden --------------------------------- #
    def test_data_gaps_section_renders(self):
        dg = _section(self.doc, "data_gaps")
        self.assertTrue(self.cockpit.data_gaps)
        sample = self.cockpit.data_gaps[0]   # "panel_id.field (...)"
        self.assertIn(sample, dg)
        # the panel name prefix is present.
        self.assertIn(sample.split(".")[0], dg)

    def test_missing_fields_have_a_marker(self):
        # at least one panel flags a missing field, rendered with a clear marker.
        self.assertIn("missing", self.doc.lower())
        self.assertIn("009", self.doc)

    # --- catalyst: rumors & negatives SEPARATE and labelled ---------------- #
    def test_rumors_and_negatives_separate_sections(self):
        cat = _section(self.doc, "catalyst")
        self.assertIn("Speculative rumors", cat)
        self.assertIn("Negative catalysts", cat)
        # the rumor block is flagged as not-confirmed.
        self.assertIn("not confirmed", cat.lower())
        # rumors are not merged into the confirmed/probable block.
        self.assertIn("confirmed / probable", cat.lower())

    # --- personalized: RANGE / max-exposure % only, no order/size/broker --- #
    def test_personalized_has_no_order_or_size_or_broker(self):
        ps = _section(self.doc, "personalized_action").lower()
        for token in ("order type", "shares", "limit price", "broker"):
            self.assertNotIn(token, ps)
        # no buy/sell action language.
        self.assertNotIn("buy", ps)
        self.assertNotIn("sell", ps)
        # it DOES expose the sizing range / max exposure %.
        self.assertIn("max exposure", ps)
        self.assertIn("sizing range", ps)
        pa = self.cockpit.personalized_action
        self.assertIn(("%g" % pa.recommended_max_exposure_pct), ps)

    # --- manual: manual-only, shows the user-selected size ----------------- #
    def test_manual_shows_user_selected_size_and_is_manual(self):
        me = _section(self.doc, "manual_execution")
        self.assertIn("manual", me.lower())
        amt = self.cockpit.manual_execution.user_selected_allocation_amount
        self.assertIn(("%g" % amt), me)

    def test_whole_document_has_no_action_affordance(self):
        low = self.doc.lower()
        for token in ("<button", "<form", "onclick", "submit", "place order", "<script"):
            self.assertNotIn(token, low)
        # no buy/sell action anywhere in the document.
        self.assertNotIn("buy", low)
        self.assertNotIn("sell", low)

    # --- technical: timing-confirmation language, never action-ready ------- #
    def test_technical_uses_timing_confirmation_language(self):
        ts = _section(self.doc, "technical_confirmation").lower()
        self.assertIn("timing-confirmation", ts)
        self.assertNotIn("action-ready", ts)
        self.assertNotIn("action_ready", ts)


if __name__ == "__main__":
    unittest.main()
