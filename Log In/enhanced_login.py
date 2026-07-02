"""
Enhanced Login System for BMS Lot Tracking System
Role-based authentication with session management
"""

import tkinter as tk
from tkinter import messagebox
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import importlib.util

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import config module using importlib to handle spaces in directory names
def import_module_from_path(module_name, file_path):
    """Import a module from a file path"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Get base directory
BASE_DIR = Path(__file__).parent.parent

# Import configuration
system_config = import_module_from_path(
    "system_config",
    BASE_DIR / "config" / "system_config.py"
)

# Import needed items from config
USER_DB = system_config.USER_DB
COLOR_BG = system_config.COLOR_BG
COLOR_SURFACE = system_config.COLOR_SURFACE
COLOR_SURFACE_2 = system_config.COLOR_SURFACE_2
COLOR_PRIMARY = system_config.COLOR_PRIMARY
COLOR_PRIMARY_H = system_config.COLOR_PRIMARY_H
COLOR_ACCENT = system_config.COLOR_ACCENT
COLOR_TEXT = system_config.COLOR_TEXT
COLOR_MUTED = system_config.COLOR_MUTED
FONT_TITLE = system_config.FONT_TITLE
FONT_H2 = system_config.FONT_H2
FONT_BODY = system_config.FONT_BODY
FONT_SMALL = system_config.FONT_SMALL
ROLE_OPERATOR = system_config.ROLE_OPERATOR
ROLE_ADMIN = system_config.ROLE_ADMIN


class UserManager:
    """Manage user authentication and authorization"""
    
    def __init__(self):
        self.user_db = USER_DB
        self._ensure_user_db_exists()
    
    def _ensure_user_db_exists(self):
        """Create default user database if it doesn't exist"""
        if not os.path.exists(self.user_db):
            default_users = {
                "admin": {
                    "password": "admin123",
                    "role": ROLE_ADMIN,
                    "full_name": "System Administrator",
                    "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                "operator": {
                    "password": "operator123",
                    "role": ROLE_OPERATOR,
                    "full_name": "Default Operator",
                    "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }
            os.makedirs(os.path.dirname(self.user_db), exist_ok=True)
            with open(self.user_db, "w") as f:
                json.dump(default_users, f, indent=4)
    
    def load_users(self):
        """Load users from database"""
        try:
            with open(self.user_db, "r") as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror("User Database Error",
                               f"Could not read user database:\n\n{str(e)}")
            return {}
    
    def save_users(self, users):
        """Save users to database"""
        try:
            os.makedirs(os.path.dirname(self.user_db), exist_ok=True)
            with open(self.user_db, "w") as f:
                json.dump(users, f, indent=4)
            return True
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save users:\n\n{str(e)}")
            return False
    
    def authenticate(self, username, password):
        """Authenticate user credentials"""
        users = self.load_users()
        
        if username in users and users[username]["password"] == password:
            user_data = users[username].copy()
            user_data["username"] = username
            user_data["login_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return True, user_data
        
        return False, None
    
    def register_user(self, username, password, role, full_name, admin_password):
        """Register a new user (requires admin password)"""
        users = self.load_users()
        
        # Verify admin password
        if "admin" not in users or users["admin"]["password"] != admin_password:
            return False, "Invalid admin password"
        
        # Check if username already exists
        if username in users:
            return False, "Username already exists"
        
        # Create new user
        users[username] = {
            "password": password,
            "role": role,
            "full_name": full_name,
            "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if self.save_users(users):
            return True, "User registered successfully"
        else:
            return False, "Failed to save user"


class LoginWindow:
    """Enhanced login window with modern UI"""
    
    def __init__(self):
        self.user_manager = UserManager()
        self.root = tk.Tk()
        self.root.title("BMS Lot Tracking System - Login")
        self.root.configure(bg=COLOR_BG)
        self.center_window(460, 580)
        self.user_data = None
        
        self.create_ui()
    
    def center_window(self, width, height):
        """Center window on screen"""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def make_entry(self, parent, show=None):
        """Create styled entry widget"""
        return tk.Entry(
            parent, show=show, font=FONT_BODY,
            bg=COLOR_SURFACE_2, fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=COLOR_SURFACE_2,
            highlightcolor=COLOR_PRIMARY
        )
    
    def style_button(self, btn, bg, hover, fg=COLOR_TEXT):
        """Style button with hover effect"""
        btn.configure(
            bg=bg, fg=fg,
            activebackground=hover, activeforeground=fg,
            relief="flat", bd=0, cursor="hand2",
            highlightthickness=0, font=FONT_BODY
        )
        btn.bind("<Enter>", lambda e: btn.configure(bg=hover))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
    
    def create_ui(self):
        """Create login UI"""
        # Main card
        card = tk.Frame(self.root, bg=COLOR_SURFACE)
        card.place(relx=0.5, rely=0.5, anchor="center", width=380, height=500)
        
        # Logo/Title
        tk.Label(
            card, text="BMS", 
            font=("Segoe UI Black", 32),
            bg=COLOR_SURFACE, fg=COLOR_ACCENT
        ).pack(pady=(32, 0))
        
        tk.Label(
            card, text="LOT TRACKING SYSTEM",
            font=("Segoe UI Semibold", 12),
            bg=COLOR_SURFACE, fg=COLOR_TEXT
        ).pack()
        
        tk.Label(
            card, text="Please sign in to continue",
            font=FONT_SMALL,
            bg=COLOR_SURFACE, fg=COLOR_MUTED
        ).pack(pady=(4, 24))
        
        # Username field
        tk.Label(
            card, text="Username",
            font=FONT_SMALL,
            bg=COLOR_SURFACE, fg=COLOR_MUTED
        ).pack(anchor="w", padx=32)
        
        self.user_entry = self.make_entry(card)
        self.user_entry.pack(fill="x", padx=32, ipady=8, pady=(2, 14))
        
        # Password field
        tk.Label(
            card, text="Password",
            font=FONT_SMALL,
            bg=COLOR_SURFACE, fg=COLOR_MUTED
        ).pack(anchor="w", padx=32)
        
        self.pass_entry = self.make_entry(card, show="●")
        self.pass_entry.pack(fill="x", padx=32, ipady=8, pady=(2, 20))
        
        # Login button
        login_btn = tk.Button(
            card, text="SIGN IN",
            command=self.attempt_login
        )
        self.style_button(login_btn, COLOR_PRIMARY, COLOR_PRIMARY_H)
        login_btn.configure(font=("Segoe UI Semibold", 10))
        login_btn.pack(fill="x", padx=32, ipady=10)
        
        # Status label
        self.status_label = tk.Label(
            card, text="",
            font=FONT_SMALL,
            bg=COLOR_SURFACE, fg=COLOR_MUTED
        )
        self.status_label.pack(pady=(8, 0))
        
        # Info label
        tk.Label(
            card, text="Default login: admin/admin123 or operator/operator123",
            font=("Segoe UI", 8),
            bg=COLOR_SURFACE, fg=COLOR_MUTED
        ).pack(pady=(20, 0))
        
        # Set focus and bind enter key
        self.user_entry.focus_set()
        self.root.bind("<Return>", lambda e: self.attempt_login())
    
    def attempt_login(self):
        """Attempt to log in user"""
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        
        if not username or not password:
            self.status_label.configure(text="Please enter username and password", fg=COLOR_MUTED)
            return
        
        self.status_label.configure(text="Authenticating...", fg=COLOR_ACCENT)
        self.root.update()
        
        success, user_data = self.user_manager.authenticate(username, password)
        
        if success:
            self.user_data = user_data
            self.status_label.configure(text="Login successful!", fg=COLOR_ACCENT)
            self.root.after(500, self.root.destroy)
        else:
            self.status_label.configure(text="Invalid username or password", fg=COLOR_MUTED)
            self.pass_entry.delete(0, tk.END)
    
    def run(self):
        """Run login window"""
        self.root.mainloop()
        return self.user_data


if __name__ == "__main__":
    login_win = LoginWindow()
    user_data = login_win.run()
    
    if user_data:
        print(f"Logged in as: {user_data['username']} ({user_data['role']})")
