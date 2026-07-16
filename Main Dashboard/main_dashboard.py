"""
Main Dashboard for BMS Lot Tracking System
Enhanced UI with dark/light mode, responsive design, and modern UX
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
import os
import json
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
DARK_THEME = system_config.DARK_THEME
LIGHT_THEME = system_config.LIGHT_THEME
FONT_TITLE = system_config.FONT_TITLE
FONT_H1 = system_config.FONT_H1
FONT_H2 = system_config.FONT_H2
FONT_BODY = system_config.FONT_BODY
FONT_SMALL = system_config.FONT_SMALL
FONT_CARD = system_config.FONT_CARD
ROLE_OPERATOR = system_config.ROLE_OPERATOR
ROLE_ADMIN = system_config.ROLE_ADMIN

DatabaseManager = database_manager_module.DatabaseManager

# Theme preferences file
THEME_PREFS_FILE = BASE_DIR / "config" / "theme_prefs.json"


class MainDashboard:
    """Enhanced main dashboard with dark/light mode and responsive design"""
    
    def __init__(self, user_data):
        self.user_data = user_data
        self.username = user_data['username']
        self.role = user_data['role']
        self.is_admin = (self.role == ROLE_ADMIN)
        
        self.db_manager = DatabaseManager()
        
        # Load theme preference
        self.load_theme_preference()
        
        self.root = tk.Tk()
        self.root.title("BMS Lot Tracking System")
        self.root.configure(bg=self.theme['bg'])
        self.center_window(1400, 900)
        self.root.minsize(1000, 600)
        
        # Window state management for responsive design
        self.root.bind('<Configure>', self.on_window_resize)
        self.last_width = 1400
        self.sidebar_collapsed = False
        
        # Current view tracking
        self.current_view = None
        self.current_view_name = 'tracking'
        self.content_frame = None
        
        self.create_ui()
        self.show_tracking_view()
    
    def load_theme_preference(self):
        """Load saved theme preference"""
        try:
            if THEME_PREFS_FILE.exists():
                with open(THEME_PREFS_FILE, 'r') as f:
                    prefs = json.load(f)
                    self.is_dark_mode = prefs.get('dark_mode', True)
            else:
                self.is_dark_mode = True
        except:
            self.is_dark_mode = True
        
        self.theme = DARK_THEME if self.is_dark_mode else LIGHT_THEME
    
    def save_theme_preference(self):
        """Save theme preference to file"""
        try:
            THEME_PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(THEME_PREFS_FILE, 'w') as f:
                json.dump({'dark_mode': self.is_dark_mode}, f)
        except Exception as e:
            print(f"Failed to save theme preference: {e}")
    
    def toggle_theme(self):
        """Toggle between dark and light mode with smooth transition"""
        self.is_dark_mode = not self.is_dark_mode
        self.theme = DARK_THEME if self.is_dark_mode else LIGHT_THEME
        self.save_theme_preference()
        
        # Refresh the entire UI
        self.refresh_ui()
    
    def refresh_ui(self):
        """Refresh all UI components with new theme"""
        # Store current view
        current = self.current_view_name
        
        # Clear all widgets
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Update root background
        self.root.configure(bg=self.theme['bg'])
        
        # Recreate UI
        self.create_ui()
        
        # Restore the current view
        if current == 'tracking':
            self.show_tracking_view()
        elif current == 'process':
            self.show_process_programs()
        elif current == 'admin':
            self.show_admin_programs()
        elif current == 'users':
            self.show_user_management()
        elif current == 'stats':
            self.show_statistics()
    
    def on_window_resize(self, event):
        """Handle window resize for responsive design"""
        if event.widget == self.root:
            new_width = event.width
            
            # Auto-collapse sidebar on small screens
            if new_width < 1200 and not self.sidebar_collapsed:
                # Could implement sidebar collapse here
                pass
            elif new_width >= 1200 and self.sidebar_collapsed:
                # Could implement sidebar expand here
                pass
            
            self.last_width = new_width
    
    def center_window(self, width, height):
        """Center window on screen"""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def create_ui(self):
        """Create main dashboard UI with modern design"""
        # Top header bar with theme toggle
        self.create_header()
        
        # Main content area with sidebar
        main_container = tk.Frame(self.root, bg=self.theme['bg'])
        main_container.pack(fill="both", expand=True)
        
        # Left sidebar for navigation
        self.create_sidebar(main_container)
        
        # Right content area
        self.content_container = tk.Frame(main_container, bg=self.theme['bg'])
        self.content_container.pack(side="right", fill="both", expand=True)
        
        # Bottom status bar
        self.create_status_bar()
    
    def create_header(self):
        """Create modern top header bar with theme toggle"""
        header = tk.Frame(self.root, bg=self.theme['surface'], height=90)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        # Left side - title and stats
        left = tk.Frame(header, bg=self.theme['surface'])
        left.pack(side="left", padx=28)
        
        # Title with icon
        title_frame = tk.Frame(left, bg=self.theme['surface'])
        title_frame.pack(anchor="w", pady=(20, 4))
        
        tk.Label(
            title_frame, text="🏭",
            font=("Segoe UI", 22),
            bg=self.theme['surface'], fg=self.theme['text']
        ).pack(side="left", padx=(0, 10))
        
        tk.Label(
            title_frame, text="BMS Lot Tracking System",
            font=FONT_TITLE,
            bg=self.theme['surface'], fg=self.theme['text']
        ).pack(side="left")
        
        # Stats
        try:
            stats = self.db_manager.get_production_statistics()
            stats_text = f"📦 {stats['total_lots']} lots  •  ⏳ {stats['in_progress']} in progress  •  ✅ {stats['completed']} completed"
        except:
            stats_text = "System Ready"
        
        tk.Label(
            left, text=stats_text,
            font=FONT_SMALL,
            bg=self.theme['surface'], fg=self.theme['muted']
        ).pack(anchor="w", pady=(0, 20))
        
        # Right side - theme toggle and user info
        right = tk.Frame(header, bg=self.theme['surface'])
        right.pack(side="right", padx=28)
        
        # Theme toggle button
        theme_btn = tk.Button(
            right,
            text="🌙" if self.is_dark_mode else "☀️",
            command=self.toggle_theme,
            font=("Segoe UI", 16),
            bg=self.theme['surface_2'],
            fg=self.theme['text'],
            activebackground=self.theme['surface_3'],
            activeforeground=self.theme['text'],
            relief="flat",
            bd=0,
            cursor="hand2",
            width=3,
            height=1
        )
        theme_btn.pack(side="right", pady=(26, 0), padx=(10, 0))
        
        # Hover effect for theme button
        theme_btn.bind("<Enter>", lambda e: theme_btn.configure(bg=self.theme['surface_3']))
        theme_btn.bind("<Leave>", lambda e: theme_btn.configure(bg=self.theme['surface_2']))
        
        # Role badge
        badge_color = self.theme['admin'] if self.is_admin else self.theme['accent']
        role_badge = tk.Label(
            right, text=f"  {self.role.upper()}  ",
            font=("Segoe UI Semibold", 9),
            bg=badge_color,
            fg=self.theme['bg' if self.is_dark_mode else 'text']
        )
        role_badge.pack(side="right", pady=(28, 0))
        
        # Username
        tk.Label(
            right, text=f"{self.user_data.get('full_name', self.username)}   ",
            font=FONT_BODY,
            bg=self.theme['surface'], fg=self.theme['text']
        ).pack(side="right", pady=(26, 0))
    
    def create_sidebar(self, parent):
        """Create modern left navigation sidebar"""
        sidebar = tk.Frame(parent, bg=self.theme['surface'], width=280)
        sidebar.pack(side="left", fill="y", padx=(0, 1))
        sidebar.pack_propagate(False)
        
        # Sidebar header
        header = tk.Frame(sidebar, bg=self.theme['surface'])
        header.pack(fill="x", pady=(28, 20), padx=24)
        
        tk.Label(
            header, text="Navigation",
            font=("Segoe UI Semibold", 14),
            bg=self.theme['surface'], fg=self.theme['text']
        ).pack(anchor="w")
        
        # Navigation buttons with icons
        nav_items = [
            ("📊", "Real-time Tracking", self.show_tracking_view, 'tracking'),
            ("📦", "Scan & Process", self.show_process_programs, 'process'),
        ]
        
        if self.is_admin:
            nav_items.append(("🔧", "Admin Programs", self.show_admin_programs, 'admin'))
        
        for icon, text, command, view_name in nav_items:
            self.create_nav_button(sidebar, icon, text, command, view_name)
        
        if self.is_admin:
            # Admin tools separator
            separator = tk.Frame(sidebar, bg=self.theme['border'], height=1)
            separator.pack(fill="x", padx=24, pady=20)
            
            tk.Label(
                sidebar, text="ADMIN TOOLS",
                font=("Segoe UI Semibold", 9),
                bg=self.theme['surface'], fg=self.theme['muted']
            ).pack(padx=24, anchor="w", pady=(0, 8))
            
            admin_items = [
                ("👥", "User Management", self.show_user_management, 'users'),
                ("📈", "Statistics", self.show_statistics, 'stats'),
            ]
            
            for icon, text, command, view_name in admin_items:
                self.create_nav_button(sidebar, icon, text, command, view_name)
        
        # Spacer
        tk.Frame(sidebar, bg=self.theme['surface']).pack(fill="both", expand=True)
        
        # Version info at bottom
        version_frame = tk.Frame(sidebar, bg=self.theme['surface_2'])
        version_frame.pack(fill="x", side="bottom")
        
        tk.Label(
            version_frame, text="Version 2.0",
            font=("Segoe UI", 8),
            bg=self.theme['surface_2'], fg=self.theme['muted']
        ).pack(pady=12)
    
    def create_nav_button(self, parent, icon, text, command, view_name):
        """Create a modern navigation button with icon"""
        is_active = (self.current_view_name == view_name)
        
        btn_frame = tk.Frame(
            parent,
            bg=self.theme['primary'] if is_active else self.theme['surface'],
            cursor="hand2"
        )
        btn_frame.pack(fill="x", padx=16, pady=3)
        
        # Icon
        icon_label = tk.Label(
            btn_frame, text=icon,
            font=("Segoe UI", 14),
            bg=self.theme['primary'] if is_active else self.theme['surface'],
            fg=self.theme['text']
        )
        icon_label.pack(side="left", padx=(12, 8), pady=12)
        
        # Text
        text_label = tk.Label(
            btn_frame, text=text,
            font=("Segoe UI Semibold", 10) if is_active else FONT_BODY,
            bg=self.theme['primary'] if is_active else self.theme['surface'],
            fg=self.theme['text'],
            anchor="w"
        )
        text_label.pack(side="left", fill="x", expand=True, pady=12)
        
        # Hover effects (only if not active)
        def on_enter(e):
            if not is_active:
                btn_frame.configure(bg=self.theme['surface_2'])
                icon_label.configure(bg=self.theme['surface_2'])
                text_label.configure(bg=self.theme['surface_2'])
        
        def on_leave(e):
            if not is_active:
                btn_frame.configure(bg=self.theme['surface'])
                icon_label.configure(bg=self.theme['surface'])
                text_label.configure(bg=self.theme['surface'])
        
        def on_click(e):
            self.current_view_name = view_name
            command()
        
        for widget in [btn_frame, icon_label, text_label]:
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<Button-1>", on_click)
        
        return btn_frame
    
    def create_status_bar(self):
        """Create modern bottom status bar"""
        status_bar = tk.Frame(self.root, bg=self.theme['surface'], height=50)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)
        
        # Status icon and text
        status_frame = tk.Frame(status_bar, bg=self.theme['surface'])
        status_frame.pack(side="left", padx=24)
        
        tk.Label(
            status_frame, text="●",
            font=("Segoe UI", 12),
            bg=self.theme['surface'], fg=self.theme['success']
        ).pack(side="left", padx=(0, 8), pady=15)
        
        self.status_var = tk.StringVar(value="System Ready")
        tk.Label(
            status_frame, textvariable=self.status_var,
            bg=self.theme['surface'], fg=self.theme['text_secondary'],
            font=FONT_SMALL
        ).pack(side="left", pady=15)
        
        # Right side buttons
        btn_frame = tk.Frame(status_bar, bg=self.theme['surface'])
        btn_frame.pack(side="right", padx=16, pady=8)
        
        # Exit button
        exit_btn = tk.Button(
            btn_frame, text="Exit System",
            command=self.root.destroy,
            font=FONT_BODY,
            bg=self.theme['danger'],
            fg="#ffffff",
            activebackground=self.theme['danger_h'],
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=20,
            pady=8
        )
        exit_btn.pack(side="right", padx=(8, 0))
        exit_btn.bind("<Enter>", lambda e: exit_btn.configure(bg=self.theme['danger_h']))
        exit_btn.bind("<Leave>", lambda e: exit_btn.configure(bg=self.theme['danger']))
        
        # Logout button
        logout_btn = tk.Button(
            btn_frame, text="Log Out",
            command=self.logout,
            font=FONT_BODY,
            bg=self.theme['surface_2'],
            fg=self.theme['text'],
            activebackground=self.theme['surface_3'],
            activeforeground=self.theme['text'],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=20,
            pady=8
        )
        logout_btn.pack(side="right")
        logout_btn.bind("<Enter>", lambda e: logout_btn.configure(bg=self.theme['surface_3']))
        logout_btn.bind("<Leave>", lambda e: logout_btn.configure(bg=self.theme['surface_2']))
    
    def create_modern_button(self, parent, text, command, style='primary'):
        """Create a modern styled button"""
        if style == 'primary':
            bg, hover = self.theme['primary'], self.theme['primary_h']
            fg = "#ffffff"
        elif style == 'success':
            bg, hover = self.theme['success'], self.theme['success_h']
            fg = "#ffffff"
        elif style == 'danger':
            bg, hover = self.theme['danger'], self.theme['danger_h']
            fg = "#ffffff"
        else:  # secondary
            bg, hover = self.theme['surface_2'], self.theme['surface_3']
            fg = self.theme['text']
        
        btn = tk.Button(
            parent, text=text,
            command=command,
            bg=bg, fg=fg,
            activebackground=hover, activeforeground=fg,
            relief="flat", bd=0, cursor="hand2",
            highlightthickness=0, font=FONT_BODY,
            padx=20, pady=10
        )
        
        btn.bind("<Enter>", lambda e: btn.configure(bg=hover))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
        
        return btn
    
    def clear_content(self):
        """Clear current content view"""
        # Cleanup current view if it has cleanup method
        if self.content_frame and hasattr(self.current_view, 'cleanup'):
            try:
                self.current_view.cleanup()
            except:
                pass
        
        if self.content_frame:
            self.content_frame.destroy()
        self.content_frame = tk.Frame(self.content_container, bg=self.theme['bg'])
        self.content_frame.pack(fill="both", expand=True)
        self.current_view = None
    
    def show_tracking_view(self):
        """Show real-time tracking view"""
        self.current_view_name = 'tracking'
        self.clear_content()
        self.status_var.set("Viewing: Real-time Tracking")
        
        # Try to import tracking view
        try:
            spec = importlib.util.spec_from_file_location(
                "realtime_tracking_view",
                os.path.join(os.path.dirname(__file__), "realtime_tracking_view.py")
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            self.current_view = module.RealtimeTrackingView(self.content_frame)
        except Exception as e:
            # Fallback to placeholder
            self.show_placeholder("Real-time Tracking", "📊", 
                                f"Tracking view will appear here.\n\n{str(e)}")
    
    def show_placeholder(self, title, icon, message):
        """Show a placeholder view"""
        container = tk.Frame(self.content_frame, bg=self.theme['bg'])
        container.place(relx=0.5, rely=0.5, anchor="center")
        
        tk.Label(
            container, text=icon,
            font=("Segoe UI", 48),
            bg=self.theme['bg'], fg=self.theme['muted']
        ).pack(pady=(0, 16))
        
        tk.Label(
            container, text=title,
            font=FONT_H1,
            bg=self.theme['bg'], fg=self.theme['text']
        ).pack()
        
        tk.Label(
            container, text=message,
            font=FONT_BODY,
            bg=self.theme['bg'], fg=self.theme['muted'],
            justify="center"
        ).pack(pady=(8, 0))
    
    def show_process_programs(self):
        """Show station-specific launcher (scan to launch)"""
        self.current_view_name = 'process'
        self.clear_content()
        self.status_var.set("Station Mode: Scan lot to launch process")
        
        # Import station launcher
        try:
            spec = importlib.util.spec_from_file_location(
                "station_launcher",
                os.path.join(os.path.dirname(__file__), "station_launcher.py")
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Create station launcher with theme and status callback
            self.current_view = module.StationLauncher(
                self.content_frame, 
                self.theme,
                status_callback=lambda msg: self.status_var.set(msg)
            )
        except Exception as e:
            # Fallback error message
            self.show_placeholder(
                "Station Launcher",
                "⚙️",
                f"Failed to load station launcher:\n\n{str(e)}"
            )
    
    def show_admin_programs(self):
        """Show admin programs launcher"""
        if not self.is_admin:
            messagebox.showerror("Access Denied", "Admin access required")
            return
        
        self.current_view_name = 'admin'
        self.clear_content()
        self.status_var.set("Viewing: Admin Programs")
        
        # Header
        header = tk.Frame(self.content_frame, bg=self.theme['bg'])
        header.pack(fill="x", padx=32, pady=(28, 16))
        
        title_frame = tk.Frame(header, bg=self.theme['bg'])
        title_frame.pack(side="left")
        
        tk.Label(
            title_frame, text="🔧 Admin Programs",
            font=("Segoe UI Semibold", 18),
            bg=self.theme['bg'], fg=self.theme['text']
        ).pack(side="left")
        
        tk.Label(
            title_frame, text="  •  Administrator tools",
            font=FONT_SMALL,
            bg=self.theme['bg'], fg=self.theme['admin']
        ).pack(side="left", pady=4)
        
        # Program grid
        self.create_program_grid(self.content_frame, ADMIN_PROGRAMS, self.theme['admin'])
    
    def create_program_grid(self, parent, programs, accent_color):
        """Create a modern responsive grid of program launcher cards"""
        # Scrollable container
        canvas = tk.Canvas(parent, bg=self.theme['bg'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        
        # Configure scrollbar style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Vertical.TScrollbar",
                       background=self.theme['surface'],
                       bordercolor=self.theme['surface'],
                       arrowcolor=self.theme['text'],
                       troughcolor=self.theme['bg'])
        
        grid_frame = tk.Frame(canvas, bg=self.theme['bg'])
        
        grid_frame.bind("<Configure>",
                       lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas_window = canvas.create_window((0, 0), window=grid_frame, anchor="nw")
        canvas.bind("<Configure>",
                   lambda e: canvas.itemconfig(canvas_window, width=e.width - 20))
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(32, 0))
        scrollbar.pack(side="right", fill="y", padx=(0, 32))
        
        # Mouse wheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        # Create program cards in responsive grid
        cols = 3
        for i in range(cols):
            grid_frame.grid_columnconfigure(i, weight=1, uniform="cards")
        
        for idx, (name, path) in enumerate(programs.items()):
            row = idx // cols
            col = idx % cols
            self.create_program_card(grid_frame, name, path, accent_color, row, col)
    
    def create_program_card(self, parent, name, path, accent_color, row, col):
        """Create a modern, clickable program launcher card"""
        # Card container with shadow effect
        card_container = tk.Frame(parent, bg=self.theme['bg'])
        card_container.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        
        card = tk.Frame(card_container, bg=self.theme['surface'], cursor="hand2",
                       highlightbackground=self.theme['border'],
                       highlightthickness=1)
        card.pack(fill="both", expand=True)
        
        # Accent bar at top
        accent_bar = tk.Frame(card, bg=accent_color, height=4)
        accent_bar.pack(fill="x")
        
        # Content
        inner = tk.Frame(card, bg=self.theme['surface'])
        inner.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Program name
        name_label = tk.Label(
            inner, text=name,
            font=("Segoe UI Semibold", 11),
            bg=self.theme['surface'], fg=self.theme['text'],
            wraplength=250, justify="left", anchor="w"
        )
        name_label.pack(anchor="w", fill="x")
        
        # Status with icon
        file_exists = os.path.exists(path)
        status_frame = tk.Frame(inner, bg=self.theme['surface'])
        status_frame.pack(anchor="w", pady=(12, 0), fill="x")
        
        status_icon = "✓" if file_exists else "✗"
        status_text = "Ready" if file_exists else "Not Found"
        status_color = self.theme['success'] if file_exists else self.theme['danger']
        
        tk.Label(
            status_frame, text=status_icon,
            font=("Segoe UI", 10),
            bg=self.theme['surface'], fg=status_color
        ).pack(side="left")
        
        tk.Label(
            status_frame, text=status_text,
            font=FONT_SMALL,
            bg=self.theme['surface'], fg=status_color
        ).pack(side="left", padx=(4, 0))
        
        # Launch button/hint
        launch_frame = tk.Frame(inner, bg=self.theme['surface'])
        launch_frame.pack(anchor="w", pady=(16, 0), fill="x")
        
        launch_icon = tk.Label(
            launch_frame, text="▶",
            font=("Segoe UI", 10),
            bg=self.theme['surface'], fg=self.theme['muted']
        )
        launch_icon.pack(side="left")
        
        launch_label = tk.Label(
            launch_frame, text="Click to launch",
            font=FONT_SMALL,
            bg=self.theme['surface'], fg=self.theme['muted']
        )
        launch_label.pack(side="left", padx=(6, 0))
        
        widgets = [card, inner, name_label, status_frame, launch_frame, launch_icon, launch_label]
        
        # Enhanced hover effects
        def on_enter(e):
            card.configure(bg=self.theme['surface_2'],
                          highlightbackground=accent_color,
                          highlightthickness=2)
            for w in widgets[1:]:  # Skip card itself
                try:
                    w.configure(bg=self.theme['surface_2'])
                except:
                    pass
            launch_icon.configure(bg=self.theme['surface_2'], fg=accent_color)
            launch_label.configure(bg=self.theme['surface_2'], fg=accent_color)
        
        def on_leave(e):
            card.configure(bg=self.theme['surface'],
                          highlightbackground=self.theme['border'],
                          highlightthickness=1)
            for w in widgets[1:]:
                try:
                    w.configure(bg=self.theme['surface'])
                except:
                    pass
            launch_icon.configure(bg=self.theme['surface'], fg=self.theme['muted'])
            launch_label.configure(bg=self.theme['surface'], fg=self.theme['muted'])
        
        def on_click(e):
            self.launch_program(name, path)
        
        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)
    
    def launch_program(self, name, path):
        """Launch a program with visual feedback"""
        try:
            if not os.path.exists(path):
                messagebox.showerror(
                    "Program Not Found",
                    f"Cannot find program:\n\n{name}\n\nPath: {path}",
                    parent=self.root
                )
                return
            
            folder = os.path.dirname(path)
            subprocess.Popen([PYTHON_EXE, path], cwd=folder)
            
            # Update status with timestamp
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.status_var.set(f"✓ Launched: {name} at {timestamp}")
            
            # Show success message briefly
            self.root.after(3000, lambda: self.status_var.set("System Ready"))
        
        except Exception as e:
            messagebox.showerror(
                "Launch Error",
                f"Failed to launch {name}:\n\n{str(e)}",
                parent=self.root
            )
    
    def show_user_management(self):
        """Show user management view with modern styling"""
        if not self.is_admin:
            messagebox.showerror("Access Denied", "Admin access required")
            return
        
        self.current_view_name = 'users'
        self.clear_content()
        self.status_var.set("Viewing: User Management")
        
        # Header
        header = tk.Frame(self.content_frame, bg=self.theme['bg'])
        header.pack(fill="x", padx=32, pady=(28, 20))
        
        tk.Label(
            header, text="👥 User Management",
            font=("Segoe UI Semibold", 18),
            bg=self.theme['bg'], fg=self.theme['text']
        ).pack(anchor="w")
        
        # Try to load users
        try:
            spec = importlib.util.spec_from_file_location(
                "enhanced_login",
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "Log In", "enhanced_login.py")
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            user_manager = module.UserManager()
            users = user_manager.load_users()
            
            # User count badge
            count_label = tk.Label(
                header, text=f"{len(users)} users",
                font=FONT_SMALL,
                bg=self.theme['accent'],
                fg="#ffffff",
                padx=12, pady=4
            )
            count_label.pack(anchor="w", pady=(8, 0))
            
            # Create modern table
            table_frame = tk.Frame(self.content_frame, bg=self.theme['surface'])
            table_frame.pack(fill="both", expand=True, padx=32, pady=(0, 32))
            
            # Configure treeview style
            style = ttk.Style()
            style.theme_use('clam')
            style.configure("Modern.Treeview",
                           background=self.theme['surface'],
                           fieldbackground=self.theme['surface'],
                           foreground=self.theme['text'],
                           rowheight=40,
                           font=FONT_BODY,
                           borderwidth=0)
            style.configure("Modern.Treeview.Heading",
                           background=self.theme['surface_2'],
                           foreground=self.theme['text'],
                           font=("Segoe UI Semibold", 10),
                           borderwidth=0)
            style.map("Modern.Treeview",
                     background=[("selected", self.theme['primary'])],
                     foreground=[("selected", "#ffffff")])
            
            # Create treeview
            tree = ttk.Treeview(
                table_frame,
                columns=("username", "role", "full_name", "created"),
                show="headings",
                style="Modern.Treeview",
                height=15
            )
            
            tree.heading("username", text="USERNAME")
            tree.heading("role", text="ROLE")
            tree.heading("full_name", text="FULL NAME")
            tree.heading("created", text="CREATED DATE")
            
            tree.column("username", width=200)
            tree.column("role", width=150)
            tree.column("full_name", width=300)
            tree.column("created", width=250)
            
            tree.pack(side="left", fill="both", expand=True, padx=2, pady=2)
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
            scrollbar.pack(side="right", fill="y")
            tree.configure(yscrollcommand=scrollbar.set)
            
            # Populate users
            for username, data in users.items():
                tree.insert("", "end", values=(
                    username,
                    data.get('role', 'N/A').upper(),
                    data.get('full_name', 'N/A'),
                    data.get('created_date', 'N/A')
                ))
        
        except Exception as e:
            self.show_placeholder("User Management", "👥",
                                f"Unable to load user data.\n\n{str(e)}")
    
    def show_statistics(self):
        """Show production statistics with modern charts"""
        if not self.is_admin:
            messagebox.showerror("Access Denied", "Admin access required")
            return
        
        self.current_view_name = 'stats'
        self.clear_content()
        self.status_var.set("Viewing: Statistics")
        
        # Header
        header = tk.Frame(self.content_frame, bg=self.theme['bg'])
        header.pack(fill="x", padx=32, pady=(28, 24))
        
        tk.Label(
            header, text="📈 Production Statistics",
            font=("Segoe UI Semibold", 18),
            bg=self.theme['bg'], fg=self.theme['text']
        ).pack(anchor="w")
        
        try:
            # Get statistics
            stats = self.db_manager.get_production_statistics()
            process_counts = self.db_manager.get_lot_counts_by_process()
            
            # Statistics cards
            stats_frame = tk.Frame(self.content_frame, bg=self.theme['bg'])
            stats_frame.pack(fill="x", padx=32, pady=(0, 24))
            
            stat_items = [
                ("Total Lots", stats['total_lots'], self.theme['accent'], "📦"),
                ("Total Sensors", stats['total_sensors'], self.theme['primary'], "🔧"),
                ("In Progress", stats['in_progress'], self.theme['warning'], "⏳"),
                ("Completed", stats['completed'], self.theme['success'], "✅"),
            ]
            
            for idx, (label, value, color, icon) in enumerate(stat_items):
                self.create_stat_card(stats_frame, label, value, color, icon, idx)
            
            # Process breakdown section
            breakdown_header = tk.Frame(self.content_frame, bg=self.theme['bg'])
            breakdown_header.pack(fill="x", padx=32, pady=(16, 12))
            
            tk.Label(
                breakdown_header, text="Lots by Process Stage",
                font=("Segoe UI Semibold", 14),
                bg=self.theme['bg'], fg=self.theme['text']
            ).pack(anchor="w")
            
            # Process list with modern bars
            process_container = tk.Frame(self.content_frame, bg=self.theme['surface'])
            process_container.pack(fill="both", expand=True, padx=32, pady=(0, 32))
            
            canvas = tk.Canvas(process_container, bg=self.theme['surface'], highlightthickness=0)
            scrollbar = ttk.Scrollbar(process_container, orient="vertical", command=canvas.yview)
            
            process_list = tk.Frame(canvas, bg=self.theme['surface'])
            process_list.bind("<Configure>",
                             lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            
            canvas.create_window((0, 0), window=process_list, anchor="nw", width=1000)
            canvas.configure(yscrollcommand=scrollbar.set)
            
            canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
            scrollbar.pack(side="right", fill="y", pady=20)
            
            # Create process bars
            max_count = max(process_counts.values()) if process_counts else 1
            
            for process, count in sorted(process_counts.items(), key=lambda x: x[1], reverse=True):
                self.create_process_bar(process_list, process, count, max_count)
        
        except Exception as e:
            self.show_placeholder("Statistics", "📈",
                                f"Unable to load statistics.\n\n{str(e)}")
    
    def create_stat_card(self, parent, label, value, color, icon, col):
        """Create a modern statistics card"""
        card = tk.Frame(parent, bg=self.theme['surface'],
                       highlightbackground=self.theme['border'],
                       highlightthickness=1)
        card.grid(row=0, column=col, padx=8, sticky="nsew")
        parent.grid_columnconfigure(col, weight=1, uniform="stats")
        
        # Colored top border
        tk.Frame(card, bg=color, height=4).pack(fill="x")
        
        # Content
        content = tk.Frame(card, bg=self.theme['surface'])
        content.pack(fill="both", expand=True, padx=24, pady=24)
        
        # Icon and value in same row
        top_row = tk.Frame(content, bg=self.theme['surface'])
        top_row.pack(fill="x")
        
        tk.Label(
            top_row, text=icon,
            font=("Segoe UI", 20),
            bg=self.theme['surface'], fg=color
        ).pack(side="left", padx=(0, 12))
        
        tk.Label(
            top_row, text=str(value),
            font=("Segoe UI Bold", 32),
            bg=self.theme['surface'], fg=self.theme['text']
        ).pack(side="left")
        
        # Label
        tk.Label(
            content, text=label,
            font=FONT_BODY,
            bg=self.theme['surface'], fg=self.theme['muted']
        ).pack(anchor="w", pady=(8, 0))
    
    def create_process_bar(self, parent, process_name, count, max_count):
        """Create a modern horizontal bar for process count"""
        container = tk.Frame(parent, bg=self.theme['surface'])
        container.pack(fill="x", pady=6, padx=8)
        
        # Process name
        name_label = tk.Label(
            container, text=process_name,
            font=FONT_BODY,
            bg=self.theme['surface'], fg=self.theme['text'],
            width=40, anchor="w"
        )
        name_label.pack(side="left", padx=(0, 16))
        
        # Bar container
        bar_container = tk.Frame(container, bg=self.theme['surface'])
        bar_container.pack(side="left", fill="x", expand=True)
        
        # Bar background
        bar_bg = tk.Frame(bar_container, bg=self.theme['surface_2'], height=28)
        bar_bg.pack(fill="x")
        
        # Bar fill
        if max_count > 0:
            fill_percent = (count / max_count)
            bar_fill = tk.Frame(bar_bg, bg=self.theme['accent'], height=28)
            bar_fill.place(relx=0, rely=0, relwidth=fill_percent, relheight=1)
            
            # Count label inside bar if space allows
            if fill_percent > 0.1:
                tk.Label(
                    bar_fill, text=str(count),
                    font=("Segoe UI Semibold", 10),
                    bg=self.theme['accent'], fg="#ffffff"
                ).place(relx=0.5, rely=0.5, anchor="center")
        
        # Count label outside
        count_label = tk.Label(
            container, text=str(count),
            font=("Segoe UI Semibold", 11),
            bg=self.theme['surface'], fg=self.theme['text'],
            width=8, anchor="e"
        )
        count_label.pack(side="left", padx=(16, 0))
    
    def logout(self):
        """Log out and return to login screen"""
        result = messagebox.askyesno(
            "Log Out",
            "Are you sure you want to log out?",
            parent=self.root
        )
        
        if result:
            self.root.destroy()
            
            # Restart login
            try:
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
            except Exception as e:
                print(f"Error restarting login: {e}")
    
    def run(self):
        """Run the dashboard"""
        self.root.mainloop()


def main():
    """Main entry point"""
    # Show login first
    try:
        from Log_In.enhanced_login import LoginWindow
        
        login_win = LoginWindow()
        user_data = login_win.run()
        
        if user_data:
            # Show dashboard
            dashboard = MainDashboard(user_data)
            dashboard.run()
    except Exception as e:
        print(f"Error starting dashboard: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
