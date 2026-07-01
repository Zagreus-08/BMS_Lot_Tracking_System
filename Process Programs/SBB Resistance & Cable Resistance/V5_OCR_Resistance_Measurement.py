import tkinter as tk
from tkinter import ttk, messagebox, Label, Button, Scale
import sqlite3
import time
import serial
import json
import os
import csv
from datetime import datetime

# OCR / camera imports
import cv2
from PIL import Image, ImageFilter, ImageOps, ImageTk
import pytesseract
import threading
import re

# ----- Config -----
db_path_tracking = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"
db_path_masterlist = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"
config_file_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\process_flow.json"

try:
    with open(config_file_path, 'r') as f:
        config = json.load(f)
    process_flow = config["process_flow"]
    process_column_mapping = config["process_column_mapping"]
except FileNotFoundError:
    messagebox.showerror("Configuration Error", f"Config file not found at: {config_file_path}")
    raise SystemExit
except json.JSONDecodeError:
    messagebox.showerror("Configuration Error", "Error decoding process_flow.json. Please check its format.")
    raise SystemExit

# ----- Tesseract / OCR config -----
# Update path if your Tesseract is installed elsewhere
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\a493353\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
custom_oem_psm_config = (
    '--oem 3 --psm 6 '
    '-c tessedit_char_whitelist="ABCDEFGIJKLMNOPQRSTVWXZ0123456789- "'
)

# ----- Helper: Lot Condition -----
def get_lot_condition(lot_number):
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

# ----- Serial setup -----
ser = serial.Serial()
ser.baudrate = 115200
ser.bytesize = serial.EIGHTBITS
ser.parity = serial.PARITY_NONE
ser.stopbits = serial.STOPBITS_ONE
ser.xonxoff = True
ser.timeout = 0.1

# ----- UI: main window -----
root = tk.Tk()
root.title("Resistance Measurement")
# default to the smaller geometry (camera hidden)
root.geometry("620x660")
root.configure(bg="lightblue")
root.resizable(False, False)

# ----- Global OCR / Camera state -----
cap = None
camera_index = 0
ocr_enabled = False  # whether OCR (camera) is active / allowed
DISPLAY_W, DISPLAY_H = 400, 300
threshold_view = False
last_successful_threshold = None  # Store the successful threshold value

# Common OCR confusion map: OCR_char -> likely_real_char
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


def _apply_confusions(s):
    if not s:
        return s
    return ''.join(OCR_CONFUSIONS.get(ch, ch) for ch in s)

# ----- Connection status label (declared early so functions can use it) -----
connection_status = tk.Label(root, text="Not Connected", font=("Arial", 12, "bold"), bg="lightblue", fg="red")
connection_status.place(x=455, y=135)

# Select serial port
def select_port(event):
    try:
        if ser.is_open:
            ser.close()
        selected_port = comport_combobox.get()
        ser.port = selected_port
        ser.open()
        ser.baudrate = 115200
        ser.bytesize = serial.EIGHTBITS
        ser.parity = serial.PARITY_NONE
        ser.stopbits = serial.STOPBITS_ONE
        ser.xonxoff = True
        ser.timeout = 0.1
        messagebox.showinfo("Serial", f"Connected to {selected_port}")
    except serial.SerialException as e:
        messagebox.showerror("Error", f"Failed to connect to selected serial port: {e}")

def update_connection_status():
    if ser and getattr(ser, "is_open", False):
        connection_status.config(text="Connected", fg="white", bg="green")
    else:
        connection_status.config(text="Not Connected", fg="red", bg="lightblue")
    root.after(1000, update_connection_status)

# ----- Serial read for Fluke QM -----
def read_with_qm():
    try:
        ser.flushInput()
        ser.flushOutput()
        ser.write(('QM' + '\r').encode('utf-8'))
        response = b''
        second_eol = False
        while True:
            c = ser.read(1)
            if c:
                response += c
                if c == b'\r':
                    if second_eol:
                        break
                    else:
                        second_eol = True
                else:
                    second_eol = False
            else:
                break
        return response
    except Exception:
        return b''

def decode_response(response):
    try:
        response_string = response.decode("utf-8")
        response_split = response_string.split('\r')
        if len(response_split) >= 2:
            measurement_split = response_split[1].split(',')
            if len(measurement_split) >= 1:
                return float(measurement_split[0])  # resistance value
    except Exception:
        pass
    return None

# ---------- OCR helpers ----------
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

def start_camera():
    global cap
    try:
        if cap and cap.isOpened():
            return
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            messagebox.showerror("Error", "Could not open camera.")
            cap = None
            return
        show_frame()
    except Exception as e:
        cap = None
        messagebox.showerror("Camera Error", f"Unable to start camera: {e}")

def stop_camera():
    global cap
    try:
        if cap and cap.isOpened():
            cap.release()
    except Exception:
        pass
    cap = None
    try:
        video_label.config(image="")
        video_label.imgtk = None
    except Exception:
        pass

def show_frame():
    global cap
    if not cap or not cap.isOpened():
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

def process_image_for_ocr_with_retries():
    """
    OPTIMIZED: Process full image with regex pattern detection.
    No manual cropping needed - automatically finds sensor ID anywhere in the image.
    """
    global threshold_view, last_successful_threshold
    try:
        if not ocr_enabled:
            root.after(0, lambda: messagebox.showwarning("OCR Disabled", "OCR is currently disabled for this process."))
            return

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
            img_gray = ImageOps.grayscale(image)
            img_sharp = img_gray.filter(ImageFilter.SHARPEN)
            img_binary = img_sharp.point(lambda p: 255 if p > threshold_value else 0)

            # Perform OCR on full image
            ocr_text = pytesseract.image_to_string(img_binary, config=custom_oem_psm_config)

            # Apply character replacements
            ocr_text = ocr_text.replace("O", "0").replace("D", "0").replace("H", "4")\
                               .replace("L", "1").replace("I", "1").replace("C", "2")\
                               .replace("b", "6").replace("G", "0").replace("P", "2")\
                               .replace("Q", "0").replace("|", "1").replace("S", "5")

            # Apply common OCR confusion corrections
            ocr_text = _apply_confusions(ocr_text)

            print(f"[OCR] Raw text (thr={threshold_value}): {ocr_text[:100]}")

            # Pattern for sensor ID: XX-XX-XXXXX-XXXXXX
            pattern = r'\b(\d{2})-(\d{2})-([A-Z0-9]{4,5}[A-Z]?)-(\d{6})\b'
            matches = re.findall(pattern, ocr_text)

            if matches:
                sensor_id = f"{matches[0][0]}-{matches[0][1]}-{matches[0][2]}-{matches[0][3]}"

                # Validate against remaining sensors
                if sensor_id in remaining_sensor_ids:
                    print(f"[OCR] ✓ Pattern detected: {sensor_id} - CORRECT (valid for this lot)")
                    print(f"✓ Success! Sensor ID '{sensor_id}' detected at threshold {threshold_value}")
                    threshold_scale.set(threshold_value)
                    last_successful_threshold = threshold_value
                    ocr_result = sensor_id
                    break
                elif sensor_id in already_scanned:
                    print(f"[OCR] ✓ Pattern detected: {sensor_id} - INCORRECT (already scanned)")
                    last_detected_pattern = sensor_id
                elif sensor_id in valid_ids:
                    # Sensor is in the lot but not in remaining (has defects or already scanned)
                    print(f"[OCR] ✓ Pattern detected: {sensor_id} - INCORRECT (has defects or already scanned)")
                    last_detected_pattern = sensor_id
                else:
                    print(f"[OCR] ✓ Pattern detected: {sensor_id} - INCORRECT (not in lot {lot_number})")
                    last_detected_pattern = sensor_id

            # Try lenient pattern
            lenient_pattern = r'(\d{2})[\s\-]?(\d{2})[\s\-]?([A-Z0-9]{4,6})[\s\-]?(\d{6})'
            lenient_matches = re.findall(lenient_pattern, ocr_text)

            if lenient_matches and not ocr_result:
                sensor_id = f"{lenient_matches[0][0]}-{lenient_matches[0][1]}-{lenient_matches[0][2]}-{lenient_matches[0][3]}"
                if sensor_id in remaining_sensor_ids:
                    print(f"[OCR] ✓ Pattern detected (lenient): {sensor_id} - CORRECT")
                    last_successful_threshold = threshold_value
                    ocr_result = sensor_id
                    break
                else:
                    print(f"[OCR] ✓ Pattern detected (lenient): {sensor_id} - INCORRECT")
                    last_detected_pattern = sensor_id
                    
                    # Try simple confusion substitutions (T->J, K->H, etc.)
                    mapped = _apply_confusions(sensor_id)
                    if mapped != sensor_id and mapped in remaining_sensor_ids:
                        print(f"[OCR] Mapped '{sensor_id}' -> '{mapped}' and matched remaining IDs")
                        last_successful_threshold = threshold_value
                        ocr_result = mapped
                        break

                    # Fuzzy match: compare sensor_id and its mapped variant against remaining IDs
                    best_match = None
                    best_dist = None
                    for variant in (sensor_id, mapped):
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
                        last_successful_threshold = threshold_value
                        break

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

            return

        print(f"Final OCR result: '{ocr_result}'")

        # Success - write to row
        def ui_update_success():
            write_ocr_to_row(ocr_result)

        root.after(0, ui_update_success)

    except Exception as e:
        root.after(0, lambda: messagebox.showerror("OCR Error", f"Error during OCR processing: {e}"))

