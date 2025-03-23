#!/bin/bash

# Copyright (c) 2025, Edge of Dusk
# This project is licensed under the MIT License - see the LICENSE file for details.

gunicorn main:app -c gunicorn.conf.py