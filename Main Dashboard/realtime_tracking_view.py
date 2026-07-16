"""
Real-time Lot Tracking Visualization
Modern, theme-aware visual display of lots moving through manufacturing processes
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import sys
import json
from pathlib import Path
import importlib.util
from datetime import datetime

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

# Import theme configurations
DARK_THEME = system_config.DARK_THEME
LIGHT_THEME = system_config.LIGHT_THEME
FONT_H2 = system_config.FONT_H2
FONT_BODY = system_config.FONT_BODY
FONT_SMALL = system_config.FONT_SMALL
FONT_H3 = system_config.FONT_H3
PROCESS_STAGES = system_config.PROCESS_STAGES
REFRESH_INTERVAL = system_config.REFRESH_INTERVAL

DatabaseManager = database_manager_module.DatabaseManager

# Theme preferences file
THEME_PREFS_FILE = BASE_DIR / "config" / "theme_prefs.json"


def get_current_theme():
    """Get the current theme from preferences"""
    try:
        if THEME_PREFS_FILE.exists():
            with open(THEME_PREFS_FILE, 'r') as f:
                prefs = json.load(f)
                is_dark = prefs.get('dark_mode', True)
                return DARK_THEME if is_dark else LIGHT_THEME
    except:
        pass
    return DARK_THEME


class ProcessStageWidget:
    """Modern visual widget for a single process stage with theme support"""
    
    def __init__(self, parent, stage_name, position, theme):
        self.stage_name = stage_name
        self.position = position
        self.theme = theme
        self.lot_count = 0
        self.sensor_count = 0
        
        # Create modern card frame for this stage
        self.frame = tk.Frame(
            parent,
            bg=self.theme['surface'],
            cursor="hand2",
            highlightbackground=self.theme['border'],
            highlightthickness=1
        )
        self.frame.grid(row=position[0], column=position[1], 
                       padx=8, pady=8, sticky="nsew")
        
        # Colored accent bar at top
        self.accent_bar = tk.Frame(self.frame, bg=self.theme['accent'], height=4)
        self.accent_bar.pack(fill="x")
        
        # Content area with padding
        self.content = tk.Frame(self.frame, bg=self.theme['surface'])
        self.content.pack(fill="both", expand=True, padx=20, pady=16)
        
        # Stage icon and name in header
        header = tk.Frame(self.content, bg=self.theme['surface'])
        header.pack(fill="x", anchor="w")
        
        # Stage icon
        icon = self.get_stage_icon(stage_name)
        self.icon_label = tk.Label(
            header, text=icon,
            font=("Segoe UI", 16),
            bg=self.theme['surface'], fg=self.theme['accent']
        )
        self.icon_label.pack(side="left", padx=(0, 10))
        
        # Stage name
        self.name_label = tk.Label(
            header, text=stage_name,
            font=("Segoe UI Semibold", 11),
            bg=self.theme['surface'], fg=self.theme['text'],
            anchor="w"
        )
        self.name_label.pack(side="left", fill="x", expand=True)
        
        # Counts section
        counts_container = tk.Frame(self.content, bg=self.theme['surface'])
        counts_container.pack(fill="x", pady=(12, 0))
        
        # Lot count (larger, primary metric)
        lot_frame = tk.Frame(counts_container, bg=self.theme['surface'])
        lot_frame.pack(fill="x", pady=(0, 6))
        
        self.lot_count_label = tk.Label(
            lot_frame, text="0",
            font=("Segoe UI Bold", 24),
            bg=self.theme['surface'], fg=self.theme['accent']
        )
        self.lot_count_label.pack(side="left")
        
        tk.Label(
            lot_frame, text=" lots",
            font=FONT_BODY,
            bg=self.theme['surface'], fg=self.theme['text_secondary']
        ).pack(side="left", pady=6)
        
        # Sensor count (secondary metric)
        sensor_frame = tk.Frame(counts_container, bg=self.theme['surface'])
        sensor_frame.pack(fill="x")
        
        tk.Label(
            sensor_frame, text="📊",
            font=("Segoe UI", 10),
            bg=self.theme['surface'], fg=self.theme['muted']
        ).pack(side="left", padx=(0, 4))
        
        self.sensor_count_label = tk.Label(
            sensor_frame, text="0 sensors",
            font=FONT_SMALL,
            bg=self.theme['surface'], fg=self.theme['muted']
        )
        self.sensor_count_label.pack(side="left")
        
        # Click hint at bottom
        self.hint_label = tk.Label(
            self.content, text="Click for details →",
            font=("Segoe UI", 9),
            bg=self.theme['surface'], fg=self.theme['muted']
        )
        self.hint_label.pack(anchor="w", pady=(12, 0))
    
    @staticmethod
    def get_stage_icon(stage_name):
        """Get appropriate icon for each stage"""
        icons = {
            "Lot Entry": "📥",
            "Laser Marking and OCR": "🔤",
            "MR Chip Alignment": "⚡",
            "MR Chip Height": "📏",
            "SBB Resistance": "🔌",
            "Assembly Measurement": "📐",
            "QA Inspection 1": "🔍",
            "Top Molding": "🔧",
            "Cable Soldering": "🔥",
            "Cable Resistance": "⚡",
            "QA Inspection 2": "✓",
            "Bottom Molding": "🔩",
            "Inductance & Resistance": "📊",
            "QA Final": "✅",
            "Shipment": "📦"
        }
        return icons.get(stage_name, "⚙️")
    
    def update_counts(self, lot_count, sensor_count):
        """Update the displayed counts with animation effect"""
        self.lot_count = lot_count
        self.sensor_count = sensor_count
        
        # Update lot count
        self.lot_count_label.configure(text=str(lot_count))
        
        # Update sensor count
        self.sensor_count_label.configure(
            text=f"{sensor_count} sensor{'s' if sensor_count != 1 else ''}"
        )
        
        # Change colors based on activity level
        if lot_count > 0:
            self.lot_count_label.configure(fg=self.theme['accent'])
            self.accent_bar.configure(bg=self.theme['success'])
        else:
            self.lot_count_label.configure(fg=self.theme['muted'])
            self.accent_bar.configure(bg=self.theme['border'])
    
    def set_click_handler(self, callback):
        """Set click handler for this stage widget"""
        widgets = [
            self.frame, self.content, self.accent_bar,
            self.icon_label, self.name_label,
            self.lot_count_label, self.sensor_count_label, self.hint_label
        ]
        
        for widget in widgets:
            widget.bind("<Button-1>", lambda e: callback(self.stage_name))
            widget.bind("<Enter>", lambda e: self._on_hover_enter())
            widget.bind("<Leave>", lambda e: self._on_hover_leave())
    
    def _on_hover_enter(self):
        """Enhanced hover enter effect"""
        self.frame.configure(
            bg=self.theme['surface_2'],
            highlightbackground=self.theme['accent'],
            highlightthickness=2
        )
        self.content.configure(bg=self.theme['surface_2'])
        self.icon_label.configure(bg=self.theme['surface_2'])
        self.name_label.configure(bg=self.theme['surface_2'])
        self.lot_count_label.configure(bg=self.theme['surface_2'])
        self.sensor_count_label.configure(bg=self.theme['surface_2'])
        self.hint_label.configure(bg=self.theme['surface_2'], fg=self.theme['accent'])
        
        # Update all child frames
        for child in self.content.winfo_children():
            if isinstance(child, tk.Frame):
                child.configure(bg=self.theme['surface_2'])
                for subchild in child.winfo_children():
                    if isinstance(subchild, tk.Label):
                        subchild.configure(bg=self.theme['surface_2'])
    
    def _on_hover_leave(self):
        """Enhanced hover leave effect"""
        self.frame.configure(
            bg=self.theme['surface'],
            highlightbackground=self.theme['border'],
            highlightthickness=1
        )
        self.content.configure(bg=self.theme['surface'])
        self.icon_label.configure(bg=self.theme['surface'])
        self.name_label.configure(bg=self.theme['surface'])
        self.lot_count_label.configure(bg=self.theme['surface'])
        self.sensor_count_label.configure(bg=self.theme['surface'])
        self.hint_label.configure(bg=self.theme['surface'], fg=self.theme['muted'])
        
        # Update all child frames
        for child in self.content.winfo_children():
            if isinstance(child, tk.Frame):
                child.configure(bg=self.theme['surface'])
                for subchild in child.winfo_children():
                    if isinstance(subchild, tk.Label):
                        subchild.configure(bg=self.theme['surface'])


class RealtimeTrackingView:
    """Modern real-time tracking visualization with theme support"""
    
    def __init__(self, parent):
        self.parent = parent
        self.theme = get_current_theme()
        self.db_manager = DatabaseManager()
        self.stage_widgets = {}
        self.auto_refresh = True
        self.refresh_job = None
        self.canvas = None  # Initialize canvas reference
        
        self.create_ui()
        self.start_auto_refresh()
    
    def cleanup(self):
        """Clean up resources when view is destroyed"""
        try:
            # Stop auto-refresh
            self.auto_refresh = False
            if self.refresh_job:
                self.parent.after_cancel(self.refresh_job)
                self.refresh_job = None
            
            # Unbind mouse wheel if canvas exists
            if self.canvas and self.canvas.winfo_exists():
                self.canvas.unbind("<MouseWheel>")
        except:
            pass
    
    def create_ui(self):
        """Create the modern tracking visualization UI"""
        # Main container
        self.container = tk.Frame(self.parent, bg=self.theme['bg'])
        self.container.pack(fill="both", expand=True)
        
        # Header with controls
        header = tk.Frame(self.container, bg=self.theme['bg'])
        header.pack(fill="x", padx=32, pady=(24, 16))
        
        # Left side - title
        left_header = tk.Frame(header, bg=self.theme['bg'])
        left_header.pack(side="left")
        
        title_frame = tk.Frame(left_header, bg=self.theme['bg'])
        title_frame.pack(side="left")
        
        tk.Label(
            title_frame, text="📊",
            font=("Segoe UI", 18),
            bg=self.theme['bg'], fg=self.theme['accent']
        ).pack(side="left", padx=(0, 10))
        
        tk.Label(
            title_frame, text="Real-time Lot Tracking",
            font=("Segoe UI Semibold", 16),
            bg=self.theme['bg'], fg=self.theme['text']
        ).pack(side="left")
        
        # Right side - controls
        right_header = tk.Frame(header, bg=self.theme['bg'])
        right_header.pack(side="right")
        
        # Last updated indicator
        update_frame = tk.Frame(right_header, bg=self.theme['surface_2'])
        update_frame.pack(side="right", padx=(12, 0))
        
        tk.Label(
            update_frame, text="🕐",
            font=("Segoe UI", 10),
            bg=self.theme['surface_2'], fg=self.theme['muted']
        ).pack(side="left", padx=(8, 4), pady=6)
        
        self.last_updated_label = tk.Label(
            update_frame, text="--:--:--",
            font=FONT_SMALL,
            bg=self.theme['surface_2'], fg=self.theme['text']
        )
        self.last_updated_label.pack(side="left", padx=(0, 8), pady=6)
        
        # Refresh button
        refresh_btn = tk.Button(
            right_header, text="🔄 Refresh",
            command=self.refresh_data,
            font=FONT_BODY,
            bg=self.theme['primary'],
            fg="#ffffff",
            activebackground=self.theme['primary_h'],
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=16,
            pady=8
        )
        refresh_btn.pack(side="right", padx=(0, 8))
        refresh_btn.bind("<Enter>", lambda e: refresh_btn.configure(bg=self.theme['primary_h']))
        refresh_btn.bind("<Leave>", lambda e: refresh_btn.configure(bg=self.theme['primary']))
        
        # Auto-refresh toggle
        self.auto_refresh_var = tk.BooleanVar(value=True)
        
        toggle_frame = tk.Frame(right_header, bg=self.theme['surface_2'])
        toggle_frame.pack(side="right")
        
        refresh_check = tk.Checkbutton(
            toggle_frame, text="Auto-refresh",
            variable=self.auto_refresh_var,
            command=self.toggle_auto_refresh,
            bg=self.theme['surface_2'],
            fg=self.theme['text'],
            selectcolor=self.theme['surface'],
            activebackground=self.theme['surface_2'],
            activeforeground=self.theme['text'],
            font=FONT_SMALL,
            bd=0,
            highlightthickness=0
        )
        refresh_check.pack(padx=12, pady=6)
        
        # Summary stats bar
        self.create_summary_bar()
        
        # Scrollable canvas for process stages
        canvas_frame = tk.Frame(self.container, bg=self.theme['bg'])
        canvas_frame.pack(fill="both", expand=True, padx=32, pady=(0, 32))
        
        self.canvas = tk.Canvas(canvas_frame, bg=self.theme['bg'], highlightthickness=0)
        
        # Configure scrollbar style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Vertical.TScrollbar",
                       background=self.theme['surface'],
                       bordercolor=self.theme['surface'],
                       arrowcolor=self.theme['text'],
                       troughcolor=self.theme['bg'])
        
        scrollbar_y = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        
        self.stage_grid = tk.Frame(self.canvas, bg=self.theme['bg'])
        
        self.stage_grid.bind("<Configure>", 
                            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        canvas_window = self.canvas.create_window((0, 0), window=self.stage_grid, anchor="nw")
        self.canvas.bind("<Configure>", 
                        lambda e: self.canvas.itemconfig(canvas_window, width=e.width - 20))
        
        self.canvas.configure(yscrollcommand=scrollbar_y.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar_y.pack(side="right", fill="y")
        
        # Mouse wheel scrolling - use regular bind instead of bind_all
        def on_mousewheel(event):
            # Check if canvas still exists before scrolling
            try:
                if self.canvas.winfo_exists():
                    self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except:
                pass
        
        # Bind to canvas only (not globally)
        self.canvas.bind("<MouseWheel>", on_mousewheel)
        
        # Also bind to the stage_grid for scrolling when mouse is over content
        self.stage_grid.bind("<MouseWheel>", on_mousewheel)
        
        # Create process stage widgets in a responsive grid layout (3 columns)
        self.create_stage_widgets()
        
        # Initial data load
        self.refresh_data()
    
    def create_summary_bar(self):
        """Create summary statistics bar"""
        summary = tk.Frame(self.container, bg=self.theme['surface'])
        summary.pack(fill="x", padx=32, pady=(0, 20))
        
        # Summary cards
        try:
            stats = self.db_manager.get_production_statistics()
            
            summary_items = [
                ("📦", "Total Lots", stats.get('total_lots', 0), self.theme['accent']),
                ("⏳", "In Progress", stats.get('in_progress', 0), self.theme['warning']),
                ("✅", "Completed", stats.get('completed', 0), self.theme['success']),
            ]
            
            for idx, (icon, label, value, color) in enumerate(summary_items):
                card = tk.Frame(summary, bg=self.theme['surface'])
                card.pack(side="left", expand=True, fill="both", padx=2, pady=2)
                
                # Icon
                tk.Label(
                    card, text=icon,
                    font=("Segoe UI", 20),
                    bg=self.theme['surface'], fg=color
                ).pack(side="left", padx=(20, 12), pady=16)
                
                # Stats
                stats_frame = tk.Frame(card, bg=self.theme['surface'])
                stats_frame.pack(side="left", pady=16)
                
                tk.Label(
                    stats_frame, text=str(value),
                    font=("Segoe UI Bold", 20),
                    bg=self.theme['surface'], fg=self.theme['text']
                ).pack(anchor="w")
                
                tk.Label(
                    stats_frame, text=label,
                    font=FONT_SMALL,
                    bg=self.theme['surface'], fg=self.theme['muted']
                ).pack(anchor="w")
        
        except Exception as e:
            tk.Label(
                summary, text=f"Unable to load summary: {e}",
                font=FONT_SMALL,
                bg=self.theme['surface'], fg=self.theme['danger']
            ).pack(padx=20, pady=16)
    
    def create_stage_widgets(self):
        """Create modern widgets for all process stages"""
        cols = 3
        
        # Configure grid weights for responsive layout
        for i in range(cols):
            self.stage_grid.grid_columnconfigure(i, weight=1, uniform="stages")
        
        # Create stage widget for each process
        for idx, stage in enumerate(PROCESS_STAGES):
            row = idx // cols
            col = idx % cols
            
            widget = ProcessStageWidget(self.stage_grid, stage, (row, col), self.theme)
            widget.set_click_handler(self.show_stage_details)
            self.stage_widgets[stage] = widget
    
    def refresh_data(self):
        """Refresh tracking data from database with visual feedback"""
        try:
            # Get lot counts by process
            lot_counts = self.db_manager.get_lot_counts_by_process()
            sensor_counts = self.db_manager.get_sensor_counts_by_process()
            
            # Update each stage widget
            for stage_name, widget in self.stage_widgets.items():
                lot_count = lot_counts.get(stage_name, 0)
                sensor_count = sensor_counts.get(stage_name, 0)
                widget.update_counts(lot_count, sensor_count)
            
            # Update last updated time
            current_time = datetime.now().strftime("%I:%M:%S %p")
            self.last_updated_label.configure(text=current_time)
        
        except Exception as e:
            print(f"Error refreshing data: {e}")
            self.last_updated_label.configure(text="Error")
    
    def start_auto_refresh(self):
        """Start automatic data refresh"""
        if self.auto_refresh and self.auto_refresh_var.get():
            self.refresh_data()
            self.refresh_job = self.parent.after(REFRESH_INTERVAL, self.start_auto_refresh)
    
    def stop_auto_refresh(self):
        """Stop automatic data refresh"""
        if self.refresh_job:
            self.parent.after_cancel(self.refresh_job)
            self.refresh_job = None
    
    def toggle_auto_refresh(self):
        """Toggle auto-refresh on/off"""
        self.auto_refresh = self.auto_refresh_var.get()
        if self.auto_refresh:
            self.start_auto_refresh()
        else:
            self.stop_auto_refresh()
    
    def show_stage_details(self, stage_name):
        """Show modern detailed view of lots in a specific stage"""
        from tkinter import Toplevel
        
        detail_win = Toplevel(self.parent)
        detail_win.title(f"Lots in {stage_name}")
        detail_win.configure(bg=self.theme['bg'])
        detail_win.geometry("1000x650")
        
        # Center the window
        detail_win.update_idletasks()
        x = (detail_win.winfo_screenwidth() // 2) - (500)
        y = (detail_win.winfo_screenheight() // 2) - (325)
        detail_win.geometry(f"+{x}+{y}")
        
        # Header
        header = tk.Frame(detail_win, bg=self.theme['surface'])
        header.pack(fill="x")
        
        header_content = tk.Frame(header, bg=self.theme['surface'])
        header_content.pack(fill="x", padx=24, pady=20)
        
        # Icon - use static method instead of creating widget instance
        icon = ProcessStageWidget.get_stage_icon(stage_name)
        tk.Label(
            header_content, text=icon,
            font=("Segoe UI", 24),
            bg=self.theme['surface'], fg=self.theme['accent']
        ).pack(side="left", padx=(0, 12))
        
        # Title and count
        title_frame = tk.Frame(header_content, bg=self.theme['surface'])
        title_frame.pack(side="left", fill="x", expand=True)
        
        tk.Label(
            title_frame, text=f"Lots in {stage_name}",
            font=("Segoe UI Semibold", 16),
            bg=self.theme['surface'], fg=self.theme['text']
        ).pack(anchor="w")
        
        # Get lots for this stage - Debug to see what we're getting
        all_lots = self.db_manager.get_all_active_lots()
        stage_lots = [lot for lot in all_lots if lot.get('current_process') == stage_name]
        
        # Count label
        tk.Label(
            title_frame, text=f"{len(stage_lots)} lot{'s' if len(stage_lots) != 1 else ''} found",
            font=FONT_SMALL,
            bg=self.theme['surface'], fg=self.theme['muted']
        ).pack(anchor="w", pady=(4, 0))
        
        # Table frame
        table_frame = tk.Frame(detail_win, bg=self.theme['bg'])
        table_frame.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        
        # Configure treeview style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Detail.Treeview",
                       background=self.theme['surface'],
                       fieldbackground=self.theme['surface'],
                       foreground=self.theme['text'],
                       rowheight=35,
                       font=FONT_BODY,
                       borderwidth=0)
        style.configure("Detail.Treeview.Heading",
                       background=self.theme['surface_2'],
                       foreground=self.theme['text'],
                       font=("Segoe UI Semibold", 10),
                       borderwidth=0,
                       relief="flat")
        style.map("Detail.Treeview",
                 background=[("selected", self.theme['primary'])],
                 foreground=[("selected", "#ffffff")])
        
        # Create treeview with 3 columns
        tree = ttk.Treeview(
            table_frame,
            columns=("lot_number", "sensor_id", "entry_date"),
            show="headings",
            style="Detail.Treeview"
        )
        
        # Configure column headings
        tree.heading("lot_number", text="LOT NUMBER")
        tree.heading("sensor_id", text="SENSOR ID")
        tree.heading("entry_date", text="ENTRY DATE")
        
        # Configure column widths
        tree.column("lot_number", width=250, anchor="w")
        tree.column("sensor_id", width=250, anchor="w")
        tree.column("entry_date", width=420, anchor="w")
        
        tree.pack(side="left", fill="both", expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Populate lots - ensure we're getting the right data
        if stage_lots:
            for lot in stage_lots:
                # Extract values with defaults
                lot_num = lot.get('lot_number', 'N/A')
                sensor = lot.get('sensor_id', 'N/A')
                entry = lot.get('entry_date', 'N/A')
                
                # Insert into tree with explicit column order
                tree.insert("", "end", values=(lot_num, sensor, entry))
                
            # Add info label
            info_frame = tk.Frame(detail_win, bg=self.theme['bg'])
            info_frame.pack(fill="x", padx=24, pady=(0, 12))
            
            tk.Label(
                info_frame, text=f"ℹ️ Showing {len(stage_lots)} lot(s) currently in {stage_name}",
                font=FONT_SMALL,
                bg=self.theme['bg'], fg=self.theme['muted']
            ).pack(side="left")
        else:
            # Show empty state message in the tree area
            tree.pack_forget()
            scrollbar.pack_forget()
            
            empty_frame = tk.Frame(table_frame, bg=self.theme['surface'])
            empty_frame.place(relx=0.5, rely=0.5, anchor="center")
            
            tk.Label(
                empty_frame, text="📭",
                font=("Segoe UI", 48),
                bg=self.theme['surface'], fg=self.theme['muted']
            ).pack()
            
            tk.Label(
                empty_frame, text="No lots in this stage",
                font=FONT_H2,
                bg=self.theme['surface'], fg=self.theme['muted']
            ).pack(pady=(8, 0))
            
            tk.Label(
                empty_frame, text="Lots will appear here when they enter this process stage",
                font=FONT_SMALL,
                bg=self.theme['surface'], fg=self.theme['muted']
            ).pack(pady=(4, 0))
        
        # Bottom button bar
        button_bar = tk.Frame(detail_win, bg=self.theme['bg'])
        button_bar.pack(fill="x", padx=24, pady=(0, 20))
        
        # Export button (if needed later)
        if stage_lots:
            export_btn = tk.Button(
                button_bar, text="📋 Copy to Clipboard",
                command=lambda: self.copy_lots_to_clipboard(stage_lots),
                bg=self.theme['surface_2'],
                fg=self.theme['text'],
                activebackground=self.theme['surface_3'],
                activeforeground=self.theme['text'],
                relief="flat",
                font=FONT_BODY,
                cursor="hand2",
                padx=20,
                pady=10
            )
            export_btn.pack(side="left")
            export_btn.bind("<Enter>", lambda e: export_btn.configure(bg=self.theme['surface_3']))
            export_btn.bind("<Leave>", lambda e: export_btn.configure(bg=self.theme['surface_2']))
        
        # Close button
        close_btn = tk.Button(
            button_bar, text="Close",
            command=detail_win.destroy,
            bg=self.theme['primary'],
            fg="#ffffff",
            activebackground=self.theme['primary_h'],
            activeforeground="#ffffff",
            relief="flat",
            font=FONT_BODY,
            cursor="hand2",
            padx=24,
            pady=10
        )
        close_btn.pack(side="right")
        close_btn.bind("<Enter>", lambda e: close_btn.configure(bg=self.theme['primary_h']))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(bg=self.theme['primary']))
    
    def copy_lots_to_clipboard(self, lots):
        """Copy lot information to clipboard"""
        try:
            # Create text representation
            text_lines = ["LOT NUMBER\tSENSOR ID\tENTRY DATE"]
            for lot in lots:
                text_lines.append(f"{lot.get('lot_number', 'N/A')}\t{lot.get('sensor_id', 'N/A')}\t{lot.get('entry_date', 'N/A')}")
            
            clipboard_text = "\n".join(text_lines)
            
            # Copy to clipboard
            self.parent.clipboard_clear()
            self.parent.clipboard_append(clipboard_text)
            
            print(f"Copied {len(lots)} lot(s) to clipboard")
        except Exception as e:
            print(f"Error copying to clipboard: {e}")
    
    def destroy(self):
        """Clean up resources"""
        self.stop_auto_refresh()
        if hasattr(self, 'container'):
            self.container.destroy()


if __name__ == "__main__":
    # Test the tracking view
    root = tk.Tk()
    root.title("Real-time Tracking Test")
    root.geometry("1200x800")
    
    theme = get_current_theme()
    root.configure(bg=theme['bg'])
    
    view = RealtimeTrackingView(root)
    
    root.mainloop()
