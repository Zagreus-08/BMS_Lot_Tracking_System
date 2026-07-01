import tkinter as tk
from tkinter import messagebox, Label, Button, Scale, ttk
import sqlite3
import time
import cv2
from PIL import Image, ImageFilter, ImageOps, ImageTk
import pytesseract
import threading
import os
import json
import csv
from datetime import datetime
import re

# Define paths
before_image_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\OCRBefore.png"
save_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\OCRAfter.png"
enhanced_image_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\Enhanced_OCRAfter.png"

# Path to Tesseract executable
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\a493353\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

# Custom Tesseract configuration
custom_oem_psm_config = (
    '--oem 3 --psm 6 '
    '-c tessedit_char_whitelist="ABCDEFGIJKLMNOPQRSTVWXZ0123456789- "'
)

# Define the paths to the databases
db_path_tracking = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"
db_path_masterlist = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"

# Define the absolute path to your config.json (update if different)
config_file_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\process_flow.json"

# Load process_flow and mapping from JSON config
try:
    with open(config_file_path, 'r') as f:
        config = json.load(f)
    process_flow = config["process_flow"]
    process_column_mapping = config["process_column_mapping"]
except FileNotFoundError:
    messagebox.showerror("Configuration Error", f"Config file not found at: {config_file_path}")
    raise SystemExit(f"Config file not found at: {config_file_path}")
except json.JSONDecodeError:
    messagebox.showerror("Configuration Error", "Error decoding process_flow.json. Please check its format.")
    raise SystemExit("Error decoding process_flow.json")

# Helper: fetch lot condition from masterlist DB
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

# Create main window
root = tk.Tk()
root.title("MR Chip Alignment Measurement")
root.geometry("1080x650")
root.configure(bg="lightblue")
root.resizable(False, False)

# Globals
sensor_ids_no_defects = []     # required sensor IDs for current lot (list of strings)
DISPLAY_W, DISPLAY_H = 400, 300
camera_index = 0
cap = None
threshold_view = False
last_successful_threshold = None  # Store the successful threshold value

# ROI Box globals
roi_enabled = False
roi_x, roi_y, roi_w, roi_h = 50, 50, 300, 200  # Default ROI position and size
dragging = False
resizing = False
drag_start_x, drag_start_y = 0, 0
resize_corner = None  # Which corner is being dragged: 'tl', 'tr', 'bl', 'br'
resize_handle_size = 10
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
    'B': '8'
}

# ---------- Utility OCR helpers ----------
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


def _apply_confusions(s):
    if not s:
        return s
    out = []
    for ch in s:
        out.append(OCR_CONFUSIONS.get(ch, ch))
    return ''.join(out)

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
        
        # Apply character corrections
        ocr_result = ocr_result.replace("O", "0").replace("D", "0").replace("I", "1")\
                               .replace("l", "1").replace("S", "5").replace("Z", "2")\
                               .replace("B", "8").replace("G", "6").replace("|", "1")
        
        # Regex pattern for sensor ID: XX-XX-XXXXX-XXXXXX
        # Format: 2digits-2digits-4-5alphanumeric-6digits
        pattern = r'\b(\d{2})-(\d{2})-([A-Z0-9]{4,5}[A-Z]?)-(\d{6})\b'
        matches = re.findall(pattern, ocr_result.upper())
        
        if matches:
            # Reconstruct the sensor ID from the first match
            sensor_id = f"{matches[0][0]}-{matches[0][1]}-{matches[0][2]}-{matches[0][3]}"
            print(f"[OCR] Regex matched sensor ID: {sensor_id}")
            return sensor_id
        
        # Fallback: return raw OCR text if no pattern match
        return ocr_result
    except Exception as exc:
        print("OCR error:", exc)
        return ""

