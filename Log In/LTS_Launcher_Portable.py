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
# PROGRAMS
# =========================================================

PROGRAMS = {
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

# =========================================================
# LOAD USERS
# =========================================================

def load_users():

    if not os.path.exists(USER_DB):

        default_users = {
            "admin": {
                "password": "1234",
                "role": "admin"
            }
        }

        with open(USER_DB, "w") as f:
            json.dump(default_users, f, indent=4)

    with open(USER_DB, "r") as f:
        return json.load(f)

# =========================================================
# SAVE USERS
# =========================================================

def save_users(users):

    with open(USER_DB, "w") as f:
        json.dump(users, f, indent=4)

# =========================================================
# RUN PROGRAM
# =========================================================

def run_program(path, name):

    try:

        if not os.path.exists(path):
            messagebox.showerror(
                "Error",
                f"Program not found:\n\n{name}"
            )
            return

        folder = os.path.dirname(path)

        subprocess.Popen(
            [PYTHON, path],
            cwd=folder
        )

        status_label.config(
            text=f"Running: {name}"
        )

    except Exception as e:

        messagebox.showerror(
            "Launch Error",
            str(e)
        )

# =========================================================
# VERSION INFO WINDOW
# =========================================================

def show_version():

    version_window = tk.Toplevel()

    version_window.title("System Version Information")
    version_window.geometry("600x400")

    txt = scrolledtext.ScrolledText(
        version_window,
        font=("Consolas", 10)
    )

    txt.pack(fill="both", expand=True)

    if os.path.exists(VERSION_FILE):

        with open(VERSION_FILE, "r") as f:
            txt.insert("1.0", f.read())

    else:

        txt.insert(
            "1.0",
            "version.txt not found"
        )

    txt.config(state="disabled")

# =========================================================
# REGISTER USER
# =========================================================

def register_user():

    reg = tk.Toplevel()

    reg.title("Register User")
    reg.geometry("350x350")

    tk.Label(reg, text="New Username").pack(pady=5)
    new_user = tk.Entry(reg)
    new_user.pack()

    tk.Label(reg, text="New Password").pack(pady=5)
    new_pass = tk.Entry(reg, show="*")
    new_pass.pack()

    tk.Label(reg, text="Admin Password").pack(pady=5)
    admin_pass = tk.Entry(reg, show="*")
    admin_pass.pack()

    def create_user():

        users = load_users()

        username = new_user.get().strip()
        password = new_pass.get().strip()
        adminpw = admin_pass.get().strip()

        if username == "" or password == "":
            messagebox.showerror(
                "Error",
                "Fields cannot be empty"
            )
            return

        if "admin" not in users:
            messagebox.showerror(
                "Error",
                "Admin account missing"
            )
            return

        if users["admin"]["password"] != adminpw:
            messagebox.showerror(
                "Error",
                "Invalid admin password"
            )
            return

        if username in users:
            messagebox.showerror(
                "Error",
                "Username already exists"
            )
            return

        users[username] = {
            "password": password,
            "role": "operator"
        }

        save_users(users)

        messagebox.showinfo(
            "Success",
            "User registered successfully"
        )

        reg.destroy()

    tk.Button(
        reg,
        text="Register",
        command=create_user,
        bg="green",
        fg="white",
        width=20
    ).pack(pady=20)

# =========================================================
# LOGIN WINDOW
# =========================================================

def login_screen():

    login = tk.Tk()

    login.title("BMS Lot Tracking System")
    login.geometry("400x350")
    login.configure(bg="#F0F0F0")

    tk.Label(
        login,
        text="BMS LOT TRACKING SYSTEM",
        font=("Arial", 16, "bold"),
        bg="#F0F0F0"
    ).pack(pady=20)

    tk.Label(
        login,
        text="Username",
        bg="#F0F0F0"
    ).pack()

    user_entry = tk.Entry(login, width=30)
    user_entry.pack()

    tk.Label(
        login,
        text="Password",
        bg="#F0F0F0"
    ).pack(pady=(10, 0))

    pass_entry = tk.Entry(
        login,
        show="*",
        width=30
    )
    pass_entry.pack()

    # =====================================================
    # LOGIN FUNCTION
    # =====================================================

    def check_login():

        users = load_users()

        username = user_entry.get().strip()
        password = pass_entry.get().strip()

        if username in users:

            if users[username]["password"] == password:

                login.destroy()
                dashboard(username)

                return

        messagebox.showerror(
            "Login Failed",
            "Invalid username or password"
        )

    # =====================================================
    # BUTTONS
    # =====================================================

    tk.Button(
        login,
        text="LOGIN",
        width=25,
        bg="#0078D7",
        fg="white",
        command=check_login
    ).pack(pady=20)

    tk.Button(
        login,
        text="Register User",
        width=25,
        command=register_user
    ).pack(pady=5)

    tk.Button(
        login,
        text="Version Info",
        width=25,
        command=show_version
    ).pack(pady=5)
    login.mainloop()

# =========================================================
# DASHBOARD
# =========================================================

def dashboard(username):

    global status_label

    root = tk.Tk()

    root.title("BMS Lot Tracking System Dashboard")
    root.geometry("900x650")
    root.configure(bg="#EAEAEA")

    # =====================================================
    # HEADER
    # =====================================================

    header = tk.Frame(
        root,
        bg="#003366",
        height=80
    )

    header.pack(fill="x")

    tk.Label(
        header,
        text="BMS LOT TRACKING SYSTEM",
        font=("Arial", 18, "bold"),
        bg="#003366",
        fg="white"
    ).pack(pady=(10, 0))

    tk.Label(
        header,
        text=f"Logged in as: {username}",
        font=("Arial", 10),
        bg="#003366",
        fg="white"
    ).pack()

    # =====================================================
    # PROGRAM BUTTONS
    # =====================================================

    body = tk.Frame(root, bg="#EAEAEA")
    body.pack(pady=20)

    row = 0
    col = 0

    for name, path in PROGRAMS.items():

        btn = tk.Button(
            body,
            text=name,
            width=35,
            height=3,
            bg="white",
            font=("Arial", 10, "bold"),
            command=lambda p=path, n=name: run_program(p, n)
        )

        btn.grid(
            row=row,
            column=col,
            padx=10,
            pady=10
        )

        col += 1

        if col > 1:
            col = 0
            row += 1

    # =====================================================
    # STATUS BAR
    # =====================================================

    bottom = tk.Frame(root, bg="#D0D0D0")
    bottom.pack(fill="x", side="bottom")

    status_label = tk.Label(
        bottom,
        text="System Ready",
        bg="#D0D0D0",
        font=("Arial", 9)
    )

    status_label.pack(side="left", padx=10)

    tk.Button(
        bottom,
        text="Exit",
        bg="red",
        fg="white",
        command=root.destroy
    ).pack(side="right", padx=10, pady=5)

    root.mainloop()

# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    login_screen()