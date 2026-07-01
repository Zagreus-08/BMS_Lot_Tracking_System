import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import time
import json
import os
import csv
from datetime import datetime
import pyvisa

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

# ----- LCR Meter setup (Keysight U1733C for inductance AND resistance) -----
lcr_meter_address = None  # Set by COM-port selection dropdown
# Tracks which ResourceManager backend succeeded (None -> default, '@py' -> pyvisa-py)
lcr_rm_backend = None

def detect_working_serial_resource(port_num, timeout=2000):
    """Try multiple pyvisa backends and resource strings for a COM port.
    Returns (backend, resource_string) or (None, None) if none worked.
    """
    candidates = [f"ASRL{port_num}::INSTR", f"COM{port_num}"]
    backends = [None, '@py']
    for backend in backends:
        try:
            rm = pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
        except Exception:
            continue
        for res in candidates:
            try:
                inst = rm.open_resource(res)
                # Quick basic config to validate serial connection
                try:
                    inst.baud_rate = 9600
                    inst.data_bits = 8
                    inst.parity = pyvisa.constants.Parity.none
                    inst.stop_bits = pyvisa.constants.StopBits.one
                    inst.timeout = timeout
                except Exception:
                    pass
                # Try a harmless query if supported
                try:
                    _ = inst.query('*IDN?', timeout=timeout)
                except Exception:
                    # Query may fail on some instruments; still treat open as success
                    pass
                try:
                    inst.close()
                except Exception:
                    pass
                return (backend, res)
            except Exception:
                try:
                    inst.close()
                except Exception:
                    pass
                continue
    return (None, None)


def get_rm():
    """Return a ResourceManager using detected backend if available, else try default then pyvisa-py."""
    global lcr_rm_backend
    try:
        if lcr_rm_backend:
            return pyvisa.ResourceManager(lcr_rm_backend)
        try:
            return pyvisa.ResourceManager()
        except Exception:
            return pyvisa.ResourceManager('@py')
    except Exception:
        return pyvisa.ResourceManager('@py')

# ----- UI: main window -----
root = tk.Tk()
root.title("Inductance and Resistance Measurement")
root.geometry("620x660")
root.configure(bg="lightblue")
root.resizable(False, False)

# ----- Connection status label (declared early so functions can use it) -----
lcr_connection_status = tk.Label(root, text="LCR: Checking...", font=("Arial", 10, "bold"), bg="lightblue", fg="orange")
lcr_connection_status.place(x=360, y=50)

# COM port selection dropdown (COM1-COM20)
com_ports = [f"COM{i}" for i in range(1, 21)]
com_port_var = tk.StringVar()
com_port_combobox = ttk.Combobox(root, values=com_ports, width=8, textvariable=com_port_var, state="readonly")
com_port_combobox.place(x=500, y=50)
com_port_combobox.set("")

def on_com_port_selected(event=None):
    global lcr_meter_address
    global lcr_rm_backend
    sel = com_port_var.get()
    if not sel:
        lcr_meter_address = None
        lcr_connection_status.config(text="LCR: Not Connected", fg="red")
        return
    try:
        port_num = int(sel.replace("COM", ""))
    except Exception:
        lcr_meter_address = None
        lcr_connection_status.config(text="LCR: Not Connected", fg="red")
        return
    # Probe multiple resource backends/strings to find a working resource
    backend, resource_string = detect_working_serial_resource(port_num, timeout=2000)
    if resource_string:
        lcr_rm_backend = backend
        lcr_meter_address = resource_string
        lcr_connection_status.config(text=f"LCR: Connected ({sel})", fg="green")
        # Ensure device in expected mode
        set_lcr_meter_mode('L')
    else:
        lcr_meter_address = None
        lcr_rm_backend = None
        lcr_connection_status.config(text="LCR: Disconnected", fg="red")

com_port_combobox.bind('<<ComboboxSelected>>', on_com_port_selected)

