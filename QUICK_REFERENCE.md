# BMS Lot Tracking System - Quick Reference Card

## 🚀 Quick Start

### Starting the System
```
Double-click: START_SYSTEM.bat
or run: python launch_system.py
```

### Default Login Credentials
| Role | Username | Password |
|------|----------|----------|
| Admin | admin | admin123 |
| Operator | operator | operator123 |

⚠️ **Change passwords after first login!**

---

## 🎯 Main Features Quick Access

### For Operators

| Feature | Navigation | Description |
|---------|------------|-------------|
| **Real-time Tracking** | Auto-loads on login | See all lots and their locations |
| **Process Programs** | Click "⚙️ Process Programs" | Launch manufacturing programs |
| **Log Out** | Bottom right button | Exit and return to login |

### For Admins (Additional)

| Feature | Navigation | Description |
|---------|------------|-------------|
| **Admin Programs** | Click "🔧 Admin Programs" | Access admin tools |
| **User Management** | Click "👥 User Management" | Manage user accounts |
| **Statistics** | Click "📈 Statistics" | View production metrics |

---

## 📊 Real-time Tracking

### At a Glance
- **Process cards** show each manufacturing stage
- **Numbers** display lot and sensor counts
- **Click a card** to see detailed lot list
- **Auto-refreshes** every 5 seconds

### Quick Actions
- ✅ Toggle auto-refresh on/off
- ✅ Click stage to see lot details
- ✅ View last update timestamp

---

## ⚙️ Launching Programs

### Steps
1. Click "⚙️ Process Programs"
2. Find your program card
3. Click the card to launch
4. Program opens in new window
5. Dashboard stays open

### Program Status
- **✓ Ready** - Program available
- **✗ Not Found** - Contact admin

---

## 🔐 User Management (Admin Only)

### View Users
1. Click "👥 User Management"
2. See all users in table
3. View roles and creation dates

### Add New User
1. Click "Add User" (if available)
2. Enter username, password
3. Select role (operator/admin)
4. Provide admin password
5. Save

---

## 📈 Statistics (Admin Only)

### Dashboard View
- **Top Cards**: Summary metrics (Total, In Progress, Completed)
- **Process Bars**: Visual breakdown by stage
- **Real-time**: Updates automatically

### Interpreting Data
- **High counts** at a stage = potential bottleneck
- **Low counts** = stage running efficiently
- **Compare stages** to balance workflow

---

## 🛠️ Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| Can't log in | Check username/password, try default credentials |
| Program won't launch | Check if file exists, contact admin |
| No data showing | Check network connection to database server |
| Screen looks wrong | Resize window, check display settings |

### Quick Fixes
1. **Restart the system** - Close and relaunch
2. **Check network** - Verify connection to \\phlsvr08
3. **Clear and reload** - Navigate to different view and back
4. **Contact admin** - If issue persists

---

## ⌨️ Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Login | Enter (on login screen) |
| Close window | Alt+F4 |
| Refresh (in browser-like views) | F5 (where applicable) |

---

## 📞 Quick Reference Numbers

### System Information
- **Refresh Interval**: 5 seconds
- **Max Lots Displayed**: 100
- **Session Timeout**: 8 hours
- **Process Stages**: 15 total

### File Locations
- **User Database**: `\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\users.json`
- **Lot Tracking DB**: `\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db`
- **Lot Masterlist DB**: `\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db`

---

## 🎨 UI Color Guide

| Color | Meaning |
|-------|---------|
| 🔵 Blue | Primary actions, links |
| 🟢 Green | Success, active, ready |
| 🔴 Red | Error, delete, exit |
| 🟡 Amber | Warning, admin features |
| ⚪ White | Text, labels |
| ⚫ Dark | Background, cards |

---

## 📋 Process Stage Names

Quick reference for process stages:

1. Lot Entry
2. Laser Marking and OCR
3. MR Chip Alignment
4. MR Chip Height
5. SBB Resistance
6. Assembly Measurement
7. QA Inspection 1
8. Top Molding
9. Cable Soldering
10. Cable Resistance
11. QA Inspection 2
12. Bottom Molding
13. Inductance & Resistance
14. QA Final
15. Shipment

---

## 🔄 Daily Workflow

### Operator Workflow
```
1. Start System → 2. Log In → 3. Check Tracking →
4. Launch Program → 5. Process Lots → 6. Log Out
```

### Admin Workflow
```
1. Start System → 2. Log In (Admin) → 3. Check Statistics →
4. Review Bottlenecks → 5. Manage Users → 6. Monitor System
```

---

## 💾 Backup Reminder (Admin)

### What to Backup
- ✅ users.json
- ✅ lot_tracking.db
- ✅ lot_masterlist.db
- ✅ system_config.py

### When to Backup
- 📅 Daily: User database
- 📅 Weekly: Lot databases
- 📅 Monthly: Full system backup
- 📅 Before changes: Configuration files

---

## 📱 Emergency Contacts

| Issue Type | Contact |
|------------|---------|
| System Down | IT Help Desk |
| Login Issues | System Admin |
| Database Errors | Database Admin |
| Training Needed | Supervisor |

---

## ✅ Pre-Shift Checklist

### Before Starting Work
- [ ] System running properly
- [ ] Can log in successfully
- [ ] Real-time tracking loading
- [ ] Process programs accessible
- [ ] Network connection stable

### If Any Issues
1. Try restarting system
2. Check network connection
3. Contact supervisor/admin
4. Document issue for follow-up

---

## 🔒 Security Best Practices

### Do's ✅
- Change default password
- Log out when leaving
- Use strong passwords
- Report suspicious activity
- Keep credentials private

### Don'ts ❌
- Share login credentials
- Leave system unattended
- Write passwords down
- Use simple passwords
- Access admin features without authorization

---

## 📊 Status Indicators

### System Status
- **System Ready** - Normal operation
- **Launched: [Program]** - Program started
- **Viewing: [View]** - Current view active
- **Last updated: [Time]** - Data refresh time

### Lot Status (in programs)
- **IN** - Entering process
- **OUT** - Exiting process
- **DEFECT** - Quality issue found
- **PASS** - Quality approved

---

## 🎯 Performance Tips

### For Best Performance
1. Close unused program windows
2. Log out when not in use
3. Don't disable auto-refresh unnecessarily
4. Keep system updated
5. Report slowdowns to admin

### If System Slow
1. Check network connection
2. Close extra windows
3. Restart system
4. Contact admin if persists

---

## 📚 Documentation Index

| Document | Purpose |
|----------|---------|
| README.md | System overview and documentation |
| SETUP_GUIDE.md | Installation and configuration |
| FEATURES.md | Detailed feature descriptions |
| QUICK_REFERENCE.md | This guide - quick lookups |

---

## 🆘 Help Commands

### Getting Help
1. Press F1 (if implemented)
2. Check README.md
3. Review this Quick Reference
4. Contact system admin
5. Refer to training materials

---

**Print this page for quick desk reference!**

---

**Quick Reference Version**: 1.0  
**Last Updated**: 2026-07-02  
**For System Version**: 2.0