# ---------- Database / form functions ----------
def fetch_lot_info(event=None):
    global sensor_ids_no_defects
    lot_number = entries["Lot Number:"].get().strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number.")
        return
    try:
        conn = sqlite3.connect(db_path_tracking)
        cursor = conn.cursor()
        cursor.execute("SELECT current_process FROM lot_tracking WHERE lot_number = ? LIMIT 1", (lot_number,))
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

        lot_condition = get_lot_condition(lot_number)
        if str(lot_condition).upper() == "MP":
            if current_process != "MR Chip Alignment Measurement":
                messagebox.showerror("Error", "The lot number inputted is not for MR Chip Alignment Measurement.")
                delete_action()
                conn.close()
                return
            if current_process not in process_flow:
                messagebox.showerror("Configuration Error", f"Process '{current_process}' not found in process_flow.")
                conn.close()
                return

        try:
            current_process_index = process_flow.index(current_process)
        except ValueError:
            current_process_index = -1

        if current_process_index > 0:
            previous_defect_columns = []
            for proc in process_flow[:current_process_index]:
                if proc in process_column_mapping and isinstance(process_column_mapping[proc], (list, tuple)) and len(process_column_mapping[proc]) > 2:
                    previous_defect_columns.append(process_column_mapping[proc][2])
            if previous_defect_columns:
                defect_conditions = " AND ".join(f"({col} IS NULL OR {col} = '')" for col in previous_defect_columns)
                query = f"""
                    SELECT sensor_id
                    FROM lot_tracking
                    WHERE lot_number = ? AND {defect_conditions}
                """
                cursor.execute(query, (lot_number,))
                sensor_ids = [r[0] for r in cursor.fetchall()]
            else:
                cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
                sensor_ids = [r[0] for r in cursor.fetchall()]
        else:
            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
            sensor_ids = [r[0] for r in cursor.fetchall()]

        if not sensor_ids:
            messagebox.showinfo("Information", "No sensors available for this process (all sensors have defects from previous processes).")
            conn.close()
            delete_action()
            return

        sensor_ids_no_defects = sensor_ids[:]  # store required sensor ids as list of strings

        # Clear table column 0 and set measurement columns readonly
        for row in range(20):
            data_entry[row][0].config(state="normal")
            data_entry[row][0].delete(0, tk.END)
            data_entry[row][0].config(bg="white")
            for col in range(1, 5):
                data_entry[row][col].config(state="readonly")
            judgement_labels[row].config(text="", bg="lightblue")

        data_entry[0][0].focus_set()
        conn.close()
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")

def navigate_on_enter(event, row, col):
    next_col = col + 1
    next_row = row
    if next_col < 5:
        data_entry[next_row][next_col].focus_set()
    else:
        next_row += 1
        if next_row < 20:
            data_entry[next_row][1].focus_set()
    if col == 4:
        judge_row_values(row)

def validate_numeric_input(P):
    if P == "" or P.replace(".", "", 1).isdigit():
        return True
    else:
        return False

def judge_row_values(row):
    if data_entry[row][0].get():
        values = [data_entry[row][1].get(), data_entry[row][2].get(), data_entry[row][3].get(), data_entry[row][4].get()]
        limits = [(0.00, 0.04)] * 4
        row_failed = False
        for col, (value, (low, high)) in enumerate(zip(values, limits), start=1):
            try:
                value = float(value)
                if low <= value <= high:
                    data_entry[row][col].config(bg="white")
                else:
                    row_failed = True
                    data_entry[row][col].config(bg="red")
            except ValueError:
                row_failed = True
                data_entry[row][col].config(bg="red")
        judgement_labels[row].config(text="Failed" if row_failed else "Passed", fg="red" if row_failed else "green")

def update_datetime():
    current_time = time.strftime("%Y-%m-%d %I:%M:%S %p")
    entries["Date and Time:"].config(state="normal")
    entries["Date and Time:"].delete(0, tk.END)
    entries["Date and Time:"].insert(0, current_time)
    entries["Date and Time:"].config(state="readonly")
    root.after(1000, update_datetime)

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

    sensor_id_textbox.delete("1.0", tk.END)
    sensor_id_textbox.config(bg="white")

    # Make next row's sensor ID entry editable and focus it
    next_row = target_row + 1
    if next_row < 20:
        data_entry[next_row][0].config(state="normal")
        data_entry[next_row][0].focus_set()
    else:
        entries["Operator:"].focus_set()

    check_all_sensor_ids()

def check_all_sensor_ids():
    entered = {data_entry[r][0].get().strip() for r in range(len(data_entry)) if data_entry[r][0].get().strip()}
    required = set(sensor_ids_no_defects) if sensor_ids_no_defects else set()
    if not required:
        return
    missing = required - entered
    if not missing:
        for r in range(len(data_entry)):
            data_entry[r][0].config(state="readonly")
            if data_entry[r][0].get().strip():
                for c in range(1, 5):
                    data_entry[r][c].config(state="normal")
        data_entry[0][1].focus_set()
        messagebox.showinfo("Info", "All Sensor IDs have been entered. Column 0 is now locked.")
    else:
        print(f"Waiting for all Sensor IDs to be entered. Missing: {missing}")

