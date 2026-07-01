import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageFilter, ImageOps
import qrcode
import os
import tempfile
import usb.core
import usb.util
import sqlite3
import time
import json
from datetime import datetime
import cv2
import pytesseract
import threading
import numpy as np
import re

# ----------------------------
# Configuration
# ----------------------------
MM_TO_INCH = 1 / 25.4
# Print-specific settings (adjusted for die-cut labels)
DPI = 600
WIDTH_MM, HEIGHT_MM = 20, 8  # Actual printable area (20mm - 2mm left - 2mm right = 16mm)
# Exact pixel dimensions for 203 DPI
WIDTH_PX = int(WIDTH_MM * DPI * MM_TO_INCH)  # 128 pixels
HEIGHT_PX = int(HEIGHT_MM * DPI * MM_TO_INCH)  # 64 pixels

# GUI preview settings (adjusted for horizontal label)
PREVIEW_SCALE = 0.6  # 60% size for preview (doesn't affect printing)
PREVIEW_W, PREVIEW_H = int(WIDTH_PX * PREVIEW_SCALE), int(HEIGHT_PX * PREVIEW_SCALE)
SCALE_F = PREVIEW_W / WIDTH_PX

# Global image references (to prevent garbage collection)
_global_images = {}

# ✅ Compatibility wrapper for resampling
try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.ANTIALIAS

# TDK Logo Path
TDK_LOGO_PATH = r"C:\Users\a493353\Downloads\TDK-Logo.png"

# Godex RT863i USB Settings
GODEX_VENDOR_ID = 0x0B9B  # Godex vendor ID
GODEX_PRODUCT_ID = 0x0863  # RT863i product ID (may vary, will auto-detect)

# ----- Database Config -----
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

# ----- Helper: Get Allowed Sensor IDs (exclude sensors with defects in previous processes) -----
def get_allowed_sensor_ids(lot_number, current_process):
    """Return sensor_ids allowed to proceed for the given process (exclude sensors with defects in previous processes)"""
    try:
        conn = sqlite3.connect(db_path_tracking)
        cur = conn.cursor()

        # Determine previous-process defect columns (safely)
        try:
            current_index = process_flow.index(current_process)
        except Exception:
            current_index = -1

        previous_defect_columns = []
        if current_index > 0:
            for proc in process_flow[:current_index]:
                if proc in process_column_mapping and isinstance(process_column_mapping[proc], (list, tuple)) and len(process_column_mapping[proc]) > 2:
                    previous_defect_columns.append(process_column_mapping[proc][2])

        if previous_defect_columns:
            defect_conditions = " AND ".join(f"({col} IS NULL OR {col} = '')" for col in previous_defect_columns)
            query = f"SELECT sensor_id FROM lot_tracking WHERE lot_number = ? AND {defect_conditions}"
            cur.execute(query, (lot_number,))
            rows = cur.fetchall()
            allowed = [r[0] for r in rows]
        else:
            cur.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
            allowed = [r[0] for r in cur.fetchall()]

        conn.close()
        return allowed
    except sqlite3.Error:
        return []

# Fonts for final rendered image
def load_pillow_fonts(height_px):
    try:
        # Optimized fonts for 128x64 label (16mm x 8mm printable area)
        font_confidential = ImageFont.truetype("arialbd.ttf", 40)
        font_bms = ImageFont.truetype("arialbd.ttf", 30)
        font_sensor = ImageFont.truetype("arial.ttf", 38)
    except Exception: 
        font_confidential = font_bms = font_sensor = ImageFont.load_default()
    return font_confidential, font_bms, font_sensor

# Generate Label 1: CONFIDENTIAL + TDK Logo + BMS-SENSOR-05
def make_label1_image():
    label1 = Image.new("RGB", (WIDTH_PX, HEIGHT_PX), "white")
    draw = ImageDraw.Draw(label1)
    font_confidential, font_bms, _ = load_pillow_fonts(HEIGHT_PX)
    
    # Load TDK logo
    tdk_logo = load_tdk_logo(HEIGHT_PX)
    
    # Calculate positions for centered layout (scaled up 4x)
    y_offset = 5
    
    # Draw CONFIDENTIAL at top
    conf_text = "CONFIDENTIAL"
    try:
        bbox = draw.textbbox((0, 0), conf_text, font=font_confidential)
        conf_width = bbox[2] - bbox[0]
    except:
        conf_width = len(conf_text) * 16
    conf_x = (WIDTH_PX - conf_width) // 2
    draw.text((conf_x, y_offset), conf_text, font=font_confidential, fill="black")
    
    # Paste TDK logo in center
    if tdk_logo:
        logo_w, logo_h = tdk_logo.size
        logo_x = (WIDTH_PX - logo_w) // 2 -10
        logo_y = (HEIGHT_PX - logo_h) // 2 -10
        label1.paste(tdk_logo, (logo_x, logo_y), tdk_logo)
    
    # Draw BMS-SENSOR-05 at bottom
    bms_text = "BMS-SENSOR-05"
    try:
        bbox = draw.textbbox((0, 0), bms_text, font=font_bms)
        bms_width = bbox[2] - bbox[0]
    except:
        bms_width = len(bms_text) * 20
    bms_x = (WIDTH_PX - bms_width) // 2 -10
    bms_y = HEIGHT_PX - 60 - y_offset
    draw.text((bms_x, bms_y), bms_text, font=font_bms, fill="black")
    
    return label1

# Generate Label 2: Sensor ID + QR Code
def make_label2_image(sensor_text):
    label2 = Image.new("RGB", (WIDTH_PX, HEIGHT_PX), "white")
    _, _, font_sensor = load_pillow_fonts(HEIGHT_PX)

    # ---------- QR CODE ----------
    qr_size = 225
    qr = qrcode.make(sensor_text)
    qr = qr.resize((qr_size, qr_size), RESAMPLE)

    qr_x = WIDTH_PX - qr_size - 50
    qr_y = -35
    label2.paste(qr, (qr_x, qr_y))

    # ---------- FORMAT SENSOR TEXT ----------
    parts = sensor_text.split('-')

    if len(parts) >= 4:
        # Merge first two parts into one linel
        sensor_lines = [parts[0] + '-' + parts[1] + '-']
        # Keep remaining parts as separate lines
        for part in parts[2:]:
            sensor_lines.append(part)
    else:
        # fallback
        sensor_lines = []
        for i, part in enumerate(parts):
            if i < len(parts) - 1:
                sensor_lines.append(part + "-")
            else:
                sensor_lines.append(part)

    sensor_multiline = "\n".join(sensor_lines)


    # ---------- DRAW TEXT ON TEMP IMAGE ----------
    temp_img = Image.new("RGBA", (300, HEIGHT_PX), (255, 255, 255, 0))
    temp_draw = ImageDraw.Draw(temp_img)

    temp_draw.multiline_text(
        (0, 0),
        sensor_multiline,
        font=font_sensor,
        fill="black",
        spacing=0
    )

    # ---------- ROTATE (THIS CONTROLS ANGLE) ----------
    rotated_text = temp_img.rotate(90, expand=True)  # ✅ correct orientation
    rotated_text = rotated_text.crop(rotated_text.getbbox())

    # ---------- PASTE ON LABEL ----------
    text_x = 60   # left / right
    text_y = 30    # up / down
    label2.paste(rotated_text, (text_x, text_y), rotated_text)

    return label2


# Load and resize TDK logo
def load_tdk_logo(size_px):
    try:
        logo = Image.open(TDK_LOGO_PATH).convert("RGBA")
        logo_w, logo_h = logo.size
        # Resize logo to fit within the narrower label
        new_h = 180
        if new_h > 0:
            new_w = int((logo_w / logo_h) * new_h)
            logo = logo.resize((new_w, new_h), RESAMPLE)
        return logo
    except FileNotFoundError:
        messagebox.showwarning("Warning", f"TDK logo file not found at: {TDK_LOGO_PATH}")
        return None
    except Exception as e:
        messagebox.showwarning("Warning", f"Could not load TDK logo: {e}")
        return None

# Create combined preview showing both labels side by side
def make_combined_preview(label1, label2):
    # Create a preview showing both labels side by side (horizontally)
    preview_label1 = label1.resize((PREVIEW_W, PREVIEW_H), RESAMPLE)
    preview_label2 = label2.resize((PREVIEW_W, PREVIEW_H), RESAMPLE)
    
    # Combine both previews horizontally with a small gap
    gap = 10
    combined_width = PREVIEW_W * 2 + gap
    combined = Image.new("RGB", (combined_width, PREVIEW_H), "lightgray")
    combined.paste(preview_label1, (0, 0))
    combined.paste(preview_label2, (PREVIEW_W + gap, 0))
    
    return combined

# Find Godex printer via USB
def find_godex_printer():
    """Find Godex RT863i printer via USB"""
    try:
        # Try to find Godex printer by vendor ID
        devices = usb.core.find(find_all=True, idVendor=GODEX_VENDOR_ID)
        godex_devices = []
        
        for dev in devices:
            try:
                product_name = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "Unknown"
                godex_devices.append({
                    'device': dev,
                    'name': product_name,
                    'vid': hex(dev.idVendor),
                    'pid': hex(dev.idProduct)
                })
            except:
                pass
        
        return godex_devices
    except Exception as e:
        return []

