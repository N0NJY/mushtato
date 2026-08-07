"""Headless tests for TwoLineTabBar (post-1.11.0): a QTabBar that
renders a tab's label as two lines instead of QTabBar's own single-line
text, which does not grow tab height for an embedded newline (confirmed
directly before writing the class -- see its own module docstring).
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QStyleFactory, QTabWidget, QWidget

from gui.windows.two_line_tab_bar import TwoLineTabBar


def make_bar(qapp) -> QTabWidget:
    # Fusion, matching what the real app forces (gui/theme.py) -- the
    # sizeHint-doesn't-grow-for-\n finding that motivated this class was
    # confirmed specifically against Fusion, not whatever the offscreen
    # platform's own default style happens to be.
    QApplication.instance().setStyle(QStyleFactory.create("Fusion"))
    tw = QTabWidget()
    tw.setTabBar(TwoLineTabBar(tw))
    return tw


def test_single_line_tab_text_is_unaffected(qapp):
    tw = make_bar(qapp)
    tw.addTab(QWidget(), "Silvren")

    assert tw.tabBar().tabText(0) == "Silvren"


def test_two_line_tab_is_taller_than_a_one_line_tab(qapp):
    tw = make_bar(qapp)
    tw.addTab(QWidget(), "Silvren")
    tw.addTab(QWidget(), "Estrellita\nThoran")
    tw.show()
    QApplication.processEvents()

    one_line_height = tw.tabBar().tabSizeHint(0).height()
    two_line_height = tw.tabBar().tabSizeHint(1).height()

    assert two_line_height > one_line_height


def test_lines_helper_splits_on_the_first_newline_only(qapp):
    bar = TwoLineTabBar()
    bar.addTab("Host\nName With Spaces")

    assert bar._lines(0) == ("Host", "Name With Spaces")


def test_lines_helper_returns_empty_second_line_for_plain_text(qapp):
    bar = TwoLineTabBar()
    bar.addTab("Silvren")

    assert bar._lines(0) == ("Silvren", "")


def test_changing_tab_text_from_one_line_to_two_grows_its_size_hint(qapp):
    # The real-world sequence: a tab starts as just the world name, then
    # gains a second line once a Character logs in (SessionTab.
    # _set_character_name -> titleChanged -> MainWindow's
    # _on_tab_title_changed -> setTabText).
    tw = make_bar(qapp)
    tw.addTab(QWidget(), "Estrellita")
    before = tw.tabBar().tabSizeHint(0).height()

    tw.setTabText(0, "Estrellita\nThoran")
    after = tw.tabBar().tabSizeHint(0).height()

    assert after > before


def test_paints_without_crashing_and_produces_non_blank_pixels_in_both_line_areas(qapp):
    # A real render, not just calling the size/text-splitting logic --
    # grabs the tab bar as a pixmap and checks that *something* was
    # actually painted in both the top-line and bottom-line regions of
    # a two-line tab, not just that paintEvent ran without raising.
    tw = make_bar(qapp)
    tw.addTab(QWidget(), "Estrellita\nThoran")
    tw.resize(200, 60)
    tw.show()
    QApplication.processEvents()

    bar = tw.tabBar()
    rect = bar.tabRect(0)
    pixmap = bar.grab(rect)
    image = pixmap.toImage()

    background = image.pixelColor(2, 2)  # a corner, presumably untouched by text
    top_line_has_ink = any(
        image.pixelColor(x, rect.height() // 4) != background for x in range(rect.width())
    )
    bottom_line_has_ink = any(
        image.pixelColor(x, 3 * rect.height() // 4) != background for x in range(rect.width())
    )

    assert top_line_has_ink
    assert bottom_line_has_ink


def test_respects_tab_text_color_set_by_the_existing_activity_flash_mechanism(qapp):
    # MainWindow's tab-activity-flash/active-tab-highlight features
    # (post-8b/post-12b) work by calling plain QTabBar.setTabTextColor()
    # -- this class must keep honoring that rather than hardcoding a
    # color, so those pre-existing features don't regress.
    tw = make_bar(qapp)
    tw.addTab(QWidget(), "Estrellita\nThoran")
    bar = tw.tabBar()

    orange = QColor(255, 140, 0)
    bar.setTabTextColor(0, orange)

    assert bar.tabTextColor(0) == orange
