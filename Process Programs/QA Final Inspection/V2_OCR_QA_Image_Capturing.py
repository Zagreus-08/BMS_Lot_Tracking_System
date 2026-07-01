import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import sqlite3
import time
import os
import shutil
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image, ImageTk, ImageEnhance
import threading
import cv2
from datetime import datetime
import json

# Define the paths to the databases
db_path_tracking = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"
db_path_masterlist = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"
# original microscope save folder (used for non-Sensor_Image columns)
microscope_folder = r'C:\Users\a493353\Documents\Digital Microscope\Default\Picture'
# Pictures folder where Capture Image will save and Sensor Image column will monitor
pictures_folder = r'C:\Users\a493353\Pictures'
destination_folder = r"\\phlsvr08\BMS Data\Assembly Data\QA Visual Inspection"

config_file_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\process_flow.json"

# ---------------- Globals ----------------
fname = None
sens_id = None
lot_number = None
curr_proc = None
current_col = None
current_row = None
suffix = None

# sensor ids expected for the current lot (populated by fetch_lot_info)
sensor_ids_expected = set()
sensor_count = 0
sensor_ids_no_defects = []

# for after scheduling cancellation
datetime_after_id = None

# watchdog / threading globals
stop_event = threading.Event()
monitor_thread = None
observer = None

# small debounce for file events
processed_files = {}
debounce_time = 1

# Load config JSON (process_flow and mapping)
try:
    with open(config_file_path, 'r') as f:
        config = json.load(f)
    process_flow = config.get("process_flow", [])
    process_column_mapping = config.get("process_column_mapping", {})
except FileNotFoundError:
    messagebox.showerror("Configuration Error", "Config file not found at: " + config_file_path)
    raise SystemExit
except json.JSONDecodeError:
    messagebox.showerror("Configuration Error", "Error decoding process_flow.json. Please check its format.")
    raise SystemExit

# ---------------- Tkinter setup ----------------
root = tk.Tk()
root.title("QA Visual Inspection System")
root.geometry("1250x640")
root.configure(bg="lightblue")
root.resizable(False, False)

cap = None

# ---------------- Utility functions ----------------
def find_row_col(widget):
    for r_idx, row in enumerate(data_entry):
        for c_idx, ent in enumerate(row):
            if ent == widget:
                return r_idx, c_idx
    return None, None

# ------------------ Sensor scanning logic ------------------
def handle_scanned_sensor(scanned_value, row_index=None):
    """
    Validate scanned sensor id, lock it into the row, enable columns 1..3 and focus col 1.
    """
    global sensor_ids_expected, current_row, current_col

    scanned = (scanned_value or "").strip()
    if not scanned:
        messagebox.showwarning("Warning", "Scanned value is empty.")
        return

    lot = entries["Lot Number:"].get().strip()
    if not lot:
        messagebox.showwarning("Warning", "Please enter Lot Number first.")
        return

    if row_index is None:
        row_index = current_row

    if row_index is None:
        messagebox.showwarning("Warning", "No sensor row is selected/focused for scanning.")
        return

    # NOTE: skip lot-membership validation here — accept the scanned sensor
    # (we still keep duplicate detection below)

    # Duplicate check
    for i in range(len(data_entry)):
        if i != row_index and data_entry[i][0].get().strip() == scanned:
            messagebox.showerror("Duplicate Sensor ID", "Sensor ID '{}' is already used in row {}.".format(scanned, i+1))
            data_entry[row_index][0].delete(0, tk.END)
            data_entry[row_index][0].focus_set()
            current_row, current_col = row_index, 0
            return

    # Write and lock sensor id for this row
    data_entry[row_index][0].config(state="normal")
    data_entry[row_index][0].delete(0, tk.END)
    data_entry[row_index][0].insert(0, scanned)
    data_entry[row_index][0].config(state="readonly")

    # enable measurement/image columns for this row
    for col in range(1, 4):
        if col < len(data_entry[row_index]):
            data_entry[row_index][col].config(state="normal")

    # move focus to first measurement/image column
    data_entry[row_index][1].focus_set()
    current_row, current_col = row_index, 1

def on_sensor_entry_return(event):
    widget = event.widget
    row_idx, col_idx = find_row_col(widget)
    if row_idx is None:
        return
    scanned_val = widget.get().strip()
    handle_scanned_sensor(scanned_val, row_index=row_idx)