# ----- LCR Meter functions (Keysight U1733C) -----
def read_lcr_meter_inductance():
    """Read inductance from Keysight U1733C LCR meter"""
    if not lcr_meter_address:
        print("LCR meter address not set")
        return ""
    
    rm = get_rm()
    lcr_meter = None
    try:
        lcr_meter = rm.open_resource(lcr_meter_address)
        lcr_meter.baud_rate = 9600
        lcr_meter.data_bits = 8
        lcr_meter.parity = pyvisa.constants.Parity.none
        lcr_meter.stop_bits = pyvisa.constants.StopBits.one
        lcr_meter.timeout = 5000
        
        # Read measurement data
        measurement = lcr_meter.query('FETC?')
        inductance_value = float(measurement.strip()) * 1e6  # Convert H to µH
        return f"{inductance_value:.3f}"
    except (pyvisa.VisaIOError, Exception) as e:
        print(f'Error communicating with LCR meter: {e}')
        return ""
    except ValueError:
        return ""
    finally:
        if lcr_meter:
            lcr_meter.close()

def read_lcr_meter_resistance():
    """Read resistance from Keysight U1733C LCR meter"""
    if not lcr_meter_address:
        print("LCR meter address not set")
        return ""
    
    rm = get_rm()
    lcr_meter = None
    try:
        lcr_meter = rm.open_resource(lcr_meter_address)
        lcr_meter.baud_rate = 9600
        lcr_meter.data_bits = 8
        lcr_meter.parity = pyvisa.constants.Parity.none
        lcr_meter.stop_bits = pyvisa.constants.StopBits.one
        lcr_meter.timeout = 5000
        
        # Read measurement data
        measurement = lcr_meter.query('FETC?')
        resistance_value = float(measurement.strip())  # Resistance in Ohms
        return f"{resistance_value:.2f}"
    except (pyvisa.VisaIOError, Exception) as e:
        print(f'Error communicating with LCR meter: {e}')
        return ""
    except ValueError:
        return ""
    finally:
        if lcr_meter:
            lcr_meter.close()

def set_lcr_meter_mode(mode='L'):
    """Set the LCR meter to inductance (L) or resistance (R) mode"""
    if not lcr_meter_address:
        print("LCR meter address not set")
        return
    
    rm = get_rm()
    lcr_meter = None
    try:
        lcr_meter = rm.open_resource(lcr_meter_address)
        lcr_meter.baud_rate = 9600
        lcr_meter.data_bits = 8
        lcr_meter.parity = pyvisa.constants.Parity.none
        lcr_meter.stop_bits = pyvisa.constants.StopBits.one
        lcr_meter.timeout = 5000
        
        lcr_meter.write('*CLS')
        if mode == 'L':
            lcr_meter.write('FUNC L')  # Inductance mode
            lcr_meter.write('RANGE:IND 1E-6')
            print('LCR meter set to inductance mode.')
        elif mode == 'R':
            lcr_meter.write('FUNC R')  # Resistance mode
            print('LCR meter set to resistance mode.')
        # Removed time.sleep() for faster switching
    except (pyvisa.VisaIOError, Exception) as e:
        print(f'LCR meter not available or error setting mode: {e}')
    finally:
        if lcr_meter:
            lcr_meter.close()

def check_lcr_connection_status():
    """Check the connection status of the LCR meter"""
    global lcr_meter_address
    # If no address set, show not connected (user must select COM port)
    if not lcr_meter_address:
        lcr_connection_status.config(text="LCR: Not Connected", fg="red")
        root.after(5000, check_lcr_connection_status)
        return
    
    # Address is set, verify connection
    rm = get_rm()
    lcr_meter = None
    try:
        lcr_meter = rm.open_resource(lcr_meter_address)
        lcr_meter.baud_rate = 9600
        lcr_meter.data_bits = 8
        lcr_meter.parity = pyvisa.constants.Parity.none
        lcr_meter.stop_bits = pyvisa.constants.StopBits.one
        lcr_meter.timeout = 5000
        idn = lcr_meter.query('*IDN?')
        print(f'LCR meter connected: {idn}')
        port_name = lcr_meter_address.replace('ASRL', 'COM').replace('::INSTR', '')
        lcr_connection_status.config(text=f"LCR: Connected ({port_name})", fg="green")
    except pyvisa.VisaIOError:
        # Connection lost, reset address to trigger re-detection
        lcr_meter_address = None
        lcr_connection_status.config(text="LCR: Disconnected", fg="red")
    except Exception as e:
        print(f'LCR meter connection error: {e}')
        lcr_meter_address = None
        lcr_connection_status.config(text="LCR: Disconnected", fg="red")
    finally:
        if lcr_meter:
            try:
                lcr_meter.close()
            except:
                pass
    root.after(5000, check_lcr_connection_status)  # Check every 5 seconds



