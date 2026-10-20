#!/usr/bin/env python3
"""
Generates a modern, Apple-style macOS AppIcon.icns for OpenGo.
"""

import os
import math
import subprocess
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

def create_app_icon():
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Margins for standard macOS squircle icon
    margin = 80
    rect = [margin, margin, size - margin, size - margin]
    radius = 190  # Apple squircle approx

    # 1. Background gradient (Deep Midnight to Electric Cyan-Blue)
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base_draw = ImageDraw.Draw(base)

    for y in range(size):
        ratio = y / size
        # Color interpolation from #0f1c3f (deep night) to #0071e3 (electric blue)
        r = int(12 + ratio * (0 - 12))
        g = int(24 + ratio * (113 - 24))
        b = int(60 + ratio * (227 - 60))
        base_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # Mask base into rounded rectangle
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(rect, radius=radius, fill=255)
    base.putalpha(mask)

    # 2. Add subtle ambient map grid lines & contour circles
    grid_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid_layer)

    # Radial radar rings centered at the pin base
    center_x = 512
    center_y = 620
    for ring_r in [100, 180, 270, 370]:
        grid_draw.ellipse(
            [center_x - ring_r, center_y - ring_r, center_x + ring_r, center_y + ring_r],
            outline=(255, 255, 255, 28),
            width=3
        )

    # Subtle crosshairs
    grid_draw.line([(center_x - 320, center_y), (center_x + 320, center_y)], fill=(255, 255, 255, 35), width=2)
    grid_draw.line([(center_x, center_y - 280), (center_x, center_y + 240)], fill=(255, 255, 255, 35), width=2)

    # Mask grid with squircle
    base = Image.alpha_composite(base, grid_layer)
    base.putalpha(mask)

    # 3. Ambient soft drop shadow under the icon squircle
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_rect = [margin, margin + 25, size - margin, size - margin + 25]
    shadow_draw.rounded_rectangle(shadow_rect, radius=radius, fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(32))

    canvas = Image.alpha_composite(shadow, base)

    # 4. Draw the Glowing Pin Icon in the center
    pin_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pin_draw = ImageDraw.Draw(pin_layer)

    # Pin measurements
    pin_cx = 512
    pin_cy = 440
    pin_radius = 160
    tip_y = 660

    # Pin shadow
    pin_shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ps_draw = ImageDraw.Draw(pin_shadow)
    ps_draw.ellipse([pin_cx - 90, tip_y + 10, pin_cx + 90, tip_y + 45], fill=(0, 0, 0, 95))
    pin_shadow = pin_shadow.filter(ImageFilter.GaussianBlur(14))
    canvas = Image.alpha_composite(canvas, pin_shadow)

    # Custom smooth Pin Shape
    # Circle head + triangle tip
    pin_head = [
        pin_cx - pin_radius, pin_cy - pin_radius,
        pin_cx + pin_radius, pin_cy + pin_radius
    ]
    pin_draw.ellipse(pin_head, fill=(255, 255, 255, 255))

    # Triangle body down to tip
    triangle = [
        (pin_cx - pin_radius * math.cos(math.radians(35)), pin_cy + pin_radius * math.sin(math.radians(35))),
        (pin_cx, tip_y),
        (pin_cx + pin_radius * math.cos(math.radians(35)), pin_cy + pin_radius * math.sin(math.radians(35)))
    ]
    pin_draw.polygon(triangle, fill=(255, 255, 255, 255))

    # Gradient overlay on the pin (Apple Red/Coral gradient)
    pin_grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pg_draw = ImageDraw.Draw(pin_grad)
    for y in range(int(pin_cy - pin_radius), tip_y + 1):
        ratio = (y - (pin_cy - pin_radius)) / (tip_y - (pin_cy - pin_radius))
        r = int(255 - ratio * 35)
        g = int(69 - ratio * 20)
        b = int(58 + ratio * 30)
        pg_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # Mask the gradient into the pin shape
    pin_mask = pin_layer.split()[3]
    pin_colored = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pin_colored.paste(pin_grad, mask=pin_mask)

    # Inner White Eye/Circle of the pin
    inner_radius = 65
    inner_circle = [
        pin_cx - inner_radius, pin_cy - inner_radius,
        pin_cx + inner_radius, pin_cy + inner_radius
    ]
    pin_draw_colored = ImageDraw.Draw(pin_colored)
    pin_draw_colored.ellipse(inner_circle, fill=(255, 255, 255, 255))

    # Specular highlight on pin head
    highlight = [
        pin_cx - pin_radius + 45, pin_cy - pin_radius + 30,
        pin_cx + pin_radius - 45, pin_cy - pin_radius + 90
    ]
    pin_draw_colored.ellipse(highlight, fill=(255, 255, 255, 75))

    canvas = Image.alpha_composite(canvas, pin_colored)

    # Save to iconset directory
    iconset_dir = Path("AppIcon.iconset")
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(parents=True, exist_ok=True)

    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]

    for s, name in sizes:
        resized = canvas.resize((s, s), Image.Resampling.LANCZOS)
        resized.save(iconset_dir / name)

    # Run iconutil to produce AppIcon.icns
    output_icns = Path("AppIcon.icns")
    subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_icns)], check=True)
    print("✓ Successfully generated AppIcon.icns!")

    # Clean up iconset folder
    shutil.rmtree(iconset_dir)

if __name__ == "__main__":
    create_app_icon()
