"""Test barcode generation for Material Request Sheet"""
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from PIL import Image

def test_barcode_generation():
    """Test generating a barcode"""
    model_no = "TEST-MODEL-123"
    
    try:
        # Create barcode using the same method as in the project
        code128 = barcode.get_barcode_class('code128')
        writer = ImageWriter()
        barcode_instance = code128(str(model_no), writer=writer)
        
        buffer = BytesIO()
        barcode_instance.write(buffer)
        buffer.seek(0)
        
        # Load image
        img = Image.open(buffer)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        # Resize to fit in the entry field area
        img = img.resize((200, 60), Image.Resampling.LANCZOS)
        
        # Save test image
        img.save("test_material_barcode_output.png")
        print(f"✓ Barcode generated successfully for: {model_no}")
        print(f"✓ Saved as: test_material_barcode_output.png")
        print(f"Image size: {img.size}")
        return True
        
    except Exception as e:
        print(f"✗ Barcode generation error: {e}")
        return False

if __name__ == "__main__":
    print("Testing barcode generation...")
    success = test_barcode_generation()
    if success:
        print("\n✓ All tests passed!")
    else:
        print("\n✗ Tests failed!")
