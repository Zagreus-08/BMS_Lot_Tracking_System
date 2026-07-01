import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import time
import os
import shutil
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image, ImageTk, ImageEnhance
import threading
import json
from datetime import datetime

# Define the paths to the databases
db_path_tracking = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"
db_path_masterlist = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"
source_folder = r'C:\Users\a493353\Documents\Digital Microscope\Default\Picture'
destination_folder = r"\\phlsvr08\BMS Data\Assembly Data\Assembly Image Capturing"
fname = None
sens_id = None
lot_number = None
curr_proc = None
current_col = None
current_row = None
suffix = None

# Define the absolute path to your config.json
config_file_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\process_flow.json" # Example for Windows

try:
    with open(config_file_path, 'r') as f:
        config = json.load(f)
    process_flow = config["process_flow"]
    process_column_mapping = config["process_column_mapping"]
except FileNotFoundError:
    messagebox.showerror("Configuration Error", f"Config file not found at: {config_file_path}")
    exit()
except json.JSONDecodeError:
    messagebox.showerror("Configuration Error", "Error decoding process_flow.json. Please check its format.")
    exit()

# Create the main application window
root = tk.Tk()
root.title("QA Inspection")
root.geometry("480x650")  # Adjusted width to fit the new column
root.configure(bg="lightblue")
root.resizable(False, False)
root.attributes('-topmost', True)  # Make the main window always on top

# Function to enable or disable the "Top Image" column based on the current process
def toggle_top_image_column():
    global curr_proc
    for row in data_entry:
        # Enable both Bottom and Top Image columns for both processes
        row[1].config(state="normal")  # Enable "Bottom Image"
        row[1].bind("<FocusIn>", on_focus_in)
        
        row[2].config(state="normal")  # Enable "Top Image"
        row[2].bind("<FocusIn>", on_focus_in)

# --- Helper Function: Get Lot Condition (added before fetch_lot_info) ---
def get_lot_condition(lot_number):
    """
    Return the lot condition string (e.g., "MP" or "EVAL").
    Defaults to "MP" if not found or on DB error.
    """
    default = "MP"
    try:
        conn = sqlite3.connect(db_path_masterlist)
        cur = conn.cursor()
        # Try a few likely column names for the Condition column
        for colname in ('"Condition"', 'Condition', 'condition', 'LotCondition', 'lot_condition'):
            try:
                cur.execute(f"SELECT {colname} FROM lot_masterlist WHERE lot_number = ? LIMIT 1", (lot_number,))
                res = cur.fetchone()
                if res and res[0] is not None:
                    conn.close()
                    return str(res[0]).strip()
            except sqlite3.OperationalError:
                # Column not present, try next
                continue
        conn.close()
    except sqlite3.Error:
        pass
    return default

# Update the fetch_lot_info function to populate sensor IDs automatically
def fetch_lot_info(event=None):
    global lot_number, curr_proc, sensor_ids_no_defects, lot_condition

    lot_number = entries["Lot Number:"].get().strip()
    curr_proc = entries["Current Process:"].get().strip()

    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number.")
        return

    try:
        conn = sqlite3.connect(db_path_tracking)
        cursor = conn.cursor()

        cursor.execute("SELECT current_process FROM lot_tracking WHERE lot_number = ?", (lot_number,))
        result = cursor.fetchone()

        if not result:
            messagebox.showwarning("Warning", "Lot Number not found in the database.")
            delete_action()
            conn.close()
            return

        current_process = result[0]
        entries["Current Process:"].config(state="normal")
        entries["Current Process:"].delete(0, tk.END)
        entries["Current Process:"].insert(0, current_process)
        entries["Current Process:"].config(state="readonly")

        # --- Get lot condition and enforce process rules ---
        lot_condition = get_lot_condition(lot_number)

        if str(lot_condition).upper() == "MP":
            if current_process not in ["QA Inspection 1", "QA Inspection 2"]:
                messagebox.showerror(
                    "Error",
                    "The lot number inputted is not for QA Inspection."
                )
                delete_action()
                conn.close()
                return
        # If "EVAL", skip the validation check entirely

        # --- Set destination folder based on process ---
        global destination_folder
        if current_process == "QA Inspection 1":
            destination_folder = r"\\phlsvr08\BMS Data\Assembly Data\Assembly Image Capturing"
        elif current_process == "QA Inspection 2":
            destination_folder = r"\\phlsvr08\BMS Data\Assembly Data\Solder Image Capturing"
        else:
            destination_folder = r"\\phlsvr08\BMS Data\Assembly Data"

        # Enable or disable "Top Image" column dynamically
        toggle_top_image_column()

        # --- Fetch sensor IDs and filter those with completed values ---
        conn_masterlist = sqlite3.connect(db_path_masterlist)
        cursor_masterlist = conn_masterlist.cursor()

        process_to_columns = {
            "QA Inspection 1": ["Assy_capturing_bottom", "Assy_capturing_top"],
            "QA Inspection 2": ["Soldering_Image_capturing"],
        }
        columns = process_to_columns.get(current_process, [])

        if columns:
            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
            sensor_ids = [row[0] for row in cursor.fetchall()]

            sensor_ids_with_values = []
            for sid in sensor_ids:
                try:
                    cursor_masterlist.execute(f"SELECT {', '.join(columns)} FROM lot_masterlist WHERE sensor_id=?", (sid,))
                    result = cursor_masterlist.fetchone()
                    if result and all(value is not None for value in result):
                        sensor_ids_with_values.append(sid)
                except sqlite3.OperationalError:
                    continue

            if sensor_ids_with_values:
                messagebox.showinfo(
                    "Information",
                    f"The following Sensor IDs already have values in '{current_process}': {', '.join(sensor_ids_with_values)}"
                )
                conn_masterlist.close()
                conn.close()
                return

        conn_masterlist.close()

        # --- Get sensors without previous defects ---
        try:
            current_process_index = process_flow.index(current_process)
        except ValueError:
            current_process_index = -1

        previous_defect_columns = []
        if current_process_index > 0:
            for process in process_flow[:current_process_index]:
                try:
                    if process in process_column_mapping:
                        previous_defect_columns.append(process_column_mapping[process][2])
                except Exception:
                    continue

        # Fetch sensor IDs without previous defects
        sensor_ids_to_display = []
        if previous_defect_columns:
            defect_conditions = " AND ".join(f"({col} IS NULL OR {col} = '')" for col in previous_defect_columns)
            query = f"""
                SELECT sensor_id 
                FROM lot_tracking 
                WHERE lot_number = ? AND {defect_conditions}
                ORDER BY sensor_id
            """
            cursor.execute(query, (lot_number,))
            sensor_ids_to_display = [row[0] for row in cursor.fetchall()]
            sensor_ids_no_defects = sensor_ids_to_display
        else:
            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ? ORDER BY sensor_id", (lot_number,))
            sensor_ids_to_display = [row[0] for row in cursor.fetchall()]
            sensor_ids_no_defects = sensor_ids_to_display

        conn.close()

        # Clear existing data in the table
        for row in range(20):
            data_entry[row][0].config(state="normal")
            data_entry[row][0].delete(0, tk.END)
            data_entry[row][1].delete(0, tk.END)
            data_entry[row][2].delete(0, tk.END)

        # Populate sensor IDs automatically
        for row, sensor_id in enumerate(sensor_ids_to_display[:20]):  # Limit to 20 rows
            data_entry[row][0].insert(0, sensor_id)
            data_entry[row][0].config(state="readonly")
            # Enable image capture columns
            data_entry[row][1].config(state="normal")
            if current_process == "QA Inspection 1":
                data_entry[row][2].config(state="normal")

        # Disable empty rows
        for row in range(len(sensor_ids_to_display), 20):
            data_entry[row][0].config(state="readonly")
            data_entry[row][1].config(state="readonly")
            data_entry[row][2].config(state="readonly")

        # Set focus to the first image capture cell
        if sensor_ids_to_display:
            data_entry[0][1].focus_set()
            get_fname(data_entry[0][1])

        # Start file monitoring only if source folder exists
        if os.path.exists(source_folder):
            threading.Thread(target=monitor_folder, args=(source_folder,), daemon=True).start()
        else:
            messagebox.showwarning(
                "Folder Not Found",
                f"Image source folder not found:\n{source_folder}\n\n"
                f"Please ensure the Digital Microscope software is installed.\n\n"
                f"You can still use the program, but automatic image detection will not work."
            )

    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")
    except Exception as e:
        messagebox.showerror("Error", f"Unexpected error: {e}")
        
