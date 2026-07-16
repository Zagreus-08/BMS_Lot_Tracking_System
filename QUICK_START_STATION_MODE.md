# Quick Start - Station Mode

## 🚀 For Operators

### First Time Setup (Takes 30 seconds)

1. **Login** to the system
2. **Click** "Scan & Process" in the sidebar
3. **Select** your station type from the dropdown
4. **Click** "Save Configuration"
5. **Done!** Your computer is now configured

### Daily Use (Takes 5 seconds)

1. **Scan** the lot number (or type it and press Enter)
2. **Program launches** automatically
3. **Complete** your process work
4. **Scan** next lot

**That's it!** No menus, no selections, just scan and go.

---

## 🎯 Key Points

✅ **Each computer = One station = One process**  
✅ **Scan lot number → Program opens automatically**  
✅ **Configuration is permanent** (one-time setup)  
✅ **Can't launch wrong program** (station knows its job)

---

## 📍 Station Types

Pick the one that matches your workstation:

| Pick This... | If You Do... |
|--------------|--------------|
| STATION_01 - Lot Entry | Initial lot registration |
| STATION_02 - Assembly Measurement | Dimension measurements |
| STATION_03 - Cable Soldering | Cable soldering work |
| STATION_04 - Inductance & Resistance | Electrical testing |
| STATION_05 - Labelling | Product labeling |
| STATION_06 - MR Chip Alignment | Chip alignment checks |
| STATION_07 - MR Chip Height | Chip height measurement |
| STATION_08 - QA Final Inspection | Final QA before shipment |
| STATION_09 - QA Inspection | QA checkpoints 1 & 2 |
| STATION_10 - Resistance Measurement | SBB & cable resistance |
| STATION_11 - Sensor Sealing | Sealing operations |
| STATION_12 - Sensor Storage | Inventory management |
| STATION_13 - Shipment | Shipment preparation |
| STATION_14 - Molding Dimension | Molding verification |

---

## 🔧 For Admins

### Setup New Station Computer

1. Install BMS Lot Tracking System
2. Run `START_SYSTEM.bat`
3. Login as admin or operator
4. Click "Scan & Process"
5. Configure station type
6. Test with a real lot number
7. Label the physical workstation

### Manage Stations

**Tool**: Admin Programs → Station Configuration Manager

**Can Do**:
- View all station types
- Configure/reconfigure stations
- See current assignments
- Export configurations

### Change Station Assignment

**Easy Way**: Click "⚙ Reconfigure Station" in launcher  
**Admin Way**: Use Station Configuration Manager  
**Manual Way**: Delete `config/local_station.json`

---

## ⚠️ Common Questions

**Q: Do I configure every time I login?**  
A: No! Configure once, it remembers forever.

**Q: Can I use multiple processes from one computer?**  
A: No. Each station = one process. Use different computers for different processes.

**Q: What if I scan a wrong lot number?**  
A: If it doesn't exist in database, you'll see an error. Just scan the correct one.

**Q: How do I know what station this computer is?**  
A: The station badge shows at the top of the scanner (e.g., "STATION_03")

**Q: Can I change which station this computer is?**  
A: Yes, click "⚙ Reconfigure Station" button (requires confirmation)

---

## 🎬 Visual Workflow

```
┌──────────────────────┐
│  Operator Arrives    │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  System Shows        │
│  Station Scanner     │
│  (Auto-configured)   │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Scan Lot Number     │
│  (or type it)        │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Program Launches!   │
│  (automatically)     │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Do Process Work     │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Scan Next Lot       │
└──────────────────────┘
```

---

## 📖 Need More Help?

- **Full User Guide**: `STATION_MODE_GUIDE.md`
- **Technical Details**: `STATION_MODE_IMPLEMENTATION.md`
- **General System Info**: `SYSTEM_OVERVIEW.md`

---

**That's all you need to know!** Station Mode makes everything simple. 🎉