def get_lot_condition(lot_number):
    conn = sqlite3.connect(db_path_masterlist)
    cursor = conn.cursor()
    cursor.execute("SELECT condition FROM lot_masterlist WHERE lot_number=?", (lot_number,))
    row = cursor.fetchone()
    conn.close()
    return row[0].strip().upper() if row and row[0] else "MP"

# ---------------- Fetch lot info and configure rows ----------------
def fetch_lot_info(event=None):
    global sensor_ids_expected, sensor_count, sensor_ids_no_defects, lot_number, curr_proc
    lot_number = entries["Lot Number:"].get().strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number.")
        return

    try:
        conn = sqlite3.connect(db_path_tracking)
        cursor = conn.cursor()

        # --- Fetch current process ---
        cursor.execute("SELECT current_process FROM lot_tracking WHERE lot_number=?", (lot_number,))
        row = cursor.fetchone()
        if not row:
            messagebox.showwarning("Warning", "Lot Number not found in the database.")
            conn.close()
            return

        current_process = row[0]
        curr_proc = current_process

        # --- Fetch lot condition ---
        try:
            conn2 = sqlite3.connect(db_path_masterlist)
            c2 = conn2.cursor()
            c2.execute("SELECT condition FROM lot_masterlist WHERE lot_number=?", (lot_number,))
            r2 = c2.fetchone()
            lot_condition = r2[0].strip().upper() if r2 and r2[0] else "MP"
            conn2.close()
        except Exception:
            lot_condition = "MP"

        # --- Update UI ---
        entries["Current Process:"].config(state="normal")
        entries["Current Process:"].delete(0, tk.END)
        entries["Current Process:"].insert(0, current_process)
        entries["Current Process:"].config(state="readonly")

        # --- Enforce allowed process for MP lots ---
        if lot_condition == "MP" and current_process != "QA Visual Inspection":
            messagebox.showerror("Error", "The lot number inputted is not for QA Visual Inspection.")
            delete_action()
            conn.close()
            return

        # --- Fetch sensors without previous defects ---
        current_process_index = process_flow.index(current_process)
        if current_process_index > 0:
            previous_defect_columns = []
            for proc in process_flow[:current_process_index]:
                cols = process_column_mapping.get(proc)
                if cols and len(cols) > 2:
                    previous_defect_columns.append(cols[2])

            if previous_defect_columns:
                defect_conditions = " AND ".join(f"({col} IS NULL OR {col}='')" for col in previous_defect_columns)
                query = f"SELECT sensor_id FROM lot_tracking WHERE lot_number=? AND {defect_conditions}"
                cursor.execute(query, (lot_number,))
            else:
                cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot_number,))
        else:
            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot_number,))

        rows = cursor.fetchall()
        conn.close()

        # --- Setup table entries ---
        sensor_ids_no_defects = [r[0].strip() for r in rows if r and r[0]]
        sensor_count = len(sensor_ids_no_defects)
        sensor_ids_expected = set(sensor_ids_no_defects)

        for r in range(len(data_entry)):
            for c in range(4):
                try:
                    data_entry[r][c].config(state="normal")
                    data_entry[r][c].delete(0, tk.END)
                except:
                    pass
            if r < sensor_count:
                data_entry[r][0].config(state="normal")
                for c in range(1, 4):
                    data_entry[r][c].config(state="readonly")
            else:
                for c in range(4):
                    data_entry[r][c].config(state="readonly")

        if sensor_count > 0:
            data_entry[0][0].focus_set()
            global current_row, current_col
            current_row, current_col = 0, 0
        else:
            messagebox.showinfo("Info", "No sensors found for this Lot Number.")

        # Store for popup use
        fetch_lot_info.lot_condition = lot_condition

    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")

# ---------------- Date/time updater ----------------
def update_datetime():
    global datetime_after_id
    try:
        current_time = time.strftime("%Y-%m-%d %I:%M:%S %p")
        entries["Date and Time:"].config(state="normal")
        entries["Date and Time:"].delete(0, tk.END)
        entries["Date and Time:"].insert(0, current_time)
        entries["Date and Time:"].config(state="readonly")
        datetime_after_id = root.after(1000, update_datetime)
    except tk.TclError:
        datetime_after_id = None

# ---------------- File monitoring (watch specific folder) ----------------
def get_most_recent_file(folder_path):
    try:
        files = [os.path.join(folder_path, f) for f in os.listdir(folder_path)
                 if os.path.isfile(os.path.join(folder_path, f))]
    except Exception:
        return None
    if not files:
        return None
    return max(files, key=os.path.getctime)

