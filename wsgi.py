#!/usr/bin/python3

"""
WSGI configuration for PythonAnywhere deployment.

This file contains the WSGI configuration required to serve the Flask blog application.
Make sure to update the project paths according to your PythonAnywhere username and directory structure.
"""

import sys
import os

# Add your project directory to the sys.path
# Replace 'yourusername' with your actual PythonAnywhere username
# Replace 'blogcms' with your actual project directory name
project_home = '/home/yourusername/blogcms'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set environment variables for production
os.environ.setdefault('FLASK_ENV', 'production')

# Import flask app instance but rename it to 'application' for WSGI
from app import app as application

# For debugging purposes, you can uncomment the following lines:
# import logging
# logging.basicConfig(level=logging.INFO)
# application.logger.info('WSGI application started')

if __name__ == "__main__":
    application.run()