# Send to printer via USB
def send_to_printer_usb(data, device):
    """Send EZPL data to Godex RT863i via USB"""
    try:
        # Detach kernel driver if necessary
        if device.is_kernel_driver_active(0):
            try:
                device.detach_kernel_driver(0)
            except:
                pass
        
        # Set configuration
        device.set_configuration()
        
        # Get endpoint
        cfg = device.get_active_configuration()
        intf = cfg[(0,0)]
        
        # Find OUT endpoint
        ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
        )
        
        if ep_out is None:
            raise Exception("Could not find USB OUT endpoint")
        
        # Send data
        ep_out.write(data.encode('ascii'))
        
        return True
        
    except usb.core.USBError as e:
        raise Exception(f"USB Error: {e}\nMake sure no other program is using the printer.")
    except Exception as e:
        raise Exception(f"Communication Error: {e}")

# Convert image to EZPL bitmap format for Godex printer
def image_to_ezpl_bitmap(image, x, y):
    """Convert PIL Image to EZPL bitmap command"""
    # Convert to 1-bit black and white
    bw_image = image.convert('1')
    width, height = bw_image.size
    
    # Get image data
    pixels = bw_image.load()
    
    # Calculate bytes per row (must be multiple of 8)
    bytes_per_row = (width + 7) // 8
    
    # Build bitmap data
    bitmap_data = []
    for row in range(height):
        byte_val = 0
        bit_pos = 7
        for col in range(width):
            if pixels[col, row] == 0:  # Black pixel
                byte_val |= (1 << bit_pos)
            bit_pos -= 1
            if bit_pos < 0:
                bitmap_data.append(byte_val)
                byte_val = 0
                bit_pos = 7
        # Pad last byte if needed
        if bit_pos != 7:
            bitmap_data.append(byte_val)
    
    # Create EZPL command
    ezpl_cmd = f"GW{x},{y},{bytes_per_row},{height},"
    ezpl_cmd += ''.join([f"{b:02X}" for b in bitmap_data])
    return ezpl_cmd

# Generate EZPL commands for label
def generate_ezpl_label(label_image, label_num):
    """Generate EZPL commands for Godex RT863i with proper die-cut label handling"""
    commands = []
    
    # Initialize printer and clear buffer
    commands.append("^Q20,3")   # Set label height (20mm) and gap (3mm)
    commands.append("^W80")     # Set label width (80mm)
    commands.append("^H10")     # Set heat/darkness (10 = medium)
    commands.append("^S4")      # Set print speed (4 = medium speed for accuracy)
    commands.append("^P1")      # Print quantity: 1 label only
    commands.append("^C1")      # Clear image buffer before printing
    commands.append("^E20")     # Gap sensor sensitivity (20 = standard)
    commands.append("^L")       # Label start position
    commands.append("Dy2-me-dd")  # Date format (optional)
    commands.append("Th:m:s")     # Time format (optional)
    
    # Positioning and alignment commands for die-cut labels
    commands.append("^R0")      # Rotation (0 = no rotation)
    commands.append("^O0")      # Print orientation
    commands.append("^D0")      # Double buffer off
    commands.append("^AT")      # Tear-off mode (auto tear after print)
    commands.append("^c0000")   # Tear-off position adjustment (0 = default)
    
    # Add a small delay command to ensure proper label positioning
    commands.append("~X")       # Pause before printing
    
    # Convert and add bitmap at position (0,0)
    bitmap_cmd = image_to_ezpl_bitmap(label_image, 0, 0)
    commands.append(bitmap_cmd)
    
    # End label and print
    commands.append("E")        # End of label format and print
    
    return '\n'.join(commands)

# Alternative: Send via Windows print spooler for USB printers
def send_to_printer_windows(label_image, printer_name="Godex RT863i+"):
    """Send image to printer via Windows print spooler"""
    try:
        import win32print
        import win32ui
        from PIL import ImageWin
        
        # Get printer handle
        hprinter = win32print.OpenPrinter(printer_name)
        
        # Start document
        hdc = win32ui.CreateDC()
        hdc.CreatePrinterDC(printer_name)
        hdc.StartDoc("Label")
        hdc.StartPage()
        
        # Print image
        dib = ImageWin.Dib(label_image)
        dib.draw(hdc.GetHandleOutput(), (0, 0, label_image.width, label_image.height))
        
        # End document
        hdc.EndPage()
        hdc.EndDoc()
        hdc.DeleteDC()
        
        win32print.ClosePrinter(hprinter)
        return True
        
    except ImportError:
        raise Exception("pywin32 not installed. Install with: pip install pywin32")
    except Exception as e:
        raise Exception(f"Windows Print Error: {e}")

# ----- Global variables -----
sensor_ids_no_defects = []
current_process = ""

# ----- UI: main window -----
root = tk.Tk()
root.title("Labelling")
root.geometry("1000x660")  # Adjusted width
root.configure(bg="lightblue")
root.resizable(False, False)

# Make messagebox calls safe to call from worker threads by scheduling via `root.after`
_orig_showerror = messagebox.showerror
_orig_showwarning = messagebox.showwarning
_orig_showinfo = messagebox.showinfo
def _safe_call(fn, title, msg, **kwargs):
    try:
        # Ensure dialog has parent set so it appears on top of the main window
        kwargs.setdefault('parent', root)
        root.after(0, lambda: fn(title, msg, **kwargs))
    except Exception:
        try:
            kwargs.setdefault('parent', root)
            fn(title, msg, **kwargs)
        except Exception:
            pass

messagebox.showerror = lambda title, msg, **kw: _safe_call(_orig_showerror, title, msg, **kw)
messagebox.showwarning = lambda title, msg, **kw: _safe_call(_orig_showwarning, title, msg, **kw)
messagebox.showinfo = lambda title, msg, **kw: _safe_call(_orig_showinfo, title, msg, **kw)