def validate_sensor_id():
    lot_number = entries["Lot Number:"].get().strip()
    value = sensor_id_textbox.get("1.0", tk.END).strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Lot Number is missing.")
        sensor_id_textbox.delete("1.0", tk.END)
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
        else:
            # check duplicate
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

# ---------- Video & rectangle handling ----------
def start_camera():
    global cap
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        messagebox.showerror("Error", "Could not open camera.")
    else:
        show_frame()

def get_corner_at_position(x, y):
    """Check if mouse is near a corner handle"""
    corners = {
        'tl': (roi_x, roi_y),
        'tr': (roi_x + roi_w, roi_y),
        'bl': (roi_x, roi_y + roi_h),
        'br': (roi_x + roi_w, roi_y + roi_h)
    }
    
    for corner_name, (cx, cy) in corners.items():
        if abs(x - cx) <= resize_handle_size and abs(y - cy) <= resize_handle_size:
            return corner_name
    return None

def is_inside_roi(x, y):
    """Check if point is inside ROI box"""
    return roi_x <= x <= roi_x + roi_w and roi_y <= y <= roi_y + roi_h

def on_mouse_press(event):
    global dragging, resizing, drag_start_x, drag_start_y, resize_corner
    if not roi_enabled:
        return
    
    x, y = event.x, event.y
    
    # Check if clicking on a corner handle (for resizing)
    corner = get_corner_at_position(x, y)
    if corner:
        resizing = True
        resize_corner = corner
        drag_start_x, drag_start_y = x, y
    # Check if clicking inside ROI (for dragging)
    elif is_inside_roi(x, y):
        dragging = True
        drag_start_x, drag_start_y = x, y

def on_mouse_drag(event):
    global roi_x, roi_y, roi_w, roi_h, drag_start_x, drag_start_y
    if not roi_enabled:
        return
    
    x, y = event.x, event.y
    dx = x - drag_start_x
    dy = y - drag_start_y
    
    MIN_SIZE = 50  # Minimum ROI size
    
    if resizing and resize_corner:
        # Resize based on which corner is being dragged
        if resize_corner == 'tl':  # Top-left
            new_x = max(0, min(roi_x + dx, roi_x + roi_w - MIN_SIZE))
            new_y = max(0, min(roi_y + dy, roi_y + roi_h - MIN_SIZE))
            new_w = roi_w - (new_x - roi_x)
            new_h = roi_h - (new_y - roi_y)
            
            if new_w >= MIN_SIZE and new_h >= MIN_SIZE:
                roi_x, roi_y = new_x, new_y
                roi_w, roi_h = new_w, new_h
                drag_start_x, drag_start_y = x, y
                
        elif resize_corner == 'tr':  # Top-right
            new_y = max(0, min(roi_y + dy, roi_y + roi_h - MIN_SIZE))
            new_w = max(MIN_SIZE, min(x - roi_x, DISPLAY_W - roi_x))
            new_h = roi_h - (new_y - roi_y)
            
            if new_w >= MIN_SIZE and new_h >= MIN_SIZE and roi_x + new_w <= DISPLAY_W:
                roi_y = new_y
                roi_w = new_w
                roi_h = new_h
                drag_start_x, drag_start_y = x, y
                
        elif resize_corner == 'bl':  # Bottom-left
            new_x = max(0, min(roi_x + dx, roi_x + roi_w - MIN_SIZE))
            new_h = max(MIN_SIZE, min(y - roi_y, DISPLAY_H - roi_y))
            new_w = roi_w - (new_x - roi_x)
            
            if new_w >= MIN_SIZE and new_h >= MIN_SIZE and roi_y + new_h <= DISPLAY_H:
                roi_x = new_x
                roi_w = new_w
                roi_h = new_h
                drag_start_x, drag_start_y = x, y
                
        elif resize_corner == 'br':  # Bottom-right
            new_w = max(MIN_SIZE, min(x - roi_x, DISPLAY_W - roi_x))
            new_h = max(MIN_SIZE, min(y - roi_y, DISPLAY_H - roi_y))
            
            if new_w >= MIN_SIZE and new_h >= MIN_SIZE and roi_x + new_w <= DISPLAY_W and roi_y + new_h <= DISPLAY_H:
                roi_w = new_w
                roi_h = new_h
                drag_start_x, drag_start_y = x, y
        
    elif dragging:
        # Move the entire ROI
        new_x = max(0, min(roi_x + dx, DISPLAY_W - roi_w))
        new_y = max(0, min(roi_y + dy, DISPLAY_H - roi_h))
        
        roi_x, roi_y = new_x, new_y
        drag_start_x, drag_start_y = x, y

