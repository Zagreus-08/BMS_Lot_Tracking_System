import typing as _typing

# --- Typing Compatibility ---
_needed = ("TypedDict", "Literal", "Final", "Protocol", "runtime_checkable", "get_origin", "get_args")
try:
    for name in _needed:
        getattr(_typing, name)
except Exception:
    try:
        import typing_extensions as _te 
        for name in _needed:
            if not hasattr(_typing, name) and hasattr(_te, name):
                setattr(_typing, name, getattr(_te, name))
    except Exception:
        if not hasattr(_typing, "TypedDict"):
            class TypedDict(dict): pass
            _typing.TypedDict = TypedDict

import tkinter as tk
from datetime import datetime
from tkinter import messagebox
import os
from PIL import Image, ImageTk, ImageDraw, ImageFont
from tkinter import Toplevel
import sqlite3
import io
import barcode 
from barcode.writer import ImageWriter
from tkinter import filedialog
import pandas as pd
import win32print
import win32con
import win32ui
from PIL import ImageWin
import math

# Database paths
SHIPMENT_DB_FILE = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\shipment_masterlist.db"
LOT_MASTER_DB_FILE = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"
LOT_TRACKING_DB_FILE = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_tracking.db"
STORAGE_DB_FILE = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\sensor_storage.db"

