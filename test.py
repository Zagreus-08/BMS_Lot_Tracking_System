import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageWin
import win32print
import win32ui
import sys
from io import BytesIO

# Check barcode library
try:
    import barcode
    from barcode.writer import ImageWriter
    print(f"✓ Barcode library loaded successfully from: {barcode.__file__}")
except ImportError as e:
    barcode = None
    print(f"✗ ERROR: python-barcode not installed: {e}")
    print(f"✗ Python interpreter: {sys.executable}")
    print(f"✗ Run this command: {sys.executable} -m pip install python-barcode")

# -----------------------------------------
# Label Settings
# -----------------------------------------

DPI = 600

LABEL_MM = 101.6

LABEL_SIZE = int((LABEL_MM / 25.4) * DPI)

LINE_WIDTH = 8

MARGIN = 20

FONT_SIZE = 45
DESC_FONT_SIZE = 35

try:
    FONT = ImageFont.truetype("arial.ttf", FONT_SIZE)
    DESC_FONT = ImageFont.truetype("arial.ttf", DESC_FONT_SIZE)
except:
    FONT = ImageFont.load_default()
    DESC_FONT = ImageFont.load_default()


# -----------------------------------------
# Generate Barcode
# -----------------------------------------

def generate_barcode_image(code_text, width=100, height=40):
    """Generate a barcode image from text - Creates actual scannable barcode graphics"""
    if not code_text or code_text.strip() == "":
        # Return empty white image if no barcode text
        return Image.new("RGB", (width, height), "white")
    
    if barcode is None:
        # If barcode library not available, show error message
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        error_text = "Install: pip install python-barcode"
        draw.text((10, height//2 - 10), error_text, fill="red", font=DESC_FONT)
        return img
    
    try:
        from io import BytesIO
        
        # Use Code128 barcode format (supports alphanumeric)
        code128 = barcode.get_barcode_class('code128')
        
        # Create barcode with custom writer settings for high quality
        writer = ImageWriter()
        writer.set_options({
            'module_width': 0.5,      # Width of barcode bars (thicker for better visibility)
            'module_height': 15.0,    # Height of barcode bars
            'quiet_zone': 4,          # White space around barcode
            'font_size': 12,          # Text size below barcode
            'text_distance': 4,       # Distance between barcode and text
            'write_text': True,       # Show the code text below barcode
        })
        
        barcode_instance = code128(str(code_text), writer=writer)
        
        # Generate to BytesIO
        buffer = BytesIO()
        barcode_instance.write(buffer)
        buffer.seek(0)
        
        # Load barcode image
        barcode_img = Image.open(buffer)
        
        # Convert to RGB if needed (barcodes are sometimes in different modes)
        if barcode_img.mode != 'RGB':
            barcode_img = barcode_img.convert('RGB')
        
        print(f"✓ Generated barcode for '{code_text}': {barcode_img.size} -> resizing to {width}x{height}")
        
        # Resize to fit cell while maintaining aspect ratio
        barcode_img = barcode_img.resize((width, height), Image.Resampling.LANCZOS)
        
        return barcode_img
        
    except Exception as e:
        print(f"✗ Error generating barcode for '{code_text}': {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback: show error
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), f"Barcode Error:", fill="red", font=DESC_FONT)
        draw.text((10, 40), str(code_text)[:20], fill="black", font=DESC_FONT)
        return img


# -----------------------------------------
# Create Label
# -----------------------------------------

def create_label(barcode_texts, description_texts):
    """Create a 5x2 grid label with barcodes and descriptions"""
    
    print("\n" + "="*50)
    print("Creating label...")
    print("="*50)
    
    img = Image.new("RGB", (LABEL_SIZE, LABEL_SIZE), "white")
    draw = ImageDraw.Draw(img)

    w = LABEL_SIZE
    h = LABEL_SIZE

    # Draw border
    draw.rectangle((0, 0, w-1, h-1), outline="black", width=LINE_WIDTH)

    # Grid - 5 rows, 2 columns
    cols = 2
    rows = 10
    
    # Draw vertical line (middle)
    draw.line((w//2, 0, w//2, h), fill="black", width=LINE_WIDTH)
    
    # Draw horizontal lines
    for i in range(1, rows):
        y = (h * i) // rows
        draw.line((0, y, w, y), fill="black", width=LINE_WIDTH)

    # Define cells for 5x2 grid
    cell_width = w // cols
    cell_height = h // rows
    
    print(f"Label size: {w}x{h} pixels")
    print(f"Cell size: {cell_width}x{cell_height} pixels")
    
    cells = []
    for row in range(rows):
        for col in range(cols):
            x1 = col * cell_width
            y1 = row * cell_height
            x2 = (col + 1) * cell_width
            y2 = (row + 1) * cell_height
            cells.append((x1, y1, x2, y2))

    # Fill each cell with barcode and description
    for i, cell in enumerate(cells):
        if i >= len(barcode_texts):
            break
            
        x1, y1, x2, y2 = cell
        
        barcode_text = barcode_texts[i]
        desc_text = description_texts[i]
        
        if not barcode_text and not desc_text:
            continue
        
        print(f"\nCell {i+1}: Barcode='{barcode_text}', Desc='{desc_text}'")
        
        # Generate barcode
        barcode_width = int((x2 - x1) * 0.85)
        barcode_height = int((y2 - y1) * 0.5)
        
        print(f"  Generating barcode: {barcode_width}x{barcode_height}")
        barcode_img = generate_barcode_image(barcode_text, barcode_width, barcode_height)
        
        # Position barcode at top of cell
        barcode_x = x1 + ((x2 - x1) - barcode_img.width) // 2
        barcode_y = y1 + 15
        
        print(f"  Pasting barcode at position ({barcode_x}, {barcode_y})")
        img.paste(barcode_img, (barcode_x, barcode_y))
        
        # Draw description text below barcode
        if desc_text:
            bbox = draw.textbbox((0, 0), desc_text, font=DESC_FONT)
            tw = bbox[2] - bbox[0]
            
            tx = x1 + ((x2 - x1) - tw) // 2
            ty = barcode_y + barcode_img.height + 10
            
            print(f"  Drawing description at ({tx}, {ty})")
            draw.text((tx, ty), desc_text, fill="black", font=DESC_FONT)

    print("\n" + "="*50)
    print("Label creation complete!")
    print("="*50 + "\n")
    
    return img


# -----------------------------------------
# Preview
# -----------------------------------------

def preview():

    barcode_texts = [barcode_entries[i].get() for i in range(10)]
    desc_texts = [desc_entries[i].get() for i in range(10)]

    img = create_label(barcode_texts, desc_texts)

    scale = 500 / LABEL_SIZE

    preview_img = img.resize(
        (int(LABEL_SIZE*scale), int(LABEL_SIZE*scale)),
        Image.Resampling.LANCZOS
    )

    tkimg = ImageTk.PhotoImage(preview_img)

    preview_label.configure(image=tkimg)
    preview_label.image = tkimg

    preview.img = img


# -----------------------------------------
# Save
# -----------------------------------------

def save_png():

    barcode_texts = [barcode_entries[i].get() for i in range(10)]
    desc_texts = [desc_entries[i].get() for i in range(10)]

    img = create_label(barcode_texts, desc_texts)

    img.save("label.png")

    messagebox.showinfo("Saved", "Saved as label.png")


# -----------------------------------------
# Print
# -----------------------------------------

def print_label():

    barcode_texts = [barcode_entries[i].get() for i in range(10)]
    desc_texts = [desc_entries[i].get() for i in range(10)]

    img = create_label(barcode_texts, desc_texts)

    printer_name = printer_combo.get()

    if printer_name == "":
        messagebox.showerror("Error", "Select printer.")
        return

    hDC = win32ui.CreateDC()
    hDC.CreatePrinterDC(printer_name)

    hDC.StartDoc("5x2 Label")
    hDC.StartPage()

    dib = ImageWin.Dib(img)

    printable_area = (
        hDC.GetDeviceCaps(8),
        hDC.GetDeviceCaps(10)
    )

    dib.draw(
        hDC.GetHandleOutput(),
        (0, 0, printable_area[0], printable_area[1])
    )

    hDC.EndPage()
    hDC.EndDoc()
    hDC.DeleteDC()

    messagebox.showinfo("Done", "Printed successfully.")


# -----------------------------------------
# Clear
# -----------------------------------------

def clear():

    for e in barcode_entries:
        e.delete(0, tk.END)
    for e in desc_entries:
        e.delete(0, tk.END)

    preview()


# -----------------------------------------
# GUI
# -----------------------------------------

# Check if barcode library is available before starting GUI
if barcode is None:
    root = tk.Tk()
    root.withdraw()  # Hide main window
    error_msg = (
        "ERROR: python-barcode library not found!\n\n"
        f"Current Python: {sys.executable}\n\n"
        "Please install it with:\n"
        f"{sys.executable} -m pip install python-barcode\n\n"
        "Or use the RUN_LABEL_PRINTER.bat file to run with the correct environment."
    )
    messagebox.showerror("Missing Library", error_msg)
    sys.exit(1)

root = tk.Tk()

root.title("Godex RT863i+ 5x2 Label Printer with Barcodes")

root.geometry("1200x800")

# Create main container with scrollbar
main_container = ttk.Frame(root)
main_container.pack(fill="both", expand=True)

# Left frame for inputs
left_frame = ttk.Frame(main_container, padding=10)
left_frame.pack(side="left", fill="both", expand=True)

# Canvas and scrollbar for inputs
canvas = tk.Canvas(left_frame)
scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=canvas.yview)
scrollable_frame = ttk.Frame(canvas)

scrollable_frame.bind(
    "<Configure>",
    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
)

canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)

canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

# Create input fields
barcode_entries = []
desc_entries = []

ttk.Label(scrollable_frame, text="Label Inputs (10 cells: 5 rows x 2 columns)", 
          font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=3, pady=10)

for i in range(10):
    # Row header
    ttk.Label(scrollable_frame, text=f"Cell {i+1}:", 
              font=("Arial", 10, "bold")).grid(row=i*2+1, column=0, sticky="w", pady=(10, 2))
    
    # Barcode input
    ttk.Label(scrollable_frame, text="Barcode:").grid(row=i*2+2, column=0, sticky="w", padx=(20, 5))
    barcode_e = ttk.Entry(scrollable_frame, width=40)
    barcode_e.grid(row=i*2+2, column=1, pady=2, padx=5, sticky="ew")
    barcode_entries.append(barcode_e)
    
    # Description input
    ttk.Label(scrollable_frame, text="Description:").grid(row=i*2+3, column=0, sticky="w", padx=(20, 5))
    desc_e = ttk.Entry(scrollable_frame, width=40)
    desc_e.grid(row=i*2+3, column=1, pady=2, padx=5, sticky="ew")
    desc_entries.append(desc_e)

# Configure column weight
scrollable_frame.columnconfigure(1, weight=1)

# Printer selection
ttk.Label(scrollable_frame, text="Printer:", font=("Arial", 10, "bold")).grid(
    row=len(barcode_entries)*3+1, column=0, sticky="w", pady=(20, 5))

printers = [p[2] for p in win32print.EnumPrinters(2)]

printer_combo = ttk.Combobox(
    scrollable_frame,
    values=printers,
    width=38
)

default = win32print.GetDefaultPrinter()

printer_combo.set(default)

printer_combo.grid(row=len(barcode_entries)*3+1, column=1, pady=(20, 5), sticky="ew")

# Buttons
button_frame = ttk.Frame(scrollable_frame)
button_frame.grid(row=len(barcode_entries)*3+2, column=0, columnspan=2, pady=20)

ttk.Button(
    button_frame,
    text="Preview",
    command=preview
).pack(side="left", padx=5)

ttk.Button(
    button_frame,
    text="Save PNG",
    command=save_png
).pack(side="left", padx=5)

ttk.Button(
    button_frame,
    text="Print",
    command=print_label
).pack(side="left", padx=5)

ttk.Button(
    button_frame,
    text="Clear All",
    command=clear
).pack(side="left", padx=5)

# Right frame for preview
right_frame = ttk.Frame(main_container, padding=10)
right_frame.pack(side="right", fill="both", expand=False)

ttk.Label(right_frame, text="Label Preview", 
          font=("Arial", 12, "bold")).pack(pady=5)

preview_label = tk.Label(right_frame, bg="gray", width=60, height=60)
preview_label.pack(pady=10)

# Initial preview
preview()

root.mainloop()