# Modal dialog helpers (use Toplevel to guarantee on-screen modal dialogs)
def _modal_dialog(title, msg, kind='info'):
    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.transient(root)
    dlg.resizable(False, False)
    try:
        dlg.configure(bg='white')
    except Exception:
        pass
    frm = tk.Frame(dlg, bg=dlg.cget('bg'))
    frm.pack(padx=12, pady=12)
    lbl = tk.Label(frm, text=msg, justify='left', wraplength=480, bg=frm.cget('bg'))
    lbl.pack(padx=6, pady=6)
    btn = tk.Button(frm, text='OK', width=12, command=dlg.destroy)
    btn.pack(pady=(6,0))
    dlg.update_idletasks()
    # center over root
    try:
        rx = root.winfo_rootx(); ry = root.winfo_rooty(); rw = root.winfo_width(); rh = root.winfo_height()
        dw = dlg.winfo_width(); dh = dlg.winfo_height()
        x = rx + max(0, (rw - dw)//2)
        y = ry + max(0, (rh - dh)//2)
        dlg.geometry(f'+{x}+{y}')
    except Exception:
        pass
    dlg.grab_set()
    root.wait_window(dlg)

def show_modal_error(title, msg):
    root.after(0, lambda: _modal_dialog(title, msg, 'error'))

def show_modal_warning(title, msg):
    root.after(0, lambda: _modal_dialog(title, msg, 'warning'))

def show_modal_info(title, msg):
    root.after(0, lambda: _modal_dialog(title, msg, 'info'))

# Title
title_label = tk.Label(root, text="Labelling", font=("BiomeW04-Bold", 16, "bold"), bg="lightblue")
title_label.place(x=10, y=0)

# Status label - positioned below Operator field
status_label = tk.Label(root, text="Ready", fg="blue", bg="lightblue", font=("Arial", 9, "bold"))
status_label.place(x=10, y=140)

# ----- Fetch lot info -----
def fetch_lot_info(event=None):
    global sensor_ids_no_defects
    global current_process

    import re

    # Remove all whitespace and non-printable characters
    lot_number_raw = entries["Lot Number:"].get()
    lot_number = re.sub(r'\s+', '', lot_number_raw)  # Removes spaces, tabs, newlines

    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number.")
        return

    conn_track = None
    conn_master = None
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

        current_process = str(row[0]).strip()  # Remove leading/trailing whitespace


        # 2) Determine lot condition (MP or Eval)
        lot_condition = get_lot_condition(lot_number)

        # 3) Replace or set the Current Process widget depending on lot_condition
        if str(lot_condition).upper() == "MP":
            if current_process.lower() != "labelling":  # lowercase for comparison
                error_msg = f"The lot number inputted is not for Labelling.\nCurrent process: {current_process}"
                if conn_track:
                    conn_track.close()
                if conn_master:
                    conn_master.close()
                messagebox.showerror("Error", error_msg)
                delete_action()
                return


        # 4) Replace or set the Current Process widget depending on lot_condition
        cur_widget = entries.get("Current Process:")
        place_x = place_y = None
        try:
            if cur_widget is not None:
                pi = cur_widget.place_info()
                if pi:
                    place_x = int(pi.get("x", 115))
                    place_y = int(pi.get("y", 65))
                else:
                    place_x = cur_widget.winfo_x()
                    place_y = cur_widget.winfo_y()
        except Exception:
            place_x, place_y = 115, 65

        if str(lot_condition).upper() == "EVAL":
            # For EVAL lots, could add dropdown choices if needed
            # For now, just use Entry widget
            if isinstance(entries.get("Current Process:"), ttk.Combobox):
                try:
                    entries["Current Process:"].destroy()
                except Exception:
                    pass
                e = tk.Entry(root, width=30, justify='center')
                e.place(x=(place_x if place_x is not None else 115), y=(place_y if place_y is not None else 65))
                entries["Current Process:"] = e
            entries["Current Process:"].config(state="normal")
            entries["Current Process:"].delete(0, tk.END)
            entries["Current Process:"].insert(0, current_process)
            entries["Current Process:"].config(state="readonly")
        else:
            if isinstance(entries.get("Current Process:"), ttk.Combobox):
                try:
                    entries["Current Process:"].destroy()
                except Exception:
                    pass
                e = tk.Entry(root, width=30, justify='center')
                e.place(x=(place_x if place_x is not None else 115), y=(place_y if place_y is not None else 65))
                entries["Current Process:"] = e
            entries["Current Process:"].config(state="normal")
            entries["Current Process:"].delete(0, tk.END)
            entries["Current Process:"].insert(0, current_process)
            entries["Current Process:"].config(state="readonly")

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

        # Get total sensor count for comparison
        cur_track.execute("SELECT COUNT(*) FROM lot_tracking WHERE lot_number = ?", (lot_number,))
        total_sensors = cur_track.fetchone()[0]
        
        if not sensor_ids_no_defects:
            messagebox.showerror("No Sensors Available", 
                               f"No sensors can proceed to this process.\n\n"
                               f"Total sensors in lot: {total_sensors}\n"
                               f"Sensors with defects from previous processes: {total_sensors}\n\n"
                               f"All sensors have been rejected in previous processes.")
            conn_track.close()
            delete_action()
            return
        
        # Show info about filtered sensors
        rejected_count = total_sensors - len(sensor_ids_no_defects)
        if rejected_count > 0:
            print(f"INFO: {rejected_count} sensor(s) excluded due to defects in previous processes")
            print(f"Proceeding with {len(sensor_ids_no_defects)} sensor(s) without defects")
            messagebox.showinfo("Lot Loaded", 
                              f"Lot {lot_number} loaded successfully.\n\n"
                              f"Total sensors: {total_sensors}\n"
                              f"Sensors with previous defects: {rejected_count}\n"
                              f"Sensors ready for this process: {len(sensor_ids_no_defects)}")

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
            "QA Final Inspection": ["QA_Final_bottom", "QA_Final_top", "QA_Final_sensor"],
            "Labelling": []  # Labelling doesn't store measurement values in masterlist
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

        # Update status to show lot is validated
        status_label.config(text="Lot validated", fg="green")

        conn_track.close()

    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")
        if conn_track:
            conn_track.close()
        if conn_master:
            conn_master.close()
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")
        if conn_track:
            conn_track.close()
        if conn_master:
            conn_master.close()

# Function to update the date and time entry
def update_datetime():
    current_time = time.strftime("%Y-%m-%d %I:%M:%S %p")
    entries["Date and Time:"].config(state="normal")
    entries["Date and Time:"].delete(0, tk.END)
    entries["Date and Time:"].insert(0, current_time)
    entries["Date and Time:"].config(state="readonly")
    root.after(1000, update_datetime)

# ----- Delete helper -----
def delete_action():
    for entry in entries.values():
        entry.config(state="normal")
        entry.delete(0, tk.END)
        entry.config(state="readonly" if entry == entries["Current Process:"] else "normal")
    status_label.config(text="Ready", fg="blue")
    
    # Clear the table
    for i in range(20):
        sensor_id_labels[i].delete(0, tk.END)
        status_labels[i].config(text="", bg="white")

# ---------- BMS Popup class for Labelling ----------
class BMSPopup(tk.Toplevel):
    def __init__(self, master, lot_number, current_process, operator,
                 sensor_list, combobox_candidates, not_printed_sensor_list, unscanned_sensor_list, 
                 print_status_data, lot_condition="MP", total_lot_count=0, unscanned_sensors=None, printed_sensors=None):
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
        self.not_printed_sensor_list = not_printed_sensor_list[:]
        self.unscanned_sensor_list = unscanned_sensor_list[:]
        self.print_status_data = print_status_data[:]
        self.lot_condition = str(lot_condition).strip()
        self.total_lot_count = total_lot_count if total_lot_count > 0 else len(sensor_list)
        self.unscanned_sensors = unscanned_sensors if unscanned_sensors else []
        self.printed_sensors = printed_sensors if printed_sensors else []

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

        # Sensor ID Combobox - include not printed AND unscanned sensors
        tk.Label(self, text="Sensor ID:", bg='#3a6ba8', fg="white").place(x=5, y=105)
        
        # Combine all sensors that need defects for the dropdown
        all_sensors_needing_defects = list(set(self.combobox_candidates + self.unscanned_sensors))
        all_sensors_needing_defects.sort()  # Sort for easier selection
        
        self.sensor_id_combobox = ttk.Combobox(self, values=all_sensors_needing_defects, width=28)
        self.sensor_id_combobox.place(x=105, y=105)
        if all_sensors_needing_defects:
            self.sensor_id_combobox.set(all_sensors_needing_defects[0])

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

        # Populate Quantity IN / OUT
        # Quantity IN = TOTAL sensors in the lot (not just scanned)
        # Quantity OUT = Total - (not printed + unscanned)
        sensors_that_printed = len(self.printed_sensors)
        
        self.quantity_in_entry.delete(0, tk.END)
        self.quantity_in_entry.insert(0, str(self.total_lot_count))
        self.quantity_out_entry.delete(0, tk.END)
        self.quantity_out_entry.insert(0, str(sensors_that_printed))

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
            messagebox.showwarning("Input Error", "Please input defects.")
            return
    
        # Allow empty sensor ID - just add defect entry
        if sensor_id:
            # Check if sensor ID already exists in table
            existing_ids = [self.table.item(row)["values"][0] for row in self.table.get_children()]
            if sensor_id in existing_ids:
                messagebox.showwarning("Input Error", "Sensor ID already exists in the table.")
                return
        
        # Insert into table (sensor ID can be empty)
        self.table.insert('', 'end', values=(sensor_id, defect, remarks))
        self.update_quantity_out()
        self.clear_fields()
            
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
    
        # Calculate sensors that need defects:
        # 1. Not printed sensors (scanned but not printed)
        # 2. Unscanned sensors (not scanned at all in this session)
        sensors_needing_defects_count = len(self.not_printed_sensor_list) + len(self.unscanned_sensors)
        
        # Count how many defect entries are in the table (regardless of sensor ID)
        defect_entries_count = len([row for row in self.table.get_children() if self.table.item(row)["values"][1]])
        
        # Check if we have enough defect entries
        if defect_entries_count < sensors_needing_defects_count:
            messagebox.showerror(
                "Missing Defects/Remarks",
                f"Total sensors needing defects: {sensors_needing_defects_count}\n"
                f"  - Not printed: {len(self.not_printed_sensor_list)}\n"
                f"  - Not scanned: {len(self.unscanned_sensors)}\n\n"
                f"Defect entries in table: {defect_entries_count}\n"
                f"Still need: {sensors_needing_defects_count - defect_entries_count} more defect entries"
            )
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
        quantity_in = self.quantity_in_entry.get()
        quantity_out = self.quantity_out_entry.get()
    
        # Get mapping for current process
        columns = process_column_mapping.get(current_process)
        
        if not columns or len(columns) < 6:
            messagebox.showerror("Configuration Error", f"Column mapping not found for process: {current_process}")
            return
        
        print(f"Using columns for {current_process}: {columns}")
    
        try:
            # 1) Update lot_masterlist with labelling status data
            if self.print_status_data:
                conn_master = sqlite3.connect(db_path_masterlist)
                cursor_master = conn_master.cursor()
                for row in self.print_status_data:
                    sensor_id = row[0]
                    status = row[1] if len(row) > 1 else None
    
                    if current_process == "Labelling":
                        try:
                            cursor_master.execute("""
                                UPDATE lot_masterlist
                                SET Labelling = ?
                                WHERE sensor_id = ?
                            """, (status, sensor_id))
                        except sqlite3.OperationalError:
                            pass
                conn_master.commit()
                conn_master.close()
    
            # 2) Update lot_tracking
            conn = sqlite3.connect(db_path_tracking)
            cursor = conn.cursor()

            # Get defects from table as a dictionary (for sensors with IDs)
            defects_dict = {}
            generic_defects = []  # Defects without sensor IDs
            
            for row in self.table.get_children():
                sid, defect, remarks = self.table.item(row)["values"]
                if sid:
                    defects_dict[sid] = (defect, remarks)
                else:
                    generic_defects.append((defect, remarks))

            # Get all sensors in the lot
            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot_number,))
            all_sensors_for_lot = [r[0] for r in cursor.fetchall()]
            
            # Assign generic defects to sensors that need them (not printed, unscanned)
            sensors_needing_generic_defects = []
            for sid in all_sensors_for_lot:
                if sid in self.not_printed_sensor_list or sid in self.unscanned_sensors:
                    if sid not in defects_dict:  # Only if not already assigned
                        sensors_needing_generic_defects.append(sid)
            
            # Assign generic defects to sensors
            for i, sid in enumerate(sensors_needing_generic_defects):
                if i < len(generic_defects):
                    defects_dict[sid] = generic_defects[i]
            
            # Update ALL sensors in the lot (only if MP)
            if str(self.lot_condition).upper() == "MP":
                for sid in all_sensors_for_lot:
                    if sid in defects_dict:
                        # Sensor has defect/remark entry - mark as "Not Printed"
                        defect, remarks = defects_dict[sid]
                        print(f"Updating {sid}: Not Printed (defect: {defect})")
                        cursor.execute(f"""
                            UPDATE lot_tracking
                            SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, 
                                {columns[3]}=?, {columns[4]}=?, {columns[5]}=?
                            WHERE lot_number=? AND sensor_id=?
                        """, (quantity_in, quantity_out, 'Not Printed', remarks, proc_datetime, operator, lot_number, sid))
                    elif sid in self.printed_sensors:
                        # Sensor printed successfully - mark as "Printed"
                        print(f"Updating {sid}: Printed")
                        cursor.execute(f"""
                            UPDATE lot_tracking
                            SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, 
                                {columns[3]}=?, {columns[4]}=?, {columns[5]}=?
                            WHERE lot_number=? AND sensor_id=?
                        """, (quantity_in, quantity_out, 'Printed', '', proc_datetime, operator, lot_number, sid))
                    else:
                        # Sensor not in any list - mark as "Not Printed"
                        print(f"Updating {sid}: Not Printed (not scanned)")
                        cursor.execute(f"""
                            UPDATE lot_tracking
                            SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, 
                                {columns[3]}=?, {columns[4]}=?, {columns[5]}=?
                            WHERE lot_number=? AND sensor_id=?
                        """, (quantity_in, quantity_out, 'Not Printed', '', proc_datetime, operator, lot_number, sid))
                
                # Advance current_process to next step
                try:
                    next_proc = process_flow[process_flow.index(self.current_process) + 1]
                    cursor.execute("UPDATE lot_tracking SET current_process=? WHERE lot_number=?", (next_proc, lot_number))
                    print(f"Advanced lot to next process: {next_proc}")
                except (ValueError, IndexError):
                    # Current process not in flow or is last process
                    print("Current process is last in flow or not found")
                    pass

            conn.commit()
            conn.close()

            messagebox.showinfo("Success", "Data saved successfully!")
            self.destroy()
            # Clear main window after successful save
            delete_action()

        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"An error occurred: {e}")
            import traceback
            traceback.print_exc()
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()

