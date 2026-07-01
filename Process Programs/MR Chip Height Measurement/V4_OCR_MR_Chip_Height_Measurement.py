import tkinter as tk
from tkinter import ttk, messagebox, filedialog, Label, Button, Scale
import sqlite3
import time
import csv
import os
import json
from datetime import datetime

# OCR / camera imports
import cv2
from PIL import Image, ImageFilter, ImageOps, ImageTk
import pytesseract
import threading
import re

# ----- Configuration & paths -----``
# Define the paths to the databases
db_path_tracking = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"
db_path_masterlist = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"

# Define the absolute path to your config.json
config_file_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\process_flow.json"  # Example for Windows

# Image capture temp paths (update if needed)
before_image_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\OCRBefore.png"
save_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\OCRAfter.png"
enhanced_image_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\Enhanced_OCRAfter.png"

# Path to Tesseract executable - UPDATE to your environment if needed
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\a493353\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

# Custom Tesseract configuration
custom_oem_psm_config = (
    '--oem 3 --psm 6 '
    '-c tessedit_char_whitelist="ABCDEFGIJKLMNOPQRSTVWXZ0123456789- "'
)

# UI's expected process name (use the same key used in process_column_mapping/process_to_columns)
UI_PROCESS_NAME = "MR Chip Height Measurement"

# Optional judgement thresholds:
# Set inclusive minimum/maximum. If None, only numeric check is enforced.
HEIGHT_MIN = 2.9
HEIGHT_MAX = 3.1

# Default folder to open automatically when a lot number is entered
DEFAULT_MEASUREMENT_FOLDER = r"\\10.111.8.86\MSetting\ESD-Migne Angle Measurement"

# Load config process_flow
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
root.title("MR Chip Height Measurement")
root.geometry("950x650")
root.configure(bg="lightblue")
root.resizable(False, False)

# Globals
sensor_ids = []         # required sensor IDs for current lot (list of strings)
lot_condition = 'MP'    # default; updated in fetch_lot_info

# Camera/ROI Globals
camera_index = 0
cap = None
threshold_view = False
# Preview dimensions
DISPLAY_W, DISPLAY_H = 400, 300
last_successful_threshold = None  # Store the successful threshold value

# OCR confusion substitutions (help fix common OCR misreads)
OCR_CONFUSIONS = {
    'T': 'J',
    't': 'J',
    'K': 'H',
    'k': 'H',
    'O': '0',
    'o': '0',
    '|': '1',
    'l': '1'
}

def _levenshtein(a, b):
    """Calculate Levenshtein distance between two strings"""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * lb
        for j, cb in enumerate(b, 1):
            insertions = prev[j] + 1
            deletions = cur[j - 1] + 1
            substitutions = prev[j - 1] + (0 if ca == cb else 1)
            cur[j] = min(insertions, deletions, substitutions)
        prev = cur
    return prev[lb]


def _apply_confusions(s: str) -> str:
    if not s:
        return s
    out = []
    for ch in s:
        out.append(OCR_CONFUSIONS.get(ch, ch))
    return ''.join(out)

# ---------- Utility OCR & DB helpers ----------
def get_lot_condition(lot_number):
    """Return lot condition from masterlist DB or default 'MP'."""
    default = "MP"
    try:
        conn = sqlite3.connect(db_path_masterlist)
        cur = conn.cursor()
        for colname in ('"Condition"', 'Condition', 'condition', 'LotCondition', 'lot_condition'):
            try:
                cur.execute(f"SELECT {colname} FROM lot_masterlist WHERE lot_number = ? LIMIT 1", (lot_number,))
                res = cur.fetchone()
                if res and res[0] is not None:
                    conn.close()
                    return str(res[0]).strip()
            except sqlite3.OperationalError:
                continue
        conn.close()
    except sqlite3.Error:
        pass
    return default

def get_valid_sensor_ids_for_lot(lot_number):
    try:
        conn = sqlite3.connect(db_path_tracking)
        cur = conn.cursor()
        cur.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
        res = [r[0] for r in cur.fetchall()]
        conn.close()
        return res
    except sqlite3.Error:
        return []

def perform_ocr_on_pil_image(pil_img, threshold):
    """
    Perform OCR on PIL image with regex pattern matching for sensor IDs.
    Pattern: XX-XX-XXXXX-XXXXXX (e.g., 01-02-ABCDE-123456)
    """
    try:
        img = pil_img.convert("L")
        
        # Upscale for better OCR
        scale_factor = 2.0
        new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
        try:
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        except AttributeError:
            img = img.resize(new_size, Image.LANCZOS)
        
        img = img.filter(ImageFilter.SHARPEN)
        img = img.point(lambda p: 255 if p > threshold else 0)
        
        ocr_result = pytesseract.image_to_string(img, config=custom_oem_psm_config)

        # Apply basic character corrections
        ocr_result = ocr_result.replace("O", "0").replace("D", "0").replace("I", "1")\
                               .replace("l", "1").replace("S", "5").replace("Z", "2")\
                               .replace("B", "8").replace("G", "6").replace("|", "1")

        # Also apply confusion substitutions to help fix common OCR mistakes
        try:
            ocr_conf_applied = _apply_confusions(ocr_result)
        except Exception:
            ocr_conf_applied = ocr_result

        # Regex pattern for sensor ID: XX-XX-XXXXX-XXXXXX
        pattern = r'\b(\d{2})-(\d{2})-([A-Z0-9]{4,5}[A-Z]?)-(\d{6})\b'
        matches = re.findall(pattern, ocr_conf_applied.upper())

        if matches:
            sensor_id = f"{matches[0][0]}-{matches[0][1]}-{matches[0][2]}-{matches[0][3]}"
            print(f"[OCR] Regex matched sensor ID: {sensor_id}")
            return sensor_id

        # Fallback: return cleaned OCR text with confusions applied
        return ocr_conf_applied.strip()
    except Exception as exc:
        print("OCR error:", exc)
        return ""

# ---------- Video & rectangle handling ----------
def start_camera():
    global cap
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        messagebox.showerror("Error", "Could not open camera.")
    else:
        show_frame()

