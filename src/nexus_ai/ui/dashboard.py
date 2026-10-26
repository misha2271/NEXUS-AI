"""Dashboard components drawn with Qt Widgets; no chart or device SDK dependency."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from nexus_ai import __version__
from nexus_ai.history import TelemetryHistory
from nexus_ai.i18n import Text
from nexus_ai.modules import ModuleSpec
from nexus_ai.ui.localization import Translator

COLORS = ("#8ce0c4", "#a8b5ff", "#e1b884", "#8bc8ed")


def label(text: str, role: str = "muted") -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def scroll_page(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(content)
    return area


class ResponsiveGrid(QWidget):
    """Reflow existing widgets instead of duplicating telemetry or chat state."""

    def __init__(
        self, widgets: list[QWidget], *, wide_columns: int, breakpoint: int, narrow_columns: int = 1
    ) -> None:
        super().__init__()
        self.widgets = widgets
        self.wide_columns = wide_columns
        self.breakpoint = breakpoint
        self.narrow_columns = narrow_columns
        self.columns = 0
        self.grid = QGridLayout(self)
        # A wide grid must not impose its current column count as the parent's
        # minimum width. Otherwise Windows font metrics can prevent the resize
        # event that is needed to switch to the compact layout.
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(14)
        self._reflow(wide_columns)

    def _reflow(self, columns: int) -> None:
        if columns == self.columns:
            return
        for widget in self.widgets:
            self.grid.removeWidget(widget)
        for column in range(max(self.columns, columns)):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, widget in enumerate(self.widgets):
            self.grid.addWidget(widget, index // columns, index % columns)
        self.columns = columns

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow(
            self.wide_columns
            if self.width() >= self.breakpoint
            else self.narrow_columns
            if self.width() >= 480
            else 1
        )


class HistoryChart(QFrame):
    def __init__(
        self, title: str, history: TelemetryHistory, prefix: str, color: str, i18n: Translator
    ) -> None:
        super().__init__()
        self.setObjectName("panel")
        self.i18n = i18n
        self.i18n.language_changed.connect(self.update)
        self.title = title
        self.history = history
        self.prefix = prefix
        self.color = color
        self.setMinimumHeight(188)
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.i18n.bind(
            self, Text("{title} historical chart", title=Text(title)), "setAccessibleName"
        )

    def chart_series(self) -> list[list[tuple[float, float | None]]]:
        keys = self.history.keys(self.prefix)
        return [self.history.series(key) for key in keys]

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#e6eaf2"))
        painter.drawText(18, 28, self.i18n.text(self.title))
        plot = QRectF(18, 48, max(1, self.width() - 66), self.height() - 88)
        temperatures = self.prefix.endswith("temp:") or self.prefix == "temperature:"
        series = self.chart_series()
        valid = [value for values in series for _, value in values if value is not None]
        maximum = max(100, max(valid, default=0) * 1.15) if temperatures else 100
        painter.setPen(QPen(QColor("#27313c"), 1))
        for fraction in (0, 0.5, 1):
            y = plot.bottom() - plot.height() * fraction
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor("#8793a6"))
            painter.drawText(QPointF(plot.right() + 8, y + 4), f"{maximum * fraction:.0f}")
            painter.setPen(QPen(QColor("#27313c"), 1))
        if not valid:
            painter.setPen(QColor("#8793a6"))
            painter.drawText(
                plot, Qt.AlignmentFlag.AlignCenter, self.i18n.text("No readings available")
            )
        elif len(self.history.points) < 2:
            painter.setPen(QColor("#8793a6"))
            painter.drawText(
                plot, Qt.AlignmentFlag.AlignCenter, self.i18n.text("Collecting history…")
            )
        else:
            first = self.history.points[0].timestamp
            span = max(1, self.history.points[-1].timestamp - first)
            for index, values in enumerate(series):
                path = QPainterPath()
                drawing = False
                for timestamp, value in values:
                    if value is None:
                        drawing = False
                        continue
                    point = QPointF(
                        plot.left() + (timestamp - first) / span * plot.width(),
                        plot.bottom() - min(maximum, max(0, value)) / maximum * plot.height(),
                    )
                    if drawing:
                        path.lineTo(point)
                    else:
                        path.moveTo(point)
                        painter.setPen(QPen(QColor(self.color), 3))
                        painter.drawPoint(point)
                    drawing = True
                color = QColor(COLORS[index % len(COLORS)] if len(series) > 1 else self.color)
                painter.setPen(QPen(color, 2))
                painter.drawPath(path)
        painter.setPen(QColor("#8793a6"))
        duration = (
            self.history.points[-1].timestamp - self.history.points[0].timestamp
            if self.history.points
            else 0
        )
        painter.drawText(
            18,
            self.height() - 14,
            self.i18n.text(
                Text("{duration:.0f}s captured · gaps = unavailable", duration=duration)
            ),
        )
        painter.end()


class ModulePage(QWidget):
    def __init__(self, spec: ModuleSpec, i18n: Translator) -> None:
        super().__init__()
        self.spec = spec
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.addWidget(label("DEVICE WORKSPACE", "eyebrow"))
        layout.addWidget(label(spec.title, "pageTitle"))
        layout.addWidget(label(spec.description, "lead"))
        panel = QFrame()
        panel.setObjectName("panel")
        body = QVBoxLayout(panel)
        body.setContentsMargins(24, 24, 24, 24)
        body.setSpacing(18)
        body.addWidget(label("NOT CONNECTED · NO VALIDATED PROVIDER", "unavailable"))
        body.addWidget(label(spec.requirements, "body"))
        body.addWidget(label("Hardware controls remain locked until a supported SDK is validated."))
        self.controls: list[QPushButton] = []
        for action in spec.controls:
            button = QPushButton()
            i18n.bind(button, Text("{action} · unavailable", action=Text(action)))
            button.setEnabled(False)
            button.setToolTip("Requires an implemented, supported and hardware-validated provider")
            self.controls.append(button)
            body.addWidget(button)
        layout.addWidget(panel)
        self.gaming_button = None
        if spec.key == "gaming":
            self.gaming_button = QPushButton("Use existing Gaming inference profile")
            self.gaming_button.setObjectName("primary")
            layout.addWidget(self.gaming_button)
        if spec.key == "updates":
            version = label("", "body")
            i18n.bind(version, Text("Installed application  /  {version}", version=__version__))
            layout.addWidget(version)
        layout.addStretch()


class Sidebar(QFrame):
    def __init__(self, i18n: Translator) -> None:
        super().__init__()
        self.i18n = i18n
        self.setObjectName("sidebar")
        self.setFixedWidth(208)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 24, 16, 20)
        self.layout.setSpacing(6)
        self.layout.addWidget(label("N / NEXUS", "brand"))
        self.layout.addWidget(label("PERSONAL SYSTEM WORKSPACE", "sidebarCaption"))
        self.layout.addSpacing(24)
        self.nav_content = QWidget()
        self.nav_layout = QVBoxLayout(self.nav_content)
        self.nav_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_layout.setSpacing(6)
        self.nav_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.nav_scroll = scroll_page(self.nav_content)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_scroll.setMinimumHeight(100)
        self.layout.addWidget(self.nav_scroll, 1)
        self.buttons: dict[str, QPushButton] = {}

    def add_route(self, key: str, title: str) -> QPushButton:
        button = QPushButton(title)
        button.setObjectName("nav")
        button.setCheckable(True)
        button.setToolTip(title)
        self.i18n.bind(button, Text("Navigate to {title}", title=Text(title)), "setAccessibleName")
        self.nav_layout.addWidget(button)
        self.buttons[key] = button
        return button

    def finish(self) -> None:
        self.layout.addWidget(label("LOCAL BY DESIGN", "eyebrow"))
        self.layout.addWidget(label(f"NEXUS AI / {__version__}", "sidebarCaption"))
        self.layout.addWidget(label("RGB & fan writes locked", "sidebarCaption"))


class SectionHeader(QWidget):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        titles = QVBoxLayout()
        titles.addWidget(label(title, "pageTitle"))
        titles.addWidget(label(subtitle))
        row.addLayout(titles, 1)