def find_row_col(focused_entry):
    """
    Finds the row and column indices of the given focused entry within the data_entry list.
    Args:
        focused_entry: The currently focused widget (e.g., an Entry widget).
    Returns:
        A tuple containing the row and column indices, or (None, None) if not found.
    """
    for row_idx, row in enumerate(data_entry):
        for col_idx, entry in enumerate(row):
            if entry == focused_entry:
                return row_idx, col_idx
    return None, None

def on_focus_in(event):
    """
    Called when any data_entry widget receives focus. Use event.widget
    so get_fname has the exact widget that gained focus.
    """
    try:
        get_fname(event.widget)
    except Exception as e:
        print(f"[on_focus_in] Error in get_fname: {e}")


def get_fname(focused_widget):
    """
    Update globals current_row, current_col, fname, sens_id, curr_proc
    based strictly on the provided widget (no root.focus_get()).
    """
    global fname, sens_id, curr_proc, current_col, current_row, suffix

    # Determine row and column for the given widget
    row_col = find_row_col(focused_widget)
    if row_col == (None, None):
        # Focused widget not found in data_entry
        current_row, current_col = None, None
        fname = None
        return

    current_row, current_col = row_col
    # Debug print
    # print(f"[get_fname] Focused entry is in row: {current_row}, column: {current_col}")

    # Extract Sensor ID from that row
    try:
        sensor_id = data_entry[current_row][0].get().strip()
    except Exception:
        sensor_id = ""

    sens_id = sensor_id
    curr_proc = entries["Current Process:"].get().strip()

    # Column mapping: 1 => Bottom, 2 => Top (as used in your UI)
    if current_col == 1:
        suffix = "Bottom"
    else:
        suffix = "Top"

    # Compose fname (guard against empty sensor_id)
    if sensor_id:
        fname = f"{sensor_id}_{suffix}.png"
    else:
        fname = f"unknown_{suffix}.png"

    # Debug print
    # print(f"[get_fname] set fname = '{fname}'")

# Function to update the date and time entry
def update_datetime():
    current_time = time.strftime("%Y-%m-%d %I:%M:%S %p")
    entries["Date and Time:"].config(state="normal")
    entries["Date and Time:"].delete(0, tk.END)
    entries["Date and Time:"].insert(0, current_time)
    entries["Date and Time:"].config(state="readonly")
    root.after(1000, update_datetime)  # Update every second

# Title Label
title_label = tk.Label(root, text="QA Inspection", font=("BiomeW04-Bold", 20, "bold"), bg="lightblue")
title_label.place(x=10, y=0)

# Labels and Entry fields for Lot Number, Operator, Current Process, Connection, Date and Time
labels = ["Lot Number:", "Current Process:", "Date and Time:", "Operator:"]
entries = {}

# Individually adjust the position of each label and entry field
label_positions = {
    "Lot Number:": (10, 50),
    "Current Process:": (10, 75),
    "Date and Time:": (10, 100),
    "Operator:": (10, 125)
}

entry_positions = {
    "Lot Number:": (120, 50),
    "Current Process:": (120, 75),
    "Date and Time:": (120, 100),
    "Operator:": (120, 125)
}

for label_text in labels:
    label = tk.Label(root, text=label_text, font=("Arial", 10), bg="lightblue")
    label.place(x=label_positions[label_text][0], y=label_positions[label_text][1])
    entry = tk.Entry(root, width=30, justify='center')
    entry.place(x=entry_positions[label_text][0], y=entry_positions[label_text][1])
    entries[label_text] = entry