def show_frame():
    global cap
    if not cap:
        return
    ret, frame = cap.read()
    if not ret or frame is None:
        video_label.after(100, show_frame)
        return
    frame_disp = cv2.resize(frame, (DISPLAY_W, DISPLAY_H))
    if threshold_view:
        gray = cv2.cvtColor(frame_disp, cv2.COLOR_BGR2GRAY)
        th = threshold_scale.get()
        _, thr = cv2.threshold(gray, th, 255, cv2.THRESH_BINARY)
        frame_to_display = cv2.cvtColor(thr, cv2.COLOR_GRAY2BGR)
    else:
        frame_to_display = frame_disp
    
    img = Image.fromarray(cv2.cvtColor(frame_to_display, cv2.COLOR_BGR2RGB))
    imgtk = ImageTk.PhotoImage(image=img)
    video_label.imgtk = imgtk
    video_label.configure(image=imgtk)
    video_label.after(10, show_frame)

# ---------- OCR capture with retry (restores original threshold) ----------
def capture_image_and_process():
    if not cap or not cap.isOpened():
        messagebox.showerror("Error", "Camera is not open.")
        return
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(before_image_path, frame)
        threading.Thread(target=process_image_for_ocr_with_retries, daemon=True).start()
    else:
        messagebox.showerror("Error", "Failed to capture image.")