def capture_image_and_process():
    if not ocr_enabled:
        messagebox.showwarning("OCR Disabled", "OCR is currently disabled for this process. Use barcode scanner to input Sensor ID.")
        return
    threading.Thread(target=process_image_for_ocr_with_retries, daemon=True).start()

def check_all_sensor_ids_written(lot_number):
    """
    Check whether all valid sensor IDs for the lot have been entered.
    If yes: notify user and make Sensor ID column read-only.
    """
    try:
        if not lot_number:
            return False
        valid_ids = set(get_valid_sensor_ids_for_lot(lot_number))
        if not valid_ids:
            return False
        entered = set()
        for r in range(20):
            v = data_entry[r][0].get().strip()
            if v:
                # normalize for comparison
                for sid in valid_ids:
                    if v.upper() == str(sid).upper():
                        entered.add(sid)
                        break
        if entered >= valid_ids:  # all required IDs present
            messagebox.showinfo("Information", "All Sensor IDs for this Lot have been entered.")
            # Make Sensor ID column read-only for all rows
            for r in range(20):
                try:
                    data_entry[r][0].config(state="readonly", bg="lightgreen")
                except Exception:
                    pass
            return True
    except Exception:
        pass
    return False

def write_ocr_to_row(sensor_text):
    """
    Write sensor_text into focused Sensor ID entry (or first empty) only if valid for the current Lot.
    If invalid, do not write and retain focus on the same Sensor ID entry.
    After successful write, enable measurement columns and check whether all sensors are entered.
    """
    lot_number = entries["Lot Number:"].get().strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number first.")
        entries["Lot Number:"].focus_set()
        return

    # determine target row: prefer focused sensor-id entry, else first empty
    focused = root.focus_get()
    target_row = None
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

    # get valid IDs for lot (case-insensitive match)
    valid_ids = get_valid_sensor_ids_for_lot(lot_number)
    # try to map sensor_text to exact valid id (preserve DB-cased id)
    matched_sid = None
    if valid_ids:
        s_up = sensor_text.strip().upper()
        for sid in valid_ids:
            if s_up == str(sid).upper():
                matched_sid = sid
                break

    # If we have a valid list and sensor_text not in it -> reject
    if valid_ids and not matched_sid:
        messagebox.showerror("Invalid Sensor ID", f"Sensor ID '{sensor_text}' does not belong to Lot '{lot_number}'. Please retry.")
        # ensure user can re-scan / edit same field
        try:
            data_entry[target_row][0].config(state="normal")
            data_entry[target_row][0].delete(0, tk.END)
            data_entry[target_row][0].focus_set()
        except Exception:
            pass
        return

    # Duplicate check (already-entered in table)
    for i in range(20):
        if i != target_row:
            existing = data_entry[i][0].get().strip()
            if existing and matched_sid and str(existing).upper() == str(matched_sid).upper():
                messagebox.showerror("Duplicate Sensor ID", f"Sensor ID '{matched_sid}' already entered in another row.")
                try:
                    data_entry[target_row][0].config(state="normal")
                    data_entry[target_row][0].delete(0, tk.END)
                    data_entry[target_row][0].focus_set()
                except Exception:
                    pass
                return
            elif existing and (not matched_sid) and str(existing).upper() == sensor_text.strip().upper():
                messagebox.showerror("Duplicate Sensor ID", f"Sensor ID '{sensor_text}' already entered in another row.")
                try:
                    data_entry[target_row][0].config(state="normal")
                    data_entry[target_row][0].delete(0, tk.END)
                    data_entry[target_row][0].focus_set()
                except Exception:
                    pass
                return

    # All good: write the canonical matched_sid if available, else sensor_text
    to_write = str(matched_sid) if matched_sid else sensor_text.strip()
    try:
        data_entry[target_row][0].config(state="normal")
        data_entry[target_row][0].delete(0, tk.END)
        data_entry[target_row][0].insert(0, to_write)
        data_entry[target_row][0].config(state="readonly", bg="lightgreen")
    except Exception:
        pass

    # Enable measurement columns for this row
    for c in range(1, 5):
        try:
            data_entry[target_row][c].config(state="normal")
        except Exception:
            pass

    # Focus first measurement column
    try:
        data_entry[target_row][1].focus_set()
    except Exception:
        pass

    # After successful entry, check whether all sensors are written
    check_all_sensor_ids_written(lot_number)

# ----- Insert resistance into entry -----
def insert_resistance_value(event, row, col):
    response = read_with_qm()
    resistance_value = decode_response(response)
    if resistance_value is not None:
        data_entry[row][col].config(state="normal")
        data_entry[row][col].delete(0, tk.END)
        if resistance_value > 2000:
            data_entry[row][col].insert(0, "OPEN")
        else:
            data_entry[row][col].insert(0, f"{resistance_value:.2f}")

# ----- Navigation / enter handling -----
def navigate_on_enter(event, row, col):
    if col == 0:  # Enter pressed on Sensor ID column
        barcode_validate_sensor_id(event, row)
        return

    insert_resistance_value(event, row, col)  # Insert measurement into the entry box

    next_col = col + 1
    next_row = row

    # If we just finished last measurement column (Vdd/Gnd is data_entry index 4 -> col==4)
    if next_col == 5:
        # Judge current row
        judge_row_values(row)

        # After judging, check whether all Sensor IDs for the lot are already written.
        lot_number = entries["Lot Number:"].get().strip()
        all_written = check_all_sensor_ids_written(lot_number)

        if all_written:
            # Make ALL table columns read-only (Sensor ID + measurements) and set Operator focus
            for r in range(20):
                for c in range(5):
                    try:
                        data_entry[r][c].config(state="readonly", bg="lightgreen")
                    except Exception:
                        pass
                try:
                    judgement_labels[r].config(bg="lightblue")
                except Exception:
                    pass
            try:
                entries["Operator:"].focus_set()
            except Exception:
                pass
            return

        # If not all written, prepare and focus next row's Sensor ID for OCR / manual entry
        next_row = row + 1
        if next_row < 20:
            try:
                data_entry[next_row][0].config(state="normal")
                data_entry[next_row][0].delete(0, tk.END)
                data_entry[next_row][0].config(bg="white")
                data_entry[next_row][0].focus_set()
            except Exception:
                pass
        return

    # Otherwise move to next measurement column
    if next_col < 5 and next_row < 20:
        data_entry[next_row][next_col].focus_set()

