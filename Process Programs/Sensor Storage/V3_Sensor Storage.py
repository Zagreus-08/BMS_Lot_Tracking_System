import tkinter as tk
from tkinter import ttk
from datetime import datetime
from tkinter import messagebox
import sqlite3
import os

# --- DATABASE PATHS ---
REF_DB_FILE = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"
STORAGE_DB_FILE = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\sensor_storage.db"
LOT_TRACKING_DB_FILE = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"

STORAGE_MAP = {
    "MAGS-N15H-AB000F": ("Nivio", "Rack 1"),
    "MAGS-N29H-AB000F": ("Nivio", "Rack 2"),
    "MAGS-N29H-AB000C": ("Nivio", "Rack 3"),
    "MAGS-N29H-AB000P": ("Nivio", "Rack 4"),
    "MAGS-S01H-AB000F": ("Nivio-S", "Rack 5"),
    "MAGS-S01H-AB000C": ("Nivio-S", "Rack 6"),
    "MAGS-S01H-AB000P": ("Nivio-S", "Rack 7"),
    "MAGS-M15H-AB000F": ("Migne", "Rack 8"), "MAGS-M15H-AB000C": ("Migne", "Rack 9"),
    "MAGS-M15H-AB000P": ("Migne", "Rack 10"), "MAGS-M29H-AB000F": ("Migne", "Rack 11"),
    "MAGS-M29H-AB000C": ("Migne", "Rack 12"), "MAGS-M29H-AB000P": ("Migne", "Rack 13"),
    "MAGS-M15H-AT000F": ("Migne", "Rack 14"), "MAGS-M15H-AT000C": ("Migne", "Rack 15"),
    "MAGS-M15H-AT000P": ("Migne", "Rack 16"), "MAGS-M29H-AT000F": ("Migne", "Rack 17"),
    "MAGS-M29H-AT000C": ("Migne", "Rack 18"), "MAGS-M29H-AT000P": ("Migne", "Rack 19"),
    "MAGS-M15V-AB000F": ("Migne", "Rack 20"), "MAGS-M15V-AB000C": ("Migne", "Rack 21"),
    "MAGS-M15V-AB000P": ("Migne", "Rack 22"), "MAGS-M29V-AB000F": ("Migne", "Rack 23"),
    "MAGS-M29V-AB000C": ("Migne", "Rack 24"), "MAGS-M29V-AB000P": ("Migne", "Rack 25"),
    "MAGS-M15V-AT000F": ("Migne", "Rack 26"), "MAGS-M15V-AT000C": ("Migne", "Rack 27"),
    "MAGS-M15V-AT000P": ("Migne", "Rack 28"), "MAGS-M29V-AT000F": ("Migne", "Rack 29"),
    "MAGS-M29V-AT000C": ("Migne", "Rack 30"), "MAGS-M29V-AT000P": ("Migne", "Rack 31"),
}

# optional GUI widgets (set to None when labels are removed)
sensor_lot_status = None
sensor_in_lot_val = None