class SimpleHandler(FileSystemEventHandler):
    def __init__(self, folder):
        super().__init__()
        self.folder = folder

    def on_created(self, event):
        if event.is_directory:
            return
        file_path = event.src_path
        current_time = time.time()
        if file_path in processed_files and (current_time - processed_files[file_path] < debounce_time):
            return
        processed_files[file_path] = current_time

        most_recent_file = get_most_recent_file(self.folder)
        if not most_recent_file:
            return

        # Only show popup if user is focused on a measurement column (1,2,3)
        if current_col is None:
            return

        # only proceed if focused column is one of capture columns
        if current_col not in (1, 2, 3):
            return

        time.sleep(1)

        # show popup immediately (no OCR / matching)
        root.after(0, show_popup, most_recent_file, file_path)

def monitor_folder(src_folder):
    global observer
    observer = Observer()
    handler = SimpleHandler(src_folder)
    observer.schedule(handler, path=src_folder, recursive=False)
    observer.start()
    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    finally:
        observer.stop()
        observer.join()

def start_monitoring(src_folder):
    global monitor_thread, stop_event
    stop_monitoring()
    stop_event.clear()
    monitor_thread = threading.Thread(target=monitor_folder, args=(src_folder,), daemon=True)
    monitor_thread.start()

def stop_monitoring():
    global monitor_thread, stop_event
    if monitor_thread and monitor_thread.is_alive():
        stop_event.set()
        monitor_thread.join(timeout=2)
    stop_event.clear()

# ---------------- GUI widgets and layout ----------------
title_label = tk.Label(root, text="QA Visual Inspection System", font=("BiomeW04-Bold", 20, "bold"), bg="lightblue")
title_label.place(x=10, y=0)

labels = ["Lot Number:", "Current Process:", "Date and Time:", "Operator:"]
entries = {}
label_positions = {
    "Lot Number:": (10, 40),
    "Current Process:": (10, 65),
    "Date and Time:": (10, 90),
    "Operator:": (10, 115)
}
entry_positions = {
    "Lot Number:": (120, 40),
    "Current Process:": (120, 65),
    "Date and Time:": (120, 90),
    "Operator:": (120, 115)
}

for label_text in labels:
    label = tk.Label(root, text=label_text, font=("Arial", 10), bg="lightblue")
    label.place(x=label_positions[label_text][0], y=label_positions[label_text][1])
    entry = tk.Entry(root, width=30, justify='center')
    entry.place(x=entry_positions[label_text][0], y=entry_positions[label_text][1])
    entries[label_text] = entry

entries["Date and Time:"].config(state="readonly")
update_datetime()

# bind Enter for lot number
entries["Lot Number:"].bind("<Return>", fetch_lot_info)

# Buttons
def delete_action():
    global sensor_ids_expected, sensor_count
    sensor_ids_expected = set()
    sensor_count = 0
    for entry in entries.values():
        entry.config(state="normal")
        entry.delete(0, tk.END)
    entries["Current Process:"].config(state="readonly")
    # Clear and set all table entries to readonly initially
    for r in range(len(data_entry)):
        for c in range(4):
            data_entry[r][c].config(state="normal")
            data_entry[r][c].delete(0, tk.END)
            data_entry[r][c].config(state="readonly")