def setup_database():
    conn = sqlite3.connect(SHIPMENT_DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shipment_masterlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number TEXT NOT NULL, lot_number TEXT NOT NULL,
            sensor_id TEXT NOT NULL, customer_name TEXT NOT NULL,
            customer_part_no TEXT NOT NULL, tdk_item_name TEXT NOT NULL,
            shipment_date TEXT NOT NULL, created_by TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    
    # Update storage database to add status column if it doesn't exist
    conn_storage = sqlite3.connect(STORAGE_DB_FILE)
    cursor_storage = conn_storage.cursor()
    try:
        cursor_storage.execute("ALTER TABLE storage_logs ADD COLUMN status TEXT DEFAULT 'in_storage'")
        conn_storage.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn_storage.close()

setup_database()

def update_datetime(date_name_text):
    if date_name_text.winfo_exists():
        current_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        date_name_text.config(state='normal')
        date_name_text.delete('1.0', tk.END)
        date_name_text.insert(tk.END, current_time)
        date_name_text.config(state='disabled')
        date_name_text.after(1000, update_datetime, date_name_text)


def clear_fields():
    global verified_sensors, available_sensors
    widgets = [po_number_text, customer_text, part_no_text, item_name_text, quantity_text, lot_no_text, invoice_no_text]
    for w in widgets:
        w.config(state='normal'); w.delete(0, tk.END); w.config(state='disabled')
    sensor_id_text.config(state='normal'); sensor_id_text.delete('1.0', tk.END); sensor_id_text.config(state='disabled')
    scan_entry.config(state='normal'); scan_entry.delete(0, tk.END); scan_entry.config(state='disabled')
    verified_sensors.clear()
    available_sensors.clear()
    status_label.config(text="Verified: 0 / 0")
    create_button.config(state='disabled')
    storage_location_label.config(text="Storage Location: ---")  # Reset storage location label


def validate_fields():
    fields = [po_number_text, customer_text, part_no_text, item_name_text, 
              quantity_text, lot_no_text, box_count_text, gross_wt_text, 
              net_wt_text, created_name_text]
    for field in fields:
        if not field.get().strip(): return False
    if not sensor_id_text.get('1.0', tk.END).strip(): return False
    return True


def fetch_sensors_from_storage(product_desc, required_qty):
    """Fetch only the required quantity of sensors from storage (oldest first), excluding shipped ones"""
    global available_sensors
    try:
        conn = sqlite3.connect(STORAGE_DB_FILE)
        cursor = conn.cursor()
        # Only fetch sensors that are 'in_storage' status, ordered by timestamp (oldest first)
        cursor.execute("""
            SELECT sensor_id, location FROM storage_logs 
            WHERE product_desc = ? AND (status IS NULL OR status = 'in_storage')
            ORDER BY timestamp ASC 
            LIMIT ?
        """, (product_desc, required_qty))
        results = cursor.fetchall()
        conn.close()

        # Store tuples (sensor_id, location) so UI can show location
        available_sensors = [(row[0], row[1] if len(row) > 1 else "Unknown") for row in results]
        return available_sensors
    except Exception as e:
        messagebox.showerror("Database Error", f"Could not fetch sensors from storage: {e}")
        return []

def open_image_and_print_option(shipment_file_path, s_ids_to_process):
    # Create a new window to display the image
    image_window = Toplevel()
    image_window.title("Generated Traveller")

    # Load the image
    img = Image.open(shipment_file_path)

    # Adjust the DPI for the SATO CL4NX Plus
    dpi = 305
    width_mm = 165
    height_mm = 102
    width_px = int(width_mm * dpi / 25.4)
    height_px = int(height_mm * dpi / 25.4)
    img = img.resize((width_px, height_px), Image.ANTIALIAS)

    # Create a smaller version for display
    display_width = 800  # Adjust this value as needed
    display_height = int(display_width * height_px / width_px)
    img_display = img.resize((display_width, display_height), Image.ANTIALIAS)

    img_tk = ImageTk.PhotoImage(img_display)

    # Create a label to show the image
    image_label = tk.Label(image_window, image=img_tk)
    image_label.image = img_tk  # Keep a reference to avoid garbage collection
    image_label.pack(pady=10)

    # Add a button to print the image
    def print_image():
        try:
            # Directly target the SATO CL4NX Plus printer
            printer_name = "SATO CL4NX Plus 305dpi"
            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)
            
            # Start the document and page
            hDC.StartDoc(shipment_file_path)
            hDC.StartPage()

            # Calculate the printable area
            printable_area = hDC.GetDeviceCaps(win32con.HORZRES), hDC.GetDeviceCaps(win32con.VERTRES)
            
            # Calculate the scale factor to fit the image within the printable area
            scale_factor = min(printable_area[0] / width_px, printable_area[1] / height_px)

            # Calculate the position to center the image
            x_offset = int((printable_area[0] - width_px * scale_factor) / 2)
            y_offset = int((printable_area[1] - height_px * scale_factor) / 2)

            # Adjust the y_offset to move the image higher
            y_offset -= 50  # Adjust this value to move the image higher

            # Draw the image centered
            dib = ImageWin.Dib(img)
            dib.draw(hDC.GetHandleOutput(), (x_offset, y_offset, x_offset + int(width_px * scale_factor), y_offset + int(height_px * scale_factor)))

            # End the page and document
            hDC.EndPage()
            try:
                hDC.EndDoc()
            except:
                pass  # Ignore EndDoc error - print still works
            hDC.DeleteDC()
            
            # MARK AS SHIPPED ONLY AFTER SUCCESSFUL PRINT
            conn_storage = sqlite3.connect(STORAGE_DB_FILE)
            cursor_storage = conn_storage.cursor()
            for sid in s_ids_to_process:
                cursor_storage.execute("UPDATE storage_logs SET status = 'shipped' WHERE sensor_id = ?", (sid,))
            conn_storage.commit()
            conn_storage.close()

            messagebox.showinfo("Success", f"Label printed successfully!\n{len(s_ids_to_process)} sensors marked as shipped.")
            image_window.destroy()
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print: {e}")
    
    # Create a frame for buttons
    button_frame = tk.Frame(image_window)
    button_frame.pack(pady=10)
    
    # Add Print button
    print_button = tk.Button(button_frame, text="Print Label", font=("Arial", 12, "bold"), 
                            bg="#32CD32", fg="white", command=print_image, 
                            width=15, height=2)
    print_button.pack(side=tk.LEFT, padx=10)
    
    