def process_image_for_ocr_with_retries():
    """
    OPTIMIZED: Process full image with regex pattern detection and enhanced error messages.
    No manual cropping needed - automatically finds sensor ID anywhere in the image.
    """
    global threshold_view, last_successful_threshold
    try:
        if not cap or not cap.isOpened():
            root.after(0, lambda: messagebox.showerror("Error", "Camera is not open."))
            return

        # Get lot number and fetch valid sensor IDs FIRST
        lot_number = entries["Lot Number:"].get().strip()
        if not lot_number:
            root.after(0, lambda: messagebox.showwarning("Input Error", "Please enter a Lot Number first."))
            return

        # Get valid sensor IDs for this lot
        valid_ids = get_valid_sensor_ids_for_lot(lot_number)
        if not valid_ids:
            root.after(0, lambda: messagebox.showwarning("Database Error", f"No sensor IDs found for lot number {lot_number}."))
            return

        # Check for already scanned sensors
        already_scanned = []
        for row in range(20):
            scanned_id = data_entry[row][0].get().strip()
            if scanned_id:
                already_scanned.append(scanned_id)

        # Filter out already scanned sensors
        remaining_sensor_ids = [sid for sid in valid_ids if sid not in already_scanned]

        if not remaining_sensor_ids:
            root.after(0, lambda: messagebox.showinfo("Complete", "All sensors for this lot have been scanned."))
            return

        print(f"Remaining sensors to scan: {len(remaining_sensor_ids)}")

        # Read one fresh frame
        ret, frame = cap.read()
        if not ret or frame is None:
            root.after(0, lambda: messagebox.showerror("Error", "Failed to capture image."))
            return

        # Convert to PIL for processing
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        # Optional: Resize large images for faster processing
        max_width = 1500
        if image.width > max_width:
            scale = max_width / image.width
            new_size = (int(image.width * scale), int(image.height * scale))
            try:
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            except AttributeError:
                image = image.resize(new_size, Image.LANCZOS)

        # Switch to threshold view for visual feedback
        original_view = threshold_view
        threshold_view = True

        # Determine threshold attempts
        if last_successful_threshold is not None and already_scanned:
            current_threshold = last_successful_threshold
            threshold_scale.set(current_threshold)
            print(f"Using last successful threshold: {current_threshold}")
            threshold_attempts = [current_threshold]
        else:
            current_threshold = threshold_scale.get()
            print(f"Starting OCR with current threshold: {current_threshold}")
            # Try only 5 thresholds (faster)
            threshold_attempts = [current_threshold, current_threshold - 10, current_threshold + 10,
                                 current_threshold - 20, current_threshold + 20]
            threshold_attempts = [max(110, min(200, t)) for t in threshold_attempts]

        ocr_result = ""
        last_detected_pattern = None

        # Try each threshold value
        for attempt_num, threshold_value in enumerate(threshold_attempts, 1):
            print(f"[Attempt {attempt_num}] Trying threshold: {threshold_value}")

            # Update threshold slider visually
            if attempt_num % 3 == 1:
                threshold_scale.set(threshold_value)
                root.update_idletasks()

            # Process image with current threshold
            ocr_raw = perform_ocr_on_pil_image(image, threshold_value)

            # Check if OCR returned a sensor ID (from regex match)
            if ocr_raw:
                # Always store detected pattern for error messages
                last_detected_pattern = ocr_raw
                
                if ocr_raw in remaining_sensor_ids:
                    print(f"[OCR] ✓ Pattern detected: {ocr_raw} - CORRECT (valid for this lot)")
                    print(f"✓ Success! Sensor ID '{ocr_raw}' detected at threshold {threshold_value}")
                    threshold_scale.set(threshold_value)
                    last_successful_threshold = threshold_value
                    ocr_result = ocr_raw
                    break
                elif ocr_raw in already_scanned:
                    print(f"[OCR] ✓ Pattern detected: {ocr_raw} - INCORRECT (already scanned)")
                elif ocr_raw in valid_ids:
                    print(f"[OCR] ✓ Pattern detected: {ocr_raw} - INCORRECT (not in remaining list)")
                else:
                    print(f"[OCR] ✓ Pattern detected: {ocr_raw} - INCORRECT (wrong lot)")

                # Try simple confusion substitutions (T->J, K->H, etc.)
                mapped = _apply_confusions(ocr_raw)
                if mapped != ocr_raw and mapped in remaining_sensor_ids:
                    print(f"[OCR] Mapped '{ocr_raw}' -> '{mapped}' and matched remaining IDs")
                    threshold_scale.set(threshold_value)
                    last_successful_threshold = threshold_value
                    ocr_result = mapped
                    break

                # Fuzzy match: compare ocr_raw and its mapped variant against remaining IDs
                best_match = None
                best_dist = None
                for variant in (ocr_raw, mapped):
                    vstr = variant.replace('-', '')
                    for rid in remaining_sensor_ids:
                        d = _levenshtein(vstr, rid.replace('-', ''))
                        if best_dist is None or d < best_dist:
                            best_dist = d
                            best_match = (rid, d, variant)

                # Accept small edit distances (3 or less)
                if best_match and best_match[1] <= 3:
                    matched_id = best_match[0]
                    print(f"[OCR] ~ Fuzzy matched '{best_match[2]}' -> '{matched_id}' (dist={best_match[1]})")
                    ocr_result = matched_id
                    threshold_scale.set(threshold_value)
                    last_successful_threshold = threshold_value
                    break

            time.sleep(0.05)

        # Restore original view mode
        threshold_view = original_view

        # Check if OCR result is valid
        if ocr_result not in remaining_sensor_ids:
            print("✗ No valid sensor ID from this lot detected")

            # Determine the specific error and show appropriate message
            if not ocr_result or ocr_result == "":
                # No direct valid result. If we detected a pattern earlier, surface it to the user.
                if last_detected_pattern:
                    ocr_result = last_detected_pattern
                    print(f"✗ No valid remaining sensor, but OCR detected pattern: {ocr_result}")
                else:
                    # No detection at all
                    print("✗ No sensor ID pattern detected")
                    root.after(0, lambda: messagebox.showerror("No OCR Output Detected",
                                   "❌ OCR could not detect any sensor ID.\n\n"
                                   "Possible issues:\n"
                                   "• Camera focus is blurry\n"
                                   "• Poor lighting conditions\n"
                                   "• Sensor ID not visible in frame\n"
                                   "• Text is too small or unclear\n\n"
                                   "Please adjust camera and try again."))
                    
                    def clear_textbox():
                        sensor_id_textbox.delete("1.0", tk.END)
                        sensor_id_textbox.config(bg="white")
                    root.after(0, clear_textbox)
                    return

            # Now check what type of error it is
            if ocr_result in already_scanned:
                # Already scanned in this session
                print(f"✗ Sensor ID '{ocr_result}' already scanned in this session")
                root.after(0, lambda r=ocr_result: messagebox.showwarning("Already Scanned",
                                     f"❌ INCORRECT SENSOR ID ❌\n\n"
                                     f"OCR Detected Pattern:\n'{r}'\n\n"
                                     f"Expected Lot: '{lot_number}'\n\n"
                                     f"ERROR: This sensor has already been\nscanned in this session.\n\n"
                                     f"ACTION: Scan the next sensor."))
            else:
                # Check if it's a defective sensor from this lot or wrong lot
                try:
                    conn_check = sqlite3.connect(db_path_tracking)
                    cur_check = conn_check.cursor()
                    cur_check.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
                    all_lot_sensors = [r[0] for r in cur_check.fetchall()]

                    if ocr_result in all_lot_sensors:
                        # Sensor belongs to this lot but has defects
                        root.after(0, lambda r=ocr_result: messagebox.showerror("DEFECTIVE SENSOR - CANNOT PROCEED",
                                           f"❌ INCORRECT SENSOR ID ❌\n\n"
                                           f"OCR Detected Pattern:\n'{r}'\n\n"
                                           f"Expected Lot: '{lot_number}'\n\n"
                                           f"⚠ THIS SENSOR IS DEFECTIVE ⚠\n\n"
                                           f"ERROR: This sensor has defects from\nprevious processes and cannot proceed.\n\n"
                                           f"ACTION REQUIRED:\n"
                                           f"• Set this sensor aside\n"
                                           f"• DO NOT process this sensor\n"
                                           f"• Scan the next sensor"))
                    else:
                        # Doesn't belong to this lot
                        root.after(0, lambda r=ocr_result: messagebox.showerror("Wrong Sensor ID - OCR Output Incorrect",
                                           f"❌ INCORRECT SENSOR ID ❌\n\n"
                                           f"OCR Detected Pattern:\n'{r}'\n\n"
                                           f"Expected Lot: '{lot_number}'\n\n"
                                           f"ERROR: This sensor does NOT belong\nto lot '{lot_number}'.\n\n"
                                           f"ACTION: Verify the sensor or set it aside."))
                    conn_check.close()
                except sqlite3.Error:
                    root.after(0, lambda r=ocr_result: messagebox.showerror("Wrong Sensor ID",
                                           f"❌ INCORRECT SENSOR ID ❌\n\n"
                                           f"OCR Detected Pattern:\n'{r}'\n\n"
                                           f"Expected Lot: '{lot_number}'\n\n"
                                           f"ERROR: This sensor is not valid for this lot."))

            def clear_textbox():
                sensor_id_textbox.delete("1.0", tk.END)
                sensor_id_textbox.config(bg="white")
            root.after(0, clear_textbox)
            return

        print(f"Final OCR result: '{ocr_result}'")

        # Success - write to textbox
        def ui_update_success():
            sensor_id_textbox.delete("1.0", tk.END)
            sensor_id_textbox.insert(tk.END, ocr_result)
            sensor_id_textbox.config(bg="green")
            validate_sensor_id(None)  # call validate to write into table

        root.after(0, ui_update_success)

    except Exception as e:
        err_msg = str(e)
        root.after(0, lambda msg=err_msg: messagebox.showerror("OCR Error", f"Error during OCR processing: {msg}"))
    finally:
        try:
            orig = int(locals().get("current_threshold", threshold_scale.get()))
        except Exception:
            orig = threshold_scale.get()
        root.after(0, lambda val=orig: threshold_scale.set(val))

# ---------- Sensor ID write/validation ----------
def write_sensor_id_to_active_pcb(value):
    """
    Write 'value' to focused sensor ID entry (or first empty).
    After writing, the next row's sensor ID entry is focused and set to normal so next write can occur.
    """
    if not value:
        messagebox.showwarning("Warning", "Sensor ID value is empty.")
        return

    target_row = None
    focused = root.focus_get()
    for r in range(20):
        if data_entry[r][0] == focused:
            target_row = r
            break
    if target_row is None:
        for r in range(20):
            if not data_entry[r][0].get().strip():
                target_row = r
                break
    if target_row is None:
        messagebox.showwarning("Warning", "No available Sensor ID slot found.")
        return

    data_entry[target_row][0].config(state="normal")
    data_entry[target_row][0].delete(0, tk.END)
    data_entry[target_row][0].insert(0, value)
    data_entry[target_row][0].config(state="readonly")
    data_entry[target_row][0].config(bg="green")

    # Move focus to next row
    next_row = target_row + 1
    if next_row < 20:
        data_entry[next_row][0].config(state="normal")
        data_entry[next_row][0].focus_set()
    else:
        entries["Operator:"].focus_set()

    # After insertion, check whether all sensor IDs are entered
    check_all_sensor_ids()