def setup_storage_db():
    conn = sqlite3.connect(STORAGE_DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS storage_logs 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       sensor_id TEXT, product_desc TEXT, 
                       location TEXT, operator TEXT, timestamp TEXT,
                       status TEXT DEFAULT 'in_storage')''')
    conn.commit()
    conn.close()

def get_product_desc_from_master(sensor_id):
    try:
        conn = sqlite3.connect(REF_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT product_description FROM lot_masterlist WHERE sensor_id = ?", (sensor_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        print(f"Masterlist DB Connection Error: {e}")
        return None

def update_history_list(description=None):
    """Update the right-hand storage tree.

    - If description is None: show all sensors in storage.
    - If description is a string: show sensors matching that product_desc.
    - If description is a list/tuple: show sensors whose product_desc is in that list.
    """
    for item in storage_tree.get_children():
        storage_tree.delete(item)
    try:
        conn = sqlite3.connect(STORAGE_DB_FILE)
        cursor = conn.cursor()
        if description is None:
            cursor.execute("SELECT sensor_id, timestamp FROM storage_logs WHERE status IS NULL OR status = 'in_storage' ORDER BY id ASC")
            params = ()
        elif isinstance(description, (list, tuple, set)):
            descs = list(description)
            if not descs:
                conn.close()
                return
            placeholders = ','.join('?' for _ in descs)
            query = f"SELECT sensor_id, timestamp FROM storage_logs WHERE product_desc IN ({placeholders}) AND (status IS NULL OR status = 'in_storage') ORDER BY id ASC"
            cursor.execute(query, tuple(descs))
        else:
            cursor.execute("SELECT sensor_id, timestamp FROM storage_logs WHERE product_desc = ? AND (status IS NULL OR status = 'in_storage') ORDER BY id ASC", (description,))
        rows = cursor.fetchall()
        for idx, row in enumerate(rows, 1):
            storage_tree.insert("", tk.END, values=(idx, row[0], row[1]))
        conn.close()
    except Exception as e:
        print(f"Storage DB History Error: {e}")
    # update filter indicator label if present (show storage location numbers)
    try:
        if description is None:
            storage_filter_label.config(text='Current sensors in this storage: All')
        elif isinstance(description, (list, tuple, set)):
            items = [d for d in description]
            if not items:
                storage_filter_label.config(text='Current sensors in this storage: (none)')
            else:
                # map product descriptions to storage locations when available
                locs = []
                for d in items:
                    loc = STORAGE_MAP.get(d, (None, None))[1]
                    locs.append(loc if loc else d)
                # keep unique while preserving order
                seen = []
                for l in locs:
                    if l not in seen:
                        seen.append(l)
                if len(seen) == 1:
                    storage_filter_label.config(text=f'Current sensors in this storage: {seen[0]}')
                else:
                    storage_filter_label.config(text=f'Current sensors in this storage: {seen[0]} (+{len(seen)-1})')
        else:
            # single description: prefer storage location if known
            loc = STORAGE_MAP.get(description, (None, None))[1]
            if loc:
                storage_filter_label.config(text=f'Current sensors in this storage: {loc}')
            else:
                storage_filter_label.config(text=f'Current sensors in this storage: {description}')
    except Exception:
        pass

def update_storage_all():
    """Refresh the right-hand storage tree with all currently stored sensors."""
    for item in storage_tree.get_children():
        storage_tree.delete(item)
    try:
        conn = sqlite3.connect(STORAGE_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT sensor_id, timestamp FROM storage_logs WHERE status IS NULL OR status = 'in_storage' ORDER BY id ASC")
        rows = cursor.fetchall()
        for idx, row in enumerate(rows, 1):
            storage_tree.insert("", tk.END, values=(idx, row[0], row[1]))
        conn.close()
    except Exception as e:
        print(f"Storage DB Refresh Error: {e}")

def load_lot(event=None):
    lot = lot_entry.get().strip()
    lot_sensors.clear()
    for item in lot_tree.get_children():
        lot_tree.delete(item)
    if not lot:
        messagebox.showwarning("Input Required", "Please enter a Lot Number to load.")
        return
    try:
        # First, validate the lot's current process from lot_tracking
        conn_tracking = sqlite3.connect(LOT_TRACKING_DB_FILE)
        cursor_tracking = conn_tracking.cursor()
        cursor_tracking.execute("SELECT current_process FROM lot_tracking WHERE lot_number = ? LIMIT 1", (lot,))
        tracking_row = cursor_tracking.fetchone()
        conn_tracking.close()
        
        if not tracking_row:
            messagebox.showerror("Lot Not Found", f"Lot Number '{lot}' does not exist in the Lot Tracking database.\nPlease ensure the lot has been created in the system.")
            return
        
        current_process = tracking_row[0]
        
        # Check if current process is "Sensor Storage"
        if current_process != "Sensor Storage":
            messagebox.showerror("Invalid Process", 
                               f"The lot number inputted is not for Sensor Storage.\n\n"
                               f"Current Process: {current_process}\n\n"
                               f"Please ensure the lot's current process is set to 'Sensor Storage'.")
            return
        
        # Now load sensors from lot_masterlist
        conn = sqlite3.connect(REF_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT sensor_id, product_description FROM lot_masterlist WHERE lot_number = ?", (lot,))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            messagebox.showinfo("No Records", f"No sensors found for lot {lot}.")
            return
        # register all sensor IDs for the loaded lot but do NOT display them yet
        descs = set()
        for row in rows:
            sid = row[0]
            desc = row[1] if len(row) > 1 and row[1] else ''
            lot_sensors.add(sid)
            if desc:
                descs.add(desc)
        # update lot status and unlock sensor entry for scanning
        try:
            if sensor_lot_status is not None:
                sensor_lot_status.config(text=f"Loaded Lot: {lot}")
            ocr_text.config(state='normal')
            ocr_text.focus()
            lot_entry.config(state='disabled')
        except Exception:
            pass
        
        # if we have product descriptions for the lot, filter the storage display
        if descs:
            if len(descs) == 1:
                update_history_list(next(iter(descs)))
            else:
                update_history_list(list(descs))
    except Exception as e:
        messagebox.showerror("DB Error", f"Could not load lot: {e}")

def process_scan(event=None):
    sid = ocr_text.get().strip()
    if not sid: return
    desc = get_product_desc_from_master(sid)
    if desc:
        family, loc = STORAGE_MAP.get(desc, ("Unknown", "No Location Defined"))
        sensor_type_val.config(text=family)
        location_val.config(text=loc)
        product_text.config(state='normal')
        product_text.delete('1.0', tk.END)
        product_text.insert('1.0', desc)
        product_text.config(state='disabled')
        update_history_list(desc)
        # indicate whether scanned sensor belongs to loaded lot
        if sid in lot_sensors:
            try:
                if sensor_in_lot_val is not None:
                    sensor_in_lot_val.config(text="IN LOT", fg="#00FF00")
            except Exception:
                pass
            # if not already displayed in lot_tree, add it now
            exists = False
            for iid in lot_tree.get_children():
                vals = lot_tree.item(iid, 'values')
                if len(vals) > 1 and vals[1] == sid:
                    exists = True
                    lot_tree.selection_set(iid)
                    lot_tree.see(iid)
                    break
            if not exists:
                idx = len(lot_tree.get_children()) + 1
                lot_tree.insert("", tk.END, values=(idx, sid, desc))
                # select the newly inserted item
                for iid in lot_tree.get_children():
                    vals = lot_tree.item(iid, 'values')
                    if len(vals) > 1 and vals[1] == sid:
                        lot_tree.selection_set(iid)
                        lot_tree.see(iid)
                        break
        else:
            try:
                if sensor_in_lot_val is not None:
                    sensor_in_lot_val.config(text="NOT IN LOT", fg="red")
            except Exception:
                pass
    else:
        sensor_type_val.config(text="NOT FOUND")
        location_val.config(text="---")
        product_text.config(state='normal')
        product_text.delete('1.0', tk.END)
        product_text.config(state='disabled')
        for item in storage_tree.get_children():
            storage_tree.delete(item)
    # clear the entry so the user can scan/input the next sensor immediately
    try:
        ocr_text.delete(0, tk.END)
        ocr_text.focus()
    except Exception:
        pass

def clear_fields():
    ocr_text.delete(0, tk.END)
    product_text.config(state='normal')
    product_text.delete('1.0', tk.END)
    product_text.config(state='disabled')
    sensor_type_val.config(text="---")
    location_val.config(text="---")
    operator_entry.delete(0, tk.END)
    for item in storage_tree.get_children():
        storage_tree.delete(item)
    for item in lot_tree.get_children():
        lot_tree.delete(item)
    lot_sensors.clear()
    # also clear the lot number textbox and reset lot status
    try:
        lot_entry.config(state='normal')
        lot_entry.delete(0, tk.END)
        sensor_lot_status.config(text='No Lot Loaded')
        # lock sensor entry until next valid lot
        ocr_text.config(state='disabled')
    except Exception:
        pass
    # reset storage display to show all sensors
    try:
        update_history_list(None)
    except Exception:
        pass
    lot_entry.focus()

def store_data():
    # If there are confirmed (scanned) sensors in the lot_tree, store them all as a batch.
    operator = operator_entry.get().strip()
    lot_items = list(lot_tree.get_children())
    if lot_items:
        if not operator:
            messagebox.showwarning("Input Required", "Please enter Operator name before storing lot sensors.")
            return
        try:
            conn = sqlite3.connect(STORAGE_DB_FILE)
            cursor = conn.cursor()
            inserted = 0
            skipped = []
            for iid in lot_items:
                vals = lot_tree.item(iid, 'values')
                if len(vals) < 2:
                    continue
                sensor_id = vals[1]
                # Duplicate check
                cursor.execute("SELECT sensor_id FROM storage_logs WHERE sensor_id = ? AND (status IS NULL OR status = 'in_storage')", (sensor_id,))
                if cursor.fetchone():
                    skipped.append(sensor_id)
                    continue
                prod = get_product_desc_from_master(sensor_id) or ''
                family, loc = STORAGE_MAP.get(prod, ("Unknown", "No Location Defined"))
                timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
                cursor.execute("INSERT INTO storage_logs (sensor_id, product_desc, location, operator, timestamp, status) VALUES (?, ?, ?, ?, ?, ?)",
                               (sensor_id, prod, loc, operator, timestamp, 'in_storage'))
                inserted += 1
                # remove from lot list and registered set
                lot_tree.delete(iid)
                lot_sensors.discard(sensor_id)
            conn.commit()
            conn.close()
            update_storage_all()
            msg = f"Stored {inserted} sensors."
            if skipped:
                msg += f" Skipped {len(skipped)} duplicates: {', '.join(skipped)}."
            messagebox.showinfo("Success", msg)
            ocr_text.delete(0, tk.END)
            ocr_text.focus()
        except Exception as e:
            messagebox.showerror("Database Error", f"Could not save lot sensors: {e}")
        return

    # Fallback: store single scanned sensor (previous behaviour)
    sensor_id = ocr_text.get().strip()
    product_desc = product_text.get('1.0', tk.END).strip()
    location = location_val.cget("text")
    if not operator or not sensor_id:
        messagebox.showwarning("Input Required", "Please ensure Sensor ID is scanned and Operator name is entered.")
        return
    try:
        conn = sqlite3.connect(STORAGE_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT operator,timestamp FROM storage_logs WHERE sensor_id = ? AND (status IS NULL OR status = 'in_storage') LIMIT 1", (sensor_id,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            op, ts = existing
            messagebox.showinfo("Already In Storage", f"Sensor {sensor_id} is already in storage (stored by: {op} at {ts}). No changes made.")
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        cursor.execute("INSERT INTO storage_logs (sensor_id, product_desc, location, operator, timestamp, status) VALUES (?, ?, ?, ?, ?, ?)",
                       (sensor_id, product_desc, location, operator, timestamp, 'in_storage'))
        conn.commit()
        conn.close()
        update_storage_all()
        messagebox.showinfo("Success", f"Sensor {sensor_id} saved.")
        ocr_text.delete(0, tk.END)
        ocr_text.focus()
    except Exception as e:
        messagebox.showerror("Database Error", f"Could not save: {e}")

def create_gui():
    global ocr_text, product_text, sensor_type_val, location_val, operator_entry, storage_tree, storage_filter_label
    setup_storage_db()
    root = tk.Tk()
    root.title("BMS Sensor Storage System")
    root.geometry("1250x450")
    root.configure(bg='#3366cc')
    tk.Label(root, text="BMS Sensor Storage", font=("Arial", 22, "bold"), bg="#3366cc", fg="orange").place(x=10, y=5)
    tk.Label(root, text='Sensor ID:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold')).place(x=20, y=210)
    ocr_text = tk.Entry(root, width=20, font=('Arial', 11))
    ocr_text.place(x=200, y=210)
    # scanner will send Enter; trigger scan processing on Return
    ocr_text.bind('<Return>', process_scan)
    # start locked; enabled after a valid lot is loaded
    ocr_text.config(state='disabled')
    tk.Label(root, text='Product Description:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold')).place(x=20, y=90)
    product_text = tk.Text(root, width=20, height=1, font=('Arial', 11))
    product_text.place(x=200, y=90)
    product_text.config(state='disabled')
    tk.Label(root, text='Sensor Type:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold')).place(x=20, y=120)
    sensor_type_val = tk.Label(root, text='---', bg='#3366cc', fg='yellow', font=('Arial', 11, 'bold'))
    sensor_type_val.place(x=200, y=120)
    tk.Label(root, text='Storage Location:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold')).place(x=20, y=150)
    location_val = tk.Label(root, text='---', bg='#3366cc', fg='#00FF00', font=('Arial', 12, 'bold'))
    location_val.place(x=200, y=150)
    tk.Label(root, text='Operator Name:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold')).place(x=20, y=180)
    operator_entry = tk.Entry(root, width=20, font=('Arial', 11))
    operator_entry.place(x=200, y=180)
    # Lot controls
    tk.Label(root, text='Lot Number:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold')).place(x=20, y=60)
    global lot_entry, lot_tree, lot_sensors, sensor_in_lot_val, sensor_lot_status
    lot_entry = tk.Entry(root, width=20, font=('Arial', 11))
    lot_entry.place(x=200, y=60)
    lot_entry.bind('<Return>', load_lot)
    lot_entry.focus()
    # status label to show whether a lot is loaded and to control unlocking
    sensor_lot_status = tk.Label(root, text='No Lot Loaded', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    sensor_lot_status.place(x=400, y=35)
    tk.Button(root, text="STORE DATA", font=("Tahoma", 15, "bold"), bg="#32CD32", fg="black", command=store_data, height=2, width=12).place(x=20, y=340)
    tk.Button(root, text="CLEAR", font=("Tahoma", 15, "bold"), bg="#FFD700", fg="black", command=clear_fields, height=2, width=12).place(x=200, y=340)
    tk.Label(root, text='Sensors in this Lot:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold')).place(x=400, y=60)
    storage_filter_label = tk.Label(root, text='Filter: All', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    storage_filter_label.place(x=820, y=60)
    history_frame = tk.Frame(root)
    history_frame.place(x=400, y=85, width=840, height=320)
    # split history_frame into lot list (left) and storage list (right)
    lot_frame = tk.Frame(history_frame)
    lot_frame.pack(side='left', fill='both', expand=True)
    storage_frame = tk.Frame(history_frame)
    storage_frame.pack(side='right', fill='both', expand=True)

    # Lot Treeview
    lot_columns = ("no", "sensor_id", "desc")
    lot_tree = ttk.Treeview(lot_frame, columns=lot_columns, show='headings')
    lot_tree.heading("no", text="#")
    lot_tree.heading("sensor_id", text="Sensor ID")
    lot_tree.heading("desc", text="Description")
    lot_tree.column("no", width=30, anchor='center')
    lot_tree.column("sensor_id", width=120)
    lot_tree.column("desc", width=150)
    lot_scroll = ttk.Scrollbar(lot_frame, orient="vertical", command=lot_tree.yview)
    lot_tree.configure(yscrollcommand=lot_scroll.set)
    lot_tree.pack(side='left', fill='both', expand=True)
    lot_scroll.pack(side='right', fill='y')

    # Storage Treeview (current sensors in storage)
    columns = ("no", "sensor_id", "time")
    storage_tree = ttk.Treeview(storage_frame, columns=columns, show='headings')
    storage_tree.heading("no", text="#")
    storage_tree.heading("sensor_id", text="Sensor ID")
    storage_tree.heading("time", text="Date Stored")
    storage_tree.column("no", width=30, anchor='center')
    storage_tree.column("sensor_id", width=120)
    storage_tree.column("time", width=150)
    storage_scroll = ttk.Scrollbar(storage_frame, orient="vertical", command=storage_tree.yview)
    storage_tree.configure(yscrollcommand=storage_scroll.set)
    storage_tree.pack(side='left', fill='both', expand=True)
    storage_scroll.pack(side='right', fill='y')
    # set globals used by functions
    globals()['lot_sensors'] = set()
    # initial display: show all sensors in storage
    try:
        update_history_list(None)
    except Exception:
        pass
    root.mainloop()

if __name__ == "__main__":
    create_gui()