# Make the Date and Time entry non-editable and start the live update
entries["Date and Time:"].config(state="readonly")
update_datetime()

# Bind Enter key to the fetch_lot_info function for the Lot Number entry
entries["Lot Number:"].bind("<Return>", fetch_lot_info)

# Buttons for Delete and Save
def delete_action():
    for entry in entries.values():
        entry.config(state="normal")
        entry.delete(0, tk.END)
        entry.config(state="readonly" if entry == entries["Current Process:"] else "normal")
    entries["Current Process:"].config(state="normal")
    entries["Current Process:"].delete(0, tk.END)
    for row in range(20):
        for col in range(3):
            data_entry[row][col].config(state="normal")  # Temporarily make all entries editable to clear
            data_entry[row][col].config(bg="white")
            data_entry[row][col].delete(0, tk.END)
            data_entry[row][col].config(state="readonly")  # Set all columns to readonly after clearing

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

        # --- Title ---
        tk.Label(self, text="BMS Lot Tracking System", font=("BiomeW04-Bold", 20, "bold"),
                 bg='#3a6ba8', fg="orange").place(x=20, y=0)

        # --- Lot Info ---
        tk.Label(self, text="Lot Number:", bg='#3a6ba8', fg="white").place(x=5, y=45)
        self.lot_number_entry = tk.Entry(self, width=31)
        self.lot_number_entry.place(x=105, y=45)
        self.lot_number_entry.insert(0, lot_number)
        self.lot_number_entry.config(state="readonly")

        tk.Label(self, text="Current Process:", bg='#3a6ba8', fg="white").place(x=5, y=75)
        self.current_process_entry = tk.Entry(self, width=31)
        self.current_process_entry.place(x=105, y=75)
        self.current_process_entry.insert(0, current_process)
        self.current_process_entry.config(state="readonly")

        # --- Sensor ID Combobox ---
        tk.Label(self, text="Sensor ID:", bg='#3a6ba8', fg="white").place(x=5, y=105)
        if self.lot_condition == "EVAL":
            # EVAL lots: do not force adding defects
            self.sensor_id_combobox = ttk.Combobox(self, values=[], width=28, state="readonly")
        else:
            self.sensor_id_combobox = ttk.Combobox(self, values=combobox_candidates, width=28)
            if combobox_candidates:
                self.sensor_id_combobox.set(combobox_candidates[0])
        self.sensor_id_combobox.place(x=105, y=105)

        # --- Rest of UI identical ---
        tk.Label(self, text="Defect:", bg='#3a6ba8', fg="white").place(x=5, y=135)
        self.defect_entry = tk.Entry(self, width=31)
        self.defect_entry.place(x=105, y=135)

        tk.Label(self, text="Remarks:", bg='#3a6ba8', fg="white").place(x=5, y=165)
        self.remarks_entry = tk.Entry(self, width=31)
        self.remarks_entry.place(x=105, y=165)

        # Quantity In/Out, Date, Operator
        tk.Label(self, text="Quantity IN:", bg='#3a6ba8', fg="white").place(x=320, y=45)
        self.quantity_in_entry = tk.Entry(self, width=15)
        self.quantity_in_entry.place(x=410, y=45)

        tk.Label(self, text="Quantity OUT:", bg='#3a6ba8', fg="white").place(x=320, y=75)
        self.quantity_out_entry = tk.Entry(self, width=15)
        self.quantity_out_entry.place(x=410, y=75)

        tk.Label(self, text="Date:", bg='#3a6ba8', fg="white").place(x=320, y=105)
        self.date_time_label = tk.Label(self, text="", bg='white', width=19)
        self.date_time_label.place(x=410, y=105)

        tk.Label(self, text="Operator:", bg='#3a6ba8', fg="white").place(x=320, y=135)
        self.operator_entry = tk.Entry(self, width=22)
        self.operator_entry.place(x=410, y=135)
        self.operator_entry.insert(0, self.operator)

        # Buttons
        tk.Button(self, text="Export Defects / Remarks", command=self.export_data, bg="green", fg="white",
                  font=("Tahoma", 10, "bold"), padx=20, pady=1, relief='raised', borderwidth=3).place(x=20, y=200)

        tk.Button(self, text="CLEAR", command=self.clear_fields, bg="yellow",
                  font=("Tahoma", 16, "bold"), padx=10, pady=1, relief='raised', borderwidth=3).place(x=320, y=185)

        tk.Button(self, text="SAVE", command=self.save_data_and_advance, bg="green", fg="white",
                  font=("Tahoma", 16, "bold"), padx=10, pady=1, relief='raised', borderwidth=3).place(x=460, y=185)

        # Table
        self.columns = ("Sensor ID", "Defects", "Remarks")
        self.table = ttk.Treeview(self, columns=self.columns, show="headings", height=7)
        for col in self.columns:
            self.table.heading(col, text=col)
        self.table.place(x=5, y=280)

        # -------------------------------------------------------
        # Compute Quantity IN
        # -------------------------------------------------------
        total_sensors = len(self.sensor_list)
        prev_defect_count = 0

        if self.lot_condition == "MP":
            try:
                idx = process_flow.index(self.current_process)
            except ValueError:
                idx = -1

            previous_defect_columns = []
            if idx > 0:
                for proc in process_flow[:idx]:
                    try:
                        cols = process_column_mapping.get(proc)
                        if cols and len(cols) > 2:
                            previous_defect_columns.append(cols[2])
                    except Exception:
                        continue

            if previous_defect_columns:
                conditions = " OR ".join(f"({col} IS NOT NULL AND {col} != '')" for col in previous_defect_columns)
                query = f"SELECT COUNT(DISTINCT sensor_id) FROM lot_tracking WHERE lot_number = ? AND ({conditions})"
                try:
                    conn = sqlite3.connect(db_path_tracking)
                    cur = conn.cursor()
                    cur.execute(query, (self.lot_number,))
                    row = cur.fetchone()
                    prev_defect_count = int(row[0]) if row and row[0] else 0
                    conn.close()
                except Exception as e:
                    print(f"[BMSPopup] Error counting previous defects: {e}")
                    try:
                        conn.close()
                    except:
                        pass

            quantity_in_value = max(0, total_sensors - prev_defect_count)

        else:
            # EVAL
            quantity_in_value = total_sensors

        self.quantity_in_entry.insert(0, str(quantity_in_value))
        self._quantity_in_base = quantity_in_value

        # -------------------------------------------------------
        # Compute Quantity OUT (REVISED)
        # -------------------------------------------------------
        quantity_out_value = 0
        try:
            if self.lot_condition == "EVAL":
                # For evaluation lots, treat all sensors as counted out
                quantity_out_value = total_sensors
            else:
                # Build a map of Sensor ID -> (bottom_val, top_val) from the UI,
                # but only for sensor IDs that belong to this lot (self.sensor_list)
                ui_map = {}
                lot_sensors_set = set(self.sensor_list or [])

                for r in range(len(data_entry)):
                    try:
                        sid = data_entry[r][0].get().strip()
                        if not sid:
                            continue
                        # Only consider UI rows whose sensor ID belongs to the lot
                        if sid not in lot_sensors_set:
                            continue
                        bottom_val = ""
                        top_val = ""
                        try:
                            bottom_val = data_entry[r][1].get().strip()
                        except Exception:
                            bottom_val = ""
                        if len(data_entry[r]) > 2:
                            try:
                                top_val = data_entry[r][2].get().strip()
                            except Exception:
                                top_val = ""
                        ui_map[sid] = (bottom_val, top_val)
                    except Exception:
                        continue

                # Now count sensors that are present in the UI and have the required "Done Capturing" status
                if self.current_process == "QA Inspection 2":
                    # For QA Inspection 2, only Bottom needs to be done
                    for sid, (bottom_val, top_val) in ui_map.items():
                        if str(bottom_val).strip().lower() == "done capturing":
                            quantity_out_value += 1

                elif self.current_process == "QA Inspection 1":
                    # For QA Inspection 1, both Bottom and Top must be done
                    for sid, (bottom_val, top_val) in ui_map.items():
                        if (str(bottom_val).strip().lower() == "done capturing" and
                                str(top_val).strip().lower() == "done capturing"):
                            quantity_out_value += 1

                else:
                    # For any other process, default: count nothing (or you can implement other rules)
                    quantity_out_value = 0

        except Exception as e:
            print(f"[BMSPopup] Error computing Quantity OUT: {e}")
            quantity_out_value = 0

        self.quantity_out_entry.insert(0, str(quantity_out_value))

        # -------------------------------------------------------
        self.update_time()

    def update_time(self):
        now = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        self.date_time_label.config(text=now)
        self.after(1000, self.update_time)

    def clear_fields(self):
        self.defect_entry.delete(0, tk.END)
        self.remarks_entry.delete(0, tk.END)

    def delete_selected_row(self):
        selected_item = self.table.selection()
        if selected_item:
            self.table.delete(selected_item)
            self.update_quantity_out()
        else:
            messagebox.showwarning("Selection Error", "Please select a row to delete.")

    def export_data(self):
            sensor_id = self.sensor_id_combobox.get().strip()
            defect = self.defect_entry.get().strip()
            remarks = self.remarks_entry.get().strip()
        
            # Require a defect description before exporting
            if not defect:
                if sensor_id:
                    messagebox.showwarning("Input Error", f"Please input defects for Sensor ID: {sensor_id}")
                else:
                    messagebox.showwarning("Input Error", "Please input defects.")
                return
        
            # Check if Sensor ID is already in the table
            existing_ids = [self.table.item(row)["values"][0] for row in self.table.get_children()]
            if sensor_id in existing_ids:
                messagebox.showwarning("Input Error", "Sensor ID already exists in the table.")
            elif sensor_id:
                self.table.insert('', 'end', values=(sensor_id, defect, remarks))
                self.update_quantity_out()
                self.clear_fields()
            else:
                messagebox.showwarning("Input Error", "Please select Sensor ID.")
            
    def update_quantity_out(self):
            """
            Recalculate Quantity OUT:
            Quantity IN (base, already excluding previous-process defects) minus
            number of defects entered in this popup.
            """
            try:
                base_in = int(self._quantity_in_base)
            except Exception:
                # fallback to reading the entry
                try:
                    base_in = int(self.quantity_in_entry.get())
                except Exception:
                    base_in = 0
    
            # Count rows in table with a non-empty Defects cell (current station defects)
            current_station_defect_count = 0
            for row in self.table.get_children():
                vals = self.table.item(row)["values"]
                if len(vals) > 1 and str(vals[1]).strip():
                    current_station_defect_count += 1
    
            quantity_out = max(0, base_in - current_station_defect_count)
            self.quantity_out_entry.delete(0, tk.END)
            self.quantity_out_entry.insert(0, str(quantity_out))
        
    def save_data_and_advance(self):
        # Ensure operator is provided
        if not self.operator_entry.get():
            messagebox.showwarning("Input Error", "Please enter Operator.")
            return

        lot_number = self.lot_number
        current_process = self.current_process
        operator = self.operator_entry.get().strip()
        proc_datetime = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")

        # Get process column mapping safely
        try:
            columns = process_column_mapping.get(current_process, [])
        except Exception:
            columns = []

        # --- Enforce configuration for MP lots only ---
        if self.lot_condition == "MP" and (not columns or len(columns) < 6):
            messagebox.showerror("Configuration Error",
                                 f"Process mapping for '{current_process}' is missing or invalid.")
            return

        quantity_in = self.quantity_in_entry.get().strip()
        quantity_out = self.quantity_out_entry.get().strip()

        try:
            # --- 1) Update lot_masterlist with image capture results ---
            conn_master = sqlite3.connect(db_path_masterlist)
            cursor_master = conn_master.cursor()

            for r in range(len(data_entry)):
                sensor_id = data_entry[r][0].get().strip()
                if not sensor_id:
                    continue

                bottom_val = ""
                top_val = ""
                try:
                    bottom_val = data_entry[r][1].get().strip()
                    if len(data_entry[r]) > 2:
                        top_val = data_entry[r][2].get().strip()
                except Exception:
                    pass

                if current_process == "QA Inspection 1":
                    try:
                        cursor_master.execute("""
                            UPDATE lot_masterlist
                            SET QA_Inspection1_bottom = ?, QA_Inspection1_top = ?
                            WHERE sensor_id = ?
                        """, (bottom_val, top_val, sensor_id))
                    except sqlite3.OperationalError:
                        pass
                elif current_process == "QA Inspection 2":
                    try:
                        cursor_master.execute("""
                            UPDATE lot_masterlist
                            SET QA_Inspection2_bottom = ?
                            WHERE sensor_id = ?
                        """, (bottom_val, sensor_id))
                    except sqlite3.OperationalError:
                        pass

            conn_master.commit()
            conn_master.close()

            # --- 2) Update lot_tracking for defect/remarks data ---
            conn = sqlite3.connect(db_path_tracking)
            cursor = conn.cursor()

            # Collect all sensors currently in popup table
            sensor_ids_in_table = []
            sensor_ids_with_defects = []
            for row in self.table.get_children():
                sid, defect, remarks = self.table.item(row)["values"]
                sensor_ids_in_table.append(sid)
                if str(defect).strip():
                    sensor_ids_with_defects.append(sid)

            # If MP, update defect and remarks normally
            if self.lot_condition == "MP" and columns and len(columns) >= 6:
                # Update defect rows
                for row in self.table.get_children():
                    sid, defect, remarks = self.table.item(row)["values"]
                    cursor.execute(f"""
                        UPDATE lot_tracking
                        SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, {columns[3]}=?,
                            {columns[4]}=?, {columns[5]}=?
                        WHERE lot_number=? AND sensor_id=?
                    """, (quantity_in, quantity_out, defect, remarks,
                          proc_datetime, operator, lot_number, sid))

                # Update remaining sensors (no defect)
                cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot_number,))
                all_sensors_for_lot = [r[0] for r in cursor.fetchall()]
                remaining_sensors = set(all_sensors_for_lot) - set(sensor_ids_in_table)
                for sid in remaining_sensors:
                    cursor.execute(f"""
                        UPDATE lot_tracking
                        SET {columns[0]}=?, {columns[1]}=?, {columns[2]}='', {columns[3]}='',
                            {columns[4]}=?, {columns[5]}=?
                        WHERE lot_number=? AND sensor_id=?
                    """, (quantity_in, quantity_out, proc_datetime, operator, lot_number, sid))

            # If EVAL lot: skip defect enforcement (just update time/operator and quantities)
            elif self.lot_condition == "EVAL":
                try:
                    cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot_number,))
                    sensors = [r[0] for r in cursor.fetchall()]
                    for sid in sensors:
                        try:
                            cursor.execute(f"""
                                UPDATE lot_tracking
                                SET current_process=?, operator=?, last_update=?
                                WHERE lot_number=? AND sensor_id=?
                            """, (current_process, operator, proc_datetime, lot_number, sid))
                        except sqlite3.OperationalError:
                            # some columns may not exist
                            pass
                except sqlite3.Error as e:
                    print(f"[EVAL update warning] {e}")

            # --- 3) Optional: remove defective sensors from file list (if path stored) ---
            try:
                cursor.execute("SELECT database_path FROM lot_tracking WHERE lot_number=? LIMIT 1", (lot_number,))
                res = cursor.fetchone()
                if res and res[0]:
                    text_file_path = res[0]
                    if os.path.exists(text_file_path):
                        with open(text_file_path, 'r') as f:
                            lines = f.readlines()
                        with open(text_file_path, 'w') as f:
                            for line in lines:
                                if line.strip() not in sensor_ids_with_defects:
                                    f.write(line)
            except sqlite3.Error:
                pass
            except Exception as e:
                print(f"[File cleanup] {e}")

            # --- 4) Advance current_process (for MP only) ---
            if self.lot_condition == "MP":
                try:
                    idx = process_flow.index(current_process)
                    next_process = process_flow[idx + 1]
                except Exception:
                    next_process = current_process

                cursor.execute("""
                    UPDATE lot_tracking
                    SET current_process=?
                    WHERE lot_number=?
                """, (next_process, lot_number))

                message = f"Data saved successfully.\nNext process set to: {next_process}"
            else:
                # For EVAL lots, we don't advance automatically
                message = "Data saved successfully (EVAL lot - process not advanced)."

            conn.commit()
            conn.close()

            messagebox.showinfo("Save", message)
            entries["Lot Number:"].focus_set()
            self.destroy()
            delete_action()

        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"An error occurred: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Unexpected error: {e}")

