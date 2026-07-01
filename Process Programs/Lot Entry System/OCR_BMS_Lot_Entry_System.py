import tkinter as tk
from tkinter import ttk
from datetime import datetime
from tkinter import messagebox
import os
import qrcode
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageWin
import cv2

# Pillow resampling compatibility: Image.Resampling exists in newer Pillow.
try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    # Older Pillow releases expose LANCZOS directly on Image (or use ANTIALIAS)
    try:
        RESAMPLE_LANCZOS = Image.LANCZOS
    except AttributeError:
        RESAMPLE_LANCZOS = Image.ANTIALIAS

from tkinter import Toplevel
import json  # Using JSON to store and load used series data
import sqlite3  # Importing sqlite3 for database operations
import textwrap
import win32print
import win32ui

# Database setup
DB_FILE = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"

def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Create table if it does not exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lot_masterlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            lot_number TEXT NOT NULL,
            sensor_id TEXT NOT NULL,
            wafer_number TEXT NOT NULL,
            pcb_batch TEXT NOT NULL,
            condition TEXT NOT NULL,
            cable_type TEXT NOT NULL,
            cable_length TEXT NOT NULL,
            coil_connection TEXT NOT NULL,
            created_date TEXT NOT NULL,
            created_by TEXT NOT NULL,
            product_description NOT NULL,
            OCR_Reading TEXT,
            X_alignment_1 TEXT,
            Y_alignment_1 TEXT,
            X_alignment_2 TEXT,
            Y_alignment_2 TEXT,
            mr_chip_height TEXT,
            SBB_Resistance_Coil_Pos TEXT,
            SBB_Resistance_Coil_Vb TEXT,
            SBB_Resistance_Va_Vb TEXT,
            SBB_Resistance_Vdd_GnD TEXT,
            BS_gap_to_GMR TEXT,
            TS_gap_to_GMR TEXT,
            BS_Gap_to_MR_Chip TEXT,
            TS_Gap_to_MR_Chip TEXT,
            PCB_Gap_to_BS1 TEXT,
            PCB_Gap_to_BS2 TEXT,
            QA_Inspection1_bottom TEXT, 
            QA_Inspection1_top TEXT,
            Top_Molding_Length TEXT,
            Top_Molding_Width TEXT,
            Top_Molding_Height TEXT,
            Wire1_Color TEXT, 
            Wire2_Color TEXT, 
            Wire3_Color TEXT, 
            Wire4_Color TEXT, 
            Wire5_Color TEXT, 
            Wire6_Color TEXT,
            Cable_Resistance_48_turns TEXT,
            Cable_Resistance_Coil_Vb TEXT,
            Cable_Resistance_Va_Vb TEXT,
            Cable_Resistance_Vdd_GnD TEXT,
            QA_Inspection2_bottom TEXT,
            Bottom_Molding_Length TEXT,
            Bottom_Molding_Width TEXT,
            Bottom_Molding_Height TEXT,
            Inductance TEXT, 
            Final_Resistance_Coil_Vb TEXT, 
            Final_Resistance_Va_Vb TEXT, 
            Final_Resistance_Vdd_GnD TEXT,
            Dynamic_range_uT TEXT,
            Linearity_FS TEXT,
            Sensitivity_mV_nT TEXT,
            Sensitivity_uV_nT TEXT,
            Noise_Density_1Hz TEXT,
            Noise_Density_10kHz TEXT,
            QA_Final_bottom TEXT, 
            QA_Final_top TEXT, 
            QA_Final_sensor TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Call the setup_database function when the script starts
setup_database()

# Define the path for the new database
LOT_TRACKING_DB_PATH = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"

