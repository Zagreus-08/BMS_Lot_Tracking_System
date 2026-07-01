import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import time
import json
import os
import csv
from datetime import datetime

# --- OCR / camera imports ---
import cv2
from PIL import Image, ImageFilter, ImageTk
import pytesseract
import threading
import re
import numpy as np

# Define the paths to the databases
db_path_tracking = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"
db_path_masterlist = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"

# Define the absolute path to your config.json
config_file_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\process_flow.json"  # Example for Windows

measurement_phase = "PHASE1"
current_row_index = 0
active_row_limit = 0

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

# Path to Tesseract executable (update if needed)
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\a493353\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

custom_oem_psm_config = (
    '--oem 3 --psm 6 '
    '-c tessedit_char_whitelist="ABCDEFGIJKLMNOPQRSTVWXZ0123456789- "'
)

# OCR temporary image paths
before_image_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\OCRBefore.png"
save_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\OCRAfter.png"

# Globals for OCR/camera
DISPLAY_W, DISPLAY_H = 320, 240
camera_index = 0
cap = None
threshold_view = False
last_successful_threshold = None  # Store the successful threshold value

# Global list used by fetch_lot_info and OCR functions
sensor_ids_no_defects = []  # expected sensor IDs for the lot (unchanged by user input)

# Common OCR confusion map: OCR_char -> likely_real_char
OCR_CONFUSIONS = {
    'T': 'J',
    't': 'J',
    'K': 'H',
    'k': 'H',
    'O': '0',
    'o': '0',
    '|': '1',
    'l': '1',
    '8': 'B'
}

def _apply_confusions(s):
    if not s:
        return s
    return ''.join(OCR_CONFUSIONS.get(ch, ch) for ch in s)

def _levenshtein(a, b):
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

# Helper: fetch lot condition from masterlist DB
def get_lot_condition(lot_number):
    """
    Return the lot condition string (e.g., "MP" or "Eval").
    Defaults to "MP" if not found or on DB error.
    """
    default = "MP"
    try:
        conn = sqlite3.connect(db_path_masterlist)
        cur = conn.cursor()
        # Try several plausible column names
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

# ---------- OCR helper functions ----------
def normalize_ocr_text(s):
    if not s:
        return ""
    s = s.upper()
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
    filtered = "".join(ch for ch in s if ch in allowed or ch.isspace())
    parts = filtered.split()
    return " ".join(parts) if parts else ""

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

def find_matching_sensor(ocr_norm, valid_ids):
    if not ocr_norm or not valid_ids:
        return None
    tokens = ocr_norm.split()
    for t in tokens:
        for sid in valid_ids:
            if t == sid.upper():
                return sid
    for sid in valid_ids:
        if ocr_norm == sid.upper():
            return sid
    for sid in valid_ids:
        s_up = sid.upper()
        if s_up in ocr_norm or ocr_norm in s_up:
            return sid
    return None

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
        img = img.resize(new_size, Image.LANCZOS)
        
        img = img.filter(ImageFilter.SHARPEN)
        img = img.point(lambda p: 255 if p > threshold else 0)
        
        ocr_result = pytesseract.image_to_string(img, config=custom_oem_psm_config)
        
        # Apply OCR confusion map first, then additional targeted replacements
        try:
            ocr_result = _apply_confusions(ocr_result)
        except Exception:
            pass

        ocr_result = ocr_result.replace("D", "0").replace("I", "1")\
                               .replace("l", "1").replace("S", "5").replace("Z", "2")\
                               .replace("B", "8").replace("G", "6").replace("|", "1")
        
        # Regex pattern for sensor ID: XX-XX-XXXXX-XXXXXX
        # Format: 2digits-2digits-4-5alphanumeric-6digits
        pattern = r'\b(\d{2})-(\d{2})-([A-Z0-9]{4,5})-(\d{6})\b'
        matches = re.findall(pattern, ocr_result.upper())
        
        if matches:
            # Reconstruct the sensor ID from the first match
            sensor_id = f"{matches[0][0]}-{matches[0][1]}-{matches[0][2]}-{matches[0][3]}"
            print(f"[OCR] Regex matched sensor ID: {sensor_id}")
            return sensor_id
        
        # Fallback: return normalized text if no pattern match
        return normalize_ocr_text(ocr_result)
    except Exception as exc:
        print("OCR error:", exc)
        return ""