def save_action():
    try:
        # 1) Basic validation
        if not entries["Operator:"].get().strip():
            messagebox.showerror("Error", "Operator field must be filled.")
            return

        lot_number = entries["Lot Number:"].get().strip()
        current_process = entries["Current Process:"].get().strip()
        operator = entries["Operator:"].get().strip()

        if not lot_number:
            messagebox.showwarning("Warning", "Please enter a Lot Number.")
            return
        if not current_process:
            messagebox.showwarning("Warning", "Current Process is not set.")
            return

        # 2) Build list of sensor IDs presently in the main UI (Sensor ID column)
        sensor_list_local = []
        for row_idx in range(len(data_entry)):
            try:
                sid = data_entry[row_idx][0].get().strip()
            except Exception:
                sid = ""
            if sid:
                sensor_list_local.append(sid)

        # 3) Read all sensors for this lot from the tracking DB
        all_sensors_for_lot = []
        conn = None
        try:
            conn = sqlite3.connect(db_path_tracking)
            cursor = conn.cursor()
            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
            all_sensors_for_lot = [r[0] for r in cursor.fetchall() if r and r[0]]
        except sqlite3.Error as db_e:
            messagebox.showerror("Database Error", f"Failed to read lot sensor list: {db_e}")
            try:
                if conn:
                    conn.close()
            except:
                pass
            return
        finally:
            try:
                if conn:
                    conn.close()
            except:
                pass

        if not all_sensors_for_lot:
            messagebox.showwarning("Warning", f"No sensor IDs found for Lot Number: {lot_number}")
            return

        # 4) Build list of sensors that are NOT yet "Done Capturing" in Bottom or Top
        sensors_not_done = []
        for sid in all_sensors_for_lot:
            # find the UI row (if any) that contains this sensor id
            found_row = None
            for r in range(len(data_entry)):
                try:
                    if data_entry[r][0].get().strip() == sid:
                        found_row = r
                        break
                except Exception:
                    continue

            done = False
            if found_row is not None:
                # check bottom and top cells (guard against missing columns)
                try:
                    bottom_val = data_entry[found_row][1].get().strip()
                except Exception:
                    bottom_val = ""
                try:
                    top_val = data_entry[found_row][2].get().strip() if len(data_entry[found_row]) > 2 else ""
                except Exception:
                    top_val = ""

                # If either bottom or top has Done Capturing (case-insensitive), consider done
                if bottom_val.lower() == "done capturing" or top_val.lower() == "done capturing":
                    done = True

            # If not marked done (or no UI row found), include it
            if not done:
                sensors_not_done.append(sid)

        # 5) Filter out sensors that already have previous-process defects
        # Determine previous defect columns based on process_flow and process_column_mapping
        try:
            proc_index = process_flow.index(current_process)
        except ValueError:
            proc_index = -1

        previous_defect_columns = []
        if proc_index > 0:
            for proc in process_flow[:proc_index]:
                cols = process_column_mapping.get(proc)
                if cols and len(cols) > 2:
                    previous_defect_columns.append(cols[2])

        combobox_candidates = sorted(sensors_not_done)

        if previous_defect_columns and combobox_candidates:
            conn = None
            try:
                conn = sqlite3.connect(db_path_tracking)
                cursor = conn.cursor()
                placeholders = ",".join("?" for _ in combobox_candidates)
                columns_sql = ", ".join(previous_defect_columns)
                query = f"""
                    SELECT sensor_id, {columns_sql}
                    FROM lot_tracking
                    WHERE lot_number = ? AND sensor_id IN ({placeholders})
                """
                params = [lot_number] + combobox_candidates
                cursor.execute(query, params)
                rows = cursor.fetchall()

                sensors_with_prev_defects = set()
                for row in rows:
                    if not row:
                        continue
                # Remove sensors that have previous-process defects
                combobox_candidates = [sid for sid in combobox_candidates if sid not in sensors_with_prev_defects]

            except sqlite3.Error as e:
                # On DB error, we leave combobox_candidates as-is but inform user (non-blocking)
                print(f"[save_action] Warning: could not filter previous defects due to DB error: {e}")
            finally:
                try:
                    if conn:
                        conn.close()
                except:
                    pass

        # combobox_candidates may be empty — still open the popup (popup handles empty lists)
        combobox_candidates = sorted(combobox_candidates)

        # 6) Determine lot condition for popup (so popup can adapt for EVAL)
        try:
            lot_condition_local = get_lot_condition(lot_number)
        except Exception:
            lot_condition_local = "MP"

        # 7) Create the popup, pass all DB sensors as sensor_list for quantity in/out calc
        popup = BMSPopup(
            root,
            lot_number,
            current_process,
            operator,
            all_sensors_for_lot,    # quantity IN basis
            combobox_candidates,    # combobox candidates (not-done capturing & not previous-defected)
            [],                     # failed_sensor_list (unused here)
            [],                     # blank_judgement_list (unused)
            [],                     # csv_rows_data (unused)
            lot_condition=lot_condition_local
        )
        popup.grab_set()

    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