# ----- Validation helpers -----
def validate_numeric_input(P):
    if P == "" or P.replace(".", "", 1).isdigit() or P.upper() == "OPEN":
        return True
    return False

# Validate sensor id (barcode or manual)
def barcode_validate_sensor_id(event, row):
    """
    Validate manual Sensor ID typed into the entry and pressed Enter.
    If invalid: clear entry, keep focus on the same Sensor ID entry so user can retry.
    If valid: enable measurement columns and move focus to first measurement.
    """
    lot_number = entries["Lot Number:"].get().strip()
    sensor_id = data_entry[row][0].get().strip()

    if not lot_number or not sensor_id:
        messagebox.showwarning("Validation Failed", "Lot Number or Sensor ID is missing.")
        try:
            data_entry[row][0].config(state="normal")
            data_entry[row][0].focus_set()
        except Exception:
            pass
        return

    try:
        conn = sqlite3.connect(db_path_tracking)
        cur = conn.cursor()
        cur.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
        valid_ids = [r[0] for r in cur.fetchall()]
        conn.close()

        # map case-insensitively
        matched = None
        for sid in valid_ids:
            if sensor_id.upper() == str(sid).upper():
                matched = sid
                break

        if not matched and valid_ids:
            messagebox.showerror("Invalid Sensor ID", f"Sensor ID '{sensor_id}' does not belong to Lot '{lot_number}'.")
            # clear and retain focus so user can retry
            try:
                data_entry[row][0].config(state="normal")
                data_entry[row][0].delete(0, tk.END)
                data_entry[row][0].focus_set()
            except Exception:
                pass
            return

        # duplicates
        for i in range(20):
            if i != row and data_entry[i][0].get().strip():
                if matched and data_entry[i][0].get().strip().upper() == str(matched).upper():
                    messagebox.showerror("Duplicate Sensor ID", f"Sensor ID '{matched}' already entered in another row.")
                    try:
                        data_entry[row][0].config(state="normal")
                        data_entry[row][0].delete(0, tk.END)
                        data_entry[row][0].focus_set()
                    except Exception:
                        pass
                    return
                elif (not matched) and data_entry[i][0].get().strip().upper() == sensor_id.upper():
                    messagebox.showerror("Duplicate Sensor ID", f"Sensor ID '{sensor_id}' already entered in another row.")
                    try:
                        data_entry[row][0].config(state="normal")
                        data_entry[row][0].delete(0, tk.END)
                        data_entry[row][0].focus_set()
                    except Exception:
                        pass
                    return

        # success: ensure canonical stored (use matched when possible)
        if matched and matched != sensor_id:
            try:
                data_entry[row][0].config(state="normal")
                data_entry[row][0].delete(0, tk.END)
                data_entry[row][0].insert(0, matched)
                data_entry[row][0].config(state="readonly", bg="lightgreen")
            except Exception:
                pass
        else:
            try:
                data_entry[row][0].config(state="readonly", bg="lightgreen")
            except Exception:
                pass

        # enable measurement columns and focus first measurement
        for c in range(1, 5):
            try:
                data_entry[row][c].config(state="normal")
            except Exception:
                pass
        try:
            data_entry[row][1].focus_set()
        except Exception:
            pass

        # After successful entry, check whether all sensors are written
        check_all_sensor_ids_written(lot_number)

    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")

# ----- Header helper -----
def set_headers(current_process):
    if current_process == "SBB Resistance":
        headers = ["No.", "Sensor ID", "Coil-/+", "Coil-/Vb", "Va/Vb", "Vdd/Gnd", "Judgement"]
    elif current_process == "Cable Resistance":
        headers = ["No.", "Sensor ID", "48_turns", "Coil-/Vb", "Va/Vb", "Vdd/Gnd", "Judgement"]
    else:
        headers = ["No.", "Sensor ID", "Coil-/+", "Coil-/Vb", "Va/Vb", "Vdd/Gnd", "Judgement"]
    return headers

# ----- Camera UI creation (widgets created but not placed initially) -----
# We'll create the widgets and then place/forget them when toggling OCR.
video_label = Label(root, bg="black")

sensor_id_label = Label(root, text="Sensor ID:", font=("Arial", 14), bg="lightblue", fg="black")
sensor_id_textbox = tk.Text(root, height=1, width=17, font=("Arial", 14))
threshold_label = Label(root, text="Threshold Level\n(110-200):", font=("Arial", 14), bg="lightblue", fg="black")
threshold_scale = Scale(root, from_=110, to=200, orient=tk.HORIZONTAL, length=200, bg="#407ec9", fg="white", font=("Arial", 10), resolution=5)
threshold_scale.set(175)
read_button = Button(root, text="READ", command=capture_image_and_process, font=("Arial", 15), bg="#00cc44", fg="white", padx=20, pady=1)
toggle_button = Button(root, text="Toggle View", command=lambda: globals().__setitem__('threshold_view', not threshold_view), font=("Arial", 15), bg="#407ec9", fg="white", padx=20, pady=1)

# Place positions for camera UI (they are to the right of the smaller main window)
_CAMERA_PLACES = {
    "video": {"x": 650, "y": 30, "width": DISPLAY_W, "height": DISPLAY_H},
    "sensor_label": {"x": 690, "y": 340},
    "sensor_text": {"x": 795, "y": 340},
    "threshold_label": {"x": 650, "y": 415},
    "threshold_scale": {"x": 830, "y": 425},
    "read_button": {"x": 680, "y": 370},
    "toggle_button": {"x": 820, "y": 370},
}

def place_camera_widgets():
    try:
        video_label.place(x=_CAMERA_PLACES["video"]["x"], y=_CAMERA_PLACES["video"]["y"], width=_CAMERA_PLACES["video"]["width"], height=_CAMERA_PLACES["video"]["height"])
        sensor_id_label.place(x=_CAMERA_PLACES["sensor_label"]["x"], y=_CAMERA_PLACES["sensor_label"]["y"])
        sensor_id_textbox.place(x=_CAMERA_PLACES["sensor_text"]["x"], y=_CAMERA_PLACES["sensor_text"]["y"])
        threshold_label.place(x=_CAMERA_PLACES["threshold_label"]["x"], y=_CAMERA_PLACES["threshold_label"]["y"])
        threshold_scale.place(x=_CAMERA_PLACES["threshold_scale"]["x"], y=_CAMERA_PLACES["threshold_scale"]["y"])
        read_button.place(x=_CAMERA_PLACES["read_button"]["x"], y=_CAMERA_PLACES["read_button"]["y"])
        toggle_button.place(x=_CAMERA_PLACES["toggle_button"]["x"], y=_CAMERA_PLACES["toggle_button"]["y"])
    except Exception:
        pass

def hide_camera_widgets():
    try:
        video_label.place_forget()
        sensor_id_label.place_forget()
        sensor_id_textbox.place_forget()
        threshold_label.place_forget()
        threshold_scale.place_forget()
        read_button.place_forget()
        toggle_button.place_forget()
    except Exception:
        pass

