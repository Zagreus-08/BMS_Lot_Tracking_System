import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from tkinter import filedialog
from openpyxl import Workbook
from openpyxl.styles import Border, Side
from datetime import datetime
from tkcalendar import DateEntry

def fetch_details():
    search_type = search_type_combobox.get()
    search_value = search_value_entry.get()
    
    if search_type == "Date":
        search_from_date = from_date_entry.get()
        search_to_date = to_date_entry.get()

        if not search_from_date or not search_to_date:
            messagebox.showwarning("Input Error", "Please enter both 'From' and 'To' dates in MM/DD/YYYY format.")
            return

        try:
            # Convert the input dates to datetime objects
            search_from_date_obj = datetime.strptime(search_from_date, "%m/%d/%Y")
            search_to_date_obj = datetime.strptime(search_to_date, "%m/%d/%Y")
            
            # Convert to the correct format for the database query
            search_from_date_str = search_from_date_obj.strftime("%Y-%m-%d")
            search_to_date_str = search_to_date_obj.strftime("%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Invalid Date Format", "Please enter the dates in the format MM/DD/YYYY.")
            return
        
        # Use the query_lot_details function to search the database
        records = query_lot_details(date_from=search_from_date_str, date_to=search_to_date_str)
    else:
        if not search_value:
            messagebox.showwarning("Input Error", f"Please enter a value for {search_type}.")
            return
        
        # Use the query_lot_details function to search the database
        if search_type == "Lot Number":
            records = query_lot_details(lot_number=search_value)
        elif search_type == "Sensor ID":
            records = query_lot_details(sensor_id=search_value)
    
    if not records:
        messagebox.showinfo("No Results", f"No records found for the given {search_type.lower()}.")
        return
    
    # Clear the sensor list before adding new search results
    sensor_list.delete(*sensor_list.get_children())
    
    for row in records:
        sensor_list.insert("", "end", values=row)
    
    # Auto-fit column widths
    for col in sensor_columns:
        # Set the initial width to a reasonable size
        sensor_list.column(col, width=tk.font.Font().measure(col))
    
    for item in sensor_list.get_children():
        for idx, val in enumerate(sensor_list.item(item)['values']):
            # Ensure we're not going out of bounds (check if the index is within range)
            if idx < len(sensor_columns):
                col_w = tk.font.Font().measure(val)
                current_width = sensor_list.column(sensor_columns[idx], width=None)
                if current_width < col_w:
                    sensor_list.column(sensor_columns[idx], width=col_w)

# Function to clear all fields
def clear_fields():
    search_value_entry.delete(0, tk.END)
    sensor_list.delete(*sensor_list.get_children())

def export_to_excel():
    sensor_data = [sensor_list.item(item)["values"] for item in sensor_list.get_children()]
    
    if not sensor_data:
        messagebox.showwarning("No Data", "No data to export.")
        return
    
    # Ask user to save the file
    file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], title="Save as")
    if not file_path:
        return
    
    # Create a new workbook using OpenPyXL
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sensor Details"  # Set sheet name
    
    # Add header
    sheet.append(sensor_columns)
    
    # Add data rows
    for row in sensor_data:
        sheet.append(row)
    
    # Apply borders and adjust column widths
    for row in sheet.iter_rows():
        for cell in row:
            cell.border = Border(left=Side(border_style="thin"), right=Side(border_style="thin"),
                                 top=Side(border_style="thin"), bottom=Side(border_style="thin"))
    
    for column in sheet.columns:
        max_length = 0
        col = column[0].column_letter  # Get the column name
        for cell in column:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        adjusted_width = (max_length + 2)  # Add padding
        sheet.column_dimensions[col].width = adjusted_width
    
    # Ensure at least one sheet is visible
    sheet.sheet_state = 'visible'
    
    # Save the workbook
    workbook.save(file_path)
    
    messagebox.showinfo("Export Successful", f"Data has been exported to {file_path}")


DB_FILE = r"\\phlsvr08\BMS Data\BMS_Database\Lot_Tracking\lot_masterlist.db"