# Create the main application window
root = tk.Tk()
root.title("Assembly Measurement")
root.geometry("1130x650")  # Adjusted width to fit the new column
root.configure(bg="lightblue")
root.resizable(False, False)

# Function to query the database for Lot Number information
def fetch_lot_info(event=None):

    global active_row_limit
    global sensor_ids_no_defects
    """
    After entering Lot Number:
    - validate lot/process
    - retrieve expected sensor IDs for the lot (sensor_ids_no_defects)
    - DO NOT auto-populate Sensor ID column
    - enable Sensor ID entries for the expected number of sensors, keep measurement columns readonly
    - focus first Sensor ID entry
    """

    lot_number = entries["Lot Number:"].get().strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number.")
        return

    try:
        # Connect to tracking DB and get current_process
        conn = sqlite3.connect(db_path_tracking)
        cursor = conn.cursor()
        cursor.execute("SELECT current_process FROM lot_tracking WHERE lot_number = ? LIMIT 1", (lot_number,))
        row = cursor.fetchone()
        if not row:
            messagebox.showwarning("Warning", "Lot Number not found in the database.")
            conn.close()
            return

        current_process = row[0]
        entries["Current Process:"].config(state="normal")
        entries["Current Process:"].delete(0, tk.END)
        entries["Current Process:"].insert(0, current_process)
        entries["Current Process:"].config(state="readonly")

        # Fetch lot condition and decide behavior
        lot_condition = get_lot_condition(lot_number)

        # Validate process only for MP
        if str(lot_condition).upper() == "MP":
            if current_process != "Assembly Measurement":
                messagebox.showerror("Error", "The lot number inputted is not for Assembly Measurement.")
                conn.close()
                delete_action()
                return
        # else Eval -> skip strict check

        # Determine previous defect columns from process flow mapping
        try:
            current_index = process_flow.index(current_process)
        except ValueError:
            current_index = -1

        previous_defect_columns = []
        if current_index > 0:
            for proc in process_flow[:current_index]:
                if proc in process_column_mapping and isinstance(process_column_mapping[proc], (list, tuple)) and len(process_column_mapping[proc]) > 2:
                    previous_defect_columns.append(process_column_mapping[proc][2])

        # Get sensors for this lot that have no defects in any previous process
        if previous_defect_columns:
            defect_conditions = " AND ".join(f"({col} IS NULL OR {col} = '')" for col in previous_defect_columns)
            query = f"SELECT sensor_id FROM lot_tracking WHERE lot_number = ? AND {defect_conditions}"
            cursor.execute(query, (lot_number,))
            sensor_ids = [r[0] for r in cursor.fetchall()]
            sensor_ids_no_defects = sensor_ids[:]
            active_row_limit = len(sensor_ids_no_defects)
        else:
            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
            sensor_ids = [r[0] for r in cursor.fetchall()]
            sensor_ids_no_defects = sensor_ids[:]
            active_row_limit = len(sensor_ids_no_defects)

        if not sensor_ids:
            messagebox.showinfo("Information", "No sensors available for this process (all sensors have defects from previous processes).")
            conn.close()
            delete_action()
            return

        # Save expected sensor ids globally for OCR matching and completion check
        sensor_ids_no_defects = sensor_ids[:]

        # Clear table and prepare entry states:
        for r in range(20):
            for c in range(7):
                data_entry[r][c].config(state="normal")
                data_entry[r][c].delete(0, tk.END)
                data_entry[r][c].config(bg="white")
            judgement_labels[r].config(text="", bg="lightblue")

        num_expected = len(sensor_ids_no_defects)
        # Enable only the Sensor ID column entries for the expected rows; keep measurements readonly
        for r in range(20):
            if r < num_expected:
                data_entry[r][0].config(state="normal", bg="white")
            else:
                data_entry[r][0].config(state="readonly", bg="white")
            # measurement columns readonly until all sensor ids are entered
            for c in range(1, 7):
                data_entry[r][c].config(state="readonly")

        # Focus first Sensor ID entry
        data_entry[0][0].focus_set()

        #messagebox.showinfo("Info", f"Lot '{lot_number}' has {num_expected} sensors to read.\nUse the READ button to OCR each Sensor ID. After all are read, measurement columns will be enabled.")

        conn.close()
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")
        try:
            conn.close()
        except:
            pass
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")
        try:
            conn.close()
        except:
            pass

