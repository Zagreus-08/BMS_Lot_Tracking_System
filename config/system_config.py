"""
System Configuration for BMS Lot Tracking System
Central configuration for paths, database connections, and system settings
"""

import os
from pathlib import Path

# =========================================================
# PORTABLE PYTHON DETECTION
# =========================================================

def find_portable_python():
    """Auto-detect WinPython portable installation"""
    base_dir = Path(__file__).parent.parent
    
    # Common portable Python locations
    search_paths = [
        # Same directory as system
        base_dir / "WPy64-3771" / "python-3.7.7.amd64" / "python.exe",
        base_dir / "WinPython" / "python-3.7.7.amd64" / "python.exe",
        base_dir / "Python" / "python.exe",
        
        # Parent directory
        base_dir.parent / "WPy64-3771" / "python-3.7.7.amd64" / "python.exe",
        base_dir.parent / "LTS" / "WPy64-3771" / "python-3.7.7.amd64" / "python.exe",
        
        # Common deployment locations
        Path("C:/Users/bio_user/Desktop/LTS/WPy64-3771/python-3.7.7.amd64/python.exe"),
    ]
    
    # Check each path
    for path in search_paths:
        if path.exists():
            return str(path)
    
    # Dynamic search for WPy* directories
    for parent in [base_dir, base_dir.parent]:
        if parent.exists():
            for item in parent.iterdir():
                if item.is_dir() and item.name.startswith("WPy"):
                    for python_exe in item.rglob("python.exe"):
                        if "python-3" in str(python_exe):  # Ensure it's the main Python
                            return str(python_exe)
    
    # Fallback to system Python
    return "python"

# =========================================================
# SYSTEM PATHS
# =========================================================

# Python executable path (auto-detected portable)
PYTHON_EXE = find_portable_python()

# Base directory for the Lot Tracking System
BASE_DIR = str(Path(__file__).resolve().parent.parent)

# =========================================================
# DATABASE PATHS
# =========================================================

# Network database location
DB_BASE_PATH = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking"

# User authentication database
USER_DB = os.path.join(DB_BASE_PATH, "users.json")

# Main lot tracking databases
LOT_TRACKING_DB = os.path.join(DB_BASE_PATH, "lot_tracking.db")
LOT_MASTERLIST_DB = os.path.join(DB_BASE_PATH, "lot_masterlist.db")

# Process flow configuration
PROCESS_FLOW_CONFIG = os.path.join(DB_BASE_PATH, "process_flow.json")

# Version control
VERSION_FILE = r"\\phlsvr08\BMS Data\Lot Tracking System\version control info\version.txt"

# =========================================================
# PROCESS PROGRAMS PATHS
# =========================================================

PROCESS_PROGRAMS_DIR = os.path.join(BASE_DIR, "Process Programs")

PROCESS_PROGRAMS = {
    "Lot Entry System": os.path.join(PROCESS_PROGRAMS_DIR, "Lot Entry System", "OCR_BMS_Lot_Entry_System.py"),
    
    "Assembly Measurement": os.path.join(PROCESS_PROGRAMS_DIR, "Assembly Measurement", "V5_OCR_Assembly_Measurement.py"),
    
    "Cable Soldering": os.path.join(PROCESS_PROGRAMS_DIR, "Cable Soldering", "V9_Cable_Soldering.py"),
    
    "Inductance & Resistance Measurement": os.path.join(PROCESS_PROGRAMS_DIR, "Inductance & Resistance Measurement", "V5_Inductance_and_Resistance_Measurement.py"),
    
    "Labelling": os.path.join(PROCESS_PROGRAMS_DIR, "Labelling", "V6_Labelling.py"),
    
    "MR Chip Alignment Measurement": os.path.join(PROCESS_PROGRAMS_DIR, "MR Chip Alignment Measurement", "V4_OCR_MR_Chip_Alignment_Measurement.py"),
    
    "MR Chip Height Measurement": os.path.join(PROCESS_PROGRAMS_DIR, "MR Chip Height Measurement", "V4_OCR_MR_Chip_Height_Measurement.py"),
    
    "QA Final Inspection": os.path.join(PROCESS_PROGRAMS_DIR, "QA Final Inspection", "V2_OCR_QA_Image_Capturing.py"),
    
    "QA Inspection 1 & 2": os.path.join(PROCESS_PROGRAMS_DIR, "QA Inspection 1 & 2", "V6_OCR_QA_Inspection.py"),
    
    "SBB & Cable Resistance": os.path.join(PROCESS_PROGRAMS_DIR, "SBB Resistance & Cable Resistance", "V5_OCR_Resistance_Measurement.py"),
    
    "Sensor Sealing": os.path.join(PROCESS_PROGRAMS_DIR, "Sensor Sealing", "V1_Sensor Sealing.py"),
    
    "Sensor Storage": os.path.join(PROCESS_PROGRAMS_DIR, "Sensor Storage", "V3_Sensor Storage.py"),
    
    "Shipment Creation": os.path.join(PROCESS_PROGRAMS_DIR, "Shipment Creation", "V3_BMS_Shipment_Lot_Entry.py"),
    
    "Top & Bottom Molding Dimension": os.path.join(PROCESS_PROGRAMS_DIR, "Top & Bottom Molding Dimension", "V8_OCR_Molding_Dimension.py"),
}

# =========================================================
# ADMIN PROGRAMS PATHS
# =========================================================