# Set up the lot_tracking database with the new schema
def setup_lot_tracking_database():
    conn = sqlite3.connect(LOT_TRACKING_DB_PATH)
    cursor = conn.cursor()
    # Create table if it does not exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lot_tracking (
            lot_number TEXT,
            sensor_id TEXT,
            database_path TEXT,
            current_process TEXT,
            lot_entry_IN TEXT,
            lot_entry_OUT TEXT,
            lot_entry_proc_date TEXT,
            lot_entry_operator TEXT,
            marking_ocr_IN TEXT, 
            marking_ocr_OUT TEXT, 
            marking_ocr_defect TEXT, 
            marking_ocr_remarks TEXT, 
            marking_ocr_proc_date TEXT, 
            marking_ocr_operator TEXT,
            chip_bonding_IN TEXT, 
            chip_bonding_OUT TEXT, 
            chip_bonding_defect TEXT, 
            chip_bonding_remarks TEXT, 
            chip_bonding_proc_date TEXT, 
            chip_bonding_operator TEXT,
            chip_meas_IN TEXT, 
            chip_meas_OUT TEXT, 
            chip_meas_defect TEXT, 
            chip_meas_remarks TEXT, 
            chip_meas_proc_date TEXT, 
            chip_meas_operator TEXT,
            chip_to_pcb_IN TEXT, 
            chip_to_pcb_OUT TEXT, 
            chip_to_pcb_defect TEXT, 
            chip_to_pcb_remarks TEXT, 
            chip_to_pcb_proc_date TEXT, 
            chip_to_pcb_operator TEXT,
            oven1_IN TEXT, 
            oven1_OUT TEXT, 
            oven1_defect TEXT, 
            oven1_remarks TEXT, 
            oven1_proc_date TEXT, 
            oven1_operator TEXT,
            cleaning1_IN TEXT, 
            cleaning1_OUT TEXT, 
            cleaning1_defect TEXT, 
            cleaning1_remarks TEXT, 
            cleaning1_proc_date TEXT, 
            cleaning1_operator TEXT,
            oven2_IN TEXT, 
            oven2_OUT TEXT, 
            oven2_defect TEXT, 
            oven2_remarks TEXT, 
            oven2_proc_date TEXT, 
            oven2_operator TEXT,
            sbb_IN TEXT, 
            sbb_OUT TEXT, 
            sbb_defect TEXT, 
            sbb_remarks TEXT, 
            sbb_proc_date TEXT, 
            sbb_operator TEXT,
            sbb_resist_IN TEXT, 
            sbb_resist_OUT TEXT, 
            sbb_resist_defect TEXT, 
            sbb_resist_remarks TEXT, 
            sbb_resist_proc_date TEXT, 
            sbb_resist_operator TEXT,
            bs_bonding_IN TEXT, 
            bs_bonding_OUT TEXT, 
            bs_bonding_defect TEXT, 
            bs_bonding_remarks TEXT, 
            bs_bonding_proc_date TEXT, 
            bs_bonding_operator TEXT,
            ts_bonding_IN TEXT, 
            ts_bonding_OUT TEXT, 
            ts_bonding_defect TEXT, 
            ts_bonding_remarks TEXT, 
            ts_bonding_proc_date TEXT, 
            ts_bonding_operator TEXT,
            assy_meas_IN TEXT, 
            assy_meas_OUT TEXT, 
            assy_meas_defect TEXT, 
            assy_meas_remarks TEXT, 
            assy_meas_proc_date TEXT, 
            assy_meas_operator TEXT,
            oven3_IN TEXT, 
            oven3_OUT TEXT, 
            oven3_defect TEXT, 
            oven3_remarks TEXT, 
            oven3_proc_date TEXT, 
            oven3_operator TEXT,
            pin_soldering_IN TEXT, 
            pin_soldering_OUT TEXT, 
            pin_soldering_defect TEXT, 
            pin_soldering_remarks TEXT, 
            pin_soldering_proc_date TEXT, 
            pin_soldering_operator TEXT,
            cleaning2_IN TEXT, 
            cleaning2_OUT TEXT, 
            cleaning2_defect TEXT, 
            cleaning2_remarks TEXT, 
            cleaning2_proc_date TEXT, 
            cleaning2_operator TEXT,
            oven4_IN TEXT, 
            oven4_OUT TEXT, 
            oven4_defect TEXT, 
            oven4_remarks TEXT, 
            oven4_proc_date TEXT, 
            oven4_operator TEXT,
            qa1_IN TEXT, 
            qa1_OUT TEXT, 
            qa1_defect TEXT, 
            qa1_remarks TEXT, 
            qa1_proc_date TEXT, 
            qa1_operator TEXT,
            top_molding_IN TEXT, 
            top_molding_OUT TEXT, 
            top_molding_defect TEXT, 
            top_molding_remarks TEXT, 
            top_molding_proc_date TEXT, 
            top_molding_operator TEXT,
            oven5_IN TEXT, 
            oven5_OUT TEXT, 
            oven5_defect TEXT, 
            oven5_remarks TEXT, 
            oven5_proc_date TEXT, 
            oven5_operator TEXT,
            top_mold_meas_IN TEXT, 
            top_mold_meas_OUT TEXT, 
            top_mold_meas_defect TEXT, 
            top_mold_meas_remarks TEXT, 
            top_mold_meas_proc_date TEXT, 
            top_mold_meas_operator TEXT,
            cable_solder_IN TEXT, 
            cable_solder_OUT TEXT, 
            cable_solder_defect TEXT, 
            cable_solder_remarks TEXT, 
            cable_solder_proc_date TEXT, 
            cable_solder_operator TEXT,
            wire_check_IN TEXT, 
            wire_check_OUT TEXT, 
            wire_check_defect TEXT, 
            wire_check_remarks TEXT, 
            wire_check_proc_date TEXT, 
            wire_check_operator TEXT,
            labelling_IN TEXT, 
            labelling_OUT TEXT, 
            labelling_defect TEXT, 
            labelling_remarks TEXT, 
            labelling_proc_date TEXT, 
            labelling_operator TEXT,
            cleaning3_IN TEXT, 
            cleaning3_OUT TEXT, 
            cleaning3_defect TEXT, 
            cleaning3_remarks TEXT, 
            cleaning3_proc_date TEXT, 
            cleaning3_operator TEXT,
            cable_resist_IN TEXT, 
            cable_resist_OUT TEXT, 
            cable_resist_defect TEXT, 
            cable_resist_remarks TEXT, 
            cable_resist_proc_date TEXT, 
            cable_resist_operator TEXT,
            oven6_IN TEXT, 
            oven6_OUT TEXT, 
            oven6_defect TEXT, 
            oven6_remarks TEXT, 
            oven6_proc_date TEXT, 
            oven6_operator TEXT,
            qa2_IN TEXT, 
            qa2_OUT TEXT, 
            qa2_defect TEXT, 
            qa2_remarks TEXT, 
            qa2_proc_date TEXT, 
            qa2_operator TEXT,
            bottom_molding_IN TEXT, 
            bottom_molding_OUT TEXT, 
            bottom_molding_defect TEXT, 
            bottom_molding_remarks TEXT, 
            bottom_molding_proc_date TEXT, 
            bottom_molding_operator TEXT,
            oven7_IN TEXT, 
            oven7_OUT TEXT, 
            oven7_defect TEXT, 
            oven7_remarks TEXT, 
            oven7_proc_date TEXT, 
            oven7_operator TEXT,
            bot_mold_meas_IN TEXT, 
            bot_mold_meas_OUT TEXT, 
            bot_mold_meas_defect TEXT, 
            bot_mold_meas_remarks TEXT, 
            bot_mold_meas_proc_date TEXT, 
            bot_mold_meas_operator TEXT,
            ind_resist_IN TEXT, 
            ind_resist_OUT TEXT, 
            ind_resist_defect TEXT, 
            ind_resist_remarks TEXT, 
            ind_resist_proc_date TEXT, 
            ind_resist_operator TEXT,
            dynamic_meas_IN TEXT,
            dynamic_meas_OUT TEXT,
            dynamic_meas_defect TEXT,
            dynamic_meas_remarks TEXT,
            dynamic_meas_proc_date TEXT,
            dynamic_meas_operator TEXT,
            freq_resp_IN TEXT, 
            freq_resp_OUT TEXT, 
            freq_resp_defect TEXT, 
            freq_resp_remarks TEXT, 
            freq_resp_proc_date TEXT,
            noise_den_IN TEXT,
            noise_den_OUT TEXT,
            noise_den_defect TEXT,
            noise_den_remarks TEXT,
            noise_den_proc_date TEXT,
            noise_den_operator TEXT,
            conn_removal_IN TEXT,
            conn_removal_OUT TEXT,
            conn_removal_defect TEXT,
            conn_removal_remarks TEXT,
            conn_removal_proc_date TEXT,
            conn_removal_operator TEXT,
            qa_final_IN TEXT, 
            qa_final_OUT TEXT, 
            qa_final_defect TEXT, 
            qa_final_remarks TEXT, 
            qa_final_proc_date TEXT, 
            qa_final_operator TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Call the setup_lot_tracking_database function to initialize the database
setup_lot_tracking_database()