# ---------- BMS Popup class (embedded and adapted) ----------
class BMSPopup(tk.Toplevel):
    def __init__(self, master, lot_number, current_process, operator,
                 sensor_list, combobox_candidates, failed_sensor_list,
                 blank_judgement_list, csv_rows_data, lot_condition="MP"):
        super().__init__(master)
        self.title("BMS Lot Tracking System - Popup")
        self.geometry("615x455")
        self.configure(bg='#3a6ba8')
        self.resizable(False, False)

        self.lot_number = lot_number
        self.current_process = current_process
        self.operator = operator
        self.sensor_list = sensor_list[:]
        self.failed_sensor_list = failed_sensor_list[:]
        self.blank_judgement_list = blank_judgement_list[:]
        self.csv_rows_data = csv_rows_data[:]
        self.lot_condition = str(lot_condition).strip().upper()

        # --- Header ---
        tk.Label(self, text="BMS Lot Tracking System", font=("BiomeW04-Bold", 20, "bold"),
                 bg='#3a6ba8', fg="orange").place(x=20, y=0)

        # --- Lot Info ---
        tk.Label(self, text="Lot Number:", bg='#3a6ba8', fg="white").place(x=5, y=45)
        self.lot_entry = tk.Entry(self, width=31)
        self.lot_entry.place(x=105, y=45)
        self.lot_entry.insert(0, lot_number)
        self.lot_entry.config(state="readonly")

        tk.Label(self, text="Current Process:", bg='#3a6ba8', fg="white").place(x=5, y=75)
        self.proc_entry = tk.Entry(self, width=31)
        self.proc_entry.place(x=105, y=75)
        self.proc_entry.insert(0, current_process)
        self.proc_entry.config(state="readonly")

        # --- Sensor Combo ---
        tk.Label(self, text="Sensor ID:", bg='#3a6ba8', fg="white").place(x=5, y=105)
        if self.lot_condition == "EVAL":
            self.sensor_combo = ttk.Combobox(self, values=[], width=28, state="readonly")
        else:
            self.sensor_combo = ttk.Combobox(self, values=combobox_candidates, width=28)
            if combobox_candidates:
                self.sensor_combo.set(combobox_candidates[0])
        self.sensor_combo.place(x=105, y=105)

        # --- Defect/Remarks ---
        tk.Label(self, text="Defect:", bg='#3a6ba8', fg="white").place(x=5, y=135)
        self.defect_entry = tk.Entry(self, width=31)
        self.defect_entry.place(x=105, y=135)

        tk.Label(self, text="Remarks:", bg='#3a6ba8', fg="white").place(x=5, y=165)
        self.remarks_entry = tk.Entry(self, width=31)
        self.remarks_entry.place(x=105, y=165)

        # --- Quantity / Date / Operator ---
        tk.Label(self, text="Quantity IN:", bg='#3a6ba8', fg="white").place(x=320, y=45)
        self.qin = tk.Entry(self, width=15)
        self.qin.place(x=410, y=45)

        tk.Label(self, text="Quantity OUT:", bg='#3a6ba8', fg="white").place(x=320, y=75)
        self.qout = tk.Entry(self, width=15)
        self.qout.place(x=410, y=75)

        tk.Label(self, text="Date:", bg='#3a6ba8', fg="white").place(x=320, y=105)
        self.date_label = tk.Label(self, text="", bg='white', width=19)
        self.date_label.place(x=410, y=105)

        tk.Label(self, text="Operator:", bg='#3a6ba8', fg="white").place(x=320, y=135)
        self.op_entry = tk.Entry(self, width=22)
        self.op_entry.place(x=410, y=135)
        self.op_entry.insert(0, self.operator)

        # --- Buttons ---
        tk.Button(self, text="Export Defects / Remarks", command=self.export_data, bg="green",
                  fg="white", font=("Tahoma", 10, "bold")).place(x=20, y=200)
        tk.Button(self, text="CLEAR", command=self.clear_fields, bg="yellow",
                  font=("Tahoma", 16, "bold")).place(x=320, y=185)
        tk.Button(self, text="SAVE", command=self.save_data_and_advance, bg="green",
                  fg="white", font=("Tahoma", 16, "bold")).place(x=460, y=185)

        # --- Table ---
        self.columns = ("Sensor ID", "Defects", "Remarks")
        self.table = ttk.Treeview(self, columns=self.columns, show="headings", height=7)
        for c in self.columns:
            self.table.heading(c, text=c)
        self.table.place(x=5, y=280)

        self.update_time()
        self.compute_quantities()

    def update_time(self):
        now = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        self.date_label.config(text=now)
        self.after(1000, self.update_time)

    def clear_fields(self):
        self.defect_entry.delete(0, tk.END)
        self.remarks_entry.delete(0, tk.END)

    def export_data(self):
        sid = self.sensor_combo.get().strip()
        defect = self.defect_entry.get().strip()
        remarks = self.remarks_entry.get().strip()
        if not sid:
            messagebox.showwarning("Input Error", "Please select Sensor ID.")
            return
        if not defect:
            messagebox.showwarning("Input Error", "Please input defect before exporting.")
            return
        existing = [self.table.item(r)["values"][0] for r in self.table.get_children()]
        if sid in existing:
            messagebox.showwarning("Duplicate", f"Sensor ID {sid} already exists.")
            return
        self.table.insert('', 'end', values=(sid, defect, remarks))
        self.clear_fields()

    def compute_quantities(self):
        total = len(self.sensor_list)
        done = 0
        for r in range(len(data_entry)):
            sid = data_entry[r][0].get().strip()
            if not sid:
                continue
            bot = data_entry[r][1].get().strip().lower()
            top = data_entry[r][2].get().strip().lower()
            sen = data_entry[r][3].get().strip().lower()
            if bot == "captured" and top == "captured" and sen == "captured":
                done += 1
        self.qin.insert(0, str(total))
        self.qout.insert(0, str(done))

    def save_data_and_advance(self):
        lot = self.lot_number
        proc = self.current_process
        op = self.op_entry.get().strip()
        if not op:
            messagebox.showwarning("Input Error", "Please enter Operator.")
            return
        proc_dt = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        cols = process_column_mapping.get(proc, [])
        if self.lot_condition == "MP" and (not cols or len(cols) < 6):
            messagebox.showerror("Error", f"Process mapping for {proc} invalid.")
            return

        qin = self.qin.get().strip()
        qout = self.qout.get().strip()
        conn = sqlite3.connect(db_path_tracking)
        cur = conn.cursor()

        if self.lot_condition == "MP":
            for item in self.table.get_children():
                sid, defect, remarks = self.table.item(item)["values"]
                cur.execute(f"""
                    UPDATE lot_tracking
                    SET {cols[0]}=?, {cols[1]}=?, {cols[2]}=?, {cols[3]}=?, {cols[4]}=?, {cols[5]}=?
                    WHERE lot_number=? AND sensor_id=?""",
                    (qin, qout, defect, remarks, proc_dt, op, lot, sid))
            # Advance to next process
            try:
                idx = process_flow.index(proc)
                next_proc = process_flow[idx + 1]
            except Exception:
                next_proc = proc
            cur.execute("UPDATE lot_tracking SET current_process=? WHERE lot_number=?", (next_proc, lot))
            msg = f"Data saved successfully. Next process: {next_proc}"
        else:
            cur.execute("""UPDATE lot_tracking SET operator=?, last_update=? WHERE lot_number=?""",
                        (op, proc_dt, lot))
            msg = "Data saved successfully (EVAL lot - process not advanced)."

        conn.commit()
        conn.close()
        messagebox.showinfo("Save", msg)
        self.destroy()
        delete_action()