def set_ocr_enabled(enabled):
    """
    Enable or disable OCR (camera) UI and runtime and adjust window size.
    When enabled=True:
      - window expanded to show camera (1070x660)
      - Camera widgets are placed
      - Camera capture started
      - ocr_enabled flag set
    When enabled=False:
      - Camera capture stopped and released
      - Camera widgets hidden
      - window shrunk to hide camera (620x660)
      - ocr_enabled flag unset
    """
    global ocr_enabled
    ocr_enabled = bool(enabled)
    if ocr_enabled:
        # expand UI so camera widgets are visible
        try:
            root.geometry("1070x660")
        except Exception:
            pass
        place_camera_widgets()
        start_camera()
    else:
        # stop camera and hide camera widgets, then shrink window
        stop_camera()
        hide_camera_widgets()
        try:
            root.geometry("620x660")
        except Exception:
            pass

# ----- Fetch lot info & prepare UI for manual/OCR entry -----
def on_current_process_change(event=None):
    """
    Called when the Current Process combobox changes (Eval case).
    Switch OCR enable/disable depending on selected process.
    """
    try:
        widget = entries.get("Current Process:")
        if isinstance(widget, ttk.Combobox):
            selected = widget.get()
        else:
            selected = widget.get() if widget else ""
        # Enable OCR only for SBB Resistance; for Cable Resistance use barcode scanner
        set_ocr_enabled(selected == "SBB Resistance")
    except Exception:
        pass

