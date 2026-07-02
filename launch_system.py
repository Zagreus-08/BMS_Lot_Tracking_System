"""
BMS Lot Tracking System - Main Launcher
Optimized system entry point with enhanced features
"""

import sys
import os
from pathlib import Path
import importlib.util

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def import_module_from_path(module_name, file_path):
    """Import a module from a file path (handles spaces in directory names)"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    """Main entry point for the Lot Tracking System"""
    try:
        base_dir = Path(__file__).parent
        
        # Import enhanced login module
        login_module = import_module_from_path(
            "enhanced_login",
            base_dir / "Log In" / "enhanced_login.py"
        )
        
        # Import main dashboard module
        dashboard_module = import_module_from_path(
            "main_dashboard",
            base_dir / "Main Dashboard" / "main_dashboard.py"
        )
        
        print("=" * 60)
        print("BMS LOT TRACKING SYSTEM")
        print("Enhanced Version with Real-time Tracking")
        print("=" * 60)
        print("\nStarting login system...")
        
        # Show login window
        login_win = login_module.LoginWindow()
        user_data = login_win.run()
        
        if user_data:
            print(f"\nLogin successful: {user_data['username']} ({user_data['role']})")
            print("Starting main dashboard...")
            
            # Show main dashboard
            dashboard = dashboard_module.MainDashboard(user_data)
            dashboard.run()
            
            print("\nSystem closed.")
        else:
            print("\nLogin cancelled.")
    
    except Exception as e:
        print(f"\nError starting system: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