# it will validate inputs & open the popup which will perform DB write and CSV export.
def save_action():
    try:
        if not entries["Operator:"].get().strip():
            messagebox.showerror("Error", "Operator field must be filled.")
            return

        lot = entries["Lot Number:"].get().strip()
        proc = entries["Current Process:"].get().strip()
        op = entries["Operator:"].get().strip()

        # Get lot condition
        try:
            conn = sqlite3.connect(db_path_masterlist)
            c = conn.cursor()
            c.execute("SELECT condition FROM lot_masterlist WHERE lot_number=?", (lot,))
            r = c.fetchone()
            lot_cond = r[0].strip().upper() if r and r[0] else "MP"
            conn.close()
        except Exception:
            lot_cond = "MP"

        # Expected sensors
        conn = sqlite3.connect(db_path_tracking)
        cur = conn.cursor()
        cur.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot,))
        rows = cur.fetchall()
        conn.close()
        sensors = [r[0] for r in rows if r and r[0]]

        # Combobox options
        combo = sensors if lot_cond == "MP" else []

        popup = BMSPopup(root, lot, proc, op, sensors, combo, [], [], [], lot_cond)
        popup.grab_set()

    except Exception as e:
        messagebox.showerror("Error", f"Unexpected error: {e}")

delete_button = tk.Button(root, text="Clear Data", font=("Tahoma", 12, "bold"), padx=10, pady=1, bg="yellow", command=delete_action)
delete_button.place(x=320, y=95)
save_button = tk.Button(root, text="SAVE", font=("Tahoma", 12, "bold"), padx=32, pady=1, bg="orange", command=save_action)
save_button.place(x=320, y=45)

# Camera frame
border_frame = tk.Frame(root, bg='white', width=680, height=510, relief='ridge', bd=2)
border_frame.place(x=530, y=10)
camera_label = tk.Label(border_frame, width=670, height=500, bg='black')
camera_label.place(x=1, y=1)

# Camera detection
combobox_label = tk.Label(root, text="Camera Index:", font=("Arial", 10), bg="#3366cc", fg="white")
combobox_label.place(x=530, y=555)
camera_index_var = tk.StringVar(value="0")
camera_index_combobox = ttk.Combobox(root, textvariable=camera_index_var, values=["0", "1"], state="readonly", width=5)
camera_index_combobox.place(x=630, y=555)

def detect_cameras(max_index=6):
    available = []
    for i in range(max_index + 1):
        cap_test = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if not cap_test or not cap_test.isOpened():
            try:
                cap_test.release()
            except:
                pass
            continue
        ret, frame = cap_test.read()
        if ret and frame is not None:
            available.append(str(i))
        try:
            cap_test.release()
        except:
            pass
    return available