def fetch_lot_info(event=None):
    global sensor_ids_no_defects
    global current_process

    lot_number = entries["Lot Number:"].get().strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number.")
        return

    # Check connection status label text (assumes it's "Connected" when ok)
    if connection_status.cget("text") != "Connected":
        messagebox.showwarning("Warning", "Please set the communication port first.")
        delete_action()
        return

    conn_track = None
    conn_master = None
    conn_ml2 = None
    try:
        # 1) Get current_process from lot_tracking
        conn_track = sqlite3.connect(db_path_tracking)
        cur_track = conn_track.cursor()
        cur_track.execute("SELECT current_process FROM lot_tracking WHERE lot_number = ? LIMIT 1", (lot_number,))
        row = cur_track.fetchone()
        if not row:
            messagebox.showwarning("Warning", "Lot Number not found in the database.")
            conn_track.close()
            delete_action()
            return

        current_process = row[0]

        # 2) Determine lot condition (MP or Eval)
        lot_condition = get_lot_condition(lot_number)

        # 3) Replace or set the Current Process widget depending on lot_condition
        cur_widget = entries.get("Current Process:")
        place_x = place_y = None
        try:
            if cur_widget is not None:
                pi = cur_widget.place_info()
                if pi:
                    place_x = int(pi.get("x", 120))
                    place_y = int(pi.get("y", 65))
                else:
                    place_x = cur_widget.winfo_x()
                    place_y = cur_widget.winfo_y()
        except Exception:
            place_x, place_y = 120, 65

        if str(lot_condition).upper() == "EVAL":
            eval_choices = ["SBB Resistance", "Cable Resistance"]
            if not isinstance(entries.get("Current Process:"), ttk.Combobox):
                try:
                    if entries.get("Current Process:") is not None:
                        entries["Current Process:"].destroy()
                except Exception:
                    pass
                cb = ttk.Combobox(root, values=eval_choices, width=27, state="readonly")
                if current_process in eval_choices:
                    cb.set(current_process)
                else:
                    cb.set(eval_choices[0])
                cb.place(x=(place_x if place_x is not None else 120), y=(place_y if place_y is not None else 65))
                entries["Current Process:"] = cb
                # Bind to handle changes
                cb.bind("<<ComboboxSelected>>", on_current_process_change)
            else:
                cb = entries["Current Process:"]
                if current_process in cb.cget("values"):
                    cb.set(current_process)
                else:
                    cb.set(cb.cget("values")[0] if cb.cget("values") else current_process)
                # Ensure binding exists
                try:
                    cb.bind("<<ComboboxSelected>>", on_current_process_change)
                except Exception:
                    pass
        else:
            if isinstance(entries.get("Current Process:"), ttk.Combobox):
                try:
                    entries["Current Process:"].destroy()
                except Exception:
                    pass
                e = tk.Entry(root, width=30, justify='center')
                e.place(x=(place_x if place_x is not None else 120), y=(place_y if place_y is not None else 65))
                entries["Current Process:"] = e
            entries["Current Process:"].config(state="normal")
            entries["Current Process:"].delete(0, tk.END)
            entries["Current Process:"].insert(0, current_process)
            entries["Current Process:"].config(state="readonly")

        # 4) If MP, enforce the resistance-type check; if Eval, skip strict check
        if str(lot_condition).upper() == "MP":
            if "Resistance" not in current_process:
                messagebox.showerror("Error", "The lot number inputted is not for Resistance Measurement")
                conn_track.close()
                delete_action()
                return

        # 5) Determine previous-process defect columns (safely)
        try:
            current_index = process_flow.index(current_process)
        except ValueError:
            current_index = -1

        previous_defect_columns = []
        if current_index > 0:
            for proc in process_flow[:current_index]:
                if proc in process_column_mapping and isinstance(process_column_mapping[proc], (list, tuple)) and len(process_column_mapping[proc]) > 2:
                    previous_defect_columns.append(process_column_mapping[proc][2])

        # 6) Get sensors for this lot that have no defects in previous processes
        if previous_defect_columns:
            defect_conditions = " AND ".join(f"({col} IS NULL OR {col} = '')" for col in previous_defect_columns)
            query = f"SELECT sensor_id FROM lot_tracking WHERE lot_number = ? AND {defect_conditions}"
            cur_track.execute(query, (lot_number,))
            sensor_ids_no_defects = [r[0] for r in cur_track.fetchall()]
        else:
            cur_track.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
            sensor_ids_no_defects = [r[0] for r in cur_track.fetchall()]

        if not sensor_ids_no_defects:
            messagebox.showinfo("Information", "No sensors available for this process (all sensors have defects from previous processes).")
            conn_track.close()
            delete_action()
            return

        # 7) Check masterlist for existing measurement values for this process (apply to filtered sensors)
        conn_master = sqlite3.connect(db_path_masterlist)
        cur_master = conn_master.cursor()
        process_to_columns = {
            "Laser Marking and OCR": ["OCR_Reading"],
            "MR Chip Alignment Measurement": ["X_alignment_1", "Y_alignment_1", "X_alignment_2", "Y_alignment_2"],
            "MR Chip Height Measurement": ["mr_chip_height"],
            "SBB Resistance Measurement": ["SBB_Resistance_Coil_Pos", "SBB_Resistance_Coil_Vb", "SBB_Resistance_Va_Vb", "SBB_Resistance_Vdd_GnD"],
            "Assembly Measurement": ["BS_gap_to_GMR", "TS_gap_to_GMR", "BS_Gap_to_MR_Chip", "TS_Gap_to_MR_Chip", "PCB_Gap_to_BS1", "PCB_Gap_to_BS2"],
            "QA Inspection 1": ["QA_Inspection1_bottom", "QA_Inspection1_top"],
            "Top Molding Dimension": ["Top_Molding_Length", "Top_Molding_Width", "Top_Molding_Height"],
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

        if columns:
            sensor_ids_with_values = []
            for sid in sensor_ids_no_defects:
                try:
                    cur_master.execute(f"SELECT {', '.join(columns)} FROM lot_masterlist WHERE sensor_id = ?", (sid,))
                    r = cur_master.fetchone()
                    if r and all(value is not None for value in r):
                        sensor_ids_with_values.append(sid)
                except sqlite3.OperationalError:
                    # column(s) missing in masterlist, skip the check
                    sensor_ids_with_values = []
                    break

            if sensor_ids_with_values:
                conn_master.close()
                conn_track.close()
                messagebox.showinfo("Information", f"The following Sensor IDs already have values in '{current_process}': {', '.join(sensor_ids_with_values)}")
                return
        conn_master.close()

        # ---------- NEW BEHAVIOR ----------
        # Do NOT auto-populate Sensor IDs. Instead:
        # - Enable Sensor ID column entries (clear them)
        # - Keep measurement columns readonly
        # - Focus the first Sensor ID entry so OCR will write there
        for row_idx in range(20):
            # enable Sensor ID entry
            try:
                data_entry[row_idx][0].config(state="normal")
                data_entry[row_idx][0].delete(0, tk.END)
                data_entry[row_idx][0].config(bg="white")
            except Exception:
                pass
            # ensure measurement columns are readonly/cleared
            for col in range(1, 5):
                try:
                    data_entry[row_idx][col].config(state="readonly")
                    data_entry[row_idx][col].delete(0, tk.END)
                    data_entry[row_idx][col].config(bg="white")
                except Exception:
                    pass
            judgement_labels[row_idx].config(text="", bg="lightblue")

        # Focus the first Sensor ID entry (row 0) for OCR input
        try:
            data_entry[0][0].focus_set()
        except Exception:
            pass
        # Store filtered sensor ids for OCR validation / matching functions to use
        # (they'll be looked up again by get_valid_sensor_ids_for_lot when OCR runs)
        conn_track.close()

        # 9) Fill Connection/Cable fields from masterlist (by lot_number) if available
        conn_ml2 = sqlite3.connect(db_path_masterlist)
        cur_ml2 = conn_ml2.cursor()
        try:
            cur_ml2.execute("SELECT coil_connection, cable_length, cable_type FROM lot_masterlist WHERE lot_number = ? LIMIT 1", (lot_number,))
            res = cur_ml2.fetchone()
            if res:
                coil_connection, cable_length, cable_type = res
                if "Connection:" in entries:
                    entries["Connection:"].config(state="normal")
                    entries["Connection:"].delete(0, tk.END)
                    entries["Connection:"].insert(0, coil_connection)
                    entries["Connection:"].config(state="readonly")
                if "Cable Length:" in entries:
                    entries["Cable Length:"].config(state="normal")
                    entries["Cable Length:"].delete(0, tk.END)
                    entries["Cable Length:"].insert(0, cable_length)
                    entries["Cable Length:"].config(state="readonly")
                if "Cable Type:" in entries:
                    entries["Cable Type:"].config(state="normal")
                    entries["Cable Type:"].delete(0, tk.END)
                    entries["Cable Type:"].insert(0, cable_type)
                    entries["Cable Type:"].config(state="readonly")
        except sqlite3.Error:
            pass
        finally:
            conn_ml2.close()

        # IMPORTANT: Toggle OCR depending on the current_process.
        # For SBB Resistance -> enable OCR (and expand window)
        # For Cable Resistance -> disable OCR (and shrink window)
        try:
            set_ocr_enabled(current_process == "SBB Resistance")
        except Exception:
            pass

        return

    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")
        try:
            if conn_track:
                conn_track.close()
        except:
            pass
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")
        try:
            if conn_track:
                conn_track.close()
        except:
            pass

# ----- Judge logic (process-specific) -----
def judge_row_values(row):
    current_process = entries["Current Process:"].get()  # Get the current process

    if data_entry[row][0].get():  # Only judge rows with Sensor ID
        # Get the values for each measurement
        values = [
            data_entry[row][1].get(),
            data_entry[row][2].get(),
            data_entry[row][3].get(),
            data_entry[row][4].get(),
        ]

        # Define the limits and logic based on the current process
        if current_process == "SBB Resistance":
            connection = entries["Connection:"].get()
            if connection == "Thin film":
                limits = [
                    None,  # Coil-/+ limits
                    None,    # Coil-/Vb limits
                    (933, 1733),    # Va/Vb limits
                    (933, 1733)   # Vdd/Gnd limits
                ]
            elif connection == "Out coil":
                limits = [
                    None,  # Coil-/+ limits
                    None,    # Coil-/Vb limits
                    (933, 1733),    # Va/Vb limits
                    (933, 1733)   # Vdd/Gnd limits
                ]
            
        elif current_process == "Cable Resistance":
            connection = entries["Connection:"].get()
            cable_length = entries["Cable Length:"].get()
            cable_type = entries["Cable Type:"].get()
            
            # Determine limits based on Connection, Cable Length, and Cable Type
            if connection == "Thin film":
                if cable_length == "2.9m" and cable_type == "Oki":
                    limits = [None, (3.8, 4.6), (933, 1733), (933, 1733)]
                elif cable_length == "2.9m" and cable_type == "Taiyo":
                    limits = [None, (3.8, 4.6), (933, 1733), (933, 1733)]
                elif cable_length == "1.5m" and cable_type == "Oki":
                    limits = [None, (3.8, 4.6), (933, 1733), (933, 1733)]
                elif cable_length == "1.5m" and cable_type == "Taiyo":
                    limits = [None, (3.8, 4.6), (933, 1733), (933, 1733)]
                else:
                    judgement_labels[row].config(text="Invalid Cable Data", fg="red")
                    return
            elif connection == "Out coil":
                if cable_length == "2.9m" and cable_type == "Oki":
                    limits = [None, (3.8, 4.6), (933, 1733), (933, 1733)]
                elif cable_length == "2.9m" and cable_type == "Taiyo":
                    limits = [None, (3.8, 4.6), (933, 1733), (933, 1733)]
                elif cable_length == "1.5m" and cable_type == "Oki":
                    limits = [None, (3.8, 4.6), (933, 1733), (933, 1733)]
                elif cable_length == "1.5m" and cable_type == "Taiyo":
                    limits = [None, (3.8, 4.6), (933, 1733), (933, 1733)]
                else:
                    judgement_labels[row].config(text="Invalid Cable Data", fg="red")
                    return
            else:
                # Unrecognized connection type
                judgement_labels[row].config(text="Invalid Connection", fg="red")
                return
        else:
            # Default case if the process isn't recognized (optional)
            judgement_labels[row].config(text="Invalid Process", fg="red")
            return

        # Initialize a flag for row status
        row_failed = False

        # Loop through each value and its corresponding limit
        for col, (value, limit) in enumerate(zip(values, limits), start=1):
            try:
                # Column 2 (Coil-/Vb) may legitimately be the string "OPEN" in some processes.
                # Accept "OPEN" as valid; otherwise fall through to numeric checking when limits are provided.
                if col == 2:
                    if value.strip().upper() == "OPEN":
                        data_entry[row][col].config(bg="white")
                        continue
                    # If no numeric limits are provided for this column, treat any non-empty value as OK
                    if limit is None:
                        data_entry[row][col].config(bg="white")
                        continue

                # Check numeric columns
                if limit is not None:
                    lower_limit, upper_limit = limit
                    value = float(value)
                    # Check if the value is within the limits (inclusive)
                    if lower_limit <= value <= upper_limit:
                        data_entry[row][col].config(bg="white")
                    else:
                        row_failed = True
                        data_entry[row][col].config(bg="red")
            except ValueError:
                # Invalid input (e.g., non-numeric), mark as failed
                row_failed = True
                data_entry[row][col].config(bg="red")

        # Update the Judgement label based on the row's status
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

# ----- Delete helper -----
def delete_action():
    for entry in entries.values():
        try:
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.config(state="readonly" if entry == entries["Current Process:"] else "normal")
        except Exception:
            pass
    for r in range(20):
        for c in range(5):
            try:
                data_entry[r][c].config(state="normal")
                data_entry[r][c].delete(0, tk.END)
                data_entry[r][c].config(state="readonly", bg="white")
            except Exception:
                pass
        try:
            judgement_labels[r].config(text="", bg="lightblue")
        except Exception:
            pass

class BMSPopup(tk.Toplevel):
    def __init__(self, master, lot_number, current_process, operator,
                 sensor_list, combobox_candidates, failed_sensor_list, blank_judgement_list, csv_rows_data, lot_condition="MP"):
        super().__init__(master)
        self.title("BMS Lot Tracking System - Popup")
        self.geometry("615x455")
        self.configure(bg='#3a6ba8')
        self.resizable(False, False)

        # Store inputs
        self.lot_number = lot_number
        self.current_process = current_process
        self.operator = operator
        self.sensor_list = sensor_list[:]
        self.combobox_candidates = combobox_candidates[:]
        self.failed_sensor_list = failed_sensor_list[:]
        self.blank_judgement_list = blank_judgement_list[:]
        self.csv_rows_data = csv_rows_data[:]
        self.lot_condition = str(lot_condition).strip()  # "MP" or "EVAL"

        # Title
        tk.Label(self, text="BMS Lot Tracking System", font=("BiomeW04-Bold", 20, "bold"),
                 bg='#3a6ba8', fg="orange").place(x=20, y=0)

        # Lot number (readonly)
        tk.Label(self, text="Lot Number:", bg='#3a6ba8', fg="white").place(x=5, y=45)
        self.lot_number_entry = tk.Entry(self, width=31)
        self.lot_number_entry.place(x=105, y=45)
        self.lot_number_entry.insert(0, lot_number)
        self.lot_number_entry.config(state="readonly")

        # Current process (readonly)
        tk.Label(self, text="Current Process:", bg='#3a6ba8', fg="white").place(x=5, y=75)
        self.current_process_entry = tk.Entry(self, width=31)
        self.current_process_entry.place(x=105, y=75)
        self.current_process_entry.insert(0, current_process)
        self.current_process_entry.config(state="readonly")

        # Sensor ID Combobox (now populated with failed OR no-judgement sensors unless Eval, then empty)
        tk.Label(self, text="Sensor ID:", bg='#3a6ba8', fg="white").place(x=5, y=105)
        self.sensor_id_combobox = ttk.Combobox(self, values=self.combobox_candidates, width=28)
        self.sensor_id_combobox.place(x=105, y=105)
        if self.combobox_candidates:
            self.sensor_id_combobox.set(self.combobox_candidates[0])

        # Defect & remarks
        tk.Label(self, text="Defect:", bg='#3a6ba8', fg="white").place(x=5, y=135)
        self.defect_entry = tk.Entry(self, width=31); self.defect_entry.place(x=105, y=135)
        tk.Label(self, text="Remarks:", bg='#3a6ba8', fg="white").place(x=5, y=165)
        self.remarks_entry = tk.Entry(self, width=31); self.remarks_entry.place(x=105, y=165)

        # Quantity IN/OUT, date, operator
        tk.Label(self, text="Quantity IN:", bg='#3a6ba8', fg="white").place(x=320, y=45)
        self.quantity_in_entry = tk.Entry(self, width=15); self.quantity_in_entry.place(x=410, y=45)
        tk.Label(self, text="Quantity OUT:", bg='#3a6ba8', fg="white").place(x=320, y=75)
        self.quantity_out_entry = tk.Entry(self, width=15); self.quantity_out_entry.place(x=410, y=75)
        tk.Label(self, text="Date:", bg='#3a6ba8', fg="white").place(x=320, y=105)
        self.date_time_label = tk.Label(self, text="", bg='white', width=19); self.date_time_label.place(x=410, y=105)
        tk.Label(self, text="Operator:", bg='#3a6ba8', fg="white").place(x=320, y=135)
        self.operator_entry = tk.Entry(self, width=22); self.operator_entry.place(x=410, y=135)
        self.operator_entry.insert(0, self.operator)

        # Buttons
        tk.Button(self, text="Export Defects / Remarks", command=self.export_data, bg="green", fg="white",
                  font=("Tahoma", 10, "bold"), padx=20, pady=1, relief='raised', borderwidth=3).place(x=20, y=200)
        tk.Button(self, text="CLEAR", command=self.clear_fields, bg="yellow", font=("Tahoma", 16, "bold"),
                  padx=10, pady=1, relief='raised', borderwidth=3).place(x=320, y=185)
        tk.Button(self, text="SAVE", command=self.save_data_and_advance, bg="green", fg="white",
                  font=("Tahoma", 16, "bold"), padx=10, pady=1, relief='raised', borderwidth=3).place(x=460, y=185)
        tk.Button(self, text="DELETE Defects / Remarks", command=self.delete_selected_row, bg="red", fg="white",
                  font=("Tahoma", 10, "bold"), padx=20, pady=1, relief='raised', borderwidth=3).place(x=20, y=235)

        # Table
        self.columns = ("Sensor ID", "Defects", "Remarks")
        self.table = ttk.Treeview(self, columns=self.columns, show="headings", height=7)
        for col in self.columns:
            self.table.heading(col, text=col)
        self.table.place(x=5, y=280, width=600, height=140)

        # Quantities
        total_sensors = len(self.sensor_list)
        reduced_count = len(self.failed_sensor_list) + len(self.blank_judgement_list)
        self.quantity_in_entry.delete(0, tk.END); self.quantity_in_entry.insert(0, str(total_sensors))
        self.quantity_out_entry.delete(0, tk.END); self.quantity_out_entry.insert(0, str(max(0, total_sensors - reduced_count)))

        # Start time updater
        self.update_time()

    def update_time(self):
        now = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        self.date_time_label.config(text=now)
        self.after(1000, self.update_time)

    def clear_fields(self):
        self.defect_entry.delete(0, tk.END)
        self.remarks_entry.delete(0, tk.END)

    def delete_selected_row(self):
        selected = self.table.selection()
        if selected:
            self.table.delete(selected)
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

        existing_ids = [self.table.item(r)["values"][0] for r in self.table.get_children()]
        if sensor_id in existing_ids:
            messagebox.showwarning("Input Error", "Sensor ID already exists in the table.")
            return

        if sensor_id:
            self.table.insert('', 'end', values=(sensor_id, defect, remarks))
            self.update_quantity_out()
            self.clear_fields()
        else:
            messagebox.showwarning("Input Error", "Please select Sensor ID.")

    def update_quantity_out(self):
        try:
            qin = int(self.quantity_in_entry.get())
        except ValueError:
            qin = 0
        defect_count = len([self.table.item(r)["values"][1] for r in self.table.get_children() if self.table.item(r)["values"][1]])
        self.quantity_out_entry.delete(0, tk.END)
        self.quantity_out_entry.insert(0, str(qin - defect_count))

    def save_data_and_advance(self):
        # Ensure operator is provided
        if not self.operator_entry.get().strip():
            messagebox.showwarning("Input Error", "Please enter Operator.")
            return
    
        # If a Sensor ID is selected in the combobox, require it to be added to the table with a defect
        selected_sensor = self.sensor_id_combobox.get().strip()
        if selected_sensor:
            found = False
            for iid in self.table.get_children():
                sid, defect, remarks = self.table.item(iid)["values"]
                if sid == selected_sensor and str(defect).strip():
                    found = True
                    break
            if not found:
                messagebox.showwarning(
                    "Input Error",
                    "Please add a defect entry for the selected Sensor ID or clear selection."
                )
                return
    
        lot_number = self.lot_number
        current_process = self.current_process
        operator = self.operator_entry.get().strip()
        proc_datetime = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    
        # Get mapping for current process (may be None)
        columns = process_column_mapping.get(current_process)
    
        # If MP require mapping to update lot_tracking; if EVAL skip lot_tracking updates
        if (not columns or len(columns) < 6) and self.lot_condition.upper() == "MP":
            messagebox.showerror("Configuration Error", f"Process mapping for '{current_process}' is missing or invalid.")
            return
    
        # Build lists for CSV/quantities
        sensor_ids_in_table = [self.table.item(r)["values"][0] for r in self.table.get_children()]
        sensor_ids_with_defects = [self.table.item(r)["values"][0] for r in self.table.get_children() if self.table.item(r)["values"][1]]
    
        # 1) Update lot_masterlist with measurement data (from MRChip table) using your exact logic
        try:
            if self.csv_rows_data:
                conn_master = sqlite3.connect(db_path_masterlist)
                cursor_master = conn_master.cursor()
                for row in self.csv_rows_data:
                    # Expect row = [sensor_id, val1, val2, val3, val4, ...]
                    sensor_id = row[0]
                    val1 = row[1] if len(row) > 1 else None
                    val2 = row[2] if len(row) > 2 else None
                    val3 = row[3] if len(row) > 3 else None
                    val4 = row[4] if len(row) > 4 else None
    
                    if current_process == "SBB Resistance":
                        try:
                            cursor_master.execute("""
                                UPDATE lot_masterlist
                                SET SBB_Resistance_Coil_Pos = ?, SBB_Resistance_Coil_Vb = ?, SBB_Resistance_Va_Vb = ?, SBB_Resistance_Vdd_GnD = ?
                                WHERE sensor_id = ?
                            """, (val1, val2, val3, val4, sensor_id))
                        except sqlite3.OperationalError:
                            pass
                    elif current_process == "Cable Resistance":
                        try:
                            cursor_master.execute("""
                                UPDATE lot_masterlist
                                SET Cable_Resistance_48_turns = ?, Cable_Resistance_Coil_Vb = ?, Cable_Resistance_Va_Vb = ?, Cable_Resistance_Vdd_GnD = ?
                                WHERE sensor_id = ?
                            """, (val1, val2, val3, val4, sensor_id))
                        except sqlite3.OperationalError:
                            pass
                    # else: do nothing for other processes here
                conn_master.commit()
                conn_master.close()
        except sqlite3.Error:
            # non-fatal, continue
            pass
    
        # 2) Update lot_tracking only if MP and mapping exists
        if columns and len(columns) >= 6 and self.lot_condition.upper() == "MP":
            try:
                conn_t = sqlite3.connect(db_path_tracking)
                cur_t = conn_t.cursor()
    
                # Update rows present in popup table
                for iid in self.table.get_children():
                    sid, defect, remarks = self.table.item(iid)["values"]
                    try:
                        cur_t.execute(f"""
                            UPDATE lot_tracking
                            SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, {columns[3]}=?, {columns[4]}=?, {columns[5]}=?
                            WHERE lot_number=? AND sensor_id=?
                        """, (self.quantity_in_entry.get(), self.quantity_out_entry.get(), defect, remarks, proc_datetime, operator, lot_number, sid))
                    except sqlite3.OperationalError:
                        # mapping references missing columns — skip for this row
                        pass
    
                # For remaining sensors, update IN/OUT and clear defect/remarks
                try:
                    cur_t.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot_number,))
                    all_sids = [r[0] for r in cur_t.fetchall()]
                except sqlite3.Error:
                    all_sids = []
                remaining = set(all_sids) - set(sensor_ids_in_table)
                for sid in remaining:
                    try:
                        cur_t.execute(f"""
                            UPDATE lot_tracking
                            SET {columns[0]}=?, {columns[1]}=?, {columns[2]}='', {columns[3]}='', {columns[4]}=?, {columns[5]}=?
                            WHERE lot_number=? AND sensor_id=?
                        """, (self.quantity_in_entry.get(), self.quantity_out_entry.get(), proc_datetime, operator, lot_number, sid))
                    except sqlite3.OperationalError:
                        pass
    
                # Try to update database_path file (if provided)
                try:
                    cur_t.execute("SELECT database_path FROM lot_tracking WHERE lot_number=? LIMIT 1", (lot_number,))
                    res = cur_t.fetchone()
                    if res and res[0]:
                        fp = res[0]
                        try:
                            if os.path.isfile(fp):
                                with open(fp, 'r') as f:
                                    lines = f.readlines()
                                with open(fp, 'w') as f:
                                    for ln in lines:
                                        if ln.strip() not in sensor_ids_with_defects:
                                            f.write(ln)
                        except Exception:
                            pass
                except sqlite3.Error:
                    pass
    
                # Advance current_process
                try:
                    next_proc = process_flow[process_flow.index(current_process) + 1]
                except Exception:
                    next_proc = current_process
                try:
                    cur_t.execute("UPDATE lot_tracking SET current_process=? WHERE lot_number=?", (next_proc, lot_number))
                except sqlite3.OperationalError:
                    pass
    
                conn_t.commit()
                conn_t.close()
            except sqlite3.Error:
                # non-fatal: continue
                pass
        else:
            # Eval or no mapping: skip lot_tracking updates
            pass
    
        # 3) Export CSV (always allowed) and show confirmation
        if self.csv_rows_data:
            base_folder_map = {
                "SBB Resistance": r"\\phlsvr08\BMS Data\Assembly Data\SBB Resistance Measurement",
                "Cable Resistance": r"\\phlsvr08\BMS Data\Assembly Data\Cable Soldering Resistance",
            }
            base_folder = base_folder_map.get(current_process, r"\\phlsvr08\BMS Data\Assembly Data\Resistance")
            y = time.strftime("%Y"); m = time.strftime("%B"); d = time.strftime("%m.%d.%Y")
            export_folder = os.path.join(base_folder, y, m, d)
            os.makedirs(export_folder, exist_ok=True)
            csv_filename = os.path.join(export_folder, f"{current_process}_{lot_number}.csv")
            try:
                with open(csv_filename, 'w', newline='') as f:
                    w = csv.writer(f)
                    w.writerow(["Lot Number", lot_number])
                    w.writerow(["Processed Date and Time", proc_datetime])
                    w.writerow(["Operator", operator]); w.writerow([])
                    if current_process == "SBB Resistance":
                        headers = ["Sensor ID", "Coil-/+", "Coil-/Vb", "Va/Vb", "Vdd/Gnd", "Judgement"]
                    else:
                        headers = ["Sensor ID", "Val1", "Val2", "Val3", "Val4", "Judgement"]
                    w.writerow(headers)
                    for r in self.csv_rows_data:
                        w.writerow(r)
                messagebox.showinfo("CSV Export", f"Data successfully exported to:\n{csv_filename}")
            except Exception:
                messagebox.showwarning("CSV Export", f"Could not export CSV to:\n{csv_filename}")
    
        # Final message
        if columns and len(columns) >= 6 and self.lot_condition.upper() == "MP":
            try:
                next_msg = process_flow[process_flow.index(current_process) + 1]
            except Exception:
                next_msg = current_process
            messagebox.showinfo("Save", f"Data saved successfully.\nNext process set to: {next_msg}")
        else:
            messagebox.showinfo("Save", f"Data saved successfully.\nLot condition is '{self.lot_condition}'; lot_tracking was not advanced.")
    
        # Cleanup and close popup
        entries["Lot Number:"].focus_set()
        self.destroy()
        delete_action()