def on_mouse_release(event):
    global dragging, resizing, resize_corner
    dragging = False
    resizing = False
    resize_corner = None

def toggle_roi():
    global roi_enabled
    roi_enabled = not roi_enabled
    if roi_enabled:
        roi_toggle_button.config(bg="#00cc44", text="ROI: ON")
    else:
        roi_toggle_button.config(bg="#ff4444", text="ROI: OFF")

def show_frame():
    global cap, roi_enabled, roi_x, roi_y, roi_w, roi_h
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
    
    # Draw ROI box if enabled
    if roi_enabled:
        # Draw main rectangle
        cv2.rectangle(frame_to_display, (roi_x, roi_y), (roi_x + roi_w, roi_y + roi_h), (0, 255, 0), 2)
        
        # Draw corner handles for resizing
        handle_color = (255, 0, 0)
        # Top-left
        cv2.circle(frame_to_display, (roi_x, roi_y), resize_handle_size//2, handle_color, -1)
        # Top-right
        cv2.circle(frame_to_display, (roi_x + roi_w, roi_y), resize_handle_size//2, handle_color, -1)
        # Bottom-left
        cv2.circle(frame_to_display, (roi_x, roi_y + roi_h), resize_handle_size//2, handle_color, -1)
        # Bottom-right
        cv2.circle(frame_to_display, (roi_x + roi_w, roi_y + roi_h), resize_handle_size//2, handle_color, -1)
        
        # Draw label
        cv2.putText(frame_to_display, "", (roi_x + 5, roi_y + 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
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
        # Resize frame to match display size
        frame_full = cv2.resize(frame, (DISPLAY_W, DISPLAY_H))
        
        # If ROI is enabled, crop to ROI region
        if roi_enabled:
            roi_frame = frame_full[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]
            cv2.imwrite(before_image_path, roi_frame)
        else:
            cv2.imwrite(before_image_path, frame_full)
        
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
                cand = str(ocr_raw).strip().upper()

                # exact match
                if cand in remaining_sensor_ids:
                    print(f"[OCR] ✓ Pattern detected: {cand} - CORRECT (valid for this lot)")
                    print(f"✓ Success! Sensor ID '{cand}' detected at threshold {threshold_value}")
                    threshold_scale.set(threshold_value)
                    last_successful_threshold = threshold_value
                    ocr_result = cand
                    break

                # try simple confusion substitutions (T->J, K->H, etc.)
                mapped = _apply_confusions(cand)
                if mapped != cand and mapped in remaining_sensor_ids:
                    print(f"[OCR] Mapped '{cand}' -> '{mapped}' and matched remaining IDs")
                    threshold_scale.set(threshold_value)
                    last_successful_threshold = threshold_value
                    ocr_result = mapped
                    break

                if cand in already_scanned:
                    print(f"[OCR] ✓ Pattern detected: {cand} - INCORRECT (already scanned)")
                elif cand in valid_ids:
                    print(f"[OCR] ✓ Pattern detected: {cand} - INCORRECT (not in remaining list)")
                else:
                    print(f"[OCR] ✓ Pattern detected: {cand} - INCORRECT (wrong lot)")

                # Fuzzy match: compare cand and its mapped variant against remaining IDs
                best_match = None
                best_dist = None
                for variant in (cand, mapped):
                    vstr = variant.replace('-', '')
                    for rid in remaining_sensor_ids:
                        d = _levenshtein(vstr, rid.replace('-', ''))
                        if best_dist is None or d < best_dist:
                            best_dist = d
                            best_match = (rid, d, variant)

                # Accept small edit distances
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

# ---------- UI: video widget, controls, bindings ----------
video_label = Label(root, bg="black")
video_label.place(x=670, y=40, width=DISPLAY_W, height=DISPLAY_H)

# Bind mouse events for ROI manipulation
video_label.bind("<Button-1>", on_mouse_press)
video_label.bind("<B1-Motion>", on_mouse_drag)
video_label.bind("<ButtonRelease-1>", on_mouse_release)

# Title Label
title_label = tk.Label(root, text="MR Chip Alignment Measurement", font=("BiomeW04-Bold", 20, "bold"), bg="lightblue")
title_label.place(x=10, y=0)

sensor_id_label = Label(root, text="Sensor ID:", font=("Arial", 14), bg="lightblue", fg="black")
sensor_id_label.place(x=690, y=350)

sensor_id_textbox = tk.Text(root, height=1, width=17, font=("Arial", 14))
sensor_id_textbox.place(x=795, y=350)

threshold_label = Label(root, text="Threshold Level\n(110-200):", font=("Arial", 14), bg="lightblue", fg="black")
threshold_label.place(x=690, y=430)

threshold_scale = Scale(root, from_=110, to=200, orient=tk.HORIZONTAL, length=200, bg="#407ec9", fg="white", font=("Arial", 10), resolution=5)
threshold_scale.set(175)
threshold_scale.place(x=840, y=435)

read_button = Button(root, text="READ", command=capture_image_and_process, font=("Arial", 15), bg="#00cc44", fg="white", padx=20, pady=1)
read_button.place(x=800, y=380)

toggle_button = Button(root, text="Toggle View", command=lambda: globals().__setitem__('threshold_view', not threshold_view), font=("Arial", 15), bg="#407ec9", fg="white", padx=20, pady=1)
toggle_button.place(x=800, y=500)

roi_toggle_button = Button(root, text="ROI: OFF", command=toggle_roi, font=("Arial", 15), bg="#ff4444", fg="white", padx=20, pady=1)
roi_toggle_button.place(x=800, y=540)

specs_label = tk.Label(root, text='Specification:\n≤0.04', font=("Tahoma", 10, "bold"), bg="lightblue")
specs_label.place(x=570, y=70)

# ---------- Form entries ----------
labels = ["Lot Number:", "Current Process:", "Date and Time:", "Operator:"]
entries = {}
label_positions = {"Lot Number:": (10, 50), "Current Process:": (10, 75), "Date and Time:": (10, 100), "Operator:": (10, 125)}
entry_positions = {"Lot Number:": (120, 50), "Current Process:": (120, 75), "Date and Time:": (120, 100), "Operator:": (120, 125)}

for label_text in labels:
    label = tk.Label(root, text=label_text, font=("Arial", 10), bg="lightblue")
    label.place(x=label_positions[label_text][0], y=label_positions[label_text][1])
    entry = tk.Entry(root, width=30, justify='center')
    entry.place(x=entry_positions[label_text][0], y=entry_positions[label_text][1])
    entries[label_text] = entry

entries["Date and Time:"].config(state="readonly")
update_datetime()
entries["Lot Number:"].bind("<Return>", fetch_lot_info)

# ---------- Delete, Save, Table, BMSPopup (kept as before) ----------
def delete_action():
    for entry in entries.values():
        entry.config(state="normal")
        entry.delete(0, tk.END)
        entry.config(state="readonly" if entry == entries["Current Process:"] else "normal")
    entries["Current Process:"].config(state="normal")
    entries["Current Process:"].delete(0, tk.END)
    entries["Current Process:"].config(state="readonly")
    for row in range(20):
        for col in range(5):
            data_entry[row][col].config(state="normal")
            data_entry[row][col].config(bg="white")
            data_entry[row][col].delete(0, tk.END)
            if col == 0:
                data_entry[row][col].config(state="readonly")
        judgement_labels[row].config(text="", bg="lightblue")

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
        self.defect_entry = tk.Entry(self, width=31)
        self.defect_entry.place(x=105, y=135)

        tk.Label(self, text="Remarks:", bg='#3a6ba8', fg="white").place(x=5, y=165)
        self.remarks_entry = tk.Entry(self, width=31)
        self.remarks_entry.place(x=105, y=165)

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

        export_button = tk.Button(self, text="Export Defects / Remarks", command=self.export_data, bg="green", fg="white", font=("Tahoma", 10, "bold"), padx=20, pady=1, relief='raised', borderwidth=3)
        export_button.place(x=20, y=200)

        clear_button = tk.Button(self, text="CLEAR", command=self.clear_fields, bg="yellow", font=("Tahoma", 16, "bold"), padx=10, pady=1, relief='raised', borderwidth=3)
        clear_button.place(x=320, y=185)

        save_button = tk.Button(self, text="SAVE", command=self.save_data_and_advance, bg="green", fg="white", font=("Tahoma", 16, "bold"), padx=10, pady=1, relief='raised', borderwidth=3)
        save_button.place(x=460, y=185)

        delete_button = tk.Button(self, text="DELETE Defects / Remarks", command=self.delete_selected_row, bg="red", fg="white", font=("Tahoma", 10, "bold"), padx=20, pady=1, relief='raised', borderwidth=3)
        delete_button.place(x=20, y=235)

        self.columns = ("Sensor ID", "Defects", "Remarks")
        self.table = ttk.Treeview(self, columns=self.columns, show="headings", height=7)
        for col in self.columns:
            self.table.heading(col, text=col)
        self.table.place(x=5, y=280)

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
        if not self.operator_entry.get():
            messagebox.showwarning("Input Error", "Please enter Operator.")
            return
        selected_sensor = self.sensor_id_combobox.get().strip()
        if selected_sensor:
            found = False
            for row in self.table.get_children():
                sid, defect, remarks = self.table.item(row)["values"]
                if sid == selected_sensor and str(defect).strip():
                    found = True
                    break
            if not found:
                messagebox.showwarning("Input Error", f"Please add a defect entry for Sensor ID: {selected_sensor} in the table\nor clear the Sensor ID selection before saving.")
                return

        lot_number = self.lot_number
        current_process = self.current_process
        operator = self.operator_entry.get()
        proc_datetime = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        columns = process_column_mapping.get(current_process)

        if (not columns or len(columns) < 6) and str(self.lot_condition).upper() == "MP":
            messagebox.showerror("Configuration Error", f"Process mapping for '{current_process}' is missing or invalid.")
            return

        quantity_in = self.quantity_in_entry.get()
        quantity_out = self.quantity_out_entry.get()

        try:
            if self.csv_rows_data:
                conn_master = sqlite3.connect(db_path_masterlist)
                cursor_master = conn_master.cursor()
                for row in self.csv_rows_data:
                    sensor_id = row[0]
                    x_alignment1 = row[1]
                    y_alignment1 = row[2]
                    x_alignment2 = row[3]
                    y_alignment2 = row[4]
                    try:
                        cursor_master.execute("""
                            UPDATE lot_masterlist
                            SET X_alignment_1 = ?, Y_alignment_1 = ?, X_alignment_2 = ?, Y_alignment_2 = ?
                            WHERE sensor_id = ?
                        """, (x_alignment1, y_alignment1, x_alignment2, y_alignment2, sensor_id))
                    except sqlite3.OperationalError:
                        pass
                conn_master.commit()
                conn_master.close()

            if columns and len(columns) >= 6 and str(self.lot_condition).upper() == "MP":
                conn = sqlite3.connect(db_path_tracking)
                cursor = conn.cursor()
                sensor_ids_in_table = [self.table.item(row)["values"][0] for row in self.table.get_children()]
                sensor_ids_with_defects = [self.table.item(row)["values"][0] for row in self.table.get_children() if self.table.item(row)["values"][1]]
                for row in self.table.get_children():
                    sid, defect, remarks = self.table.item(row)["values"]
                    cursor.execute(f"""
                        UPDATE lot_tracking
                        SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, {columns[3]}=?, {columns[4]}=?, {columns[5]}=?
                        WHERE lot_number=? AND sensor_id=?
                    """, (quantity_in, quantity_out, defect, remarks, proc_datetime, operator, lot_number, sid))
                cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot_number,))
                all_sensors_for_lot = [r[0] for r in cursor.fetchall()]
                remaining_sensors = set(all_sensors_for_lot) - set(sensor_ids_in_table)
                for sid in remaining_sensors:
                    cursor.execute(f"""
                        UPDATE lot_tracking
                        SET {columns[0]}=?, {columns[1]}=?, {columns[2]}='', {columns[3]}='', {columns[4]}=?, {columns[5]}=?
                        WHERE lot_number=? AND sensor_id=?
                    """, (quantity_in, quantity_out, proc_datetime, operator, lot_number, sid))

                try:
                    cursor.execute("SELECT database_path FROM lot_tracking WHERE lot_number=? LIMIT 1", (lot_number,))
                    res = cursor.fetchone()
                    if res and res[0]:
                        text_file_path = res[0]
                        try:
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

                if str(self.lot_condition).upper() == "MP":
                    try:
                        next_process = process_flow[process_flow.index(current_process) + 1]
                    except Exception:
                        next_process = current_process
                    cursor.execute("UPDATE lot_tracking SET current_process=? WHERE lot_number=?", (next_process, lot_number))

                conn.commit()
                conn.close()
            else:
                if str(self.lot_condition).upper() != "EVAL":
                    messagebox.showwarning("Warning", f"No process-column mapping available for '{current_process}'. No lot_tracking updates performed.")

            base_folder = r"\\phlsvr08\BMS Data\Assembly Data\MR Chip Alignment"
            current_year = time.strftime("%Y")
            current_month_name = time.strftime("%B")
            current_date_formatted = time.strftime("%m.%d.%Y")
            export_folder = os.path.join(base_folder, current_year, current_month_name, current_date_formatted)
            os.makedirs(export_folder, exist_ok=True)
            csv_filename = os.path.join(export_folder, f"MR_Chip_Alignment_{lot_number}.csv")

            if self.csv_rows_data:
                with open(csv_filename, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(["Lot Number", lot_number])
                    writer.writerow(["Processed Date and Time", proc_datetime])
                    writer.writerow(["Operator", operator])
                    writer.writerow([])
                    writer.writerow(["Sensor ID", "X-alignment 1", "Y-alignment 1", "X-alignment 2", "Y-alignment 2", "Judgement"])
                    for row_data in self.csv_rows_data:
                        writer.writerow(row_data)
                messagebox.showinfo("CSV Export", f"Data successfully exported to:\n{csv_filename}")

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
                x_alignment1 = data_entry[row_idx][1].get().strip()
                y_alignment1 = data_entry[row_idx][2].get().strip()
                x_alignment2 = data_entry[row_idx][3].get().strip()
                y_alignment2 = data_entry[row_idx][4].get().strip()
                judgement = judgement_labels[row_idx].cget("text").strip()
                csv_rows_data.append([sensor_id, x_alignment1, y_alignment1, x_alignment2, y_alignment2, judgement])
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

        lot_condition = get_lot_condition(lot_number)
        if str(lot_condition).upper() == "EVAL":
            combobox_candidates_local = []

        popup = BMSPopup(root, lot_number, current_process, operator,
                         sensor_list_local, combobox_candidates_local,
                         failed_sensor_list_local, blank_judgement_list_local, csv_rows_data, lot_condition)
        popup.grab_set()
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

# UI layout: table and controls
delete_button = tk.Button(root, text="Clear Data", font=("Tahoma", 12, "bold"), padx=10, pady=1, bg="yellow", command=delete_action, relief='raised', borderwidth=3)
delete_button.place(x=350, y=50)
save_button = tk.Button(root, text="SAVE", font=("Tahoma", 12, "bold"), padx=32, pady=1, bg="orange", command=save_action, relief='raised', borderwidth=3)
save_button.place(x=350, y=100)

headers = ["No.", "Sensor ID", "X-alignment 1", "Y-alignment 1", "X-alignment 2", "Y-alignment 2", "Judgement"]
for col, header in enumerate(headers):
    label = tk.Label(root, text=header, font=("Arial", 10, "bold"), bg="lightblue", relief="ridge")
    if header == "No.":
        label.place(x=10, y=160)
    else:
        label.place(x=-20 + col*100, y=160)

data_entry = []
judgement_labels = []
vcmd = (root.register(validate_numeric_input), '%P')

for row in range(20):
    row_entries = []
    number_label = tk.Label(root, text=str(row + 1), width=3, bg="lightblue", relief="ridge")
    number_label.place(x=10, y=190 + row*23)
    for col in range(5):
        if col == 0:
            entry = tk.Entry(root, width=20, justify='center')
            entry.place(x=45 + col*100, y=190 + row*23)
            entry.config(state="readonly")
        else:
            entry = tk.Entry(root, width=10, validate="key", validatecommand=vcmd, justify='center')
            entry.place(x=195 + (col-1)*100, y=190 + row*23)
            entry.config(state="readonly")
            entry.bind("<Return>", lambda event, r=row, c=col: navigate_on_enter(event, r, c))
        row_entries.append(entry)
    data_entry.append(row_entries)
    judgement_label = tk.Label(root, text="", width=10, bg="lightblue", relief="ridge")
    judgement_label.place(x=580, y=190 + row*23)
    judgement_labels.append(judgement_label)

start_camera()

def on_closing():
    global cap
    if cap and cap.isOpened():
        cap.release()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
entries["Lot Number:"].focus_set()
root.mainloop()