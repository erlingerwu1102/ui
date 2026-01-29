# Bootstrap PowerShell: create venv and install core deps
param(
    [switch]$Optional,
    [switch]$Dev
)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
if($Optional){ pip install -r requirements-optional.txt }
if($Dev){ pip install -r requirements-dev.txt }