def new_entry():
    global verified_sensors, invoice_number
    file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
    if file_path:
        filename = os.path.splitext(os.path.basename(file_path))[0]
        try:
            df = pd.read_excel(file_path, header=None)  # Read without header to access by position
            def update_entry(widget, value):
                widget.config(state='normal'); widget.delete(0, tk.END); widget.insert(0, value); widget.config(state='disabled')

            # Read from row 1 (index 0) for main data
            df_data = pd.read_excel(file_path, header=0)
            
            update_entry(po_number_text, filename)
            mat = df_data['Material'].iloc[0] if 'Material' in df_data.columns else ""
            cust = df_data['Sold To Desc.'].iloc[0] if 'Sold To Desc.' in df_data.columns else ""
            desc = str(df_data['Description'].iloc[0]) if 'Description' in df_data.columns else ""
            qty = int(df_data['PO Qty'].iloc[0]) if 'PO Qty' in df_data.columns else 0
            lot = df_data['Delivery Order'].iloc[0] if 'Delivery Order' in df_data.columns else ""
            
            # Get invoice number from column Q (index 16), row 2 (index 1)
            invoice_number = str(df.iloc[1, 16]) if len(df) > 1 and len(df.columns) > 16 else ""

            update_entry(part_no_text, mat)
            update_entry(customer_text, cust)
            update_entry(item_name_text, desc)
            update_entry(quantity_text, qty)
            update_entry(lot_no_text, lot)
            update_entry(invoice_no_text, invoice_number)

            # Calculate total boxes needed (25 sensors per box)
            if qty > 0:
                import math
                total_boxes_needed = math.ceil(qty / 25)
                out_of_text.config(state='normal')
                out_of_text.delete(0, tk.END)
                out_of_text.insert(0, f"{total_boxes_needed:03}")
                out_of_text.config(state='disabled')

            if desc:
                # FETCH ONLY THE REQUIRED QUANTITY FROM STORAGE (oldest first)
                all_found_sensors = fetch_sensors_from_storage(desc, qty)
                found_count = len(all_found_sensors)
                # Show storage location (all sensors share same product desc)
                try:
                    if all_found_sensors:
                        first = all_found_sensors[0]
                        loc = first[1] if isinstance(first, (list, tuple)) and len(first) > 1 else "Unknown"
                        storage_location_label.config(text=f"Storage Location: {loc}")
                    else:
                        storage_location_label.config(text="Storage Location: ---")
                except Exception:
                    pass
                
                # Reset verification
                verified_sensors.clear()
                
                # Update display
                update_sensor_display()
                
                # Update status
                status_label.config(text=f"Verified: 0 / {qty}")

                # VALIDATE IF WE HAVE ENOUGH FOR THE PO
                if found_count >= qty and qty > 0:
                    scan_entry.config(state='normal')
                    scan_entry.focus()
                    messagebox.showinfo("Ready to Verify", f"Found {found_count} sensors in storage (oldest first).\nPlease scan each sensor to verify.")
                else:
                    create_button.config(state='disabled')
                    scan_entry.config(state='disabled')
                    messagebox.showwarning("Insufficient Stock", f"Need {qty} sensors, but only {found_count} available in storage for this Item Name.")

        except Exception as e:
            messagebox.showerror("Error", f"Excel read error: {e}")

def create_shipment_template(path):
    dpi = 600
    w, h = int(165/25.4*dpi), int(102/25.4*dpi)
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    line_color = "black"
    line_color2 = "white"
    
    try: 
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 85)
    except: 
        font = ImageFont.load_default()
    
    # Complete cell positions from original
    cells = {
        "(3S):": (118, 141, 1974, 517),
        "(6S)C/NO:": (118, 507, 1974, 907),
        "   BOX COUNT": (1193, 507, 1974, 907),
        " ": (1193, 758, 1974, 907),
        "                     SHIPPING MARK": (118, 897, 1974, 1034),
        "": (118, 1024, 1974, 1786),
        "   ": (118, 1776, 1974, 2390),
        "CUSTOMER:": (1964, 141, 3774, 306),
        "CUST PART NO(P):": (1964, 296, 3774, 541),
        "TDK ITEM CODE(6P):": (1964, 531, 3774, 776),
        "P/O NO(K):": (1964, 766, 3774, 1034),
        "INVOICE NO(7K):": (1964, 1024, 3774, 1269),
        "LOT NO(1T):": (1964, 1259, 2998, 1504),
        "QTY(Q):": (1964, 1494, 3774, 1739),
        "TDK ITEM NAME(1P):": (1964, 1729, 3774, 2092)
    }
    
    for label, (x1, y1, x2, y2) in cells.items():
        draw.rectangle([x1, y1, x2, y2], outline=line_color, width=10)
        draw.text((x1 + 25, y1 + 17), label, fill="black", font=font)
    
    draw.rectangle([118,141,3774,2390], outline=line_color2, width=10)
    img.save(path, dpi=(dpi, dpi))