def show_info_on_top(title, message):
    # Make sure the main window is topmost while the dialog is shown
    root.attributes('-topmost', True)
    root.update()  # ensure attribute takes effect
    try:
        messagebox.showinfo(title, message, parent=root)
    finally:
        # Restore normal stacking and return focus to the app
        root.attributes('-topmost', False)
        root.lift()
        root.focus_force()

def check_capture_complete_and_notify():
    global suppress_popups
    try:
        lot_no = entries["Lot Number:"].get().strip()
        current_process = entries["Current Process:"].get().strip()
        if not lot_no or not current_process:
            return False

        # determine previous defect columns (same as earlier)
        try:
            cur_idx = process_flow.index(current_process)
        except ValueError:
            cur_idx = -1

        previous_defect_columns = []
        if cur_idx > 0:
            for proc in process_flow[:cur_idx]:
                cols = process_column_mapping.get(proc)
                if cols and len(cols) > 2:
                    previous_defect_columns.append(cols[2])

        conn = sqlite3.connect(db_path_tracking)
        cur = conn.cursor()

        if previous_defect_columns:
            cond = " AND ".join(f"({col} IS NULL OR {col} = '')" for col in previous_defect_columns)
            query = f"SELECT sensor_id FROM lot_tracking WHERE lot_number = ? AND {cond}"
            cur.execute(query, (lot_no,))
        else:
            cur.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_no,))

        rows = cur.fetchall()
        conn.close()

        eligible_sensors = {r[0] for r in rows if r and r[0]}
        if not eligible_sensors:
            return False

        entered_sensor_ids = {
            data_entry[r][0].get().strip()
            for r in range(len(data_entry))
            if data_entry[r][0].get().strip()
        }

        # Check if all eligible sensors have completed capture (not just entered)
        all_completed = True
        for sensor_id in eligible_sensors:
            # Find the row for this sensor
            found_row = None
            for r in range(len(data_entry)):
                if data_entry[r][0].get().strip() == sensor_id:
                    found_row = r
                    break
            
            if found_row is None:
                # Sensor not in table yet
                all_completed = False
                break
            
            # Check if both Bottom and Top are "Done Capturing"
            try:
                bottom_val = data_entry[found_row][1].get().strip()
            except Exception:
                bottom_val = ""
            
            try:
                top_val = data_entry[found_row][2].get().strip() if len(data_entry[found_row]) > 2 else ""
            except Exception:
                top_val = ""
            
            # For QA Inspection 1: Both Bottom and Top must be done
            # For QA Inspection 2: Both Bottom and Top must be done (now that we unlocked Top)
            if bottom_val.lower() != "done capturing" or top_val.lower() != "done capturing":
                all_completed = False
                break

        if all_completed and eligible_sensors.issubset(entered_sensor_ids):
            # Destroy any existing image popup before showing the modal
            try:
                if hasattr(show_popup, 'popup') and getattr(show_popup, 'popup', None):
                    p = show_popup.popup
                    if p and p.winfo_exists():
                        p.destroy()
            except Exception:
                pass

            # Suppress any new popups while the modal appears
            suppress_popups = True
            try:
                messagebox.showinfo("Capture Complete", f"Capturing of Lot {lot_no} is completed.")
                entries["Operator:"].focus_set()
            finally:
                suppress_popups = False

            return True

    except Exception as e:
        print(f"[check_capture_complete_and_notify] Error: {e}")
    return False