def on_detect_cameras():
    camera_index_combobox.config(values=["Detecting..."])
    root.update()
    available = detect_cameras(max_index=6)
    if not available:
        messagebox.showwarning("Camera Detection", "No cameras detected. Check drivers and connections.")
        camera_index_combobox.config(values=["0", "1"])
    else:
        camera_index_combobox.config(values=available)
        camera_index_var.set(available[0])

on_detect_cameras()

def start_camera_feed(camera_index):
    global cap
    try:
        if cap is not None and cap.isOpened():
            cap.release()
    except Exception:
        pass
    cap = cv2.VideoCapture(int(camera_index), cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(int(camera_index))
        if not cap.isOpened():
            messagebox.showerror("Error", "Unable to open camera index {}.".format(camera_index))
            return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    def update_camera():
        if cap is None or not cap.isOpened():
            return
        ret, frame = cap.read()
        if ret and frame is not None:
            # store last frame in global so Capture Image can save exact shown frame
            global last_camera_frame
            last_camera_frame = frame.copy()
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            label_width = camera_label.winfo_width()
            label_height = camera_label.winfo_height()
            if label_width <= 1 or label_height <= 1:
                label_width, label_height = 300, 220
            h, w = frame.shape[:2]
            scale = min(label_width / w, label_height / h)
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            frame_resized = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)
            img = Image.fromarray(frame_resized)
            imgtk = ImageTk.PhotoImage(image=img)
            camera_label.imgtk = imgtk
            camera_label.configure(image=imgtk)
        camera_label.after(20, update_camera)

    update_camera()

def on_start_camera():
    try:
        camera_index = int(camera_index_var.get())
        start_camera_feed(camera_index)
    except ValueError:
        messagebox.showerror("Error", "Invalid camera index selected.")

