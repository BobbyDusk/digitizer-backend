# TODO: replace luminicity calculation by conversion to "L"
# TODO: getbbox instead of own custon function
# TODO: replace contour detection with opencv contour detection or pillow filter contour
# TODO: automatically detect different objects by first making backkground black and then using opencv.contours()

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
import numpy as np
import cv2 as cv

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

def calculate_L(r, g, b, model:str):
    match model:
        case "lightness":
            L = calculate_lightness(r, g, b)
        case "average":
            L = calculate_average(r, g, b)
        case "luminocity":
            L = calculate_luminocity(r, g, b)
        case _:
            L = calculate_luminocity(r, g, b)
    return L

def calculate_transparency(image:Image, x:int, y:int , model:str, threshold:int, max:int) -> int:
    if image.mode == "RGB":
        r, g, b = image.getpixel((x, y))
        a = 255
        L = calculate_L(r, g, b, model)
    elif image.mode == "RGBA":
        r, g, b, a = image.getpixel((x, y))
        L = calculate_L(r, g, b, model)
    elif image.mode == "L":
        a = 255
        L = image.getpixel((x, y))
    elif image.mode == "LA":
        L, a = image.getpixel((x, y))
    else:
        raise Exception(f"Provided image has mode {image.mode}, which is not supported.")

    # If original opacity is 0, leave it
    if (a == 0):
        return a
    #values lighter than max have 0 opacity
    if (L >= max):
        return 0

    # values darker than threshold are left at original opacity
    if (L <= threshold):
        return a

    # values with lightness between threshold and max are scaled
    range = max - threshold
    relative_L = L - threshold
    scaled_relative_L = relative_L / range # between 0 and 1
    scaled_L = scaled_relative_L * 255
    scaled_a = a / 255 # between 0 and 1
    return int(scaled_a * (255 - scaled_L))

def calculate_luminocity(r:int, g:int, b:int) -> int:
    # Many possible calculations. This is a simple one. However, see Myndex's answer
    # for a more accurate and complete calculation
    # https://stackoverflow.com/questions/596216/formula-to-determine-perceived-brightness-of-rgb-color/37624009#37624009
    return int(0.299 * r + 0.587 * g + 0.114 * b)

def calculate_average(r:int, g:int, b:int) -> int:
    return int((r + g + b) / 3)

def calculate_lightness(r:int, g:int, b:int) -> int:
    return int((max(r, g, b) + min(r, g, b)) / 2) 

def add_alpha_channel_based_on_lightness(image:Image, model:str = "pillow", threshold:int = 230, max:int = 255) -> Image:
    result = Image.new('RGBA', (image.width, image.height))
    
    if (model == "pillow"):
        L_image = image.convert("LA")
        L_image.save("test.png")

    for y in range(image.height):
        for x in range(image.width):
            pixel = image.getpixel((x, y))
            if (model == "pillow"):
                a = calculate_transparency(L_image, x, y, model, threshold, max)
            else:
                a = calculate_transparency(image, x, y, model, threshold, max)
            result.putpixel((x, y), (pixel[0], pixel[1], pixel[2], a))
    return result

def filter_white_in_edge(image:Image, border_width:int = 2, threshold:int = 150, max:int = 240) -> Image:
    # TODO: improve computation with larger border_width
    pixel_positions_to_change:list(tuple(int, int)) = []
    for y in range(image.height):
        for x in range(image.width):
            pixel = image.getpixel((x, y))
            if (pixel[3] > 10):
                found = False
                for y_offset in range(-1 * border_width, border_width + 1, 1):
                    if (found):
                        break
                    for x_offset in range(-1 * border_width, border_width + 1, 1):
                        comparisonY = y + y_offset
                        comparisonX = x + x_offset
                        if (comparisonY >= 0 and comparisonY < image.height and comparisonX >= 0 and comparisonX < image.width):
                            comparison_pixel = image.getpixel((comparisonX, comparisonY))
                            if (comparison_pixel[3] <= 10):
                                pixel_positions_to_change.append((x, y))
                                found = True
                                break

    L_image = image.convert("L")
    for pos in pixel_positions_to_change:
        pixel = image.getpixel((pos[0], pos[1]))
        a = calculate_transparency(L_image, pos[0], pos[1], "pillow", threshold, max)
        new_pixel = (pixel[0], pixel[1], pixel[2], a)
        image.putpixel((pos[0], pos[1]), new_pixel)

    return image


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

    cropParams = data["crop"]
    if (cropParams["enabled"]):
        cropBox = (cropParams["left"], cropParams["top"], cropParams["left"] + cropParams["width"], cropParams["top"] + cropParams["height"])
        image = image.crop(cropBox)
   
    # necessary in order to limit the required processing power
    MAX_SIZE = 2000
    if (image.height > MAX_SIZE or image.width > MAX_SIZE):
        image.thumbnail([MAX_SIZE, MAX_SIZE])

    removeBackgroundParams = data["removeBackground"]
    if (removeBackgroundParams["enabled"]):
        session = new_session(removeBackgroundParams["model"])
        input_points = np.array(removeBackgroundParams["points"])
        input_labels = np.array([1 for point in removeBackgroundParams["points"]])
        image = remove(image, session=session, input_points=input_points, input_labels=input_labels, post_process_mask=removeBackgroundParams["postProcess"])

        if (removeBackgroundParams["edgeWhiteFilter"]):
            image = filter_white_in_edge(image, border_width=removeBackgroundParams["edgeWhiteFilterWidth"], threshold=removeBackgroundParams["edgeWhiteFilterThreshold"], max=removeBackgroundParams["edgeWhiteFilterMax"])

    filterWhiteParams = data["filterWhite"]
    if (filterWhiteParams["enabled"]):
        image = add_alpha_channel_based_on_lightness(image, model=filterWhiteParams["model"], threshold=filterWhiteParams["threshold"], max=filterWhiteParams["max"])

    if (cropParams["enabled"] and cropParams["autoEnabled"] and image.mode == "RGBA"):
        top = image.height
        left = image.width
        bottom = 0
        right = 0
        for y in range(image.height):
            for x in range(image.width):
                r, g, b, a = image.getpixel((x, y))
                if (a > cropParams["threshold"]):
                    top = min(top, y)
                    left = min(left, x)
                    bottom = max(bottom, y)
                    right = max(right, x)
        if (bottom != 0): # non-transparent pixel found
            borderWidth = 2
            image = image.crop((left - borderWidth, top - borderWidth, right + borderWidth, bottom + borderWidth))

    resizeParams = data["resize"]
    if (resizeParams["enabled"]):
        image.thumbnail((resizeParams["width"], resizeParams["height"]))

    image_bytes_io = BytesIO()
    image.save(image_bytes_io, format="PNG")
    base64_image = base64.b64encode(image_bytes_io.getvalue()).decode('utf-8')
    base64_image = f"data:image/png;base64,{base64_image}"
    message = f"image processed succesfully."
    data = {"message": message, "image": base64_image}
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True, port=8000)