# ----- save_action wrapper -----
def save_action_wrapper():
    try:
        if not entries["Operator:"].get():
            messagebox.showerror("Error", "Operator field must be filled.")
            return

        csv_rows_data = []
        failed_sensor_list_local = []
        blank_judgement_list_local = []
        combobox_candidates_local = []
        sensor_list_local = []

        for r in range(20):
            sid = data_entry[r][0].get().strip()
            if sid:
                sensor_list_local.append(sid)
                v1 = data_entry[r][1].get().strip()
                v2 = data_entry[r][2].get().strip()
                v3 = data_entry[r][3].get().strip()
                v4 = data_entry[r][4].get().strip()
                j = judgement_labels[r].cget("text").strip()
                csv_rows_data.append([sid, v1, v2, v3, v4, j])
                if j == "Failed":
                    if sid not in failed_sensor_list_local:
                        failed_sensor_list_local.append(sid)
                    if sid not in combobox_candidates_local:
                        combobox_candidates_local.append(sid)
                elif j == "":
                    if sid not in blank_judgement_list_local:
                        blank_judgement_list_local.append(sid)
                    if sid not in combobox_candidates_local:
                        combobox_candidates_local.append(sid)

        if not sensor_list_local:
            messagebox.showwarning("Warning", "No Sensor IDs entered.")
            return

        lot_number = entries["Lot Number:"].get().strip()
        current_process = entries["Current Process:"].get().strip()
        operator = entries["Operator:"].get().strip()

        lot_condition = get_lot_condition(lot_number)
        if str(lot_condition).upper() == "EVAL":
            combobox_candidates_local = []
        # Validate that all required sensor IDs for this lot have been entered
        try:
            # Prefer filtered sensor list (no defects) if available
            required = None
            if 'sensor_ids_no_defects' in globals() and isinstance(sensor_ids_no_defects, (list, tuple)) and sensor_ids_no_defects:
                required = {str(s).strip().upper() for s in sensor_ids_no_defects}
            else:
                required = {str(s).strip().upper() for s in get_valid_sensor_ids_for_lot(lot_number)}

            entered = {str(s).strip().upper() for s in sensor_list_local}
            missing = sorted(list(required - entered)) if required else []
            if missing:
                # Show a clear error listing missing sensor IDs and block save
                sample = ", ".join(missing[:20])
                messagebox.showerror("Missing Sensors",
                                     f"Cannot save: {len(missing)} required sensor(s) missing for Lot '{lot_number}'.\n\nMissing (first 20): {sample}\n\nPlease scan/enter all required Sensor IDs before saving.")
                return
        except Exception:
            # If validation fails unexpectedly, prevent silent continue — block save and ask user to retry
            messagebox.showerror("Validation Error", "An error occurred while validating required Sensor IDs. Please retry fetching lot info and try again.")
            return

        popup = BMSPopup(root, lot_number, current_process, operator,
                         sensor_list_local, combobox_candidates_local,
                         failed_sensor_list_local, blank_judgement_list_local, csv_rows_data, lot_condition)
        popup.grab_set()
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