# ----- Save action -----
def save_action():
    try:
        lot_number = entries["Lot Number:"].get().strip()
        operator = entries["Operator:"].get().strip()
        
        if not lot_number:
            messagebox.showwarning("Input Error", "Please enter a Lot Number.")
            return
        
        if not operator:
            messagebox.showwarning("Input Error", "Please enter an Operator name.")
            return
        
        # Collect scanned sensors and their print status
        sensor_list_local = []
        print_status_data = []
        printed_sensor_list_local = []
        not_printed_sensor_list_local = []
        
        for i in range(20):
            sensor_id = sensor_id_labels[i].get().strip()
            if sensor_id:
                sensor_list_local.append(sensor_id)
                status = status_labels[i].cget("text").strip()
                print_status_data.append((sensor_id, status))
                
                if status == "Printed":
                    printed_sensor_list_local.append(sensor_id)
                else:
                    not_printed_sensor_list_local.append(sensor_id)
        
        if not sensor_list_local:
            messagebox.showwarning("No Data", "No sensors have been scanned yet.")
            return
        
        # Get all sensors for this lot
        conn = sqlite3.connect(db_path_tracking)
        cursor = conn.cursor()
        cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
        all_lot_sensors = [r[0] for r in cursor.fetchall()]
        conn.close()
        
        total_lot_count = len(all_lot_sensors)
        unscanned_sensors = [sid for sid in all_lot_sensors if sid not in sensor_list_local]
        
        # Determine sensors that need defects (not printed + unscanned)
        combobox_candidates_local = not_printed_sensor_list_local + unscanned_sensors
        
        # Fetch lot condition
        lot_condition = get_lot_condition(lot_number)

        # If Eval, don't populate combobox with not printed sensors
        if str(lot_condition).upper() == "EVAL":
            combobox_candidates_local = []

        # Open the BMS Popup with total lot count and unscanned sensors
        popup = BMSPopup(root, lot_number, current_process, operator,
                         sensor_list_local, combobox_candidates_local,
                         not_printed_sensor_list_local, unscanned_sensors, 
                         print_status_data, lot_condition, 
                         total_lot_count, unscanned_sensors, printed_sensor_list_local)
        popup.grab_set()
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")
            
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"Could not fetch lot sensors: {e}")
        return

        # Fetch lot condition
        lot_condition = get_lot_condition(lot_number)

        # If Eval, don't populate combobox with not printed sensors
        if str(lot_condition).upper() == "EVAL":
            combobox_candidates_local = []

        # Open the BMS Popup with total lot count and unscanned sensors
        popup = BMSPopup(root, lot_number, current_process, operator,
                         sensor_list_local, combobox_candidates_local,
                         not_printed_sensor_list_local, unscanned_sensors, 
                         print_status_data, lot_condition, 
                         total_lot_count, unscanned_sensors, printed_sensor_list_local)
        popup.grab_set()
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

# Entries
labels = ["Lot Number:", "Current Process:", "Date and Time:", "Operator:"]
entries = {}
label_positions = {"Lot Number:": (10, 40), "Current Process:": (10, 65), "Date and Time:": (10, 90), "Operator:": (10, 115)}
entry_positions = {"Lot Number:": (115, 40), "Current Process:": (115, 65), "Date and Time:": (115, 90), "Operator:": (115, 115)}

for lt in labels:
    tk.Label(root, text=lt, font=("Arial", 10), bg="lightblue").place(x=label_positions[lt][0], y=label_positions[lt][1])
    e = tk.Entry(root, width=30, justify='center')
    e.place(x=entry_positions[lt][0], y=entry_positions[lt][1])
    entries[lt] = e

entries["Date and Time:"].config(state="readonly")
entries["Current Process:"].config(state="readonly")
update_datetime()
entries["Lot Number:"].bind("<Return>", fetch_lot_info)

# Buttons
delete_button = tk.Button(root, text="Clear Data", font=("Tahoma", 12, "bold"), padx=10, pady=1, bg="yellow", command=delete_action, relief='raised', borderwidth=3)
delete_button.place(x=465, y=95)

save_button = tk.Button(root, text="SAVE", font=("Tahoma", 12, "bold"), padx=32, pady=1, bg="orange", command=save_action, relief='raised', borderwidth=3)
save_button.place(x=325, y=95)

# Printer status label (auto-detect) - positioned below Operator field
printer_status_label = tk.Label(root, text="Detecting printer...", font=("Arial", 9, "bold"), bg="lightblue", fg="blue")
printer_status_label.place(x=100, y=140)

# Auto-detected printer variable
detected_printer = {"name": None, "method": None, "online": False}

# Canvas to show both labels (moved to right side)
tk.Label(root, text="Label Preview:", font=("Arial", 10, "bold"), bg="lightblue").place(x=350, y=500)
canvas_width = PREVIEW_W * 2 + 20
canvas_height = PREVIEW_H + 10
canvas = tk.Canvas(root, width=canvas_width, height=canvas_height, bg="grey", relief="sunken", borderwidth=2)
canvas.place(x=350, y=520)

# Create blank preview
blank_preview = Image.new("RGB", (canvas_width - 10, canvas_height - 10), "white")
blank_photo = ImageTk.PhotoImage(blank_preview, master=root)
_global_images["blank"] = blank_photo

canvas_bg = canvas.create_image(5, 5, anchor="nw", image=blank_photo)

# Store generated labels
canvas.label1_full = None
canvas.label2_full = None

# Preview update
def update_preview(sensor_id):
    if not sensor_id:
        return
    
    print(f"Updating preview with sensor ID: {sensor_id}")
    
    # Generate both labels
    label1 = make_label1_image()
    label2 = make_label2_image(sensor_id)
    
    print(f"Label 1 size: {label1.size}")
    print(f"Label 2 size: {label2.size}")
    
    canvas.label1_full = label1
    canvas.label2_full = label2
    
    # Create combined preview
    combined_preview = make_combined_preview(label1, label2)
    
    print(f"Combined preview size: {combined_preview.size}")
    
    ph = ImageTk.PhotoImage(combined_preview, master=root)
    _global_images["preview"] = ph
    canvas.itemconfig(canvas_bg, image=ph)
    
    print("Preview updated successfully!")