# ---------------- Camera capture helper ----------------
def capture_and_save_image():
    """
    Save the currently shown camera frame (last_camera_frame) to pictures_folder.
    Filename: image_YYYYMMDD_HHMMSS.png
    """
    global last_camera_frame
    if 'last_camera_frame' not in globals():
        messagebox.showerror("Error", "No camera frame available to capture. Start camera first.")
        return
    frame = last_camera_frame
    if frame is None:
        messagebox.showerror("Error", "No camera frame available to capture. Start camera first.")
        return

    # ensure pictures folder exists
    os.makedirs(pictures_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_name = f"image_{timestamp}.png"
    save_path_local = os.path.join(pictures_folder, save_name)

    try:
        # frame is BGR since stored copy was from cv2; write directly
        cv2.imwrite(save_path_local, frame)
        # Optionally notify user
        tmp = tk.Toplevel()
        tmp.withdraw()
        tmp.attributes('-topmost', True)
        #messagebox.showinfo("Captured", f"Image saved to {save_path_local}", parent=tmp)
        tmp.destroy()
    except Exception as e:
        messagebox.showerror("Error", "Failed to save captured image: {}".format(e))

# ---------------- Popup / Save logic ----------------
def show_popup(most_recent_file, file_path):
    global fname, lot_number, curr_proc, current_row, current_col, suffix
    if hasattr(show_popup, 'popup') and show_popup.popup.winfo_exists():
        return
    popup = tk.Toplevel(root)
    show_popup.popup = popup
    popup.title("File Detected")
    popup.geometry("500x540")
    popup.attributes('-topmost', True)

    # --- Image Preview ---
    try:
        img = Image.open(file_path)
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.2)
        img = img.resize((450, 338), Image.LANCZOS)
        img_tk = ImageTk.PhotoImage(img)
        image_label = tk.Label(popup, image=img_tk)
        image_label.image = img_tk
        image_label.pack(pady=10)
    except Exception as e:
        tk.Label(popup, text=f"Error loading image: {e}", fg="red").pack(pady=10)

    # --- Detected Filename ---
    detected_name = os.path.basename(most_recent_file) if most_recent_file else os.path.basename(file_path)
    tk.Label(popup, text=f"Detected file: {detected_name}", wraplength=450).pack(pady=4)

    # --- Build Preview Name ---
    if current_row is not None and current_row < len(data_entry):
        sensor_id_preview = data_entry[current_row][0].get().strip()
    else:
        sensor_id_preview = ""

    if suffix:
        suffix_preview = suffix
    else:
        if current_col == 1:
            suffix_preview = "_Top_Molding"
        elif current_col == 2:
            suffix_preview = "_Final_Molding"
        elif current_col == 3:
            suffix_preview = "_Sensor_Image"
        else:
            suffix_preview = ""

    display_sensor = sensor_id_preview if sensor_id_preview else "<<NO_SENSOR_ID>>"
    preview_name = f"{display_sensor}{suffix_preview}.png" if suffix_preview else f"{display_sensor}.png"

    tk.Label(popup, text="Will be saved as:", font=("Arial", 10, "bold")).pack(pady=(8, 0))
    tk.Label(popup, text=preview_name, wraplength=450, fg="blue").pack(pady=(0, 8))

    # --- Buttons Frame ---
    buttons_frame = tk.Frame(popup)
    buttons_frame.pack(pady=6)

    def on_ok():
        nonlocal file_path
        global current_row, current_col, lot_number, curr_proc, suffix

        if not lot_number:
            messagebox.showerror("Error", "Lot number is not set.")
            return
        if current_row is None or current_col is None:
            messagebox.showerror("Error", "No active cell selected to save this image into.")
            return

        sensor_id = data_entry[current_row][0].get().strip()
        if not sensor_id:
            messagebox.showerror("Error", "Sensor ID in the current row is empty. Please scan sensor ID first.")
            return

        # --- Determine Filename ---
        if suffix:
            new_name = f"{sensor_id}{suffix}.png"
        else:
            if current_col == 1:
                new_name = f"{sensor_id}_Top_Molding.png"
            elif current_col == 2:
                new_name = f"{sensor_id}_Final_Molding.png"
            elif current_col == 3:
                new_name = f"{sensor_id}_Sensor_Image.png"
            else:
                new_name = f"{sensor_id}.png"

        dest_path = os.path.join(destination_folder, lot_number, curr_proc or "")
        os.makedirs(dest_path, exist_ok=True)
        img_path = os.path.join(dest_path, new_name)

        try:
            # --- Copy the detected file ---
            shutil.copy2(file_path, img_path)
            print(f"[Info] File saved to: {img_path}")

            # --- Permanently delete original detected file ---
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"[Cleanup] Deleted source file: {file_path}")
            except Exception as e:
                print(f"[Warning] Could not delete file {file_path}: {e}")

            # Continue workflow
            show_success_and_navigate(img_path)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy file: {e}")

        popup.destroy()

    def on_retake():
        popup.destroy()
        # --- Permanently delete original detected file ---
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"[Cleanup] Deleted source file: {file_path}")
        except Exception as e:
            print(f"[Warning] Could not delete file {file_path}: {e}")
            
        # If user retakes, revert states for the relevant fields (optional)
        if current_row is not None and current_col == 1:
            data_entry[current_row][0].config(state="normal")
            data_entry[current_row][0].delete(0, tk.END)
            data_entry[current_row][0].focus_set()
            data_entry[current_row][1].config(state="readonly")

    # --- Buttons ---
    tk.Button(buttons_frame, text="OK", command=on_ok, bg="green", fg="white",
              padx=20, pady=5).grid(row=0, column=0, padx=10)
    tk.Button(buttons_frame, text="RETAKE", command=on_retake, bg="red", fg="white",
              padx=20, pady=5).grid(row=0, column=1, padx=10)

def show_success_and_navigate(img_path):
    global current_col, current_row, curr_proc
    tmp = tk.Toplevel()
    tmp.withdraw()
    tmp.attributes('-topmost', True)
    messagebox.showinfo("Success", "File moved to {}".format(img_path), parent=tmp)
    tmp.destroy()

    # mark current measurement cell done
    if current_row is not None and current_col is not None:
        try:
            data_entry[current_row][current_col].delete(0, tk.END)
            data_entry[current_row][current_col].insert(0, "Captured")
        except Exception:
            pass

    # If we just captured the Sensor Image column (col == 3), and we're on the last expected sensor,
    # check whether ALL expected sensors have all three capture columns == "Captured".
    try:
        # Only proceed if the captured column is the Sensor Image column
        if current_col == 3:
            # Use sensor_count (number of expected sensors) to determine last index
            if sensor_count and sensor_count > 0 and current_row == sensor_count - 1:
                all_captured = True
                for r in range(sensor_count):
                    # Check Top Molding (col 1), Final Molding (col 2), Sensor Image (col 3)
                    for c in (1, 2, 3):
                        try:
                            val = data_entry[r][c].get().strip()
                        except Exception:
                            val = ""
                        if val.lower() != "captured":
                            all_captured = False
                            break
                    if not all_captured:
                        break

                if all_captured:
                    # Show popup notifying all sensors for the lot are captured
                    try:
                        tmp2 = tk.Toplevel()
                        tmp2.withdraw()
                        tmp2.attributes('-topmost', True)
                        lot_display = entries["Lot Number:"].get().strip() or "<Unknown Lot>"
                        messagebox.showinfo("All Captured", f"All Sensor ID on Lot Number {lot_display} was successfully Captured", parent=tmp2)
                        tmp2.destroy()
                    except Exception:
                        # fallback: non-parented messagebox
                        messagebox.showinfo("All Captured", f"All Sensor ID on Lot Number {lot_display} was successfully Captured")
    except Exception:
        # don't let this block navigation on any error
        pass

    # move to next column in same row
    if current_row is not None and current_col is not None:
        next_col = current_col + 1
        next_row = current_row
        if next_col >= 4:
            # after finishing the row, move to next row's sensor ID (if any)
            next_row = current_row + 1
            next_col = 0

        if next_row < len(data_entry):
            if next_col == 0:
                # focus next sensor id for scanning if it's enabled
                if data_entry[next_row][0]['state'] == 'normal':
                    data_entry[next_row][0].focus_set()
                    current_row, current_col = next_row, 0
            else:
                # focus next measurement col if enabled
                if data_entry[next_row][next_col]['state'] != 'readonly':
                    data_entry[next_row][next_col].focus_set()
                    current_row, current_col = next_row, next_col