def query_lot_details(lot_number=None, sensor_id=None, date_from=None, date_to=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    query = "SELECT * FROM lot_masterlist WHERE 1=1"
    params = []

    if lot_number:
        query += " AND lot_number = ?"
        params.append(lot_number)
    if sensor_id:
        query += " AND sensor_id = ?"
        params.append(sensor_id)

    if date_from and date_to:
        query += " AND DATE(substr(created_date, 7, 4) || '-' || substr(created_date, 1, 2) || '-' || substr(created_date, 4, 2)) BETWEEN DATE(?) AND DATE(?)"
        params.extend([date_from, date_to])

    print("Executing Query:", query)  # Debugging statement
    print("With Parameters:", params)  # Debugging statement
    cursor.execute(query, params)
    result = cursor.fetchall()
    conn.close()

    # Replace None with empty strings
    result = [[value if value is not None else '' for value in row] for row in result]
    
    return result

sensor_columns = ["ID", "Project", "Lot Number", "Sensor ID", "Wafer Number", "PCB Sheet Number", "Condition", "Cable Type", 
                  "Cable Length", "Coil Connection", "Created Date", "Created By", "Product Description", "OCR_Reading", "X_alignment_1", "Y_alignment_1", "X_alignment_2", "Y_alignment_2","mr_chip_height",
                  "SBB_Resistance_Coil_Pos", "SBB_Resistance_Coil_Vb", "SBB_Resistance_Va_Vb", "SBB_Resistance_Vdd_GnD", 
                  "BS_gap_to_GMR", "TS_gap_to_GMR", "BS_Gap_to_MR_Chip", "TS_Gap_to_MR_Chip", "PCB_Gap_to_BS1", "PCB_Gap_to_BS2",
                  "QA_Inspection1_bottom", "QA_Inspection1_top", "Top_Molding_Length", "Top_Molding_Width",
                  "Top_Molding_Height", "Wire1_Color", "Wire2_Color", "Wire3_Color", "Wire4_Color", "Wire5_Color", "Wire6_Color",
                  "Labelling","Cable_Resistance_48_turns", "Cable_Resistance_Coil_Vb", "Cable_Resistance_Va_Vb", "Cable_Resistance_Vdd_GnD", 
                  "QA_Inspection2_bottom", "Bottom_Molding_Length", "Bottom_Molding_Width", "Bottom_Molding_Height",
                  "Inductance", "Final_Resistance_Coil_Vb", "Final_Resistance_Va_Vb", "Final_Resistance_Vdd_GnD", 
                  "Dynamic_range_uT", "Linearity_FS", "Sensitivity_mV_nT", "Sensitivity_uV_nT", "Noise_Density_1Hz", 
                  "Noise_Density_10kHz", "QA_Final_bottom", "QA_Final_top", "QA_Final_sensor", "Sensor_Sealing"]

root = tk.Tk()
root.title("BMS Data Package Query System")
root.geometry("1210x570")
root.configure(bg='lightgray')
root.resizable(False, False)

title_label = tk.Label(root, text="BMS Data Package Query System", font=("BiomeW04-Bold", 24, "bold"), bg="lightgray")
title_label.place(x=10, y=10)

tk.Label(root, text="Search By:", bg='lightgray', fg="black").place(x=5, y=65)
search_type_combobox = ttk.Combobox(root, values=["Lot Number", "Sensor ID", "Date"], width=27)
search_type_combobox.place(x=105, y=65)
search_type_combobox.set("Lot Number")
search_type_combobox.bind("<<ComboboxSelected>>", lambda event: clear_fields())
tk.Label(root, text="Value:", bg='lightgray', fg="black").place(x=5, y=95)
search_value_entry = tk.Entry(root, width=30)
search_value_entry.place(x=105, y=95)

search_button = tk.Button(root, text="Search", command=fetch_details, bg="green", fg="white",
                          font=("Tahoma", 12, "bold"), padx=10, pady=2, relief='raised', borderwidth=3)
search_button.place(x=550, y=70)

clear_button = tk.Button(root, text="Clear", command=clear_fields, bg="red", fg="white",
                         font=("Tahoma", 12, "bold"), padx=17, pady=1, relief='raised', borderwidth=3)
clear_button.place(x=650, y=70)

export_button = tk.Button(root, text="Export", command=export_to_excel, bg="blue", fg="white",
                          font=("Tahoma", 12, "bold"), padx=12, pady=1, relief='raised', borderwidth=3)
export_button.place(x=750, y=70)

tk.Label(root, text="From Date:", bg='lightgray', fg="black").place(x=350, y=65)
from_date_entry = DateEntry(root, width=12, date_pattern="mm/dd/yyyy")
from_date_entry.place(x=420, y=65)
tk.Label(root, text="To Date:", bg='lightgray', fg="black").place(x=350, y=95)
to_date_entry = DateEntry(root, width=12, date_pattern="mm/dd/yyyy")
to_date_entry.place(x=420, y=95)

# Initialize sensor_list Treeview with sensor_columns
sensor_list = ttk.Treeview(root, columns=sensor_columns, show="headings", height=10)
# Add a horizontal scrollbar
h_scrollbar = ttk.Scrollbar(root, orient="horizontal", command=sensor_list.xview)
sensor_list.configure(xscrollcommand=h_scrollbar.set)
h_scrollbar.place(x=5, y=540, width=1200)

for col in sensor_columns:
    sensor_list.heading(col, text=col)
    sensor_list.column(col, width=tk.font.Font().measure(col))
sensor_list.column("ID", width=40, stretch=True)
sensor_list.place(x=5, y=140, width=1200, height=400)

root.mainloop()