# Function to handle Enter key navigation
def navigate_on_enter(event, row, col):
    global measurement_phase, active_row_limit

    max_rows = active_row_limit

    # ---------------- PHASE 1 ----------------
    if measurement_phase == "PHASE1":

        phase1 = [1, 2, 4, 3]

        if col not in phase1:
            return

        idx = phase1.index(col)

        if idx < len(phase1) - 1:
            next_col = phase1[idx + 1]
            next_row = row
        else:
            next_row = row + 1
            next_col = phase1[0]

            # ONLY GO UNTIL ACTIVE ROWS
            if next_row >= max_rows:
                measurement_phase = "PHASE2"
                next_row = 0
                next_col = 5

        data_entry[next_row][next_col].focus_set()

    # ---------------- PHASE 2 ----------------
    elif measurement_phase == "PHASE2":

        phase2 = [5, 6]

        if col not in phase2:
            return

        idx = phase2.index(col)

        if idx < len(phase2) - 1:
            next_col = phase2[idx + 1]
            next_row = row
        else:
            judge_row_values(row)
            next_row = row + 1
            next_col = phase2[0]

            if next_row >= max_rows:
                messagebox.showinfo("Done", "All sensor measurements completed.")
                return

        data_entry[next_row][next_col].focus_set()

# Function to validate numeric input
def validate_numeric_input(P):
    if P == "" or (P[0] == "-" and P[1:].replace(".", "", 1).isdigit()) or P.replace(".", "", 1).isdigit():
        return True
    else:
        return False

# Function to judge the input values for a specific row and change Entry box colors individually
def judge_row_values(row):
    if data_entry[row][0].get():  # Only judge rows with Sensor ID
        values = [
            data_entry[row][1].get(),  # BS gap to GMR
            data_entry[row][2].get(),  # TS gap to GMR
            data_entry[row][3].get(),  # BS gap to MR Chip
            data_entry[row][4].get(),  # TS Gap to MR Chip
            data_entry[row][5].get(),  # PCB Gap to BS1
            data_entry[row][6].get(),  # PCB Gap to BS2
        ]

        limits = [
            (0.015, 0.315),  # BS gap to GMR
            (0.010, 0.190),  # TS gap to GMR
            (0.000, 0.020),  # BS gap to MR Chip
            (0.000, 0.020),  # TS Gap to MR Chip
            (0.000, 0.050),  # PCB Gap to BS1
            (0.000, 0.050),  # PCB Gap to BS2
        ]

        row_failed = False

        for col, (value, (lower_limit, upper_limit)) in enumerate(zip(values, limits), start=1):
            try:
                value = float(value)
                if lower_limit <= value <= upper_limit:
                    data_entry[row][col].config(bg="white")
                else:
                    row_failed = True
                    data_entry[row][col].config(bg="red")
            except ValueError:
                row_failed = True
                data_entry[row][col].config(bg="red")

        if row_failed:
            judgement_labels[row].config(text="Failed", fg="red")
        else:
            judgement_labels[row].config(text="Passed", fg="green")

# Function to update the date and time entry
def update_datetime():
    current_time = time.strftime("%Y-%m-%d %I:%M:%S %p")
    entries["Date and Time:"].config(state="normal")
    entries["Date and Time:"].delete(0, tk.END)
    entries["Date and Time:"].insert(0, current_time)
    entries["Date and Time:"].config(state="readonly")
    root.after(1000, update_datetime)  # Update every second

# ---------- Camera / video handlers ----------
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

def start_camera():
    global cap
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        messagebox.showerror("Error", "Could not open camera.")
    else:
        show_frame()