# ----- Main UI construction -----
title_label = tk.Label(root, text="Resistance Measurement", font=("BiomeW04-Bold", 20, "bold"), bg="lightblue")
title_label.place(x=10, y=0)

# COM port combobox
port_list = ['COM' + str(i) for i in range(1, 20)]
tk.Label(root, text='Comm Port:', font=("Tahoma", 10, "bold"), bg="lightblue").place(x=380, y=10)
comport_combobox = ttk.Combobox(root, values=port_list, state="readonly"); comport_combobox.set("Select Port")
comport_combobox.bind("<<ComboboxSelected>>", select_port); comport_combobox.place(x=460, y=10)
connection_status.place(x=455, y=135)
update_connection_status()

# Entries
labels = ["Lot Number:", "Current Process:", "Date and Time:", "Operator:", "Connection:", "Cable Length:", "Cable Type:"]
entries = {}
label_positions = {"Lot Number:": (10, 40), "Current Process:": (10, 65), "Date and Time:": (10, 90), "Operator:": (10, 115), "Connection:": (10, 140), "Cable Length:": (320, 40), "Cable Type:": (320, 65)}
entry_positions = {"Lot Number:": (115, 40), "Current Process:": (115, 65), "Date and Time:": (115, 90), "Operator:": (115, 115), "Connection:": (115, 140), "Cable Length:": (425, 40), "Cable Type:": (425, 65)}
for lt in labels:
    tk.Label(root, text=lt, font=("Arial", 10), bg="lightblue").place(x=label_positions[lt][0], y=label_positions[lt][1])
    e = tk.Entry(root, width=30, justify='center'); e.place(x=entry_positions[lt][0], y=entry_positions[lt][1]); entries[lt] = e
