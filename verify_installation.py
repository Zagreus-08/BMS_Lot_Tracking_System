"""
Installation Verification Script
Checks all components of the BMS Lot Tracking System
"""

import os
import sys

def check_directories():
    """Check if all required directories exist"""
    print("\n" + "=" * 60)
    print("CHECKING DIRECTORIES")
    print("=" * 60)
    
    directories = [
        "config",
        "Log In",
        "Main Dashboard",
        "Process Programs",
        "Admin Programs"
    ]
    
    all_ok = True
    for directory in directories:
        if os.path.exists(directory):
            print(f"✓ {directory}")
        else:
            print(f"✗ {directory} - MISSING")
            all_ok = False
    
    return all_ok

def check_files():
    """Check if all required files exist"""
    print("\n" + "=" * 60)
    print("CHECKING KEY FILES")
    print("=" * 60)
    
    files = [
        "config\\system_config.py",
        "config\\database_manager.py",
        "Log In\\enhanced_login.py",
        "Main Dashboard\\main_dashboard.py",
        "Main Dashboard\\realtime_tracking_view.py",
        "launch_system.py",
        "README.md",
        "SETUP_GUIDE.md"
    ]
    
    all_ok = True
    for file in files:
        if os.path.exists(file):
            print(f"✓ {file}")
        else:
            print(f"✗ {file} - MISSING")
            all_ok = False
    
    return all_ok

def check_python_modules():
    """Check if required Python modules are available"""
    print("\n" + "=" * 60)
    print("CHECKING PYTHON MODULES")
    print("=" * 60)
    
    modules = {
        'tkinter': 'GUI framework',
        'sqlite3': 'Database operations',
        'json': 'Configuration files',
        'subprocess': 'Program launching',
        'datetime': 'Date/time handling',
        'pathlib': 'Path operations'
    }
    
    all_ok = True
    for module, description in modules.items():
        try:
            __import__(module)
            print(f"✓ {module:15} - {description}")
        except ImportError:
            print(f"✗ {module:15} - MISSING - {description}")
            all_ok = False
    
    return all_ok

def check_process_programs():
    """Check if process programs exist"""
    print("\n" + "=" * 60)
    print("CHECKING PROCESS PROGRAMS")
    print("=" * 60)
    
    process_dirs = [
        "Process Programs\\Lot Entry System",
        "Process Programs\\Assembly Measurement",
        "Process Programs\\Cable Soldering",
        "Process Programs\\Labelling",
        "Process Programs\\MR Chip Alignment Measurement",
        "Process Programs\\MR Chip Height Measurement",
        "Process Programs\\QA Final Inspection",
        "Process Programs\\QA Inspection 1 & 2",
        "Process Programs\\SBB Resistance & Cable Resistance",
    ]
    
    all_ok = True
    for directory in process_dirs:
        if os.path.exists(directory):
            # Count Python files
            py_files = [f for f in os.listdir(directory) if f.endswith('.py')]
            print(f"✓ {directory:50} ({len(py_files)} file(s))")
        else:
            print(f"✗ {directory:50} - MISSING")
            all_ok = False
    
    return all_ok

def main():
    """Run all verification checks"""
    print("\n" + "=" * 60)
    print("BMS LOT TRACKING SYSTEM - INSTALLATION VERIFICATION")
    print("=" * 60)
    print(f"Python Version: {sys.version}")
    print(f"Current Directory: {os.getcwd()}")
    
    # Run all checks
    results = {
        'Directories': check_directories(),
        'Key Files': check_files(),
        'Python Modules': check_python_modules(),
        'Process Programs': check_process_programs()
    }
    
    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{check:20} {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL CHECKS PASSED - System ready to run!")
        print("\nTo start the system, run:")
        print("  python launch_system.py")
    else:
        print("✗ SOME CHECKS FAILED - Please fix issues before running")
        print("\nRefer to SETUP_GUIDE.md for installation instructions")
    print("=" * 60)
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
