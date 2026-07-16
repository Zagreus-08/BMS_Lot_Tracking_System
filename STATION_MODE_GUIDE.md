# Station Mode Guide - BMS Lot Tracking System

## Overview

The BMS Lot Tracking System now operates in **Station Mode** - each computer is dedicated to ONE specific process. Operators simply scan the lot number, and the system automatically launches the correct process program.

---

## 🎯 Key Concepts

### Station-Based Operation
- **One Station = One Process**: Each computer/workstation is configured for a specific process only
- **No Process Selection**: Operators don't see a menu of all processes
- **Scan & Go**: Scan lot number → Program launches automatically
- **Dedicated Workflow**: Each station knows its role in the production line

---

## 🚀 Initial Setup (One-Time Per Computer)

### Step 1: First Login
1. Launch the system using `START_SYSTEM.bat`
2. Log in with your credentials
3. Click **"Scan & Process"** in the sidebar

### Step 2: Configure Station
When you first access the station launcher, you'll see the **Station Configuration** screen:

1. **Select Your Station Type** from the dropdown:
   - STATION_01 - Lot Entry Station
   - STATION_02 - Assembly Measurement Station
   - STATION_03 - Cable Soldering Station
   - STATION_04 - Inductance & Resistance Station
   - STATION_05 - Labelling Station
   - STATION_06 - MR Chip Alignment Station
   - STATION_07 - MR Chip Height Station
   - STATION_08 - QA Final Inspection Station
   - STATION_09 - QA Inspection Station
   - STATION_10 - Resistance Measurement Station
   - STATION_11 - Sensor Sealing Station
   - STATION_12 - Sensor Storage Station
   - STATION_13 - Shipment Station
   - STATION_14 - Molding Dimension Station

2. **Review the process description** to confirm it's correct

3. **Click "Save Configuration"**

4. The computer is now permanently configured as that station type!

---

## 📦 Daily Operations

### Using the Station Launcher

Once configured, the station launcher appears with:
- **Station Badge**: Shows your station ID (e.g., STATION_03)
- **Station Name**: Clear identification (e.g., "Cable Soldering Station")
- **Process Name**: The dedicated process (e.g., "Cable Soldering")
- **Scanner Interface**: Large, clear input field for lot numbers

### How to Process a Lot

1. **Scan the Lot Number**
   - Use your barcode scanner to scan the lot QR code/barcode
   - OR manually type the lot number and press Enter

2. **System Validates**
   - Checks if lot exists in database
   - Shows error if lot not found

3. **Program Launches Automatically**
   - The correct process program opens
   - Continue with your normal process workflow
   - Status shows: "✓ Launched [Process] for lot [Number] at [Time]"

4. **Scan Next Lot**
   - Ready immediately for next lot
   - No need to close anything

### Visual Feedback

**Success**: ✓ Green checkmark with process name and timestamp  
**Not Found**: ❌ Red X with "Lot not found in system"  
**Warning**: ⚠ Yellow warning if field is empty  

---

## ⚙️ Reconfiguring a Station

If you need to change what process this computer handles:

1. Click **"⚙ Reconfigure Station"** at the bottom of the screen
2. Confirm the change
3. Select the new station type
4. Save configuration

**Note**: This should only be done when reassigning workstations!

---

## 🔐 Access Levels

### Operators
- Access to "Scan & Process" (Station Launcher)
- Access to "Real-time Tracking" (view only)
- Cannot access Admin Programs

### Administrators
- Full access to all features
- Can reconfigure stations
- Access to Admin Programs and User Management

---

## 📊 Station Mapping Reference

| Station ID | Station Name | Process Program |
|-----------|--------------|----------------|
| STATION_01 | Lot Entry Station | Lot Entry System |
| STATION_02 | Assembly Measurement Station | Assembly Measurement |
| STATION_03 | Cable Soldering Station | Cable Soldering |
| STATION_04 | Inductance & Resistance Station | Inductance & Resistance Measurement |
| STATION_05 | Labelling Station | Labelling |
| STATION_06 | MR Chip Alignment Station | MR Chip Alignment Measurement |
| STATION_07 | MR Chip Height Station | MR Chip Height Measurement |
| STATION_08 | QA Final Inspection Station | QA Final Inspection |
| STATION_09 | QA Inspection Station | QA Inspection 1 & 2 |
| STATION_10 | Resistance Measurement Station | SBB & Cable Resistance |
| STATION_11 | Sensor Sealing Station | Sensor Sealing |
| STATION_12 | Sensor Storage Station | Sensor Storage |
| STATION_13 | Shipment Station | Shipment Creation |
| STATION_14 | Molding Dimension Station | Top & Bottom Molding Dimension |

---

## 🛠️ Troubleshooting

### "Lot not found in system"
- **Cause**: Lot hasn't been entered into the system yet
- **Solution**: Ensure lot goes through Lot Entry Station first (STATION_01)

### "Program not found"
- **Cause**: Process program file is missing or path is incorrect
- **Solution**: Contact IT/Admin to verify process program installation

### Station configuration doesn't save
- **Cause**: Permission issues with config file
- **Solution**: Run as administrator or contact IT

### Wrong station selected
- **Solution**: Click "⚙ Reconfigure Station" and select the correct one

---

## 💡 Best Practices

1. **One Computer = One Station**: Don't change station types frequently
2. **Dedicated Hardware**: Label each computer with its station ID
3. **Barcode Scanners**: Use barcode scanners for speed and accuracy
4. **Verify Station**: Always check the station badge matches your workstation
5. **Close Programs**: Close the process program window after completing work on a lot

---

## 📝 Configuration Files

### Station Configuration
**Location**: `config/station_config.json`  
Contains the mapping of station IDs to processes

### Local Station Assignment  
**Location**: `config/local_station.json`  
Stores which station this computer is configured as

**Example**:
```json
{
  "station_id": "STATION_03"
}
```

---

## 🔄 Workflow Diagram

```
┌─────────────────────────────────────────┐
│  Operator arrives at workstation        │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  System shows station-specific          │
│  scanner interface (auto-configured)     │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  Operator scans lot number               │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  System validates lot exists             │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  Process program launches automatically  │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  Operator completes process work         │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  Operator closes program, scans next lot │
└─────────────────────────────────────────┘
```

---

## ❓ FAQ

**Q: Can I run multiple processes from one station?**  
A: No. Each station is dedicated to one process. This ensures clarity and prevents errors.

**Q: What if I need to run a different process temporarily?**  
A: You can reconfigure the station, but it's better to use the computer assigned to that process.

**Q: Do I need to enter the lot number every time?**  
A: Yes, each lot must be scanned to launch the program. This ensures correct tracking.

**Q: Can admins see all process programs?**  
A: Yes, admins can access "Admin Programs" which includes system management tools.

**Q: How do I know if a lot is ready for my station?**  
A: Check "Real-time Tracking" to see which lots are at which process stage.

---

## 📞 Support

For technical issues or questions:
- Contact your system administrator
- Refer to `SYSTEM_OVERVIEW.md` for general system information
- Check `START_HERE.md` for initial setup guidance

---

**Last Updated**: 2024  
**System Version**: 2.0 (Station Mode)