# Auto print function
def auto_print_label(sensor_id, row_index):
    # Generate labels
    label1 = make_label1_image()
    label2 = make_label2_image(sensor_id)
    
    # Update preview
    canvas.label1_full = label1
    canvas.label2_full = label2
    combined_preview = make_combined_preview(label1, label2)
    ph = ImageTk.PhotoImage(combined_preview, master=root)
    _global_images["preview"] = ph
    canvas.itemconfig(canvas_bg, image=ph)
    
    # Check if printer is detected
    if not detected_printer["name"]:
        status_labels[row_index].config(text="No Printer", bg="red", fg="white")
        status_label.config(text="✗ No printer detected", fg="red")
        return False
    
    # Check if printer is online
    if not detected_printer.get("online", True):
        status_labels[row_index].config(text="Printer Offline", bg="orange", fg="white")
        status_label.config(text="⚠ Printer is offline", fg="orange")
        messagebox.showwarning("Printer Offline", 
                             f"The printer '{detected_printer['name']}' is offline.\n\n"
                             "Please check:\n"
                             "- Printer is powered on\n"
                             "- Printer is connected to computer\n"
                             "- Printer is not in error state")
        return False
    
    method = detected_printer["method"]
    printer_name = detected_printer["name"]
    
    try:
        if method == "windows":
            status_label.config(text=f"Printing label 1 for {sensor_id}...", fg="blue")
            root.update()
            
            # Print first label
            send_to_printer_windows(label1, printer_name)
            
            # Wait longer for printer to finish and position next label (increased from 500ms to 2000ms)
            time.sleep(2.0)
            root.update()
            
            status_label.config(text=f"Printing label 2 for {sensor_id}...", fg="blue")
            root.update()
            
            # Print second label
            send_to_printer_windows(label2, printer_name)
            
            # Wait for second label to finish
            time.sleep(1.5)
            
            status_label.config(text=f"✓ Printed: {sensor_id}", fg="green")
            status_labels[row_index].config(text="Printed", bg="green", fg="white")
            return True
            
        elif method == "usb":
            usb_devices = find_godex_printer()
            if not usb_devices:
                raise Exception("USB device not found")
            
            device = usb_devices[0]['device']
            
            status_label.config(text=f"Printing label 1 for {sensor_id}...", fg="blue")
            root.update()
            
            # Print first label
            ezpl1 = generate_ezpl_label(label1, 1)
            send_to_printer_usb(ezpl1, device)
            
            # Wait longer for printer to finish and position next label (increased from 500ms to 2000ms)
            time.sleep(2.0)
            root.update()
            
            status_label.config(text=f"Printing label 2 for {sensor_id}...", fg="blue")
            root.update()
            
            # Print second label
            ezpl2 = generate_ezpl_label(label2, 2)
            send_to_printer_usb(ezpl2, device)
            
            # Wait for second label to finish
            time.sleep(1.5)
            
            status_label.config(text=f"✓ Printed: {sensor_id}", fg="green")
            status_labels[row_index].config(text="Printed", bg="green", fg="white")
            return True
            
        else:
            status_labels[row_index].config(text="Config Error", bg="red", fg="white")
            return False
        
    except Exception as e:
        status_label.config(text=f"✗ Print failed: {sensor_id}", fg="red")
        status_labels[row_index].config(text="Not Printed", bg="red", fg="white")
        print(f"Print error: {e}")
        
        # Check if it's an offline error
        if "offline" in str(e).lower() or "not available" in str(e).lower():
            messagebox.showerror("Printer Offline", 
                               f"Printer appears to be offline.\n\n"
                               f"Error: {e}\n\n"
                               "Please check printer connection and try 2again.")
        return False

