"""Styles for the Jet TUI."""

STYLES = """
Screen {
    background: #000000;
    scrollbar-size: 0 0;
}

Container {
    scrollbar-size: 0 0;
}

Static {
    scrollbar-size: 0 0;
}

#header {
    dock: top;
    height: 1;
    background: #000000;
    padding: 0 1;
    margin-bottom: 0;
}

#title {
    text-align: center;
    text-style: bold;
    color: #00ff9f;
    width: 100%;
}

#subtitle {
    text-align: center;
    color: #6272a4;
    width: 100%;
}

#footer {
    dock: bottom;
    height: 1;
    background: #1a1a1a;
    padding: 0 1;
}

#content {
    height: 1fr;
    width: 1fr;
    padding: 0;
    margin: 0;
    scrollbar-size: 0 0;
}

DataTable {
    /* Use the theme's background color */
    width: 1fr;
    min-width: 100%;
    /* Add "%0" after background to make the background fully transparent. */
    background: $background;
    scrollbar-size-horizontal: 0;
    scrollbar-size-vertical: 1;
    scrollbar-background: #0a0a0a;
    scrollbar-color: #333333;
    scrollbar-color-hover: #555555;
    scrollbar-color-active: #666666;
}

DataTable > .datatable--header {
    background: #1a1a1a;
    color: #00ff9f;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #2a2a4a;
}

DataTable:focus > .datatable--cursor {
    background: #3a3a5a;
}

DataTable > .datatable--hover {
    background: #262626;
}

DataTable > .datatable--even-row {
    /* Base Color (Matches the overall app background) */
    background: $background;
}

DataTable > .datatable--odd-row {
    /* Slightly lighter/darker color (A subtle contrast) */
    background: $surface; 
}

.status-running {
    color: #50fa7b;
}

.status-pending {
    color: #f1fa8c;
}

.status-failed {
    color: #ff5555;
}

.status-complete {
    color: #50fa7b;
}

#log-container {
    height: 100%;
    width: 100%;
    background: #000000;
    scrollbar-size: 1 1;
    scrollbar-background: #0a0a0a;
    scrollbar-color: #333333;
    scrollbar-color-hover: #555555;
    scrollbar-color-active: #666666;
}

#log-content {
    width: 100%;
    background: #000000;
    scrollbar-size: 0 0;
}

#describe-container {
    height: 100%;
    width: 100%;
    background: #000000;
    scrollbar-size: 1 1;
    scrollbar-background: #0a0a0a;
    scrollbar-color: #333333;
    scrollbar-color-hover: #555555;
    scrollbar-color-active: #666666;
}

#describe-content {
    width: 100%;
    height: auto;
    background: #000000;
    scrollbar-size: 0 0;
}

.header-box {
    height: 3;
    border: solid #444444;
    padding: 0 2;
    margin-bottom: 1;
}

.header-title {
    text-align: center;
    text-style: bold;
}

LoadingIndicator {
    height: 100%;
    width: 100%;
}

#search-input {
    dock: bottom;
    height: 1;
    display: none;
}

#search-input.visible {
    display: block;
}

#confirm-dialog {
    align: center middle;
    width: 50;
    height: 7;
    border: solid #ff5555;
    background: #1a1a1a;
    padding: 1 2;
}

#confirm-message {
    text-align: center;
    color: #f8f8f2;
    margin-bottom: 1;
}

#confirm-buttons, #btn-container {
    text-align: center;
    width: 100%;
}

#confirm-hint {
    text-align: center;
    color: #666666;
    margin-top: 1;
}

#search-input {
    dock: top;
    height: 1;
    background: #1a1a1a;
    border: none;
    padding: 0 1;
}

#search-input:focus {
    border: none;
}

Footer {
    background: #1a1a1a;
}

Footer > .footer--key {
    background: #333333;
    color: #00ff9f;
}

Footer > .footer--description {
    color: #f8f8f2;
}

#footer-input {
    dock: bottom;
    height: 1;
    display: none;
    background: #1a1a1a;
    color: #f8f8f2;
    border: none;
    padding: 0 1;
}

#footer-input:focus {
    border: none;
}

RichLog {
    background: #000000;
    color: #f8f8f2;
}
"""