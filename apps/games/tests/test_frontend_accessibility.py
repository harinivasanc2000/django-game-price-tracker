"""Regression coverage for keyboard-safe shared navigation widgets."""

from django.template.loader import render_to_string
from django.test import SimpleTestCase


class SharedWidgetAccessibilityTests(SimpleTestCase):
    def test_search_suggestions_are_an_accessible_race_safe_combobox(self):
        html = render_to_string("games/_search_box.html")

        self.assertIn('role="combobox"', html)
        self.assertIn('aria-controls="suggestDropdown"', html)
        self.assertIn('role="listbox"', html)
        self.assertIn("new AbortController()", html)
        self.assertIn("version !== requestVersion", html)
        self.assertIn("platform.addEventListener('change', updateSuggestionLinks)", html)
        self.assertNotIn(".innerHTML", html)

    def test_tracked_drawer_exposes_and_manages_modal_focus(self):
        html = render_to_string("base.html")

        self.assertIn('aria-controls="trackedDrawer" aria-expanded="false"', html)
        self.assertIn('role="dialog" aria-modal="true"', html)
        self.assertIn('tabindex="-1" inert', html)
        self.assertIn("previouslyFocused = document.activeElement", html)
        self.assertIn("e.key === 'Tab' && isOpen()", html)
        self.assertIn("restoreTarget.focus()", html)
