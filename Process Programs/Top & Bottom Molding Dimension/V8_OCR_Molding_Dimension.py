# Full updated script with the fix: when all Sensor IDs are entered we only lock the Sensor ID column
# and keep measurement fields enabled. After entering the final Sensor ID the measurement fields for
# that last row remain enabled (focus moves to the first empty measurement), not to Operator.

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

# Define the paths to the databases
db_path_tracking = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"
db_path_masterlist = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"

# Define the absolute path to your config.json
config_file_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\process_flow.json"

# Path to molding specs editable JSON on server
molding_specs_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\molding_specs.json"

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

# Path to Tesseract executable (update if needed)
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\a493353\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

custom_oem_psm_config = (
    '--oem 3 --psm 6 '
    '-c tessedit_char_whitelist="ABCDEFGIJKLMNOPQRSTVWXZ0123456789- "'
)

# OCR temporary image paths (optional)
before_image_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\OCRBefore.png"
save_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\OCRAfter.png"

# Globals for OCR/camera
DISPLAY_W, DISPLAY_H = 320, 240
camera_index = 0
cap = None
threshold_view = False
ocr_allowed = False  # whether current process uses OCR

# Global list used by fetch_lot_info and OCR functions
sensor_ids_no_defects = []  # expected sensor IDs for the lot

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

# Create the main application window
root = tk.Tk()
root.title("Molding Dimension")
# default to the small geometry (camera hidden)
root.geometry("540x650")
root.configure(bg="lightblue")
root.resizable(False, False)

# ----- Helper functions / DB helpers -----
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

# Removed normalize_ocr_text - using fuzzy matching instead