ADMIN_PROGRAMS_DIR = os.path.join(BASE_DIR, "Admin Programs")

ADMIN_PROGRAMS = {
    "Lot Tracking System Admin": os.path.join(ADMIN_PROGRAMS_DIR, "BMS_Lot_Tracking_System.py"),
    
    "Lot Package System": os.path.join(ADMIN_PROGRAMS_DIR, "BMS_Lot_Package_System.py"),
    
    "Manual Parameter Encode": os.path.join(ADMIN_PROGRAMS_DIR, "Manual Parameter Encode.py"),
    
    "LTS Inquiry System": os.path.join(ADMIN_PROGRAMS_DIR, "v3_BMS_LTS_Inquiry_System copy.py"),
    
    "Station Configuration Manager": os.path.join(ADMIN_PROGRAMS_DIR, "Station_Configuration_Manager.py"),
}

# =========================================================
# UI THEME CONFIGURATION
# =========================================================

# Dark theme colors
DARK_THEME = {
    'bg': "#0f172a",          # App background (slate-900)
    'surface': "#1e293b",     # Cards/panels (slate-800)
    'surface_2': "#334155",   # Hover (slate-700)
    'surface_3': "#475569",   # Elevated surface (slate-600)
    'primary': "#2563eb",     # Blue-600
    'primary_h': "#1d4ed8",   # Blue-700 (hover)
    'accent': "#0ea5e9",      # Sky-500
    'accent_h': "#0284c7",    # Sky-600 (hover)
    'success': "#16a34a",     # Green-600
    'success_h': "#15803d",   # Green-700 (hover)
    'danger': "#dc2626",      # Red-600
    'danger_h': "#b91c1c",    # Red-700 (hover)
    'warning': "#f59e0b",     # Amber-500
    'warning_h': "#d97706",   # Amber-600 (hover)
    'text': "#f8fafc",        # Near white
    'text_secondary': "#cbd5e1",  # Slate-300
    'muted': "#94a3b8",       # Slate-400
    'border': "#334155",      # Slate-700
    'admin': "#f59e0b",       # Amber-500 (admin badge)
}

# Light theme colors
LIGHT_THEME = {
    'bg': "#f8fafc",          # App background (slate-50)
    'surface': "#ffffff",     # Cards/panels (white)
    'surface_2': "#f1f5f9",   # Hover (slate-100)
    'surface_3': "#e2e8f0",   # Elevated surface (slate-200)
    'primary': "#2563eb",     # Blue-600
    'primary_h': "#1d4ed8",   # Blue-700 (hover)
    'accent': "#0ea5e9",      # Sky-500
    'accent_h': "#0284c7",    # Sky-600 (hover)
    'success': "#16a34a",     # Green-600
    'success_h': "#15803d",   # Green-700 (hover)
    'danger': "#dc2626",      # Red-600
    'danger_h': "#b91c1c",    # Red-700 (hover)
    'warning': "#f59e0b",     # Amber-500
    'warning_h': "#d97706",   # Amber-600 (hover)
    'text': "#0f172a",        # Dark text (slate-900)
    'text_secondary': "#475569",  # Slate-600
    'muted': "#64748b",       # Slate-500
    'border': "#e2e8f0",      # Slate-200
    'admin': "#f59e0b",       # Amber-500 (admin badge)
}

# Backwards compatibility - default to dark theme
COLOR_BG = DARK_THEME['bg']
COLOR_SURFACE = DARK_THEME['surface']
COLOR_SURFACE_2 = DARK_THEME['surface_2']
COLOR_PRIMARY = DARK_THEME['primary']
COLOR_PRIMARY_H = DARK_THEME['primary_h']
COLOR_ACCENT = DARK_THEME['accent']
COLOR_SUCCESS = DARK_THEME['success']
COLOR_SUCCESS_H = DARK_THEME['success_h']
COLOR_DANGER = DARK_THEME['danger']
COLOR_DANGER_H = DARK_THEME['danger_h']
COLOR_WARNING = DARK_THEME['warning']
COLOR_TEXT = DARK_THEME['text']
COLOR_MUTED = DARK_THEME['muted']
COLOR_ADMIN = DARK_THEME['admin']

# Fonts
FONT_TITLE = ("Segoe UI Semibold", 20)
FONT_H1 = ("Segoe UI Semibold", 16)
FONT_H2 = ("Segoe UI Semibold", 13)
FONT_H3 = ("Segoe UI Semibold", 11)
FONT_BODY = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_CARD = ("Segoe UI Semibold", 11)

# =========================================================
# PROCESS FLOW STAGES (for visualization)
# =========================================================

PROCESS_STAGES = [
    "Lot Entry",
    "Laser Marking and OCR",
    "MR Chip Alignment",
    "MR Chip Height",
    "SBB Resistance",
    "Assembly Measurement",
    "QA Inspection 1",
    "Top Molding",
    "Cable Soldering",
    "Cable Resistance",
    "QA Inspection 2",
    "Bottom Molding",
    "Inductance & Resistance",
    "QA Final",
    "Shipment"
]

# =========================================================
# USER ROLES
# =========================================================

ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"

# =========================================================
# SYSTEM SETTINGS
# =========================================================

# Auto-refresh interval for real-time tracking (milliseconds)
REFRESH_INTERVAL = 5000  # 5 seconds

# Maximum lots to display in tracking view
MAX_LOTS_DISPLAY = 100

# Session timeout (minutes)
SESSION_TIMEOUT = 480  # 8 hours
