import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import subprocess
import os
import json
from datetime import datetime

# =========================================================
# PATHS
# =========================================================

PYTHON = r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\python-3.7.7.amd64\python.exe"

USER_DB = r"\\phlsvr08\BMS Data\Lot Tracking System\user login\users.json"

VERSION_FILE = r"\\phlsvr08\BMS Data\Lot Tracking System\version control info\version.txt"

# =========================================================
# THEME (modern flat look)
# =========================================================

COLOR_BG        = "#0f172a"   # app background (slate-900)
COLOR_SURFACE   = "#1e293b"   # cards / panels (slate-800)
COLOR_SURFACE_2 = "#334155"   # hover (slate-700)
COLOR_PRIMARY   = "#2563eb"   # blue-600
COLOR_PRIMARY_H = "#1d4ed8"   # blue-700
COLOR_ACCENT    = "#0ea5e9"   # sky-500
COLOR_DANGER    = "#dc2626"   # red-600
COLOR_DANGER_H  = "#b91c1c"
COLOR_SUCCESS   = "#16a34a"   # green-600
COLOR_TEXT      = "#f8fafc"   # near white
COLOR_MUTED     = "#94a3b8"   # slate-400
COLOR_ADMIN     = "#f59e0b"   # amber-500 (admin badge)

FONT_TITLE  = ("Segoe UI Semibold", 20)
FONT_H2     = ("Segoe UI Semibold", 13)
FONT_BODY   = ("Segoe UI", 10)
FONT_SMALL  = ("Segoe UI", 9)
FONT_CARD   = ("Segoe UI Semibold", 11)

# =========================================================
# PROGRAMS
#   PROCESS_PROGRAMS  -> visible to EVERYONE (operator + admin)
#   ADMIN_PROGRAMS    -> visible to ADMIN ONLY
# =========================================================

PROCESS_PROGRAMS = {
    "Lot Entry": r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\LTS_Programs\Lot Entry\OCR_BMS_Lot_Entry_System.py",

    "Laser Marking & OCR Reader":
    r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\LTS_Programs\Laser Marking & OCR Reader\Laser_Marking_and_OCR.py",

    "MR Chip Alignment Measurement":
    r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\LTS_Programs\MR Chip Alignment Measurement\OCR_MR_Chip_Alignment_Measurement.py",

    "MR Chip Height Measurement":
    r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\LTS_Programs\MR Chip Height Measurement\OCR_MR_Chip_Height_Measurement.py",

    "SBB & Cable Resistance Measurement":
    r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\LTS_Programs\Resistance Measurement\OCR_Resistance_Measurement.py",

    "QA Inspection 1 & 2":
    r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\LTS_Programs\QA Inspection 1 & 2\OCR_QA_Inspection.py",

    "Cable Soldering & Labelling":
    r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\LTS_Programs\Cable Soldering & Labelling\Cable_Soldering.py",

    "Inductance & Resistance Measurement":
    r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\LTS_Programs\Inductance & Resistance Measurement\Inductance_and_Resistance_Measurement.py",

    "QA Final Inspection":
    r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\LTS_Programs\QA Final Inspection\OCR_QA_Image_Capturing.py"
}

# Admin-only external programs. Add real paths here as needed.
ADMIN_PROGRAMS = {
    # "Data Report Generator":
    # r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\LTS_Programs\Admin\Report_Generator.py",
    # "Database Maintenance":
    # r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\LTS_Programs\Admin\DB_Maintenance.py",
}

# =========================================================
# USER DATABASE
# =========================================================

def load_users():
    try:
        if not os.path.exists(USER_DB):
            default_users = {
                "admin": {"password": "1234", "role": "admin"}
            }
            os.makedirs(os.path.dirname(USER_DB), exist_ok=True)
            with open(USER_DB, "w") as f:
                json.dump(default_users, f, indent=4)

        with open(USER_DB, "r") as f:
            return json.load(f)

    except Exception as e:
        messagebox.showerror("User Database Error",
                             "Could not read user database:\n\n" + str(e))
        return {}


def save_users(users):
    try:
        os.makedirs(os.path.dirname(USER_DB), exist_ok=True)
        with open(USER_DB, "w") as f:
            json.dump(users, f, indent=4)
        return True
    except Exception as e:
        messagebox.showerror("Save Error", "Could not save users:\n\n" + str(e))
        return False


