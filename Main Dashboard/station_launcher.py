"""
Station-Specific Process Launcher for BMS Lot Tracking System
Each station is dedicated to ONE process - scan lot to auto-launch the correct program
"""

import tkinter as tk
from tkinter import messagebox, ttk
import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import importlib.util

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

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

database_manager = import_module_from_path(
    "database_manager",
    BASE_DIR / "config" / "database_manager.py"
)

PYTHON_EXE = system_config.PYTHON_EXE
PROCESS_PROGRAMS = system_config.PROCESS_PROGRAMS
STATION_CONFIG_FILE = BASE_DIR / "config" / "station_config.json"

DatabaseManager = database_manager.DatabaseManager


class StationLauncher:
    """Station-specific launcher that auto-launches process programs when lot is scanned"""
    
    def __init__(self, parent_frame, theme, status_callback=None):
        self.parent = parent_frame
        self.theme = theme
        self.status_callback = status_callback
        self.db_manager = DatabaseManager()
        
        # Load station configuration
        self.station_id = self.load_station_id()
        self.station_config = self.load_station_config()
        
        # If no station ID set, prompt user to configure
        if not self.station_id:
            self.show_station_setup()
        else:
            self.show_scanner_interface()
    
    def load_station_id(self):
        """Load saved station ID from local config"""
        local_config = BASE_DIR / "config" / "local_station.json"
        if local_config.exists():
            try:
                with open(local_config, 'r') as f:
                    data = json.load(f)
                    return data.get('station_id')
            except:
                pass
        return None
    
    def save_station_id(self, station_id):
        """Save station ID to local config"""
        local_config = BASE_DIR / "config" / "local_station.json"
        try:
            with open(local_config, 'w') as f:
                json.dump({'station_id': station_id}, f, indent=2)
            return True
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save station configuration:\n\n{str(e)}")
            return False
    
    def load_station_config(self):
        """Load station mapping configuration"""
        try:
            with open(STATION_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get('station_mapping', {})
        except Exception as e:
            messagebox.showerror("Config Error", 
                               f"Failed to load station configuration:\n\n{str(e)}")
            return {}
    
    def show_station_setup(self):
        """Show station setup interface (first-time configuration)"""
        # Clear parent
        for widget in self.parent.winfo_children():
            widget.destroy()
        
        # Setup container
        setup_container = tk.Frame(self.parent, bg=self.theme['bg'])
        setup_container.place(relx=0.5, rely=0.5, anchor="center", width=600, height=500)
        
        # Title
        tk.Label(
            setup_container,
            text="🏭 Station Configuration",
            font=("Segoe UI Semibold", 24),
            bg=self.theme['bg'],
            fg=self.theme['text']
        ).pack(pady=(40, 10))
        
        tk.Label(
            setup_container,
            text="Configure this computer as a dedicated station",
            font=("Segoe UI", 11),
            bg=self.theme['bg'],
            fg=self.theme['muted']
        ).pack(pady=(0, 40))
        
        # Station selection card
        card = tk.Frame(setup_container, bg=self.theme['surface'])
        card.pack(fill="both", expand=True, padx=60, pady=(0, 40))
        
        tk.Label(
            card,
            text="Select Station Type:",
            font=("Segoe UI Semibold", 12),
            bg=self.theme['surface'],
            fg=self.theme['text']
        ).pack(pady=(30, 10), padx=30, anchor="w")
        
        # Station dropdown preparation
        station_var = tk.StringVar()
        station_options = []
        
        # Add station cards
        for station_id in sorted(self.station_config.keys()):
            info = self.station_config[station_id]
            station_display = f"{station_id} - {info['name']}"
            station_options.append(station_display)
        
        combo = ttk.Combobox(
            card,
            textvariable=station_var,
            values=station_options,
            state="readonly",
            font=("Segoe UI", 11),
            width=45
        )
        combo.pack(pady=(0, 10), padx=30, fill="x")
        
        if station_options:
            combo.current(0)
        
        # Description
        desc_label = tk.Label(
            card,
            text="",
            font=("Segoe UI", 9),
            bg=self.theme['surface'],
            fg=self.theme['muted'],
            wraplength=450,
            justify="left"
        )
        desc_label.pack(pady=(0, 30), padx=30, anchor="w")
        
        def update_description(event=None):
            selected = station_var.get()
            if selected:
                station_id = selected.split(" - ")[0]
                if station_id in self.station_config:
                    info = self.station_config[station_id]
                    desc = f"Process: {info['process']}\n{info['description']}"
                    desc_label.config(text=desc)
        
        combo.bind("<<ComboboxSelected>>", update_description)
        update_description()  # Initial description
        
        # Save button
        def save_config():
            selected = station_var.get()
            if not selected:
                messagebox.showwarning("Selection Required", "Please select a station type")
                return
            
            station_id = selected.split(" - ")[0]
            if self.save_station_id(station_id):
                self.station_id = station_id
                messagebox.showinfo("Success", 
                                  f"Station configured as:\n\n{selected}\n\nThis computer is now dedicated to this process.")
                self.show_scanner_interface()
        
        save_btn = tk.Button(
            card,
            text="Save Configuration",
            command=save_config,
            font=("Segoe UI Semibold", 11),
            bg=self.theme['primary'],
            fg="#ffffff",
            activebackground=self.theme['primary_h'],
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=30,
            pady=12
        )
        save_btn.pack(pady=(0, 30))
        save_btn.bind("<Enter>", lambda e: save_btn.configure(bg=self.theme['primary_h']))
        save_btn.bind("<Leave>", lambda e: save_btn.configure(bg=self.theme['primary']))
    
    def show_scanner_interface(self):
        """Show the main lot scanner interface"""
        # Clear parent
        for widget in self.parent.winfo_children():
            widget.destroy()
        
        # Get station info
        station_info = self.station_config.get(self.station_id, {})
        station_name = station_info.get('name', self.station_id)
        process_name = station_info.get('process', 'Unknown')
        process_desc = station_info.get('description', '')
        
        # Main container
        main_container = tk.Frame(self.parent, bg=self.theme['bg'])
        main_container.pack(fill="both", expand=True)
        
        # Header section
        header = tk.Frame(main_container, bg=self.theme['surface'])
        header.pack(fill="x", pady=(0, 2))
        
        header_inner = tk.Frame(header, bg=self.theme['surface'])
        header_inner.pack(pady=30, padx=40)
        
        # Station badge
        badge_frame = tk.Frame(header_inner, bg=self.theme['primary'])
        badge_frame.pack()
        
        tk.Label(
            badge_frame,
            text=f"  {self.station_id}  ",
            font=("Segoe UI Black", 14),
            bg=self.theme['primary'],
            fg="#ffffff"
        ).pack(padx=20, pady=8)
        
        # Station name
        tk.Label(
            header_inner,
            text=station_name,
            font=("Segoe UI Semibold", 20),
            bg=self.theme['surface'],
            fg=self.theme['text']
        ).pack(pady=(16, 4))
        
        # Process info
        tk.Label(
            header_inner,
            text=f"Process: {process_name}",
            font=("Segoe UI", 12),
            bg=self.theme['surface'],
            fg=self.theme['accent']
        ).pack(pady=(0, 4))
        
        tk.Label(
            header_inner,
            text=process_desc,
            font=("Segoe UI", 10),
            bg=self.theme['surface'],
            fg=self.theme['muted']
        ).pack()
        
        # Scanner section
        scanner_container = tk.Frame(main_container, bg=self.theme['bg'])
        scanner_container.pack(fill="both", expand=True, pady=40, padx=60)
        
        # Scanner card
        scanner_card = tk.Frame(scanner_container, bg=self.theme['surface'])
        scanner_card.place(relx=0.5, rely=0.5, anchor="center", width=700, height=400)
        
        # Scanner icon/instruction
        tk.Label(
            scanner_card,
            text="📦",
            font=("Segoe UI", 80),
            bg=self.theme['surface'],
            fg=self.theme['primary']
        ).pack(pady=(50, 20))
        
        tk.Label(
            scanner_card,
            text="Scan Lot Number to Begin",
            font=("Segoe UI Semibold", 18),
            bg=self.theme['surface'],
            fg=self.theme['text']
        ).pack(pady=(0, 10))
        
        tk.Label(
            scanner_card,
            text="Use barcode scanner or type lot number below",
            font=("Segoe UI", 11),
            bg=self.theme['surface'],
            fg=self.theme['muted']
        ).pack(pady=(0, 30))
        
        # Lot entry field
        entry_frame = tk.Frame(scanner_card, bg=self.theme['surface'])
        entry_frame.pack(pady=(0, 20))
        
        lot_entry = tk.Entry(
            entry_frame,
            font=("Segoe UI", 16),
            bg=self.theme['surface_2'],
            fg=self.theme['text'],
            insertbackground=self.theme['text'],
            relief="flat",
            bd=0,
            highlightthickness=2,
            highlightbackground=self.theme['border'],
            highlightcolor=self.theme['primary'],
            width=30
        )
        lot_entry.pack(ipady=12, padx=4, pady=4)
        
        # Ensure focus after short delay (allow UI to render first)
        def set_focus():
            try:
                lot_entry.focus_force()
                lot_entry.icursor(tk.END)
            except:
                pass
        
        scanner_card.after(100, set_focus)
        
        # Click anywhere on card to focus entry
        def focus_entry(event=None):
            lot_entry.focus_force()
        
        scanner_card.bind("<Button-1>", focus_entry)
        entry_frame.bind("<Button-1>", focus_entry)
        
        # Status message
        status_var = tk.StringVar(value="")
        status_label = tk.Label(
            scanner_card,
            textvariable=status_var,
            font=("Segoe UI", 10),
            bg=self.theme['surface'],
            fg=self.theme['muted']
        )
        status_label.pack()
        
        # Launch function
        def launch_process():
            lot_number = lot_entry.get().strip().upper()
            
            if not lot_number:
                status_var.set("⚠ Please enter a lot number")
                status_label.config(fg=self.theme['warning'])
                return
            
            # Validate lot exists in database
            try:
                lot_info = self.db_manager.get_lot_info(lot_number)
                
                if not lot_info:
                    status_var.set(f"❌ Lot {lot_number} not found in system")
                    status_label.config(fg=self.theme['danger'])
                    lot_entry.delete(0, tk.END)
                    return
                
                # Get process program path
                program_path = PROCESS_PROGRAMS.get(process_name)
                
                if not program_path or not os.path.exists(program_path):
                    status_var.set(f"❌ Program not found: {process_name}")
                    status_label.config(fg=self.theme['danger'])
                    return
                
                # Launch the process program
                status_var.set(f"✓ Launching {process_name}...")
                status_label.config(fg=self.theme['success'])
                
                folder = os.path.dirname(program_path)
                subprocess.Popen([PYTHON_EXE, program_path], cwd=folder)
                
                # Update status callback
                if self.status_callback:
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    self.status_callback(f"✓ Launched {process_name} for lot {lot_number} at {timestamp}")
                
                # Clear entry and reset
                lot_entry.delete(0, tk.END)
                
                # Reset status after 2 seconds
                scanner_card.after(2000, lambda: status_var.set(""))
                
            except Exception as e:
                status_var.set(f"❌ Error: {str(e)}")
                status_label.config(fg=self.theme['danger'])
                print(f"Launch error: {str(e)}")
        
        # Bind Enter key to launch
        lot_entry.bind("<Return>", lambda e: launch_process())
        
        # Manual launch button (optional)
        launch_btn = tk.Button(
            scanner_card,
            text="Launch Process",
            command=launch_process,
            font=("Segoe UI Semibold", 11),
            bg=self.theme['primary'],
            fg="#ffffff",
            activebackground=self.theme['primary_h'],
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=30,
            pady=10
        )
        launch_btn.pack(pady=(10, 0))
        launch_btn.bind("<Enter>", lambda e: launch_btn.configure(bg=self.theme['primary_h']))
        launch_btn.bind("<Leave>", lambda e: launch_btn.configure(bg=self.theme['primary']))
        
        # Bottom toolbar
        toolbar = tk.Frame(main_container, bg=self.theme['surface'])
        toolbar.pack(fill="x", side="bottom")
        
        toolbar_inner = tk.Frame(toolbar, bg=self.theme['surface'])
        toolbar_inner.pack(pady=12, padx=30)
        
        # Reconfigure station button
        def reconfigure():
            confirm = messagebox.askyesno(
                "Reconfigure Station",
                "Are you sure you want to reconfigure this station?\n\n"
                "This will change the dedicated process for this computer.",
                parent=self.parent
            )
            if confirm:
                self.station_id = None
                self.show_station_setup()
        
        reconfig_btn = tk.Button(
            toolbar_inner,
            text="⚙ Reconfigure Station",
            command=reconfigure,
            font=("Segoe UI", 9),
            bg=self.theme['surface_2'],
            fg=self.theme['text'],
            activebackground=self.theme['surface_3'],
            activeforeground=self.theme['text'],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=15,
            pady=6
        )
        reconfig_btn.pack(side="left")
        reconfig_btn.bind("<Enter>", lambda e: reconfig_btn.configure(bg=self.theme['surface_3']))
        reconfig_btn.bind("<Leave>", lambda e: reconfig_btn.configure(bg=self.theme['surface_2']))
        
        # Session info
        tk.Label(
            toolbar_inner,
            text=f"Session: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            font=("Segoe UI", 9),
            bg=self.theme['surface'],
            fg=self.theme['muted']
        ).pack(side="right", padx=20)


if __name__ == "__main__":
    # Standalone test
    root = tk.Tk()
    root.title("Station Launcher Test")
    root.geometry("1200x800")
    
    # Mock theme
    test_theme = {
        'bg': "#0f172a",
        'surface': "#1e293b",
        'surface_2': "#334155",
        'surface_3': "#475569",
        'primary': "#2563eb",
        'primary_h': "#1d4ed8",
        'accent': "#0ea5e9",
        'success': "#16a34a",
        'danger': "#dc2626",
        'warning': "#f59e0b",
        'text': "#f8fafc",
        'muted': "#94a3b8",
        'border': "#334155",
    }
    
    root.configure(bg=test_theme['bg'])
    
    frame = tk.Frame(root, bg=test_theme['bg'])
    frame.pack(fill="both", expand=True)
    
    launcher = StationLauncher(frame, test_theme)
    
    root.mainloop()
