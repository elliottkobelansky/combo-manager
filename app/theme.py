"""Look of the app: the Sun Valley theme (sv-ttk package) in light or dark, or a similar built-in fallback.

apply(root, mode) sets the theme and returns the palette (colours for the parts ttk doesn't draw: the output panel,
its highlighted lines, hint text and the calendar pop-up).
"""
import sys
from tkinter import font as tkfont
from tkinter import ttk

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

# Accent colours are Sun Valley's own blues, so the buttons, the selection and the calendar all match.
PALETTES = {
    "light": dict(bg="#FAFAFA", panel="#FFFFFF", text="#1C1C1E", muted="#6B6B76", border="#E3E3E8",
                  warn="#B25E00", bad="#D11A2A", good="#1F8A4C", accent="#005FB8", accent_text="#FFFFFF",
                  band="#EEF1F6"),
    "dark": dict(bg="#1C1C1C", panel="#232326", text="#ECECF1", muted="#A0A0AB", border="#3A3A40",
                 warn="#F0A54A", bad="#FF6B6B", good="#4CD787", accent="#57C8FF", accent_text="#1C1C1C",
                 band="#2C2D33"),
}


def ui_font():
    if sys.platform.startswith("win"):
        return "Segoe UI"
    if sys.platform == "darwin":
        return "Helvetica Neue"
    return tkfont.nametofont("TkDefaultFont").actual("family")


def mono_font():
    if sys.platform.startswith("win"):
        return "Cascadia Mono" if "Cascadia Mono" in tkfont.families() else "Consolas"
    if sys.platform == "darwin":
        return "Menlo"
    return tkfont.nametofont("TkFixedFont").actual("family")


def _unstamp_labels(widget):
    """Sun Valley's theme switch calls tk_setPalette, which writes its text colour into every existing ttk label and
    so overrides the label styles (grey hints, blue step titles and links). Clearing it lets the styles show."""
    for child in widget.winfo_children():
        if child.winfo_class() == "TLabel":
            child.configure(foreground="")
        _unstamp_labels(child)


def apply(root, mode="light"):
    mode = mode if mode in PALETTES else "light"
    p = PALETTES[mode]
    style = ttk.Style(root)
    if sv_ttk is not None:
        if not getattr(root, "_unstamp_bound", False):    # after the palette pass (it runs on the same event)
            root.bind("<<ThemeChanged>>", lambda e: root.after_idle(_unstamp_labels, root), add="+")
            root._unstamp_bound = True
        sv_ttk.set_theme(mode)
    else:                                              # fallback: the plain 'clam' theme, recoloured
        style.theme_use("clam")
        style.configure(".", background=p["bg"], foreground=p["text"], fieldbackground=p["panel"],
                        bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"])
        style.configure("TButton", padding=(12, 6), background=p["panel"])
        style.map("TButton", background=[("active", p["border"])])
        style.configure("Accent.TButton", background=p["accent"], foreground=p["accent_text"])
        style.map("Accent.TButton", background=[("active", p["accent"]), ("disabled", p["border"])])
        style.configure("Card.TFrame", background=p["panel"], relief="solid", borderwidth=1)
        style.configure("TNotebook.Tab", padding=(14, 6))
        style.configure("Treeview", background=p["panel"], fieldbackground=p["panel"], foreground=p["text"],
                        rowheight=26)
        root.configure(background=p["bg"])
    family = ui_font()
    style.configure("Title.TLabel", font=(family, 18, "bold"))
    style.configure("Sub.TLabel", font=(family, 10), foreground=p["muted"])
    style.configure("Hint.TLabel", font=(family, 9), foreground=p["muted"])
    style.configure("CardTitle.TLabel", font=(family, 12, "bold"))
    style.configure("Link.TLabel", font=(family, 11), foreground=p["accent"])
    style.configure("Step.TLabel", font=(family, 12, "bold"), foreground=p["accent"])
    style.configure("Big.Accent.TButton", font=(family, 11, "bold"), padding=(18, 8))
    root.option_add("*Toplevel.background", p["bg"])
    return p


def popup(menu, x, y):
    """Shows a pop-up menu at (x, y). It keeps Tk's mouse grab, so on Linux a click anywhere else closes it (the
    usual 'try: tk_popup / finally: grab_release' recipe left it stuck open there); Escape closes it too."""
    menu.bind("<Escape>", lambda _: menu.unpost())
    menu.tk_popup(x, y)


def calendar_colors(p):
    """Keyword arguments for tkcalendar.Calendar so the pop-up matches the theme."""
    return dict(background=p["accent"], foreground=p["accent_text"], headersbackground=p["panel"],
                headersforeground=p["muted"], normalbackground=p["panel"], normalforeground=p["text"],
                weekendbackground=p["panel"], weekendforeground=p["text"], othermonthbackground=p["bg"],
                othermonthforeground=p["muted"], othermonthwebackground=p["bg"], othermonthweforeground=p["muted"],
                selectbackground=p["accent"], selectforeground=p["accent_text"], bordercolor=p["border"],
                font=(ui_font(), 10))
