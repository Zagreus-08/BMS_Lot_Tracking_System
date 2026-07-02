"""
Main Dashboard for BMS Lot Tracking System
Role-based dashboard with real-time tracking and program launcher
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime
import importlib.util

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import config modules using importlib to handle spaces in directory names
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

database_manager_module = import_module_from_path(
    "database_manager",
    BASE_DIR / "config" / "database_manager.py"
)

# Import needed items from config
PYTHON_EXE = system_config.PYTHON_EXE
PROCESS_PROGRAMS = system_config.PROCESS_PROGRAMS
ADMIN_PROGRAMS = system_config.ADMIN_PROGRAMS
COLOR_BG = system_config.COLOR_BG
COLOR_SURFACE = system_config.COLOR_SURFACE
COLOR_SURFACE_2 = system_config.COLOR_SURFACE_2
COLOR_PRIMARY = system_config.COLOR_PRIMARY
COLOR_PRIMARY_H = system_config.COLOR_PRIMARY_H
COLOR_ACCENT = system_config.COLOR_ACCENT
COLOR_SUCCESS = system_config.COLOR_SUCCESS
COLOR_SUCCESS_H = system_config.COLOR_SUCCESS_H
COLOR_DANGER = system_config.COLOR_DANGER
COLOR_DANGER_H = system_config.COLOR_DANGER_H
COLOR_TEXT = system_config.COLOR_TEXT
COLOR_MUTED = system_config.COLOR_MUTED
COLOR_ADMIN = system_config.COLOR_ADMIN
COLOR_WARNING = system_config.COLOR_WARNING
FONT_TITLE = system_config.FONT_TITLE
FONT_H1 = system_config.FONT_H1
FONT_H2 = system_config.FONT_H2
FONT_BODY = system_config.FONT_BODY
FONT_SMALL = system_config.FONT_SMALL
FONT_CARD = system_config.FONT_CARD
ROLE_OPERATOR = system_config.ROLE_OPERATOR
ROLE_ADMIN = system_config.ROLE_ADMIN

DatabaseManager = database_manager_module.DatabaseManager


class MainDashboard:
    """Main dashboard window with role-based access"""
    
    def __init__(self, user_data):
        self.user_data = user_data
        self.username = user_data['username']
        self.role = user_data['role']
        self.is_admin = (self.role == ROLE_ADMIN)
        
        self.db_manager = DatabaseManager()
        
        self.root = tk.Tk()
        self.root.title("BMS Lot Tracking System - Dashboard")
        self.root.configure(bg=COLOR_BG)
        self.center_window(1400, 900)
        self.root.minsize(1200, 700)
        
        # Current view
        self.current_view = None
        self.content_frame = None
        
        self.create_ui()
        self.show_tracking_view()
    
    def center_window(self, width, height):
        """Center window on screen"""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def create_ui(self):
        """Create main dashboard UI"""
        # Top header bar
        self.create_header()
        
        # Main content area with sidebar
        main_container = tk.Frame(self.root, bg=COLOR_BG)
        main_container.pack(fill="both", expand=True)
        
        # Left sidebar for navigation
        self.create_sidebar(main_container)
        
        # Right content area
        self.content_container = tk.Frame(main_container, bg=COLOR_BG)
        self.content_container.pack(side="right", fill="both", expand=True)
        
        # Bottom status bar
        self.create_status_bar()
    
    def create_header(self):
        """Create top header bar"""
        header = tk.Frame(self.root, bg=COLOR_SURFACE, height=80)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        # Left side - title and stats
        left = tk.Frame(header, bg=COLOR_SURFACE)
        left.pack(side="left", padx=24)
        
        tk.Label(
            left, text="BMS Lot Tracking System",
            font=FONT_TITLE,
            bg=COLOR_SURFACE, fg=COLOR_TEXT
        ).pack(anchor="w", pady=(16, 0))
        
        # Stats
        stats = self.db_manager.get_production_statistics()
        stats_text = f"{stats['total_lots']} lots  •  {stats['in_progress']} in progress  •  {stats['completed']} completed"
        
        tk.Label(
            left, text=stats_text,
            font=FONT_SMALL,
            bg=COLOR_SURFACE, fg=COLOR_MUTED
        ).pack(anchor="w")
        
        # Right side - user info and logout
        right = tk.Frame(header, bg=COLOR_SURFACE)
        right.pack(side="right", padx=24)
        
        # Role badge
        badge_color = COLOR_ADMIN if self.is_admin else COLOR_ACCENT
        tk.Label(
            right, text=f"  {self.role.upper()}  ",
            font=("Segoe UI Semibold", 9),
            bg=badge_color, fg=COLOR_BG
        ).pack(side="right", pady=(28, 0))
        
        # Username
        tk.Label(
            right, text=f"{self.user_data.get('full_name', self.username)}   ",
            font=FONT_BODY,
            bg=COLOR_SURFACE, fg=COLOR_TEXT
        ).pack(side="right", pady=(26, 0))
    
    def create_sidebar(self, parent):
        """Create left navigation sidebar"""
        sidebar = tk.Frame(parent, bg=COLOR_SURFACE, width=260)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        
        # Sidebar title
        tk.Label(
            sidebar, text="Navigation",
            font=FONT_H2,
            bg=COLOR_SURFACE, fg=COLOR_TEXT
        ).pack(pady=(24, 16), padx=20, anchor="w")
        
        # Navigation buttons
        self.create_nav_button(sidebar, "📊 Real-time Tracking", self.show_tracking_view)
        self.create_nav_button(sidebar, "⚙️ Process Programs", self.show_process_programs)
        
        if self.is_admin:
            self.create_nav_button(sidebar, "🔧 Admin Programs", self.show_admin_programs)
            
            # Admin tools separator
            tk.Frame(sidebar, bg=COLOR_SURFACE_2, height=1).pack(fill="x", padx=20, pady=16)
            
            tk.Label(
                sidebar, text="Admin Tools",
                font=FONT_SMALL,
                bg=COLOR_SURFACE, fg=COLOR_MUTED
            ).pack(padx=20, anchor="w")
            
            self.create_nav_button(sidebar, "👥 User Management", self.show_user_management)
            self.create_nav_button(sidebar, "📈 Statistics", self.show_statistics)
    
    def create_nav_button(self, parent, text, command):
        """Create a navigation button"""
        btn = tk.Button(
            parent, text=text,
            command=command,
            bg=COLOR_SURFACE, fg=COLOR_TEXT,
            activebackground=COLOR_SURFACE_2,
            activeforeground=COLOR_TEXT,
            relief="flat", bd=0,
            font=FONT_BODY,
            cursor="hand2",
            anchor="w",
            padx=20, pady=12
        )
        btn.pack(fill="x", padx=12, pady=2)
        
        btn.bind("<Enter>", lambda e: btn.configure(bg=COLOR_SURFACE_2))
        btn.bind("<Leave>", lambda e: btn.configure(bg=COLOR_SURFACE))
        
        return btn
    
    def create_status_bar(self):
        """Create bottom status bar"""
        status_bar = tk.Frame(self.root, bg=COLOR_SURFACE, height=45)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)
        
        # Status text
        self.status_var = tk.StringVar(value="System Ready")
        tk.Label(
            status_bar, textvariable=self.status_var,
            bg=COLOR_SURFACE, fg=COLOR_MUTED,
            font=FONT_SMALL
        ).pack(side="left", padx=20)
        
        # Logout button
        logout_btn = tk.Button(
            status_bar, text="Log Out",
            command=self.logout
        )
        self.style_button(logout_btn, COLOR_SURFACE_2, COLOR_SURFACE)
        logout_btn.pack(side="right", padx=12, pady=8, ipadx=12)
        
        # Exit button
        exit_btn = tk.Button(
            status_bar, text="Exit",
            command=self.root.destroy
        )
        self.style_button(exit_btn, COLOR_DANGER, COLOR_DANGER_H)
        exit_btn.pack(side="right", padx=4, pady=8, ipadx=12)
    
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
    
    def clear_content(self):
        """Clear current content view"""
        if self.content_frame:
            self.content_frame.destroy()
        self.content_frame = tk.Frame(self.content_container, bg=COLOR_BG)
        self.content_frame.pack(fill="both", expand=True)
    
    def show_tracking_view(self):
        """Show real-time tracking view"""
        self.clear_content()
        self.status_var.set("Viewing: Real-time Tracking")
        
        # Import with correct path
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "realtime_tracking_view",
            os.path.join(os.path.dirname(__file__), "realtime_tracking_view.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        self.current_view = module.RealtimeTrackingView(self.content_frame)
    
    def show_process_programs(self):
        """Show process programs launcher"""
        self.clear_content()
        self.status_var.set("Viewing: Process Programs")
        
        # Header
        header = tk.Frame(self.content_frame, bg=COLOR_BG)
        header.pack(fill="x", padx=28, pady=(24, 10))
        
        tk.Label(
            header, text="Process Programs",
            font=FONT_H2, bg=COLOR_BG, fg=COLOR_TEXT
        ).pack(side="left")
        
        tk.Label(
            header, text=f"{len(PROCESS_PROGRAMS)} programs available",
            font=FONT_SMALL, bg=COLOR_BG, fg=COLOR_MUTED
        ).pack(side="left", padx=12)
        
        # Program grid
        self.create_program_grid(self.content_frame, PROCESS_PROGRAMS, COLOR_ACCENT)
    
    def show_admin_programs(self):
        """Show admin programs launcher"""
        if not self.is_admin:
            messagebox.showerror("Access Denied", "Admin access required")
            return
        
        self.clear_content()
        self.status_var.set("Viewing: Admin Programs")
        
        # Header
        header = tk.Frame(self.content_frame, bg=COLOR_BG)
        header.pack(fill="x", padx=28, pady=(24, 10))
        
        tk.Label(
            header, text="Admin Programs",
            font=FONT_H2, bg=COLOR_BG, fg=COLOR_TEXT
        ).pack(side="left")
        
        tk.Label(
            header, text="Administrator tools",
            font=FONT_SMALL, bg=COLOR_BG, fg=COLOR_ADMIN
        ).pack(side="left", padx=12)
        
        # Program grid
        self.create_program_grid(self.content_frame, ADMIN_PROGRAMS, COLOR_ADMIN)
    
    def create_program_grid(self, parent, programs, accent_color):
        """Create a grid of program launcher cards"""
        # Scrollable frame
        canvas = tk.Canvas(parent, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        
        grid_frame = tk.Frame(canvas, bg=COLOR_BG)
        
        grid_frame.bind("<Configure>", 
                       lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas_window = canvas.create_window((0, 0), window=grid_frame, anchor="nw")
        canvas.bind("<Configure>", 
                   lambda e: canvas.itemconfig(canvas_window, width=e.width))
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=20)
        scrollbar.pack(side="right", fill="y")
        
        # Mouse wheel scrolling
        canvas.bind_all("<MouseWheel>",
                       lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        
        # Create program cards in grid (3 columns)
        cols = 3
        for i in range(cols):
            grid_frame.grid_columnconfigure(i, weight=1, uniform="cards")
        
        for idx, (name, path) in enumerate(programs.items()):
            row = idx // cols
            col = idx % cols
            self.create_program_card(grid_frame, name, path, accent_color, row, col)
    
    def create_program_card(self, parent, name, path, accent_color, row, col):
        """Create a clickable program launcher card"""
        card = tk.Frame(parent, bg=COLOR_SURFACE, cursor="hand2")
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        
        # Accent bar
        tk.Frame(card, bg=accent_color, width=5).pack(side="left", fill="y")
        
        # Content
        inner = tk.Frame(card, bg=COLOR_SURFACE)
        inner.pack(side="left", fill="both", expand=True, padx=16, pady=16)
        
        # Program name
        name_label = tk.Label(
            inner, text=name,
            font=FONT_CARD, bg=COLOR_SURFACE, fg=COLOR_TEXT,
            wraplength=240, justify="left", anchor="w"
        )
        name_label.pack(anchor="w")
        
        # Status
        status_text = "✓ Ready" if os.path.exists(path) else "✗ Not Found"
        status_color = COLOR_SUCCESS if os.path.exists(path) else COLOR_DANGER
        
        status_label = tk.Label(
            inner, text=status_text,
            font=FONT_SMALL, bg=COLOR_SURFACE, fg=status_color
        )
        status_label.pack(anchor="w", pady=(4, 0))
        
        # Launch hint
        hint_label = tk.Label(
            inner, text="Click to launch  →",
            font=FONT_SMALL, bg=COLOR_SURFACE, fg=COLOR_MUTED
        )
        hint_label.pack(anchor="w", pady=(8, 0))
        
        widgets = [card, inner, name_label, status_label, hint_label]
        
        # Hover effects
        def on_enter(e):
            for w in widgets:
                try:
                    w.configure(bg=COLOR_SURFACE_2)
                except:
                    pass
            hint_label.configure(bg=COLOR_SURFACE_2, fg=accent_color)
        
        def on_leave(e):
            for w in widgets:
                try:
                    w.configure(bg=COLOR_SURFACE)
                except:
                    pass
            hint_label.configure(bg=COLOR_SURFACE, fg=COLOR_MUTED)
        
        def on_click(e):
            self.launch_program(name, path)
        
        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)
    
    def launch_program(self, name, path):
        """Launch a program"""
        try:
            if not os.path.exists(path):
                messagebox.showerror("Error", f"Program not found:\n\n{name}\n{path}")
                return
            
            folder = os.path.dirname(path)
            subprocess.Popen([PYTHON_EXE, path], cwd=folder)
            
            self.status_var.set(f"Launched: {name}   ({datetime.now().strftime('%H:%M:%S')})")
        
        except Exception as e:
            messagebox.showerror("Launch Error", f"Failed to launch {name}:\n\n{str(e)}")
    
    def show_user_management(self):
        """Show user management view"""
        if not self.is_admin:
            messagebox.showerror("Access Denied", "Admin access required")
            return
        
        self.clear_content()
        self.status_var.set("Viewing: User Management")
        
        # Import user manager
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "enhanced_login",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "Log In", "enhanced_login.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Header
        tk.Label(
            self.content_frame, text="User Management",
            font=FONT_H2, bg=COLOR_BG, fg=COLOR_TEXT
        ).pack(pady=(24, 16), padx=28, anchor="w")
        
        # User list
        user_manager = module.UserManager()
        users = user_manager.load_users()
        
        # Create treeview
        style = ttk.Style()
        style.configure("Treeview", 
                       background=COLOR_SURFACE,
                       fieldbackground=COLOR_SURFACE,
                       foreground=COLOR_TEXT,
                       rowheight=32,
                       font=FONT_BODY,
                       borderwidth=0)
        style.configure("Treeview.Heading", font=FONT_SMALL)
        style.map("Treeview", background=[("selected", COLOR_PRIMARY)])
        
        tree_frame = tk.Frame(self.content_frame, bg=COLOR_BG)
        tree_frame.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        
        tree = ttk.Treeview(
            tree_frame,
            columns=("username", "role", "full_name", "created"),
            show="headings",
            height=15
        )
        
        tree.heading("username", text="Username")
        tree.heading("role", text="Role")
        tree.heading("full_name", text="Full Name")
        tree.heading("created", text="Created Date")
        
        tree.column("username", width=180)
        tree.column("role", width=120)
        tree.column("full_name", width=240)
        tree.column("created", width=200)
        
        tree.pack(side="left", fill="both", expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Populate users
        for username, data in users.items():
            tree.insert("", "end", values=(
                username,
                data.get('role', 'N/A'),
                data.get('full_name', 'N/A'),
                data.get('created_date', 'N/A')
            ))
    
    def show_statistics(self):
        """Show production statistics"""
        if not self.is_admin:
            messagebox.showerror("Access Denied", "Admin access required")
            return
        
        self.clear_content()
        self.status_var.set("Viewing: Statistics")
        
        # Header
        tk.Label(
            self.content_frame, text="Production Statistics",
            font=FONT_H2, bg=COLOR_BG, fg=COLOR_TEXT
        ).pack(pady=(24, 20), padx=28, anchor="w")
        
        # Get statistics
        stats = self.db_manager.get_production_statistics()
        process_counts = self.db_manager.get_lot_counts_by_process()
        
        # Statistics cards
        stats_frame = tk.Frame(self.content_frame, bg=COLOR_BG)
        stats_frame.pack(fill="x", padx=28, pady=(0, 20))
        
        self.create_stat_card(stats_frame, "Total Lots", stats['total_lots'], COLOR_ACCENT, 0)
        self.create_stat_card(stats_frame, "Total Sensors", stats['total_sensors'], COLOR_PRIMARY, 1)
        self.create_stat_card(stats_frame, "In Progress", stats['in_progress'], COLOR_WARNING, 2)
        self.create_stat_card(stats_frame, "Completed", stats['completed'], COLOR_SUCCESS, 3)
        
        # Process breakdown
        tk.Label(
            self.content_frame, text="Lots by Process Stage",
            font=FONT_H2, bg=COLOR_BG, fg=COLOR_TEXT
        ).pack(pady=(20, 10), padx=28, anchor="w")
        
        # Process list
        process_frame = tk.Frame(self.content_frame, bg=COLOR_BG)
        process_frame.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        
        canvas = tk.Canvas(process_frame, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(process_frame, orient="vertical", command=canvas.yview)
        
        process_list = tk.Frame(canvas, bg=COLOR_BG)
        process_list.bind("<Configure>", 
                         lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas.create_window((0, 0), window=process_list, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Create process bars
        max_count = max(process_counts.values()) if process_counts else 1
        
        for process, count in sorted(process_counts.items(), key=lambda x: x[1], reverse=True):
            self.create_process_bar(process_list, process, count, max_count)
    
    def create_stat_card(self, parent, label, value, color, col):
        """Create a statistics card"""
        card = tk.Frame(parent, bg=COLOR_SURFACE)
        card.grid(row=0, column=col, padx=6, sticky="nsew")
        parent.grid_columnconfigure(col, weight=1, uniform="stats")
        
        # Accent bar
        tk.Frame(card, bg=color, height=4).pack(fill="x")
        
        # Content
        content = tk.Frame(card, bg=COLOR_SURFACE)
        content.pack(fill="both", expand=True, padx=20, pady=20)
        
        tk.Label(
            content, text=str(value),
            font=("Segoe UI Semibold", 28),
            bg=COLOR_SURFACE, fg=color
        ).pack()
        
        tk.Label(
            content, text=label,
            font=FONT_BODY,
            bg=COLOR_SURFACE, fg=COLOR_MUTED
        ).pack()
    
    def create_process_bar(self, parent, process_name, count, max_count):
        """Create a horizontal bar for process count"""
        container = tk.Frame(parent, bg=COLOR_BG)
        container.pack(fill="x", pady=4)
        
        # Process name
        name_label = tk.Label(
            container, text=process_name,
            font=FONT_BODY, bg=COLOR_BG, fg=COLOR_TEXT,
            width=35, anchor="w"
        )
        name_label.pack(side="left", padx=(0, 10))
        
        # Bar background
        bar_bg = tk.Frame(container, bg=COLOR_SURFACE, height=24)
        bar_bg.pack(side="left", fill="x", expand=True)
        
        # Bar fill
        if max_count > 0:
            fill_width = int((count / max_count) * 400)
            bar_fill = tk.Frame(bar_bg, bg=COLOR_ACCENT, width=fill_width, height=24)
            bar_fill.pack(side="left")
        
        # Count label
        count_label = tk.Label(
            container, text=str(count),
            font=FONT_BODY, bg=COLOR_BG, fg=COLOR_TEXT,
            width=6, anchor="e"
        )
        count_label.pack(side="left", padx=(10, 0))
    
    def logout(self):
        """Log out and return to login screen"""
        if messagebox.askyesno("Log Out", "Are you sure you want to log out?"):
            self.root.destroy()
            # Restart login
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "enhanced_login",
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "Log In", "enhanced_login.py")
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            login_win = module.LoginWindow()
            user_data = login_win.run()
            
            if user_data:
                # Restart dashboard with new user
                new_dashboard = MainDashboard(user_data)
                new_dashboard.run()
    
    def run(self):
        """Run the dashboard"""
        self.root.mainloop()


def main():
    """Main entry point"""
    # Show login first
    from Log_In.enhanced_login import LoginWindow
    
    login_win = LoginWindow()
    user_data = login_win.run()
    
    if user_data:
        # Show dashboard
        dashboard = MainDashboard(user_data)
        dashboard.run()


if __name__ == "__main__":
    main()