def generate_and_resize_barcode(data, size):
    from barcode.codex import Code128
    barcode_instance = Code128(data, writer=ImageWriter())
    barcode_io = io.BytesIO()
    barcode_instance.write(barcode_io, options={"write_text": False, 'quiet_zone': 0})
    barcode_io.seek(0)
    return Image.open(barcode_io).resize(size, Image.ANTIALIAS)

def update_sensor_display():
    """Update the sensor list display with color coding for verified sensors (shows location)."""
    sensor_id_text.config(state='normal')
    sensor_id_text.delete('1.0', tk.END)

    sensor_id_text.tag_configure("verified", foreground="green", font=("Arial", 10, "bold"))
    sensor_id_text.tag_configure("unverified", foreground="black")

    for entry in available_sensors:
        # entry may be (sensor_id, location) or just sensor_id

        if isinstance(entry, (list, tuple)):
            sid = entry[0]
        else:
            sid = entry

        if sid in verified_sensors:
            sensor_id_text.insert(tk.END, f"✓ {sid}\n", "verified")
        else:
            sensor_id_text.insert(tk.END, f"  {sid}\n", "unverified")

    sensor_id_text.config(state='disabled')


def verify_sensor_scan(event=None):
    """Handle sensor verification via barcode scan (works with available_sensors as tuples).
    """
    global verified_sensors
    scanned_id = scan_entry.get().strip()

    if not scanned_id:
        return

    # Find the sensor in available_sensors
    found_entry = None
    for entry in available_sensors:
        sid = entry[0] if isinstance(entry, (list, tuple)) else entry
        if sid == scanned_id:
            found_entry = entry
            break

    if not found_entry:
        messagebox.showwarning("Invalid Sensor", f"Sensor {scanned_id} is not in the available list for this shipment!")
        scan_entry.delete(0, tk.END)
        return

    if scanned_id in verified_sensors:
        messagebox.showinfo("Already Verified", f"Sensor {scanned_id} has already been verified.")
        scan_entry.delete(0, tk.END)
        return

    verified_sensors.add(scanned_id)
    update_sensor_display()

    # Update status label and enable create when enough verified
    required_qty = int(quantity_text.get().strip()) if quantity_text.get().strip().isdigit() else 0
    verified_count = len(verified_sensors)
    status_label.config(text=f"Verified: {verified_count} / {required_qty}")

    if verified_count >= required_qty and required_qty > 0:
        create_button.config(state='normal')
        messagebox.showinfo("Ready", f"All {required_qty} sensors verified! You can now create the shipment record.")

    scan_entry.delete(0, tk.END)
    scan_entry.focus()