# ----- Navigation / enter handling -----
def navigate_on_enter(event, row, col):
    if col == 0:  # Enter pressed on Sensor ID column
        barcode_validate_sensor_id(event, row)
        return

    # Column 1 is Inductance (LCR meter already in L mode), columns 2-4 are resistances (LCR meter in R mode)
    if col == 1:
        # LCR meter is already in L mode from startup/previous row, just read
        inductance_value = read_lcr_meter_inductance()
        if inductance_value:
            data_entry[row][col].config(state="normal")
            data_entry[row][col].delete(0, tk.END)
            data_entry[row][col].insert(0, inductance_value)
            print(f"Inductance: {inductance_value} µH")
            # Immediately switch to R mode for next measurements (no delay)
            set_lcr_meter_mode('R')
    elif col == 2:
        # First resistance column - LCR meter already switched to R mode after inductance
        resistance_value = read_lcr_meter_resistance()
        if resistance_value:
            data_entry[row][col].config(state="normal")
            data_entry[row][col].delete(0, tk.END)
            try:
                res_float = float(resistance_value)
                if res_float > 2000:
                    data_entry[row][col].insert(0, "OPEN")
                else:
                    data_entry[row][col].insert(0, resistance_value)
            except ValueError:
                data_entry[row][col].insert(0, resistance_value)
            print(f"Resistance: {resistance_value} Ω")
    else:
        # Columns 3-4: LCR meter already in R mode, just read
        resistance_value = read_lcr_meter_resistance()
        if resistance_value:
            data_entry[row][col].config(state="normal")
            data_entry[row][col].delete(0, tk.END)
            try:
                res_float = float(resistance_value)
                if res_float > 2000:
                    data_entry[row][col].insert(0, "OPEN")
                else:
                    data_entry[row][col].insert(0, resistance_value)
            except ValueError:
                data_entry[row][col].insert(0, resistance_value)
            print(f"Resistance: {resistance_value} Ω")

    next_col = col + 1
    next_row = row

    # If we just finished last measurement column (col==4)
    if next_col == 5:
        # Judge current row
        judge_row_values(row)
        # Switch back to L mode for next row's inductance measurement
        set_lcr_meter_mode('L')
        # Prepare and focus next row's Sensor ID
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
        # Get current process
        current_process = entries.get("Current Process:", tk.Entry()).get().strip()
        
        # Use get_allowed_sensor_ids to get only sensors without defects
        valid_ids = get_allowed_sensor_ids(lot_number, current_process)

        # map case-insensitively
        matched = None
        for sid in valid_ids:
            if sensor_id.upper() == str(sid).upper():
                matched = sid
                break

        if not matched and valid_ids:
            messagebox.showerror("Sensor Rejected", 
                               f"Sensor ID '{sensor_id}' CANNOT proceed.\n\n"
                               f"Reason: Either not in lot '{lot_number}' OR\n"
                               f"has defects from previous processes.\n\n"
                               f"This sensor must be set aside.")
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
                data_entry[row][0].config(bg="lightgreen")
            except Exception:
                pass
        else:
            try:
                data_entry[row][0].config(bg="lightgreen")
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

    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"An error occurred: {e}")