def load_molding_specs():
    """Load molding specs JSON from network path. Returns dict or None on failure."""
    try:
        if os.path.isfile(molding_specs_path):
            with open(molding_specs_path, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return None


def get_molding_limits(process_name):
    """Return list of (low, high) tuples for Length, Width, Height.
    Falls back to built-in defaults if JSON missing or invalid.
    """
    specs = load_molding_specs()
    if specs and isinstance(specs, dict):
        proc = specs.get(process_name)
        if proc and isinstance(proc, dict):
            try:
                L = proc.get('Length')
                W = proc.get('Width')
                H = proc.get('Height')
                if L and W and H and len(L) == 2 and len(W) == 2 and len(H) == 2:
                    return [(float(L[0]), float(L[1])), (float(W[0]), float(W[1])), (float(H[0]), float(H[1]))]
            except Exception:
                pass

    # Fallback defaults (previous hardcoded values)
    if process_name == "Top Molding Dimension":
        return [(8.30, 8.70), (8.30, 8.70), (4.35, 5.35)]
    elif process_name == "Bottom Molding Dimension":
        return [(5.30, 6.30), (7.10, 8.10), (6.25, 7.45)]
    return None

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

# Removed find_matching_sensor - using fuzzy matching instead

def perform_ocr_on_pil_image(pil_img, threshold):
    """
    OPTIMIZED: Perform OCR on full image and extract sensor ID using regex pattern.
    No manual cropping needed - automatically detects sensor ID format.
    """
    import re
    try:
        # Convert to grayscale and enhance
        img = pil_img.convert("L")
        img = img.filter(ImageFilter.SHARPEN)
        
        # Apply binary threshold
        img = img.point(lambda p: 255 if p > threshold else 0)
        
        # Perform OCR on full image
        ocr_result = pytesseract.image_to_string(img, config=custom_oem_psm_config)
        
        # Apply OCR confusion map first (common char confusion corrections)
        try:
            ocr_result = _apply_confusions(ocr_result)
        except Exception:
            pass

        # Avoid blanket letter->digit replacements here; rely on _apply_confusions and
        # normalization/fuzzy matching later to map OCR text to canonical DB IDs.
        
        print(f"[OCR] Raw text (thr={threshold}): {ocr_result[:150]}")
        
        # Pattern for sensor ID: XX-XX-XXXXX-XXXXXX
        # Format: 2digits-2digits-4-5alphanumeric-6digits
        # Example: 68-01-4AAJF-360204 or 12-05-SA196-340202
        pattern = r'\b(\d{2})-(\d{2})-([A-Z0-9]{4,5}[A-Z]?)-(\d{6})\b'
        matches = re.findall(pattern, ocr_result)
        
        if matches:
            # Reconstruct the sensor ID from the first match
            sensor_id = f"{matches[0][0]}-{matches[0][1]}-{matches[0][2]}-{matches[0][3]}"
            print(f"[OCR] ✓ Sensor ID detected: {sensor_id}")
            return sensor_id
        
        # Try lenient pattern (handles spacing/dash errors)
        lenient_pattern = r'(\d{2})[\s\-]?(\d{2})[\s\-]?([A-Z0-9]{4,6})[\s\-]?(\d{6})'
        lenient_matches = re.findall(lenient_pattern, ocr_result)
        
        if lenient_matches:
            sensor_id = f"{lenient_matches[0][0]}-{lenient_matches[0][1]}-{lenient_matches[0][2]}-{lenient_matches[0][3]}"
            print(f"[OCR] ✓ Sensor ID detected (lenient): {sensor_id}")
            return sensor_id
        
        print(f"[OCR] ✗ No sensor ID pattern found")
        return ocr_result  # Return raw OCR if no pattern match
        
    except Exception as e:
        print(f"[OCR] ERROR: {e}")
        return ""

# ----- Camera widget helpers (place/show/hide) -----
video_label = tk.Label(root, bg="black")

sensor_id_label = tk.Label(root, text="Sensor ID:", font=("Arial", 10), bg="lightblue")
sensor_id_textbox = tk.Text(root, height=1, width=18, font=("Arial", 10))

# Info label for OCR (crop box is now optional)
ocr_info_label = tk.Label(root, text="Auto-detect (no crop needed)", font=("Arial", 8), bg="lightblue", fg="green")

threshold_label = tk.Label(root, text="Threshold:", font=("Arial", 8), bg="lightblue")
threshold_scale = tk.Scale(root, from_=110, to=200, orient=tk.HORIZONTAL, length=200, bg="#407ec9", fg="white", font=("Arial", 8), resolution=5)
threshold_scale.set(175)

read_button = tk.Button(root, text="READ", command=lambda: capture_image_and_process(), font=("Arial", 10), bg="#00cc44", fg="white", padx=10)
toggle_button = tk.Button(root, text="Toggle View", command=lambda: globals().__setitem__('threshold_view', not threshold_view), font=("Arial", 10), bg="#407ec9", fg="white", padx=10)

_CAMERA_PLACES = {
    "video": {"x": 550, "y": 30, "width": DISPLAY_W, "height": DISPLAY_H},
    "sensor_label": {"x": 650, "y": 280},
    "sensor_text": {"x": 690, "y": 280},
    "ocr_info": {"x": 630, "y": 300},
    "threshold_label": {"x": 570, "y": 350},
    "threshold_scale": {"x": 650, "y": 350},
    "read_button": {"x": 600, "y": 310},
    "toggle_button": {"x": 700, "y": 310},
}

def place_camera_widgets():
    try:
        video_label.place(x=_CAMERA_PLACES["video"]["x"], y=_CAMERA_PLACES["video"]["y"],
                          width=_CAMERA_PLACES["video"]["width"], height=_CAMERA_PLACES["video"]["height"])
        sensor_id_label.place(x=_CAMERA_PLACES["sensor_label"]["x"], y=_CAMERA_PLACES["sensor_label"]["y"])
        sensor_id_textbox.place(x=_CAMERA_PLACES["sensor_text"]["x"], y=_CAMERA_PLACES["sensor_text"]["y"])
        ocr_info_label.place(x=_CAMERA_PLACES["ocr_info"]["x"], y=_CAMERA_PLACES["ocr_info"]["y"])
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
        ocr_info_label.place_forget()
        threshold_label.place_forget()
        threshold_scale.place_forget()
        read_button.place_forget()
        toggle_button.place_forget()
    except Exception:
        pass

def set_ocr_allowed(allow: bool):
    global ocr_allowed
    ocr_allowed = bool(allow)
    if ocr_allowed:
        try:
            root.geometry("900x650")
        except Exception:
            pass
        place_camera_widgets()
        start_camera()
    else:
        stop_camera()
        hide_camera_widgets()
        try:
            root.geometry("540x650")
        except Exception:
            pass

# ---------- Camera control functions ----------
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

# ---------- OCR capture and processing ----------
def capture_image_and_process():
    if not ocr_allowed:
        messagebox.showwarning("OCR Disabled", "OCR is disabled for this process. Use barcode scanner instead.")
        return
    if not cap or not cap.isOpened():
        messagebox.showerror("Error", "Camera is not open.")
        return
    ret, frame = cap.read()
    if ret:
        try:
            cv2.imwrite(before_image_path, frame)
        except Exception:
            pass
        threading.Thread(target=process_image_for_ocr_with_retries, daemon=True).start()
    else:
        messagebox.showerror("Error", "Failed to capture image.")

def process_image_for_ocr_with_retries():
    """
    OPTIMIZED: Process full image with regex pattern detection and fuzzy matching only.
    No cropping needed - automatically finds sensor ID anywhere in the image.
    Uses fuzzy matching with Levenshtein distance instead of normalization.
    """
    import re
    try:
        pil_orig = Image.open(before_image_path)
        
        # Optional: Resize large images for faster processing
        max_width = 1500
        if pil_orig.width > max_width:
            scale = max_width / pil_orig.width
            new_size = (int(pil_orig.width * scale), int(pil_orig.height * scale))
            pil_orig = pil_orig.resize(new_size, Image.LANCZOS)
        
        # Save processed image for debugging
        try:
            pil_orig.save(save_path)
        except Exception:
            pass

        lot_number = entries["Lot Number:"].get().strip()
        valid_ids = get_valid_sensor_ids_for_lot(lot_number) if lot_number else []

        # Get threshold settings
        try:
            orig_thresh = int(threshold_scale.get())
        except Exception:
            orig_thresh = 175
        
        # OPTIMIZED: Try only 5 thresholds instead of 11 (faster)
        thresholds = [orig_thresh, orig_thresh - 10, orig_thresh + 10, orig_thresh - 20, orig_thresh + 20]
        thresholds = [max(110, min(200, t)) for t in thresholds]

        final_ocr = ""
        matched_sensor = None

        for t in thresholds:
            print(f"[OCR] Trying threshold: {t}")
            ocr_result = perform_ocr_on_pil_image(pil_orig, t)
            
            if not ocr_result:
                continue
            
            # Check if OCR result matches the sensor ID pattern
            pattern = r'\b(\d{2})-(\d{2})-([A-Z0-9]{4,5}[A-Z]?)-(\d{6})\b'
            if re.search(pattern, ocr_result):
                # Pattern found - this is likely a valid sensor ID
                if valid_ids:
                    # Try exact case-insensitive match first
                    for vid in valid_ids:
                        if str(vid).upper() == ocr_result.upper():
                            final_ocr = vid
                            matched_sensor = vid
                            print(f"[OCR] ✓ Exact match to lot sensor: {vid}")
                            break
                    
                    # If no exact match, try fuzzy matching with confusion map
                    if not matched_sensor:
                        try:
                            ocr_conf = _apply_confusions(ocr_result)
                            for vid in valid_ids:
                                if str(vid).strip().upper() == ocr_conf.upper():
                                    final_ocr = vid
                                    matched_sensor = vid
                                    print(f"[OCR] ✓ Matched via confusion map: {vid}")
                                    break
                            
                            # If still no match, try fuzzy with Levenshtein
                            if not matched_sensor:
                                best_match = None
                                best_dist = None
                                
                                for variant in (ocr_result, ocr_conf):
                                    vstr = variant.replace('-', '').replace(' ', '').upper()
                                    for vid in valid_ids:
                                        vidstr = str(vid).replace('-', '').replace(' ', '').upper()
                                        d = _levenshtein(vstr, vidstr)
                                        if best_dist is None or d < best_dist:
                                            best_dist = d
                                            best_match = (vid, d, variant)
                                
                                # Accept fuzzy matches with edit distance <= 3
                                if best_match and best_match[1] <= 3:
                                    final_ocr = best_match[0]
                                    matched_sensor = best_match[0]
                                    print(f"[OCR] ✓ Fuzzy matched '{best_match[2]}' -> '{matched_sensor}' (dist={best_match[1]})")
                        except Exception as e:
                            print(f"[Fuzzy] Error: {e}")
                    
                    if matched_sensor:
                        break
                else:
                    # No validation list, accept the pattern match
                    final_ocr = ocr_result
                    matched_sensor = ocr_result
                    break
            
            if not final_ocr and ocr_result:
                final_ocr = ocr_result
            
            time.sleep(0.05)  # Small delay between attempts

        def ui_update_success():
            sensor_id_textbox.delete("1.0", tk.END)
            
            if matched_sensor:
                # Matched sensor found - insert and validate
                sensor_id_textbox.insert(tk.END, matched_sensor)
                sensor_id_textbox.config(bg="green")
                print(f"[OCR] ✓ Valid sensor ID: {matched_sensor}")
                validate_sensor_id()
            elif final_ocr:
                # Pattern found but not validated against lot
                sensor_id_textbox.insert(tk.END, final_ocr.strip())
                sensor_id_textbox.config(bg="orange")
                print(f"[OCR] ⚠ Pattern detected but not validated: {final_ocr}")
                messagebox.showwarning(
                    "OCR Warning", 
                    f"Detected: '{final_ocr}'\n\n"
                    f"This sensor ID does not belong to Lot '{lot_number}'.\n"
                    f"Please verify the sensor or scan again."
                )
                # Clear invalid sensor ID
                sensor_id_textbox.delete("1.0", tk.END)
                sensor_id_textbox.config(bg="white")
            else:
                # No pattern detected
                sensor_id_textbox.config(bg="red")
                print(f"[OCR] ✗ No valid pattern detected")
                messagebox.showwarning(
                    "OCR Failed", 
                    "Could not detect a valid Sensor ID pattern.\n"
                    "Please adjust the camera position or threshold and try again."
                )

        root.after(0, ui_update_success)

    except Exception as e:
        root.after(0, lambda: messagebox.showerror("OCR Error", f"Error during OCR processing: {e}"))

# ---------- Write/validate Sensor ID into table ----------
def write_sensor_id_to_active_pcb():
    """Used by OCR flow to write sensor id from sensor_id_textbox into the focused/first empty sensor entry."""
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
        for r in range(20):
            st = str(data_entry[r][0].cget("state"))
            if st == "normal" and not data_entry[r][0].get().strip():
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

    for i in range(20):
        if i != target_row and data_entry[i][0].get().strip() == value:
            messagebox.showerror("Duplicate Sensor ID", f"Sensor ID '{value}' is already entered in another row.")
            # Only clear on error
            sensor_id_textbox.delete("1.0", tk.END)
            sensor_id_textbox.config(bg="white")
            return

    data_entry[target_row][0].config(state="normal")
    data_entry[target_row][0].delete(0, tk.END)
    data_entry[target_row][0].insert(0, value)
    data_entry[target_row][0].config(state="readonly", bg="lightgreen")

    # FIXED: Only clear textbox after successfully writing to table
    # Keep the sensor ID visible in the OCR textbox for reference
    # sensor_id_textbox.delete("1.0", tk.END)
    # sensor_id_textbox.config(bg="white")

    # Enable measurement columns for this row
    for col in range(1, 4):
        data_entry[target_row][col].config(state="normal", bg="white")
    data_entry[target_row][1].focus_set()

    # Do NOT immediately lock all columns here; instead check and lock sensor-id column only.
    check_all_sensor_ids()

# NEW: validate barcode-entered sensor id from the sensor ID entry itself
def sensor_entry_validate(event, row):
    """
    Validates the sensor id typed/scanned directly into the sensor-id entry at row.
    On success:
      - sets the sensor id entry to readonly (and lightgreen),
      - enables measurement columns for that row and focuses first measurement,
      - runs check_all_sensor_ids()
    On failure:
      - clears the sensor id entry and focuses it for retry
    """
    lot_number = entries["Lot Number:"].get().strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number first.")
        try:
            data_entry[row][0].config(state="normal")
            data_entry[row][0].focus_set()
        except Exception:
            pass
        return

    sensor_id = data_entry[row][0].get().strip()
    if not sensor_id:
        messagebox.showwarning("Warning", "Sensor ID is empty.")
        try:
            data_entry[row][0].config(state="normal")
            data_entry[row][0].focus_set()
        except Exception:
            pass
        return

    # validate against lot_tracking
    try:
        conn = sqlite3.connect(db_path_tracking)
        cur = conn.cursor()
        cur.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
        valid_ids = [r[0] for r in cur.fetchall()]
        conn.close()
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")
        return

    # check membership (case-insensitive)
    matched = None
    for sid in valid_ids:
        if str(sid).strip().upper() == sensor_id.upper():
            matched = sid
            break

    if not matched and valid_ids:
        messagebox.showerror("Invalid Sensor ID", f"Sensor ID '{sensor_id}' is not valid for Lot '{lot_number}'.")
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

    # success: write canonical ID (if matched) and lock the sensor entry
    to_write = str(matched) if matched else sensor_id
    try:
        data_entry[row][0].config(state="normal")
        data_entry[row][0].delete(0, tk.END)
        data_entry[row][0].insert(0, to_write)
        data_entry[row][0].config(state="readonly", bg="lightgreen")
    except Exception:
        pass

    # enable measurement columns
    for col in range(1, 4):
        try:
            data_entry[row][col].config(state="normal", bg="white")
        except Exception:
            pass
    try:
        data_entry[row][1].focus_set()
    except Exception:
        pass

    check_all_sensor_ids()

def check_all_sensor_ids():
    """
    Lock ONLY the Sensor ID column for expected rows once all sensor IDs are entered.
    Keep measurement columns enabled for rows that have Sensor ID and focus the first empty
    measurement field (so last sensor's measurements can be entered).
    """
    entered = {data_entry[r][0].get().strip() for r in range(len(data_entry)) if data_entry[r][0].get().strip()}
    required = set(sensor_ids_no_defects) if sensor_ids_no_defects else set()
    if not required:
        return False
    missing = required - entered
    if not missing:
        expected = len(sensor_ids_no_defects)
        # Lock Sensor ID entries for expected rows only
        for r in range(expected):
            try:
                data_entry[r][0].config(state="readonly", bg="lightgreen")
            except Exception:
                pass
            # Enable measurement columns for rows that have sensor id
            if data_entry[r][0].get().strip():
                for c in range(1, 4):
                    try:
                        data_entry[r][c].config(state="normal", bg="white")
                    except Exception:
                        pass
            else:
                for c in range(1, 4):
                    try:
                        data_entry[r][c].config(state="readonly")
                    except Exception:
                        pass
        # For rows beyond expected, keep everything readonly
        for r in range(expected, 20):
            for c in range(0, len(data_entry[r])):
                try:
                    data_entry[r][c].config(state="readonly")
                except Exception:
                    pass

        # Focus first empty measurement cell among expected rows (so user can input measurements)
        for r in range(expected):
            for c in range(1, 4):
                if not data_entry[r][c].get().strip():
                    try:
                        data_entry[r][c].focus_set()
                        return True
                    except Exception:
                        return True

        # If all measurements are already filled, focus Operator
        try:
            entries["Operator:"].focus_set()
        except Exception:
            pass

        messagebox.showinfo("Info", "All Sensor IDs entered. Sensor ID column locked. Please verify measurements and SAVE.")
        return True
    return False

def validate_sensor_id():
    """
    Validate the sensor ID in the textbox against the lot's valid sensor IDs.
    Only accept if it matches exactly (case-insensitive).
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

        # 1) Try exact case-insensitive match first
        matched = None
        for vid in valid_ids:
            if str(vid).strip().upper() == value.upper():
                matched = vid
                break

        # 2) If not exact, apply OCR confusion map + normalization helpers
        if not matched and value:
            try:
                # First try OCR confusion mapping
                val_conf = _apply_confusions(value)
                for vid in valid_ids:
                    if str(vid).strip().upper() == val_conf.upper():
                        matched = vid
                        break
                
                # If still no match, try fuzzy matching with Levenshtein distance
                if not matched:
                    best_match = None
                    best_dist = None
                    
                    # Try both original value and confusion-mapped value
                    for variant in (value, val_conf):
                        vstr = variant.replace('-', '').replace(' ', '').upper()
                        for vid in valid_ids:
                            vidstr = str(vid).replace('-', '').replace(' ', '').upper()
                            d = _levenshtein(vstr, vidstr)
                            if best_dist is None or d < best_dist:
                                best_dist = d
                                best_match = (vid, d, variant)
                    
                    # Accept fuzzy matches with edit distance <= 3
                    if best_match and best_match[1] <= 3:
                        matched = best_match[0]
                        print(f"[Fuzzy] Matched '{best_match[2]}' -> '{matched}' (dist={best_match[1]})")
            except Exception as e:
                print(f"[Fuzzy] Error: {e}")
                matched = None

        if not matched:
            sensor_id_textbox.config(bg="red")
            messagebox.showerror(
                "Invalid Sensor ID",
                f"Sensor ID '{value}' is NOT valid for Lot '{lot_number}'.\n\n"
                f"Please verify the sensor and try again."
            )
            # Clear the invalid sensor ID only on error
            sensor_id_textbox.delete("1.0", tk.END)
            sensor_id_textbox.config(bg="white")
            return

        # Check for duplicates in the table (compare to canonical matched)
        for i in range(20):
            existing = data_entry[i][0].get().strip()
            if existing and existing.upper() == str(matched).strip().upper():
                messagebox.showerror(
                    "Duplicate Sensor ID",
                    f"Sensor ID '{matched}' is already entered in row {i+1}."
                )
                # Clear on duplicate error
                sensor_id_textbox.delete("1.0", tk.END)
                sensor_id_textbox.config(bg="white")
                return

        # Valid and unique - update textbox with canonical ID and write to table
        sensor_id_textbox.config(bg="green")
        sensor_id_textbox.delete("1.0", tk.END)
        sensor_id_textbox.insert(tk.END, str(matched))
        # The textbox will remain populated after write (changed in write_sensor_id_to_active_pcb)
        write_sensor_id_to_active_pcb()

    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")
        sensor_id_textbox.config(bg="red")

# ---------- Navigation / judgement ----------
def navigate_on_enter(event, row, col):
    if col < 3:
        next_col = col + 1
        data_entry[row][next_col].focus_set()
    else:
        judge_row_values(row)

def validate_numeric_input(P):
    if P == "" or (P[0] == "-" and P[1:].replace(".", "", 1).isdigit()) or P.replace(".", "", 1).isdigit():
        return True
    else:
        return False

def judge_row_values(row):
    if data_entry[row][0].get().strip():
        # choose limits based on current process (load from JSON on server if available)
        current_process = entries["Current Process:"].get().strip()
        limits = get_molding_limits(current_process)
        if not limits:
            messagebox.showerror("Invalid Process", f"Cannot judge row: unrecognized process '{current_process}'.")
            return

        values = [
            data_entry[row][1].get(),
            data_entry[row][2].get(),
            data_entry[row][3].get(),
        ]
        row_failed = False
        for col_idx, (val_str, (low, high)) in enumerate(zip(values, limits), start=1):
            try:
                v = float(val_str)
                if low <= v <= high:
                    data_entry[row][col_idx].config(bg="white")
                else:
                    row_failed = True
                    data_entry[row][col_idx].config(bg="red")
            except ValueError:
                row_failed = True
                data_entry[row][col_idx].config(bg="red")
        if row_failed:
            judgement_labels[row].config(text="Failed", fg="red")
        else:
            judgement_labels[row].config(text="Passed", fg="green")

        # After judgement, enable next sensor-id if expected; else check_all_sensor_ids and focus first empty measurement
        next_row = row + 1
        expected = len(sensor_ids_no_defects) if sensor_ids_no_defects else 20
        if next_row < expected:
            # Only clear and enable if the next row's sensor ID is actually empty
            if not data_entry[next_row][0].get().strip():
                data_entry[next_row][0].config(state="normal")
                data_entry[next_row][0].delete(0, tk.END)
                data_entry[next_row][0].focus_set()
            else:
                # Sensor ID already exists in next row, just move focus to it
                data_entry[next_row][0].focus_set()
        else:
            all_locked = check_all_sensor_ids()
            if not all_locked:
                try:
                    entries["Operator:"].focus_set()
                except Exception:
                    pass

# ---------- UI construction ----------
title_label = tk.Label(root, text="Molding Dimension", font=("BiomeW04-Bold", 20, "bold"), bg="lightblue")
title_label.place(x=10, y=0)

# Labels and Entry fields
labels = ["Lot Number:", "Current Process:", "Date and Time:", "Operator:"]
entries = {}

label_positions = {
    "Lot Number:": (10, 50),
    "Current Process:": (10, 75),
    "Date and Time:": (10, 100),
    "Operator:": (10, 125)
}
entry_positions = {
    "Lot Number:": (140, 50),
    "Current Process:": (140, 75),
    "Date and Time:": (140, 100),
    "Operator:": (140, 125)
}

for label_text in labels:
    label = tk.Label(root, text=label_text, font=("Arial", 10), bg="lightblue")
    label.place(x=label_positions[label_text][0], y=label_positions[label_text][1])
    entry = tk.Entry(root, width=28, justify='center')
    entry.place(x=entry_positions[label_text][0], y=entry_positions[label_text][1])
    entries[label_text] = entry

entries["Date and Time:"].config(state="readonly")

def update_datetime():
    current_time = time.strftime("%Y-%m-%d %I:%M:%S %p")
    entries["Date and Time:"].config(state="normal")
    entries["Date and Time:"].delete(0, tk.END)
    entries["Date and Time:"].insert(0, current_time)
    entries["Date and Time:"].config(state="readonly")
    root.after(1000, update_datetime)

update_datetime()

entries["Lot Number:"].bind("<Return>", lambda e: fetch_lot_info())

# Buttons
def delete_action():
    for entry in entries.values():
        try:
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.config(state="readonly" if entry == entries["Current Process:"] else "normal")
        except Exception:
            pass
    entries["Current Process:"].config(state="normal")
    entries["Current Process:"].delete(0, tk.END)
    entries["Current Process:"].config(state="readonly")
    global sensor_ids_no_defects
    sensor_ids_no_defects = []
    for r in range(20):
        for c in range(len(data_entry[r])):
            try:
                data_entry[r][c].config(state="normal")
                data_entry[r][c].delete(0, tk.END)
                data_entry[r][c].config(bg="white")
                if c != 0:
                    data_entry[r][c].config(state="readonly")
                else:
                    data_entry[r][c].config(state="readonly")
            except Exception:
                pass
        try:
            judgement_labels[r].config(text="", bg="lightblue")
        except Exception:
            pass
    # hide camera by default
    set_ocr_allowed(False)

delete_button = tk.Button(root, text="Clear Data", font=("Tahoma", 12, "bold"), padx=10, pady=1, bg="yellow", command=delete_action, relief='raised', borderwidth=3)
delete_button.place(x=350, y=50)
save_button = tk.Button(root, text="SAVE", font=("Tahoma", 12, "bold"), padx=32, pady=1, bg="orange", command=lambda: save_action(), relief='raised', borderwidth=3)
save_button.place(x=350, y=100)

# Table headers
headers = ["No.", "Sensor ID", "Length", "Width", "Height", "Judgement"]
header_positions = {
    "No.": (10, 150),
    "Sensor ID": (75, 150),
    "Length": (200, 150),
    "Width": (290, 150),
    "Height": (380, 150),
    "Judgement": (455, 150)
}
for header in headers:
    label = tk.Label(root, text=header, font=("Arial", 10, "bold"), bg="lightblue", relief="ridge")
    label.place(x=header_positions[header][0], y=header_positions[header][1])

# Table rows for data entry
data_entry = []
judgement_labels = []
vcmd = (root.register(validate_numeric_input), '%P')

for row in range(20):
    row_entries = []
    number_label = tk.Label(root, text=str(row + 1), width=3, bg="lightblue", relief="ridge")
    number_label.place(x=10, y=180 + row*23)

    # Start sensor ID entries as readonly. fetch_lot_info will enable the first (or desired) row.
    sensor_id_entry = tk.Entry(root, width=20, justify='center')
    sensor_id_entry.place(x=45, y=180 + row*23)
    sensor_id_entry.config(state="readonly")
    # Bind Enter to validation routine for barcode/manual entry
    sensor_id_entry.bind("<Return>", lambda event, r=row: sensor_entry_validate(event, r))
    row_entries.append(sensor_id_entry)

    for col in range(1, 4):
        entry = tk.Entry(root, width=10, validate="key", validatecommand=vcmd, justify='center')
        entry.place(x=190 + (col-1)*90, y=180 + row*23)
        entry.config(state="readonly")
        entry.bind("<Return>", lambda event, r=row, c=col: navigate_on_enter(event, r, c))
        row_entries.append(entry)

    data_entry.append(row_entries)

    judgement_label = tk.Label(root, text="", width=10, bg="lightblue", relief="ridge")
    judgement_label.place(x=455, y=180 + row*23)
    judgement_labels.append(judgement_label)

# Initially hide camera widgets
hide_camera_widgets()

# ----- Fetch lot info and enable/disable OCR depending on process -----
def fetch_lot_info(event=None):
    global sensor_ids_no_defects
    lot_number = entries["Lot Number:"].get().strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number.")
        return
    try:
        conn = sqlite3.connect(db_path_tracking)
        cur = conn.cursor()
        cur.execute("SELECT current_process FROM lot_tracking WHERE lot_number = ? LIMIT 1", (lot_number,))
        row = cur.fetchone()
        if not row:
            messagebox.showwarning("Warning", "Lot Number not found in the database.")
            conn.close()
            delete_action()
            return
        current_process = row[0]
        entries["Current Process:"].config(state="normal")
        entries["Current Process:"].delete(0, tk.END)
        entries["Current Process:"].insert(0, current_process)
        entries["Current Process:"].config(state="readonly")

        lot_condition = get_lot_condition(lot_number)

        # Validate for MP
        if str(lot_condition).upper() == "MP":
            if current_process not in ("Top Molding Dimension", "Bottom Molding Dimension"):
                messagebox.showerror("Error", f"The lot number inputted is not for Top/Bottom Molding Dimension (got '{current_process}').")
                conn.close()
                delete_action()
                return

        # Toggle OCR and window size based on current_process
        if current_process == "Top Molding Dimension":
            set_ocr_allowed(True)
            title_label.config(text="Molding Dimension - Top")
        else:  # "Bottom Molding Dimension"
            set_ocr_allowed(False)
            title_label.config(text="Molding Dimension - Bottom")

        # determine sensors available (filtering by previous defects same as original)
        try:
            idx = process_flow.index(current_process)
        except ValueError:
            idx = -1

        if idx > 0:
            previous_defect_columns = []
            for proc in process_flow[:idx]:
                if proc in process_column_mapping and isinstance(process_column_mapping[proc], (list, tuple)) and len(process_column_mapping[proc]) > 2:
                    previous_defect_columns.append(process_column_mapping[proc][2])
            if previous_defect_columns:
                defect_conditions = " AND ".join(f"({col} IS NULL OR {col} = '')" for col in previous_defect_columns)
                query = f"SELECT sensor_id FROM lot_tracking WHERE lot_number = ? AND {defect_conditions}"
                cur.execute(query, (lot_number,))
                sensor_ids = [r[0] for r in cur.fetchall()]
            else:
                cur.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
                sensor_ids = [r[0] for r in cur.fetchall()]
        else:
            cur.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
            sensor_ids = [r[0] for r in cur.fetchall()]

        if not sensor_ids:
            messagebox.showinfo("Information", "No sensors available for this process (all sensors have defects from previous processes).")
            conn.close()
            delete_action()
            return

        # check masterlist if these sensors already have values for this process
        conn_master = sqlite3.connect(db_path_masterlist)
        cur_master = conn_master.cursor()
        process_to_columns = {
            "Top Molding Dimension": ["Top_Molding_Length", "Top_Molding_Width", "Top_Molding_Height"],
            "Bottom Molding Dimension": ["Bottom_Molding_Length", "Bottom_Molding_Width", "Bottom_Molding_Height"],
        }
        columns = process_to_columns.get(current_process, [])
        if columns:
            sensor_ids_with_values = []
            for sid in sensor_ids:
                try:
                    cur_master.execute(f"SELECT {', '.join(columns)} FROM lot_masterlist WHERE sensor_id=?", (sid,))
                    r = cur_master.fetchone()
                    if r and all(value is not None for value in r):
                        sensor_ids_with_values.append(sid)
                except sqlite3.OperationalError:
                    break
            if sensor_ids_with_values:
                messagebox.showinfo("Information", f"The following Sensor IDs already have values in '{current_process}':\n{', '.join(sensor_ids_with_values)}")
                conn_master.close()
                conn.close()
                return
        conn_master.close()

        # store expected sensors but do NOT prefill
        sensor_ids_no_defects = sensor_ids[:]

        # prepare table:
        # - Make sensor-id entries readonly for all rows then enable only the first row
        # - Ensure measurement columns are readonly and cleared
        for r in range(20):
            try:
                data_entry[r][0].config(state="readonly")
                data_entry[r][0].delete(0, tk.END)
                data_entry[r][0].config(bg="white")
            except Exception:
                pass
            for c in range(1, 4):
                try:
                    data_entry[r][c].config(state="readonly", bg="white")
                    data_entry[r][c].delete(0, tk.END)
                except Exception:
                    pass
            try:
                judgement_labels[r].config(text="", bg="lightblue")
            except Exception:
                pass

        # enable first sensor id slot for entry (either barcode or OCR will fill it)
        try:
            data_entry[0][0].config(state="normal")
            data_entry[0][0].focus_set()
        except Exception:
            pass

        conn.close()

    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")
        try:
            conn.close()
        except Exception:
            pass

# ---------- BMS Popup class (with Top/Bottom write paths & folder selection) ----------
class BMSPopup(tk.Toplevel):
    def __init__(self, master, lot_number, current_process, operator,
                 sensor_list, combobox_candidates, failed_sensor_list, blank_judgement_list, csv_rows_data, lot_condition="MP"):
        super().__init__(master)
        self.title("BMS Lot Tracking System - Popup")
        self.geometry("615x455")
        self.configure(bg='#3a6ba8')
        self.resizable(False, False)

        self.lot_number = lot_number
        self.current_process = current_process
        self.operator = operator
        self.sensor_list = sensor_list[:]
        self.combobox_candidates = combobox_candidates[:]
        self.failed_sensor_list = failed_sensor_list[:]
        self.blank_judgement_list = blank_judgement_list[:]
        self.csv_rows_data = csv_rows_data[:]
        self.lot_condition = str(lot_condition).strip()

        tk.Label(self, text="BMS Lot Tracking System", font=("BiomeW04-Bold", 20, "bold"), bg='#3a6ba8', fg="orange").place(x=20, y=0)

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

        tk.Label(self, text="Sensor ID:", bg='#3a6ba8', fg="white").place(x=5, y=105)
        self.sensor_id_combobox = ttk.Combobox(self, values=self.combobox_candidates, width=28)
        self.sensor_id_combobox.place(x=105, y=105)
        if self.combobox_candidates:
            self.sensor_id_combobox.set(self.combobox_candidates[0])

        tk.Label(self, text="Defect:", bg='#3a6ba8', fg="white").place(x=5, y=135)
        self.defect_entry = tk.Entry(self, width=31); self.defect_entry.place(x=105, y=135)

        tk.Label(self, text="Remarks:", bg='#3a6ba8', fg="white").place(x=5, y=165)
        self.remarks_entry = tk.Entry(self, width=31); self.remarks_entry.place(x=105, y=165)

        tk.Label(self, text="Quantity IN:", bg='#3a6ba8', fg="white").place(x=320, y=45)
        self.quantity_in_entry = tk.Entry(self, width=15); self.quantity_in_entry.place(x=410, y=45)
        tk.Label(self, text="Quantity OUT:", bg='#3a6ba8', fg="white").place(x=320, y=75)
        self.quantity_out_entry = tk.Entry(self, width=15); self.quantity_out_entry.place(x=410, y=75)
        tk.Label(self, text="Date:", bg='#3a6ba8', fg="white").place(x=320, y=105)
        self.date_time_label = tk.Label(self, text="", bg='white', width=19); self.date_time_label.place(x=410, y=105)
        tk.Label(self, text="Operator:", bg='#3a6ba8', fg="white").place(x=320, y=135)
        self.operator_entry = tk.Entry(self, width=22); self.operator_entry.place(x=410, y=135)
        self.operator_entry.insert(0, self.operator)

        tk.Button(self, text="Export Defects / Remarks", command=self.export_data, bg="green", fg="white",
                  font=("Tahoma", 10, "bold"), padx=20, pady=1, relief='raised', borderwidth=3).place(x=20, y=200)
        tk.Button(self, text="CLEAR", command=self.clear_fields, bg="yellow", font=("Tahoma", 16, "bold"),
                  padx=10, pady=1, relief='raised', borderwidth=3).place(x=320, y=185)
        tk.Button(self, text="SAVE", command=self.save_data_and_advance, bg="green", fg="white",
                  font=("Tahoma", 16, "bold"), padx=10, pady=1, relief='raised', borderwidth=3).place(x=460, y=185)
        tk.Button(self, text="DELETE Defects / Remarks", command=self.delete_selected_row, bg="red", fg="white",
                  font=("Tahoma", 10, "bold"), padx=20, pady=1, relief='raised', borderwidth=3).place(x=20, y=235)

        self.columns = ("Sensor ID", "Defects", "Remarks")
        self.table = ttk.Treeview(self, columns=self.columns, show="headings", height=7)
        for col in self.columns:
            self.table.heading(col, text=col)
        self.table.place(x=5, y=280, width=600, height=140)

        total_sensors = len(self.sensor_list)
        reduced_count = len(self.failed_sensor_list) + len(self.blank_judgement_list)
        self.quantity_in_entry.delete(0, tk.END); self.quantity_in_entry.insert(0, str(total_sensors))
        self.quantity_out_entry.delete(0, tk.END); self.quantity_out_entry.insert(0, str(max(0, total_sensors - reduced_count)))

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
        if not self.operator_entry.get().strip():
            messagebox.showwarning("Input Error", "Please enter Operator.")
            return

        selected_sensor = self.sensor_id_combobox.get().strip()
        if selected_sensor:
            found = False
            for iid in self.table.get_children():
                sid, defect, remarks = self.table.item(iid)["values"]
                if sid == selected_sensor and str(defect).strip():
                    found = True
                    break
            if not found:
                messagebox.showwarning("Input Error", "Please add a defect entry for the selected Sensor ID or clear selection.")
                return

        lot_number = self.lot_number
        current_process = self.current_process
        operator = self.operator_entry.get().strip()
        proc_datetime = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")

        columns = process_column_mapping.get(current_process)
        if (not columns or len(columns) < 6) and str(self.lot_condition).upper() == "MP":
            messagebox.showerror("Configuration Error", f"Process mapping for '{current_process}' is missing or invalid.")
            return

        quantity_in = self.quantity_in_entry.get()
        quantity_out = self.quantity_out_entry.get()

        try:
            # 1) Update lot_masterlist with measurement data
            if self.csv_rows_data:
                conn_master = sqlite3.connect(db_path_masterlist)
                cursor_master = conn_master.cursor()    
                for row in self.csv_rows_data:
                    try:
                        sensor_id = row[0]
                        val1 = row[1] if len(row) > 1 else None
                        val2 = row[2] if len(row) > 2 else None
                        val3 = row[3] if len(row) > 3 else None
                    except IndexError:
                        continue

                    if current_process == "Top Molding Dimension":
                        try:
                            cursor_master.execute("""
                                UPDATE lot_masterlist
                                SET Top_Molding_Length = ?, Top_Molding_Width = ?, Top_Molding_Height = ?
                                WHERE sensor_id = ?
                            """, (val1, val2, val3, sensor_id))
                        except sqlite3.OperationalError:
                            pass
                    elif current_process == "Bottom Molding Dimension":
                        try:
                            cursor_master.execute("""
                                UPDATE lot_masterlist
                                SET Bottom_Molding_Length = ?, Bottom_Molding_Width = ?, Bottom_Molding_Height = ?
                                WHERE sensor_id = ?
                            """, (val1, val2, val3, sensor_id))
                        except sqlite3.OperationalError:
                            pass
                conn_master.commit()
                conn_master.close()

            # 2) Update lot_tracking if MP and mapping exists
            if columns and len(columns) >= 6 and str(self.lot_condition).upper() == "MP":
                conn_t = sqlite3.connect(db_path_tracking)
                cur_t = conn_t.cursor()

                sensor_ids_in_table = [self.table.item(r)["values"][0] for r in self.table.get_children()]
                sensor_ids_with_defects = [self.table.item(r)["values"][0] for r in self.table.get_children() if self.table.item(r)["values"][1]]

                for iid in self.table.get_children():
                    sid, defect, remarks = self.table.item(iid)["values"]
                    try:
                        cur_t.execute(f"""
                            UPDATE lot_tracking
                            SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, {columns[3]}=?, {columns[4]}=?, {columns[5]}=?
                            WHERE lot_number=? AND sensor_id=?
                        """, (quantity_in, quantity_out, defect, remarks, proc_datetime, operator, lot_number, sid))
                    except sqlite3.OperationalError:
                        pass

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
                        """, (quantity_in, quantity_out, proc_datetime, operator, lot_number, sid))
                    except sqlite3.OperationalError:
                        pass

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

                if str(self.lot_condition).upper() == "MP":
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
            else:
                if str(self.lot_condition).upper() != "EVAL":
                    messagebox.showwarning("Warning", f"No process-column mapping available for '{current_process}'. No lot_tracking updates performed.")

            # 3) Export CSV
            base_folder_map = {
                "Top Molding Dimension": r"\\phlsvr08\BMS Data\Assembly Data\Top Molding Dimension",
                "Bottom Molding Dimension": r"\\phlsvr08\BMS Data\Assembly Data\Bottom Molding Dimension",
            }
            base_folder = base_folder_map.get(current_process, r"\\phlsvr08\BMS Data\Assembly Data\Molding Dimension")
            y = time.strftime("%Y"); m = time.strftime("%B"); d = time.strftime("%m.%d.%Y")
            export_folder = os.path.join(base_folder, y, m, d)
            os.makedirs(export_folder, exist_ok=True)
            csv_filename = os.path.join(export_folder, f"{current_process}_{lot_number}.csv")

            if self.csv_rows_data:
                with open(csv_filename, 'w', newline='') as f:
                    w = csv.writer(f)
                    w.writerow(["Lot Number", lot_number])
                    w.writerow(["Processed Date and Time", proc_datetime])
                    w.writerow(["Operator", operator]); w.writerow([])
                    w.writerow(["Sensor ID", "Length", "Width", "Height", "Judgement"])
                    for r in self.csv_rows_data:
                        w.writerow(r)
                messagebox.showinfo("CSV Export", f"Data successfully exported to:\n{csv_filename}")

            if columns and len(columns) >= 6 and str(self.lot_condition).upper() == "MP":
                try:
                    next_msg = process_flow[process_flow.index(current_process) + 1]
                except Exception:
                    next_msg = current_process
                messagebox.showinfo("Save", f"Data saved successfully.\nNext process set to: {next_msg}")
            else:
                messagebox.showinfo("Save", f"Data saved successfully.\nLot condition is '{self.lot_condition}'; lot_tracking was not advanced.")

            entries["Lot Number:"].focus_set()
            self.destroy()
            delete_action()

        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"An error occurred: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

# ---------- Save wrapper ----------
def save_action():
    try:
        if not entries["Operator:"].get().strip():
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
                x1 = data_entry[r][1].get().strip()
                x2 = data_entry[r][2].get().strip()
                x3 = data_entry[r][3].get().strip()
                j = judgement_labels[r].cget("text").strip()
                csv_rows_data.append([sid, x1, x2, x3, j])
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

        popup = BMSPopup(root, lot_number, current_process, operator,
                         sensor_list_local, combobox_candidates_local,
                         failed_sensor_list_local, blank_judgement_list_local, csv_rows_data, lot_condition)
        popup.grab_set()
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

# finalize UI
entries["Lot Number:"].focus_set()

def on_closing():
    global cap
    try:
        if cap and cap.isOpened():
            cap.release()
    except Exception:
        pass
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()