entries["Date and Time:"].config(state="readonly"); update_datetime()
entries["Lot Number:"].bind("<Return>", fetch_lot_info)

# Buttons
delete_button = tk.Button(root, text="Clear Data", font=("Tahoma", 12, "bold"), padx=10, pady=1, bg="yellow", command=delete_action, relief='raised', borderwidth=3)
delete_button.place(x=465, y=95)
save_button = tk.Button(root, text="SAVE", font=("Tahoma", 12, "bold"), padx=32, pady=1, bg="orange", command=lambda: save_action_wrapper(), relief='raised', borderwidth=3)
save_button.place(x=325, y=95)

# Table headers (static)
headers = ["No.", "Sensor ID", "Coil-/+", "Coil-/Vb", "Va/Vb", "Vdd/Gnd", "Judgement"]
header_positions = {"No.":(10,170), "Sensor ID":(75,170), "Coil-/+":(190,170), "Coil-/Vb":(265,170), "Va/Vb":(355,170), "Vdd/Gnd":(427,170), "Judgement":(510,170)}
for h in headers:
    tk.Label(root, text=h, font=("Arial", 10, "bold"), bg="lightblue", relief="ridge").place(x=header_positions[h][0], y=header_positions[h][1])

# Data table
data_entry = []
judgement_labels = []
vcmd = (root.register(validate_numeric_input), '%P')
for row in range(20):
    row_entries = []
    tk.Label(root, text=str(row+1), width=3, bg="lightblue", relief="ridge").place(x=10, y=200 + row*23)
    for col in range(5):
        if col == 0:
            e = tk.Entry(root, width=20, justify='center')
            e.place(x=45 + col*100, y=200 + row*23)
            e.config(state="readonly")
            e.bind("<Return>", lambda event, r=row: barcode_validate_sensor_id(event, r))
        else:
            e = tk.Entry(root, width=10, validate="key", validatecommand=vcmd, justify='center')
            e.place(x=180 + (col-1)*82, y=200 + row*23)
            e.config(state="readonly")
            e.bind("<Return>", lambda event, r=row, c=col: navigate_on_enter(event, r, c))
        row_entries.append(e)
    data_entry.append(row_entries)
    jl = tk.Label(root, text="", width=10, bg="lightblue", relief="ridge"); jl.place(x=510, y=200 + row*23)
    judgement_labels.append(jl)

# Initially hide camera widgets and ensure OCR is off (Camera not started)
hide_camera_widgets()
ocr_enabled = False

def on_closing():
    global cap
    if cap and getattr(cap, "isOpened", lambda: False)():
        try:
            cap.release()
        except Exception:
            pass
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
entries["Lot Number:"].focus_set()
update_connection_status()
root.mainloop()