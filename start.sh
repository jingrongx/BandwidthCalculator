#!/bin/bash
# Navigate to the application directory
cd /home/mystic/code/vxrail/bandwidth_calculator/

# Activate the virtual environment
source .venv/bin/activate

# Start Gunicorn
exec gunicorn -w 4 -b 0.0.0.0:5000 app:app