def validate_sensor_id(event):
    """Validate the sensor_id_textbox content against required sensor IDs and write to table if valid."""
    lot_number = entries["Lot Number:"].get().strip()
    value = sensor_id_textbox.get("1.0", tk.END).strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Lot Number is missing.")
        sensor_id_textbox.delete("1.0", tk.END)
        sensor_id_textbox.config(bg="white")
        return

    if not value:
        sensor_id_textbox.config(bg="white")
        return

    # Prefer using sensor_ids (set when fetch_lot_info is called)
    valid_ids = sensor_ids[:] if sensor_ids else get_valid_sensor_ids_for_lot(lot_number)

    if value not in valid_ids:
        sensor_id_textbox.config(bg="red")
        messagebox.showerror("Invalid Sensor ID", f"Sensor ID '{value}' is not valid for Lot {lot_number}.")
    else:
        # check duplicate in table
        for i in range(20):
            if data_entry[i][0].get().strip() == value:
                messagebox.showerror("Duplicate Sensor ID", f"Sensor ID '{value}' is already entered in another row.")
                sensor_id_textbox.delete("1.0", tk.END)
                sensor_id_textbox.config(bg="white")
                return
        sensor_id_textbox.config(bg="green")
        # write into table
        write_sensor_id_to_active_pcb(value)
        sensor_id_textbox.delete("1.0", tk.END)
        sensor_id_textbox.config(bg="white")

# ---------- Existing fetch_lot_info (modified to NOT auto-populate sensor IDs) ----------
def fetch_lot_info(event=None):
    global sensor_ids, lot_condition

    lot_number = entries["Lot Number:"].get().strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number.")
        return

    try:
        # Connect to the tracking database
        conn = sqlite3.connect(db_path_tracking)
        cursor = conn.cursor()

        # Fetch current_process based on Lot Number
        cursor.execute("SELECT current_process FROM lot_tracking WHERE lot_number = ? LIMIT 1", (lot_number,))
        result = cursor.fetchone()
        if not result:
            messagebox.showwarning("Warning", "Lot Number not found in the database.")
            conn.close()
            delete_action()
            return

        current_process = result[0]
        entries["Current Process:"].config(state="normal")
        entries["Current Process:"].delete(0, tk.END)
        entries["Current Process:"].insert(0, current_process)
        entries["Current Process:"].config(state="readonly")

        # Read Condition from masterlist (normalize; treat values starting with "EVAL" as Eval)
        lot_condition = 'MP'
        try:
            conn_masterlist = sqlite3.connect(db_path_masterlist)
            cursor_masterlist = conn_masterlist.cursor()
            cursor_masterlist.execute("SELECT DISTINCT [Condition] FROM lot_masterlist WHERE lot_number = ?", (lot_number,))
            cond_row = cursor_masterlist.fetchone()
            if cond_row and cond_row[0]:
                lot_condition = str(cond_row[0]).strip().upper()
            conn_masterlist.close()
        except sqlite3.Error:
            lot_condition = 'MP'

        is_eval = str(lot_condition).strip().upper().startswith("EVAL")

        # Validate the expected process for this UI unless the lot is Eval
        if not is_eval:
            if current_process != UI_PROCESS_NAME:
                messagebox.showerror("Error", f"The lot number inputted is not for {UI_PROCESS_NAME}.")
                conn.close()
                delete_action()
                return
        # If Eval: skip strict process matching

        # Determine if current_process is known in process_flow
        current_in_flow = current_process in process_flow
        current_process_index = process_flow.index(current_process) if current_in_flow else None

        # Build filtered sensor list:
        # Apply previous-defect filtering only for non-Eval lots and when we have a valid index > 0
        if (not is_eval) and (current_process_index is not None and current_process_index > 0):
            previous_defect_columns = [
                process_column_mapping[proc][2]
                for proc in process_flow[:current_process_index]
                if proc in process_column_mapping and len(process_column_mapping[proc]) > 2
            ]

            if previous_defect_columns:
                # require all previous defect columns to be NULL or empty
                defect_conditions = " AND ".join(f"({col} IS NULL OR {col} = '')" for col in previous_defect_columns)
                query = f"SELECT sensor_id FROM lot_tracking WHERE lot_number = ? AND {defect_conditions}"
                cursor.execute(query, (lot_number,))
                sensor_ids = [r[0] for r in cursor.fetchall()]
            else:
                # fallback: include all sensors for this lot
                cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
                sensor_ids = [r[0] for r in cursor.fetchall()]
        else:
            # For Eval or first process or unknown index: include all sensors
            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
            sensor_ids = [r[0] for r in cursor.fetchall()]

        # If none remain after filtering, inform user and exit
        if not sensor_ids:
            messagebox.showinfo("Information", "No sensors available for this process (all sensors have defects from previous processes).")
            conn.close()
            delete_action()
            return

        # Check masterlist for existing values as before (to warn user), then close
        conn_masterlist = sqlite3.connect(db_path_masterlist)
        cursor_masterlist = conn_masterlist.cursor()
        process_to_columns = {
            "Laser Marking and OCR": ["OCR_Reading"],
            "MR Chip Alignment Measurement": ["X_alignment_1", "Y_alignment_1", "X_alignment_2", "Y_alignment_2"],
            "MR Chip Height Measurement": ["mr_chip_height"],
            # ... (rest kept as before)
        }
        columns = process_to_columns.get(current_process, [])

        if columns:
            sensor_ids_with_values = []
            for sid in sensor_ids:
                try:
                    cursor_masterlist.execute(f"SELECT {', '.join(columns)} FROM lot_masterlist WHERE sensor_id=?", (sid,))
                    r = cursor_masterlist.fetchone()
                    if r and all(value is not None and str(value) != '' for value in r):
                        sensor_ids_with_values.append(sid)
                except sqlite3.Error:
                    continue

            conn_masterlist.close()

            if sensor_ids_with_values:
                messagebox.showinfo("Information", f"The following Sensor IDs already have values in '{current_process}': {', '.join(sensor_ids_with_values)}")
                conn.close()
                return
        else:
            conn_masterlist.close()

        # CLEAR table but DO NOT populate Sensor IDs - OCR will populate them after pressing READ.
        for row in range(20):
            data_entry[row][0].config(state="normal")
            data_entry[row][0].delete(0, tk.END)
            data_entry[row][0].config(bg="white")
            # Ensure measurement column is readonly until all IDs entered or enabled later
            data_entry[row][1].config(state="readonly")
            judgement_labels[row].config(text="", bg="lightblue")

        # Make first Sensor ID row editable and focused so OCR/manual entry can start
        data_entry[0][0].config(state="normal")
        data_entry[0][0].focus_set()

        # Keep global sensor_ids list up-to-date (already assigned above)
        # DO NOT auto-import measurement here. User will press "Import Measurement" after IDs are written.

        conn.close()
        # Enable the READ button and ensure Import Measurement is disabled until all IDs are entered
        read_button.config(state="normal")
        import_button.config(state="disabled")

    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")
        try:
            conn.close()
        except:
            pass

