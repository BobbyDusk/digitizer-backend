# TODO: add manual remove background mode by finding contour and  then only allowing th biggest contour (or every contour bigger than X)
# TODO: for edge filter white, also account for the case where there is an internal contour by not only using external contours, but, for example, hierarchical contours
# TODO: think of best way to handle white areas in character

from PIL import Image
import os
import math
from flask import Flask, request, jsonify, send_file, url_for
from flask_cors import CORS
from datetime import datetime, time
from pathlib import Path
from io import BytesIO
import base64
from rembg import new_session, remove
import numpy as np
import logging
import numpy as np
import cv2 as cv
import zipfile

app = Flask(__name__)
# CORS(app, resources={r"/*": {"origins": [r"localhost:(\d+)", r"(\w+)\.edgeofdusk\.com", "edgeofdusk.com"]}})
CORS(app)

if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

def convert_pillow_to_openCV(pillow_image:Image) -> np.array:
    if pillow_image.mode == "RGB":
        cv_image = np.array(pillow_image)
        return cv.cvtColor(cv_image, cv.COLOR_RGB2BGR)
    elif pillow_image.mode == "RGBA":
        cv_image = np.array(pillow_image)
        return cv.cvtColor(cv_image, cv.COLOR_RGBA2BGRA)
    elif pillow_image.mode == "L":
        return np.array(pillow_image)
    elif pillow_image.mode == "1":
        pillow_image = pillow_image.convert("L")
        return np.array(pillow_image)
    else:
        raise Exception("Image mode not supported.")

def convert_openCV_to_pillow(cv_image:Image, mode) -> Image:
    if mode == "RGB":
        cv_image = cv.cvtColor(cv_image, cv.COLOR_BGR2RGB)
        return Image.fromarray(cv_image, mode)
    elif mode == "RGBA":
        cv_image = cv.cvtColor(cv_image, cv.COLOR_BGRA2RGBA)
        return Image.fromarray(cv_image, mode)
    elif mode == "L":
        return Image.fromarray(cv_image, mode)
    elif mode == "1":
        pillow_image = Image.fromarray(cv_image, "L")
        return pillow_image.convert("1", dither = Image.Dither.NONE)
    else:
        raise Exception("Image mode not supported.")

def get_contours(image:Image, threshold:int = 200, min_area_percentage:float = 0.001):
    min_area = image.height * image.width * min_area_percentage / 100
    print(min_area)
    image = image.convert("L")
    cv_image = convert_pillow_to_openCV(image)
    retval, threshold_image = cv.threshold(src=cv_image, thresh=threshold, maxval=255, type=cv.THRESH_BINARY_INV)
    contours, hierarchy = cv.findContours(image=threshold_image, mode=cv.RETR_EXTERNAL, method=cv.CHAIN_APPROX_NONE)
    contours = [contour for contour in contours if cv.contourArea(contour) > min_area]
    contours = sorted(contours, key=lambda contour: cv.contourArea(contour), reverse=True)
    return contours

def slice_and_crop(image, threshold:int = 200, min_area_percentage:float = 0.001):
    contours = get_contours(image, threshold, min_area_percentage)
    images = []
    cv_image = convert_pillow_to_openCV(image)
    cv_image = cv.cvtColor(cv_image, cv.COLOR_BGR2BGRA)
    for contour in contours:
        cv_mask_image = np.zeros((image.height, image.width, 1), dtype = "uint8")
        blank_image = np.zeros((image.height, image.width, 4), dtype = "uint8")
        cv_mask_image = cv.drawContours(image=cv_mask_image, contours=[contour], contourIdx=-1, color=255, thickness=cv.FILLED)
        masked_image = cv.bitwise_or(blank_image, cv_image, mask=cv_mask_image)
        x, y, w, h = cv.boundingRect(contour)
        cropped_image = masked_image[y:y+h, x:x+w]
        result_image = convert_openCV_to_pillow(cropped_image, mode="RGBA")
        images.append(result_image)
    return images

def get_contours_of_alpha(image:Image):
    image = image.getchannel("A")
    image = image.convert("1", dither = Image.Dither.NONE)
    cv_image = convert_pillow_to_openCV(image)
    contours, hierarchy = cv.findContours(image=cv_image, mode=cv.RETR_EXTERNAL, method=cv.CHAIN_APPROX_NONE)
    return contours

def get_contours_mask_of_alpha(image:Image, thickness = 1):
    # sadly, cv.drawContours cannot draw on grayscale imaga
    contours = get_contours_of_alpha(image)
    cv_mask_image = np.zeros((image.height, image.width, 3), dtype = "uint8")
    cv_mask_image = cv.drawContours(image=cv_mask_image, contours=contours, contourIdx=-1, color=(255, 255, 255), thickness=thickness)
    mask_image = convert_openCV_to_pillow(cv_mask_image, mode="RGB")
    mask_image = mask_image.getchannel("R")
    return mask_image

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

