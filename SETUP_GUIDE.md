# BMS Lot Tracking System - Setup Guide

## 📋 Installation Instructions

### Step 1: Verify Python Installation

1. Check Python version (3.7+ required):
   ```cmd
   python --version
   ```

2. Verify required modules:
   ```cmd
   python -c "import tkinter, sqlite3, json; print('All required modules available')"
   ```

### Step 2: Configure System Paths

1. Open `config\system_config.py`

2. Update the Python executable path:
   ```python
   PYTHON_EXE = r"C:\path\to\your\python.exe"
   ```

3. Verify database paths are accessible:
   ```python
   DB_BASE_PATH = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking"
   ```

4. Update process program paths if needed

### Step 3: Database Setup

The system will automatically create the user database on first run.

**Database Locations:**
- User DB: `\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\users.json`
- Lot Tracking: `\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db`
- Lot Masterlist: `\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db`

### Step 4: First Launch

1. Run the system:
   ```cmd
   python launch_system.py
   ```

2. Log in with default credentials:
   - **Username**: admin
   - **Password**: admin123

3. Navigate through the dashboard to verify all features

### Step 5: Create User Accounts

1. Log in as admin
2. Go to "User Management"
3. Add operator accounts as needed
4. Change default admin password

---

## 🔧 Configuration Options

### Customize UI Theme

Edit `config\system_config.py`:

```python
# Change colors
COLOR_PRIMARY = "#2563eb"    # Main accent color
COLOR_ACCENT = "#0ea5e9"     # Secondary accent
COLOR_BG = "#0f172a"         # Background

# Change fonts
FONT_TITLE = ("Segoe UI Semibold", 20)
FONT_BODY = ("Segoe UI", 10)
```

### Adjust Auto-Refresh Rate

```python
REFRESH_INTERVAL = 5000  # milliseconds (5 seconds)
```

### Add New Process Programs

```python
PROCESS_PROGRAMS = {
    "Your New Program": r"path\to\program.py",
    # ... existing programs
}
```

---

## 🚀 Running the System

### Normal Operation

```cmd
python launch_system.py
```

### Development/Testing

Run individual components:

```cmd
# Test login only
python "Log In\enhanced_login.py"

# Test dashboard (requires login first)
python "Main Dashboard\main_dashboard.py"

# Test real-time tracking
python "Main Dashboard\realtime_tracking_view.py"
```

---

## 🔍 Testing Checklist

After installation, verify:

- [ ] Login system works with default credentials
- [ ] Dashboard loads properly for both roles
- [ ] Real-time tracking displays process stages
- [ ] Process programs launch correctly
- [ ] Admin programs accessible (admin only)
- [ ] User management functions (admin only)
- [ ] Statistics display correctly (admin only)
- [ ] Auto-refresh updates data
- [ ] Database connections work

---

## 🐛 Common Issues & Solutions

### Issue: "Module not found" error

**Solution**: Ensure all files are in correct directories:
```
Lot Tracking System/
├── config/
│   ├── system_config.py
│   └── database_manager.py
├── Log In/
│   └── enhanced_login.py
├── Main Dashboard/
│   ├── main_dashboard.py
│   └── realtime_tracking_view.py
└── launch_system.py
```

### Issue: Database connection fails

**Solution**: 
1. Verify network access to `\\phlsvr08`
2. Check database paths in `system_config.py`
3. Ensure proper file permissions

### Issue: Programs won't launch

**Solution**:
1. Verify PYTHON_EXE path in `system_config.py`
2. Check individual program paths in PROCESS_PROGRAMS
3. Test program manually: `python "Process Programs\<program>\<file>.py"`

### Issue: Login window doesn't appear

**Solution**:
1. Check for errors in console
2. Verify tkinter is installed: `python -c "import tkinter"`
3. Try running directly: `python "Log In\enhanced_login.py"`

---

## 📊 Database Schema

### users.json Structure

```json
{
  "username": {
    "password": "password",
    "role": "operator|admin",
    "full_name": "Full Name",
    "created_date": "2024-01-01 12:00:00"
  }
}
```

### lot_tracking.db Tables

- **lot_tracking**: Main tracking table with process columns
- Columns include: lot_number, sensor_id, current_process, timestamps, operators

### lot_masterlist.db Tables

- **lot_masterlist**: Detailed lot information
- Includes all measurement and parameter data

---

## 🔐 Security Recommendations

1. **Change Default Passwords**
   - Change admin password immediately after first login
   - Use strong passwords for all accounts

2. **Backup User Database**
   - Regular backups of `users.json`
   - Store in secure location

3. **Access Control**
   - Limit admin access to trusted personnel
   - Regular audit of user accounts

4. **Network Security**
   - Ensure secure network access to database server
   - Use VPN if accessing remotely

---

## 📈 Performance Optimization

### For Large Databases

1. **Adjust Query Limits**
   Edit `system_config.py`:
   ```python
   MAX_LOTS_DISPLAY = 100  # Reduce if slow
   ```

2. **Increase Refresh Interval**
   ```python
   REFRESH_INTERVAL = 10000  # 10 seconds
   ```

3. **Database Maintenance**
   - Regular VACUUM on SQLite databases
   - Archive old completed lots

---

## 📞 Support & Maintenance

### Regular Maintenance Tasks

- Weekly: Check database sizes and performance
- Monthly: Review and clean up old user accounts
- Quarterly: Update documentation with any changes

### Getting Help

1. Check README.md for feature documentation
2. Review this setup guide for configuration
3. Check console output for error messages
4. Contact system administrator

---

## 🔄 Updating the System

### To Update Configuration

1. Backup current `config\system_config.py`
2. Make changes
3. Test with `python launch_system.py`
4. If issues, restore backup

### To Add New Features

1. Create new module in appropriate directory
2. Update `system_config.py` if needed
3. Update `main_dashboard.py` for navigation
4. Test thoroughly before deployment

---

## ✅ Post-Installation Verification

Run this verification script:

```python
# verify_installation.py
import os
import sys

print("Verifying BMS Lot Tracking System Installation...")
print("=" * 60)

# Check directories
directories = [
    "config",
    "Log In",
    "Main Dashboard",
    "Process Programs",
    "Admin Programs"
]

for dir in directories:
    if os.path.exists(dir):
        print(f"✓ Directory exists: {dir}")
    else:
        print(f"✗ Missing directory: {dir}")

# Check key files
files = [
    "config\\system_config.py",
    "config\\database_manager.py",
    "Log In\\enhanced_login.py",
    "Main Dashboard\\main_dashboard.py",
    "Main Dashboard\\realtime_tracking_view.py",
    "launch_system.py"
]

for file in files:
    if os.path.exists(file):
        print(f"✓ File exists: {file}")
    else:
        print(f"✗ Missing file: {file}")

# Check Python modules
print("\nChecking Python modules...")
try:
    import tkinter
    print("✓ tkinter available")
except:
    print("✗ tkinter not available")

try:
    import sqlite3
    print("✓ sqlite3 available")
except:
    print("✗ sqlite3 not available")

try:
    import json
    print("✓ json available")
except:
    print("✗ json not available")

print("\n" + "=" * 60)
print("Verification complete!")
```

Save as `verify_installation.py` and run:
```cmd
python verify_installation.py
```

---

**Installation Guide Version**: 1.0  
**Last Updated**: 2026-07-02  
**System Version**: 2.0