# =========================================================
# STYLED WIDGET HELPERS
# =========================================================

def style_button(btn, bg, hover, fg=COLOR_TEXT):
    """Give a tk.Button a flat modern look with hover feedback."""
    btn.configure(
        bg=bg, fg=fg,
        activebackground=hover, activeforeground=fg,
        relief="flat", bd=0, cursor="hand2",
        highlightthickness=0, font=FONT_BODY
    )
    btn.bind("<Enter>", lambda e: btn.configure(bg=hover))
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))


def make_entry(parent, show=None):
    return tk.Entry(
        parent, show=show, font=FONT_BODY,
        bg=COLOR_SURFACE_2, fg=COLOR_TEXT,
        insertbackground=COLOR_TEXT,
        relief="flat", bd=0, highlightthickness=1,
        highlightbackground=COLOR_SURFACE_2,
        highlightcolor=COLOR_PRIMARY
    )


def center_window(win, w, h):
    win.update_idletasks()
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry("%dx%d+%d+%d" % (w, h, x, y))


# =========================================================
# RUN PROGRAM
# =========================================================

def run_program(path, name, status_setter=None):
    try:
        if not os.path.exists(path):
            messagebox.showerror("Error", "Program not found:\n\n%s\n%s" % (name, path))
            return

        folder = os.path.dirname(path)
        subprocess.Popen([PYTHON, path], cwd=folder)

        if status_setter:
            status_setter("Launched:  %s   (%s)" % (name, datetime.now().strftime("%H:%M:%S")))

    except Exception as e:
        messagebox.showerror("Launch Error", str(e))


# =========================================================
# VERSION INFO WINDOW  (admin tool)
# =========================================================

def show_version(parent=None):
    win = tk.Toplevel(parent)
    win.title("System Version Information")
    win.configure(bg=COLOR_BG)
    center_window(win, 640, 440)

    tk.Label(win, text="System Version Information", font=FONT_H2,
             bg=COLOR_BG, fg=COLOR_TEXT).pack(anchor="w", padx=20, pady=(18, 8))

    txt = scrolledtext.ScrolledText(
        win, font=("Consolas", 10),
        bg=COLOR_SURFACE, fg=COLOR_TEXT,
        insertbackground=COLOR_TEXT, relief="flat", bd=0
    )
    txt.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, "r") as f:
                txt.insert("1.0", f.read())
        except Exception as e:
            txt.insert("1.0", "Could not read version file:\n" + str(e))
    else:
        txt.insert("1.0", "version.txt not found")

    txt.config(state="disabled")


# =========================================================
# REGISTER USER  (admin tool)
# =========================================================

def register_user(parent=None):
    reg = tk.Toplevel(parent)
    reg.title("Register New User")
    reg.configure(bg=COLOR_BG)
    center_window(reg, 380, 470)

    tk.Label(reg, text="Register New User", font=FONT_H2,
             bg=COLOR_BG, fg=COLOR_TEXT).pack(pady=(24, 4))
    tk.Label(reg, text="Admin authorisation required", font=FONT_SMALL,
             bg=COLOR_BG, fg=COLOR_MUTED).pack(pady=(0, 16))

    def field(label):
        tk.Label(reg, text=label, font=FONT_SMALL,
                 bg=COLOR_BG, fg=COLOR_MUTED).pack(anchor="w", padx=40)
        e = make_entry(reg, show="*" if "Password" in label else None)
        e.pack(fill="x", padx=40, ipady=6, pady=(2, 12))
        return e

    new_user = field("New Username")
    new_pass = field("New Password")

    tk.Label(reg, text="Role", font=FONT_SMALL,
             bg=COLOR_BG, fg=COLOR_MUTED).pack(anchor="w", padx=40)
    role_var = tk.StringVar(value="operator")
    role_box = ttk.Combobox(reg, textvariable=role_var,
                            values=["operator", "admin"], state="readonly")
    role_box.pack(fill="x", padx=40, ipady=3, pady=(2, 12))

    admin_pass = field("Admin Password")

    def create_user():
        users = load_users()
        username = new_user.get().strip()
        password = new_pass.get().strip()
        adminpw = admin_pass.get().strip()

        if not username or not password:
            messagebox.showerror("Error", "Username and password cannot be empty")
            return
        if "admin" not in users:
            messagebox.showerror("Error", "Admin account missing")
            return
        if users["admin"]["password"] != adminpw:
            messagebox.showerror("Error", "Invalid admin password")
            return
        if username in users:
            messagebox.showerror("Error", "Username already exists")
            return

        users[username] = {"password": password, "role": role_var.get()}
        if save_users(users):
            messagebox.showinfo("Success",
                                "User '%s' registered as %s" % (username, role_var.get()))
            reg.destroy()

    b = tk.Button(reg, text="Register User", command=create_user)
    style_button(b, COLOR_SUCCESS, "#15803d")
    b.pack(fill="x", padx=40, ipady=10, pady=(10, 8))


