"""
Real-time Lot Tracking Visualization
Visual display of lots moving through manufacturing processes
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import sys
from pathlib import Path
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
COLOR_BG = system_config.COLOR_BG
COLOR_SURFACE = system_config.COLOR_SURFACE
COLOR_SURFACE_2 = system_config.COLOR_SURFACE_2
COLOR_PRIMARY = system_config.COLOR_PRIMARY
COLOR_ACCENT = system_config.COLOR_ACCENT
COLOR_SUCCESS = system_config.COLOR_SUCCESS
COLOR_TEXT = system_config.COLOR_TEXT
COLOR_MUTED = system_config.COLOR_MUTED
FONT_H2 = system_config.FONT_H2
FONT_BODY = system_config.FONT_BODY
FONT_SMALL = system_config.FONT_SMALL
FONT_H3 = system_config.FONT_H3
PROCESS_STAGES = system_config.PROCESS_STAGES
REFRESH_INTERVAL = system_config.REFRESH_INTERVAL

DatabaseManager = database_manager_module.DatabaseManager


class ProcessStageWidget:
    """Visual widget for a single process stage"""
    
    def __init__(self, parent, stage_name, position):
        self.stage_name = stage_name
        self.position = position
        self.lot_count = 0
        self.sensor_count = 0
        
        # Create frame for this stage
        self.frame = tk.Frame(parent, bg=COLOR_SURFACE, cursor="hand2")
        self.frame.grid(row=position[0], column=position[1], 
                       padx=4, pady=4, sticky="nsew")
        
        # Accent bar
        accent_bar = tk.Frame(self.frame, bg=COLOR_ACCENT, width=5)
        accent_bar.pack(side="left", fill="y")
        
        # Content area
        content = tk.Frame(self.frame, bg=COLOR_SURFACE)
        content.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        # Stage name
        self.name_label = tk.Label(
            content, text=stage_name,
            font=FONT_H3, bg=COLOR_SURFACE, fg=COLOR_TEXT,
            anchor="w", wraplength=180
        )
        self.name_label.pack(anchor="w")
        
        # Counts
        count_frame = tk.Frame(content, bg=COLOR_SURFACE)
        count_frame.pack(anchor="w", pady=(6, 0))
        
        self.lot_count_label = tk.Label(
            count_frame, text="0 lots",
            font=FONT_BODY, bg=COLOR_SURFACE, fg=COLOR_ACCENT
        )
        self.lot_count_label.pack(side="left", padx=(0, 8))
        
        self.sensor_count_label = tk.Label(
            count_frame, text="0 sensors",
            font=FONT_SMALL, bg=COLOR_SURFACE, fg=COLOR_MUTED
        )
        self.sensor_count_label.pack(side="left")
    
    def update_counts(self, lot_count, sensor_count):
        """Update the displayed counts"""
        self.lot_count = lot_count
        self.sensor_count = sensor_count
        
        self.lot_count_label.configure(text=f"{lot_count} lot{'s' if lot_count != 1 else ''}")
        self.sensor_count_label.configure(text=f"{sensor_count} sensor{'s' if sensor_count != 1 else ''}")
        
        # Change color based on activity
        if lot_count > 0:
            self.lot_count_label.configure(fg=COLOR_ACCENT)
        else:
            self.lot_count_label.configure(fg=COLOR_MUTED)
    
    def set_click_handler(self, callback):
        """Set click handler for this stage widget"""
        widgets = [self.frame, self.name_label, self.lot_count_label, self.sensor_count_label]
        
        for widget in widgets:
            widget.bind("<Button-1>", lambda e: callback(self.stage_name))
            widget.bind("<Enter>", lambda e: self._on_hover_enter())
            widget.bind("<Leave>", lambda e: self._on_hover_leave())
    
    def _on_hover_enter(self):
        """Handle hover enter"""
        self.frame.configure(bg=COLOR_SURFACE_2)
        for widget in self.frame.winfo_children():
            if isinstance(widget, tk.Frame) and widget.cget("width") != 5:
                widget.configure(bg=COLOR_SURFACE_2)
                for child in widget.winfo_children():
                    if isinstance(child, (tk.Label, tk.Frame)):
                        try:
                            child.configure(bg=COLOR_SURFACE_2)
                        except:
                            pass
    
    def _on_hover_leave(self):
        """Handle hover leave"""
        self.frame.configure(bg=COLOR_SURFACE)
        for widget in self.frame.winfo_children():
            if isinstance(widget, tk.Frame) and widget.cget("width") != 5:
                widget.configure(bg=COLOR_SURFACE)
                for child in widget.winfo_children():
                    if isinstance(child, (tk.Label, tk.Frame)):
                        try:
                            child.configure(bg=COLOR_SURFACE)
                        except:
                            pass


class RealtimeTrackingView:
    """Main real-time tracking visualization window"""
    
    def __init__(self, parent):
        self.parent = parent
        self.db_manager = DatabaseManager()
        self.stage_widgets = {}
        self.auto_refresh = True
        self.refresh_job = None
        
        self.create_ui()
        self.start_auto_refresh()
    
    def create_ui(self):
        """Create the tracking visualization UI"""
        # Main container
        self.container = tk.Frame(self.parent, bg=COLOR_BG)
        self.container.pack(fill="both", expand=True)
        
        # Header
        header = tk.Frame(self.container, bg=COLOR_BG)
        header.pack(fill="x", padx=20, pady=(20, 10))
        
        tk.Label(
            header, text="Real-time Lot Tracking",
            font=FONT_H2, bg=COLOR_BG, fg=COLOR_TEXT
        ).pack(side="left")
        
        # Last updated label
        self.last_updated_label = tk.Label(
            header, text="Last updated: --:--:--",
            font=FONT_SMALL, bg=COLOR_BG, fg=COLOR_MUTED
        )
        self.last_updated_label.pack(side="right")
        
        # Auto-refresh toggle
        self.auto_refresh_var = tk.BooleanVar(value=True)
        refresh_check = tk.Checkbutton(
            header, text="Auto-refresh",
            variable=self.auto_refresh_var,
            command=self.toggle_auto_refresh,
            bg=COLOR_BG, fg=COLOR_TEXT,
            selectcolor=COLOR_SURFACE,
            activebackground=COLOR_BG,
            activeforeground=COLOR_TEXT,
            font=FONT_SMALL
        )
        refresh_check.pack(side="right", padx=(0, 10))
        
        # Scrollable canvas for process stages
        canvas_frame = tk.Frame(self.container, bg=COLOR_BG)
        canvas_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        self.canvas = tk.Canvas(canvas_frame, bg=COLOR_BG, highlightthickness=0)
        scrollbar_y = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        scrollbar_x = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        
        self.stage_grid = tk.Frame(self.canvas, bg=COLOR_BG)
        
        self.stage_grid.bind("<Configure>", 
                            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        canvas_window = self.canvas.create_window((0, 0), window=self.stage_grid, anchor="nw")
        self.canvas.bind("<Configure>", 
                        lambda e: self.canvas.itemconfig(canvas_window, width=e.width))
        
        self.canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x.pack(side="bottom", fill="x")
        
        # Create process stage widgets in a grid layout (3 columns)
        self.create_stage_widgets()
        
        # Initial data load
        self.refresh_data()
    
    def create_stage_widgets(self):
        """Create widgets for all process stages"""
        cols = 3
        
        # Configure grid weights
        for i in range(cols):
            self.stage_grid.grid_columnconfigure(i, weight=1, uniform="stages")
        
        # Create stage widget for each process
        for idx, stage in enumerate(PROCESS_STAGES):
            row = idx // cols
            col = idx % cols
            
            widget = ProcessStageWidget(self.stage_grid, stage, (row, col))
            widget.set_click_handler(self.show_stage_details)
            self.stage_widgets[stage] = widget
    
    def refresh_data(self):
        """Refresh tracking data from database"""
        from datetime import datetime
        
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
            self.last_updated_label.configure(text=f"Last updated: {current_time}")
        
        except Exception as e:
            print(f"Error refreshing data: {e}")
    
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
        """Show detailed view of lots in a specific stage"""
        from tkinter import Toplevel
        
        detail_win = Toplevel(self.parent)
        detail_win.title(f"Lots in {stage_name}")
        detail_win.configure(bg=COLOR_BG)
        detail_win.geometry("800x600")
        
        # Header
        tk.Label(
            detail_win, text=f"Lots in {stage_name}",
            font=FONT_H2, bg=COLOR_BG, fg=COLOR_TEXT
        ).pack(pady=(20, 10), padx=20, anchor="w")
        
        # Create treeview for lots
        tree_frame = tk.Frame(detail_win, bg=COLOR_BG)
        tree_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        style = ttk.Style()
        style.configure("Treeview", 
                       background=COLOR_SURFACE, 
                       fieldbackground=COLOR_SURFACE,
                       foreground=COLOR_TEXT, 
                       rowheight=28, 
                       font=FONT_BODY, 
                       borderwidth=0)
        style.configure("Treeview.Heading", font=FONT_SMALL)
        style.map("Treeview", background=[("selected", COLOR_PRIMARY)])
        
        tree = ttk.Treeview(
            tree_frame, 
            columns=("lot_number", "sensor_id", "entry_date"),
            show="headings", 
            height=20
        )
        tree.heading("lot_number", text="Lot Number")
        tree.heading("sensor_id", text="Sensor ID")
        tree.heading("entry_date", text="Entry Date")
        
        tree.column("lot_number", width=200)
        tree.column("sensor_id", width=200)
        tree.column("entry_date", width=350)
        
        tree.pack(side="left", fill="both", expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Load lots for this stage
        all_lots = self.db_manager.get_all_active_lots()
        stage_lots = [lot for lot in all_lots if lot['current_process'] == stage_name]
        
        for lot in stage_lots:
            tree.insert("", "end", values=(
                lot['lot_number'],
                lot['sensor_id'],
                lot.get('entry_date', 'N/A')
            ))
        
        # Close button
        close_btn = tk.Button(
            detail_win, text="Close",
            command=detail_win.destroy,
            bg=COLOR_SURFACE, fg=COLOR_TEXT,
            activebackground=COLOR_SURFACE_2,
            relief="flat", font=FONT_BODY,
            cursor="hand2"
        )
        close_btn.pack(pady=(0, 20), ipadx=20, ipady=8)
    
    def destroy(self):
        """Clean up resources"""
        self.stop_auto_refresh()
        self.container.destroy()


if __name__ == "__main__":
    # Test the tracking view
    root = tk.Tk()
    root.title("Real-time Tracking Test")
    root.geometry("1200x800")
    root.configure(bg=COLOR_BG)
    
    view = RealtimeTrackingView(root)
    
    root.mainloop()