# ---------- OCR capture and processing ----------
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
    Automatically finds sensor ID anywhere in the image using pattern matching.
    """
    global threshold_view, last_successful_threshold
    try:
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

        # Load captured image
        pil_orig = Image.open(before_image_path)
        pil_orig.save(save_path)

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
                root.after(0, lambda val=threshold_value: threshold_scale.set(val))
                root.update_idletasks()

            # Process image with current threshold
            ocr_raw = perform_ocr_on_pil_image(pil_orig, threshold_value)

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

            # Try normalized matching as fallback
            ocr_norm = normalize_ocr_text(ocr_raw)
            if valid_ids:
                match = find_matching_sensor(ocr_norm, valid_ids)
                if match:
                    # Always store detected pattern
                    last_detected_pattern = match
                    if match in remaining_sensor_ids:
                        print(f"[OCR] ✓ Normalized match found: {match}")
                        last_successful_threshold = threshold_value
                        ocr_result = match
                        break
                    else:
                        print(f"[OCR] ✓ Normalized match found: {match} - INCORRECT")
            
            # Try fuzzy matching with Levenshtein distance
            if ocr_raw and remaining_sensor_ids:
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
                    vstr = variant.replace('-', '').replace(' ', '')
                    for rid in remaining_sensor_ids:
                        d = _levenshtein(vstr, str(rid).replace('-', '').replace(' ', ''))
                        if best_dist is None or d < best_dist:
                            best_dist = d
                            best_match = (rid, d, variant)
                
                # Accept small edit distances (distance <= 3)
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
            validate_sensor_id()

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

# ---------- Write/validate Sensor ID into table ----------
def write_sensor_id_to_active_pcb():
    """
    Write sensor_id_textbox content to focused sensor ID entry (or first empty).
    After writing, the next row's sensor ID entry is focused and set to normal so next write can occur.
    """
    current_bg = sensor_id_textbox.cget("bg")
    if current_bg == "red":
        messagebox.showerror("Error", "Sensor ID is invalid. Please correct it before proceeding.")
        return
    value = sensor_id_textbox.get("1.0", tk.END).strip()
    if not value:
        messagebox.showwarning("Warning", "Sensor ID textbox is empty.")
        return

    target_row = None
    focused = root.focus_get()
    for r in range(20):
        if data_entry[r][0] == focused:
            target_row = r
            break
    if target_row is None:
        # prefer the first enabled/editable sensor id slot
        for r in range(20):
            st = str(data_entry[r][0].cget("state"))
            if st == "normal" and not data_entry[r][0].get().strip():
                target_row = r
                break
        # fallback: first empty
        if target_row is None:
            for r in range(20):
                if not data_entry[r][0].get().strip():
                    target_row = r
                    break

    if target_row is None:
        messagebox.showwarning("Warning", "No available Sensor ID slot found.")
        return

    # Write sensor id into target row
    data_entry[target_row][0].config(state="normal")
    data_entry[target_row][0].delete(0, tk.END)
    data_entry[target_row][0].insert(0, value)
    data_entry[target_row][0].config(state="readonly")

    sensor_id_textbox.delete("1.0", tk.END)
    sensor_id_textbox.config(bg="white")

    # Make next row's sensor ID entry editable and focus it (if within expected count)
    # Determine expected number:
    expected = len(sensor_ids_no_defects) if sensor_ids_no_defects else 0
    next_row = target_row + 1
    if next_row < expected:
        data_entry[next_row][0].config(state="normal")
        data_entry[next_row][0].focus_set()
    else:
        # if we've filled last expected row, focus operator or first measurement if enabled later
        entries["Operator:"].focus_set()

    check_all_sensor_ids()

def check_all_sensor_ids():
    """
    Check whether all expected sensor IDs have been entered.
    If yes: lock Sensor ID column (for expected rows) and enable measurement columns for those rows.
    """
    entered = {data_entry[r][0].get().strip() for r in range(len(data_entry)) if data_entry[r][0].get().strip()}
    required = set(sensor_ids_no_defects) if sensor_ids_no_defects else set()
    if not required:
        return
    missing = required - entered
    if not missing:
        expected = len(sensor_ids_no_defects)
        # Lock Sensor ID entries for expected rows
        for r in range(expected):
            data_entry[r][0].config(state="readonly")
            if data_entry[r][0].get().strip():
                for c in range(1, 7):
                    data_entry[r][c].config(state="normal", bg="white")
        # For rows beyond expected, keep readonly
        for r in range(expected, 20):
            data_entry[r][0].config(state="readonly")
            for c in range(1, 7):
                data_entry[r][c].config(state="readonly")
        data_entry[0][1].focus_set()
        messagebox.showinfo("Info", "All Sensor IDs have been entered. Sensor ID column is now locked, measurement columns enabled. You can now start Assembly Measurement.")
    else:
        print(f"Waiting for all Sensor IDs to be entered. Missing: {missing}")

def validate_sensor_id():
    """
    Validate the OCR text in the sensor_id_textbox against the lot's valid sensor IDs,
    ensure no duplicates in the table, and then write to the table (via write_sensor_id_to_active_pcb).
    """
    lot_number = entries["Lot Number:"].get().strip()
    value = sensor_id_textbox.get("1.0", tk.END).strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Lot Number is missing.")
        sensor_id_textbox.delete("1.0", tk.END)
        sensor_id_textbox.config(bg="white")
        return
    if not value:
        messagebox.showwarning("Warning", "Sensor ID textbox is empty.")
        sensor_id_textbox.config(bg="white")
        return
    try:
        conn = sqlite3.connect(db_path_tracking)
        cursor = conn.cursor()
        cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
        valid_ids = [r[0] for r in cursor.fetchall()]
        conn.close()
        if value not in valid_ids:
            sensor_id_textbox.config(bg="red")
            messagebox.showerror("Validation Error", f"'{value}' is not a valid Sensor ID for Lot '{lot_number}'.")
        else:
            # check duplicate (do not consider the focused target which may be same if editing)
            for i in range(20):
                if data_entry[i][0].get().strip() == value:
                    messagebox.showerror("Duplicate Sensor ID", f"Sensor ID '{value}' is already entered in another row.")
                    sensor_id_textbox.delete("1.0", tk.END)
                    sensor_id_textbox.config(bg="white")
                    return
            sensor_id_textbox.config(bg="green")
            write_sensor_id_to_active_pcb()
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")

# Title Label
title_label = tk.Label(root, text="Assembly Measurement", font=("BiomeW04-Bold", 20, "bold"), bg="lightblue")
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
        for col in range(7):
            data_entry[row][col].config(state="normal")  # Temporarily make all entries editable to clear
            data_entry[row][col].delete(0, tk.END)
            data_entry[row][col].config(bg="white")
            if col == 0:  # Set Sensor ID column back to readonly after clearing
                data_entry[row][col].config(state="readonly")
        judgement_labels[row].config(text="", bg="lightblue")
    # clear expected list
    global sensor_ids_no_defects
    sensor_ids_no_defects = []

# ---------- BMS Popup class (embedded and adapted) ----------
class BMSPopup(tk.Toplevel):
    def __init__(self, master, lot_number, current_process, operator,
                 sensor_list, combobox_candidates, failed_sensor_list, blank_judgement_list, csv_rows_data, lot_condition="MP"):
        super().__init__(master)
        self.title("BMS Lot Tracking System - Popup")
        self.geometry("615x455")
        self.configure(bg='#3a6ba3')
        self.resizable(False, False)

        self.lot_number = lot_number
        self.current_process = current_process
        self.operator = operator
        self.sensor_list = sensor_list[:]              # all sensors
        # combobox_candidates may be empty when lot_condition == "EVAL"
        self.combobox_candidates = combobox_candidates[:]
        self.failed_sensor_list = failed_sensor_list[:]
        self.blank_judgement_list = blank_judgement_list[:]
        self.csv_rows_data = csv_rows_data[:]
        self.lot_condition = str(lot_condition).strip()

        # Title
        tk.Label(self, text="BMS Lot Tracking System", font=("BiomeW04-Bold", 20, "bold"), bg='#3a6ba3', fg="orange").place(x=20, y=0)

        # Lot number & current process (prefilled)
        tk.Label(self, text="Lot Number:", bg='#3a6ba3', fg="white").place(x=5, y=45)
        self.lot_number_entry = tk.Entry(self, width=31)
        self.lot_number_entry.place(x=105, y=45)
        self.lot_number_entry.insert(0, lot_number)
        self.lot_number_entry.config(state="readonly")

        tk.Label(self, text="Current Process:", bg='#3a6ba3', fg="white").place(x=5, y=75)
        self.current_process_entry = tk.Entry(self, width=31)
        self.current_process_entry.place(x=105, y=75)
        self.current_process_entry.insert(0, current_process)
        self.current_process_entry.config(state="readonly")

        # Sensor ID Combobox
        tk.Label(self, text="Sensor ID:", bg='#3a6ba3', fg="white").place(x=5, y=105)
        self.sensor_id_combobox = ttk.Combobox(self, values=self.combobox_candidates, width=28)
        self.sensor_id_combobox.place(x=105, y=105)
        if self.combobox_candidates:
            self.sensor_id_combobox.set(self.combobox_candidates[0])

        # Defect, Remarks
        tk.Label(self, text="Defect:", bg='#3a6ba3', fg="white").place(x=5, y=135)
        self.defect_entry = tk.Entry(self, width=31)
        self.defect_entry.place(x=105, y=135)

        tk.Label(self, text="Remarks:", bg='#3a6ba3', fg="white").place(x=5, y=165)
        self.remarks_entry = tk.Entry(self, width=31)
        self.remarks_entry.place(x=105, y=165)

        # Quantity in/out
        tk.Label(self, text="Quantity IN:", bg='#3a6ba3', fg="white").place(x=320, y=45)
        self.quantity_in_entry = tk.Entry(self, width=15)
        self.quantity_in_entry.place(x=410, y=45)

        tk.Label(self, text="Quantity OUT:", bg='#3a6ba3', fg="white").place(x=320, y=75)
        self.quantity_out_entry = tk.Entry(self, width=15)
        self.quantity_out_entry.place(x=410, y=75)

        # Date and operator
        tk.Label(self, text="Date:", bg='#3a6ba3', fg="white").place(x=320, y=105)
        self.date_time_label = tk.Label(self, text="", bg='white', width=19)
        self.date_time_label.place(x=410, y=105)

        tk.Label(self, text="Operator:", bg='#3a6ba3', fg="white").place(x=320, y=135)
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
            for row_id in self.table.get_children():
                sid, defect, remarks = self.table.item(row_id)["values"]
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
        columns = process_column_mapping.get(current_process)

        # Only require mapping and advance when lot_condition == "MP"
        if (not columns or len(columns) < 6) and str(self.lot_condition).upper() == "MP":
            messagebox.showerror("Configuration Error", f"Process mapping for '{current_process}' is missing or invalid.")
            return

        quantity_in = self.quantity_in_entry.get()
        quantity_out = self.quantity_out_entry.get()

        try:
            # 1) Update lot_masterlist with measurement data (from CSV rows)
            if self.csv_rows_data:
                conn_master = sqlite3.connect(db_path_masterlist)
                cursor_master = conn_master.cursor()
                for csv_row in self.csv_rows_data:
                    try:
                        sensor_id = csv_row[0]
                        x1 = csv_row[1]
                        x2 = csv_row[2]
                        x3 = csv_row[3]
                        x4 = csv_row[4]
                        x5 = csv_row[5]
                        x6 = csv_row[6]
                    except IndexError:
                        continue
                    try:
                        cursor_master.execute("""
                            UPDATE lot_masterlist
                            SET BS_gap_to_GMR = ?, TS_gap_to_GMR = ?, BS_Gap_to_MR_Chip = ?, TS_Gap_to_MR_Chip = ?, PCB_Gap_to_BS1 = ?, PCB_Gap_to_BS2 = ?
                            WHERE sensor_id = ?
                        """, (x1, x2, x3, x4, x5, x6, sensor_id))
                    except sqlite3.OperationalError:
                        # columns missing, skip
                        pass
                conn_master.commit()
                conn_master.close()

            # 2) Update lot_tracking only if lot_condition == "MP" and mapping exists
            if columns and len(columns) >= 6 and str(self.lot_condition).upper() == "MP":
                conn = sqlite3.connect(db_path_tracking)
                cursor = conn.cursor()

                sensor_ids_in_table = [self.table.item(row)["values"][0] for row in self.table.get_children()]
                sensor_ids_with_defects = [self.table.item(row)["values"][0] for row in self.table.get_children() if self.table.item(row)["values"][1]]

                # Update rows present in table
                for row_id in self.table.get_children():
                    sid, defect, remarks = self.table.item(row_id)["values"]
                    cursor.execute(f"""
                        UPDATE lot_tracking
                        SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, {columns[3]}=?, {columns[4]}=?, {columns[5]}=?
                        WHERE lot_number=? AND sensor_id=?
                    """, (quantity_in, quantity_out, defect, remarks, proc_datetime, operator, lot_number, sid))

                # Remaining sensors
                cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot_number,))
                all_sensors_for_lot = [r[0] for r in cursor.fetchall()]
                remaining_sensors = set(all_sensors_for_lot) - set(sensor_ids_in_table)
                for sid in remaining_sensors:
                    cursor.execute(f"""
                        UPDATE lot_tracking
                        SET {columns[0]}=?, {columns[1]}=?, {columns[2]}='', {columns[3]}='', {columns[4]}=?, {columns[5]}=?
                        WHERE lot_number=? AND sensor_id=?
                    """, (quantity_in, quantity_out, proc_datetime, operator, lot_number, sid))

                # Try to update database_path file if exists
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

                # Advance current_process only if lot_condition == MP
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
            else:
                # mapping missing or lot_condition != MP: skip lot_tracking updates
                if str(self.lot_condition).upper() != "EVAL":
                    messagebox.showwarning("Warning", f"No process-column mapping available for '{current_process}'. No lot_tracking updates performed.")
                # If Eval: intentionally skip lot_tracking updates and do not advance current_process

            # 6) Export CSV
            base_folder = r"\\phlsvr08\BMS Data\Assembly Data\Assembly Measurement"
            current_year = time.strftime("%Y")
            current_month_name = time.strftime("%B")
            current_date_formatted = time.strftime("%m.%d.%Y")

            export_folder = os.path.join(base_folder, current_year, current_month_name, current_date_formatted)
            os.makedirs(export_folder, exist_ok=True)
            csv_filename = os.path.join(export_folder, f"{current_process}_{lot_number}.csv")

            if self.csv_rows_data:
                with open(csv_filename, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(["Lot Number", lot_number])
                    writer.writerow(["Processed Date and Time", proc_datetime])
                    writer.writerow(["Operator", operator])
                    writer.writerow([])
                    writer.writerow(["Sensor ID", "BS gap to GMR", "TS gap to GMR", "BS Gap to MR Chip", "TS Gap to MR Chip", "PCB Gap to BS1", "PCB Gap to BS2", "Judgement"])
                    for row_data in self.csv_rows_data:
                        writer.writerow(row_data)
                messagebox.showinfo("CSV Export", f"Data successfully exported to:\n{csv_filename}")

            # Final message
            if columns and len(columns) >= 6 and str(self.lot_condition).upper() == "MP":
                try:
                    next_proc_for_msg = process_flow[process_flow.index(current_process) + 1]
                except Exception:
                    next_proc_for_msg = current_process
                messagebox.showinfo("Save", f"Data saved successfully.\nNext process set to: {next_proc_for_msg}")
            else:
                messagebox.showinfo("Save", f"Data saved successfully.\nLot condition is '{self.lot_condition}'; lot_tracking was not advanced.")

            entries["Lot Number:"].focus_set()
            self.destroy()
            delete_action()
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"An error occurred: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

# it will validate inputs & open the popup which will perform DB write and CSV export.
def save_action():
    try:
        if not entries["Operator:"].get():
            messagebox.showerror("Error", "Operator field must be filled.")
            return

        csv_rows_data = []
        failed_sensor_list_local = []         # sensors with judgement == "Failed"
        blank_judgement_list_local = []       # sensors with judgement == "" (blank)
        combobox_candidates_local = []       # sensors to show in popup combobox (Failed or blank)
        sensor_list_local = []

        for row_idx in range(20):
            sensor_id = data_entry[row_idx][0].get().strip()
            if sensor_id:
                sensor_list_local.append(sensor_id)
                x1 = data_entry[row_idx][1].get().strip()
                x2 = data_entry[row_idx][2].get().strip()
                x3 = data_entry[row_idx][3].get().strip()
                x4 = data_entry[row_idx][4].get().strip()
                x5 = data_entry[row_idx][5].get().strip()
                x6 = data_entry[row_idx][6].get().strip()
                judgement = judgement_labels[row_idx].cget("text").strip()

                csv_rows_data.append([sensor_id, x1, x2, x3, x4, x5, x6, judgement])

                # Always collect failed and blank lists for quantities/records
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

        # Fetch lot condition (default to "MP" if not found)
        lot_condition = get_lot_condition(lot_number)

        # If lot_condition is Eval, do NOT populate the popup combobox with failed/blank sensors,
        # but keep failed/blank lists for quantity calculations and CSV.
        if str(lot_condition).upper() == "EVAL":
            combobox_candidates_local = []

        # Pass lot_condition into popup
        popup = BMSPopup(root, lot_number, current_process, operator,
                         sensor_list_local, combobox_candidates_local,
                         failed_sensor_list_local, blank_judgement_list_local, csv_rows_data, lot_condition)
        popup.grab_set()
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

delete_button = tk.Button(root, text="Clear Data", font=("Tahoma", 12, "bold"), padx=10, pady=1, bg="yellow", command=delete_action, relief='raised', borderwidth=3)
delete_button.place(x=350, y=50)
save_button = tk.Button(root, text="SAVE", font=("Tahoma", 12, "bold"), padx=32, pady=1, bg="orange", command=save_action, relief='raised', borderwidth=3)
save_button.place(x=350, y=100)

# Table headers
headers = ["No.", "Sensor ID", "BS gap to GMR", "TS gap to GMR", "BS Gap to MR Chip", "TS Gap to MR Chip", 
           "PCB Gap to BS1", "PCB Gap to BS2", "Judgement"]
header_positions = {
    "No.": (13, 165),
    "Sensor ID": (75, 165),
    "BS gap to GMR": (180, 165),
    "TS gap to GMR": (273, 165),
    "BS Gap to MR Chip": (350, 165),
    "TS Gap to MR Chip": (445, 165),
    "PCB Gap to BS1": (539, 165),
    "PCB Gap to BS2": (628, 165),
    "Judgement": (730, 165),
}
for header in headers:
    label = tk.Label(root, text=header, font=("Arial", 7, "bold"), bg="lightblue", relief="ridge")
    label.place(x=header_positions[header][0], y=header_positions[header][1])

# Table rows for data entry
data_entry = []
judgement_labels = []
vcmd = (root.register(validate_numeric_input), '%P')

for row in range(20):
    row_entries = []
    # Add numbering label
    number_label = tk.Label(root, text=str(row + 1), width=3, bg="lightblue", relief="ridge")
    number_label.place(x=10, y=185 + row*23)
    for col in range(7):
        if col == 0:
            entry = tk.Entry(root, width=20, justify='center')
            entry.place(x=45 + col*115, y=185 + row*23)
            entry.config(state="readonly")  # Set Sensor ID column to readonly initially
        else:
            entry = tk.Entry(root, width=12, validate="key", validatecommand=vcmd if col > 0 else None, justify='center')
            entry.place(x=180 + (col-1)*90, y=185 + row*23)
            entry.bind("<Return>", lambda event, r=row, c=col: navigate_on_enter(event, r, c))
            entry.config(state="readonly")  # measurement columns readonly at start
        row_entries.append(entry)
    data_entry.append(row_entries)

    # Add judgement label
    judgement_label = tk.Label(root, text="", width=10, bg="lightblue", relief="ridge")
    judgement_label.place(x=720, y=185 + row*23)
    judgement_labels.append(judgement_label)
    
# Specifications LabelFrame
specs_frame = tk.LabelFrame(root, text="Specifications", font=("Arial", 7, "bold"), bg="lightblue", relief="ridge")
specs_frame.place(x=480, y=0, width=300, height=160)

specs = [
    ["Measurement", "Lower Limit(mm)", "Upper Limit(mm)"],
    ["BS gap to GMR", "0.015", "0.315"],
    ["TS gap to GMR", "0.010", "0.190"],
    ["BS Gap to MR Chip", "0.000", "0.020"],
    ["TS Gap to MR Chip", "0.000", "0.020"],
    ["PCB Gap to BS1", "0.000", "0.050"],
    ["PCB Gap to BS2", "0.000", "0.050"]
]

for i, row in enumerate(specs):
    for j, value in enumerate(row):
        label = tk.Label(specs_frame, text=value, font=("Arial", 7), bg="lightblue", relief="ridge", width=15)
        label.grid(row=i, column=j, padx=1, pady=1)

# ---------- Video preview & OCR controls (placed to the right) ----------
video_label = tk.Label(root, bg="black")
video_label.place(x=800, y=30, width=DISPLAY_W, height=DISPLAY_H)

sensor_id_label = tk.Label(root, text="Sensor ID:", font=("Arial", 10), bg="lightblue")
sensor_id_label.place(x=850, y=280)
sensor_id_textbox = tk.Text(root, height=1, width=18, font=("Arial", 10))
sensor_id_textbox.place(x=940, y=280)
sensor_id_textbox.bind("<Return>", lambda event: validate_sensor_id())

threshold_label = tk.Label(root, text="Threshold:", font=("Arial", 8), bg="lightblue")
threshold_label.place(x=820, y=350)
threshold_scale = tk.Scale(root, from_=110, to=200, orient=tk.HORIZONTAL, length=200, bg="#407ec9", fg="white", font=("Arial", 8), resolution=5)
threshold_scale.set(175)
threshold_scale.place(x=900, y=350)

read_button = tk.Button(root, text="READ", command=capture_image_and_process, font=("Arial", 10), bg="#00cc44", fg="white", padx=10)
read_button.place(x=850, y=310)
toggle_button = tk.Button(root, text="Toggle View", command=lambda: globals().__setitem__('threshold_view', not threshold_view), font=("Arial", 10), bg="#407ec9", fg="white", padx=10)
toggle_button.place(x=950, y=310)

# Start camera preview
start_camera()

def on_closing():
    global cap
    try:
        if cap and cap.isOpened():
            cap.release()
    except Exception:
        pass
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
entries["Lot Number:"].focus_set()
root.mainloop()