def create_lot_masterlist():
    if not validate_fields():
        messagebox.showwarning("Input Required", "Please fill in all fields.")
        return
    
    po = po_number_text.get().strip()
    qty_val = int(quantity_text.get().strip())
    lot = lot_no_text.get().strip()
    cust = customer_text.get().strip()
    part = part_no_text.get().strip()
    item = item_name_text.get().strip()
    box = box_count_text.get().strip()
    total_box = out_of_text.get().strip()
    gross_wt = gross_wt_text.get().strip()
    net_wt = net_wt_text.get().strip()
    created_by = created_name_text.get().strip()
    
    # Check if we have enough verified sensors
    if len(verified_sensors) < qty_val:
        messagebox.showerror("Insufficient Verification", f"Only {len(verified_sensors)} sensors verified, but {qty_val} required!")
        return
    
    s_ids_to_process = list(verified_sensors)[:qty_val]
    now_str = datetime.now().strftime("%m/%d/%Y %I:%M %p")
    shipment_date = datetime.now()

    try:
        dest_folder = r"\\phlsvr08\BMS Data\Lot ID's\Shipment Label"
        os.makedirs(dest_folder, exist_ok=True)
        img_path = os.path.join(dest_folder, f"{po}.png")

        # Split verified sensors into boxes of up to 90 sensors each
        total_needed = qty_val
        s_ids = list(verified_sensors)[:total_needed]
        box_chunks = [s_ids[i:i+25] for i in range(0, len(s_ids), 25)]
        total_boxes = len(box_chunks) if box_chunks else 1

        try:
            for box_index, chunk in enumerate(box_chunks, start=1):
                # Prepare box-specific identifiers
                box_str = f"{box_index:03}"
                total_box_str = f"{total_boxes:03}"
                box_qty = len(chunk)

                img_path_box = os.path.join(dest_folder, f"{po}_box{box_index}.png")
                create_shipment_template(img_path_box)
                img = Image.open(img_path_box)
                draw = ImageDraw.Draw(img)

                try:
                    font = ImageFont.truetype(r"C:\Windows\Fonts\arialnb.ttf", 100)
                except:
                    try:
                        font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 100)
                    except:
                        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 100)

                # Text positions from original working code
                text_data = {
                    "(3S)": (365, 150),
                    "(6S)C/NO": (658, 516),
                    "BOX COUNT": (1387, 621),
                    "SHIPPING MARK1": (130, 1050),
                    "SHIPPING MARK2": (130, 1167),
                    "SHIPPING MARK3": (130, 1284),
                    "SHIPPING MARK4": (130, 1401),
                    "SHIPPING MARK5": (130, 1518),
                    "SHIPPING MARK6": (130, 1635),
                    "CUSTOMER": (2530, 150),
                    "CUST PART NO(P)": (2800, 305),
                    "TDK ITEM CODE(6P)": (2880, 540),
                    "P/O NO(K)": (2500, 775),
                    "INVOICE NO(7K)": (2700, 1033),
                    "LOT NO(1T)": (2520, 1268),
                    "DATE": (3035, 1325),
                    "QTY(Q)": (2350, 1503),
                    "TDK ITEM NAME(1P)": (2850, 1738),
                    "ITEM NAME": (2375, 1970),
                    "Gross Weight": (1984, 2090),
                    "Net Weight": (1984, 2176),
                    "Company Name": (1984, 2260)
                }

                # Use box-specific values when drawing
                draw.text(text_data["(3S)"], f"TPH+{lot}{box_str}{total_box_str}000000{box_qty}", fill="black", font=font)
                draw.text(text_data["(6S)C/NO"], box_str, fill="black", font=font)
                draw.text(text_data["BOX COUNT"], f"{box_str}/{total_box_str}", fill="black", font=font)
                draw.text(text_data["SHIPPING MARK1"], cust, fill="black", font=font)
                draw.text(text_data["SHIPPING MARK2"], po, fill="black", font=font)
                draw.text(text_data["SHIPPING MARK3"], "JAPAN", fill="black", font=font)
                draw.text(text_data["SHIPPING MARK4"], f"C/NO:{box_str}", fill="black", font=font)
                draw.text(text_data["SHIPPING MARK5"], "MADE IN PHILIPPINES", fill="black", font=font)
                draw.text(text_data["SHIPPING MARK6"], lot, fill="black", font=font)
                draw.text(text_data["CUSTOMER"], cust, fill="black", font=font)
                draw.text(text_data["CUST PART NO(P)"], part, fill="black", font=font)
                draw.text(text_data["TDK ITEM CODE(6P)"], f"{part}PHL", fill="black", font=font)
                draw.text(text_data["P/O NO(K)"], po, fill="black", font=font)   
                draw.text(text_data["INVOICE NO(7K)"], invoice_number, fill="black", font=font)
                draw.text(text_data["DATE"], f"DATE:{shipment_date.strftime('%b %d, %Y')}", fill="black", font=ImageFont.truetype(r"C:\Windows\Fonts\arialn.ttf", 90))
                draw.text(text_data["LOT NO(1T)"], lot, fill="black", font=font)
                draw.text(text_data["QTY(Q)"], str(box_qty), fill="black", font=font)
                draw.text(text_data["TDK ITEM NAME(1P)"], item, fill="black", font=ImageFont.truetype(r"C:\Windows\Fonts\arialnb.ttf", 85))
                draw.text(text_data["ITEM NAME"], f"({item})", fill="black", font=ImageFont.truetype(r"C:\Windows\Fonts\arialnb.ttf", 85))
                draw.text(text_data["Gross Weight"], f"GW:  {gross_wt}Kg", fill="black", font=ImageFont.truetype(r"C:\Windows\Fonts\arialn.ttf", 70))
                draw.text(text_data["Net Weight"], f"NW:  {net_wt}Kg", fill="black", font=ImageFont.truetype(r"C:\Windows\Fonts\arialn.ttf", 70))
                draw.text(text_data["Company Name"], "TDK PHILIPPINES", fill="black", font=font)

                # Barcodes from original working code (use box-specific qty and identifiers)
                barcode_details = {
                    "S_data": {"data": f"3STPH+{po}{box_str}{total_box_str}000000{box_qty}", "position": (143, 260), "size": (1586, 208)},
                    "C_NO_data": {"data": f"6S{box_str}", "position": (143, 636), "size": (650, 208)},
                    "cust_part_no_data": {"data": f"P{part}", "position": (2050, 410), "size": (858, 104)},
                    "item_code_data": {"data": f"6P{part}PHL", "position": (2050, 645), "size": (1222, 104)},
                    "po_number_data": {"data": f"K{po}", "position": (2050, 880), "size": (728, 104)},
                    "invoice_number_data": {"data": f"7K{invoice_number}", "position": (2015, 1135), "size": (806, 104)},
                    "lot_number_data": {"data": f"1T{lot}", "position": (2015, 1370), "size": (806, 104)},
                    "quantity_data": {"data": f"Q{box_qty}", "position": (2050, 1605), "size": (290, 104)},
                    "tdk_item_data": {"data": f"1P{item}", "position": (2050, 1860), "size": (1638, 104)}
                }

                for key, details in barcode_details.items():
                    barcode_image = generate_and_resize_barcode(details["data"], details["size"]) 
                    img.paste(barcode_image, details["position"])

                dpi = 600
                img.save(img_path_box, dpi=(dpi, dpi))

                # Save to shipment database for this box
                conn_shipment = sqlite3.connect(SHIPMENT_DB_FILE)
                for sid in chunk:
                    conn_shipment.execute("INSERT INTO shipment_masterlist (po_number, lot_number, sensor_id, customer_name, customer_part_no, tdk_item_name, shipment_date, created_by) VALUES (?,?,?,?,?,?,?,?)", 
                                 (po, lot, sid, cust, part, item, now_str, created_by))
                conn_shipment.commit()
                conn_shipment.close()

                # Inform user and open print dialog (open_image_and_print_option will mark shipped on successful print)
                messagebox.showinfo("Success", f"Shipment record created for box {box_index}/{total_boxes}.\nPlease print the label to mark sensors as shipped.")
                open_image_and_print_option(img_path_box, chunk)
        except Exception as e_box:
            messagebox.showerror("Error", f"Box creation error: {e_box}")
        # end for box chunks

    except Exception as e:
        messagebox.showerror("Error", f"Failed to create shipment: {e}")

