#!/bin/bash
gunicorn main:app -c gunicorn.conf.py