# ---------- Fetch measurement CSV (existing) ----------
def fetch_measurement(initial_dir=None):
    """
    Import MR Chip Height CSV. If initial_dir provided, the file dialog will open there.
    This function expects sensor IDs already populated in data_entry column 0.
    """
    # Retrieve all Sensor IDs entered in column 0
    entered_sensor_ids = {data_entry[row][0].get().strip() for row in range(len(data_entry)) if data_entry[row][0].get().strip()}

    # Ensure sensor_ids is a list of strings
    required_sensor_ids = set(sensor_ids)

    if not entries["Lot Number:"].get():
        messagebox.showerror("Error", "Please input Lot Number First.")
        return

    if entered_sensor_ids != required_sensor_ids:
        messagebox.showerror("Error", "Please input all of the required Sensor ID")
        return

    lot_number = entries["Lot Number:"].get().strip()

    # Open file dialog for user to select CSV
    try:
        if initial_dir and not os.path.isdir(initial_dir):
            try:
                normalized = os.path.normpath(initial_dir)
                if not os.path.isdir(normalized):
                    messagebox.showinfo("Info", f"Measurement folder not reachable: {initial_dir}\nYou can select a CSV manually.")
                    initial_dir = None
                else:
                    initial_dir = normalized
            except Exception:
                messagebox.showinfo("Info", f"Measurement folder not reachable: {initial_dir}\nYou can select a CSV manually.")
                initial_dir = None
    except Exception:
        initial_dir = None

    height_csv_path = filedialog.askopenfilename(
        initialdir=initial_dir or os.getcwd(),
        title="Select MR Chip Height CSV File",
        filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
    )

    if height_csv_path:
        try:
            with open(height_csv_path, mode='r', newline='') as file:
                csv_reader = csv.reader(file)
                height_values = []
                row_num = 0
                for row in csv_reader:
                    row_num += 1
                    if row_num < 2:  # Skip header
                        continue
                    if len(height_values) < len(required_sensor_ids):
                        try:
                            # Default to column H (index 7) as used in previous scripts.
                            # If your CSV differs, change this index accordingly.
                            height_value = row[7].strip()
                            float(height_value)  # ensure numeric
                            height_values.append(height_value)
                        except (IndexError, ValueError):
                            # skip malformed rows
                            continue

            for row_index, height in enumerate(height_values[:20]):
                data_entry[row_index][1].config(state="normal")
                data_entry[row_index][1].delete(0, tk.END)
                data_entry[row_index][1].insert(0, height)
                data_entry[row_index][1].config(state="readonly")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read CSV file: {e}")
            return
    else:
        messagebox.showerror("Error", "MR Chip Height CSV file not selected.")
        return

    # Judge the values for each row
    for row in range(20):
        judge_row_values(row)

# Function to judge the input values for a specific row
def judge_row_values(row):
    if data_entry[row][0].get():  # Only judge rows with Sensor ID
        height = data_entry[row][1].get()

        # Ensure value is present
        if height:
            try:
                height_value = float(height)
                passed = True
                # If thresholds are configured, check them
                if HEIGHT_MIN is not None and height_value < HEIGHT_MIN:
                    passed = False
                if HEIGHT_MAX is not None and height_value > HEIGHT_MAX:
                    passed = False

                if passed:
                    judgement_labels[row].config(text="Passed", fg="green")
                else:
                    judgement_labels[row].config(text="Failed", fg="red")
            except ValueError:
                judgement_labels[row].config(text="Error", fg="red")
        else:
            judgement_labels[row].config(text="")
    else:
        # Clear judgement for empty sensor rows
        judgement_labels[row].config(text="")

# Function to update the date and time entry
def update_datetime():
    current_time = time.strftime("%m/%d/%Y %H:%M")
    entries["Date and Time:"].config(state="normal")
    entries["Date and Time:"].delete(0, tk.END)
    entries["Date and Time:"].insert(0, current_time)
    entries["Date and Time:"].config(state="readonly")
    root.after(1000, update_datetime)  # Update every second

def check_all_sensor_ids():
    entered_sensor_ids = {
        data_entry[row][0].get().strip()
        for row in range(len(data_entry))
        if data_entry[row][0].get().strip()
    }

    required_sensor_ids = set(sensor_ids)

    if entered_sensor_ids == required_sensor_ids and required_sensor_ids:
        # Lock Sensor ID column and enable measurement entry
        for row in range(len(data_entry)):
            data_entry[row][0].config(state="readonly")
            if data_entry[row][0].get().strip():
                try:
                    data_entry[row][1].config(state="normal")
                except Exception:
                    pass

        data_entry[0][1].focus_set()
        # Enable Import Measurement button and notify user
        import_button.config(state="normal")
        lot_number = entries["Lot Number:"].get().strip()
        messagebox.showinfo("Info", f"All Sensor IDs for Lot {lot_number} have been entered. You can now start Measurement (use Import Measurement).")
    else:
        missing_ids = required_sensor_ids - entered_sensor_ids
        print(f"Waiting for all Sensor IDs to be entered. Missing: {missing_ids}")

# ---------- UI: title, entries, video & OCR controls ----------
title_label = tk.Label(root, text="MR Chip Height Measurement", font=("BiomeW04-Bold", 18, "bold"), bg="lightblue")
title_label.place(x=10, y=0)