def show_success_and_navigate(img_path):
    global current_col, current_row, curr_proc
    show_info_on_top("Success", f"File moved to {img_path}")

    # Consider capture completed when Top image is done for each process
    was_capture_completed = (
        (curr_proc == "QA Inspection 1" and current_col == 2)
        or (curr_proc == "QA Inspection 2" and current_col == 2)
    )

    current_entry = data_entry[current_row][current_col]
    current_entry.delete(0, tk.END)
    current_entry.insert(0, "Done Capturing")

    if curr_proc == "QA Inspection 1":
        next_col = current_col + 1
        next_row = current_row
        if next_col >= 3:
            # finished Top Image in this row -> go to next row, Bottom Image (col 1)
            next_col = 1  # Changed from 0 to 1 (Bottom Image column)
            next_row += 1

    elif curr_proc == "QA Inspection 2":
        next_col = current_col + 1
        next_row = current_row
        # For QA Inspection 2 we have 3 columns (0:Sensor,1:Bottom,2:Top)
        # After Bottom (1) -> go to Top (2). After Top (2) -> wrap to next row Bottom Image.
        if next_col >= 3:
            next_col = 1  # Changed from 0 to 1 (Bottom Image column)
            next_row += 1

    # If next position exists, prepare and focus it
    if 0 <= next_row < len(data_entry) and 0 <= next_col < len(data_entry[next_row]):
        next_entry = data_entry[next_row][next_col]

        # Focus the next entry (only if not readonly)
        if next_entry["state"] != "readonly":
            next_entry.focus_set()
            current_row = next_row
            current_col = next_col
        else:
            # If readonly (unexpected), attempt to move further down the same column
            alt_row = next_row + 1
            if alt_row < len(data_entry):
                alt_entry = data_entry[alt_row][next_col]
                if alt_entry["state"] != "readonly":
                    alt_entry.focus_set()
                    current_row = alt_row
                    current_col = next_col

    # After advancing focus, if we had just finished the Top Image, check overall completion
    if was_capture_completed:
        # Run the DB/UI check and notify if complete
        try:
            check_capture_complete_and_notify()
        except Exception as e:
            print(f"[show_success_and_navigate] Error checking capture complete: {e}")

