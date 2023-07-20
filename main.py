from PIL import Image, ImageTk
import tkinter as tk
from tkinter import filedialog
import os
import math
from flask import Flask, request, jsonify, send_file, url_for
from flask_cors import CORS
from datetime import datetime
from pathlib import Path
from io import BytesIO
import base64

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}})

ANY_FILETYPE = ("any", ".png .jpg .jpeg")
JPEG_FILETYPE = ("JPEG", ".jpg .jpeg")
PNG_FILETYPE = ("PNG", ".png")

def ask_for_image_file_path():
    file_path = filedialog.askopenfilename(title="Choose one or more images", multiple=False, filetypes=[ANY_FILETYPE, JPEG_FILETYPE, PNG_FILETYPE])
    return file_path

def get_file_name_without_extension(file_path):
    base_name = os.path.basename(file_path)
    file_name, file_extension = os.path.splitext(base_name)
    return file_name

def get_parent_directory(file_path):
    return os.path.dirname(file_path)

def ask_for_image_save_path(original_file_path):
    original_file_name = get_file_name_without_extension(original_file_path)
    original_parent_directory = get_parent_directory(original_file_path)
    suggested_file_name = f"{original_file_name}_digitized.png"
    save_file_path = filedialog.asksaveasfilename(title="Choose where to save the digitized file", filetypes=[PNG_FILETYPE], initialdir=original_parent_directory, initialfile=suggested_file_name)
    return save_file_path

def calculate_transparency(r, g, b, mode, threshold):
    # value between 0 and 255

    match mode:
        case "lightness":
            L = calculate_lightness(r, g, b)
        case "average":
            L = calculate_average(r, g, b)
        case "luminocity":
            L = calculate_luminocity(r, g, b)
        case _:
            L = calculate_luminocity(r, g, b)

    # values above the cutoff are left at 100% opacity
    max_L = 100

    if (threshold == max_L):
        L_scaled = 0
    else:
        L_scaled = (L - threshold) * (max_L / (max_L - threshold))
        L_scaled = max(0, L_scaled)
    return int(255 * (max_L - L_scaled) / max_L)

def calculate_luminocity(r, g, b):
    # value between 0 and 100, 100 is max luminocity 0 is min luminocity
    # Many possible calculations. This is a simple one. However, see Myndex's answer
    # for a more accurate and complete calculation
    # https://stackoverflow.com/questions/596216/formula-to-determine-perceived-brightness-of-rgb-color/37624009#37624009
    return int( (0.299 * r + 0.587 * g + 0.114 * b) / 255 * 100)

def calculate_average(r, g, b):
    return int(((r + g + b) / 3) / 255 * 100 )

def calculate_lightness(r, g, b):
    return int(((max(r, g, b) + min(r, g, b)) / 2) / 255 * 100) 

def add_alpha_channel_based_on_lightness(file, mode="luminocity", threshold=80):
    image = Image.open(file)
    rgba_image = image.convert("RGBA")
    pixel_data = list(rgba_image.getdata())
    updated_pixel_data = [(r, g, b, calculate_transparency(r, g, b, mode, threshold)) for r, g, b, a in pixel_data]
    rgba_image.putdata(updated_pixel_data)
    return rgba_image

def open_UI():
    root = tk.Tk()
    root.title("Digitizer")

def main():
    file_path = ask_for_image_file_path()
    rgba_image = add_alpha_channel_based_on_lightness(file_path)
    save_file_path = ask_for_image_save_path(file_path)
    rgba_image.save(save_file_path)

@app.route("/test", methods=["GET"])
def test():
    return "test"

@app.route("/upload", methods=["POST"])
def process_image():
    if "file" not in request.files:
        message = "No file uploaded"

    file = request.files["file"]

    if file.filename == "":
        message = "No file uploaded"

    if file:
        filename = file.filename
        base_filename, file_extension = os.path.splitext(filename)
        content_type = file.content_type
        mode = request.values["mode"]
        threshold = int(request.values["threshold"])
        date_string = datetime.today().date().isoformat()
        time_string = datetime.now().time().strftime("%H-%M-%S")
        # base_dir = os.path.join("static", "images", date_string)
        # Path(base_dir).mkdir(parents=True, exist_ok=True)
        # original_file_path = os.path.join(base_dir, f"{time_string}_{base_filename}_original{file_extension}")
        # file.save(original_file_path)
        processed_image = add_alpha_channel_based_on_lightness(file, mode=mode, threshold=threshold)
        # processed_file_path = os.path.join(base_dir, f"{time_string}_{base_filename}_processed.png")
        image_bytes_io = BytesIO()
        processed_image.save(image_bytes_io, format="PNG")
        base64_image = base64.b64encode(image_bytes_io.getvalue()).decode('utf-8')
        base64_image = f"data:image/png;base64,{base64_image}"
        message = f"File {filename} uploaded succesfully. Content type: {content_type}, mode: {mode}, threshold: {threshold}"
        # return send_file(image_bytes_io, mimetype="image/png", as_attachment=True, download_name="test.png")
        # path = processed_file_path
    data = {"message": message, "image": base64_image}
    print(message)
    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True, port=8080)