def auto_detect_printer():
    """Auto-detect available Godex printer and check if it's online"""
    printers = []
    
    # Try USB detection
    usb_devices = find_godex_printer()
    for dev in usb_devices:
        printers.append({
            'name': f"{dev['name']} (VID:{dev['vid']} PID:{dev['pid']})",
            'method': 'usb',
            'online': True  # USB devices are online if detected
        })
    
    # Try Windows printers - use actual print test
    try:
        import win32print
        import pywintypes
        
        win_printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        for printer in win_printers:
            printer_name = printer[2]
            if "godex" in printer_name.lower() or "rt863" in printer_name.lower():
                print(f"\n=== Testing Printer: {printer_name} ===")
                
                # Test if printer is actually accessible by trying to print
                is_offline = True
                
                try:
                    handle = win32print.OpenPrinter(printer_name)
                    
                    try:
                        # Try to start a document - this will FAIL if printer is offline
                        print("Attempting to start print job...")
                        job_info = ("StatusTest", None, "RAW")
                        
                        try:
                            job_id = win32print.StartDocPrinter(handle, 1, job_info)
                            print(f"  ✓ StartDocPrinter succeeded (job_id: {job_id})")
                            
                            # If we got here, printer accepted the job = ONLINE
                            is_offline = False
                            
                            # Clean up - end and delete the test job
                            try:
                                win32print.EndDocPrinter(handle)
                                win32print.SetJob(handle, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
                                print("  ✓ Test job cleaned up")
                            except:
                                pass
                                
                        except pywintypes.error as e:
                            # StartDocPrinter failed = printer is OFFLINE
                            error_code = e.args[0] if e.args else 0
                            error_msg = e.args[2] if len(e.args) > 2 else str(e)
                            print(f"  ✗ StartDocPrinter FAILED: Error {error_code} - {error_msg}")
                            is_offline = True
                            
                    finally:
                        win32print.ClosePrinter(handle)
                    
                    print(f"Result: {'OFFLINE' if is_offline else 'ONLINE'}")
                    print("=" * 40 + "\n")
                    
                    printers.append({
                        'name': printer_name,
                        'method': 'windows',
                        'online': not is_offline
                    })
                    
                except pywintypes.error as e:
                    print(f"  ✗ Cannot open printer: {e}")
                    printers.append({
                        'name': printer_name,
                        'method': 'windows',
                        'online': False
                    })
                except Exception as e:
                    print(f"  ✗ Error: {e}")
                    printers.append({
                        'name': printer_name,
                        'method': 'windows',
                        'online': False
                    })
                    
    except Exception as e:
        print(f"Error enumerating printers: {e}")
    
    if printers:
        # Use the first detected printer
        printer = printers[0]
        detected_printer["name"] = printer["name"]
        detected_printer["method"] = printer["method"]
        detected_printer["online"] = printer["online"]
        
        if printer["online"]:
            printer_status_label.config(
                text=f"✓ Printer: {printer['name'][:35]}...", 
                fg="green"
            )
            status_label.config(text="Printer ready", fg="green")
        else:
            printer_status_label.config(
                text=f"⚠ OFFLINE: {printer['name'][:35]}...", 
                fg="orange"
            )
            status_label.config(text="⚠ Printer is OFFLINE!", fg="orange")
    else:
        detected_printer["name"] = None
        detected_printer["method"] = None
        detected_printer["online"] = False
        printer_status_label.config(text="✗ No Godex printer found", fg="red")
        status_label.config(text="✗ No printer found!", fg="red")

# Camera feed label
video_label = tk.Label(root, bg="black")
video_label.place(x=350, y=180, width=400, height=300)

# Scale for adjusting the threshold level
threshold_label = tk.Label(root, text="Threshold", font=("Arial", 10, "bold"), bg="lightblue", fg="black")
threshold_label.place(x=820, y=200)

threshold_scale = tk.Scale(root, from_=110, to=200, orient=tk.HORIZONTAL, length=150, bg="#407ec9", fg="white", font=("Arial", 8), resolution=5)
threshold_scale.set(120)
threshold_scale.place(x=780, y=220)

toggle_button = tk.Button(root, text="Toggle View", command=lambda: toggle_view(), font=("Arial", 10, "bold"), bg="#407ec9", fg="white", padx=10, pady=1, relief='raised', borderwidth=3)
toggle_button.place(x=800, y=280)

# READ button for manual OCR scanning
read_button = tk.Button(root, text="READ", command=lambda: capture_and_process_ocr(), font=("Arial", 12, "bold"), bg="#00cc44", fg="white", padx=20, pady=1, relief='raised', borderwidth=3)
read_button.place(x=805, y=350)

# Table for scanned sensors
# Table headers
headers = ["No.", "Sensor ID", "Status"]
header_positions = {
    "No.": (13, 165),
    "Sensor ID": (80, 165),
    "Status": (235, 165),
}
for header in headers:
    label = tk.Label(root, text=header, font=("Arial", 7, "bold"), bg="lightblue", relief="ridge")
    label.place(x=header_positions[header][0], y=header_positions[header][1])

# Create table rows (20 rows)
sensor_id_labels = []
status_labels = []

def on_sensor_entry_return(event, row_idx):
    """Handle Enter key press on sensor ID entry"""
    sensor_id = sensor_id_labels[row_idx].get().strip()
    if sensor_id:
        # Validate and print
        validate_and_print_manual_entry(sensor_id, row_idx)

def validate_and_print_manual_entry(sensor_id, row_idx):
    """Validate manually entered sensor ID and print if valid"""
    lot_number_raw = entries["Lot Number:"].get()
    lot_number = re.sub(r'\s+', '', lot_number_raw)
    
    if not lot_number:
        status_label.config(text="⚠ Enter Lot Number first", fg="orange")
        messagebox.showwarning("Input Error", "Please enter a Lot Number first.")
        return
    
    # Get current process
    current_process = entries["Current Process:"].get().strip()
    
    # Get valid sensor IDs
    valid_sensor_ids = get_allowed_sensor_ids(lot_number, current_process)
    
    # Get already scanned sensors
    already_scanned = []
    for i in range(20):
        if i != row_idx:  # Don't include current row
            text = sensor_id_labels[i].get().strip() if isinstance(sensor_id_labels[i], tk.Entry) else sensor_id_labels[i].cget("text").strip()
            if text:
                already_scanned.append(text)
    
    remaining_sensor_ids = [sid for sid in valid_sensor_ids if sid not in already_scanned]
    
    # Validate sensor ID
    if sensor_id in already_scanned:
        status_label.config(text="✗ Already scanned", fg="red")
        show_modal_warning("Already Scanned", 
                         f"Sensor ID: {sensor_id}\n\n"
                         f"This sensor has already been scanned in this session.")
        return
    
    if sensor_id not in remaining_sensor_ids:
        status_label.config(text="✗ Invalid sensor ID", fg="red")
        
        # Check if it belongs to this lot but has defects
        try:
            conn = sqlite3.connect(db_path_tracking)
            cursor = conn.cursor()
            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
            all_lot_sensors = [r[0] for r in cursor.fetchall()]
            conn.close()
            
            if sensor_id in all_lot_sensors:
                show_modal_error("DEFECTIVE SENSOR - CANNOT PROCEED", 
                               f"Sensor ID: {sensor_id}\n\n"
                               f"This sensor has defects from previous processes\n"
                               f"and cannot proceed to this process.\n\n"
                               f"Action: Set aside and enter next sensor.")
            else:
                show_modal_error("Invalid Sensor ID", 
                               f"Sensor ID: {sensor_id}\n\n"
                               f"This sensor does NOT belong to lot '{lot_number}'.\n\n"
                               f"Please verify the sensor ID.")
        except sqlite3.Error:
            show_modal_error("Invalid Sensor ID", 
                           f"Sensor ID: {sensor_id}\n\n"
                           f"This sensor is not valid for this lot.")
        return
    
    # Valid sensor - update status and print
    status_labels[row_idx].config(text="Printing...", bg="yellow", fg="black")
    status_label.config(text=f"Processing: {sensor_id}", fg="blue")
    
    # Update preview
    update_preview(sensor_id)
    
    # Auto print
    root.after(100, lambda: auto_print_label(sensor_id, row_idx))

for row in range(20):
    # Row number
    number_label = tk.Label(root, text=str(row + 1), width=3, bg="lightblue", relief="ridge")
    number_label.place(x=10, y=185 + row*23)
    
    # Sensor ID entry (changed from Label to Entry)
    sensor_entry = tk.Entry(root, font=("Arial", 8), bg="white", width=22, relief="ridge")
    sensor_entry.place(x=45, y=185 + row*23)
    sensor_entry.bind("<Return>", lambda e, r=row: on_sensor_entry_return(e, r))
    sensor_id_labels.append(sensor_entry)
    
    # Status label
    status_label_item = tk.Label(root, text="", font=("Arial", 8, "bold"), bg="white", width=15, relief="ridge")
    status_label_item.place(x=200, y=185 + row*23)
    status_labels.append(status_label_item)

# OCR Camera functionality
import cv2
import pytesseract
import threading
import numpy as np
from PIL import ImageFilter, ImageOps
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

# Global variables for camera
camera_index = 0
cap = None
threshold_view = False
last_successful_threshold = None  # Store the successful threshold value

# OCR confusion mapping for character corrections
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

def _apply_confusions(s):
    if not s:
        return s
    try:
        return ''.join(OCR_CONFUSIONS.get(ch, ch) for ch in s)
    except Exception:
        return s

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

def toggle_view():
    global threshold_view
    threshold_view = not threshold_view

def start_camera():
    global cap
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        messagebox.showerror("Error", "Could not open camera.")
    else:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        show_frame()

def show_frame():
    global threshold_view
    ret, frame = cap.read()
    if frame is not None:
        orig_height, orig_width = frame.shape[:2]
        display_width = 400
        display_height = int(display_width * orig_height / orig_width)
        frame_display = cv2.resize(frame.copy(), (display_width, display_height))

        if threshold_view:
            gray_frame = cv2.cvtColor(frame_display, cv2.COLOR_BGR2GRAY)
            threshold_value = threshold_scale.get()
            _, thresholded_frame = cv2.threshold(gray_frame, threshold_value, 255, cv2.THRESH_BINARY)
            frame_to_display = cv2.cvtColor(thresholded_frame, cv2.COLOR_GRAY2BGR)
        else:
            frame_to_display = frame_display

        # Convert to ImageTk format
        img = Image.fromarray(cv2.cvtColor(frame_to_display, cv2.COLOR_BGR2RGB))
        imgtk = ImageTk.PhotoImage(image=img)
        video_label.imgtk = imgtk
        video_label.configure(image=imgtk)
        
    video_label.after(10, show_frame)

def capture_and_process_ocr():
    if not cap or not cap.isOpened():
        messagebox.showerror("Error", "Camera is not open.")
        return

    ret, frame = cap.read()
    if ret:
        cv2.imwrite(before_image_path, frame)
        print(f"Image captured and saved as {before_image_path}")
        
        # Process OCR in a separate thread
        threading.Thread(target=process_image_for_ocr).start()
    else:
        messagebox.showerror("Error", "Failed to capture image.")

def process_image_for_ocr():
    """
    OPTIMIZED: Process full image with regex pattern detection.
    No manual cropping needed - automatically finds sensor ID anywhere in the image.
    """
    global threshold_view, last_successful_threshold
    try:
        # Remove all whitespace and non-printable characters (same as fetch_lot_info)
        lot_number_raw = entries["Lot Number:"].get()
        lot_number = re.sub(r'\s+', '', lot_number_raw)  # Removes spaces, tabs, newlines
        
        if not lot_number:
            status_label.config(text="⚠ Enter Lot Number first", fg="orange")
            messagebox.showwarning("Input Error", "Please enter a Lot Number first.")
            return

        # Fetch valid sensor IDs (only those without defects in previous processes)
        try:
            conn = sqlite3.connect(db_path_tracking)
            cursor = conn.cursor()
            
            # Get current process
            current_process = entries["Current Process:"].get().strip()
            
            # Use get_allowed_sensor_ids to get only sensors without defects
            valid_sensor_ids = get_allowed_sensor_ids(lot_number, current_process)
            conn.close()
            
            if not valid_sensor_ids:
                status_label.config(text="⚠ No sensors allowed for lot", fg="orange")
                messagebox.showwarning("Database Error", f"No sensor IDs without defects found for lot number {lot_number}")
                return
            
            # Check for already scanned sensors
            already_scanned = [sensor_id_labels[i].get().strip() for i in range(20) if sensor_id_labels[i].get().strip()]
            remaining_sensor_ids = [sid for sid in valid_sensor_ids if sid not in already_scanned]
            
            if not remaining_sensor_ids:
                status_label.config(text="✓ All sensors scanned", fg="green")
                messagebox.showinfo("Complete", "All sensors allowed for this process have been scanned.")
                return
            
            print(f"✓ Valid sensor IDs (no defects) for lot {lot_number}: {len(valid_sensor_ids)} sensors")
            print(f"  Already scanned: {len(already_scanned)}")
            print(f"  Remaining to scan: {len(remaining_sensor_ids)}")
                
        except sqlite3.Error as e:
            status_label.config(text=f"✗ Database error", fg="red")
            messagebox.showerror("Database Error", f"Could not fetch sensor IDs: {e}")
            return
        
        # Load the captured image
        img = cv2.imread(before_image_path)
        if img is None:
            raise Exception("Could not load captured image")
        
        print(f"Original image shape: {img.shape}")
        
        # Convert to PIL for processing
        image = Image.open(before_image_path)
        
        # Optional: Resize large images for faster processing
        max_width = 1500
        if image.width > max_width:
            scale = max_width / image.width
            new_size = (int(image.width * scale), int(image.height * scale))
            image = image.resize(new_size, RESAMPLE)
        
        # Save for debugging
        image.save(save_path)
        print(f"Processed image saved: {save_path}")
        
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
            # OPTIMIZED: Try only 5 thresholds (faster)
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
            img_binary.save(enhanced_image_path)
            
            # Perform OCR on full image
            raw_ocr_text = pytesseract.image_to_string(img_binary, config=custom_oem_psm_config)

            # Apply simple OCR confusion mapping and normalize
            ocr_text = _apply_confusions(raw_ocr_text)
            ocr_text = ocr_text.upper()

            print(f"[OCR] Raw text (thr={threshold_value}): {raw_ocr_text[:100]}")
            print(f"[OCR] Corrected text: {ocr_text[:100]}")
            
            # Pattern for sensor ID: XX-XX-XXXXX-XXXXXX
            pattern = r'\b(\d{2})-(\d{2})-([A-Z0-9]{4,5}[A-Z]?)-(\d{6})\b'
            matches = re.findall(pattern, ocr_text)
            
            if matches:
                sensor_id = f"{matches[0][0]}-{matches[0][1]}-{matches[0][2]}-{matches[0][3]}"
                cand = sensor_id.strip().upper()
                
                # Exact match - validate against remaining sensors
                if cand in remaining_sensor_ids:
                    print(f"[OCR] ✓ Pattern detected: {cand} - CORRECT (valid for this lot)")
                    print(f"✓ Success! Sensor ID '{cand}' detected at threshold {threshold_value}")
                    threshold_scale.set(threshold_value)
                    last_successful_threshold = threshold_value
                    ocr_result = cand
                    break
                
                # Try confusion mapping
                mapped = _apply_confusions(cand)
                if mapped != cand and mapped in remaining_sensor_ids:
                    print(f"[OCR] Mapped '{cand}' -> '{mapped}' and matched remaining IDs")
                    threshold_scale.set(threshold_value)
                    last_successful_threshold = threshold_value
                    ocr_result = mapped
                    break
                
                # Store for error reporting
                if cand in already_scanned:
                    print(f"[OCR] ✓ Pattern detected: {cand} - INCORRECT (already scanned)")
                    last_detected_pattern = cand
                elif cand in all_sensors_needing_defects:
                    print(f"[OCR] ✓ Pattern detected: {cand} - INCORRECT (not in remaining list)")
                    last_detected_pattern = cand
                else:
                    print(f"[OCR] ✓ Pattern detected: {cand} - INCORRECT (not in lot {lot_number})")
                    last_detected_pattern = cand
                
                # Fuzzy matching: compare cand and its mapped variant against remaining IDs
                best_match = None
                best_dist = None
                for variant in (cand, mapped):
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
            
            # Try lenient pattern
            lenient_pattern = r'(\d{2})[\s\-]?(\d{2})[\s\-]?([A-Z0-9]{4,6})[\s\-]?(\d{6})'
            lenient_matches = re.findall(lenient_pattern, ocr_text)
            
            if lenient_matches and not ocr_result:
                sensor_id = f"{lenient_matches[0][0]}-{lenient_matches[0][1]}-{lenient_matches[0][2]}-{lenient_matches[0][3]}"
                cand = sensor_id.strip().upper()
                
                # Exact match
                if cand in remaining_sensor_ids:
                    print(f"[OCR] ✓ Pattern detected (lenient): {cand} - CORRECT")
                    last_successful_threshold = threshold_value
                    ocr_result = cand
                    break
                
                # Try confusion mapping
                mapped = _apply_confusions(cand)
                if mapped != cand and mapped in remaining_sensor_ids:
                    print(f"[OCR] Mapped (lenient) '{cand}' -> '{mapped}' and matched")
                    last_successful_threshold = threshold_value
                    ocr_result = mapped
                    break
                
                # Store for error reporting
                if not last_detected_pattern:
                    last_detected_pattern = cand
                
                # Fuzzy matching for lenient pattern
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
                    print(f"[OCR] ~ Fuzzy matched (lenient) '{best_match[2]}' -> '{matched_id}' (dist={best_match[1]})")
                    ocr_result = matched_id
                    threshold_scale.set(threshold_value)
                    last_successful_threshold = threshold_value
                    break
        
        # Restore original view mode
        threshold_view = original_view
        
        # Check if OCR result is valid
        if ocr_result not in remaining_sensor_ids:
            status_label.config(text="✗ Sensor rejected", fg="red")
            
            # Determine the specific error and show appropriate message
            if not ocr_result or ocr_result == "":
                # No direct valid result. If we detected a pattern earlier, surface it to the user.
                if last_detected_pattern:
                    # Treat last_detected_pattern as the detected text and run the same validation path below
                    ocr_result = last_detected_pattern
                    print(f"✗ No valid remaining sensor, but OCR detected pattern: {ocr_result}")
                else:
                    # No detection at all
                    print("✗ No sensor ID pattern detected")
                    show_modal_error("No OCR Output Detected", 
                                   "❌ OCR could not detect any sensor ID.\n\n"
                                   "Possible issues:\n"
                                   "• Camera focus is blurry\n"
                                   "• Poor lighting conditions\n"
                                   "• Sensor ID not visible in frame\n"
                                   "• Text is too small or unclear\n\n"
                                   "Please adjust camera and try again.")
                    return
            
            # Now check what type of error it is
            if ocr_result in already_scanned:
                # Already scanned in this session
                print(f"✗ Sensor ID '{ocr_result}' already scanned in this session")
                show_modal_warning("Already Scanned", 
                                     f"❌ INCORRECT SENSOR ID ❌\n\n"
                                     f"OCR Detected Pattern:\n'{ocr_result}'\n\n"
                                     f"Expected Lot: '{lot_number}'\n\n"
                                     f"ERROR: This sensor has already been\nscanned in this session.\n\n"
                                     f"ACTION: Scan the next sensor.")
            else:
                # Check if it's a defective sensor from this lot or wrong lot
                try:
                    conn_check = sqlite3.connect(db_path_tracking)
                    cur_check = conn_check.cursor()
                    cur_check.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
                    all_lot_sensors = [r[0] for r in cur_check.fetchall()]
                    
                    if ocr_result in all_lot_sensors:
                        # Sensor belongs to this lot but has defects
                        show_modal_error("DEFECTIVE SENSOR - CANNOT PROCEED", 
                                           f"❌ INCORRECT SENSOR ID ❌\n\n"
                                           f"OCR Detected Pattern:\n'{ocr_result}'\n\n"
                                           f"Expected Lot: '{lot_number}'\n\n"
                                           f"⚠ THIS SENSOR IS DEFECTIVE ⚠\n\n"
                                           f"ERROR: This sensor has defects from\nprevious processes and cannot proceed.\n\n"
                                           f"ACTION REQUIRED:\n"
                                           f"• Set this sensor aside\n"
                                           f"• DO NOT label this sensor\n"
                                           f"• Scan the next sensor")
                    else:
                        # Doesn't belong to this lot
                        show_modal_error("Wrong Sensor ID - OCR Output Incorrect", 
                                           f"❌ INCORRECT SENSOR ID ❌\n\n"
                                           f"OCR Detected Pattern:\n'{ocr_result}'\n\n"
                                           f"Expected Lot: '{lot_number}'\n\n"
                                           f"ERROR: This sensor does NOT belong\nto lot '{lot_number}'.\n\n"
                                           f"ACTION: Verify the sensor or set it aside.")
                    conn_check.close()
                except sqlite3.Error:
                    show_modal_error("Wrong Sensor ID", 
                                       f"❌ INCORRECT SENSOR ID ❌\n\n"
                                       f"OCR Detected Pattern:\n'{ocr_result}'\n\n"
                                       f"Expected Lot: '{lot_number}'\n\n"
                                       f"ERROR: This sensor is not valid for this lot.")
            
            return

        print(f"Final OCR result: '{ocr_result}'")

        # Find first empty row
        row_index = -1
        for i in range(20):
            if not sensor_id_labels[i].get().strip():
                row_index = i
                break
        
        if row_index == -1:
            status_label.config(text="✗ Table full", fg="red")
            messagebox.showwarning("Table Full", "All 20 rows are filled. Cannot add more sensors.")
            return

        # Update table
        sensor_id_labels[row_index].delete(0, tk.END)
        sensor_id_labels[row_index].insert(0, ocr_result)
        status_labels[row_index].config(text="Printing...", bg="yellow", fg="black")
        
        # Update preview
        update_preview(ocr_result)
        
        # Auto print
        root.after(100, lambda: auto_print_label(ocr_result, row_index))
        
    except Exception as e:
        status_label.config(text=f"✗ OCR error", fg="red")
        messagebox.showerror("OCR Error", f"An error occurred during OCR processing:\n{e}")
        print(f"Error during OCR processing: {e}")
        import traceback
        traceback.print_exc()
    try:
        # Remove all whitespace and non-printable characters (same as fetch_lot_info)
        lot_number_raw = entries["Lot Number:"].get()
        lot_number = re.sub(r'\s+', '', lot_number_raw)  # Removes spaces, tabs, newlines
        
        if not lot_number:
            status_label.config(text="⚠ Enter Lot Number first", fg="orange")
            messagebox.showwarning("Input Error", "Please enter a Lot Number first.")
            return

        # Fetch valid sensor IDs (only those without defects in previous processes)
        try:
            conn = sqlite3.connect(db_path_tracking)
            cursor = conn.cursor()
            
            # Get current process
            current_process = entries["Current Process:"].get().strip()
            
            # Use get_allowed_sensor_ids to get only sensors without defects
            valid_sensor_ids = get_allowed_sensor_ids(lot_number, current_process)
            conn.close()
            
            if not valid_sensor_ids:
                status_label.config(text="⚠ No sensors allowed for lot", fg="orange")
                messagebox.showwarning("Database Error", f"No sensor IDs without defects found for lot number {lot_number}")
                return
            
            # Check for already scanned sensors
            already_scanned = [sensor_id_labels[i].get().strip() for i in range(20) if sensor_id_labels[i].get().strip()]
            remaining_sensor_ids = [sid for sid in valid_sensor_ids if sid not in already_scanned]
            
            if not remaining_sensor_ids:
                status_label.config(text="✓ All sensors scanned", fg="green")
                messagebox.showinfo("Complete", "All sensors allowed for this process have been scanned.")
                return
            
            # Debug: Print sensor IDs for troubleshooting
            print(f"✓ Valid sensor IDs (no defects) for lot {lot_number}: {len(valid_sensor_ids)} sensors")
            print(f"  Sample IDs: {valid_sensor_ids[:3] if len(valid_sensor_ids) >= 3 else valid_sensor_ids}")
            print(f"  Already scanned: {len(already_scanned)}")
            print(f"  Remaining to scan: {len(remaining_sensor_ids)}")
                
        except sqlite3.Error as e:
            status_label.config(text=f"✗ Database error", fg="red")
            messagebox.showerror("Database Error", f"Could not fetch sensor IDs: {e}")
            return
        
        # Load and process image
        img = cv2.imread(before_image_path)
        if img is None:
            raise Exception("Could not load captured image")
        
        print(f"Original image shape: {img.shape}")
        
        # Get original frame dimensions
        height, width = img.shape[:2]
        
        # Calculate display dimensions with proper aspect ratio
        display_width = 400
        display_height = int(display_width * height / width)
        
        # Scale coordinates from display size to actual camera resolution
        scale_x = width / display_width
        scale_y = height / display_height
        
        # Use ocr_frame coordinates directly (they're already in display space)
        # and scale them to the actual camera resolution
        x1 = int(ocr_frame["x1"] * scale_x)
        y1 = int(ocr_frame["y1"] * scale_y)
        x2 = int(ocr_frame["x2"] * scale_x)
        y2 = int(ocr_frame["y2"] * scale_y)
        
        print(f"OCR frame (display space): x1={ocr_frame['x1']}, y1={ocr_frame['y1']}, x2={ocr_frame['x2']}, y2={ocr_frame['y2']}")
        print(f"Scaled crop coordinates (camera space): x1={x1}, y1={y1}, x2={x2}, y2={y2}")
        
        image = Image.open(before_image_path)
        cropped_image = image.crop((x1, y1, x2, y2))
        # Crop using PIL
        image = Image.open(before_image_path)
        cropped_image = image.crop((x1, y1, x2, y2))
        cropped_image.save(save_path)
        print(f"Cropped image saved: {save_path}")
        
        # Switch to threshold view for visual feedback
        original_view = threshold_view
        threshold_view = True
        
        # Try OCR with automatic threshold adjustment
        ocr_result = ""
        
        # Get CURRENT threshold value from slider (whatever user set manually)
        current_threshold = threshold_scale.get()
        print(f"Starting OCR with current threshold: {current_threshold}")
        
        # Build threshold sequence: current first, then increase by 1, then decrease by 1
        threshold_attempts = [current_threshold]
        
        # Add increasing values from current+1 up to 200 (step by 1 for accuracy)
        for t in range(current_threshold + 1, 201, 1):
            threshold_attempts.append(t)
        
        # Add decreasing values from current-1 down to 110 (step by 1 for accuracy)
        for t in range(current_threshold - 1, 109, -1):
            threshold_attempts.append(t)
        
        print(f"Will try up to {len(threshold_attempts)} threshold values if needed")
        
        # Try each threshold value
        ocr_result = ""
        last_detected_pattern = None
        for attempt_num, threshold_value in enumerate(threshold_attempts, 1):
            if attempt_num == 1:
                print(f"[Attempt {attempt_num}] Trying CURRENT threshold: {threshold_value}")
            else:
                print(f"[Attempt {attempt_num}] Auto-adjusting to threshold: {threshold_value}")
            
            # Update threshold slider visually (every 3rd attempt to reduce GUI overhead)
            if attempt_num % 3 == 1:
                threshold_scale.set(threshold_value)
                root.update_idletasks()  # Force GUI update
            
            # Process image with current threshold
            image = Image.open(save_path)
            image = ImageOps.grayscale(image)
            image = image.filter(ImageFilter.SHARPEN)
            image = image.point(lambda p: p > threshold_value and 255)
            image.save(enhanced_image_path)
            
            # Use Tesseract to perform OCR
            img_ocr = cv2.imread(enhanced_image_path)
            raw_ocr_result = pytesseract.image_to_string(img_ocr, config=custom_oem_psm_config)

            # Apply simple OCR confusion mapping and normalize
            ocr_result = _apply_confusions(raw_ocr_result)
            ocr_result = ocr_result.upper().strip()
            
            # Normalize OCR text by applying regex patterns to extract sensor ID if present
            # Strict pattern: XX-XX-XXXXX-XXXXXX (with optional extra letter in the 3rd group)
            pattern = r'\b(\d{2})-(\d{2})-([A-Z0-9]{4,5}[A-Z]?)-(\d{6})\b'
            # Lenient pattern: allow missing or spaced hyphens
            lenient_pattern = r'(\d{2})[\s\-]?(\d{2})[\s\-]?([A-Z0-9]{4,6})[\s\-]?(\d{6})'

            found = False
            m = re.search(pattern, ocr_result)
            if m:
                ocr_result = f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}"
                found = True
            else:
                m2 = re.search(lenient_pattern, ocr_result)
                if m2:
                    ocr_result = f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}-{m2.group(4)}"
                    found = True

            if not found:
                # Try a cleaned version (remove non-alnum/hyphen and apply confusions)
                cleaned = re.sub(r'[^A-Z0-9\-]', '', _apply_confusions(raw_ocr_result).upper())
                m3 = re.search(lenient_pattern, cleaned)
                if m3:
                    ocr_result = f"{m3.group(1)}-{m3.group(2)}-{m3.group(3)}-{m3.group(4)}"

            # Now proceed with validation
            if ocr_result in remaining_sensor_ids:
                if attempt_num == 1:
                    print(f"✓ Success! Sensor ID '{ocr_result}' detected at your manual threshold {threshold_value}")
                else:
                    print(f"✓ Success! Sensor ID '{ocr_result}' detected after auto-adjusting to threshold {threshold_value}")
                # Update slider to final successful value
                threshold_scale.set(threshold_value)
                break
            elif ocr_result:
                # OCR detected something - just log it and continue trying
                sensor_id_pattern = r'^\d+-\d+-[A-Z0-9]+-\d+$'
                if re.match(sensor_id_pattern, ocr_result):
                    # Valid sensor ID format detected
                    if ocr_result in already_scanned:
                        print(f"  Rejected '{ocr_result}' - already scanned (continuing...)")
                        last_detected_pattern = ocr_result
                    elif ocr_result in valid_sensor_ids:
                        print(f"  Rejected '{ocr_result}' - already scanned in valid list (continuing...)")
                        last_detected_pattern = ocr_result
                    else:
                        # Valid format but doesn't belong to this lot - keep trying
                        print(f"  Rejected '{ocr_result}' - not in lot {lot_number} (continuing...)")
                        last_detected_pattern = ocr_result
                else:
                    # Invalid format - keep trying
                    print(f"  Rejected '{ocr_result}' - invalid format (continuing...)")
                    # don't set last_detected_pattern for invalid format
        
        # Restore original view mode
        threshold_view = original_view
        
        print(f"Final OCR result: '{ocr_result}'")
        
        # Check if OCR result is valid
        if ocr_result not in remaining_sensor_ids:
            # Determine the specific error and show an on-screen modal warning/error
            if not ocr_result or ocr_result == "":
                # No direct valid result. If we detected a pattern earlier, surface it to the user.
                if last_detected_pattern:
                    ocr_result = last_detected_pattern
                    print(f"✗ No valid remaining sensor, but OCR detected pattern: {ocr_result}")
                else:
                    # No detection at all
                    print("✗ No text detected by OCR after all threshold attempts")
                    show_modal_error("OCR Failed", 
                                     "No sensor ID detected.\n\n"
                                     "Please check:\n"
                                     "- Sensor ID is clearly visible\n"
                                     "- Camera focus is correct\n"
                                     "- Lighting is adequate")
                    return
            if ocr_result in already_scanned:
                print(f"✗ Sensor ID '{ocr_result}' already scanned in this session")
                show_modal_warning("Already Scanned", 
                                   f"Sensor ID: {ocr_result}\n\n"
                                   f"This sensor has already been scanned in this session.")
                return
            if ocr_result in valid_sensor_ids:
                print(f"✗ Sensor ID '{ocr_result}' already scanned (in valid_sensor_ids)")
                show_modal_warning("Already Scanned", 
                                   f"Sensor ID: {ocr_result}\n\n"
                                   f"This sensor has already been scanned.")
                return
            # Otherwise check if it's a valid sensor ID format and whether it belongs to this lot
            sensor_id_pattern = r'^\d+-\d+-[A-Z0-9]+-\d+$'
            if re.match(sensor_id_pattern, ocr_result):
                try:
                    conn_check = sqlite3.connect(db_path_tracking)
                    cur_check = conn_check.cursor()
                    cur_check.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
                    all_lot_sensors = [r[0] for r in cur_check.fetchall()]
                    if ocr_result in all_lot_sensors:
                        show_modal_warning("DEFECTIVE SENSOR - CANNOT PROCEED", 
                                           f"Detected: '{ocr_result}'\n\n"
                                           f"This sensor belongs to lot '{lot_number}' but has defects from previous processes.\n\n"
                                           f"Action: Set aside and scan next sensor.")
                    else:
                        show_modal_warning("Wrong Sensor ID - OCR Output Incorrect", 
                                           f"Detected: '{ocr_result}'\n\n"
                                           f"This sensor does NOT belong to lot '{lot_number}'.\n\n"
                                           f"Please verify the sensor or set it aside.")
                    conn_check.close()
                except sqlite3.Error:
                    show_modal_warning("Wrong Sensor ID", f"Detected: '{ocr_result}'\n\nThis sensor is not valid for this lot.")
                return
                return

        # Find first empty row
        row_index = -1
        for i in range(20):
            if not sensor_id_labels[i].get().strip():
                row_index = i
                break
        
        if row_index == -1:
            status_label.config(text="✗ Table full", fg="red")
            messagebox.showwarning("Table Full", "All 20 rows are filled. Cannot add more sensors.")
            return

        # Update table
        sensor_id_labels[row_index].delete(0, tk.END)
        sensor_id_labels[row_index].insert(0, ocr_result)
        status_labels[row_index].config(text="Printing...", bg="yellow", fg="black")
        
        # Update preview
        update_preview(ocr_result)
        
        # Auto print
        root.after(100, lambda: auto_print_label(ocr_result, row_index))
        
    except Exception as e:
        status_label.config(text=f"✗ OCR error", fg="red")
        messagebox.showerror("OCR Error", f"An error occurred during OCR processing:\n{e}")
        print(f"Error during OCR processing: {e}")
        import traceback
        traceback.print_exc()

# Start camera automatically
start_camera()

# Initialize preview with default sensor ID
update_preview("12-23-12345-123456")

# Auto-detect printer on startup
auto_detect_printer()

# Periodic printer check (every 3 seconds for faster updates)
def check_printer():
    auto_detect_printer()
    root.after(3000, check_printer)  # Check every 3 seconds

# Start periodic printer check immediately
check_printer()

def on_closing():
    global cap
    if cap and cap.isOpened():
        cap.release()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

# Focus lot number entry
entries["Lot Number:"].focus_set()

root.mainloop()
