"""
Test script to verify all imports work correctly
"""

import sys
from pathlib import Path
import importlib.util

def import_module_from_path(module_name, file_path):
    """Import a module from a file path"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_imports():
    """Test all critical imports"""
    print("=" * 60)
    print("Testing BMS Lot Tracking System Imports")
    print("=" * 60)
    
    base_dir = Path(__file__).parent
    
    tests = []
    
    # Test 1: Config imports
    print("\n1. Testing config imports...")
    try:
        system_config = import_module_from_path(
            "system_config",
            base_dir / "config" / "system_config.py"
        )
        print("   ✓ system_config.py imported successfully")
        tests.append(("Config - system_config", True))
    except Exception as e:
        print(f"   ✗ Error: {e}")
        tests.append(("Config - system_config", False))
    
    try:
        database_manager = import_module_from_path(
            "database_manager",
            base_dir / "config" / "database_manager.py"
        )
        print("   ✓ database_manager.py imported successfully")
        tests.append(("Config - database_manager", True))
    except Exception as e:
        print(f"   ✗ Error: {e}")
        tests.append(("Config - database_manager", False))
    
    # Test 2: Login module
    print("\n2. Testing login module...")
    try:
        login_module = import_module_from_path(
            "enhanced_login",
            base_dir / "Log In" / "enhanced_login.py"
        )
        print("   ✓ enhanced_login.py imported successfully")
        tests.append(("Login - enhanced_login", True))
    except Exception as e:
        print(f"   ✗ Error: {e}")
        tests.append(("Login - enhanced_login", False))
    
    # Test 3: Dashboard modules
    print("\n3. Testing dashboard modules...")
    try:
        dashboard_module = import_module_from_path(
            "main_dashboard",
            base_dir / "Main Dashboard" / "main_dashboard.py"
        )
        print("   ✓ main_dashboard.py imported successfully")
        tests.append(("Dashboard - main_dashboard", True))
    except Exception as e:
        print(f"   ✗ Error: {e}")
        tests.append(("Dashboard - main_dashboard", False))
    
    try:
        tracking_module = import_module_from_path(
            "realtime_tracking_view",
            base_dir / "Main Dashboard" / "realtime_tracking_view.py"
        )
        print("   ✓ realtime_tracking_view.py imported successfully")
        tests.append(("Dashboard - realtime_tracking", True))
    except Exception as e:
        print(f"   ✗ Error: {e}")
        tests.append(("Dashboard - realtime_tracking", False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in tests if result)
    total = len(tests)
    
    for test_name, result in tests:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:30} {status}")
    
    print("\n" + "-" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("\n✓ ALL IMPORTS SUCCESSFUL!")
        print("The system is ready to launch.")
        print("\nTo start the system:")
        print("  Double-click: START_SYSTEM.bat")
        print("  or run: python launch_system.py")
    else:
        print("\n✗ SOME IMPORTS FAILED")
        print("Please check the errors above and fix them.")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_imports()
    input("\nPress Enter to exit...")