def create_gui():
    global po_number_text, customer_text, part_no_text, item_name_text, quantity_text, lot_no_text, invoice_no_text, shipment_date_text
    global box_count_text, out_of_text, gross_wt_text, net_wt_text, created_name_text, sensor_id_text, clear_button, create_button, storage_location_label
    global scan_entry, verified_sensors, available_sensors, invoice_number
    
    verified_sensors = set()  # Track verified sensor IDs
    available_sensors = []    # Store available sensors from storage
    invoice_number = ""       # Store invoice number from Excel
    
    root = tk.Tk()
    root.title("BMS Shipment System")
    root.geometry("850x580") 
    root.configure(bg='#3366cc')

    tk.Label(root, text="BMS Shipment System", font=("Arial", 18, "bold"), bg="#3366cc", fg="orange").place(x=10, y=5)

    y, gap = 50, 28
    labels = ["PO Number:", "Customer:", "Customer Part No:", "TDK Item Name:", "Sensor Quantity:", "Lot Number:", "Invoice Number:", "Date Created:"]
    for i, txt in enumerate(labels):
        tk.Label(root, text=txt, bg='#3366cc', fg='white', font=('Arial', 9, 'bold')).place(x=10, y=y + (i*gap))

    po_number_text = tk.Entry(root, width=29, state='disabled'); po_number_text.place(x=180, y=y)
    customer_text = tk.Entry(root, width=29, state='disabled'); customer_text.place(x=180, y=y + gap)
    part_no_text = tk.Entry(root, width=29, state='disabled'); part_no_text.place(x=180, y=y + gap*2)
    item_name_text = tk.Entry(root, width=29, state='disabled'); item_name_text.place(x=180, y=y + gap*3)
    quantity_text = tk.Entry(root, width=29, state='disabled'); quantity_text.place(x=180, y=y + gap*4)
    lot_no_text = tk.Entry(root, width=29, state='disabled'); lot_no_text.place(x=180, y=y + gap*5)
    invoice_no_text = tk.Entry(root, width=29, state='disabled'); invoice_no_text.place(x=180, y=y + gap*6)
    shipment_date_text = tk.Text(root, width=22, height=1, state='disabled'); shipment_date_text.place(x=180, y=y + gap*7)

    y_box = y + gap*8
    tk.Label(root, text="Box Count / Total:", bg='#3366cc', fg='white', font=('Arial', 9, 'bold')).place(x=10, y=y_box)
    box_count_text = tk.Entry(root, width=10); box_count_text.place(x=180, y=y_box); box_count_text.insert(0, "001")
    tk.Label(root, text="/", bg='#3366cc', fg='white', font=('Arial', 10, 'bold')).place(x=270, y=y_box)
    out_of_text = tk.Entry(root, width=10, state='disabled'); out_of_text.place(x=295, y=y_box); out_of_text.insert(0, "001")

    gross_wt_text = tk.Entry(root, width=20); gross_wt_text.place(x=180, y=y_box + gap); gross_wt_text.insert(0, "20")
    tk.Label(root, text="Gross Weight:", bg='#3366cc', fg='white', font=('Arial', 9, 'bold')).place(x=10, y=y_box+gap)
    
    net_wt_text = tk.Entry(root, width=20); net_wt_text.place(x=180, y=y_box + gap*2); net_wt_text.insert(0, "20")
    tk.Label(root, text="Net Weight:", bg='#3366cc', fg='white', font=('Arial', 9, 'bold')).place(x=10, y=y_box+gap*2)

    created_name_text = tk.Entry(root, width=29); created_name_text.place(x=180, y=y_box + gap*3)
    tk.Label(root, text="Created By:", bg='#3366cc', fg='white', font=('Arial', 9, 'bold')).place(x=10, y=y_box+gap*3)

    # Scan Entry Field for Verification
    tk.Label(root, text="Verified Sensor:", bg='#3366cc', fg='white', font=('Arial', 9, 'bold')).place(x=10, y=y_box+gap*4)
    scan_entry = tk.Entry(root, width=25, state='disabled', font=('Arial', 10))
    scan_entry.place(x=180, y=y_box + gap*4)
    scan_entry.bind('<Return>', verify_sensor_scan)

    # Status Label
    global status_label
    status_label = tk.Label(root, text="Verified: 0 / 0", bg='#3366cc', fg='yellow', font=('Arial', 10, 'bold'))
    status_label.place(x=10, y=y_box+gap*5)

    # Storage location indicator (applies to all imported sensors)
    storage_location_label = tk.Label(root, text="Storage Location: ---", bg='#3366cc', fg='white', font=('Arial', 10, 'bold'))
    storage_location_label.place(x=10, y=y_box+gap*6)

    # Wider, scrollable sensor display
    sensor_frame = tk.Frame(root)
    sensor_frame.place(x=390, y=60, width=420, height=420)
    sensor_id_text = tk.Text(sensor_frame, wrap='none', bg="#eeeeee", state='disabled')
    sensor_id_text.pack(side='left', fill='both', expand=True)
    sensor_vscroll = tk.Scrollbar(sensor_frame, orient='vertical', command=sensor_id_text.yview)
    sensor_vscroll.pack(side='right', fill='y')
    sensor_id_text.configure(yscrollcommand=sensor_vscroll.set)

    tk.Button(root, text="Import \nDetails", font=("Arial", 11, "bold"), bg="#F45AE9", command=new_entry, width=10, height=3).place(x=10, y=480)
    
    create_button = tk.Button(root, text="Create \nShipment \nRecord", font=("Arial", 11, "bold"), bg="#32CD32", command=create_lot_masterlist, width=10, height=3, state='disabled')
    create_button.place(x=135, y=480)
    
    tk.Button(root, text="Clear \nFields", font=("Arial", 11, "bold"), bg="#FFD700", command=clear_fields, width=10, height=3).place(x=260, y=480)

    update_datetime(shipment_date_text)
    root.mainloop()

create_gui()