# =========================================================
# USER MANAGEMENT  (admin tool)
# =========================================================

def manage_users(parent=None):
    win = tk.Toplevel(parent)
    win.title("User Management")
    win.configure(bg=COLOR_BG)
    center_window(win, 560, 470)

    tk.Label(win, text="User Management", font=FONT_H2,
             bg=COLOR_BG, fg=COLOR_TEXT).pack(anchor="w", padx=20, pady=(18, 10))

    style = ttk.Style()
    style.configure("Treeview", background=COLOR_SURFACE, fieldbackground=COLOR_SURFACE,
                    foreground=COLOR_TEXT, rowheight=28, font=FONT_BODY, borderwidth=0)
    style.configure("Treeview.Heading", font=FONT_SMALL)
    style.map("Treeview", background=[("selected", COLOR_PRIMARY)])

    tree = ttk.Treeview(win, columns=("username", "role"), show="headings", height=10)
    tree.heading("username", text="Username")
    tree.heading("role", text="Role")
    tree.column("username", width=320)
    tree.column("role", width=160, anchor="center")
    tree.pack(fill="both", expand=True, padx=20)

    def refresh():
        tree.delete(*tree.get_children())
        for name, info in load_users().items():
            tree.insert("", "end", values=(name, info.get("role", "operator")))

    def delete_selected():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("Delete User", "Select a user first")
            return
        username = tree.item(sel[0])["values"][0]
        if username == "admin":
            messagebox.showerror("Error", "The main admin account cannot be deleted")
            return
        if messagebox.askyesno("Confirm", "Delete user '%s'?" % username):
            users = load_users()
            users.pop(username, None)
            if save_users(users):
                refresh()

    btnbar = tk.Frame(win, bg=COLOR_BG)
    btnbar.pack(fill="x", padx=20, pady=16)

    b1 = tk.Button(btnbar, text="+ Add User", command=lambda: register_user(win))
    style_button(b1, COLOR_PRIMARY, COLOR_PRIMARY_H)
    b1.pack(side="left", ipadx=10, ipady=6)

    b2 = tk.Button(btnbar, text="Delete User", command=delete_selected)
    style_button(b2, COLOR_DANGER, COLOR_DANGER_H)
    b2.pack(side="left", padx=8, ipadx=10, ipady=6)

    b3 = tk.Button(btnbar, text="Refresh", command=refresh)
    style_button(b3, COLOR_SURFACE_2, COLOR_SURFACE)
    b3.pack(side="left", ipadx=10, ipady=6)

    refresh()


# =========================================================
# LOGIN WINDOW
# =========================================================

