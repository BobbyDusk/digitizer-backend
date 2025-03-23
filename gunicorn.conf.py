# Copyright (c) 2025, Edge of Dusk
# This project is licensed under the MIT License - see the LICENSE file for details.

from os import environ

bind = f"0.0.0.0:{environ.get('PORT', '8000')}"
workers = 1
