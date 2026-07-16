"""
Portable Configuration for BMS Lot Tracking System
Automatically detects WinPython portable installation
"""

import os
from pathlib import Path

def find_portable_python():
    """
    Find WinPython portable installation
    Searches in common locations relative to the system directory
    """
    # Get the base directory (where the system is installed)
    base_dir = Path(__file__).parent.parent
    
    # Common portable Python locations to check
    search_paths = [
        # Same directory as the system
        base_dir / "WPy64-3771" / "python-3.7.7.amd64" / "python.exe",
        base_dir / "WinPython" / "python-3.7.7.amd64" / "python.exe",
        base_dir / "Python" / "python.exe",
        
        # Parent directory
        base_dir.parent / "WPy64-3771" / "python-3.7.7.amd64" / "python.exe",
        base_dir.parent / "WinPython" / "python-3.7.7.amd64" / "python.exe",
        base_dir.parent / "Python" / "python.exe",
        
        # Sibling directory (common deployment)
        base_dir.parent / "LTS" / "WPy64-3771" / "python-3.7.7.amd64" / "python.exe",
        
        # Desktop locations (for development)
        Path.home() / "Desktop" / "LTS" / "WPy64-3771" / "python-3.7.7.amd64" / "python.exe",
        Path("C:/Users/bio_user/Desktop/LTS/WPy64-3771/python-3.7.7.amd64/python.exe"),
        
        # Try to find any WPy64-* folder in parent directories
        base_dir.parent / "WPy64" / "python.exe",
    ]
    
    # Check each path
    for path in search_paths:
        if path.exists():
            return str(path)
    
    # Try to find WinPython directory dynamically
    for parent in [base_dir, base_dir.parent]:
        if parent.exists():
            # Look for WPy* directories
            for item in parent.iterdir():
                if item.is_dir() and item.name.startswith("WPy"):
                    # Look for python.exe inside
                    for python_dir in item.rglob("python.exe"):
                        if python_dir.exists():
                            return str(python_dir)
    
    # If not found, return system Python (fallback)
    return "python"

def get_portable_python_path():
    """Get the portable Python executable path"""
    python_path = find_portable_python()
    
    if python_path != "python":
        print(f"Found portable Python: {python_path}")
    else:
        print("Using system Python (portable not found)")
    
    return python_path

# Auto-detect on import
PORTABLE_PYTHON_EXE = get_portable_python_path()