# ----- Fetch lot info & prepare UI for manual/OCR entry -----
def fetch_lot_info(event=None):
    global sensor_ids_no_defects
    global current_process

    lot_number = entries["Lot Number:"].get().strip()
    if not lot_number:
        messagebox.showwarning("Warning", "Please enter a Lot Number.")
        return

    # Check LCR connection status
    if "Connected" not in lcr_connection_status.cget("text"):
        messagebox.showwarning("Warning", "Please ensure LCR meter is connected.")
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
            else:
                cb = entries["Current Process:"]
                if current_process in cb.cget("values"):
                    cb.set(current_process)
                else:
                    cb.set(cb.cget("values")[0] if cb.cget("values") else current_process)
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

        # 4) If MP, enforce the process check; if Eval, skip strict check
        if str(lot_condition).upper() == "MP":
            if current_process != "Inductance and Resistance":
                messagebox.showerror("Error", "The lot number inputted is not for Inductance and Resistance Measurement")
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

        # Focus the first Sensor ID entry (row 0) for manual input
        try:
            data_entry[0][0].focus_set()
        except Exception:
            pass
        conn_track.close()

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
    current_process = entries["Current Process:"].get()

    if data_entry[row][0].get():  # Only judge rows with Sensor ID
        # Get the values: Inductance, Coil-/Vb, Va/Vb, Vdd/Gnd
        values = [
            data_entry[row][1].get(),  # Inductance
            data_entry[row][2].get(),  # Coil-/Vb
            data_entry[row][3].get(),  # Va/Vb
            data_entry[row][4].get(),  # Vdd/Gnd
        ]

        # Define limits for Inductance and Resistance Measurement
        # Inductance: 18.00-22.15 µH, Resistances: 933-1733 Ω
        limits = [
            (18.50, 22.50),   # Inductance in µH
            (3.80, 4.60),      # Coil-/Vb resistance
            (933, 1733),      # Va/Vb resistance
            (933, 1733),      # Vdd/Gnd resistance
        ]

        row_failed = False

        # Loop through each value and its corresponding limit
        for col, (value, limit) in enumerate(zip(values, limits), start=1):
            try:
                if not value or value.strip() == "":
                    row_failed = True
                    data_entry[row][col].config(bg="red")
                    continue
                
                # Skip "OPEN" values - treat as failed
                if value.upper() == "OPEN":
                    row_failed = True
                    data_entry[row][col].config(bg="red")
                    continue
                    
                lower_limit, upper_limit = limit
                value_float = float(value)
                
                # Check if the value is within the limits (inclusive)
                if lower_limit <= value_float <= upper_limit:
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
        entry.config(state="normal")
        entry.delete(0, tk.END)
        entry.config(state="readonly" if entry == entries["Current Process:"] else "normal")
    for r in range(20):
        for c in range(5):
            data_entry[r][c].config(state="normal")
            data_entry[r][c].delete(0, tk.END)
            data_entry[r][c].config(state="readonly", bg="white")
        judgement_labels[r].config(text="", bg="lightblue")

