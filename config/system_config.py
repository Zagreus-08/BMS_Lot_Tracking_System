"""
System Configuration for BMS Lot Tracking System
Central configuration for paths, database connections, and system settings
"""

import os

# =========================================================
# SYSTEM PATHS
# =========================================================

# Python executable path
PYTHON_EXE = r"C:\Users\bio_user\Desktop\LTS\WPy64-3771\python-3.7.7.amd64\python.exe"

# Base directory for the Lot Tracking System
BASE_DIR = r"c:\Users\a493353\Desktop\Lans Galos\Lot Tracking System"

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
}

# =========================================================
# UI THEME CONFIGURATION
# =========================================================

# Modern dark theme colors
COLOR_BG = "#0f172a"          # App background (slate-900)
COLOR_SURFACE = "#1e293b"     # Cards/panels (slate-800)
COLOR_SURFACE_2 = "#334155"   # Hover (slate-700)
COLOR_PRIMARY = "#2563eb"     # Blue-600
COLOR_PRIMARY_H = "#1d4ed8"   # Blue-700 (hover)
COLOR_ACCENT = "#0ea5e9"      # Sky-500
COLOR_SUCCESS = "#16a34a"     # Green-600
COLOR_SUCCESS_H = "#15803d"   # Green-700 (hover)
COLOR_DANGER = "#dc2626"      # Red-600
COLOR_DANGER_H = "#b91c1c"    # Red-700 (hover)
COLOR_WARNING = "#f59e0b"     # Amber-500
COLOR_TEXT = "#f8fafc"        # Near white
COLOR_MUTED = "#94a3b8"       # Slate-400
COLOR_ADMIN = "#f59e0b"       # Amber-500 (admin badge)

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
