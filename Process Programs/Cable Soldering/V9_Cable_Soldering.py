import tkinter as tk
from tkinter import messagebox, Label, Button, Scale, ttk
import sqlite3
import time
import cv2
from PIL import Image, ImageFilter, ImageOps, ImageTk, ImageDraw, ImageFont
import pytesseract
import threading
import numpy as np
import os
import csv
from datetime import datetime
import re
from scipy.ndimage import gaussian_filter1d
import json
from tkinter import ttk
import usb.core
import usb.util
import qrcode

# ML functionality removed - using traditional color detection only

# ----------------------------
# Godex RT863i+ Printer Configuration
# ----------------------------
# Godex RT863i USB Settings
GODEX_VENDOR_ID = 0x0B9B  # Godex vendor ID
GODEX_PRODUCT_ID = 0x0863  # RT863i product ID (may vary, will auto-detect)

# Label dimensions (20mm x 8mm die-cut labels)
MM_TO_INCH = 1 / 25.4
DPI = 600
WIDTH_MM, HEIGHT_MM = 20, 8
WIDTH_PX = int(WIDTH_MM * DPI * MM_TO_INCH)  # 128 pixels
HEIGHT_PX = int(HEIGHT_MM * DPI * MM_TO_INCH)  # 64 pixels

# Cutter Settings
ENABLE_CUTTER = True
CUT_COMMAND_EZPL = "^C"
CUT_FEED_EZPL = "^N10"
CUT_BACK_EZPL = ""
CUT_COMMAND_WINDOWS = b""
CUT_FEED_WINDOWS = b""
CUT_BACK_WINDOWS = b""

# TDK Logo Path
TDK_LOGO_PATH = r"C:\Users\a493353\Downloads\TDK-Logo.png"

# Compatibility wrapper for resampling
try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.ANTIALIAS

# Define paths
before_image_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\OCRBefore.png"
save_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\OCRAfter.png"
enhanced_image_path = r"\\phlsvr08\BMS Data\Lot ID's\Database\Enhanced_OCRAfter.png"
assembly_data_base_path = r"\\phlsvr08\BMS Data\Assembly Data\Cable Wire Soldering Orientation"

# Path to Tesseract executable
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\a493353\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

# Custom Tesseract configuration
custom_oem_psm_config = (
    '--oem 3 --psm 6 '
    '-c tessedit_char_whitelist="ABCDEFGIJKLMNOPQRSTVWXZ0123456789- "'
    #'-c textord_min_linesize=5 '
    #'-c textord_debug_tabfind=3 '  # Debug mode (optional for troubleshooting)
    #'-c font_name="OCR-A Extended"'
    )

# Define the paths to the databases
db_path_tracking = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"
db_path_masterlist = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"
config_file_path = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\process_flow.json"

# Load process flow configuration
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

# Using traditional color detection only

# ----------------------------
# Printer Helper Functions
# ----------------------------

def find_godex_printer():
    """Find Godex RT863i printer via USB"""
    try:
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

def send_to_printer_usb(data, device):
    """Send EZPL data to Godex RT863i via USB"""
    try:
        if device.is_kernel_driver_active(0):
            try:
                device.detach_kernel_driver(0)
            except:
                pass
        
        device.set_configuration()
        cfg = device.get_active_configuration()
        intf = cfg[(0,0)]
        
        ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
        )
        
        if ep_out is None:
            raise Exception("Could not find USB OUT endpoint")
        
        ep_out.write(data.encode('ascii'))
        return True
        
    except usb.core.USBError as e:
        raise Exception(f"USB Error: {e}\nMake sure no other program is using the printer.")
    except Exception as e:
        raise Exception(f"Communication Error: {e}")

def send_to_printer_windows(label_image, printer_name="Godex RT863i+"):
    """Send image to printer via Windows print spooler"""
    try:
        import win32print
        import win32ui
        from PIL import ImageWin
        
        hprinter = win32print.OpenPrinter(printer_name)
        hdc = win32ui.CreateDC()
        hdc.CreatePrinterDC(printer_name)
        hdc.StartDoc("Label")
        hdc.StartPage()
        
        dib = ImageWin.Dib(label_image)
        dib.draw(hdc.GetHandleOutput(), (0, 0, label_image.width, label_image.height))
        
        hdc.EndPage()
        hdc.EndDoc()
        hdc.DeleteDC()
        win32print.ClosePrinter(hprinter)
        return True
        
    except ImportError:
        raise Exception("pywin32 not installed. Install with: pip install pywin32")
    except Exception as e:
        raise Exception(f"Windows Print Error: {e}")

def send_raw_to_windows_printer(printer_name, data_bytes):
    """Send raw bytes to a Windows printer via the spooler (RAW mode)"""
    try:
        import win32print
        handle = win32print.OpenPrinter(printer_name)
        try:
            job_id = win32print.StartDocPrinter(handle, 1, ("RawData", None, "RAW"))
            try:
                win32print.StartPagePrinter(handle)
                win32print.WritePrinter(handle, data_bytes)
                win32print.EndPagePrinter(handle)
            finally:
                try:
                    win32print.EndDocPrinter(handle)
                except Exception:
                    pass
        finally:
            try:
                win32print.ClosePrinter(handle)
            except Exception:
                pass
        return True
    except ImportError:
        raise Exception("pywin32 not installed. Install with: pip install pywin32")
    except Exception as e:
        raise Exception(f"Write raw printer error: {e}")

def image_to_ezpl_bitmap(image, x, y):
    """Convert PIL Image to EZPL bitmap command"""
    bw_image = image.convert('1')
    width, height = bw_image.size
    pixels = bw_image.load()
    bytes_per_row = (width + 7) // 8
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
        if bit_pos != 7:
            bitmap_data.append(byte_val)
    
    ezpl_cmd = f"GW{x},{y},{bytes_per_row},{height},"
    ezpl_cmd += ''.join([f"{b:02X}" for b in bitmap_data])
    return ezpl_cmd

def generate_ezpl_label(label_image, label_num, cut=False):
    """Generate EZPL commands for Godex RT863i with proper die-cut label handling"""
    commands = []
    
    commands.append("^Q20,3")
    commands.append("^W80")
    commands.append("^H10")
    commands.append("^S4")
    commands.append("^P1")
    commands.append("^C1")
    commands.append("^E20")
    commands.append("^L")
    commands.append("~X")
    
    bitmap_cmd = image_to_ezpl_bitmap(label_image, 0, 0)
    commands.append(bitmap_cmd)
    commands.append("E")
    
    try:
        if cut and ENABLE_CUTTER:
            if CUT_FEED_EZPL:
                commands.append(str(CUT_FEED_EZPL))
            if CUT_COMMAND_EZPL:
                commands.append(str(CUT_COMMAND_EZPL))
            if CUT_BACK_EZPL:
                commands.append(str(CUT_BACK_EZPL))
    except NameError:
        pass

    return '\n'.join([c for c in commands if c])

def load_tdk_logo(size_px):
    """Load and resize TDK logo"""
    try:
        logo = Image.open(TDK_LOGO_PATH).convert("RGBA")
        logo_w, logo_h = logo.size
        new_h = 180
        if new_h > 0:
            new_w = int((logo_w / logo_h) * new_h)
            logo = logo.resize((new_w, new_h), RESAMPLE)
        return logo
    except FileNotFoundError:
        print(f"Warning: TDK logo file not found at: {TDK_LOGO_PATH}")
        return None
    except Exception as e:
        print(f"Warning: Could not load TDK logo: {e}")
        return None

def load_pillow_fonts(height_px):
    """Load fonts for label rendering"""
    try:
        font_confidential = ImageFont.truetype("arialbd.ttf", 40)
        font_bms = ImageFont.truetype("arialbd.ttf", 30)
        font_sensor = ImageFont.truetype("arial.ttf", 38)
    except Exception: 
        font_confidential = font_bms = font_sensor = ImageFont.load_default()
    return font_confidential, font_bms, font_sensor

def make_label1_image():
    """Generate Label 1: CONFIDENTIAL + TDK Logo + BMS-SENSOR-05"""
    label1 = Image.new("RGB", (WIDTH_PX, HEIGHT_PX), "white")
    draw = ImageDraw.Draw(label1)
    font_confidential, font_bms, _ = load_pillow_fonts(HEIGHT_PX)
    
    tdk_logo = load_tdk_logo(HEIGHT_PX)
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
        logo_x = (WIDTH_PX - logo_w) // 2 - 10
        logo_y = (HEIGHT_PX - logo_h) // 2 - 10
        label1.paste(tdk_logo, (logo_x, logo_y), tdk_logo)
    
    # Draw BMS-SENSOR-05 at bottom
    bms_text = "BMS-SENSOR-05"
    try:
        bbox = draw.textbbox((0, 0), bms_text, font=font_bms)
        bms_width = bbox[2] - bbox[0]
    except:
        bms_width = len(bms_text) * 20
    bms_x = (WIDTH_PX - bms_width) // 2 - 10
    bms_y = HEIGHT_PX - 60 - y_offset
    draw.text((bms_x, bms_y), bms_text, font=font_bms, fill="black")
    
    return label1