def login_screen():
    login = tk.Tk()
    login.title("BMS Lot Tracking System")
    login.configure(bg=COLOR_BG)
    center_window(login, 420, 520)

    card = tk.Frame(login, bg=COLOR_SURFACE)
    card.place(relx=0.5, rely=0.5, anchor="center", width=340, height=430)

    tk.Label(card, text="BMS", font=("Segoe UI Black", 30),
             bg=COLOR_SURFACE, fg=COLOR_ACCENT).pack(pady=(28, 0))
    tk.Label(card, text="LOT TRACKING SYSTEM", font=("Segoe UI Semibold", 12),
             bg=COLOR_SURFACE, fg=COLOR_TEXT).pack()
    tk.Label(card, text="Please sign in to continue", font=FONT_SMALL,
             bg=COLOR_SURFACE, fg=COLOR_MUTED).pack(pady=(4, 20))

    tk.Label(card, text="Username", font=FONT_SMALL,
             bg=COLOR_SURFACE, fg=COLOR_MUTED).pack(anchor="w", padx=30)
    user_entry = make_entry(card)
    user_entry.pack(fill="x", padx=30, ipady=7, pady=(2, 12))

    tk.Label(card, text="Password", font=FONT_SMALL,
             bg=COLOR_SURFACE, fg=COLOR_MUTED).pack(anchor="w", padx=30)
    pass_entry = make_entry(card, show="\u2022")
    pass_entry.pack(fill="x", padx=30, ipady=7, pady=(2, 18))

    def check_login():
        users = load_users()
        username = user_entry.get().strip()
        password = pass_entry.get().strip()

        if username in users and users[username]["password"] == password:
            role = users[username].get("role", "operator")
            login.destroy()
            dashboard(username, role)
            return

        messagebox.showerror("Login Failed", "Invalid username or password")

    login_btn = tk.Button(card, text="SIGN IN", command=check_login)
    style_button(login_btn, COLOR_PRIMARY, COLOR_PRIMARY_H)
    login_btn.configure(font=("Segoe UI Semibold", 10))
    login_btn.pack(fill="x", padx=30, ipady=9)

    ver_btn = tk.Button(card, text="Version Info", command=lambda: show_version(login))
    style_button(ver_btn, COLOR_SURFACE, COLOR_SURFACE_2, fg=COLOR_MUTED)
    ver_btn.pack(pady=(14, 0))

    user_entry.focus_set()
    login.bind("<Return>", lambda e: check_login())
    login.mainloop()


# =========================================================
# DASHBOARD
# =========================================================

