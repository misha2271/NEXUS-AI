"""Shared dark Qt Widgets theme."""

STYLE = """
QWidget { background: #0c1017; color: #e6eaf2; font-family: 'Segoe UI', sans-serif;
          font-size: 13px; }
QLabel { background: transparent; }
QLabel#pageTitle { font-size: 29px; font-weight: 700; letter-spacing: -1px; }
QLabel#brand { font-size: 24px; font-weight: 800; color: #8ce0c4; }
QLabel#muted, QLabel#sidebarCaption { color: #919caf; font-size: 12px; }
QLabel#eyebrow { color: #8ce0c4; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QLabel#lead { font-size: 18px; color: #b8c3d5; }
QLabel#body { font-size: 15px; color: #b8c3d5; }
QLabel#unavailable { color: #dfbb86; font-weight: 600; }
QLabel#metricValue { font-size: 22px; font-weight: 600; }
QLabel#breadcrumb { color: #919caf; font-size: 11px; letter-spacing: 1px; }
QFrame#sidebar { background: #10161f; border-right: 1px solid #242e3a; }
QFrame#panel { background: #131b26; border: 1px solid #293443; border-radius: 12px; }
QFrame#panel QLabel, QFrame#panel QWidget { background: transparent; }
QPlainTextEdit, QLineEdit, QComboBox { background: #101720; border: 1px solid #334153;
    border-radius: 8px; padding: 10px; selection-background-color: #345c60; }
QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus { border-color: #8ce0c4; }
QPlainTextEdit#transcript { background: #111923; padding: 20px; font-size: 15px; }
QComboBox::drop-down { border: 0; width: 24px; }
QPushButton { background: #202c3b; border: 1px solid #334153; border-radius: 7px;
              padding: 9px 14px; font-weight: 500; }
QPushButton:hover { background: #2b3b4c; border-color: #657c92; }
QPushButton:focus { border-color: #8ce0c4; }
QPushButton#primary { background: #8ce0c4; color: #0c211c; border-color: #8ce0c4;
                      font-weight: 700; }
QPushButton#primary:hover { background: #b0efd9; }
QPushButton#primary:disabled { color: #69798d; background: #151e2a; border-color: #273343; }
QPushButton:disabled { color: #69798d; background: #151e2a; border-color: #273343; }
QPushButton#nav { text-align: left; background: transparent; border: 0;
                 color: #9ba9bb; padding: 12px; font-size: 13px; }
QPushButton#nav:checked { background: #233b3b; color: #a4f0d6; }
QPushButton#nav:hover { background: #1c2a37; color: #e6eaf2; }
QProgressBar { background: #263344; border: 0; border-radius: 3px; height: 5px; }
QProgressBar::chunk { background: #8ce0c4; border-radius: 3px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: #111923; width: 7px; border: 0; }
QScrollBar::handle:vertical { background: #3b4c60; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #253345; color: #e6eaf2; border: 1px solid #63738a; padding: 6px; }
"""