class BMSPopup(tk.Toplevel):
    def __init__(self, master, lot_number, current_process, operator,
                 sensor_list, combobox_candidates, failed_sensor_list, blank_judgement_list, csv_rows_data, lot_condition="MP", 
                 total_lot_count=0, unscanned_sensors=None, passed_sensors=None):
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
        self.total_lot_count = total_lot_count if total_lot_count > 0 else len(sensor_list)
        self.unscanned_sensors = unscanned_sensors if unscanned_sensors else []
        self.passed_sensors = passed_sensors if passed_sensors else []

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

        # Sensor ID Combobox - include failed, blank, AND unscanned sensors
        tk.Label(self, text="Sensor ID:", bg='#3a6ba8', fg="white").place(x=5, y=105)
        
        # Combine all sensors that need defects for the dropdown
        all_sensors_needing_defects = list(set(self.combobox_candidates + self.unscanned_sensors))
        all_sensors_needing_defects.sort()  # Sort for easier selection
        
        self.sensor_id_combobox = ttk.Combobox(self, values=all_sensors_needing_defects, width=28)
        self.sensor_id_combobox.place(x=105, y=105)
        if all_sensors_needing_defects:
            self.sensor_id_combobox.set(all_sensors_needing_defects[0])

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

        # Populate Quantity IN / OUT
        # Quantity IN = TOTAL sensors in the lot (not just scanned)
        # Quantity OUT = Total - (failed + blank + unscanned)
        sensors_that_passed = len(self.passed_sensors)
        
        self.quantity_in_entry.delete(0, tk.END)
        self.quantity_in_entry.insert(0, str(self.total_lot_count))
        self.quantity_out_entry.delete(0, tk.END)
        self.quantity_out_entry.insert(0, str(sensors_that_passed))

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
            qin = int(self.quantity_in_entry.get())
        except ValueError:
            qin = 0
        defect_count = len([self.table.item(r)["values"][1] for r in self.table.get_children() if self.table.item(r)["values"][1]])
        self.quantity_out_entry.delete(0, tk.END)
        self.quantity_out_entry.insert(0, str(qin - defect_count))
        
    def export_to_csv(self, lot_number, proc_datetime, operator):
        """Helper to export measurement data to CSV"""
        # Ensure csv_rows_data is iterable
        rows = list(self.csv_rows_data) if self.csv_rows_data else []

        current_process = self.current_process
        base_folder = r"\\phlsvr08\BMS Data\Assembly Data\Inductance and Resistance Measurement"
        y = time.strftime("%Y")
        m = time.strftime("%B")
        d = time.strftime("%m.%d.%Y")

        export_folder = os.path.join(base_folder, y, m, d)

        try:
            os.makedirs(export_folder, exist_ok=True)
            csv_filename = os.path.join(export_folder, f"{current_process}_{lot_number}.csv")

            # Use UTF-8 with BOM so Excel recognizes UTF-8 (handles 'µ' correctly)
            with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(["Lot Number", lot_number])
                w.writerow(["Processed Date and Time", proc_datetime])
                w.writerow(["Operator", operator])
                w.writerow([])
                headers = ["Sensor ID", "Inductance (uH)", "Coil-/Vb (Ohm)", "Va/Vb (Ohm)", "Vdd/Gnd (Ohm)", "Judgement"]
                w.writerow(headers)

                # Write rows defensively: pad or trim to header length
                for r in rows:
                    try:
                        row = list(r)
                    except Exception:
                        row = [str(r)]
                    # normalize length
                    if len(row) < len(headers):
                        row += [""] * (len(headers) - len(row))
                    elif len(row) > len(headers):
                        row = row[:len(headers)]
                    w.writerow(row)
            print(f"CSV Exported: {csv_filename}")
        except Exception as e:
            messagebox.showwarning("CSV Export Error", f"Could not export CSV: {e}")
            
    def save_data_and_advance(self):
        if not self.operator_entry.get():
            messagebox.showwarning("Input Error", "Please enter Operator.")
            return
    
        # 1. Validation logic for defects
        sensors_needing_defects_count = len(self.failed_sensor_list) + len(self.blank_judgement_list) + len(self.unscanned_sensors)
        defect_entries_count = len([row for row in self.table.get_children() if self.table.item(row)["values"][1]])
        
        if defect_entries_count < sensors_needing_defects_count:
            messagebox.showerror("Missing Defects", f"Need {sensors_needing_defects_count} defect entries, but only have {defect_entries_count}.")
            return
    
        lot_number = self.lot_number
        current_process = self.current_process
        operator = self.operator_entry.get()
        proc_datetime = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        quantity_in = self.quantity_in_entry.get()
        quantity_out = self.quantity_out_entry.get()
    
        try:
            # --- 1) Update lot_masterlist with RAW MEASUREMENTS ---
            if self.csv_rows_data:
                conn_master = sqlite3.connect(db_path_masterlist)
                cursor_master = conn_master.cursor()
                for row in self.csv_rows_data:
                    sensor_id = row[0]
                    val1, val2, val3, val4 = row[1], row[2], row[3], row[4]
    
                    # Map columns based on process name
                    # This ensures EVAL processes also save data
                    if current_process == "Inductance and Resistance":
                        sql = """UPDATE lot_masterlist SET Inductance=?, Final_Resistance_Coil_Vb=?, 
                                 Final_Resistance_Va_Vb=?, Final_Resistance_Vdd_GnD=? WHERE sensor_id=?"""
                        params = (val1, val2, val3, val4, sensor_id)
                    else:
                        continue 

                    cursor_master.execute(sql, params)
                
                conn_master.commit()
                conn_master.close()
    
            # --- 2) Update lot_tracking with PROCESS METADATA ---
            conn = sqlite3.connect(db_path_tracking)
            cursor = conn.cursor()

            # Map defects
            defects_dict = {}
            generic_defects = []
            for row in self.table.get_children():
                sid, dfct, rem = self.table.item(row)["values"]
                if sid: defects_dict[sid] = (dfct, rem)
                else: generic_defects.append((dfct, rem))

            cursor.execute("SELECT sensor_id FROM lot_tracking WHERE lot_number=?", (lot_number,))
            all_sensors_for_lot = [r[0] for r in cursor.fetchall()]
            
            # Match generic defects to missing sensors
            sensors_needing_generic = [s for s in all_sensors_for_lot if (s in self.failed_sensor_list or s in self.unscanned_sensors) and s not in defects_dict]
            for i, sid in enumerate(sensors_needing_generic):
                if i < len(generic_defects): defects_dict[sid] = generic_defects[i]

            columns = process_column_mapping.get(current_process)
            
            # IMPORTANT: Remove the strict "MP" check if you want EVAL lots to save to tracking too
            if columns and len(columns) >= 6:
                for sid in all_sensors_for_lot:
                    defect, remarks = defects_dict.get(sid, ("", ""))
                    
                    cursor.execute(f"""
                        UPDATE lot_tracking
                        SET {columns[0]}=?, {columns[1]}=?, {columns[2]}=?, {columns[3]}=?, {columns[4]}=?, {columns[5]}=?
                        WHERE lot_number=? AND sensor_id=?
                    """, (quantity_in, quantity_out, defect, remarks, proc_datetime, operator, lot_number, sid))
                
                # Advance process only if it's a standard MP lot
                if self.lot_condition.upper() == "MP":
                    try:
                        idx = process_flow.index(current_process)
                        if idx + 1 < len(process_flow):
                            next_proc = process_flow[idx + 1]
                            cursor.execute("UPDATE lot_tracking SET current_process=? WHERE lot_number=?", (next_proc, lot_number))
                    except ValueError:
                        pass

            conn.commit()
            conn.close()
    
            # --- 3) Export CSV ---
            # (Your existing CSV code is fine, but ensure csv_rows_data is populated)
            self.export_to_csv(lot_number, proc_datetime, operator) # Moved to helper for cleanliness

            messagebox.showinfo("Success", "Data saved successfully to both databases!")
            self.destroy()
            delete_action()

        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Critical Error: {e}")

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

        popup = BMSPopup(root, lot_number, current_process, operator,
                         sensor_list_local, combobox_candidates_local,
                         failed_sensor_list_local, blank_judgement_list_local, csv_rows_data, lot_condition)
        popup.grab_set()
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