# Labels and Entry fields for Lot Number, Operator, Current Process, Connection, Date and Time
labels = ["Lot Number:", "Current Process:", "Date and Time:", "Operator:"]
entries = {}

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
    entries["Current Process:"].config(state="readonly")
    for row in range(20):
        for col in range(2):  # column 0 = Sensor ID, column 1 = MR Chip Height
            data_entry[row][col].config(state="normal")
            data_entry[row][col].delete(0, tk.END)
            data_entry[row][col].config(state="readonly")
            if col == 0:
                data_entry[row][col].config(state="readonly")
            # Reset sensor id background
            data_entry[row][0].config(bg="white")
        judgement_labels[row].config(text="", bg="lightblue")

# ---------- BMS Popup class (existing v2) ----------
class BMSPopup(tk.Toplevel):
    def __init__(self, master, lot_number, current_process, operator,
                 sensor_list, combobox_candidates, failed_sensor_list, blank_judgement_list, csv_rows_data,
                 lot_condition, ui_process=None):
        super().__init__(master)
        self.title("BMS Lot Tracking System - Popup")
        self.geometry("615x455")
        self.configure(bg='#3a6ba8')
        self.resizable(False, False)

        self.lot_number = lot_number
        self.current_process = current_process
        self.operator = operator
        self.sensor_list = sensor_list[:]              # all sensors
        self.combobox_candidates = combobox_candidates[:]  # for the Combobox: Failed OR blank
        self.failed_sensor_list = failed_sensor_list[:]    # only sensors judged "Failed"
        self.blank_judgement_list = blank_judgement_list[:] # sensors with blank judgement
        self.csv_rows_data = csv_rows_data[:]          # measurement data for CSV export
        self.lot_condition = str(lot_condition).strip().upper()  # normalized
        self.ui_process = ui_process or current_process

        # Title
        tk.Label(self, text="BMS Lot Tracking System", font=("BiomeW04-Bold", 20, "bold"), bg='#3a6ba8', fg="orange").place(x=20, y=0)

        # Lot number & current process (prefilled)
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

        # Sensor ID Combobox (now populated with failed OR no-judgement sensors)
        tk.Label(self, text="Sensor ID:", bg='#3a6ba8', fg="white").place(x=5, y=105)
        self.sensor_id_combobox = ttk.Combobox(self, values=self.combobox_candidates, width=28)
        self.sensor_id_combobox.place(x=105, y=105)
        if self.combobox_candidates:
            self.sensor_id_combobox.set(self.combobox_candidates[0])

        # Defect, Remarks
        tk.Label(self, text="Defect:", bg='#3a6ba8', fg="white").place(x=5, y=135)
        self.defect_entry = tk.Entry(self, width=31)
        self.defect_entry.place(x=105, y=135)

        tk.Label(self, text="Remarks:", bg='#3a6ba8', fg="white").place(x=5, y=165)
        self.remarks_entry = tk.Entry(self, width=31)
        self.remarks_entry.place(x=105, y=165)

        # Quantity in/out
        tk.Label(self, text="Quantity IN:", bg='#3a6ba8', fg="white").place(x=320, y=45)
        self.quantity_in_entry = tk.Entry(self, width=15)
        self.quantity_in_entry.place(x=410, y=45)

        tk.Label(self, text="Quantity OUT:", bg='#3a6ba8', fg="white").place(x=320, y=75)
        self.quantity_out_entry = tk.Entry(self, width=15)
        self.quantity_out_entry.place(x=410, y=75)

        # Date and operator
        tk.Label(self, text="Date:", bg='#3a6ba8', fg="white").place(x=320, y=105)
        self.date_time_label = tk.Label(self, text="", bg='white', width=19)
        self.date_time_label.place(x=410, y=105)

        tk.Label(self, text="Operator:", bg='#3a6ba8', fg="white").place(x=320, y=135)
        self.operator_entry = tk.Entry(self, width=22)
        self.operator_entry.place(x=410, y=135)
        self.operator_entry.insert(0, self.operator)

        # Buttons
        export_button = tk.Button(self, text="Export Defects / Remarks", command=self.export_data, bg="green", fg="white", font=("Tahoma", 10, "bold"), padx=20, pady=1, relief='raised', borderwidth=3)
        export_button.place(x=20, y=200)

        clear_button = tk.Button(self, text="CLEAR", command=self.clear_fields, bg="yellow", font=("Tahoma", 16, "bold"), padx=10, pady=1, relief='raised', borderwidth=3)
        clear_button.place(x=320, y=185)

        save_button = tk.Button(self, text="SAVE", command=self.save_data_and_advance, bg="green", fg="white", font=("Tahoma", 16, "bold"), padx=10, pady=1, relief='raised', borderwidth=3)
        save_button.place(x=460, y=185)

        delete_button = tk.Button(self, text="DELETE Defects / Remarks", command=self.delete_selected_row, bg="red", fg="white", font=("Tahoma", 10, "bold"), padx=20, pady=1, relief='raised', borderwidth=3)
        delete_button.place(x=20, y=235)

        # Table for Sensor ID, Defects, Remarks
        self.columns = ("Sensor ID", "Defects", "Remarks")
        self.table = ttk.Treeview(self, columns=self.columns, show="headings", height=7)
        for col in self.columns:
            self.table.heading(col, text=col)
        self.table.place(x=5, y=280)

        # Populate Quantity IN / OUT:
        total_sensors = len(self.sensor_list)
        reduced_count = len(self.failed_sensor_list) + len(self.blank_judgement_list)
        self.quantity_in_entry.delete(0, tk.END)
        self.quantity_in_entry.insert(0, str(total_sensors))
        self.quantity_out_entry.delete(0, tk.END)
        self.quantity_out_entry.insert(0, str(max(0, total_sensors - reduced_count)))

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

        if not defect:
            if sensor_id:
                messagebox.showwarning("Input Error", f"Please input defects for Sensor ID: {sensor_id}")
            else:
                messagebox.showwarning("Input Error", "Please input defects.")
            return

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
        try:
            quantity_in = int(self.quantity_in_entry.get())
        except ValueError:
            quantity_in = 0
        sensor_ids_with_defects = len([self.table.item(row)["values"][1] for row in self.table.get_children() if self.table.item(row)["values"][1]])
        self.quantity_out_entry.delete(0, tk.END)
        self.quantity_out_entry.insert(0, str(quantity_in - sensor_ids_with_defects))

    def save_data_and_advance(self):
        # Ensure operator is provided
        if not self.operator_entry.get():
            messagebox.showwarning("Input Error", "Please enter Operator.")
            return

        # If a Sensor ID is selected in the combobox, require that sensor to be added to the table with a defect
        selected_sensor = self.sensor_id_combobox.get().strip()
        if selected_sensor:
            found = False
            for row in self.table.get_children():
                sid, defect, remarks = self.table.item(row)["values"]
                if sid == selected_sensor and str(defect).strip():
                    found = True
                    break
            if not found:
                messagebox.showwarning(
                    "Input Error",
                    f"Please add a defect entry for Sensor ID: {selected_sensor} in the table\n"
                    "or clear the Sensor ID selection before saving."
                )
                return

        lot_number = self.lot_number
        current_process = self.current_process
        operator = self.operator_entry.get()
        proc_datetime = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")

        # Try to get mapping for current_process; if missing and lot is Eval, fallback to UI mapping
        columns = process_column_mapping.get(current_process)

        if not columns or len(columns) < 6:
            is_eval = str(self.lot_condition).strip().upper().startswith("EVAL")
            if is_eval:
                fallback_columns = process_column_mapping.get(self.ui_process)
                if fallback_columns and len(fallback_columns) >= 6:
                    columns = fallback_columns
                else:
                    messagebox.showerror("Configuration Error", f"Process mapping for '{current_process}' is missing or invalid.")
                    return
            else:
                messagebox.showerror("Configuration Error", f"Process mapping for '{current_process}' is missing or invalid.")
                return

        quantity_in = self.quantity_in_entry.get()
        quantity_out = self.quantity_out_entry.get()

        try:
            # 1) Update lot_masterlist with measurement data (from MRChip table)
            if self.csv_rows_data:
                conn_master = sqlite3.connect(db_path_masterlist)
                cursor_master = conn_master.cursor()
                for row in self.csv_rows_data:
                    sensor_id = row[0]
                    height = row[1]
                    # Update only MR_Chip_Height column
                    cursor_master.execute("""
                        UPDATE lot_masterlist
                        SET MR_Chip_Height = ?
                        WHERE sensor_id = ?
                    """, (height, sensor_id))
                conn_master.commit()
                conn_master.close()

            # 2) Update lot_tracking for sensors in table (defects/remarks)
            conn = sqlite3.connect(db_path_tracking)
            cursor = conn.cursor()

            sensor_ids_in_table = [self.table.item(row)["values"][0] for row in self.table.get_children()]
            sensor_ids_with_defects = [self.table.item(row)["values"][0] for row in self.table.get_children() if self.table.item(row)["values"][1]]

            # Update rows present in table (use provided defect/remarks)
            for row in self.table.get_children():
                sid, defect, remarks = self.table.item(row)["values"]
                cursor.execute(f"""
                    UPDATE lot_tracking
                    SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, {columns[3]}=?, {columns[4]}=?, {columns[5]}=?
                    WHERE lot_number=? AND sensor_id=?
                """, (quantity_in, quantity_out, defect, remarks, proc_datetime, operator, lot_number, sid))

            # For remaining sensors (not listed in table), update with IN/OUT and clear defect/remarks
            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot_number,))
            all_sensors_for_lot = [r[0] for r in cursor.fetchall()]
            remaining_sensors = set(all_sensors_for_lot) - set(sensor_ids_in_table)
            for sid in remaining_sensors:
                cursor.execute(f"""
                    UPDATE lot_tracking
                    SET {columns[0]}=?, {columns[1]}=?, {columns[2]}='', {columns[3]}='', {columns[4]}=?, {columns[5]}=?
                    WHERE lot_number=? AND sensor_id=?
                """, (quantity_in, quantity_out, proc_datetime, operator, lot_number, sid))

            # 4) Try to remove defective sensor IDs from file path stored in lot_tracking.database_path (if column exists)
            try:
                cursor.execute("SELECT database_path FROM lot_tracking WHERE lot_number=? LIMIT 1", (lot_number,))
                res = cursor.fetchone()
                if res and res[0]:
                    text_file_path = res[0]
                    try:
                        if os.path.isfile(text_file_path):
                            with open(text_file_path, 'r') as file:
                                lines = file.readlines()
                            with open(text_file_path, 'w') as file:
                                for line in lines:
                                    if line.strip() not in sensor_ids_with_defects:
                                        file.write(line)
                    except Exception as e:
                        print(f"Could not update sensor file {text_file_path}: {e}")
            except sqlite3.Error:
                pass

            # 5) Update current_process for remaining sensors only for non-Eval lots
            if self.lot_condition.startswith("EVAL"):
                # DO NOT update current_process in the DB for Eval lots. Leave it as-is.
                next_process = current_process
            else:
                # Safe attempt to advance process for MP/non-eval lots
                try:
                    next_process = process_flow[process_flow.index(current_process) + 1]
                except Exception:
                    next_process = current_process

                cursor.execute("""
                    UPDATE lot_tracking
                    SET current_process=?
                    WHERE lot_number=?
                """, (next_process, lot_number))

            conn.commit()
            conn.close()

            # 6) Export measurement CSV
            base_folder = r"\\phlsvr08\BMS Data\Assembly Data\MR Chip Height"
            current_year = time.strftime("%Y")
            current_month_name = time.strftime("%B")
            current_date_formatted = time.strftime("%m.%d.%Y")

            export_folder = os.path.join(base_folder, current_year, current_month_name, current_date_formatted)
            os.makedirs(export_folder, exist_ok=True)
            csv_filename = os.path.join(export_folder, f"MR_Chip_Height_{lot_number}.csv")

            if self.csv_rows_data:
                with open(csv_filename, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(["Lot Number", lot_number])
                    writer.writerow(["Processed Date and Time", proc_datetime])
                    writer.writerow(["Operator", operator])
                    writer.writerow([])
                    writer.writerow(["Sensor ID", "MR Chip Height", "Judgement"])
                    for row_data in self.csv_rows_data:
                        # Expecting [sensor_id, height, judgement]
                        writer.writerow(row_data)
                messagebox.showinfo("CSV Export", f"Data successfully exported to:\n{csv_filename}")

            # Inform user appropriately
            if self.lot_condition.startswith("EVAL"):
                messagebox.showinfo("Save", "Data saved successfully. Lot is in 'Eval' condition: current process was not advanced.")
            else:
                messagebox.showinfo("Save", f"Data saved successfully.\nNext process set to: {next_process}")

            entries["Lot Number:"].focus_set()
            self.destroy()
            delete_action()
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"An error occurred: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

def save_action():
    try:
        if not entries["Operator:"].get():
            messagebox.showerror("Error", "Operator field must be filled.")
            return

        csv_rows_data = []
        failed_sensor_list_local = []
        blank_judgement_list_local = []
        combobox_candidates_local = []
        sensor_list_local = []

        for row_idx in range(20):
            sensor_id = data_entry[row_idx][0].get().strip()
            if sensor_id:
                sensor_list_local.append(sensor_id)
                height = data_entry[row_idx][1].get().strip()
                judgement = judgement_labels[row_idx].cget("text").strip()
                # Store only sensor_id, height, judgement
                csv_rows_data.append([sensor_id, height, judgement])

                if judgement == "Failed":
                    if sensor_id not in failed_sensor_list_local:
                        failed_sensor_list_local.append(sensor_id)
                    if sensor_id not in combobox_candidates_local:
                        combobox_candidates_local.append(sensor_id)
                elif judgement == "":
                    if sensor_id not in blank_judgement_list_local:
                        blank_judgement_list_local.append(sensor_id)
                    if sensor_id not in combobox_candidates_local:
                        combobox_candidates_local.append(sensor_id)

        if not sensor_list_local:
            messagebox.showwarning("Warning", "No Sensor IDs entered.")
            return

        lot_number = entries["Lot Number:"].get().strip()
        current_process = entries["Current Process:"].get().strip()
        operator = entries["Operator:"].get().strip()

        # Pass lot_condition and UI_PROCESS_NAME to popup so save knows whether to advance process and can fallback mapping
        popup = BMSPopup(root, lot_number, current_process, operator,
                         sensor_list_local, combobox_candidates_local,
                         failed_sensor_list_local, blank_judgement_list_local, csv_rows_data,
                         lot_condition, UI_PROCESS_NAME)
        popup.grab_set()
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

# UI Buttons
delete_button = tk.Button(root, text="Clear Data", font=("Tahoma", 12, "bold"), padx=10, pady=1, bg="yellow", command=delete_action, relief='raised', borderwidth=3)
delete_button.place(x=310, y=50)
save_button = tk.Button(root, text="SAVE", font=("Tahoma", 12, "bold"), padx=32, pady=1, bg="orange", command=save_action, relief='raised', borderwidth=3)
save_button.place(x=310, y=90)

# Table headers
headers = ["No.", "Sensor ID", "MR Chip Height", "Judgement"]
header_positions = {
    "No.": (10, 150),
    "Sensor ID": (75, 150),
    "MR Chip Height": (190, 150),
    "Judgement": (320, 150)
}
for header in headers:
    label = tk.Label(root, text=header, font=("Arial", 10, "bold"), bg="lightblue", relief="ridge")
    label.place(x=header_positions[header][0], y=header_positions[header][1])

# Table rows for data entry
data_entry = []
judgement_labels = []

for row in range(20):
    row_entries = []
    # Add numbering label
    number_label = tk.Label(root, text=str(row + 1), width=3, bg="lightblue", relief="ridge")
    number_label.place(x=10, y=180 + row*23)

    # Sensor ID entry (col 0)
    entry_sid = tk.Entry(root, width=20, validate="key", justify='center')
    entry_sid.place(x=50, y=180 + row*23)
    entry_sid.config(state="readonly")
    row_entries.append(entry_sid)

    # MR Chip Height entry (col 1)
    entry_height = tk.Entry(root, width=13, validate="key", justify='center')
    entry_height.place(x=200, y=180 + row*23)
    entry_height.config(state="readonly")
    row_entries.append(entry_height)

    data_entry.append(row_entries)

    # Add judgement label
    judgement_label = tk.Label(root, text="", width=10, bg="lightblue", relief="ridge")
    judgement_label.place(x=320, y=180 + row*23)
    judgement_labels.append(judgement_label)

# ---------- UI: video widget, controls, bindings ----------
video_label = Label(root, bg="black")
video_label.place(x=470, y=50, width=DISPLAY_W, height=DISPLAY_H)

sensor_id_label = Label(root, text="Sensor ID:", font=("Arial", 14), bg="lightblue", fg="black")
sensor_id_label.place(x=500, y=360)

sensor_id_textbox = tk.Text(root, height=1, width=17, font=("Arial", 14))
sensor_id_textbox.place(x=610, y=360)
sensor_id_textbox.bind("<Return>", lambda ev: validate_sensor_id(ev))

threshold_label = Label(root, text="Threshold Level\n(110-200):", font=("Arial", 14), bg="lightblue", fg="black")
threshold_label.place(x=490, y=430)

threshold_scale = Scale(root, from_=110, to=200, orient=tk.HORIZONTAL, length=200, bg="#407ec9", fg="white", font=("Arial", 10), resolution=5)
threshold_scale.set(175)
threshold_scale.place(x=640, y=435)

read_button = Button(root, text="READ", command=capture_image_and_process, font=("Arial", 15), bg="#00cc44", fg="white", padx=20, pady=1)
read_button.place(x=500, y=390)

toggle_button = Button(root, text="Toggle View", command=lambda: globals().__setitem__('threshold_view', not threshold_view), font=("Arial", 15), bg="#407ec9", fg="white", padx=20, pady=1)
toggle_button.place(x=630, y=390)

# Import Measurement button (disabled until all sensor IDs present)
import_button = Button(root, text="Import Measurement", command=lambda: fetch_measurement(initial_dir=DEFAULT_MEASUREMENT_FOLDER), font=("Arial", 16), bg="#3a8bd9", fg="white", padx=10, pady=1)
import_button.place(x=530, y=490)
import_button.config(state="disabled")

# Start camera preview (non-blocking)
start_camera()

# Ensure camera is released on close
def on_closing():
    global cap
    if cap and cap.isOpened():
        cap.release()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
entries["Lot Number:"].focus_set()
root.mainloop() 