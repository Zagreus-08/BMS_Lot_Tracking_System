import json
import tkinter as tk
from tkinter import messagebox, ttk
import sqlite3
import os

# Database file paths (update if needed)
MASTER_DB = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"
TRACK_DB = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"

# Path to process_flow.json
config_file_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\process_flow.json"

# Load process_flow and mapping
process_flow = []
process_column_mapping = {}
try:
    with open(config_file_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    process_flow = cfg.get("process_flow", []) or []
    process_column_mapping = cfg.get("process_column_mapping", {}) or {}
except FileNotFoundError:
    messagebox.showerror("Configuration Error", f"Config file not found at: {config_file_path}")
except json.JSONDecodeError:
    messagebox.showerror("Configuration Error", "Error decoding process_flow.json. Please check its format.")
except Exception as e:
    messagebox.showwarning("Configuration Warning", f"Error loading config file: {e}")

# List of categories
categories = [
    "OCR_Reading", "X_alignment_1", "Y_alignment_1", "X_alignment_2", "Y_alignment_2","mr_chip_height",
    "SBB_Resistance_Coil_Pos", "SBB_Resistance_Coil_Vb", "SBB_Resistance_Va_Vb", "SBB_Resistance_Vdd_GnD", 
    "BS_gap_to_GMR", "TS_gap_to_GMR", "BS_Gap_to_MR_Chip", "TS_Gap_to_MR_Chip", "PCB_Gap_to_BS1", "PCB_Gap_to_BS2",
    "QA_Inspection1_bottom", "QA_Inspection1_top", "Top_Molding_Length", "Top_Molding_Width",
    "Top_Molding_Height", "Wire1_Color", "Wire2_Color", "Wire3_Color", "Wire4_Color", "Wire5_Color", "Wire6_Color",
    "Labelling", "Cable_Resistance_48_turns", "Cable_Resistance_Coil_Vb", "Cable_Resistance_Va_Vb", "Cable_Resistance_Vdd_GnD", 
    "QA_Inspection2_bottom", "Bottom_Molding_Length", "Bottom_Molding_Width", "Bottom_Molding_Height",
    "Inductance", "Final_Resistance_Coil_Vb", "Final_Resistance_Va_Vb", "Final_Resistance_Vdd_GnD", 
    "Dynamic_range_uT", "Linearity_FS", "Sensitivity_mV_nT", "Sensitivity_uV_nT", "Noise_Density_1Hz", 
    "Noise_Density_10kHz", "QA_Final_bottom", "QA_Final_top", "QA_Final_sensor" 
]

_current_process_original = None  # Track original current process

def check_databases():
    missing = [p for p in (MASTER_DB, TRACK_DB) if not os.path.exists(p)]
    if missing:
        messagebox.showerror("Database missing", "Database file(s) not found:\n" + "\n".join(missing))
        return False
    return True

def load_lot_list():
    lots = set()
    try:
        conn = sqlite3.connect(TRACK_DB)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT lot_number FROM lot_tracking")
        for r in cur.fetchall():
            if r[0]:
                lots.add(str(r[0]))
        conn.close()
    except Exception:
        try:
            conn = sqlite3.connect(MASTER_DB)
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT lot_number FROM lot_masterlist")
            for r in cur.fetchall():
                if r[0]:
                    lots.add(str(r[0]))
            conn.close()
        except Exception as e:
            print("Error loading lot list:", e)
    lot_list = sorted(lots)
    lot_combobox['values'] = lot_list

def on_lot_selected(event=None):
    global _current_process_original
    lot_number = lot_combobox.get().strip()
    if not lot_number:
        return

    # Populate sensor combobox from masterlist
    sensor_ids = []
    try:
        conn = sqlite3.connect(MASTER_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT sensor_id FROM lot_masterlist WHERE lot_number = ?", (lot_number,))
        sensor_ids = [str(r[0]) for r in cursor.fetchall() if r[0]]
        conn.close()
        
        if not sensor_ids:
            messagebox.showwarning("No Sensors", f"No sensor IDs found for lot number: {lot_number}")
    except sqlite3.DatabaseError as e:
        messagebox.showerror("Database Error", f"The database file may be corrupted:\n{e}")
        return
    except Exception as e:
        messagebox.showerror("Error", f"Error loading sensors: {e}")
        return

    sensor_combobox['values'] = sensor_ids
    if sensor_ids:
        sensor_combobox.set(sensor_ids[0])
        on_sensor_selected()
    else:
        sensor_combobox.set("")
        # Clear all entry fields
        for cat in categories:
            entries[cat].delete(0, tk.END)

    # Load current process
    try:
        conn = sqlite3.connect(TRACK_DB)
        cursor = conn.cursor()
        
        cursor.execute("SELECT current_process FROM lot_tracking WHERE lot_number = ? LIMIT 1", (lot_number,))
        row = cursor.fetchone()
        conn.close()
        current_process_combobox.set(str(row[0]) if row and row[0] else "")
        _current_process_original = row[0] if row else ""
    except Exception as e:
        messagebox.showerror("Error", f"Error loading current process: {e}")

def on_sensor_selected(event=None):
    sensor_id = sensor_combobox.get().strip()
    if not sensor_id:
        return
    try:
        conn = sqlite3.connect(MASTER_DB)
        cursor = conn.cursor()
        
        # Get all column names from the table
        cursor.execute("PRAGMA table_info(lot_masterlist)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # Filter categories to only include existing columns
        valid_categories = [cat for cat in categories if cat in existing_columns]
        
        if not valid_categories:
            messagebox.showwarning("Warning", "No valid columns found in database")
            conn.close()
            return
        
        query = f"SELECT {', '.join(valid_categories)} FROM lot_masterlist WHERE sensor_id = ?"
        cursor.execute(query, (sensor_id,))
        row = cursor.fetchone()
        conn.close()
        
        # Clear all entries first
        for cat in categories:
            entries[cat].delete(0, tk.END)
        
        # Fill in values for valid columns
        if row:
            for i, cat in enumerate(valid_categories):
                if row[i] is not None:
                    entries[cat].insert(0, str(row[i]))
    except Exception as e:
        messagebox.showerror("Error", f"Error loading sensor data: {e}")

def _gather_all_mapped_columns():
    cols = []
    for v in process_column_mapping.values():
        if isinstance(v, (list, tuple)):
            for c in v:
                if c and c not in cols:
                    cols.append(c)
    return cols

def save_data():
    global _current_process_original
    lot_number = lot_combobox.get().strip()
    sensor_id = sensor_combobox.get().strip()
    if not lot_number or not sensor_id:
        messagebox.showerror("Error", "Lot Number and Sensor ID are required")
        return

    # Update masterlist - only update columns that exist
    try:
        conn = sqlite3.connect(MASTER_DB)
        cursor = conn.cursor()
        
        # Get all column names from the table
        cursor.execute("PRAGMA table_info(lot_masterlist)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # Only update columns that exist in the database
        for cat in categories:
            if cat in existing_columns:
                val = entries[cat].get().strip()
                q = f"UPDATE lot_masterlist SET {cat} = ? WHERE sensor_id = ?"
                try:
                    cursor.execute(q, (val if val != "" else None, sensor_id))
                except Exception as e:
                    print(f"Warning: Could not update {cat}: {e}")
        
        conn.commit()
        conn.close()
    except Exception as e:
        messagebox.showerror("DB Error", f"Error updating masterlist: {e}")
        return

    # Update tracking DB
    new_process = current_process_combobox.get().strip()
    try:
        conn2 = sqlite3.connect(TRACK_DB)
        cur2 = conn2.cursor()
        cur2.execute("UPDATE lot_tracking SET current_process = ? WHERE lot_number = ?", (new_process, lot_number))
        conn2.commit()
        conn2.close()
    except Exception as e:
        messagebox.showerror("DB Error", f"Error updating tracking: {e}")
        return

    _current_process_original = new_process
    messagebox.showinfo("Success", "Data saved successfully")
    load_lot_list()
    on_lot_selected()

# --- NEW FUNCTION: Delete Lot ---
def delete_lot():
    lot_number = lot_combobox.get().strip()
    if not lot_number:
        messagebox.showerror("Error", "Please select a Lot Number to delete.")
        return

    confirm = messagebox.askyesno(
        "Confirm Delete",
        f"Are you sure you want to delete Lot '{lot_number}'?\n"
        "This will remove all related Sensor IDs and data from both databases."
    )
    if not confirm:
        return

    try:
        # Delete from masterlist
        conn1 = sqlite3.connect(MASTER_DB)
        cur1 = conn1.cursor()
        cur1.execute("DELETE FROM lot_masterlist WHERE lot_number = ?", (lot_number,))
        conn1.commit()
        conn1.close()

        # Delete from tracking DB
        conn2 = sqlite3.connect(TRACK_DB)
        cur2 = conn2.cursor()
        cur2.execute("DELETE FROM lot_tracking WHERE lot_number = ?", (lot_number,))
        conn2.commit()
        conn2.close()

        # Refresh UI
        load_lot_list()
        lot_combobox.set("")
        sensor_combobox.set("")
        for cat in categories:
            entries[cat].delete(0, tk.END)

        messagebox.showinfo("Deleted", f"Lot '{lot_number}' and all its data have been deleted.")
    except Exception as e:
        messagebox.showerror("Delete Error", f"Error deleting lot: {e}")

# --- UI Setup ---
root = tk.Tk()
root.title("Sensor Data Input (Lot-based)")
root.geometry("450x550")  # <--- set your desired width x height here

if not check_databases():
    root.destroy()
    raise SystemExit("Missing database files")

top_frame = tk.Frame(root)
top_frame.pack(fill=tk.X, padx=8, pady=6)

tk.Label(top_frame, text="Lot Number:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
lot_combobox = ttk.Combobox(top_frame, width=30)
lot_combobox.grid(row=0, column=1, padx=4, pady=2, sticky="w")
lot_combobox.bind("<<ComboboxSelected>>", on_lot_selected)
lot_combobox.bind("<Return>", on_lot_selected)

tk.Label(top_frame, text="Sensor ID:").grid(row=1, column=0, sticky="w", padx=4, pady=2)
sensor_combobox = ttk.Combobox(top_frame, width=30)
sensor_combobox.grid(row=1, column=1, padx=4, pady=2, sticky="w")
sensor_combobox.bind("<<ComboboxSelected>>", on_sensor_selected)
sensor_combobox.bind("<Return>", on_sensor_selected)

tk.Label(top_frame, text="Current Process:").grid(row=2, column=0, sticky="w", padx=4, pady=2)
# Add "Sensor Storage" to process flow if not present
if "Sensor Storage" not in process_flow:
    process_flow.append("Sensor Storage")
current_process_combobox = ttk.Combobox(top_frame, width=30, values=process_flow)
current_process_combobox.grid(row=2, column=1, padx=4, pady=2, sticky="w")

save_button = tk.Button(top_frame, text="Save", command=save_data, width=12)
save_button.place(x=320, y=10)

delete_button = tk.Button(top_frame, text="Delete Lot", command=delete_lot, width=12, bg="#ff6961", fg="white")
delete_button.place(x=320, y=40)

# Scrollable frame for category entries
frame = tk.Frame(root)
frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

canvas = tk.Canvas(frame)
scrollbar = tk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
canvas.configure(yscrollcommand=scrollbar.set)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

input_frame = tk.Frame(canvas)
canvas.create_window((0, 0), window=input_frame, anchor='nw')

def on_canvas_configure(event):
    canvas.configure(scrollregion=canvas.bbox('all'))

canvas.bind('<Configure>', on_canvas_configure)

# Mouse wheel support
def _on_mousewheel(event):
    if hasattr(event, 'num') and event.num in (4, 5):
        if event.num == 4:
            canvas.yview_scroll(-1, "units")
        else:
            canvas.yview_scroll(1, "units")
    else:
        try:
            delta = int(-1*(event.delta/120))
        except Exception:
            delta = -1 if event.delta > 0 else 1
        if delta != 0:
            canvas.yview_scroll(delta, "units")

def _bind_to_mousewheel(event):
    canvas.bind_all("<MouseWheel>", _on_mousewheel)
    canvas.bind_all("<Button-4>", _on_mousewheel)
    canvas.bind_all("<Button-5>", _on_mousewheel)

def _unbind_from_mousewheel(event):
    canvas.unbind_all("<MouseWheel>")
    canvas.unbind_all("<Button-4>")
    canvas.unbind_all("<Button-5>")

canvas.bind("<Enter>", _bind_to_mousewheel)
canvas.bind("<Leave>", _unbind_from_mousewheel)
input_frame.bind("<Enter>", _bind_to_mousewheel)
input_frame.bind("<Leave>", _unbind_from_mousewheel)

# Category entries
entries = {}
for i, category in enumerate(categories):
    lbl = tk.Label(input_frame, text=category)
    lbl.grid(row=i, column=0, sticky="w", padx=6, pady=3)
    ent = tk.Entry(input_frame, width=40)
    ent.grid(row=i, column=1, padx=6, pady=3)
    entries[category] = ent

# Initialize UI
load_lot_list()
if lot_combobox['values']:
    lot_combobox.set(lot_combobox['values'][0])
    on_lot_selected()

root.mainloop()