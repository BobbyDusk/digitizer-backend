from PIL import Image
import os
import math
from flask import Flask, request, jsonify, send_file, url_for
from flask_cors import CORS
from datetime import datetime
from pathlib import Path
from io import BytesIO
import base64
from rembg import new_session, remove
import numpy as np
import logging

app = Flask(__name__)
# CORS(app, resources={r"/*": {"origins": [r"localhost:(\d+)", r"(\w+)\.edgeofdusk\.com", "edgeofdusk.com"]}})
CORS(app)

if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

def get_file_name_without_extension(file_path:str) -> str:
    base_name = os.path.basename(file_path)
    file_name, file_extension = os.path.splitext(base_name)
    return file_name

def get_parent_directory(file_path:str) -> str:
    return os.path.dirname(file_path)

def calculate_transparency(r:int, g:int, b:int, a:int, model:str, threshold:int) -> int:
    # value between 0 and 255
    if (a == 0):
        return a
    # between 0 and 1
    max_transparency = 255
    scaled_a = a / max_transparency

    match model:
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
    return int(scaled_a * (max_transparency * (max_L - L_scaled) / max_L))

def calculate_luminocity(r:int, g:int, b:int) -> int:
    # value between 0 and 100, 100 is max luminocity 0 is min luminocity
    # Many possible calculations. This is a simple one. However, see Myndex's answer
    # for a more accurate and complete calculation
    # https://stackoverflow.com/questions/596216/formula-to-determine-perceived-brightness-of-rgb-color/37624009#37624009
    return int( (0.299 * r + 0.587 * g + 0.114 * b) / 255 * 100)

def calculate_average(r:int, g:int, b:int) -> int:
    return int(((r + g + b) / 3) / 255 * 100 )

def calculate_lightness(r:int, g:int, b:int) -> int:
    return int(((max(r, g, b) + min(r, g, b)) / 2) / 255 * 100) 

def add_alpha_channel_based_on_lightness(image:Image, model:str = "luminocity", threshold:int = 80) -> Image:
    rgba_image = image.convert("RGBA")
    pixel_data = list(rgba_image.getdata())
    updated_pixel_data = [(r, g, b, calculate_transparency(r, g, b, a, model, threshold)) for r, g, b, a in pixel_data]
    rgba_image.putdata(updated_pixel_data)
    return rgba_image

@app.route("/test", methods=["GET"])
def test() -> str:
    return "test"


def check_required_keys_present(data:dict, required_keys:list[str]) -> bool:
    for key in required_keys:
        if key not in data:
            return False
    return True

@app.route("/upload", methods=["POST"])
def process_image():
    if request.json:
        data = request.json

    # TODO: also add recursive required key check
    required_keys = [
        "image", 
        "filterWhite", 
        "removeBackground", 
    ]
    if not check_required_keys_present(data, required_keys):
        return jsonify({"message": f"One or more of the following info not included: {', '.join(required_keys)}"})

    image_front, image_string = data["image"].split(",")
    imageRaw = BytesIO(base64.b64decode(image_string))
    image = Image.open(imageRaw, formats=["JPEG", "PNG"])

    removeBackgroundParams = data["removeBackground"]
    if removeBackgroundParams["enabled"]:
        session = new_session(removeBackgroundParams["model"])
        input_points = np.array(removeBackgroundParams["points"])
        input_labels = np.array([1 for point in removeBackgroundParams["points"]])
        image = remove(image, session=session, input_points=input_points, input_labels=input_labels, post_process_mask=removeBackgroundParams["postProcess"])

    filterWhiteParams = data["filterWhite"]
    if filterWhiteParams["enabled"]:
        image = add_alpha_channel_based_on_lightness(image, model=filterWhiteParams["model"], threshold=filterWhiteParams["threshold"])

    image_bytes_io = BytesIO()
    image.save(image_bytes_io, format="PNG")
    base64_image = base64.b64encode(image_bytes_io.getvalue()).decode('utf-8')
    base64_image = f"data:image/png;base64,{base64_image}"
    message = f"image processed succesfully."
    data = {"message": message, "image": base64_image}
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True, port=8000)