def make_label2_image(sensor_text):
    """Generate Label 2: Sensor ID + QR Code"""
    label2 = Image.new("RGB", (WIDTH_PX, HEIGHT_PX), "white")
    _, _, font_sensor = load_pillow_fonts(HEIGHT_PX)

    # QR CODE
    qr_size = 225
    qr = qrcode.make(sensor_text)
    qr = qr.resize((qr_size, qr_size), RESAMPLE)
    qr_x = WIDTH_PX - qr_size - 50
    qr_y = -35
    label2.paste(qr, (qr_x, qr_y))

    # FORMAT SENSOR TEXT
    parts = sensor_text.split('-')
    if len(parts) >= 4:
        sensor_lines = [parts[0] + '-' + parts[1] + '-']
        for part in parts[2:]:
            sensor_lines.append(part)
    else:
        sensor_lines = []
        for i, part in enumerate(parts):
            if i < len(parts) - 1:
                sensor_lines.append(part + "-")
            else:
                sensor_lines.append(part)

    sensor_multiline = "\n".join(sensor_lines)

    # DRAW TEXT ON TEMP IMAGE
    temp_img = Image.new("RGBA", (300, HEIGHT_PX), (255, 255, 255, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    temp_draw.multiline_text((0, 0), sensor_multiline, font=font_sensor, fill="black", spacing=0)

    # ROTATE
    rotated_text = temp_img.rotate(90, expand=True)
    rotated_text = rotated_text.crop(rotated_text.getbbox())

    # PASTE ON LABEL
    text_x = 60
    text_y = 30
    label2.paste(rotated_text, (text_x, text_y), rotated_text)

    return label2

def auto_detect_printer():
    """Auto-detect available Godex printers and populate dropdown"""
    global available_printers
    printers = []
    
    # Try USB detection
    usb_devices = find_godex_printer()
    for dev in usb_devices:
        printers.append({
            'name': f"{dev['name']} (VID:{dev['vid']} PID:{dev['pid']})",
            'method': 'usb',
            'online': True,
            'display_name': f"USB: {dev['name']}"
        })
    
    # Try Windows printers
    try:
        import win32print
        import pywintypes
        
        win_printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        for printer in win_printers:
            printer_name = printer[2]
            if "godex" in printer_name.lower() or "rt863" in printer_name.lower():
                is_offline = True
                
                try:
                    handle = win32print.OpenPrinter(printer_name)
                    try:
                        job_info = ("StatusTest", None, "RAW")
                        try:
                            job_id = win32print.StartDocPrinter(handle, 1, job_info)
                            is_offline = False
                            try:
                                win32print.EndDocPrinter(handle)
                                win32print.SetJob(handle, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
                            except:
                                pass
                        except pywintypes.error:
                            is_offline = True
                    finally:
                        win32print.ClosePrinter(handle)
                    
                    status_text = "Online" if not is_offline else "Offline"
                    printers.append({
                        'name': printer_name,
                        'method': 'windows',
                        'online': not is_offline,
                        'display_name': f"Win: {printer_name} ({status_text})"
                    })
                except:
                    printers.append({
                        'name': printer_name,
                        'method': 'windows',
                        'online': False,
                        'display_name': f"Win: {printer_name} (Offline)"
                    })
    except Exception:
        pass
    
    available_printers = printers
    
    # Update the combobox with detected printers
    if printers:
        printer_names = [p['display_name'] for p in printers]
        printer_combobox['values'] = printer_names
        
        # Select the first online printer by default
        online_printers = [i for i, p in enumerate(printers) if p['online']]
        if online_printers:
            printer_combobox.current(online_printers[0])
        else:
            printer_combobox.current(0)
        
        # Set the detected printer
        on_printer_selected(None)
    else:
        printer_combobox['values'] = ["No Godex printer found"]
        printer_combobox.current(0)
        detected_printer["name"] = None
        detected_printer["method"] = None
        detected_printer["online"] = False

def on_printer_selected(event):
    """Handle printer selection from dropdown"""
    global detected_printer
    
    selected_index = printer_combobox.current()
    if selected_index >= 0 and selected_index < len(available_printers):
        printer = available_printers[selected_index]
        detected_printer["name"] = printer["name"]
        detected_printer["method"] = printer["method"]
        detected_printer["online"] = printer["online"]
        print(f"✓ Selected printer: {printer['display_name']}")
    else:
        detected_printer["name"] = None
        detected_printer["method"] = None
        detected_printer["online"] = False

def try_print_label(sensor_id):
    """Print labels for the sensor ID"""
    if not detected_printer.get("name"):
        print(f"✗ No printer detected for {sensor_id}")
        return False
    
    if not detected_printer.get("online", True):
        print(f"✗ Printer offline for {sensor_id}")
        return False
    
    try:
        label1 = make_label1_image()
        label2 = make_label2_image(sensor_id)
        
        method = detected_printer["method"]
        printer_name = detected_printer["name"]
        
        if method == "windows":
            send_to_printer_windows(label1, printer_name)
            time.sleep(2.0)
            send_to_printer_windows(label2, printer_name)
            time.sleep(1.5)
            
            if ENABLE_CUTTER:
                try:
                    if CUT_FEED_WINDOWS:
                        send_raw_to_windows_printer(printer_name, CUT_FEED_WINDOWS)
                    elif CUT_FEED_EZPL:
                        send_raw_to_windows_printer(printer_name, str(CUT_FEED_EZPL).encode('ascii', errors='ignore'))
                    
                    if CUT_COMMAND_WINDOWS:
                        send_raw_to_windows_printer(printer_name, CUT_COMMAND_WINDOWS)
                    elif CUT_COMMAND_EZPL:
                        send_raw_to_windows_printer(printer_name, str(CUT_COMMAND_EZPL).encode('ascii', errors='ignore'))
                    
                    if CUT_BACK_WINDOWS:
                        time.sleep(0.2)
                        send_raw_to_windows_printer(printer_name, CUT_BACK_WINDOWS)
                    elif CUT_BACK_EZPL:
                        time.sleep(0.2)
                        send_raw_to_windows_printer(printer_name, str(CUT_BACK_EZPL).encode('ascii', errors='ignore'))
                except Exception as e:
                    print(f"Cut command failed: {e}")
            
            print(f"✓ Printed labels for {sensor_id} via Windows")
            return True
            
        elif method == "usb":
            usb_devices = find_godex_printer()
            if not usb_devices:
                raise Exception("USB device not found")
            
            device = usb_devices[0]['device']
            
            ezpl1 = generate_ezpl_label(label1, 1, cut=False)
            send_to_printer_usb(ezpl1, device)
            time.sleep(2.0)
            
            ezpl2 = generate_ezpl_label(label2, 2, cut=True)
            send_to_printer_usb(ezpl2, device)
            time.sleep(1.5)
            
            print(f"✓ Printed labels for {sensor_id} via USB")
            return True
        
        return False
        
    except Exception as e:
        print(f"✗ Print error for {sensor_id}: {e}")
        return False

# Auto-detected printer variable
detected_printer = {"name": None, "method": None, "online": False}
available_printers = []  # Store all detected printers

# Create the main application window
root = tk.Tk()
root.title("Cable Wire Soldering")
root.geometry("1350x650")  # Increased width to fit thumbnail gallery
root.configure(bg="lightblue")
root.resizable(False, False)

# Function to query the database for Lot Number information
def fetch_lot_info(event=None):
    
    global sensor_ids_no_defects, current_lot_number, thumbnail_data
    
    lot_number = entries["Lot Number:"].get().strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number.")
        return

    # Check if lot number changed - clear thumbnails if different lot
    if current_lot_number != lot_number:
        current_lot_number = lot_number
        clear_thumbnail_gallery()
        thumbnail_data = []
        print(f"✓ Lot number changed to {lot_number} - thumbnail gallery cleared")

    try:
        # Connect to the tracking database  
        conn = sqlite3.connect(db_path_tracking)
        cursor = conn.cursor()

        # Fetch current_process based on Lot Number
        cursor.execute("SELECT current_process FROM lot_tracking WHERE lot_number = ?", (lot_number,))
        result = cursor.fetchone()
        if result:
            current_process = result[0]
            entries["Current Process:"].config(state="normal")
            entries["Current Process:"].delete(0, tk.END)
            entries["Current Process:"].insert(0, current_process)
            entries["Current Process:"].config(state="readonly")

            # Check if the current_process is "Cable Soldering"
            if current_process != "Cable Soldering":
                messagebox.showerror("Error", "The lot number inputted is not for Cable Soldering.")
                delete_action()
                return
        else:
            messagebox.showwarning("Warning", "Lot Number not found in the database.")
            return

        # Fetch sensor_id values based on Lot Number
        # Use allowed sensor ids for this process (excludes sensors with defects in previous processes)
        sensor_ids_no_defects = get_allowed_sensor_ids(lot_number, current_process)

        # Clear existing Sensor ID values in the table
        for row in range(20):
            data_entry[row][0].config(state="normal")  # Set to normal to clear previous data
            data_entry[row][0].delete(0, tk.END)
            data_entry[row][0].config(state="readonly")  # Set back to readonly
            # Keep wire color columns DISABLED
            for col in range(1, 7):
                data_entry[row][col].config(state="readonly")
                data_entry[row][col].delete(0, tk.END)
                data_entry[row][col].config(bg="white")
            judgement_labels[row].config(text="", bg="lightblue")

        # Clear the sensor ID textbox and set focus to it
        sensor_id_textbox.delete("1.0", tk.END)
        sensor_id_textbox.focus_set()

        conn.close()

    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")

def navigate_on_enter(event, row, col):
    global data_entry  # Ensure access to the data_entry list

    next_row, next_col = row, col
    total_rows = len(data_entry)  # Get total rows count

    if col == 4:  # Column 5 (TS Gap to MR Chip)
        next_row += 1  # Move to the next row
        next_col = 1  # Move to Column 2 (BS Gap to GMR)
        if next_row >= total_rows or not data_entry[next_row][0].get().strip():
            # If at the last row with a Sensor ID, move to Column 6 (first row)
            next_row = 0
            next_col = 5

    elif col == 5:  # Column 6 (PCB Gap to BS1)
        next_row += 1  # Move to the next row
        if next_row >= total_rows or not data_entry[next_row][0].get().strip():
            # If at the last row with a Sensor ID, move to Column 7 (first row)
            next_row = 0
            next_col = 6

    elif col == 6:  # Column 7 (PCB Gap to BS2)
        if 0 <= row < total_rows:  # Ensure row is within valid range
            judge_row_values(row)  # ✅ Call judge_row_values for the current row
        
        next_row += 1  # ✅ Move to the next row in Column 7
        next_col = 6  # ✅ Stay in Column 7
        
        # ✅ Ensure we don't go out of bounds
        if next_row >= total_rows:
            next_row = total_rows - 1  # Stay on the last valid row

    else:
        # Default behavior: move to the next column (if no special rule is applied)
        next_col += 1
        if next_col >= len(data_entry[row]):  
            next_row += 1
            next_col = 1  # Move to the first column after Sensor ID

    # ✅ Ensure we don't move beyond the table limits
    if 0 <= next_row < total_rows and 0 <= next_col < len(data_entry[next_row]):
        data_entry[next_row][next_col].focus_set()


# Function to validate text input (for wire colors)
def validate_text_input(P):
    # Allow any text input for wire colors
    return True

# Function to judge the input values for a specific row and change Entry box colors individually
def judge_row_values(row):
    if data_entry[row][0].get():  # Only judge rows with Sensor ID
        # Get the values for each wire color
        values = [
            data_entry[row][1].get(),  # Wire 1
            data_entry[row][2].get(),  # Wire 2
            data_entry[row][3].get(),  # Wire 3
            data_entry[row][4].get(),  # Wire 4
            data_entry[row][5].get(),  # Wire 5
            data_entry[row][6].get(),  # Wire 6
        ]

        # Define the expected colors for each wire
        expected_colors = ["Blue", "White", "Black", "Green", "Brown", "Yellow"]

        # Initialize a flag for row status
        row_failed = False

        # Loop through each value and check against expected color
        for col, (value, expected_color) in enumerate(zip(values, expected_colors), start=1):
            if value.strip():  # Only check if there's a value
                if value == expected_color:
                    # Reset the background color for valid values
                    data_entry[row][col].config(bg="white")
                else:
                    # Mark as failed and change background to red
                    row_failed = True
                    data_entry[row][col].config(bg="red")
            else:
                # Empty value, mark as failed
                row_failed = True
                data_entry[row][col].config(bg="white")

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

def save_wire_orientation_image(sensor_id, lot_number):
    """Save the wire orientation image to the assembly data folder"""
    try:
        # Get current date for folder structure
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Create folder path: Base/Date/Lot Number
        date_folder = os.path.join(assembly_data_base_path, current_date)
        lot_folder = os.path.join(date_folder, lot_number)
        
        # Create directories if they don't exist
        os.makedirs(lot_folder, exist_ok=True)
        
        # Capture current frame from camera
        if cap and cap.isOpened():
            ret, frame = cap.read()
            if ret:
                # Save image with sensor ID as filename
                image_filename = f"{sensor_id}.png"
                image_path = os.path.join(lot_folder, image_filename)
                cv2.imwrite(image_path, frame)
                print(f"✓ Wire orientation image saved: {image_path}")
                
                # Add thumbnail to gallery
                add_thumbnail_to_gallery(frame, sensor_id, image_path)
                
                return True
            else:
                print("✗ Failed to capture frame for wire orientation image")
                return False
        else:
            print("✗ Camera not available for wire orientation image")
            return False
    except Exception as e:
        print(f"✗ Error saving wire orientation image: {e}")
        return False

def show_image_preview(image_path, sensor_id):
    """Show a popup window with the full-size captured image"""
    try:
        # Create popup window
        preview_window = tk.Toplevel(root)
        preview_window.title(f"Image Preview - {sensor_id}")
        preview_window.geometry("700x600")
        preview_window.configure(bg="#2c3e50")
        preview_window.resizable(False, False)
        
        # Title label
        title_label = tk.Label(preview_window, text=f"Sensor ID: {sensor_id}", 
                              font=("Arial", 14, "bold"), bg="#2c3e50", fg="white")
        title_label.pack(pady=10)
        
        # Load and display image
        img = cv2.imread(image_path)
        if img is not None:
            # Resize to fit window while maintaining aspect ratio
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(img_rgb)
            
            # Calculate size to fit in window
            max_width = 680
            max_height = 500
            # Use LANCZOS (compatible with older PIL versions)
            try:
                img_pil.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            except AttributeError:
                # Fallback for older Pillow versions
                img_pil.thumbnail((max_width, max_height), Image.LANCZOS)
            
            img_tk = ImageTk.PhotoImage(img_pil)
            
            # Image label
            img_label = tk.Label(preview_window, image=img_tk, bg="#2c3e50")
            img_label.image = img_tk  # Keep reference
            img_label.pack(pady=10)
            
            # Path label
            path_label = tk.Label(preview_window, text=f"Path: {image_path}", 
                                 font=("Arial", 8), bg="#2c3e50", fg="#95a5a6", wraplength=650)
            path_label.pack(pady=5)
            
            # Close button
            close_btn = tk.Button(preview_window, text="Close", command=preview_window.destroy,
                                 font=("Arial", 12, "bold"), bg="#e74c3c", fg="white", 
                                 padx=20, pady=5)
            close_btn.pack(pady=10)
        else:
            error_label = tk.Label(preview_window, text="Failed to load image", 
                                  font=("Arial", 12), bg="#2c3e50", fg="red")
            error_label.pack(pady=50)
            
    except Exception as e:
        print(f"Error showing image preview: {e}")
        messagebox.showerror("Preview Error", f"Could not open image preview:\n{e}")

def add_thumbnail_to_gallery(frame, sensor_id, image_path):
    """Add a thumbnail to the gallery canvas"""
    global thumbnail_data
    
    try:
        # Find the next available slot (based on number of sensors scanned)
        slot_index = len(thumbnail_data)
        
        print(f"Adding thumbnail for {sensor_id}, slot_index: {slot_index}")
        
        if slot_index >= 20:
            print(f"⚠ Gallery full - cannot add more thumbnails")
            return
        
        # Store thumbnail data FIRST
        thumbnail_data.append({'image_path': image_path, 'sensor_id': sensor_id})
        
        # Create thumbnail (smaller size to fit better)
        thumbnail_width = 50
        thumbnail_height = 40
        frame_resized = cv2.resize(frame, (thumbnail_width, thumbnail_height))
        frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        imgtk = ImageTk.PhotoImage(image=img)
        
        # Calculate position in grid (1 column, 20 rows)
        x = 5
        y = 5 + slot_index * 50
        
        print(f"Thumbnail position: slot={slot_index}, x={x}, y={y}")
        
        # Create thumbnail on canvas with clickable functionality
        img_id = thumbnail_canvas.create_image(x, y, anchor="nw", image=imgtk, tags=f"thumb_{slot_index}")
        
        # Add sensor ID text next to thumbnail
        thumbnail_canvas.create_text(x + 60, y + 20, text=sensor_id[-8:], 
                                     font=("Arial", 6), fill="white", anchor="w", tags=f"thumb_{slot_index}")
        
        # Bind click event to thumbnail
        thumbnail_canvas.tag_bind(f"thumb_{slot_index}", "<Button-1>", 
                                 lambda e, path=image_path, sid=sensor_id: show_image_preview(path, sid))
        
        # Store reference to prevent garbage collection - CRITICAL!
        thumbnail_canvas.images.append(imgtk)
        
        # Force canvas update
        thumbnail_canvas.update()
        
        print(f"✓ Thumbnail added successfully for {sensor_id}, total images: {len(thumbnail_canvas.images)}")
        
    except Exception as e:
        print(f"✗ Error adding thumbnail: {e}")
        import traceback
        traceback.print_exc()

def clear_thumbnail_gallery():
    """Clear all thumbnails from the gallery"""
    global thumbnail_data
    thumbnail_canvas.delete("all")
    thumbnail_data = []
    if hasattr(thumbnail_canvas, 'images'):
        thumbnail_canvas.images.clear()

def validate_sensor_id():
    # Get the values from the lot number entry and sensor ID textbox
    lot_number = entries["Lot Number:"].get().strip()
    sensor_id_value = sensor_id_textbox.get("1.0", tk.END).strip()

    if not lot_number:
        messagebox.showwarning("Warning", "Lot Number is missing.")
        sensor_id_textbox.delete("1.0", tk.END)
        sensor_id_textbox.config(bg="white")
        return

    try:
        # Use allowed sensors for this process (exclude sensors with defects in previous processes)
        current_process = entries.get("Current Process:", tk.Entry()).get().strip()
        allowed_sensor_ids = get_allowed_sensor_ids(lot_number, current_process)

        if not allowed_sensor_ids:
            sensor_id_textbox.config(bg="red")
            messagebox.showerror("No Sensors Available", 
                               "No sensors can proceed to this process.\n\n"
                               "All sensors have defects from previous processes.")
            sensor_id_textbox.delete("1.0", tk.END)
            sensor_id_textbox.config(bg="white")
            return

        if sensor_id_value not in allowed_sensor_ids:
            sensor_id_textbox.config(bg="red")
            messagebox.showerror("Sensor Rejected", 
                               f"Sensor ID: {sensor_id_value}\n\n"
                               f"This sensor CANNOT proceed to '{current_process}'.\n\n"
                               f"Reason: Either not in lot '{lot_number}' OR\n"
                               f"has defects from previous processes.\n\n"
                               f"This sensor must be set aside.")
            sensor_id_textbox.delete("1.0", tk.END)
            sensor_id_textbox.config(bg="white")
        else:
            # Check if sensor ID is already in the table
            duplicate_found = False
            for row in range(20):
                if data_entry[row][0].get() == sensor_id_value:
                    duplicate_found = True
                    break
            
            if duplicate_found:
                messagebox.showerror("Duplicate Sensor ID", f"Sensor ID '{sensor_id_value}' has already been scanned.")
                sensor_id_textbox.delete("1.0", tk.END)
                sensor_id_textbox.config(bg="white")
                return
            
            # Find the first empty row and add the sensor ID
            row_found = False
            for row in range(20):
                if not data_entry[row][0].get():
                    row_found = True
                    sensor_id_textbox.config(bg="green")
                    
                    # Add sensor ID to the row
                    data_entry[row][0].config(state="normal")
                    data_entry[row][0].delete(0, tk.END)
                    data_entry[row][0].insert(0, sensor_id_value)
                    data_entry[row][0].config(state="readonly")
                    
                    # Enable wire color columns for this row only
                    for col in range(1, 7):
                        data_entry[row][col].config(state="normal")
                    
                    # Auto-fill with detected colors
                    for i in range(6):
                        detected_color = color_labels[i].cget("text")
                        if detected_color != "---":
                            data_entry[row][i + 1].delete(0, tk.END)
                            data_entry[row][i + 1].insert(0, detected_color)
                    
                    # Judge the row after filling
                    judge_row_values(row)
                    
                    # Check if the row failed
                    if judgement_labels[row].cget("text") == "Failed":
                        messagebox.showerror("Wire Orientation Error", 
                                           "The wire orientation is not correct. Please reposition the wires and scan again.")
                        # Clear the row for re-scan
                        data_entry[row][0].config(state="normal")
                        data_entry[row][0].delete(0, tk.END)
                        data_entry[row][0].config(state="readonly")
                        for col in range(1, 7):
                            data_entry[row][col].delete(0, tk.END)
                            data_entry[row][col].config(state="readonly", bg="white")
                        judgement_labels[row].config(text="", bg="lightblue")
                    else:
                        # Row passed - save the wire orientation image
                        saved = save_wire_orientation_image(sensor_id_value, lot_number)
                        # Auto-print labels if printer selected
                        try:
                            if saved and detected_printer.get("name") is not None:
                                # Print in background thread to avoid UI freeze
                                threading.Thread(target=try_print_label, args=(sensor_id_value,)).start()
                                print(f"✓ Initiated label printing for {sensor_id_value}")
                        except Exception as e:
                            print(f"Print initiation error: {e}")
                    
                    # Clear the sensor ID textbox and reset background
                    sensor_id_textbox.delete("1.0", tk.END)
                    sensor_id_textbox.config(bg="white")
                    
                    # Set focus back to sensor ID textbox for next scan
                    sensor_id_textbox.focus_set()
                    break
            
            if not row_found:
                messagebox.showwarning("Table Full", "All 20 rows are filled. Cannot add more sensors.")
                sensor_id_textbox.delete("1.0", tk.END)
                sensor_id_textbox.config(bg="white")
                
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")

def on_sensor_id_enter(event=None):
    """Handle Enter key in the sensor ID textbox: validate and prevent newline."""
    validate_sensor_id()
    return "break"

# Global variable to control the live video feed
camera_index = 0
cap = None
cap_color = None  # Will use same camera as cap
last_successful_threshold = None  # Store the successful threshold value
current_lot_number = None  # Track current lot number for thumbnail management
thumbnail_data = []  # Store thumbnail data (image_path, sensor_id)

# Simple OCR confusion mapping (like in molding program)
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
        # Apply mapping character-by-character
        return ''.join(OCR_CONFUSIONS.get(ch, ch) for ch in s)
    except Exception:
        return s

def _levenshtein(a, b):
    """Calculate Levenshtein distance between two strings for fuzzy matching."""
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


# ---------- EZPL helpers (local copy/adapted - used for serial fallback) ----------
def image_to_ezpl_bitmap(image, x, y):
    """Convert PIL Image to EZPL GW bitmap command."""
    bw_image = image.convert('1')
    width, height = bw_image.size
    pixels = bw_image.load()
    bytes_per_row = (width + 7) // 8
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
        if bit_pos != 7:
            bitmap_data.append(byte_val)
    ezpl_cmd = f"GW{x},{y},{bytes_per_row},{height},"
    ezpl_cmd += ''.join([f"{b:02X}" for b in bitmap_data])
    return ezpl_cmd


def generate_ezpl_label(label_image, label_num, cut=False):
    """Generate a minimal EZPL label stream for the given PIL image."""
    commands = []
    commands.append("^Q20,3")
    commands.append("^W80")
    commands.append("^H10")
    commands.append("^S4")
    commands.append("^P1")
    commands.append("^C1")
    commands.append("^E20")
    commands.append("^L")
    commands.append("~X")
    bitmap_cmd = image_to_ezpl_bitmap(label_image, 0, 0)
    commands.append(bitmap_cmd)
    commands.append("E")
    try:
        if cut and 'CUT_COMMAND_EZPL' in globals() and CUT_COMMAND_EZPL:
            commands.append(str(CUT_FEED_EZPL) if 'CUT_FEED_EZPL' in globals() and CUT_FEED_EZPL else '')
            commands.append(str(CUT_COMMAND_EZPL))
    except Exception:
        pass
    return '\n'.join([c for c in commands if c])

# -------------------------------------------------------------------------------

# Add a flag to track the current view mode
threshold_view = False  # Start with threshold view
debug_detection_view = False  # New debug mode for wire detection

# Wire color detection regions (can be adjusted manually by dragging)
wire_regions = [
    {"x1": 115, "y1": 120, "x2": 139, "y2": 152, "name": "W1"},
    {"x1": 150, "y1": 117, "x2": 174, "y2": 147, "name": "W2"},
    {"x1": 185, "y1": 110, "x2": 206, "y2": 142, "name": "W3"},
    {"x1": 220, "y1": 116, "x2": 240, "y2": 146, "name": "W4"},
    {"x1": 251, "y1": 116, "x2": 273, "y2": 147, "name": "W5"},
    {"x1": 288, "y1": 114, "x2": 312, "y2": 147, "name": "W6"}
]
wire_dragging = {"active": False, "wire_index": -1, "corner": None, "start_x": 0, "start_y": 0}

# Function to toggle the view mode
def toggle_view():
    global threshold_view
    threshold_view = not threshold_view


def get_corner(x, y, frame):
    """Determine which corner/edge of the frame is being clicked"""
    corner_size = 10
    x1, y1, x2, y2 = frame["x1"], frame["y1"], frame["x2"], frame["y2"]
    
    # Check corners first
    if abs(x - x1) < corner_size and abs(y - y1) < corner_size:
        return "top_left"
    elif abs(x - x2) < corner_size and abs(y - y1) < corner_size:
        return "top_right"
    elif abs(x - x1) < corner_size and abs(y - y2) < corner_size:
        return "bottom_left"
    elif abs(x - x2) < corner_size and abs(y - y2) < corner_size:
        return "bottom_right"
    # Check edges
    elif abs(x - x1) < corner_size and y1 < y < y2:
        return "left"
    elif abs(x - x2) < corner_size and y1 < y < y2:
        return "right"
    elif abs(y - y1) < corner_size and x1 < x < x2:
        return "top"
    elif abs(y - y2) < corner_size and x1 < x < x2:
        return "bottom"
    # Check if inside frame (for moving)
    elif x1 < x < x2 and y1 < y < y2:
        return "move"
    return None

def on_wire_mouse_down(event):
    """Handle mouse down for wire region adjustment"""
    global wire_dragging
    
    # Check if clicking on a wire region
    for i, region in enumerate(wire_regions):
        corner = get_corner(event.x, event.y, region)
        if corner:
            wire_dragging["active"] = True
            wire_dragging["wire_index"] = i
            wire_dragging["corner"] = corner
            wire_dragging["start_x"] = event.x
            wire_dragging["start_y"] = event.y
            return

def on_wire_mouse_move(event):
    """Handle mouse move for wire region adjustment"""
    global wire_regions, wire_dragging
    
    # Handle wire dragging
    if wire_dragging["active"] and wire_dragging["wire_index"] >= 0:
        i = wire_dragging["wire_index"]
        region = wire_regions[i]
        dx = event.x - wire_dragging["start_x"]
        dy = event.y - wire_dragging["start_y"]
        corner = wire_dragging["corner"]
        
        if corner == "move":
            region["x1"] += dx
            region["x2"] += dx
            region["y1"] += dy
            region["y2"] += dy
        elif corner == "top_left":
            region["x1"] += dx
            region["y1"] += dy
        elif corner == "top_right":
            region["x2"] += dx
            region["y1"] += dy
        elif corner == "bottom_left":
            region["x1"] += dx
            region["y2"] += dy
        elif corner == "bottom_right":
            region["x2"] += dx
            region["y2"] += dy
        elif corner == "left":
            region["x1"] += dx
        elif corner == "right":
            region["x2"] += dx
        elif corner == "top":
            region["y1"] += dy
        elif corner == "bottom":
            region["y2"] += dy
        
        wire_dragging["start_x"] = event.x
        wire_dragging["start_y"] = event.y

def on_wire_mouse_up(event):
    """Handle mouse up for wire region adjustment"""
    global wire_dragging
    
    if wire_dragging["active"]:
        if wire_dragging["wire_index"] >= 0:
            print(f"Wire {wire_dragging['wire_index'] + 1} Region: {wire_regions[wire_dragging['wire_index']]}")
        wire_dragging["active"] = False
        wire_dragging["wire_index"] = -1

def hex_to_rgb(hex_color):
    """Converts a hex color string to an RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def detect_color(roi):
    """Advanced color detection using HSV color space with improved brown detection."""
    if roi.size == 0:
        return "Unknown"
    
    # Convert to HSV for better color detection
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    
    # Get median HSV values (more robust than mean)
    h_median = np.median(hsv_roi[:, :, 0])
    s_median = np.median(hsv_roi[:, :, 1])
    v_median = np.median(hsv_roi[:, :, 2])
    
    # Also get mean for comparison
    h_mean, s_mean, v_mean = cv2.mean(hsv_roi)[:3]
    
    # Use median for more robust detection
    h, s, v = h_median, s_median, v_median
    
    # White detection - high value (brightness), low saturation
    if v > 140 and s < 50:
        return "White"
    
    # Black detection - RELAXED to catch darker wires
    if v < 85:  # Increased from 70 to 85
        return "Black"
    
    # Brown detection - IMPROVED (check first before other colors)
    # Brown has low-medium saturation and medium-low value
    # Hue can be in orange-red range (0-20) or wrap-around (165-180)
    if 40 < v < 140 and 20 < s < 120:
        if (0 <= h <= 25) or (h >= 160):
            return "Brown"
    
    # For colored wires, check saturation
    if s > 30:  # Has enough color saturation
        # Blue: Hue 90-130 (cyan to blue range)
        if 90 <= h <= 130:
            return "Blue"
        
        # Green: Hue 40-85 (green range)
        if 40 <= h <= 85:
            return "Green"
        
        # Yellow: Hue 20-40 (yellow range) - expanded slightly
        if 20 <= h <= 40:
            return "Yellow"
    
    # Fallback: if saturation is low but not white/black
    if s < 30:
        if v > 120:
            return "White"
        elif v < 90:  # Increased from 80 to 90
            return "Black"
    
    return "Unknown"

def start_camera():
    global cap
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        messagebox.showerror("Error", "Could not open camera.")
    else:
        # Set camera resolution to 640x480 (4:3 aspect ratio)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        show_frame()

def auto_detect_wires(frame, debug=False):
    """Automatically detect 6 wire regions using fixed spacing and color validation"""
    global wire_regions
    
    # Define the search area - where wires are typically located
    search_y_start = 90 
    search_y_end = 155
    search_x_start = 110
    search_x_end = 320
    
    # Crop to search area
    search_area = frame[search_y_start:search_y_end, search_x_start:search_x_end].copy()
    search_width = search_x_end - search_x_start
    
    # Expected wire spacing - divide the width into 6 equal sections
    wire_width = 24  # Approximate width of each wire
    spacing = search_width / 6  # Space allocated per wire
    
    wire_candidates = []
    
    # For each expected wire position
    for i in range(6):
        # Calculate center position for this wire
        center_x = int(spacing * i + spacing / 2)
        
        # Define wire region with some margin
        x1 = max(0, center_x - wire_width // 2)
        x2 = min(search_width, center_x + wire_width // 2)
        
        # Check if there's actually a wire here by analyzing the region
        wire_region = search_area[:, x1:x2]
        
        # Convert to HSV to check for colored content
        hsv_region = cv2.cvtColor(wire_region, cv2.COLOR_BGR2HSV)
        
        # Check saturation - wires have color, background doesn't
        saturation = hsv_region[:, :, 1]
        mean_saturation = np.mean(saturation)
        
        # Check value (brightness) variation
        value = hsv_region[:, :, 2]
        std_value = np.std(value)
        
        # If there's enough color saturation or brightness variation, it's likely a wire
        if mean_saturation > 30 or std_value > 20:
            # Find the actual vertical extent of the wire
            gray_region = cv2.cvtColor(wire_region, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray_region, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Find rows with content
            row_sums = np.sum(binary, axis=1)
            rows_with_content = row_sums > (binary.shape[1] * 50)  # At least some pixels
            
            if np.any(rows_with_content):
                y_indices = np.where(rows_with_content)[0]
                y1 = max(0, y_indices[0] - 3)
                y2 = min(search_area.shape[0], y_indices[-1] + 3)
            else:
                y1 = 0
                y2 = search_area.shape[0]
            
            # Convert back to full frame coordinates
            wire_candidates.append({
                "x1": search_x_start + x1,
                "y1": search_y_start + y1,
                "x2": search_x_start + x2,
                "y2": search_y_start + y2,
                "center_x": search_x_start + center_x,
                "saturation": mean_saturation,
                "variance": std_value
            })
    
    # Debug visualization
    if debug:
        debug_frame = frame.copy()
        
        # Draw search area
        cv2.rectangle(debug_frame, (search_x_start, search_y_start), 
                     (search_x_end, search_y_end), (255, 0, 255), 2)
        
        # Draw expected wire divisions
        for i in range(7):
            x = search_x_start + int(spacing * i)
            cv2.line(debug_frame, (x, search_y_start), (x, search_y_end), 
                    (255, 255, 0), 1)
        
        # Draw detected wires
        for i, candidate in enumerate(wire_candidates):
            color = (0, 255, 0) if i < 6 else (0, 165, 255)
            cv2.rectangle(debug_frame, 
                         (candidate["x1"], candidate["y1"]), 
                         (candidate["x2"], candidate["y2"]), 
                         color, 2)
            # Draw center line
            cv2.line(debug_frame, 
                    (candidate["center_x"], candidate["y1"]),
                    (candidate["center_x"], candidate["y2"]),
                    color, 1)
            # Draw number and stats
            cv2.putText(debug_frame, f"{i+1}", 
                       (candidate["center_x"]-8, search_y_start - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            cv2.putText(debug_frame, f"S:{int(candidate['saturation'])}", 
                       (candidate["x1"], search_y_end + 15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)
        
        # Add info text
        return debug_frame, len(wire_candidates)
    
    # Apply detected regions
    if len(wire_candidates) == 6:
        for i in range(6):
            wire_regions[i]["x1"] = wire_candidates[i]["x1"]
            wire_regions[i]["y1"] = wire_candidates[i]["y1"]
            wire_regions[i]["x2"] = wire_candidates[i]["x2"]
            wire_regions[i]["y2"] = wire_candidates[i]["y2"]
        print(f"✓ Auto-detected 6 wires successfully")
        print(f"  Wire centers: {[w['center_x'] for w in wire_candidates]}")
        return True
    else:
        print(f"⚠ Detected {len(wire_candidates)} wires, expected 6.")
        return False

def detect_wire_colors_from_frame(frame):
    """Detect wire colors from a captured frame and update the color labels"""
    global wire_regions
    
    # Get original frame dimensions
    orig_height, orig_width = frame.shape[:2]
    
    # Calculate proper aspect ratio for display
    display_width = 400
    display_height = int(display_width * orig_height / orig_width)
    
    # Resize frame to match display size for coordinate mapping
    frame_display = cv2.resize(frame.copy(), (display_width, display_height))
    
    # DON'T auto-detect here - use the existing wire_regions that were set manually or by auto-detect button
    # auto_detect_wires(frame_display)  # REMOVED - this was causing the frame to shift
    
    expected_colors = ["Blue", "White", "Black", "Green", "Brown", "Yellow"]
    
    # Analyze regions and detect colors
    for i, region in enumerate(wire_regions):
        x1, y1, x2, y2 = region["x1"], region["y1"], region["x2"], region["y2"]
        
        # Ensure coordinates are within frame bounds
        x1 = max(0, min(x1, frame_display.shape[1] - 1))
        x2 = max(0, min(x2, frame_display.shape[1]))
        y1 = max(0, min(y1, frame_display.shape[0] - 1))
        y2 = max(0, min(y2, frame_display.shape[0]))
        
        if x2 > x1 and y2 > y1:
            roi = frame_display[y1:y2, x1:x2]
            detected_color = detect_color(roi)
            
            # Update the color detection labels
            color_labels[i].config(text=detected_color)
            
            # Change background color based on detection
            if detected_color != expected_colors[i]:
                color_labels[i].config(bg="red", fg="white")
            else:
                color_labels[i].config(bg="green", fg="white")
            
            print(f"Wire {i+1}: Detected {detected_color}, Expected {expected_colors[i]}")

def start_color_camera():
    """Color detection is now integrated into show_frame() - no separate camera needed"""
    pass

# Update the show_frame function
def show_frame():
    global threshold_view, wire_regions, debug_detection_view
    ret, frame = cap.read()
    if frame is not None:
        # Get original frame dimensions
        orig_height, orig_width = frame.shape[:2]
        
        # Calculate proper aspect ratio for display (maintain 4:3 ratio)
        display_width = 400
        display_height = int(display_width * orig_height / orig_width)
        
        # Process for display - single camera view with proper aspect ratio
        frame_display = cv2.resize(frame.copy(), (display_width, display_height))

        # Debug detection view mode
        if debug_detection_view:
            debug_frame, wire_count = auto_detect_wires(frame_display, debug=True)
            frame_to_display = debug_frame
            
        elif threshold_view:
            # Process for threshold view
            gray_frame = cv2.cvtColor(frame_display, cv2.COLOR_BGR2GRAY)
            threshold_value = threshold_scale.get()
            _, thresholded_frame = cv2.threshold(gray_frame, threshold_value, 255, cv2.THRESH_BINARY)
            frame_to_display = cv2.cvtColor(thresholded_frame, cv2.COLOR_GRAY2BGR)
        else:
            # Use the actual view
            frame_to_display = frame_display

        # Only draw wire regions if NOT in debug mode
        if not debug_detection_view:
            # Draw wire color detection regions on the frame
            expected_colors = ["Blue", "White", "Black", "Green", "Brown", "Yellow"]

            # Analyze regions and detect colors using adjustable wire_regions
            for i, region in enumerate(wire_regions):
                x1, y1, x2, y2 = region["x1"], region["y1"], region["x2"], region["y2"]
                
                # Ensure coordinates are within frame bounds
                x1 = max(0, min(x1, frame_display.shape[1] - 1))
                x2 = max(0, min(x2, frame_display.shape[1]))
                y1 = max(0, min(y1, frame_display.shape[0] - 1))
                y2 = max(0, min(y2, frame_display.shape[0]))
                
                if x2 > x1 and y2 > y1:
                    roi = frame_display[y1:y2, x1:x2]
                    detected_color = detect_color(roi)
                    
                    # Update the color detection labels
                    color_labels[i].config(text=detected_color)
                    
                    # Change background color based on detection
                    if detected_color != expected_colors[i]:
                        color_labels[i].config(bg="red", fg="white")
                    else:
                        color_labels[i].config(bg="green", fg="white")

                    # Draw rectangles around each wire region for visualization
                    # Use different colors for better visibility
                    rect_color = (0, 255, 0) if detected_color == expected_colors[i] else (0, 0, 255)
                    cv2.rectangle(frame_to_display, (x1, y1), (x2, y2), rect_color, 2)
                    
                    # Draw wire label at the top of the frame
                    wire_label = region["name"]
                    label_bg_color = (0, 180, 0) if detected_color == expected_colors[i] else (0, 0, 200)
                    
                    # Draw label background rectangle
                    label_size = cv2.getTextSize(wire_label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                    cv2.rectangle(frame_to_display, 
                                (x1, y1 - label_size[1] - 8), 
                                (x1 + label_size[0] + 4, y1), 
                                label_bg_color, -1)
                    
                    # Draw wire label text
                    cv2.putText(frame_to_display, wire_label, (x1 + 2, y1 - 4), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                    
                    # Draw expected color label at the bottom of the frame
                    expected_label = expected_colors[i][:3]  # Shortened (e.g., "Blu", "Whi")
                    cv2.putText(frame_to_display, expected_label, (x1 + 2, y2 - 4), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, rect_color, 1)
                    
                    # Draw corner handles for manual adjustment
                    handle_size = 3
                    cv2.circle(frame_to_display, (x1, y1), handle_size, rect_color, -1)
                    cv2.circle(frame_to_display, (x2, y1), handle_size, rect_color, -1)
                    cv2.circle(frame_to_display, (x1, y2), handle_size, rect_color, -1)
                    cv2.circle(frame_to_display, (x2, y2), handle_size, rect_color, -1)

        # Convert to ImageTk format and display (convert BGR to RGB)
        img = Image.fromarray(cv2.cvtColor(frame_to_display, cv2.COLOR_BGR2RGB))
        imgtk = ImageTk.PhotoImage(image=img)
        video_label.imgtk = imgtk
        video_label.configure(image=imgtk)
        
    video_label.after(10, show_frame)

def toggle_debug_view():
    """Toggle debug detection view"""
    global debug_detection_view
    debug_detection_view = not debug_detection_view
    if debug_detection_view:
        print("Debug detection view enabled - showing wire detection")
    else:
        print("Debug detection view disabled")

def manual_auto_detect():
    """Manually trigger automatic wire detection"""
    if not cap or not cap.isOpened():
        messagebox.showerror("Error", "Camera is not open.")
        return
    
    ret, frame = cap.read()
    if ret:
        # Get original frame dimensions
        orig_height, orig_width = frame.shape[:2]
        display_width = 400
        display_height = int(display_width * orig_height / orig_width)
        frame_display = cv2.resize(frame.copy(), (display_width, display_height))
        
        success = auto_detect_wires(frame_display)
        if success:
            messagebox.showinfo("Success", "Automatically detected 6 wires!")
        else:
            messagebox.showwarning("Detection Failed", "Could not detect 6 wires. Using manual regions.")
    else:
        messagebox.showerror("Error", "Failed to capture frame.")

def capture_image_and_process():
    if not cap or not cap.isOpened():
        messagebox.showerror("Error", "Camera is not open.")
        return

    ret, frame = cap.read()
    if ret:
        cv2.imwrite(before_image_path, frame)
        print(f"Image captured and saved as {before_image_path}")
        
        # Detect wire colors from the same captured frame
        detect_wire_colors_from_frame(frame)
        
        # Process OCR in a separate thread
        threading.Thread(target=process_image_for_ocr).start()
    else:
        messagebox.showerror("Error", "Failed to capture image.")

def process_image_for_ocr():
    """
    OPTIMIZED: Process full image with regex pattern detection.
    No manual cropping needed - automatically finds sensor ID anywhere in the image.
    """
    import re
    global threshold_view, last_successful_threshold, ocr_status_label
    try:
        # Get lot number and fetch valid sensor IDs FIRST
        lot_number = entries["Lot Number:"].get().strip()
        if not lot_number:
            print("⚠ Warning: Lot Number is missing, cannot validate sensor ID")
            sensor_id_textbox.config(bg="yellow")
            messagebox.showwarning("Input Error", "Please enter a Lot Number first.")
            return

        # Use allowed sensors for this process
        try:
            current_process = entries.get("Current Process:", tk.Entry()).get().strip()
            allowed_sensor_ids = get_allowed_sensor_ids(lot_number, current_process)

            if not allowed_sensor_ids:
                print(f"⚠ Warning: No allowed sensor IDs for lot {lot_number}")
                sensor_id_textbox.config(bg="yellow")
                messagebox.showwarning("Database Error", f"No allowed sensor IDs found for lot number {lot_number}.")
                return

            print(f"Allowed sensor IDs for lot {lot_number}: {len(allowed_sensor_ids)} sensors")

            # Check for already scanned sensors
            already_scanned = []
            for row in range(20):
                scanned_id = data_entry[row][0].get().strip()
                if scanned_id:
                    already_scanned.append(scanned_id)

            # Filter out already scanned sensors
            remaining_sensor_ids = [sid for sid in allowed_sensor_ids if sid not in already_scanned]

            if not remaining_sensor_ids:
                print("⚠ All allowed sensors for this lot have been scanned")
                sensor_id_textbox.config(bg="orange")
                messagebox.showinfo("Complete", "All sensors allowed for this process have been scanned.")
                return

            print(f"Remaining sensors to scan: {len(remaining_sensor_ids)}")
            
        except sqlite3.Error as e:
            print(f"Database Error during validation: {e}")
            sensor_id_textbox.config(bg="yellow")
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
            image = image.resize(new_size, Image.LANCZOS)
        
        # Save for debugging
        image.save(save_path)
        print(f"Processed image saved: {save_path}")
        
        # Switch to threshold view for visual feedback
        original_view = threshold_view
        threshold_view = True
        
        # Determine threshold attempts
        if 'last_successful_threshold' in globals() and last_successful_threshold is not None and already_scanned:
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
                threshold_scale.config(command=lambda x: None)
                threshold_scale.set(threshold_value)
                threshold_scale.config(command=on_threshold_changed)
                root.update_idletasks()
            
            # Process image with current threshold
            img_gray = ImageOps.grayscale(image)
            img_sharp = img_gray.filter(ImageFilter.SHARPEN)
            img_binary = img_sharp.point(lambda p: 255 if p > threshold_value else 0)
            img_binary.save(enhanced_image_path)
            
            # Perform OCR on full image
            raw_ocr_text = pytesseract.image_to_string(img_binary, config=custom_oem_psm_config)

            # Apply simple OCR confusion corrections (like molding program)
            ocr_text = _apply_confusions(raw_ocr_text)
            # Normalize to uppercase to help regex matching
            ocr_text = ocr_text.upper()

            print(f"[OCR] Raw text (thr={threshold_value}): {raw_ocr_text[:100]}")
            print(f"[OCR] Corrected text: {ocr_text[:100]}")
            
            # Pattern for sensor ID: XX-XX-XXXXX-XXXXXX
            pattern = r'\b(\d{2})-(\d{2})-([A-Z0-9]{4,5}[A-Z]?)-(\d{6})\b'
            matches = re.findall(pattern, ocr_text)
            
            if matches:
                sensor_id = f"{matches[0][0]}-{matches[0][1]}-{matches[0][2]}-{matches[0][3]}"
                last_detected_pattern = sensor_id  # Store for error messages
                
                # Exact match
                if sensor_id in remaining_sensor_ids:
                    print(f"[OCR] ✓ Pattern detected: {sensor_id} - CORRECT (valid for this lot)")
                    print(f"✓ Success! Sensor ID '{sensor_id}' detected at threshold {threshold_value}")
                    threshold_scale.config(command=lambda x: None)
                    threshold_scale.set(threshold_value)
                    threshold_scale.config(command=on_threshold_changed)
                    last_successful_threshold = threshold_value
                    ocr_result = sensor_id
                    break
                
                # Try simple confusion substitutions
                mapped = _apply_confusions(sensor_id)
                if mapped != sensor_id and mapped in remaining_sensor_ids:
                    print(f"[OCR] Mapped '{sensor_id}' -> '{mapped}' and matched remaining IDs")
                    threshold_scale.config(command=lambda x: None)
                    threshold_scale.set(threshold_value)
                    threshold_scale.config(command=on_threshold_changed)
                    last_successful_threshold = threshold_value
                    ocr_result = mapped
                    break
                
                if sensor_id in already_scanned:
                    print(f"[OCR] ✓ Pattern detected: {sensor_id} - INCORRECT (already scanned)")
                elif sensor_id in allowed_sensor_ids:
                    print(f"[OCR] ✓ Pattern detected: {sensor_id} - INCORRECT (not in remaining list)")
                else:
                    print(f"[OCR] ✓ Pattern detected: {sensor_id} - INCORRECT (wrong lot)")
                
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
                    threshold_scale.config(command=lambda x: None)
                    threshold_scale.set(threshold_value)
                    threshold_scale.config(command=on_threshold_changed)
                    last_successful_threshold = threshold_value
                    break
            
            # Try lenient pattern
            lenient_pattern = r'(\d{2})[\s\-]?(\d{2})[\s\-]?([A-Z0-9]{4,6})[\s\-]?(\d{6})'
            lenient_matches = re.findall(lenient_pattern, ocr_text)
            
            if lenient_matches and not ocr_result:
                sensor_id = f"{lenient_matches[0][0]}-{lenient_matches[0][1]}-{lenient_matches[0][2]}-{lenient_matches[0][3]}"
                last_detected_pattern = sensor_id  # Store for error messages
                
                if sensor_id in remaining_sensor_ids:
                    print(f"[OCR] ✓ Pattern detected (lenient): {sensor_id} - CORRECT")
                    print(f"✓ Success (lenient)! Sensor ID '{sensor_id}' detected")
                    last_successful_threshold = threshold_value
                    ocr_result = sensor_id
                    break
                
                # Try fuzzy matching on lenient pattern too
                mapped = _apply_confusions(sensor_id)
                best_match = None
                best_dist = None
                for variant in (sensor_id, mapped):
                    vstr = variant.replace('-', '')
                    for rid in remaining_sensor_ids:
                        d = _levenshtein(vstr, rid.replace('-', ''))
                        if best_dist is None or d < best_dist:
                            best_dist = d
                            best_match = (rid, d, variant)
                
                if best_match and best_match[1] <= 3:
                    matched_id = best_match[0]
                    print(f"[OCR] ~ Fuzzy matched (lenient) '{best_match[2]}' -> '{matched_id}' (dist={best_match[1]})")
                    ocr_result = matched_id
                    last_successful_threshold = threshold_value
                    break
                else:
                    print(f"[OCR] ✓ Pattern detected (lenient): {sensor_id} - INCORRECT")
        
        # Restore original view mode
        threshold_view = original_view
        
        # If no valid result found
        if ocr_result not in remaining_sensor_ids:
            print("✗ No valid sensor ID from this lot detected")
            sensor_id_textbox.config(bg="red")
            
            if ocr_result:  # OCR detected something, but it's wrong
                print(f"OCR detected: '{ocr_result}' but it's not valid for this lot")
                if ocr_result in already_scanned:
                    ocr_status_label.config(text=f"✗ WRONG - Already scanned", bg="orange", fg="white")
                    messagebox.showwarning("Already Scanned", 
                                         f"❌ INCORRECT SENSOR ID ❌\n\n"
                                         f"OCR Detected Pattern:\n'{ocr_result}'\n\n"
                                         f"Expected Lot: '{lot_number}'\n\n"
                                         f"ERROR: This sensor has already been\nscanned in this session.\n\n"
                                         f"ACTION: Scan the next sensor.")
                else:
                    # Check if sensor belongs to this lot but has defects
                    try:
                        conn_check = sqlite3.connect(db_path_tracking)
                        cur_check = conn_check.cursor()
                        cur_check.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
                        all_lot_sensors = [r[0] for r in cur_check.fetchall()]
                        
                        if ocr_result in all_lot_sensors:
                            # Sensor belongs to this lot but has defects
                            ocr_status_label.config(text=f"✗ DEFECTIVE SENSOR", bg="red", fg="white")
                            messagebox.showerror("DEFECTIVE SENSOR - CANNOT PROCEED", 
                                               f"❌ INCORRECT SENSOR ID ❌\n\n"
                                               f"OCR Detected Pattern:\n'{ocr_result}'\n\n"
                                               f"Expected Lot: '{lot_number}'\n\n"
                                               f"⚠ THIS SENSOR IS DEFECTIVE ⚠\n\n"
                                               f"ERROR: This sensor has defects from\nprevious processes and cannot proceed.\n\n"
                                               f"ACTION REQUIRED:\n"
                                               f"• Set this sensor aside\n"
                                               f"• DO NOT process this sensor\n"
                                               f"• Scan the next sensor")
                        else:
                            # Doesn't belong to this lot
                            ocr_status_label.config(text=f"✗ WRONG OUTPUT", bg="red", fg="white")
                            messagebox.showerror("Wrong Sensor ID - OCR Output Incorrect", 
                                               f"❌ INCORRECT SENSOR ID ❌\n\n"
                                               f"OCR Detected Pattern:\n'{ocr_result}'\n\n"
                                               f"Expected Lot: '{lot_number}'\n\n"
                                               f"ERROR: This sensor does NOT belong\nto lot '{lot_number}'.\n\n"
                                               f"ACTION: Verify the sensor or set it aside.")
                        conn_check.close()
                    except sqlite3.Error:
                        ocr_status_label.config(text=f"✗ WRONG OUTPUT", bg="red", fg="white")
                        messagebox.showerror("Wrong Sensor ID", 
                                           f"❌ INCORRECT SENSOR ID ❌\n\n"
                                           f"OCR Detected Pattern:\n'{ocr_result}'\n\n"
                                           f"Expected Lot: '{lot_number}'\n\n"
                                           f"ERROR: This sensor is not valid for this lot.")
            elif last_detected_pattern:  # Pattern was detected but not valid
                print(f"OCR detected pattern: '{last_detected_pattern}' but it's not valid for this lot")
                if last_detected_pattern in already_scanned:
                    ocr_status_label.config(text=f"✗ WRONG - Already scanned", bg="orange", fg="white")
                    messagebox.showwarning("Already Scanned", 
                                         f"❌ INCORRECT SENSOR ID ❌\n\n"
                                         f"OCR Detected Pattern:\n'{last_detected_pattern}'\n\n"
                                         f"Expected Lot: '{lot_number}'\n\n"
                                         f"ERROR: This sensor has already been\nscanned in this session.\n\n"
                                         f"ACTION: Scan the next sensor.")
                else:
                    try:
                        conn_check = sqlite3.connect(db_path_tracking)
                        cur_check = conn_check.cursor()
                        cur_check.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
                        all_lot_sensors = [r[0] for r in cur_check.fetchall()]
                        
                        if last_detected_pattern in all_lot_sensors:
                            ocr_status_label.config(text=f"✗ DEFECTIVE SENSOR", bg="red", fg="white")
                            messagebox.showerror("DEFECTIVE SENSOR - CANNOT PROCEED", 
                                               f"❌ INCORRECT SENSOR ID ❌\n\n"
                                               f"OCR Detected Pattern:\n'{last_detected_pattern}'\n\n"
                                               f"Expected Lot: '{lot_number}'\n\n"
                                               f"⚠ THIS SENSOR IS DEFECTIVE ⚠\n\n"
                                               f"ERROR: This sensor has defects from\nprevious processes and cannot proceed.\n\n"
                                               f"ACTION REQUIRED:\n"
                                               f"• Set this sensor aside\n"
                                               f"• DO NOT process this sensor\n"
                                               f"• Scan the next sensor")
                        else:
                            ocr_status_label.config(text=f"✗ WRONG OUTPUT", bg="red", fg="white")
                            messagebox.showerror("Wrong Sensor ID - OCR Output Incorrect", 
                                               f"❌ INCORRECT SENSOR ID ❌\n\n"
                                               f"OCR Detected Pattern:\n'{last_detected_pattern}'\n\n"
                                               f"Expected Lot: '{lot_number}'\n\n"
                                               f"ERROR: This sensor does NOT belong\nto lot '{lot_number}'.\n\n"
                                               f"ACTION: Verify the sensor or set it aside.")
                        conn_check.close()
                    except sqlite3.Error:
                        ocr_status_label.config(text=f"✗ WRONG OUTPUT", bg="red", fg="white")
                        messagebox.showerror("Wrong Sensor ID", 
                                           f"❌ INCORRECT SENSOR ID ❌\n\n"
                                           f"OCR Detected Pattern:\n'{last_detected_pattern}'\n\n"
                                           f"Expected Lot: '{lot_number}'\n\n"
                                           f"ERROR: This sensor is not valid for this lot.")
            else:  # OCR couldn't detect anything
                print("OCR could not detect any sensor ID pattern")
                ocr_status_label.config(text="✗ NO OCR OUTPUT", bg="red", fg="white")
                messagebox.showerror("No OCR Output Detected", 
                                   "❌ OCR could not detect any sensor ID.\n\n"
                                   "Possible issues:\n"
                                   "• Camera focus is blurry\n"
                                   "• Poor lighting conditions\n"
                                   "• Sensor ID not visible in frame\n"
                                   "• Text is too small or unclear\n\n"
                                   "Please adjust camera and try again.")
            
            sensor_id_textbox.delete("1.0", tk.END)
            sensor_id_textbox.config(bg="white")
            root.after(3000, lambda: ocr_status_label.config(text="", bg="lightblue"))
            return

        print(f"Final OCR result: '{ocr_result}'")
        ocr_status_label.config(text="✓ CORRECT OUTPUT", bg="green", fg="white")

        # Update the textbox with the OCR result
        sensor_id_textbox.delete("1.0", tk.END)
        sensor_id_textbox.insert(tk.END, ocr_result.strip())

        # Validate the sensor ID
        validate_sensor_id()
        
    except Exception as e:
        print(f"Error during OCR processing: {e}")
        import traceback
        traceback.print_exc()
        sensor_id_textbox.config(bg="red")
        ocr_status_label.config(text="✗ OCR ERROR", bg="red", fg="white")
        messagebox.showerror("OCR Error", f"An error occurred during OCR processing:\n\n{str(e)}")
        root.after(3000, lambda: ocr_status_label.config(text="", bg="lightblue"))
        
# ========== THUMBNAIL GALLERY (Right Side) ==========
# Thumbnail gallery frame
gallery_frame = tk.Frame(root, bg="#34495e", relief="ridge", borderwidth=2)
gallery_frame.place(x=1220, y=50, width=130, height=590)

# Gallery title
gallery_title = tk.Label(gallery_frame, text="Captured", font=("Arial", 9, "bold"), 
                         bg="#34495e", fg="white")
gallery_title.pack(pady=3)

# Scrollable canvas for thumbnails
thumbnail_canvas = tk.Canvas(gallery_frame, bg="#2c3e50", width=110, height=540, 
                             highlightthickness=0, bd=0)
thumbnail_canvas.pack(padx=5, pady=5)

# Initialize canvas images list
thumbnail_canvas.images = []
# ==================================================

# Camera feed label - adjusted for proper aspect ratio
video_label = Label(root, bg="black")
video_label.place(x=810, y=50, width=400, height=300)  # Changed height from 250 to 300 for 4:3 ratio
# Bind mouse events for wire region adjustment
video_label.bind("<Button-1>", on_wire_mouse_down)
video_label.bind("<B1-Motion>", on_wire_mouse_move)
video_label.bind("<ButtonRelease-1>", on_wire_mouse_up)

# Textbox for displaying the Sensor ID
sensor_id_label = Label(root, text="Sensor ID:", font=("Arial", 14), bg="lightblue", fg="black")
sensor_id_label.place(x=830, y=360)  # Moved down from 300 to 360

sensor_id_textbox = tk.Text(root, height=1, width=17, font=("Arial", 14))
sensor_id_textbox.place(x=935, y=360)  # Moved down from 300 to 360
sensor_id_textbox.tag_add("center", "1.0", "end")
# Bind Enter keys to validate the sensor ID (prevent newline insertion)
sensor_id_textbox.bind("<Return>", on_sensor_id_enter)
sensor_id_textbox.bind("<KP_Enter>", on_sensor_id_enter)

# OCR status label - shows if detected sensor ID is valid or not
ocr_status_label = Label(root, text="", font=("Arial", 10, "bold"), bg="lightblue", fg="black")
ocr_status_label.place(x=935, y=385)

def on_threshold_changed(value):
    """Called when user manually adjusts the threshold slider"""
    global last_successful_threshold
    # Reset the saved threshold when user manually adjusts
    last_successful_threshold = None
    print(f"Threshold manually adjusted to {value} - auto-threshold reset")

# Scale for adjusting the threshold level - moved to left side
threshold_label = Label(root, text="Threshold", font=("Arial", 10, "bold"), bg="lightblue", fg="black")
threshold_label.place(x=620, y=30)

threshold_scale = Scale(root, from_=110, to=200, orient=tk.HORIZONTAL, length=200, bg="#407ec9", fg="white", font=("Arial", 8), command=on_threshold_changed, resolution=5)
threshold_scale.set(120)
threshold_scale.place(x=550, y=50)

read_button = Button(root, text="READ", command=capture_image_and_process, font=("Arial", 12), bg="#00cc44", fg="white", padx=15, pady=1, relief='raised', borderwidth=3)
read_button.place(x=980, y=390)  # Moved down from 330 to 390

toggle_button = Button(root, text="Toggle View", command=toggle_view, font=("Arial", 10, "bold"), bg="#407ec9", fg="white", padx=10, pady=1, relief='raised', borderwidth=3)
toggle_button.place(x=600, y=100)

auto_detect_button = Button(root, text="Auto Detect Wires", command=manual_auto_detect, font=("Arial", 10, "bold"), bg="#ff8c00", fg="white", padx=10, pady=1, relief='raised', borderwidth=3)
auto_detect_button.place(x=900, y=440)

debug_button = Button(root, text="Debug View", command=toggle_debug_view, font=("Arial", 9, "bold"), bg="#9400d3", fg="white", padx=10, pady=1, relief='raised', borderwidth=3)
debug_button.place(x=1050, y=440)

# Color detection labels for each wire - improved layout
color_labels = []
color_label_frame = tk.Frame(root, bg="lightblue", relief="ridge", borderwidth=2)
color_label_frame.place(x=815, y=560)

for i in range(6):
    # Create a container frame for each wire
    wire_container = tk.Frame(color_label_frame, bg="lightblue")
    wire_container.grid(row=0, column=i, padx=3, pady=3)
    
    # Wire number label
    wire_label = tk.Label(wire_container, text=f"W{i+1}", font=("Arial", 8, "bold"), 
                         bg="#407ec9", fg="white", width=3, relief="raised", borderwidth=1)
    wire_label.pack()
    
    # Color detection label
    color_label = tk.Label(wire_container, text="---", font=("Arial", 9, "bold"), 
                          bg="gray", fg="white", width=7, height=1, relief="sunken", borderwidth=2)
    color_label.pack(pady=(2, 0))
    color_labels.append(color_label)

# Title Label
title_label = tk.Label(root, text="Cable Wire Soldering", font=("BiomeW04-Bold", 20, "bold"), bg="lightblue")
title_label.place(x=10, y=0)

# Printer status label - positioned below Operator field
printer_label = tk.Label(root, text="Printer:", font=("Arial", 9, "bold"), bg="lightblue", fg="black")
printer_label.place(x=320, y=140)

printer_combobox = ttk.Combobox(root, width=35, state="readonly", font=("Arial", 8))
printer_combobox.place(x=380, y=140)
printer_combobox.bind("<<ComboboxSelected>>", on_printer_selected)

# Specs Label
#specs_label = tk.Label(root, text='Specification:\n≤0.04', font=("Tahoma", 10, "bold"), bg="lightblue")
#specs_label.place(x=520, y=70)

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

# Helper: fetch lot condition from masterlist DB
def get_lot_condition(lot_number):
    """Return the lot condition string (e.g., "MP" or "Eval"). Defaults to "MP" if not found."""
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


# Helper: return sensor_ids allowed to proceed for the given process
def get_allowed_sensor_ids(lot_number, current_process):
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

# ---------- BMS Popup class ----------
class BMSPopup(tk.Toplevel):
    def __init__(self, master, lot_number, current_process, operator,
                 sensor_list, combobox_candidates, failed_sensor_list, blank_judgement_list, 
                 csv_rows_data, lot_condition="MP", total_lot_count=0, unscanned_sensors=None, passed_sensors=None):
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
        self.total_lot_count = total_lot_count if total_lot_count > 0 else len(sensor_list)
        self.unscanned_sensors = unscanned_sensors if unscanned_sensors else []
        self.passed_sensors = passed_sensors if passed_sensors else []

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

        # Sensor ID Combobox - include failed, blank, AND unscanned sensors
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
        # Quantity OUT = Total - (failed + blank + unscanned)
        sensors_that_passed = len(self.passed_sensors)
        
        self.quantity_in_entry.delete(0, tk.END)
        self.quantity_in_entry.insert(0, str(self.total_lot_count))
        self.quantity_out_entry.delete(0, tk.END)
        self.quantity_out_entry.insert(0, str(sensors_that_passed))

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
        # 1. Failed sensors (scanned and failed)
        # 2. Blank judgement sensors (scanned but no judgement)
        # 3. Unscanned sensors (not scanned at all in this session)
        sensors_needing_defects_count = len(self.failed_sensor_list) + len(self.blank_judgement_list) + len(self.unscanned_sensors)
        
        # Count how many defect entries are in the table (regardless of sensor ID)
        defect_entries_count = len([row for row in self.table.get_children() if self.table.item(row)["values"][1]])
        
        # Check if we have enough defect entries
        if defect_entries_count < sensors_needing_defects_count:
            messagebox.showerror(
                "Missing Defects/Remarks",
                f"Total sensors needing defects: {sensors_needing_defects_count}\n"
                f"  - Failed: {len(self.failed_sensor_list)}\n"
                f"  - No judgement: {len(self.blank_judgement_list)}\n"
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
    
        try:
            # Update lot_masterlist with wire color data
            if self.csv_rows_data:
                conn_master = sqlite3.connect(db_path_masterlist)
                cursor_master = conn_master.cursor()
                for row in self.csv_rows_data:
                    sensor_id = row[0]
                    w1, w2, w3, w4, w5, w6 = row[1], row[2], row[3], row[4], row[5], row[6]
                    try:
                        cursor_master.execute("""
                            UPDATE lot_masterlist
                            SET Wire1_Color = ?, Wire2_Color = ?, Wire3_Color = ?, Wire4_Color = ?, Wire5_Color = ?, Wire6_Color = ?
                            WHERE sensor_id = ?
                        """, (w1, w2, w3, w4, w5, w6, sensor_id))
                    except sqlite3.OperationalError:
                        pass
                conn_master.commit()
                conn_master.close()
    
            # Update lot_tracking
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
            
            # Assign generic defects to sensors that need them (failed, blank, unscanned)
            sensors_needing_generic_defects = []
            for sid in all_sensors_for_lot:
                if sid in self.failed_sensor_list or sid in self.blank_judgement_list or sid in self.unscanned_sensors:
                    if sid not in defects_dict:  # Only if not already assigned
                        sensors_needing_generic_defects.append(sid)
            
            # Assign generic defects to sensors
            for i, sid in enumerate(sensors_needing_generic_defects):
                if i < len(generic_defects):
                    defects_dict[sid] = generic_defects[i]
            
            # Update ALL sensors in the lot (only if MP and columns exist)
            if columns and len(columns) >= 6 and self.lot_condition.upper() == "MP":
                for sid in all_sensors_for_lot:
                    if sid in defects_dict:
                        # Sensor has defect/remark entry
                        defect, remarks = defects_dict[sid]
                        cursor.execute(f"""
                            UPDATE lot_tracking
                            SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, {columns[3]}=?, {columns[4]}=?, {columns[5]}=?
                            WHERE lot_number=? AND sensor_id=?
                        """, (quantity_in, quantity_out, defect, remarks, proc_datetime, operator, lot_number, sid))
                    elif sid in self.passed_sensors:
                        # Sensor passed - no defects
                        cursor.execute(f"""
                            UPDATE lot_tracking
                            SET {columns[0]}=?, {columns[1]}=?, {columns[2]}='', {columns[3]}='', {columns[4]}=?, {columns[5]}=?
                            WHERE lot_number=? AND sensor_id=?
                        """, (quantity_in, quantity_out, proc_datetime, operator, lot_number, sid))
                
                # Advance current_process
                try:
                    next_proc = process_flow[process_flow.index(current_process) + 1]
                    cursor.execute("UPDATE lot_tracking SET current_process=? WHERE lot_number=?", (next_proc, lot_number))
                except Exception:
                    pass

            conn.commit()
            conn.close()

            messagebox.showinfo("Success", "Data saved successfully!")
            self.destroy()
            # Clear main window after successful save
            delete_action()

        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"An error occurred: {e}")

# Buttons for Delete and Save
def delete_action():
    global last_successful_threshold, current_lot_number, thumbnail_data
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
    # Reset the threshold memory when clearing data
    last_successful_threshold = None
    print("✓ Data cleared - threshold auto-adjustment re-enabled for next lot")
    
    # Clear thumbnail gallery and reset lot tracking
    clear_thumbnail_gallery()
    current_lot_number = None
    thumbnail_data = []

def save_action():
    global thumbnail_data, current_lot_number
    try:
        # Check for unfilled entries
        if not entries["Operator:"].get():
            messagebox.showerror("Error", "Operator field must be filled.")
            return
        
        lot_number = entries["Lot Number:"].get().strip()
        if not lot_number:
            messagebox.showerror("Error", "Lot Number field must be filled.")
            return

        csv_rows_data = []
        failed_sensor_list_local = []
        blank_judgement_list_local = []
        combobox_candidates_local = []
        sensor_list_local = []
        passed_sensor_list_local = []

        for row in range(20):
            sensor_id = data_entry[row][0].get().strip()
            if sensor_id:
                sensor_list_local.append(sensor_id)
                w1 = data_entry[row][1].get().strip()
                w2 = data_entry[row][2].get().strip()
                w3 = data_entry[row][3].get().strip()
                w4 = data_entry[row][4].get().strip()
                w5 = data_entry[row][5].get().strip()
                w6 = data_entry[row][6].get().strip()
                judgement = judgement_labels[row].cget("text").strip()

                if not all([w1, w2, w3, w4, w5, w6]):
                    messagebox.showerror("Error", "All wire color fields must be filled for each Sensor ID.")
                    return

                csv_rows_data.append([sensor_id, w1, w2, w3, w4, w5, w6, judgement])

                # Collect failed, blank, and passed lists
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
                elif judgement == "Passed":
                    if sensor_id not in passed_sensor_list_local:
                        passed_sensor_list_local.append(sensor_id)

        # Allow saving even if no sensors were scanned
        # if not sensor_list_local:
        #     messagebox.showwarning("Warning", "No Sensor IDs entered.")
        #     return

        current_process = entries["Current Process:"].get().strip()
        operator = entries["Operator:"].get().strip()

        # Get TOTAL sensors in the lot from database
        try:
            conn = sqlite3.connect(db_path_tracking)
            cursor = conn.cursor()
            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number = ?", (lot_number,))
            all_lot_sensors = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            if not all_lot_sensors:
                messagebox.showerror("Error", f"No sensors found for lot number {lot_number}")
                return
            
            total_lot_count = len(all_lot_sensors)
            
            # Find sensors that were NOT scanned in this session
            scanned_sensors = set(sensor_list_local)
            unscanned_sensors = [sid for sid in all_lot_sensors if sid not in scanned_sensors]
            
            print(f"Total sensors in lot: {total_lot_count}")
            print(f"Scanned in this session: {len(scanned_sensors)}")
            print(f"Not scanned: {len(unscanned_sensors)}")
            
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Could not fetch lot sensors: {e}")
            return

        # Fetch lot condition
        lot_condition = get_lot_condition(lot_number)

        # If Eval, don't populate combobox with failed/blank sensors
        if str(lot_condition).upper() == "EVAL":
            combobox_candidates_local = []

        # Open the BMS Popup with total lot count and unscanned sensors
        popup = BMSPopup(root, lot_number, current_process, operator,
                         sensor_list_local, combobox_candidates_local,
                         failed_sensor_list_local, blank_judgement_list_local, 
                         csv_rows_data, lot_condition, 
                         total_lot_count, unscanned_sensors, passed_sensor_list_local)
        popup.grab_set()
        
        # Wait for popup to close, then clear thumbnails
        popup.wait_window()
        
        # After saving, clear thumbnail gallery for next lot
        clear_thumbnail_gallery()
        current_lot_number = None
        thumbnail_data = []
        print("✓ Data saved - thumbnail gallery cleared for next lot")
        
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

delete_button = tk.Button(root, text="Clear Data", font=("Tahoma", 12, "bold"), padx=10, pady=1, bg="yellow", command=delete_action, relief='raised', borderwidth=3)
delete_button.place(x=350, y=50)
save_button = tk.Button(root, text="SAVE", font=("Tahoma", 12, "bold"), padx=32, pady=1, bg="orange", command=save_action, relief='raised', borderwidth=3)
save_button.place(x=350, y=100)

# Table headers
headers = ["No.", "Sensor ID", "Wire 1", "Wire 2", "Wire 3", "Wire 4", 
           "Wire 5", "Wire 6", "Judgement"]
header_positions = {
    "No.": (13, 165),
    "Sensor ID": (80, 165),
    "Wire 1": (200, 165),
    "Wire 2": (290, 165),
    "Wire 3": (380, 165),
    "Wire 4": (470, 165),
    "Wire 5": (560, 165),
    "Wire 6": (650, 165),
    "Judgement": (730, 165),
}
for header in headers:
    label = tk.Label(root, text=header, font=("Arial", 7, "bold"), bg="lightblue", relief="ridge")
    label.place(x=header_positions[header][0], y=header_positions[header][1])

# Table rows for data entry
data_entry = []
judgement_labels = []
vcmd_text = (root.register(validate_text_input), '%P')

for row in range(20):
    row_entries = []
    # Add numbering label
    number_label = tk.Label(root, text=str(row + 1), width=3, bg="lightblue", relief="ridge")
    number_label.place(x=10, y=185 + row*23)
    for col in range(7):
        if col == 0:
            entry = tk.Entry(root, width=20, justify='center')
            entry.place(x=45 + col*115, y=185 + row*23)
            entry.config(state="readonly")  # Set Sensor ID column to readonly
        else:
            entry = tk.Entry(root, width=12, validate="key", validatecommand=vcmd_text, justify='center')
            entry.place(x=180 + (col-1)*90, y=185 + row*23)
            # Bind Enter key to move focus to the next cell and judge the row
            entry.bind("<Return>", lambda event, r=row, c=col: navigate_on_enter(event, r, c))
        row_entries.append(entry)
    data_entry.append(row_entries)

    # Add judgement label
    judgement_label = tk.Label(root, text="", width=10, bg="lightblue", relief="ridge")
    judgement_label.place(x=720, y=185 + row*23)
    judgement_labels.append(judgement_label)
    
start_camera()
# start_color_camera() is no longer needed - color detection integrated into show_frame()

# Auto-detect printer on startup
root.after(1000, auto_detect_printer)

def on_closing():
    global cap
    if cap and cap.isOpened():
        cap.release()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

# Start the application
root.mainloop() 