def insert_into_lot_tracking(lot_number, sensor_id, database_path, current_process, lot_entry_IN, lot_entry_OUT, lot_entry_proc_date, lot_entry_operator):
    conn = sqlite3.connect(LOT_TRACKING_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO lot_tracking (
            lot_number, sensor_id, database_path, current_process, lot_entry_IN, lot_entry_OUT, lot_entry_proc_date, lot_entry_operator
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (lot_number, sensor_id, database_path, current_process, lot_entry_IN, lot_entry_OUT, lot_entry_proc_date, lot_entry_operator))
    conn.commit()
    conn.close()

# File to store the used Series Numbers per date
USED_SERIES_FILE = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\used_series.json"

# Load used series from the file
def load_used_series():
    if os.path.exists(USED_SERIES_FILE):
        with open(USED_SERIES_FILE, "r") as file:
            return json.load(file)
    return {}

# Save the used series to the file
def save_used_series(used_series):
    with open(USED_SERIES_FILE, "w") as file:
        json.dump(used_series, file)

# Get today's date in 'YYYY-MM-DD' format
def get_today_date():
    return datetime.now().strftime("%Y-%m-%d")

# Function to generate the next available series number and populate the series_text entry
def generate_next_series():
    used_series = load_used_series()
    today = get_today_date()

    # Get today's used series numbers
    used_today = used_series.get(today, [])

    # Determine the next available series number
    if used_today:
        # Find the maximum used series number and increment it
        last_used = max(int(s) for s in used_today)
        next_series = f"{last_used + 1:02}" if last_used < 99 else "01" # Roll over to 01 if 99 is reached
    else:
        # If nothing is used today, start with "01"
        next_series = "01"
    
    # Update the series_text entry
    series_text.config(state='normal')  # Temporarily enable to update
    series_text.delete(0, tk.END)  # Clear previous count
    series_text.insert(0, next_series)  # Insert the new series number
    series_text.config(state='disabled')  # Disable editing again

# Add the selected Series Number to the used list and force the order
def add_used_series(series):
    used_series = load_used_series()
    today = get_today_date()

    # Add today's series if not already present
    if today not in used_series:
        used_series[today] = []

    # Add the selected series to today's used series if it's valid
    if series not in used_series[today]:
        used_series[today].append(series)

    # Save the updated used series data
    save_used_series(used_series)

    # Update the combobox to reflect the next available series in order
    generate_next_series()


# This code was generated by TDK ChatGPT 
PCB_COUNT_FILE = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\pcb_count.json"

# Load the PCB count from the JSON file
def load_pcb_count():
    if os.path.exists(PCB_COUNT_FILE):
        with open(PCB_COUNT_FILE, "r") as file:
            return json.load(file)
    return {}
 
# Save the updated PCB count back to the JSON file
def save_pcb_count(pcb_count):
    with open(PCB_COUNT_FILE, "w") as file:
        json.dump(pcb_count, file)

# Temporary storage for the current session's PCB count
temp_pcb_count_data = {}

# Track the number of lines in the OCR text
previous_line_count = 0

# Dictionary to track the PCB count assigned to each OCR line position
line_pcb_counts = {}

def update_sensor_id(ocr_text, wafer_text, pcb_text, sensor_id_text, sensor_start_widget):
    global previous_line_count, line_pcb_counts

    ocr_lines = ocr_text.get('1.0', tk.END).strip().splitlines()
    wafer_no = wafer_text.get().strip()
    pcb_batch = pcb_text.get().strip()

    # Load the PCB count data for fallback
    pcb_count_data = load_pcb_count()

    # Try to get starting number from the Starting No. entry (passed widget)
    start_text = sensor_start_widget.get().strip()
    try:
        start_num = int(start_text)
    except ValueError:
        # Fallback: use temporary or saved PCB count + 1 if starting number invalid
        start_num = temp_pcb_count_data.get(pcb_batch, pcb_count_data.get(pcb_batch, 0)) + 1

    # Prepare list for display
    sensor_id_lines = []

    # Extract parts for the format
    pcb_sheet_no = pcb_batch[:2]   # first two characters of PCB Sheet No.
    wafer_short = wafer_no[:5]     # first five characters of Wafer No.

    for i, ocr_line in enumerate(ocr_lines):
        if i in line_pcb_counts:
            # preserve previously assigned count for this line position
            assigned_count = line_pcb_counts[i]
        else:
            # New line: decide next count
            if line_pcb_counts:
                max_assigned = max(line_pcb_counts.values())
                proposed = start_num + i
                # If proposed would reuse/overlap existing assigned numbers, continue from max_assigned + 1
                if proposed <= max_assigned:
                    assigned_count = max_assigned + 1
                else:
                    assigned_count = proposed
            else:
                # no previous assignments: base on start_num + index
                assigned_count = start_num + i

            line_pcb_counts[i] = assigned_count

        # two-digit formatted count (wraps at 100 -> 00)
        ocr_count_formatted = f"{(assigned_count % 100):02}"

        # last 6 characters of the OCR line
        ocr_last_6 = ocr_line[-6:]

        sensor_id = f"{pcb_sheet_no}-{ocr_count_formatted}-{wafer_short}-{ocr_last_6}"
        sensor_id_lines.append(sensor_id)

    # Display updated Sensor IDs
    sensor_id_text.config(state='normal')
    sensor_id_text.delete('1.0', tk.END)
    sensor_id_text.insert('1.0', '\n'.join(sensor_id_lines))
    sensor_id_text.config(state='disabled')

    # Update the Quantity textbox with the number of Sensor IDs
    quantity_name_text.config(state='normal')
    quantity_name_text.delete(0, tk.END)
    quantity_name_text.insert(0, str(len(ocr_lines)))
    quantity_name_text.config(state='disabled')

    # Temporarily save the highest assigned count for this PCB batch so it can be persisted later
    if line_pcb_counts:
        temp_pcb_count_data[pcb_batch] = max(line_pcb_counts.values())
    else:
        temp_pcb_count_data[pcb_batch] = temp_pcb_count_data.get(pcb_batch, pcb_count_data.get(pcb_batch, 0))

    previous_line_count = len(ocr_lines)

# Function to bind focusout event to the textboxes
def bind_focusout_event(widget, ocr_text, wafer_text, pcb_text, sensor_id_text):
    widget.bind('<FocusOut>', lambda event: update_sensor_id(ocr_text, wafer_text, pcb_text, sensor_id_text))

def update_datetime(date_name_text):
    if date_name_text.winfo_exists():  # Check if the widget still exists
        current_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        date_name_text.config(state='normal')
        date_name_text.delete('1.0', tk.END)
        date_name_text.insert(tk.END, current_time)
        date_name_text.config(state='disabled')
        date_name_text.after(1000, update_datetime, date_name_text)  # Update every second

def disable_fields():
    # Disable all textboxes and comboboxes except Date Created Textbox, Lot Number Textbox, and Sensor ID Textbox
    quantity_name_text.config(state='disabled')
    created_name_text.config(state='disabled')
    details_name_text.config(state='disabled')
    wafer_no_text.config(state='disabled')
    ocr_text.config(state='disabled')
    pcb_batch_text.config(state='disabled')
    sensor_start_text.config(state='disabled')
    project_combobox.config(state='disabled')
    condition_combobox.config(state='disabled')
    cable_combobox.config(state='disabled')
    length_combobox.config(state='disabled')
    coil_combobox.config(state='disabled')
    series_text.config(state='disabled')
    board_combobox.config(state='disabled')
    resin_combobox.config(state='disabled')
    cost_charging_combobox.config(state='disabled')

def enable_fields():
    # Enable all textboxes and comboboxes except Date Created Textbox, Lot Number Textbox, and Sensor ID Textbox
    created_name_text.config(state='normal')
    details_name_text.config(state='normal')
    wafer_no_text.config(state='normal')
    ocr_text.config(state='normal')
    pcb_batch_text.config(state='normal')
    sensor_start_text.config(state='normal')
    project_combobox.config(state='readonly')
    condition_combobox.config(state='readonly')
    cable_combobox.config(state='readonly')
    length_combobox.config(state='readonly')
    coil_combobox.config(state='readonly')
    series_text.config(state='readonly')
    resin_combobox.config(state='readonly')
    cost_charging_combobox.config(state='readonly')
    board_combobox.config(state='readonly')
    create_button.config(state='normal')  # Enable Create button

def clear_fields():
    global previous_line_count
    
    enable_fields()  # Enable fields as part of the clear operation
    ocr_text.delete('1.0', tk.END)
    quantity_name_text.config(state='normal')
    quantity_name_text.delete(0, tk.END)
    quantity_name_text.insert(0, "0")  # Set initial value to zero
    quantity_name_text.config(state='disabled')
    pcb_batch_text.delete(0, tk.END)
    sensor_start_text.delete(0, tk.END)
    details_name_text.delete('1.0', tk.END)
    wafer_no_text.delete(0, tk.END)
    sensor_id_text.config(state='normal')
    sensor_id_text.delete('1.0', tk.END)
    sensor_id_text.config(state='disabled')
    lot_name_text.config(state='normal')
    lot_name_text.delete('1.0', tk.END)
    lot_name_text.config(state='disabled')
    product_text.config(state='normal')
    product_text.delete('1.0', tk.END)
    product_text.config(state='disabled')
    created_name_text.delete(0, tk.END)
    project_combobox.set('')
    coil_combobox.set('')
    cable_combobox.set('')
    length_combobox.set('')
    condition_combobox.set('')
    board_combobox.set('')
    resin_combobox.set('')
    cost_charging_combobox.set('')
    
    # Revert PCB count to the last saved count only if not updated after creation
    pcb_count_data = load_pcb_count()
    temp_pcb_count_data.clear()
    temp_pcb_count_data.update(pcb_count_data)
    
    # Reset the previous line count
    previous_line_count = 0
    generate_next_series() # Generate a new series number on clear

def validate_fields():
    if not project_combobox.get():
        return False
    if not quantity_name_text.get().strip():
        return False
    if not condition_combobox.get():
        return False
    if not cable_combobox.get():
        return False
    if not length_combobox.get():
        return False
    if not coil_combobox.get():
        return False
    if not wafer_no_text.get().strip():
        return False
    if not series_text.get():
        return False
    if not created_name_text.get().strip():
        return False
    if condition_combobox.get() == "Eval" and not details_name_text.get('1.0', tk.END).strip():
        return False
    return True

# Define the perform_printing function (extracted and slightly renamed from original open_image_and_copy_option)
def perform_printing(traveller_file_path, preview_window=None):
    # This part contains the original printing logic from open_image_and_copy_option
    # It maintains the high DPI for quality printing.
    img_to_print = Image.open(traveller_file_path)

    # Original resizing for printing (keep this as is for high-quality print)
    dpi = 300
    width_cm = 100
    height_cm = 60
    width_px = int(width_cm * dpi / 25.4)
    height_px = int(height_cm * dpi / 25.4)
    img_to_print = img_to_print.resize((width_px, height_px), RESAMPLE_LANCZOS)

    try:
        printer_name = win32print.GetDefaultPrinter()
        hdc = win32ui.CreateDC()
        hdc.CreatePrinterDC(printer_name)

        hdc.StartDoc("Image Print")
        hdc.StartPage()

        dib = ImageWin.Dib(img_to_print)
        printable_area = hdc.GetDeviceCaps(8), hdc.GetDeviceCaps(10)
        dib.draw(hdc.GetHandleOutput(), (0, 0, printable_area[0], printable_area[1]))

        hdc.EndPage()
        hdc.EndDoc()
        hdc.DeleteDC()

        # Show the info dialog (this is modal). After user clicks OK, destroy preview if present.
        messagebox.showinfo("Printed", "Image sent to printer successfully.")
        if preview_window is not None and preview_window.winfo_exists():
            preview_window.destroy()

    except Exception as e:
        # On error show message; optionally close the preview as well if you want
        messagebox.showerror("Error", f"An error occurred while printing: {e}")

# Modified open_image_and_copy_option to show a preview window
def open_image_and_copy_option(traveller_file_path):
    # Create a Toplevel window for displaying the image preview
    preview_window = Toplevel()
    preview_window.title("Traveller Image Preview")

    # Load the image from the path
    img_original = Image.open(traveller_file_path)

    # Determine a suitable display size (e.g., scale to fit screen, or a fixed small size)
    # Let's aim for a maximum height of 600 pixels for preview
    max_display_height = 400
    original_width, original_height = img_original.size

    # Calculate new dimensions for display, maintaining aspect ratio
    if original_height > max_display_height:
        aspect_ratio = original_width / original_height
        display_height = max_display_height
        display_width = int(display_height * aspect_ratio)
        img_display = img_original.resize((display_width, display_height), RESAMPLE_LANCZOS)
    else:
        img_display = img_original # If already small enough, use original size for display

    # Convert PIL Image to Tkinter PhotoImage
    photo = ImageTk.PhotoImage(img_display)

    # Create a Label to display the image in the preview window
    image_label = tk.Label(preview_window, image=photo)
    image_label.image = photo  # Keep a reference to prevent garbage collection
    image_label.pack(padx=10, pady=10)

    # Add a button to trigger the actual printing
    print_button = tk.Button(preview_window, text="Print Traveller", font=("Tahoma", 12, "bold"), bg="#4CAF50", fg="white",
                              command=lambda: perform_printing(traveller_file_path, preview_window))
    print_button.pack(pady=5)


def new_entry():
    global line_pcb_counts
    enable_fields()  # Enable fields as part of the clear operation
    ocr_text.delete('1.0', tk.END)
    quantity_name_text.config(state='normal')
    quantity_name_text.delete(0, tk.END)
    quantity_name_text.insert(0, "0")  # Set initial value to zero
    quantity_name_text.config(state='disabled')
    pcb_batch_text.delete(0, tk.END)
    sensor_start_text.delete(0, tk.END)
    details_name_text.delete('1.0', tk.END)
    wafer_no_text.delete(0, tk.END)
    sensor_id_text.config(state='normal')
    sensor_id_text.delete('1.0', tk.END)
    sensor_id_text.config(state='disabled')
    lot_name_text.config(state='normal')
    lot_name_text.delete('1.0', tk.END)
    lot_name_text.config(state='disabled')
    product_text.config(state='normal')
    product_text.delete('1.0', tk.END)
    product_text.config(state='disabled')
    created_name_text.delete(0, tk.END)
    project_combobox.set('')
    coil_combobox.set('')
    cable_combobox.set('')
    length_combobox.set('')
    condition_combobox.set('')
    board_combobox.set('')
    resin_combobox.set('')
    cost_charging_combobox.set('')
    clear_button.config(state='normal')
    line_pcb_counts.clear()
    generate_next_series() # Generate a new series number on new entry
    
def create_traveller(traveller_file_path):
    # Define dimensions in pixels for 100mm x 62mm at 300 DPI
    dpi = 600
    image_width = int(100 / 25.4 * dpi)  # ≈ 1181 pixels / 2362 for 600
    image_height = int(60 / 25.4 * dpi)  # ≈ 732 pixels / 1465 for 600
    background_color = "white"
    line_color = "black"
    font_color = "black"

    # Create a new image with a white background
    image = Image.new("RGB", (image_width, image_height), background_color)
    draw = ImageDraw.Draw(image)

    # Define font (adjust font size or use a specific path to a TTF font if needed)
    try:
        font = ImageFont.truetype("arialbd.ttf", 50)  # Larger font for higher resolution
    except IOError:
        font = ImageFont.load_default()

    # Define the coordinates for each cell (adjusted to fit the new size)
    # left, top, right, bottom
    cell_positions = {
        "Project:": (60, 5, 952, 137),
        "Lot Number:": (60, 135, 952, 407),
        "Condition:": (60, 405, 952, 547),
        "Coil Connection:": (60, 545, 952, 687),
        "Board Connection:": (60, 685, 952, 827),
        "Cable Type:": (60, 825, 952, 967),
        "Cable Length(m):": (60, 965, 952, 1107),
        "Resin Used:": (60, 1105, 952, 1247),
        "Date Created:": (60, 1245, 952, 1400),
        "Details:": (950, 5, 1762, 827),
        "Wafer Number:": (950, 825, 1762, 967),
        "PCB Sheet No.:": (950, 965, 1762, 1107),
        "Quantity:": (950, 1105, 1762, 1247),
        "Created by:": (950, 1245, 1762, 1400),
        "Sensor List:": (1760, 5, 2310, 1400)
    }
    
    # Draw rectangles and add text for each cell
    for label, (x1, y1, x2, y2) in cell_positions.items():
        # Draw the cell border
        draw.rectangle([x1, y1, x2, y2], outline=line_color, width=4)
        # Draw the text
        draw.text((x1 + 10, y1 + 10), label, fill=font_color, font=font)

    # Save the image with 300 DPI to maintain 100mm x 62mm size
    image.save(traveller_file_path, dpi=(dpi, dpi))

    print("Image template created and saved as template_image.png with 100mm x 62mm dimensions at 300 DPI.")
    
# This code was generated by TDK ChatGPT 
def create_lot_masterlist():
    if not validate_fields():
        messagebox.showwarning("Input Required", "Please fill in all fields.")
        return
    project = project_combobox.get()
    lot_name1 = lot_name_text.get('1.0', tk.END).strip()
    sensor_ids = [s.strip() for s in sensor_id_text.get("1.0", tk.END).splitlines() if s.strip()] # Get non-empty lines
    resin_used = resin_combobox.get().strip()
    quantity = quantity_name_text.get().strip()
    condition = condition_combobox.get()
    cable_type = cable_combobox.get()
    length = length_combobox.get()
    coil = coil_combobox.get()
    board = board_combobox.get()
    wafer = wafer_no_text.get()
    date_created = datetime.now()
    created_by = created_name_text.get().strip()
    product_description = product_text.get('1.0', tk.END).strip()
    pcb_batch = pcb_batch_text.get().strip()
    details = details_name_text.get('1.0', tk.END).strip()
    
    # Save the final count for the PCB batch in temporary data
    current_count = temp_pcb_count_data.get(pcb_batch, 0)
    pcb_count_data = load_pcb_count()
    pcb_count_data[pcb_batch] = current_count  # Update the saved count
    
    # Generate the QR code for the lot_name1
    lot_qr_data = f"{lot_name1}"  # Combine file path and lot name
    lot_qr_code = qrcode.make(lot_qr_data)
    lot_qr_code = lot_qr_code.resize((265, 265))  # Adjust size as needed
    lot_qr_pos = (673,138)

    if not lot_name1:
        messagebox.showwarning("Input Required", "Please enter the Lot Name.")
    elif not sensor_ids:
        messagebox.showwarning("Input Required", "Please enter Sensor IDs.")
    else:
        base_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking"
        year = datetime.now().strftime("%Y")
        month = datetime.now().strftime("%B")
        day_folder = datetime.now().strftime("%m.%d.%Y")
        day_path = os.path.join(base_path, year, month, day_folder)
        
        os.makedirs(day_path, exist_ok=True)

        filename = f"{lot_name1}.txt"
        file_path = os.path.join(day_path, filename)

        try:
            # Open the text file for writing
            with open(file_path, 'w') as file:
                # Write header row
                file.write("Sensor IDs\n")
                
                # Write data rows
                for sensor_id in sensor_ids:
                    formatted_date = date_created.strftime("%m/%d/%Y %I:%M %p")
                    file.write(f"{sensor_id}\n")
                    insert_into_database(project, lot_name1, sensor_id, wafer, pcb_batch, condition, cable_type, length, coil, formatted_date, created_by, product_description)
                    # choose current_process based on condition (trim / handle case just in case)
                    cond = (condition or "").strip()
                    if cond == "Eval":
                        current_process = "Evaluation"
                    else:
                        current_process = "Laser Marking and OCR"
                    
                    insert_into_lot_tracking(lot_name1, sensor_id, file_path, current_process, quantity, quantity, formatted_date, created_by)

            # Update the PCB count data and save it
            pcb_count_data.update({pcb_batch: pcb_count_data.get(pcb_batch, 0)})
            save_pcb_count(pcb_count_data)

            print(f"Updated PCB count for batch {pcb_batch}: {pcb_count_data.get(pcb_batch, 0)}")

            traveller_filename = f"{lot_name1}.png"
            traveller_file_path = os.path.join(r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\Traveller", traveller_filename)            

            create_traveller(traveller_file_path)

            # Load the template image
            template_path = traveller_file_path  # Path to your template image
            image = Image.open(template_path)

            # Prepare to draw text
            draw = ImageDraw.Draw(image)
            font_path = "tahoma.ttf"  # You can also specify the full path to the .ttf file if needed
            font_size = 55
            font = ImageFont.truetype(font_path, font_size)
            
            # Specify text and its coordinates (adjust based on your template)
            text_data = {
                "Project": (300, 60),
                "Lot Number": (69, 325),
                "Condition": (300, 460),
                "Coil Connection": (300, 610),
                "Board Connection": (300, 750),
                "Cable Type": (300, 890),
                "Cable Length": (300, 1020),
                "Resin Used": (300, 1170),
                "Date Created": (300, 1320),
                "Details": (1000, 80),
                "Wafer Number": (1000, 895),
                "PCB Sheet Number": (1000, 1030),
                "Quantity": (1000, 1170),
                "Created by": (1000, 1315),
                "Sensor IDs": (1775, 70)
                }

            # Draw text on the image
            draw.text(text_data["Project"], project, fill="black", font=font)
            draw.text(text_data["Lot Number"], lot_name1, fill="black", font=ImageFont.truetype("arial.ttf", 60))
            draw.text(text_data["Resin Used"], resin_used, fill="black", font=font)
            draw.text(text_data["PCB Sheet Number"], pcb_batch, fill="black", font=font)
            draw.text(text_data["Quantity"], quantity, fill="black", font=font)
            draw.text(text_data["Condition"], condition, fill="black", font=font)
            draw.text(text_data["Cable Type"], cable_type, fill="black", font=font)
            draw.text(text_data["Cable Length"], length, fill="black", font=font)
            draw.text(text_data["Coil Connection"], coil, fill="black", font=font)
            draw.text(text_data["Board Connection"], board, fill="black", font=font)
            draw.text(text_data["Wafer Number"], wafer, fill="black", font=font)
            draw.text(text_data["Date Created"], date_created.strftime("%Y-%m-%d %I:%M %p"), fill="black", font=ImageFont.truetype('arial.ttf', 50))
            draw.text(text_data["Created by"], created_by, fill="black", font=ImageFont.truetype('arial.ttf', 50))
            
            # Wrap the text within a specified width
            wrapped_text = textwrap.wrap(details, width=20)  # Adjust the width as needed

            # Draw the wrapped text on the image
            draw.multiline_text(text_data["Details"], "\n".join(wrapped_text), fill="black", font=ImageFont.truetype('arial.ttf', 55))

            # Concatenate all sensor IDs as a single string and draw on the image
            sensor_ids_text = "\n".join(sensor_ids)
            draw.text(text_data["Sensor IDs"], sensor_ids_text, fill="black", font=ImageFont.truetype('arial.ttf',55))

            image.paste(lot_qr_code, lot_qr_pos)

            # Save the new image with details
            dpi = 600
            #image_output_path = (traveller_file_path)
            #image.resize((int(100 * 300), int(62 * 300)), PIL.Image.Resampling.LANCZOS)
            image.save(traveller_file_path, dpi=(dpi, dpi))
            
            selected_series = series_text.get()
            add_used_series(selected_series)

            disable_fields()  # Disable input on all textboxes after creation
            create_button.config(state='disabled')  # Disable Create button
            clear_button.config(state='disabled')  # Enable Create button
            #messagebox.showinfo("Success", f"File '{filename}' created successfully in folder '{day_path}'.")

            # Print the image with A4 paper and top position
            #image.print(printer=None, dpi=300)  # Adjust DPI as needed
            
            # Open the generated image in a pop-up with print option
            open_image_and_copy_option(traveller_file_path)

        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")

def insert_into_database(project, lot_number, sensor_id, wafer_number, pcb_batch, condition, cable_type, cable_length, coil_connection, created_date, created_by, product_description):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO lot_masterlist (project, lot_number, sensor_id, wafer_number, pcb_batch, condition, cable_type, cable_length, coil_connection, created_date, created_by, product_description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (project, lot_number, sensor_id, wafer_number, pcb_batch, condition, cable_type, cable_length, coil_connection, created_date, created_by, product_description))
    conn.commit()
    conn.close()

# Define the abbreviations based on the provided context
project_abbr = {
    "Nivio": "NV",
    "Nivio-S": "NS",
    "Migne Horizontal": "MH",
    "Migne Vertical": "MV",
    "Gen2": "G2",
}

coil_connection_abbr = {
    "Out coil": "B",
    "Thin film": "T"
}

cable_type_abbr = {
    "Oki": "K",
    "Taiyo": "T"
}

cable_length_abbr = {
    "0.1m": "01",
    "1.5m": "15",
    "2.9m": "29",
    "Other Length": "XX"
}

condition_abbr = {
    "MP": "M",
    "Eval": "E"
}

product_abbr = {
    "Nivio": "N",
    "Nivio-S": "S",
    "Migne Horizontal": "M",
    "Migne Vertical": "M",
    "Gen2": "G",
}

prod_coil_abbr = {
    "Out coil": "B",
    "Thin film": "C",
}

coil_compen_abbr = {
    "Out coil": "B",
    "Thin film": "T",
}

prod_cable_length_abbr = {
    "1.5m": "D",
    "2.9m": "E",
    "Other Length": "F"
}

sensor_conn_abbr = {
    "Nivio": "D",
    "Nivio-S": "D",
    "Migne Horizontal": "H",
    "Migne Vertical": "V",
    "Gen2": "D",
}

board_conn_abbr = {
    "Direct Solder": "D",
    "Connector": "C",
}

prod_cond_abbr = {
    "MP": "C",
    "Eval": "S"
}

cable_dir_abbr = {
    "Nivio": "H",
    "Nivio-S": "H",
    "Migne Horizontal": "H",
    "Migne Vertical": "V",
    "Gen2": "H",
}

costing_abbr = {
    "FOC": "F",
    "Paid by Mag BG": "C",
    "Profit with PO from Customer": "P",
}

# Function to generate the concatenated value
def generate_concatenated_value(project, coil_connection, cable_type, cable_lengths, condition, series):
    # Get the current date
    now = datetime.now()

    # Extract the required date components
    year = now.year % 100  # Last two digits of the year
    month = now.month
    day = now.day %100

    # Convert month to the required format
    if month <= 9:
        month_str = str(month)
    else:
        month_str = chr(55 + month)  # Convert 10, 11, 12 to A, B, C
 
    day_str = f"{day:02}"

    # Get the abbreviations
    project_char = project_abbr.get(project, "XX")
    coil_connection_char = coil_connection_abbr.get(coil_connection, "X")
    cable_type_char = cable_type_abbr.get(cable_type, "X")
    cable_length_char = cable_length_abbr.get(cable_lengths, "XX")
    condition_char = condition_abbr.get(condition, "X")

    # Concatenate the values
    concatenated_value = (
        f"{project_char}{year:02}{month_str}{day_str}{coil_connection_char}"
        f"{cable_type_char}{cable_length_char}{condition_char}{series}XX"
    )
    return concatenated_value

# Function to generate the product description
def generate_product_description(project, coil_connection, cable_type, cable_lengths, costing):

    # Get the abbreviations
    product_char = product_abbr.get(project, "X")

    if project == "Migne Horizontal" or "Migne Vertical":
        coil_compen_char = coil_compen_abbr.get(coil_connection, "X")
    elif project == "Nivio" or "Nivio-S":
        coil_compen_char = "B"
    
    cable_dir_char = cable_dir_abbr.get(project, "X")    
    cable_length_char = cable_length_abbr.get(cable_lengths, "XX")   
    costing_char = costing_abbr.get(costing, "X")
    
    
    # Concatenate the values
    product_value = (
        f"MAGS-{product_char}{cable_length_char}"
        f"{cable_dir_char}-A{coil_compen_char}000{costing_char}"
    )
    
    return product_value

def create_gui():
    global lot_name_text, sensor_id_text, project_combobox, coil_combobox, cable_combobox, length_combobox
    global condition_combobox, series_text, board_combobox, resin_combobox, cost_charging_combobox 
    global quantity_name_text, wafer_no_text, created_name_text, product_text, details_name_text, ocr_text 
    global pcb_batch_text, sensor_start_text, pcb_count_data, clear_button, create_button

    # Clear the PCB count data at the beginning of a new session
    pcb_count_data = {}
    
    root = tk.Tk()
    root.title("BMS Lot Entry System")
    # Make room for the camera to the right
    root.geometry("1150x380")
    root.configure(bg='#3366cc')
    
    # Disable maximize functionality
    root.resizable(False, False)

    title_label = tk.Label(root, text="BMS Lot Entry", font=("BiomeW04-Bold", 25, "bold"), bg="#3366cc", fg="orange")
    title_label.place(x=10, y=0)

    # Dropdown values from your table
    projects = ["Nivio", "Nivio-S", "Migne Horizontal", "Migne Vertical", "Gen2"]
    coil_connections = ["Out coil", "Thin film"]
    cable_types = ["Oki", "Taiyo"]
    cable_lengths = ["0.1m", "1.5m", "2.9m", "Other Length"]
    conditions = ["MP", "Eval"]
    board_connections = ["Direct Solder", "Connector"]
    resin_type = ["U422", "NEA123S"]
    costing = ["FOC", "Paid by Mag BG", "Profit with PO from Customer"]

    def create_combobox(root, values, x, y, width=20):
        combobox = ttk.Combobox(root, values=values, width=width, state='readonly')
        combobox.place(x=x, y=y)
        combobox.bind('<<ComboboxSelected>>', lambda event: update_lot_name_text())
        return combobox

    project_label = tk.Label(root, text='Project:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    project_label.place(x=10, y=50)
    project_combobox = create_combobox(root, projects, 130, 50, width=26)

    condition_label = tk.Label(root, text='Condition:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    condition_label.place(x=10, y=80)
    condition_combobox = create_combobox(root, conditions, 130, 80, width=26)
    
    coil_label = tk.Label(root, text='Coil Connection:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    coil_label.place(x=10, y=110)
    coil_combobox = create_combobox(root, coil_connections, 130, 110, width=26)
    
    board_label = tk.Label(root, text='Board Conn:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    board_label.place(x=10, y=140)
    board_combobox = create_combobox(root, board_connections, 130, 140, width=26)
    
    cable_label = tk.Label(root, text='Cable Type:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    cable_label.place(x=10, y=170)
    cable_combobox = create_combobox(root, cable_types, 130, 170, width=26)
    
    length_label = tk.Label(root, text='Cable Length:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    length_label.place(x=10, y=200)
    length_combobox = create_combobox(root, cable_lengths, 130, 200, width=26)
    
    resin_label = tk.Label(root, text='Resin Type:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    resin_label.place(x=10, y=230)
    resin_combobox = create_combobox(root, resin_type, 130, 230, width=26)
    
    # Date and Time Created Label and Textbox
    date_label = tk.Label(root, text='Date Created:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    date_label.place(x=10, y=260)
    date_name_text = tk.Text(root, width=22, height=1)
    date_name_text.place(x=130, y=260)
    date_name_text.config(state='disabled')

    wafer_no_label = tk.Label(root, text='Wafer No.:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    wafer_no_label.place(x=320, y=20)
    wafer_no_text = tk.Entry(root, width=27)
    wafer_no_text.place(x=430, y=20)
    
    pcb_batch_label = tk.Label(root, text='PCB Sheet No.:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    pcb_batch_label.place(x=320, y=50)
    pcb_batch_text = tk.Entry(root, width=27)
    pcb_batch_text.place(x=430, y=50)

    sensor_start_label = tk.Label(root, text='Starting No.:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    sensor_start_label.place(x=320, y=80)
    sensor_start_text = tk.Entry(root, width=27)
    sensor_start_text.place(x=430, y=80)

    series_label = tk.Label(root, text='Series Number:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    series_label.place(x=320, y=110)
    series_text = tk.Entry(root, width=27) # Changed to Entry widget
    series_text.place(x=430, y=110)
    series_text.config(state='disabled') # Make it read-only

    created_label = tk.Label(root, text='Created by:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    created_label.place(x=320, y=140)
    created_name_text = tk.Entry(root, width=27)
    created_name_text.place(x=430, y=140)
    
    quantity_label = tk.Label(root, text='Quantity:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    quantity_label.place(x=320, y=170)
    quantity_name_text = tk.Entry(root, width=27)
    quantity_name_text.place(x=430, y=170)
    quantity_name_text.insert(0, "0")  # Set initial value to zero
    quantity_name_text.config(state='disabled')

    cost_charging = tk.Label(root, text='Cost Charging:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    cost_charging.place(x=320, y=200)
    cost_charging_combobox = create_combobox(root, costing, 430, 200, width=24)

    lot_label = tk.Label(root, text='Lot Number:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    lot_label.place(x=320, y=230)
    lot_name_text = tk.Text(root, width=20, height=1)
    lot_name_text.place(x=430, y=230)
    lot_name_text.config(state='disabled')

    product_label = tk.Label(root, text='Product Desc:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    product_label.place(x=320, y=260)
    product_text = tk.Text(root, width=20, height=1)
    product_text.place(x=430, y=260)
    product_text.config(state='disabled')

    details_label = tk.Label(root, text='Details:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    details_label.place(x=390, y=280)
    details_name_text = tk.Text(root, width=25, height=4, wrap=tk.WORD)
    details_name_text.place(x=390, y=300)
    details_name_text.configure(spacing1=0)  # Adjust spacing as needed

    ocr_label = tk.Label(root, text='OCR No.:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    ocr_label.place(x=615, y=10)
    ocr_text = tk.Text(root, width=8, height=21)
    ocr_text.place(x=610, y=30)

    chip_ocr_label = tk.Label(root, text='MR Chip OCR No.:', bg='#3366cc', fg='yellow', font=('Arial', 15, 'bold'))
    chip_ocr_label.place(x=910, y=50)

    def limit_lines(event):
        lines = ocr_text.get('1.0', tk.END).split('\n')
        for i, line in enumerate(lines):
            if len(line) > 6:
                ocr_text.delete(f'{i + 1}.6', f'{i + 1}.end')
            line_count = int(ocr_text.index('end-1c').split('.')[0])
            if line_count > 20:
                ocr_text.delete(f'{line_count}.0', tk.END)  # Delete the extra lines
                return "break"  # Prevent further input

    ocr_text.bind('<KeyRelease>', limit_lines)

    def limit_input(event):
        current_line_index = ocr_text.index("insert").split(".")[0]  # Current line number
        current_line = ocr_text.get(f'{current_line_index}.0', f'{current_line_index}.end').strip()
        all_lines = ocr_text.get('1.0', tk.END).strip().split('\n')

        # Exclude the current line when checking for duplicates
        other_lines = [line for idx, line in enumerate(all_lines) if str(idx + 1) != current_line_index]

        # If pressing "Return", check for duplicates
        if event.keysym == "Return":
            if current_line in other_lines:
                # Show warning message
                messagebox.showwarning("Duplicate Entry", "This value has already been entered.")
                # Clear the current line's value
                ocr_text.delete(f'{current_line_index}.0', f'{current_line_index}.end')
                return "break"
            if current_line == "":
                messagebox.showwarning("Empty Entry", "You cannot input an empty value.")
                return "break"

        # Limit length of each line to 6 characters
        if len(current_line) >= 6 and event.keysym not in ('BackSpace', 'Left', 'Right', 'Up', 'Down', 'Return'):
            return "break"

        # Limit number of lines to 20
        if len(all_lines) >= 20 and event.keysym == 'Return':
            messagebox.showwarning("Line Limit", "You cannot add more than 20 lines.")
            return "break"

    ocr_text.bind('<KeyPress>', limit_input)

    sensor_id_label = tk.Label(root, text='Sensor ID:', bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    sensor_id_label.place(x=690, y=10)
    sensor_id_text = tk.Text(root, width=18, height=21)
    sensor_id_text.place(x=690, y=30)
    sensor_id_text.config(state='disabled')
    
    def update_lot_name_text():
        project = project_combobox.get()
        coil_connection = coil_combobox.get()
        cable_type = cable_combobox.get()
        cable_lengths = length_combobox.get()
        condition = condition_combobox.get()
        series = series_text.get() # Get from Entry widget
        costing = cost_charging_combobox.get()

        concatenated_value = generate_concatenated_value(project, coil_connection, cable_type, cable_lengths, condition, series)
        lot_name_text.config(state='normal')
        lot_name_text.delete('1.0', tk.END)
        lot_name_text.insert('1.0', concatenated_value)
        lot_name_text.config(state='disabled')
        
        product_desc_value = generate_product_description(project, coil_connection, cable_type, cable_lengths, costing)
        product_text.config(state='normal')
        product_text.delete('1.0', tk.END)
        product_text.insert('1.0', product_desc_value)
        product_text.config(state='disabled')

    new_button = tk.Button(root, text="New Entry", font=("Tahoma", 16, "bold"), bg="#F45AE9", fg="black", 
                              command=new_entry, padx=5, pady=1, relief='raised', borderwidth=3, height=2)
    new_button.place(x=10, y=300)

    create_button = tk.Button(root, text="Create", font=("Tahoma", 16, "bold"), bg="#32CD32", fg="black", 
                              command=create_lot_masterlist, padx=10, pady=1, relief='raised', borderwidth=3, height=2)
    create_button.place(x=160, y=300)

    clear_button = tk.Button(root, text="Clear", font=("Tahoma", 16, "bold"), bg="#FFD700", fg="black", 
                             command=clear_fields, padx=10, pady=1, relief='raised', borderwidth=3, height=2)
    clear_button.place(x=280, y=300)

    #ocr_text.bind('<Return>', lambda event: update_sensor_id(ocr_text, wafer_no_text, 
    ocr_text.bind('<KeyRelease>', lambda event: update_sensor_id(ocr_text, wafer_no_text, pcb_batch_text, sensor_id_text, sensor_start_text))
    wafer_no_text.bind('<KeyRelease>', lambda event: update_sensor_id(ocr_text, wafer_no_text, pcb_batch_text, sensor_id_text, sensor_start_text))
    pcb_batch_text.bind('<KeyRelease>', lambda event: update_sensor_id(ocr_text, wafer_no_text, pcb_batch_text, sensor_id_text, sensor_start_text))
    sensor_start_text.bind('<KeyRelease>', lambda event: update_sensor_id(ocr_text, wafer_no_text, pcb_batch_text, sensor_id_text, sensor_start_text))
    # Call the update_datetime function to start updating the Date Created field
    update_datetime(date_name_text)
    generate_next_series() # Call to generate the initial series number

    # Camera area on the right
    cam_x = 850
    cam_y = 80
    cam_width = 290
    cam_height = 220

    camera_frame = tk.Frame(root, width=cam_width, height=cam_height, bg="black", relief="sunken", borderwidth=2)
    camera_frame.place(x=cam_x, y=cam_y)

    camera_label = tk.Label(camera_frame)
    camera_label.place(relx=0.5, rely=0.5, anchor="center")

    # Try to open the default camera (index 0). Use CAP_DSHOW on Windows to reduce delays.
    try:
        cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    except Exception:
        cap = cv2.VideoCapture(0)

    # Optionally set capture resolution (camera dependent)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Keep reference to cap so we can release on close
    root.cap = cap

    def update_camera():
        if not getattr(root, "cap", None):
            return
        cap_local = root.cap
        if not cap_local.isOpened():
            # Could show an error frame or text
            camera_label.config(text="Camera not available", image="", fg="white", bg="black")
            return

        ret, frame = cap_local.read()
        if not ret:
            # If no frame captured, show a placeholder text (do not crash)
            camera_label.config(text="No camera frame", image="", fg="white", bg="black")
        else:
            # Convert BGR (OpenCV) -> RGB (PIL)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Convert to PIL Image
            pil_img = Image.fromarray(frame)

            # Resize to fit our camera_frame while preserving aspect ratio
            pil_img.thumbnail((cam_width - 10, cam_height - 10), RESAMPLE_LANCZOS)

            imgtk = ImageTk.PhotoImage(image=pil_img)
            camera_label.imgtk = imgtk  # keep reference
            camera_label.config(image=imgtk, text="")

        # schedule next update (about 30 FPS -> every 33ms; use 15-50ms as desired)
        if root.winfo_exists():
            root.after(33, update_camera)

    # Optional snapshot button (saves an image to disk)
    def take_snapshot():
        if not getattr(root, "cap", None) or not root.cap.isOpened():
            messagebox.showwarning("Camera", "Camera not available.")
            return
        ret, frame = root.cap.read()
        if not ret:
            messagebox.showwarning("Camera", "Failed to grab frame.")
            return
        # Save as RGB PNG (convert BGR -> RGB first)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        save_path = os.path.join(os.getcwd(), f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        img.save(save_path)
        messagebox.showinfo("Snapshot", f"Saved snapshot to:\n{save_path}")

    snap_button = tk.Button(root, text="Snapshot", command=take_snapshot, font=("Tahoma", 10))
    snap_button.place(x=cam_x + 10, y=cam_y + cam_height + 6)

    # Clean exit handler to release camera
    def on_closing():
        try:
            if getattr(root, "cap", None) and root.cap.isOpened():
                root.cap.release()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Start camera updating loop
    update_camera()

    # Call the update_datetime function to start updating the Date Created field
    update_datetime(date_name_text)
    generate_next_series() # Call to generate the initial series number

    root.mainloop()

create_gui()