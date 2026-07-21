"""Quick visual test without GUI"""
from PIL import Image, ImageDraw, ImageFont
import barcode
from barcode.writer import ImageWriter
from io import BytesIO

DPI = 300
LABEL_MM = 101.6
LABEL_SIZE = int((LABEL_MM / 25.4) * DPI)
DESC_FONT_SIZE = 35

try:
    DESC_FONT = ImageFont.truetype("arial.ttf", DESC_FONT_SIZE)
except:
    DESC_FONT = ImageFont.load_default()

def generate_barcode_image(code_text, width=300, height=80):
    """Generate a barcode image from text"""
    if not code_text or code_text.strip() == "":
        return Image.new("RGB", (width, height), "white")
    
    try:
        from io import BytesIO
        code128 = barcode.get_barcode_class('code128')
        
        writer = ImageWriter()
        writer.set_options({
            'module_width': 0.5,
            'module_height': 15.0,
            'quiet_zone': 4,
            'font_size': 12,
            'text_distance': 4,
            'write_text': True,
        })
        
        barcode_instance = code128(str(code_text), writer=writer)
        buffer = BytesIO()
        barcode_instance.write(buffer)
        buffer.seek(0)
        
        barcode_img = Image.open(buffer)
        if barcode_img.mode != 'RGB':
            barcode_img = barcode_img.convert('RGB')
        
        barcode_img = barcode_img.resize((width, height), Image.Resampling.LANCZOS)
        return barcode_img
        
    except Exception as e:
        print(f"Error: {e}")
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        draw.text((10, height//2), "ERROR", fill="red")
        return img

# Create simple 2x2 test label
print("Creating test label with barcodes...")

img = Image.new("RGB", (800, 800), "white")
draw = ImageDraw.Draw(img)

# Draw grid
draw.rectangle((0, 0, 799, 799), outline="black", width=5)
draw.line((400, 0, 400, 800), fill="black", width=5)
draw.line((0, 400, 800, 400), fill="black", width=5)

# Test data
test_data = [
    ("123456789012", "PCB SENSOR"),
    ("MAGS-M15H-AB000P", "MOTOR SENSOR"),
    ("LOT123456789", "DESCRIPTION 1"),
    ("ABC987654321", "DESCRIPTION 2"),
]

positions = [
    (50, 50),    # Top-left
    (450, 50),   # Top-right
    (50, 450),   # Bottom-left
    (450, 450),  # Bottom-right
]

for (barcode_text, desc_text), (x, y) in zip(test_data, positions):
    print(f"\nGenerating: {barcode_text}")
    
    # Generate barcode
    barcode_img = generate_barcode_image(barcode_text, 300, 100)
    img.paste(barcode_img, (x, y))
    
    # Draw description
    draw.text((x + 50, y + 120), desc_text, fill="black", font=DESC_FONT)
    print(f"✓ Added to position ({x}, {y})")

# Save
output_file = "test_label_with_barcodes.png"
img.save(output_file)
print(f"\n✓ Saved as {output_file}")
print("Open this file to verify barcodes are showing!")