# ----- save_action wrapper -----
def save_action_wrapper():
    try:
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
                
                # Collect failed, blank, and passed lists
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
                elif j == "Passed":
                    if sid not in passed_sensor_list_local:
                        passed_sensor_list_local.append(sid)

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

        current_process = entries["Current Process:"].get().strip()
        operator = entries["Operator:"].get().strip()

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
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

# ----- Main UI construction -----
title_label = tk.Label(root, text="Inductance and Resistance Measurement", font=("BiomeW04-Bold", 16, "bold"), bg="lightblue")
title_label.place(x=10, y=0)

# COM port selection dropdown is provided above

# Entries
labels = ["Lot Number:", "Current Process:", "Date and Time:", "Operator:"]
entries = {}
label_positions = {"Lot Number:": (10, 40), "Current Process:": (10, 65), "Date and Time:": (10, 90), "Operator:": (10, 115)}
entry_positions = {"Lot Number:": (115, 40), "Current Process:": (115, 65), "Date and Time:": (115, 90), "Operator:": (115, 115)}
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



# Table headers (static)e
headers = ["No.", "Sensor ID", "Inductance", "Coil-/Vb", "Va/Vb", "Vdd/Gnd", "Judgement"]
header_positions = {"No.":(10,170), "Sensor ID":(75,170), "Inductance":(175,170), "Coil-/Vb":(267,170), "Va/Vb":(355,170), "Vdd/Gnd":(428,170), "Judgement":(510,170)}
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

# COM port will be selected by the user from the dropdown above

# Start connection status check
entries["Lot Number:"].focus_set()
check_lcr_connection_status()
root.mainloop()