def filter_white_in_edge(image:Image, border_width:int = 3, threshold:int = 150, max:int = 240) -> Image:
    contours_mask_image = get_contours_mask_of_alpha(image, thickness=border_width)
    L_image = image.convert("LA")
    for y in range(image.height):
        for x in range(image.width):
            if contours_mask_image.getpixel((x, y)) == 255:
                pixel = image.getpixel((x, y))
                a = calculate_transparency(L_image, x, y, "pillow", threshold, max)
                new_pixel = (pixel[0], pixel[1], pixel[2], a)
                image.putpixel((x, y), new_pixel)
    return image

@app.route("/test", methods=["GET"])
def test() -> str:
    return "test"


def check_required_keys_present(data:dict, required_keys:list[str]) -> bool:
    for key in required_keys:
        if key not in data:
            return False
    return True

def automatically_process_image(image):
    cropped_images = slice_and_crop(image)
    images = []
    for image in cropped_images:
        image = filter_white_in_edge(image=image, border_width=4, threshold=100, max=195)
        images.append(image)
    base64_images = []
    for image in images:
        image_base64 = convert_image_to_base64(image)
        base64_images.append(image_base64)
    base64_zip = create_zip_base_64(images)
    return base64_images, base64_zip

def manually_process_image(image, data):
    cropParams = data["crop"]
    if (cropParams["enabled"]):
        cropBox = (cropParams["left"], cropParams["top"], cropParams["left"] + cropParams["width"], cropParams["top"] + cropParams["height"])
        image = image.crop(cropBox)
   
    # necessary in order to limit the required processing power
    MAX_SIZE = 2000
    if (image.height > MAX_SIZE or image.width > MAX_SIZE):
        # https://pillow.readthedocs.io/en/latest/handbook/concepts.html#filters
        image.thumbnail([MAX_SIZE, MAX_SIZE], resample=Image.Resampling.LANCZOS)

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
        bbox = image.getbbox(alpha_only=True)
        border_width = 2
        image = image.crop((bbox[0] - border_width, bbox[1] - border_width,  bbox[2] + border_width, bbox[3] + border_width))
        
    resizeParams = data["resize"]
    if (resizeParams["enabled"]):
        image.thumbnail((resizeParams["width"], resizeParams["height"]), resample=Image.Resampling.LANCZOS)

    image_base64 = convert_image_to_base64(image)
    base64_zip = create_zip_base_64([image])
    return [image_base64], base64_zip

def get_image_from_data(data) -> Image:
    image_front, image_string = data["image"].split(",")
    imageRaw = BytesIO(base64.b64decode(image_string))
    image = Image.open(imageRaw, formats=["JPEG", "PNG"])
    return image

def convert_image_to_memory_file(image: Image) -> BytesIO:
    image_bytes_io = BytesIO()
    image.save(image_bytes_io, format="PNG")
    image_bytes_io.seek(0)
    return image_bytes_io

def convert_image_to_base64(image: Image) -> str:
    mem_file = convert_image_to_memory_file(image)
    base64_image = base64.b64encode(mem_file.getvalue()).decode('utf-8')
    base64_image = f"data:image/png;base64,{base64_image}"
    return base64_image

def create_zip_base_64(images: [Image]) -> str:
    memory_zip_file = BytesIO()
    with zipfile.ZipFile(memory_zip_file, 'w') as zf:
        index = 0
        for image in images:
            index += 1
            filename = f"image_{index}.png"
            mem_file = convert_image_to_memory_file(image)
            zf.writestr(filename, mem_file.getvalue())
    memory_zip_file.seek(0)
    base64_zip = base64.b64encode(memory_zip_file.getvalue()).decode('utf-8')
    base64_zip = f"data:application/zip;base64,{base64_zip}"
    return base64_zip

@app.route("/upload", methods=["POST"])
def process_image():
    if request.json:
        data = request.json

    # TODO: also add recursive required key check
    required_keys = [
        "image", 
        "mode", 
    ]
    if not check_required_keys_present(data, required_keys):
        return jsonify({"message": f"One or more of the following info not included: {', '.join(required_keys)}"})

    image = get_image_from_data(data)

    if (data["mode"] == "automatic"):
        images, zip = automatically_process_image(image)
        message = f"image processed succesfully."
        data = {"message": message, "images": images, "zip": zip}

    elif (data["mode"] == "manual"):
        images, zip = manually_process_image(image, data)
        message = f"image processed succesfully."
        data = {"message": message, "images": images, "zip": zip}
    
    else:
        message = f"Error: provided mode {data['mode']} not supported."
        data = {"message": message}
       
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True, port=8000)