# ---------------- Focus handling helper ----------------
def on_focus_in_cell(r, c):
    global current_row, current_col, suffix
    current_row, current_col = r, c
    # set suffix for naming
    if c == 1:
        suffix = "_Top_Molding"
    elif c == 2:
        suffix = "_Final_Molding"
    elif c == 3:
        suffix = "_Sensor_Image"
    else:
        suffix = None

    # choose which folder to monitor depending on column
    if c in (1, 2, 3):
        # If focusing Sensor Image (col 3) monitor pictures_folder
        folder_to_monitor = pictures_folder if c == 3 else microscope_folder
        # only start monitor if folder exists (create Pictures if needed)
        os.makedirs(folder_to_monitor, exist_ok=True)
        start_monitoring(folder_to_monitor)
    else:
        stop_monitoring()

# Table headers
headers = ["No.", "Sensor ID", "Top Molding", "Final Molding", "Sensor Image"]
header_positions = {"No.": (12, 140), "Sensor ID": (75, 140), "Top Molding": (190, 140),
                    "Final Molding": (310, 140), "Sensor Image": (425, 140)}
for h in headers:
    label = tk.Label(root, text=h, font=("Arial", 8, "bold"), bg="lightblue", relief="ridge")
    label.place(x=header_positions[h][0], y=header_positions[h][1])

# Table rows
data_entry = []
for row in range(20):
    row_entries = []
    number_label = tk.Label(root, text=str(row + 1), width=3, bg="lightblue", relief="ridge")
    number_label.place(x=10, y=165 + row * 23)
    for col in range(4):
        e = tk.Entry(root, width=18, justify='center')
        if col == 0:
            e.place(x=45 + col * 90, y=165 + row * 23)
            e.config(state="readonly")  # default locked
            e.bind("<Return>", on_sensor_entry_return)
        else:
            e.place(x=170 + (col - 1) * 120, y=165 + row * 23)
            e.config(state="readonly")
        # bind focus to set current row/col and suffix
        e.bind("<FocusIn>", lambda ev, r=row, c=col: on_focus_in_cell(r, c))
        row_entries.append(e)
    data_entry.append(row_entries)

# ---------------- Camera control buttons ----------------
capture_button = tk.Button(root, text="Capture Image", command=capture_and_save_image, font=("Arial", 12), bg="#32CD32", fg="black", width=15)
capture_button.place(x=840, y=555)
start_button = tk.Button(root, text="Start Camera", command=on_start_camera, font=("Arial", 12), bg="yellow", fg="black", width=15)
start_button.place(x=540, y=580)


# ---------------- Closing / cleanup ----------------
def on_closing():
    global cap, datetime_after_id, observer
    try:
        stop_monitoring()
    except Exception:
        pass
    try:
        if datetime_after_id is not None:
            root.after_cancel(datetime_after_id)
    except Exception:
        pass
    try:
        if cap is not None and cap.isOpened():
            cap.release()
    except Exception:
        pass
    # stop observer if running
    try:
        if observer:
            observer.stop()
            observer.join(timeout=1)
    except Exception:
        pass
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

# ---------------- Startup ----------------
delete_action()
root.mainloop()