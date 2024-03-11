from os import environ

bind = f"0.0.0.0:{environ.get('PORT', '8000')}"
workers = 1