def dashboard(username, role):
    is_admin = (role == "admin")

    root = tk.Tk()
    root.title("BMS Lot Tracking System")
    root.configure(bg=COLOR_BG)
    center_window(root, 1000, 700)
    root.minsize(860, 600)

    # ---------------- Header ----------------
    header = tk.Frame(root, bg=COLOR_SURFACE, height=76)
    header.pack(fill="x")
    header.pack_propagate(False)

    left = tk.Frame(header, bg=COLOR_SURFACE)
    left.pack(side="left", padx=24)
    tk.Label(left, text="BMS Lot Tracking System", font=FONT_TITLE,
             bg=COLOR_SURFACE, fg=COLOR_TEXT).pack(anchor="w", pady=(14, 0))
    tk.Label(left, text="%d process modules available" % len(PROCESS_PROGRAMS),
             font=FONT_SMALL, bg=COLOR_SURFACE, fg=COLOR_MUTED).pack(anchor="w")

    right = tk.Frame(header, bg=COLOR_SURFACE)
    right.pack(side="right", padx=24)

    badge_color = COLOR_ADMIN if is_admin else COLOR_ACCENT
    tk.Label(right, text="  %s  " % role.upper(), font=("Segoe UI Semibold", 9),
             bg=badge_color, fg="#0f172a").pack(side="right", pady=(26, 0))
    tk.Label(right, text="%s   " % username, font=FONT_BODY,
             bg=COLOR_SURFACE, fg=COLOR_TEXT).pack(side="right", pady=(24, 0))

    # ---------------- Scrollable body ----------------
    body_wrap = tk.Frame(root, bg=COLOR_BG)
    body_wrap.pack(fill="both", expand=True)

    canvas = tk.Canvas(body_wrap, bg=COLOR_BG, highlightthickness=0)
    scrollbar = ttk.Scrollbar(body_wrap, orient="vertical", command=canvas.yview)
    body = tk.Frame(canvas, bg=COLOR_BG)

    body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    inner_id = canvas.create_window((0, 0), window=body, anchor="nw")
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(inner_id, width=e.width))
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    canvas.bind_all("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    # ---------------- Status bar ----------------
    bottom = tk.Frame(root, bg=COLOR_SURFACE, height=40)
    bottom.pack(fill="x", side="bottom")
    bottom.pack_propagate(False)

    status_var = tk.StringVar(value="System Ready")
    tk.Label(bottom, textvariable=status_var, bg=COLOR_SURFACE, fg=COLOR_MUTED,
             font=FONT_SMALL).pack(side="left", padx=16)

    def set_status(text):
        status_var.set(text)

    exit_btn = tk.Button(bottom, text="Exit", command=root.destroy)
    style_button(exit_btn, COLOR_DANGER, COLOR_DANGER_H)
    exit_btn.pack(side="right", padx=12, pady=6, ipadx=12)

    logout_btn = tk.Button(bottom, text="Log Out",
                           command=lambda: (root.destroy(), login_screen()))
    style_button(logout_btn, COLOR_SURFACE_2, COLOR_SURFACE)
    logout_btn.pack(side="right", padx=4, pady=6, ipadx=10)

    # ---------------- Helpers ----------------
    def section_title(text, subtitle=""):
        f = tk.Frame(body, bg=COLOR_BG)
        f.pack(fill="x", padx=28, pady=(22, 6))
        tk.Label(f, text=text, font=FONT_H2, bg=COLOR_BG, fg=COLOR_TEXT).pack(anchor="w")
        if subtitle:
            tk.Label(f, text=subtitle, font=FONT_SMALL,
                     bg=COLOR_BG, fg=COLOR_MUTED).pack(anchor="w")

    def make_card(grid, name, path, accent, r, c):
        card = tk.Frame(grid, bg=COLOR_SURFACE, cursor="hand2")
        card.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")

        tk.Frame(card, bg=accent, width=5).pack(side="left", fill="y")

        inner = tk.Frame(card, bg=COLOR_SURFACE)
        inner.pack(side="left", fill="both", expand=True, padx=14, pady=14)

        lbl = tk.Label(inner, text=name, font=FONT_CARD, bg=COLOR_SURFACE,
                       fg=COLOR_TEXT, wraplength=210, justify="left", anchor="w")
        lbl.pack(anchor="w")
        hint = tk.Label(inner, text="Click to launch  \u2192", font=FONT_SMALL,
                        bg=COLOR_SURFACE, fg=COLOR_MUTED)
        hint.pack(anchor="w", pady=(8, 0))

        widgets = [card, inner, lbl, hint]

        def on_enter(_):
            for w in widgets:
                w.configure(bg=COLOR_SURFACE_2)
            hint.configure(bg=COLOR_SURFACE_2, fg=accent)

        def on_leave(_):
            for w in widgets:
                w.configure(bg=COLOR_SURFACE)
            hint.configure(fg=COLOR_MUTED)

        def on_click(_):
            run_program(path, name, set_status)

        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)

    def program_grid(items, accent):
        grid = tk.Frame(body, bg=COLOR_BG)
        grid.pack(fill="x", padx=20)
        cols = 3
        for i in range(cols):
            grid.grid_columnconfigure(i, weight=1, uniform="cards")
        for idx, (name, path) in enumerate(items):
            r, c = divmod(idx, cols)
            make_card(grid, name, path, accent, r, c)

    def tool_grid(tools, accent):
        grid = tk.Frame(body, bg=COLOR_BG)
        grid.pack(fill="x", padx=20, pady=(0, 10))
        cols = 3
        for i in range(cols):
            grid.grid_columnconfigure(i, weight=1, uniform="tools")
        for idx, (label, cmd) in enumerate(tools):
            r, c = divmod(idx, cols)
            b = tk.Button(grid, text=label, command=cmd)
            style_button(b, COLOR_SURFACE, COLOR_SURFACE_2)
            b.configure(font=FONT_CARD, anchor="w", padx=16,
                        highlightthickness=2, highlightbackground=accent)
            b.grid(row=r, column=c, padx=8, pady=8, ipady=18, sticky="nsew")

    # ---------------- Process programs (EVERYONE) ----------------
    section_title("Process Programs", "Manufacturing and inspection modules")
    program_grid(list(PROCESS_PROGRAMS.items()), COLOR_ACCENT)

    # ---------------- Admin-only content ----------------
    if is_admin:
        if ADMIN_PROGRAMS:
            section_title("Admin Programs", "Restricted tools \u2014 administrators only")
            program_grid(list(ADMIN_PROGRAMS.items()), COLOR_ADMIN)

        section_title("Administration",
                      "User accounts and system management \u2014 administrators only")
        tool_grid([
            ("Manage Users", lambda: manage_users(root)),
            ("Register User", lambda: register_user(root)),
            ("Version Info", lambda: show_version(root)),
        ], COLOR_ADMIN)

    tk.Frame(body, bg=COLOR_BG, height=20).pack()

    root.mainloop()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    login_screen()
