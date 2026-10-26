"""Per-window bindings that retranslate in place without recreating UI or workers."""

from __future__ import annotations

from weakref import ref

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSlider,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QScrollBar,
    QStyle,
    QStyleOptionSlider,
    QWidget,
)
from shiboken6 import isValid

from nexus_ai.i18n import LANGUAGES, Text, render


class Translator(QObject):
    language_changed = Signal()

    def __init__(self, language: str, parent: QObject | None = None):
        super().__init__(parent)
        if language not in LANGUAGES:
            raise ValueError("Unsupported language")
        self.language = language
        self._bindings = {}
        self._objects = {}

    def text(self, message: str) -> str:
        return render(message, self.language)

    def bind(self, widget, message: str, setter: str = "setText") -> None:
        identity = id(widget)
        if identity not in self._objects:
            # Qt-created QAction wrappers can otherwise be collected while the
            # underlying menu stays alive. Keep wrappers until QObject destruction.
            self._objects[identity] = widget
            owner = ref(self)

            def cleanup(*_, identity=identity, owner=owner):
                manager = owner()
                if manager is not None:
                    manager._objects.pop(identity, None)
                    for key in [key for key in manager._bindings if key[0] == identity]:
                        del manager._bindings[key]

            widget.destroyed.connect(cleanup)
        self._bindings[(identity, setter)] = (ref(widget), message)
        getattr(widget, setter)(self.text(message))

    def watch_tree(self, root: QWidget) -> None:
        """Register program-owned captions only, never input or conversation contents."""
        for widget in [root, *root.findChildren(QWidget)]:
            properties = ["toolTip", "accessibleName", "accessibleDescription", "windowTitle"]
            if isinstance(widget, (QLabel, QAbstractButton)):
                properties.append("text")
            if isinstance(widget, (QPlainTextEdit, QLineEdit)):
                properties.append("placeholderText")
                if not widget.property("nexusLocalizedMenu"):
                    widget.setProperty("nexusLocalizedMenu", True)
                    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    reference = ref(widget)
                    widget.customContextMenuRequested.connect(
                        lambda point, reference=reference: self._context_menu(reference, point)
                    )
            if isinstance(widget, QScrollBar) and not widget.property("nexusLocalizedMenu"):
                widget.setProperty("nexusLocalizedMenu", True)
                widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                reference = ref(widget)
                widget.customContextMenuRequested.connect(
                    lambda point, reference=reference: self._scroll_menu(reference, point)
                )
            for name in properties:
                setter = "set" + name[0].upper() + name[1:]
                existing = self._bindings.get((id(widget), setter))
                if existing and existing[0]() is widget:
                    continue
                message = getattr(widget, name)()
                if message:
                    self.bind(widget, message, setter)

    def translate_menu(self, menu) -> None:
        for action in menu.actions():
            caption, separator, shortcut = action.text().partition("\t")
            self.bind(
                action,
                Text("{caption}{suffix}", caption=Text(caption), suffix=separator + shortcut),
            )

    def _context_menu(self, reference, point) -> None:
        widget = reference()
        if widget is None or not isValid(widget):
            return
        menu = widget.createStandardContextMenu()
        self.translate_menu(menu)
        menu.exec(widget.mapToGlobal(point))
        menu.deleteLater()

    def scrollbar_menu(self, widget, point):
        menu = QMenu(widget)
        option = QStyleOptionSlider()
        widget.initStyleOption(option)
        style = widget.style()
        groove = style.subControlRect(
            QStyle.ComplexControl.CC_ScrollBar,
            option,
            QStyle.SubControl.SC_ScrollBarGroove,
            widget,
        )
        handle = style.subControlRect(
            QStyle.ComplexControl.CC_ScrollBar,
            option,
            QStyle.SubControl.SC_ScrollBarSlider,
            widget,
        )
        vertical = widget.orientation() == Qt.Orientation.Vertical
        length = handle.height() if vertical else handle.width()
        span = max(1, (groove.height() if vertical else groove.width()) - length)
        position = (point.y() - groove.y() if vertical else point.x() - groove.x()) - length // 2
        value = QStyle.sliderValueFromPosition(
            widget.minimum(),
            widget.maximum(),
            max(0, min(span, position)),
            span,
            option.upsideDown,
        )
        here = menu.addAction("")
        self.bind(here, "Scroll here")
        here.triggered.connect(lambda: widget.setValue(value))
        menu.addSeparator()
        names = (
            ("Top", "Bottom", "Page up", "Page down", "Scroll up", "Scroll down")
            if vertical
            else (
                "Left edge",
                "Right edge",
                "Page left",
                "Page right",
                "Scroll left",
                "Scroll right",
            )
        )
        actions = (
            QAbstractSlider.SliderAction.SliderToMinimum,
            QAbstractSlider.SliderAction.SliderToMaximum,
            QAbstractSlider.SliderAction.SliderPageStepSub,
            QAbstractSlider.SliderAction.SliderPageStepAdd,
            QAbstractSlider.SliderAction.SliderSingleStepSub,
            QAbstractSlider.SliderAction.SliderSingleStepAdd,
        )
        for title, operation in zip(names, actions, strict=True):
            action = menu.addAction("")
            self.bind(action, title)
            action.triggered.connect(
                lambda checked=False, operation=operation: widget.triggerAction(operation)
            )
        return menu

    def _scroll_menu(self, reference, point) -> None:
        widget = reference()
        if widget is None or not isValid(widget):
            return
        menu = self.scrollbar_menu(widget, point)
        menu.exec(widget.mapToGlobal(point))
        menu.deleteLater()

    def set_language(self, language: str) -> None:
        if language not in LANGUAGES:
            raise ValueError("Unsupported language")
        if language == self.language:
            return
        self.language = language
        for key, (reference, message) in list(self._bindings.items()):
            widget = reference()
            if widget is None or not isValid(widget):
                del self._bindings[key]
            else:
                getattr(widget, key[1])(self.text(message))
        self.language_changed.emit()