def get_most_recent_file(folder_path):
    files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    if not files:
        return None
    return max(files, key=os.path.getctime)

def show_popup(most_recent_file, file_path, dest_folder):
    global suppress_popups

    # If popups are temporarily suppressed, skip showing this popup.
    if suppress_popups:
        # optional debug
        print(f"[show_popup] Suppressed popup for {file_path}")
        return

    # Prevent multiple popups from the caller side as well
    if hasattr(show_popup, 'popup') and getattr(show_popup, 'popup', None) and show_popup.popup.winfo_exists():
        return

    popup = tk.Toplevel(root)
    show_popup.popup = popup  # store reference
    popup.title("File Detected")
    popup.geometry("500x500")
    popup.attributes('-topmost', True)

    # Compute display name from current_row/current_col (fallback to fname)
    try:
        if current_row is not None and current_col is not None:
            sid = data_entry[current_row][0].get().strip()
            suffix_local = "Bottom" if current_col == 1 else "Top"
            display_name = f"{sid}_{suffix_local}.png" if sid else f"unknown_{suffix_local}.png"
        else:
            display_name = fname if fname else "unknown.png"
    except Exception:
        display_name = fname if fname else "unknown.png"

    # Load and display image
    try:
        img = Image.open(file_path)
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.2)
        img = img.resize((450, 350), Image.LANCZOS)
        img_tk = ImageTk.PhotoImage(img)

        image_label = tk.Label(popup, image=img_tk)
        image_label.image = img_tk
        image_label.pack(pady=10)
    except Exception as e:
        tk.Label(popup, text=f"Error loading image: {e}", fg="red").pack(pady=10)

    tk.Label(popup, text=f"Image saved as: {display_name}", wraplength=450).pack(pady=10)

    # Buttons
    buttons_frame = tk.Frame(popup)
    buttons_frame.pack(pady=10)

    def on_ok():
        nonlocal display_name
        global lot_number, curr_proc, fname

        if display_name is None and fname is None:
            messagebox.showerror("Error", "Filename is not available.")
            return

        try:
            if current_row is not None and current_col is not None:
                sid_now = data_entry[current_row][0].get().strip()
                suffix_now = "Bottom" if current_col == 1 else "Top"
                final_name = f"{sid_now}_{suffix_now}.png" if sid_now else (fname or display_name)
            else:
                final_name = fname or display_name

            dest_path = os.path.join(dest_folder, lot_number, curr_proc)
            os.makedirs(dest_path, exist_ok=True)
            img_path = os.path.join(dest_path, final_name)

            # Copy file first
            shutil.copy2(file_path, img_path)

            # After successful copy, attempt to delete the source file
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                # Log but do not prevent successful flow
                print(f"[show_popup] Warning: Failed to delete source file '{file_path}': {e}")

            show_success_and_navigate(img_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy file: {e}")

        popup.destroy()

    def on_retake():
        popup.destroy()
        try:
            if current_col == 1 and current_row is not None:
                data_entry[current_row][0].config(state="normal")
                data_entry[current_row][0].delete(0, tk.END)
                data_entry[current_row][0].focus_set()
                data_entry[current_row][1].config(state="readonly")
                if len(data_entry[current_row]) > 2:
                    data_entry[current_row][2].config(state="readonly")
        except Exception:
            pass

    ok_button = tk.Button(buttons_frame, text="OK", command=on_ok, bg="green", fg="white", padx=20, pady=5)
    ok_button.grid(row=0, column=0, padx=10)

    retake_button = tk.Button(buttons_frame, text="RETAKE", command=on_retake, bg="red", fg="white", padx=20, pady=5)
    retake_button.grid(row=0, column=1, padx=10)

processed_files = {}
debounce_time = 1

# Suppress popup flag
suppress_popups = False

def on_created(event):
    global processed_files, suffix, file_path, curr_proc

    if event.is_directory:
        return

    file_path = event.src_path
    current_time = time.time()

    # Debounce: ignore if processed very recently
    if file_path in processed_files:
        last_processed_time = processed_files[file_path]
        if current_time - last_processed_time < debounce_time:
            return

    processed_files[file_path] = current_time
    most_recent_file = get_most_recent_file(source_folder)
    if not most_recent_file:
        return

    # Show popup directly without template matching
    root.after(0, show_popup, most_recent_file, file_path, destination_folder)

def monitor_folder(src_folder):
    # Check if folder exists before starting observer
    if not os.path.exists(src_folder):
        print(f"[WARNING] Source folder does not exist: {src_folder}")
        print(f"[WARNING] File monitoring will not start. Please create the folder or check the path.")
        # Show warning to user
        root.after(0, lambda: messagebox.showwarning(
            "Folder Not Found",
            f"Image source folder not found:\n{src_folder}\n\nPlease ensure the Digital Microscope software is installed and the folder exists.\n\nThe program will continue, but automatic image detection will not work."
        ))
        return
    
    class SimpleHandler(FileSystemEventHandler):
        def on_created(self, event):
            on_created(event)

    observer = Observer()
    try:
        observer.schedule(SimpleHandler(), path=src_folder, recursive=False)
        observer.start()
        print(f"[INFO] File monitoring started for: {src_folder}")
        try:
            while True:
                time.sleep(1)  # Keep the observer running
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
    except Exception as e:
        print(f"[ERROR] Failed to start file monitoring: {e}")
        root.after(0, lambda: messagebox.showerror(
            "Monitoring Error",
            f"Could not start file monitoring:\n{str(e)}\n\nPlease check the folder path and permissions."
        ))

def get_previous_defect_info(lot_number, sensor_id, current_process):
    """
    Returns (has_defect: bool, process_name: str, defect_value: str, defect_column: str)
    If no defect found, returns (False, None, None, None)
    """
    try:
        # determine previous processes
        try:
            idx = process_flow.index(current_process)
        except ValueError:
            return (False, None, None, None)

        if idx == 0:
            return (False, None, None, None)

        previous_processes = process_flow[:idx]
        conn = sqlite3.connect(db_path_tracking)
        cursor = conn.cursor()

        # iterate previous processes and check their defect column (process_column_mapping[proc][2])
        for proc in previous_processes:
            cols = process_column_mapping.get(proc)
            if not cols or len(cols) <= 2:
                continue
            defect_col = cols[2]
            cursor.execute(f"SELECT {defect_col} FROM lot_tracking WHERE lot_number = ? AND sensor_id = ? LIMIT 1", (lot_number, sensor_id))
            row = cursor.fetchone()
            if row:
                val = row[0]
                if val is not None and str(val).strip() != "":
                    conn.close()
                    return (True, proc, str(val).strip(), defect_col)
        conn.close()
        return (False, None, None, None)
    except Exception as e:
        # On error, be conservative and treat as no defect (or you can treat as defect)
        print(f"Error checking previous defects: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return (False, None, None, None)

# Buttons for Delete and Save
headers = ["No.", "Sensor ID", "Bottom Image", "Top Image"]
header_positions = {
    "No.": (10, 155),
    "Sensor ID": (75, 155),
    "Bottom Image": (200, 155),
    "Top Image": (360, 155),
}
for header in headers:
    label = tk.Label(root, text=header, font=("Arial", 10, "bold"), bg="lightblue", relief="ridge")
    label.place(x=header_positions[header][0], y=header_positions[header][1])

# Table rows for data entry
data_entry = []

for row in range(20):
    row_entries = []
    # Add numbering label
    number_label = tk.Label(root, text=str(row + 1), width=3, bg="lightblue", relief="ridge")
    number_label.place(x=10, y=185 + row*23)
    for col in range(3):
        if col == 0:
                entry = tk.Entry(root, width=20, validate="key", justify='center')
                entry.place(x=45 + col*115, y=185 + row*23)
                entry.config(state="readonly")  # Sensor ID will be auto-populated, readonly
        else:
                entry = tk.Entry(root, width=20, validate="key", justify='center')
                entry.place(x=185 + (col-1)*150, y=185 + row*23)
        row_entries.append(entry)
    data_entry.append(row_entries)

# Bind focus_in events to all entries except Sensor ID entries
for row in data_entry:
    for col in range(0, 3):
        row[col].bind("<FocusIn>", on_focus_in)

# Buttons for Clear and Save (recreate them near top-right area)
delete_button = tk.Button(root, text="Clear Data", font=("Tahoma", 11, "bold"), padx=10, pady=1, bg="yellow", command=delete_action, relief='raised', borderwidth=3)
delete_button.place(x=320, y=84)
save_button = tk.Button(root, text="SAVE", font=("Tahoma", 11, "bold"), padx=30, pady=1, bg="orange", command=save_action, relief='raised', borderwidth=3)
save_button.place(x=320, y=45)

# Start the application
delete_action()
entries["Lot Number:"].focus_set()
root.mainloop()