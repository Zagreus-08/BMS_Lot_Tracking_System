"""
Station Configuration Manager - Admin Tool
Manage and view station assignments across the production floor
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
from pathlib import Path
from datetime import datetime

# Paths
BASE_DIR = Path(__file__).parent.parent
STATION_CONFIG_FILE = BASE_DIR / "config" / "station_config.json"
LOCAL_STATION_FILE = BASE_DIR / "config" / "local_station.json"

# Theme
THEME = {
    'bg': "#0f172a",
    'surface': "#1e293b",
    'surface_2': "#334155",
    'primary': "#2563eb",
    'primary_h': "#1d4ed8",
    'accent': "#0ea5e9",
    'success': "#16a34a",
    'danger': "#dc2626",
    'text': "#f8fafc",
    'muted': "#94a3b8",
}


class StationConfigManager:
    """Admin tool for managing station configurations"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Station Configuration Manager - Admin Tool")
        self.root.geometry("1000x700")
        self.root.configure(bg=THEME['bg'])
        
        self.station_config = self.load_station_config()
        self.current_station = self.load_current_station()
        
        self.create_ui()
    
    def load_station_config(self):
        """Load station mapping configuration"""
        try:
            with open(STATION_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get('station_mapping', {})
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load station config:\n\n{str(e)}")
            return {}
    
    def load_current_station(self):
        """Load current station assignment for this computer"""
        try:
            if LOCAL_STATION_FILE.exists():
                with open(LOCAL_STATION_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get('station_id')
        except:
            pass
        return None
    
    def save_current_station(self, station_id):
        """Save station assignment for this computer"""
        try:
            LOCAL_STATION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOCAL_STATION_FILE, 'w') as f:
                json.dump({
                    'station_id': station_id,
                    'configured_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }, f, indent=2)
            messagebox.showinfo("Success", 
                              f"This computer is now configured as:\n\n{station_id}")
            self.current_station = station_id
            self.refresh_ui()
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration:\n\n{str(e)}")
            return False
    
    def create_ui(self):
        """Create the admin interface"""
        # Header
        header = tk.Frame(self.root, bg=THEME['surface'])
        header.pack(fill="x", pady=(0, 2))
        
        tk.Label(
            header,
            text="🏭 Station Configuration Manager",
            font=("Segoe UI Semibold", 20),
            bg=THEME['surface'],
            fg=THEME['text']
        ).pack(pady=(20, 5))
        
        tk.Label(
            header,
            text="Manage station assignments for production floor computers",
            font=("Segoe UI", 11),
            bg=THEME['surface'],
            fg=THEME['muted']
        ).pack(pady=(0, 20))
        
        # Current station indicator
        if self.current_station:
            current_frame = tk.Frame(header, bg=THEME['primary'])
            current_frame.pack(fill="x", pady=(0, 20))
            
            info = self.station_config.get(self.current_station, {})
            tk.Label(
                current_frame,
                text=f"This Computer: {self.current_station} - {info.get('name', 'Unknown')}",
                font=("Segoe UI Semibold", 11),
                bg=THEME['primary'],
                fg="#ffffff"
            ).pack(pady=10)
        
        # Main content area
        content = tk.Frame(self.root, bg=THEME['bg'])
        content.pack(fill="both", expand=True, padx=30, pady=20)
        
        # Left panel - Station list
        left_panel = tk.Frame(content, bg=THEME['surface'])
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        tk.Label(
            left_panel,
            text="Available Stations",
            font=("Segoe UI Semibold", 14),
            bg=THEME['surface'],
            fg=THEME['text']
        ).pack(pady=(20, 10), padx=20, anchor="w")
        
        # Scrollable station list
        list_frame = tk.Frame(left_panel, bg=THEME['surface'])
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # Canvas for scrolling
        canvas = tk.Canvas(list_frame, bg=THEME['surface'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        
        self.stations_container = tk.Frame(canvas, bg=THEME['surface'])
        
        self.stations_container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.stations_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Populate stations
        self.populate_stations()
        
        # Right panel - Actions
        right_panel = tk.Frame(content, bg=THEME['surface'], width=300)
        right_panel.pack(side="right", fill="y", padx=(10, 0))
        right_panel.pack_propagate(False)
        
        tk.Label(
            right_panel,
            text="Actions",
            font=("Segoe UI Semibold", 14),
            bg=THEME['surface'],
            fg=THEME['text']
        ).pack(pady=(20, 20), padx=20, anchor="w")
        
        # Action buttons
        actions = [
            ("Configure This Computer", self.configure_this_computer, THEME['primary']),
            ("View Station Details", self.view_details, THEME['accent']),
            ("Export Configuration", self.export_config, THEME['success']),
            ("Clear Configuration", self.clear_config, THEME['danger']),
        ]
        
        for text, command, color in actions:
            btn = tk.Button(
                right_panel,
                text=text,
                command=command,
                font=("Segoe UI", 10),
                bg=color,
                fg="#ffffff",
                activebackground=color,
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                cursor="hand2",
                padx=20,
                pady=12
            )
            btn.pack(fill="x", padx=20, pady=5)
        
        # Info section
        info_frame = tk.Frame(right_panel, bg=THEME['surface_2'])
        info_frame.pack(fill="x", side="bottom", padx=20, pady=20)
        
        tk.Label(
            info_frame,
            text="Information",
            font=("Segoe UI Semibold", 10),
            bg=THEME['surface_2'],
            fg=THEME['text']
        ).pack(pady=(15, 5), padx=15, anchor="w")
        
        tk.Label(
            info_frame,
            text=f"Total Stations: {len(self.station_config)}\n"
                 f"Configuration File:\n{STATION_CONFIG_FILE.name}",
            font=("Segoe UI", 9),
            bg=THEME['surface_2'],
            fg=THEME['muted'],
            justify="left"
        ).pack(pady=(0, 15), padx=15, anchor="w")
        
        # Bottom status bar
        self.status_bar = tk.Frame(self.root, bg=THEME['surface'], height=40)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_bar.pack_propagate(False)
        
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(
            self.status_bar,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            bg=THEME['surface'],
            fg=THEME['muted']
        ).pack(side="left", padx=20, pady=10)
        
        # Close button
        close_btn = tk.Button(
            self.status_bar,
            text="Close",
            command=self.root.destroy,
            font=("Segoe UI", 9),
            bg=THEME['surface_2'],
            fg=THEME['text'],
            activebackground=THEME['surface_2'],
            activeforeground=THEME['text'],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=15,
            pady=5
        )
        close_btn.pack(side="right", padx=20, pady=5)
    
    def populate_stations(self):
        """Populate the stations list"""
        # Clear existing
        for widget in self.stations_container.winfo_children():
            widget.destroy()
        
        # Add station cards
        for station_id in sorted(self.station_config.keys()):
            info = self.station_config[station_id]
            self.create_station_card(station_id, info)
    
    def create_station_card(self, station_id, info):
        """Create a station card"""
        is_current = (station_id == self.current_station)
        
        card = tk.Frame(
            self.stations_container,
            bg=THEME['primary'] if is_current else THEME['surface_2'],
            cursor="hand2"
        )
        card.pack(fill="x", pady=5)
        
        inner = tk.Frame(card, bg=THEME['primary'] if is_current else THEME['surface_2'])
        inner.pack(fill="x", padx=15, pady=12)
        
        # Station ID and icon
        header = tk.Frame(inner, bg=THEME['primary'] if is_current else THEME['surface_2'])
        header.pack(fill="x")
        
        tk.Label(
            header,
            text=f"[+] {station_id}",
            font=("Segoe UI Semibold", 11),
            bg=THEME['primary'] if is_current else THEME['surface_2'],
            fg=THEME['text']
        ).pack(side="left")
        
        if is_current:
            tk.Label(
                header,
                text="● ACTIVE",
                font=("Segoe UI", 8),
                bg=THEME['primary'],
                fg="#ffffff"
            ).pack(side="right")
        
        # Station name
        tk.Label(
            inner,
            text=info.get('name', 'Unknown'),
            font=("Segoe UI", 10),
            bg=THEME['primary'] if is_current else THEME['surface_2'],
            fg=THEME['text'] if not is_current else "#ffffff"
        ).pack(anchor="w", pady=(5, 2))
        
        # Process
        tk.Label(
            inner,
            text=f"Process: {info.get('process', 'Unknown')}",
            font=("Segoe UI", 9),
            bg=THEME['primary'] if is_current else THEME['surface_2'],
            fg=THEME['muted'] if not is_current else "#e0e0e0"
        ).pack(anchor="w")
        
        # Click to select
        def on_click(e):
            self.select_station(station_id)
        
        for widget in [card, inner, header]:
            widget.bind("<Button-1>", on_click)
    
    def select_station(self, station_id):
        """Select a station"""
        self.selected_station = station_id
        info = self.station_config.get(station_id, {})
        self.status_var.set(f"Selected: {station_id} - {info.get('name', 'Unknown')}")
    
    def configure_this_computer(self):
        """Configure this computer as a station"""
        if not hasattr(self, 'selected_station'):
            messagebox.showwarning("No Selection", "Please select a station first")
            return
        
        info = self.station_config.get(self.selected_station, {})
        
        confirm = messagebox.askyesno(
            "Configure Computer",
            f"Configure this computer as:\n\n"
            f"{self.selected_station}\n"
            f"{info.get('name', 'Unknown')}\n"
            f"Process: {info.get('process', 'Unknown')}\n\n"
            f"This will be the permanent station assignment.",
            parent=self.root
        )
        
        if confirm:
            self.save_current_station(self.selected_station)
    
    def view_details(self):
        """View station details"""
        if not hasattr(self, 'selected_station'):
            messagebox.showwarning("No Selection", "Please select a station first")
            return
        
        info = self.station_config.get(self.selected_station, {})
        
        details = (
            f"Station ID: {self.selected_station}\n"
            f"Station Name: {info.get('name', 'Unknown')}\n"
            f"Process: {info.get('process', 'Unknown')}\n"
            f"Description: {info.get('description', 'No description')}"
        )
        
        messagebox.showinfo("Station Details", details, parent=self.root)
    
    def export_config(self):
        """Export station configuration to file"""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="station_config_export.json",
            parent=self.root
        )
        
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    json.dump(self.station_config, f, indent=2)
                messagebox.showinfo("Success", f"Configuration exported to:\n\n{filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export:\n\n{str(e)}")
    
    def clear_config(self):
        """Clear this computer's station configuration"""
        if not self.current_station:
            messagebox.showinfo("No Configuration", 
                              "This computer is not currently configured as a station")
            return
        
        confirm = messagebox.askyesno(
            "Clear Configuration",
            f"Clear the station configuration for this computer?\n\n"
            f"Current: {self.current_station}\n\n"
            f"You will need to reconfigure when accessing the station launcher.",
            parent=self.root
        )
        
        if confirm:
            try:
                if LOCAL_STATION_FILE.exists():
                    LOCAL_STATION_FILE.unlink()
                self.current_station = None
                messagebox.showinfo("Success", "Station configuration cleared")
                self.refresh_ui()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear configuration:\n\n{str(e)}")
    
    def refresh_ui(self):
        """Refresh the UI"""
        self.root.destroy()
        self.__init__()
        self.run()
    
    def run(self):
        """Run the application"""
        self.root.mainloop()


if __name__ == "__main__":
    app = StationConfigManager()
    app.run()
