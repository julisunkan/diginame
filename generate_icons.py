
from PIL import Image, ImageDraw, ImageFont
import os

def create_gradient_background(size, color1='#667eea', color2='#764ba2'):
    """Create a gradient background"""
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Convert hex to RGB
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    rgb1 = hex_to_rgb(color1)
    rgb2 = hex_to_rgb(color2)
    
    # Create gradient
    for y in range(size[1]):
        ratio = y / size[1]
        r = int(rgb1[0] * (1 - ratio) + rgb2[0] * ratio)
        g = int(rgb1[1] * (1 - ratio) + rgb2[1] * ratio)
        b = int(rgb1[2] * (1 - ratio) + rgb2[2] * ratio)
        draw.line([(0, y), (size[0], y)], fill=(r, g, b, 255))
    
    return img

def create_icon(size):
    """Create an icon with the blog logo"""
    img = create_gradient_background((size, size))
    draw = ImageDraw.Draw(img)
    
    # Draw a simple blog icon (book with pen)
    center = size // 2
    
    # Draw book
    book_width = size // 2.5
    book_height = size // 2
    book_x = center - book_width // 2
    book_y = center - book_height // 2
    
    # Book cover
    draw.rounded_rectangle(
        [book_x, book_y, book_x + book_width, book_y + book_height],
        radius=size // 20,
        fill='white',
        outline='#333',
        width=max(1, size // 64)
    )
    
    # Book lines
    line_spacing = book_height // 6
    for i in range(3):
        y = book_y + book_height // 4 + i * line_spacing
        draw.line(
            [book_x + book_width // 6, y, book_x + book_width * 5 // 6, y],
            fill='#667eea',
            width=max(1, size // 80)
        )
    
    # Draw pen
    pen_length = size // 3
    pen_width = size // 25
    pen_x = center + book_width // 4
    pen_y = center - pen_length // 2
    
    # Pen body
    draw.rounded_rectangle(
        [pen_x, pen_y, pen_x + pen_width, pen_y + pen_length],
        radius=pen_width // 2,
        fill='#764ba2'
    )
    
    # Pen tip
    draw.ellipse(
        [pen_x - pen_width // 4, pen_y + pen_length - pen_width, 
         pen_x + pen_width + pen_width // 4, pen_y + pen_length + pen_width // 2],
        fill='#333'
    )
    
    return img

def create_maskable_icon(size):
    """Create a maskable icon with safe zone"""
    # Create larger canvas to ensure safe zone
    canvas_size = int(size * 1.2)
    img = create_gradient_background((canvas_size, canvas_size))
    
    # Create the icon in the center
    icon = create_icon(size)
    
    # Paste icon in center of canvas
    offset = (canvas_size - size) // 2
    img.paste(icon, (offset, offset), icon)
    
    # Resize back to original size
    img = img.resize((size, size), Image.LANCZOS)
    
    return img

def generate_all_icons():
    """Generate all required PWA icons"""
    # Create icons directory
    icons_dir = 'static/icons'
    os.makedirs(icons_dir, exist_ok=True)
    
    # Regular icon sizes
    sizes = [72, 96, 128, 144, 152, 192, 384, 512]
    
    print("Generating regular icons...")
    for size in sizes:
        icon = create_icon(size)
        icon.save(f'{icons_dir}/icon-{size}x{size}.png', 'PNG')
        print(f"Created icon-{size}x{size}.png")
    
    # Maskable icons
    maskable_sizes = [192, 512]
    
    print("Generating maskable icons...")
    for size in maskable_sizes:
        maskable_icon = create_maskable_icon(size)
        maskable_icon.save(f'{icons_dir}/maskable-icon-{size}x{size}.png', 'PNG')
        print(f"Created maskable-icon-{size}x{size}.png")
    
    print("All icons generated successfully!")

if __name__ == "__main__":
    generate_all_icons()
