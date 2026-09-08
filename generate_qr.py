"""
Generate a QR code image (PNG) that links to The Elevate — SNAP IT! game.

Usage:
    python generate_qr.py
    python generate_qr.py --url https://example.com --output static/my_qr.png
"""
import argparse
import os

import qrcode

DEFAULT_URL = "https://the-elevate-snap-it-game.onrender.com/"
DEFAULT_OUTPUT = os.path.join("static", "qr_code.png")


def generate_qr_code(url: str, output_path: str) -> str:
    """Generate a QR code PNG for `url` and save it to `output_path`."""
    qr = qrcode.QRCode(
        version=None,  # auto-size based on data
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path)
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a QR code PNG for a URL.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Link to encode into the QR code.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to save the PNG file.")
    args = parser.parse_args()

    path = generate_qr_code(args.url, args.output)
    print(f"QR code saved to: {os.path.abspath(path)}")
    print(f"Encoded URL: {args.url}")
