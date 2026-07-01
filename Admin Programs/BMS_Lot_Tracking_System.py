import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import sqlite3
import json
import sys
import os

# Define the absolute path to your process_flow.json
config_file_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\process_flow.json"  # Example for Windows
# config_file_path = "/home/user/my_app/process_flow.json"  # Example for Linux/macOS

def show_error_and_exit(title, message):
    # Create a temporary root so messagebox can show
    tmp = tk.Tk()
    tmp.withdraw()
    messagebox.showerror(title, message)
    tmp.destroy()
    sys.exit(1)

# Load process_flow and process_column_mapping from JSON config
try:
    with open(config_file_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    process_flow = config.get("process_flow")
    process_column_mapping = config.get("process_column_mapping")
    if not isinstance(process_flow, list) or not isinstance(process_column_mapping, dict):
        raise ValueError("process_flow must be a list and process_column_mapping must be a dict in JSON.")
    # Ensure mapping values are lists/tuples of expected length (6)
    for k, v in process_column_mapping.items():
        if not isinstance(v, (list, tuple)) or len(v) < 6:
            raise ValueError(f"Mapping for process '{k}' must be a list/tuple of at least 6 column names.")
except FileNotFoundError:
    show_error_and_exit("Configuration Error", f"Config file not found at: {config_file_path}")
except json.JSONDecodeError:
    show_error_and_exit("Configuration Error", "Error decoding process_flow.json. Please check its format.")
except Exception as e:
    show_error_and_exit("Configuration Error", f"Invalid configuration: {e}")

# Function to update date and time in real-time
def update_time():
    current_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    date_time_label.config(text=current_time)
    root.after(1000, update_time)  # Update every second

# Function to clear fields
def clear_fields():
    lot_number_entry.delete(0, tk.END)
    sensor_id_combobox.set("")
    current_process_entry.delete(0, tk.END)
    defect_entry.delete(0, tk.END)
    remarks_entry.delete(0, tk.END)
    operator_entry.delete(0, tk.END)
    quantity_in_entry.delete(0, tk.END)
    quantity_out_entry.delete(0, tk.END)
    for row in table.get_children():
        table.delete(row)

# Function to clear only Defect and Remarks fields
def clear_defect_remarks_fields():
    defect_entry.delete(0, tk.END)
    remarks_entry.delete(0, tk.END)

# Function to delete selected row from the table
def delete_selected_row():
    selected_item = table.selection()
    if selected_item:
        table.delete(selected_item)
        update_quantity_out()
    else:
        messagebox.showwarning("Selection Error", "Please select a row to delete.")

# Function to save data
def save_data():
    lot_number = lot_number_entry.get().strip()
    current_process = current_process_entry.get().strip()
    sensor_id = sensor_id_combobox.get().strip()
    operator = operator_entry.get().strip()

    # Validation checks
    if not lot_number or not current_process or not sensor_id or not operator:
        messagebox.showwarning("Input Error", "Please ensure Lot Number, Current Process, Sensor ID, and Operator are filled.")
        return

    # Ensure current_process exists in process_flow
    if current_process not in process_flow:
        messagebox.showwarning("Process Error", f"Current process '{current_process}' not found in process_flow configuration.")
        return

    # Ensure current_process has column mapping
    if current_process not in process_column_mapping:
        messagebox.showwarning("Mapping Error", f"No column mapping found for process '{current_process}' in config.")
        return

    # Fetch sensor IDs related to the lot number
    try:
        conn = sqlite3.connect(r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db")
        cursor = conn.cursor()
    except Exception as e:
        messagebox.showerror("Database Error", f"Could not connect to lot_tracking.db: {e}")
        return

    cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot_number,))
    sensor_ids = [row[0] for row in cursor.fetchall()]

    if not sensor_ids:
        messagebox.showwarning("Input Error", "No Sensor IDs found for the given Lot Number.")
        conn.close()
        return

    # Check for missing values in lot_masterlist.db for certain processes (existing hardcoded mapping)
    process_to_columns = {
        "Laser Marking and OCR": ["OCR_Reading"],
        "MR Chip Alignment Measurement": ["X_alignment_1", "Y_alignment_1", "X_alignment_2", "Y_alignment_2"],
        "MR Chip Height Measurement": ["mr_chip_height"],
        "SBB Resistance Measurement": ["SBB_Resistance_Coil_Pos", "SBB_Resistance_Coil_Vb", "SBB_Resistance_Va_Vb", "SBB_Resistance_Vdd_GnD"],
        "Assembly Measurement": ["BS_gap_to_GMR", "TS_gap_to_GMR", "BS_Gap_to_MR_Chip", "TS_Gap_to_MR_Chip", "PCB_Gap_to_BS1", "PCB_Gap_to_BS2"],
        "QA Inspection 1": ["QA_Inspection1_bottom", "QA_Inspection1_top"],
        "Top Molding Dimension": ["Top_Molding_Length", "Top_Molding_Width", "Top_Molding_Height"],
        "Labelling": ["Labelling"],
        "Wire Orientation Check": ["Wire1_Color", "Wire2_Color", "Wire3_Color", "Wire4_Color", "Wire5_Color", "Wire6_Color"], 
        "Cable Resistance": ["Cable_Resistance_48_turns", "Cable_Resistance_Coil_Vb", "Cable_Resistance_Va_Vb", "Cable_Resistance_Vdd_GnD"],
        "QA Inspection 2": ["QA_Inspection2_bottom"],
        "Bottom Molding Dimension": ["Bottom_Molding_Length", "Bottom_Molding_Width", "Bottom_Molding_Height"],
        "Inductance and Resistance Measurement": ["Inductance", "Final_Resistance_Coil_Vb", "Final_Resistance_Va_Vb", "Final_Resistance_Vdd_GnD"],
        "Dynamic Range Measurement": ["Dynamic_range_uT", "Linearity_FS"],
        "Frequency Response Measurement": ["Sensitivity_mV_nT", "Sensitivity_uV_nT"],
        "Noise Density Measurement": ["Noise_Density_1Hz", "Noise_Density_10kHz"],
        "QA Final Inspection": ["QA_Final_bottom", "QA_Final_top", "QA_Final_sensor"]
    }
    columns = process_to_columns.get(current_process, [])

    missing_values_sensor_ids = []
    columns_check = process_to_columns.get(current_process, [])

    if columns_check:
        try:
            conn_masterlist = sqlite3.connect(r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db")
            cursor_masterlist = conn_masterlist.cursor()
        except Exception as e:
            messagebox.showerror("Database Error", f"Could not connect to lot_masterlist.db: {e}")
            conn.close()
            return

        sensor_ids_combobox = sensor_id_combobox['values']  # Get the sensor IDs from the combobox
        for sid in sensor_ids_combobox:
            cursor_masterlist.execute(f"SELECT {', '.join(columns_check)} FROM lot_masterlist WHERE sensor_id=?", (sid,))
            result = cursor_masterlist.fetchone()
            if not result or any(value is None for value in result):
                missing_values_sensor_ids.append(sid)
        conn_masterlist.close()

        if missing_values_sensor_ids:
            messagebox.showwarning("Input Error", f"The following Sensor IDs have missing values in '{current_process}': {', '.join(missing_values_sensor_ids)}")
            conn.close()
            return

    # Continue with saving logic
    try:
        quantity_in = quantity_in_entry.get().strip()
        quantity_out = quantity_out_entry.get().strip()
        current_date_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        columns = process_column_mapping[current_process]
    except KeyError:
        messagebox.showerror("Mapping Error", f"No column mapping found for process '{current_process}'.")
        conn.close()
        return

    # Update lot_tracking for sensor IDs in the table
    for row in table.get_children():
        sid, defect, remarks = table.item(row)["values"]
        try:
            cursor.execute(f"""
                UPDATE lot_tracking
                SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, {columns[3]}=?, {columns[4]}=?, {columns[5]}=?
                WHERE lot_number=? AND sensor_id=?
            """, (quantity_in, quantity_out, defect, remarks, current_date_time, operator, lot_number, sid))
        except sqlite3.OperationalError as e:
            messagebox.showerror("SQL Error", f"Database schema issue when updating columns for process '{current_process}': {e}")
            conn.close()
            return

    # Update remaining sensor IDs (those not in table)
    sensor_ids_in_table = {table.item(row)["values"][0] for row in table.get_children()}
    remaining_sensor_ids = set(sensor_ids) - sensor_ids_in_table
    for sid in remaining_sensor_ids:
        try:
            cursor.execute(f"""
                UPDATE lot_tracking
                SET {columns[0]}=?, {columns[1]}=?, {columns[2]}='', {columns[3]}='', {columns[4]}=?, {columns[5]}=?
                WHERE lot_number=? AND sensor_id=?
            """, (quantity_in, quantity_out, current_date_time, operator, lot_number, sid))
        except sqlite3.OperationalError as e:
            messagebox.showerror("SQL Error", f"Database schema issue when updating columns for process '{current_process}': {e}")
            conn.close()
            return

    # Update next process
    try:
        next_process_index = process_flow.index(current_process) + 1
        if next_process_index < len(process_flow):
            next_process = process_flow[next_process_index]
        else:
            next_process = "Done Assy and Testing"
    except ValueError:
        next_process = "Done Assy and Testing"

    # Remove records for sensor IDs with defects
    sensor_ids_with_defects = [table.item(row)["values"][0] for row in table.get_children() if table.item(row)["values"][1]]

    for sid in sensor_ids_with_defects:
        cursor.execute("DELETE FROM lot_tracking WHERE lot_number=? AND sensor_id=?", (lot_number, sid))

    # Update external sensor list file if database_path exists
    cursor.execute("SELECT database_path FROM lot_tracking WHERE lot_number=?", (lot_number,))
    row = cursor.fetchone()
    if row and row[0]:
        text_file_path = row[0]
        try:
            # Only proceed if file exists
            if os.path.isfile(text_file_path):
                with open(text_file_path, 'r', encoding='utf-8') as file:
                    lines = file.readlines()

                with open(text_file_path, 'w', encoding='utf-8') as file:
                    for line in lines:
                        if line.strip() not in sensor_ids_with_defects:
                            file.write(line)
            else:
                # If file not found, warn but continue
                messagebox.showwarning("File Warning", f"Sensor list file not found: {text_file_path}. Skipping file update.")
                lines = []
        except Exception as e:
            messagebox.showerror("File Error", f"An error occurred while updating the sensor list file: {e}")
            conn.close()
            return
    else:
        lines = []

    # Special saving behavior for Main Curing 2
    if current_process == "Main Curing 2":
        new_file_path = r"D:\BMS\DR-FMEA Action Items\Labels\Sensor Label.txt"
        try:
            with open(new_file_path, 'w', encoding='utf-8') as file:
                for line in lines:
                    if line.strip() not in sensor_ids_with_defects:
                        file.write(line)
            # Optionally log success
            print(f"File successfully saved to {new_file_path}.")
        except Exception as e:
            messagebox.showerror("File Error", f"An error occurred while saving the file: {e}")
            conn.close()
            return

    cursor.execute("""
        UPDATE lot_tracking
        SET current_process=?
        WHERE lot_number=?
    """, (next_process, lot_number))
    conn.commit()
    conn.close()
    messagebox.showinfo("Success", "Data saved successfully.")
    clear_fields()

# Function to update Quantity Out based on defect entries
def update_quantity_out():
    try:
        quantity_in_val = quantity_in_entry.get().strip()
        quantity_in = int(quantity_in_val) if quantity_in_val else 0
    except ValueError:
        quantity_in = 0
    # Count the number of Sensor IDs with defects
    sensor_ids_with_defects = len([table.item(row)["values"][1] for row in table.get_children() if table.item(row)["values"][1]])
    quantity_out = max(quantity_in - sensor_ids_with_defects, 0)
    quantity_out_entry.delete(0, tk.END)
    quantity_out_entry.insert(0, str(quantity_out))

# Function to export table data to a CSV file (this actually inserts defects/remarks into the table)
def export_data():
    sensor_id = sensor_id_combobox.get().strip()
    defect = defect_entry.get().strip()
    remarks = remarks_entry.get().strip()

    # Check if Sensor ID is already in the table
    existing_ids = [table.item(row)["values"][0] for row in table.get_children()]
    if sensor_id in existing_ids:
        messagebox.showwarning("Input Error", "Sensor ID already exists in the table.")
    elif sensor_id:
        table.insert('', 'end', values=(sensor_id, defect, remarks))
        update_quantity_out()
        clear_defect_remarks_fields()
    else:
        messagebox.showwarning("Input Error", "Please enter Sensor ID.")

# Function to fetch Sensor IDs from the database based on Lot Number
def fetch_sensor_ids():
    lot_number = lot_number_entry.get().strip()
    if not lot_number:
        messagebox.showwarning("Input Error", "Please enter a Lot Number.")
        return

    try:
        conn = sqlite3.connect(r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db")
        cursor = conn.cursor()
    except Exception as e:
        messagebox.showerror("Database Error", f"Could not connect to lot_tracking.db: {e}")
        return

    # Try exact match first, then fall back to more permissive matching
    rows = []
    try:
        cursor.execute("SELECT sensor_id, current_process FROM lot_tracking WHERE lot_number=?", (lot_number,))
        rows = cursor.fetchall()

        if not rows:
            # lot_number stored with suffix/prefix -> try startswith
            cursor.execute("SELECT sensor_id, current_process FROM lot_tracking WHERE lot_number LIKE ?", (lot_number + '%',))
            rows = cursor.fetchall()

        if not rows:
            # maybe sensor_id contains the lot number
            cursor.execute("SELECT sensor_id, current_process FROM lot_tracking WHERE sensor_id LIKE ?", ('%' + lot_number + '%',))
            rows = cursor.fetchall()
    except Exception as e:
        messagebox.showerror("Database Error", f"Query error: {e}")
        conn.close()
        return

    if not rows:
        messagebox.showerror("Error", f"Invalid Lot Number: {lot_number}. Please check and try again.")
        conn.close()
        return

    sensor_ids = [row[0] for row in rows]
    current_process = rows[0][1] if rows else ""

    if current_process == "Done Assy and Testing":
        messagebox.showinfo("Information",  f"Lot Number:{lot_number} was Finished Assembly and Testing")
        conn.close()
        clear_fields()
        return

    # Determine the current process index (for filtering using previous steps)
    try:
        current_process_index = process_flow.index(current_process)
    except ValueError:
        messagebox.showwarning("Process Warning", f"Current process '{current_process}' not found in process_flow config.")
        current_process_index = 0

    # For each previous process, keep only sensor_ids that have no defect recorded
    for i in range(current_process_index):
        previous_process = process_flow[i]
        previous_columns = process_column_mapping.get(previous_process)
        if not previous_columns:
            continue
        defect_col = previous_columns[2]

        # Query only the sensor_ids we have so far and check defect column is empty or NULL
        if not sensor_ids:
            break
        placeholders = ','.join('?' for _ in sensor_ids)
        sql = f"""
            SELECT sensor_id FROM lot_tracking
            WHERE sensor_id IN ({placeholders}) AND (COALESCE({defect_col}, '') = '')
        """
        try:
            cursor.execute(sql, tuple(sensor_ids))
            allowed = {r[0] for r in cursor.fetchall()}
            sensor_ids = [sid for sid in sensor_ids if sid in allowed]
        except Exception as e:
            # If column doesn't exist or other DB error, skip filtering for this step but warn
            messagebox.showwarning("Database Warning", f"Could not filter by previous process '{previous_process}': {e}")
            # don't further filter by this step

    conn.close()

    # Update Sensor ID Combobox
    sensor_id_combobox['values'] = sensor_ids
    if sensor_ids:
        sensor_id_combobox.set(sensor_ids[0])

    # Update Quantity In/Out and Current Process
    quantity_in_entry.delete(0, tk.END)
    quantity_in_entry.insert(0, str(len(sensor_ids)))
    quantity_out_entry.delete(0, tk.END)
    quantity_out_entry.insert(0, str(len(sensor_ids)))
    current_process_entry.delete(0, tk.END)
    current_process_entry.insert(0, current_process)


# Setting up the GUI
root = tk.Tk()
root.title("BMS Lot Tracking System")
root.geometry("615x455")
root.configure(bg='#3a6ba8')

# Disable maximize functionality
root.resizable(False, False)

# Labels and Entries
title_label = tk.Label(root, text="BMS Lot Tracking System", font=("BiomeW04-Bold", 20, "bold"), bg='#3a6ba8', fg="orange")
title_label.place(x=20, y=0)

# Lot Number and Current Process
tk.Label(root, text="Lot Number:", bg='#3a6ba8', fg="white").place(x=5, y=45)
lot_number_entry = tk.Entry(root, width=31)
lot_number_entry.place(x=105, y=45)
lot_number_entry.bind("<Return>", lambda event: fetch_sensor_ids())  # Bind Enter key to fetch_sensor_ids function

tk.Label(root, text="Current Process:", bg='#3a6ba8', fg="white").place(x=5, y=75)
current_process_entry = tk.Entry(root, width=31)
current_process_entry.place(x=105, y=75)

# Sensor ID, Defect, and Remarks
tk.Label(root, text="Sensor ID:", bg='#3a6ba8', fg="white").place(x=5, y=105)
sensor_id_combobox = ttk.Combobox(root, values=[], width=28)
sensor_id_combobox.place(x=105, y=105)

tk.Label(root, text="Defect:", bg='#3a6ba8', fg="white").place(x=5, y=135)
defect_entry = tk.Entry(root, width=31)
defect_entry.place(x=105, y=135)

tk.Label(root, text="Remarks:", bg='#3a6ba8', fg="white").place(x=5, y=165)
remarks_entry = tk.Entry(root, width=31)
remarks_entry.place(x=105, y=165)

# Quantity In and Out
tk.Label(root, text="Quantity IN:", bg='#3a6ba8', fg="white").place(x=320, y=45)
quantity_in_entry = tk.Entry(root, width=15)
quantity_in_entry.place(x=410, y=45)

tk.Label(root, text="Quantity OUT:", bg='#3a6ba8', fg="white").place(x=320, y=75)
quantity_out_entry = tk.Entry(root, width=15)
quantity_out_entry.place(x=410, y=75)

# Date and Operator
tk.Label(root, text="Date:", bg='#3a6ba8', fg="white").place(x=320, y=105)
date_time_label = tk.Label(root, text="", bg='white', width=19)
date_time_label.place(x=410, y=105)

tk.Label(root, text="Operator:", bg='#3a6ba8', fg="white").place(x=320, y=135)
operator_entry = tk.Entry(root, width=22)
operator_entry.place(x=410, y=135)

# Buttons
export_button = tk.Button(root, text="Export Defects / Remarks", command=export_data, bg="green", fg="white", font=("Tahoma", 10, "bold"), padx=20, pady=1, relief='raised', borderwidth=3)
export_button.place(x=20, y=200)

clear_button = tk.Button(root, text="CLEAR", command=clear_fields, bg="yellow", font=("Tahoma", 16, "bold"), padx=10, pady=1, relief='raised', borderwidth=3)
clear_button.place(x=320, y=185)

save_button = tk.Button(root, text="SAVE", command=save_data, bg="green", fg="white", font=("Tahoma", 16, "bold"), padx=10, pady=1, relief='raised', borderwidth=3)
save_button.place(x=460, y=185)

delete_button = tk.Button(root, text="DELETE Defects / Remarks", command=delete_selected_row, bg="red", fg="white", font=("Tahoma", 10, "bold"), padx=20, pady=1, relief='raised', borderwidth=3)
delete_button.place(x=20, y=235)

# Table for Sensor ID, Defects, Remarks
columns = ("Sensor ID", "Defects", "Remarks")
table = ttk.Treeview(root, columns=columns, show="headings", height=7)
for col in columns:
    table.heading(col, text=col)
table.place(x=5, y=280)

# Configure row and column weights for resizing
root.grid_rowconfigure(3, weight=1)
root.grid_columnconfigure(0, weight=1)
root.grid_columnconfigure(1, weight=1)
root.grid_columnconfigure(2, weight=1)
root.grid_columnconfigure(3, weight=1)

# Start updating time
update_time()
root.mainloop()