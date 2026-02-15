# Image Converter Pro

![GitHub release](https://img.shields.io/github/v/release/raja5667/Image-Converter)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-yellow)

A PyQt6-based desktop application for converting images between multiple formats with a clean UI and fast processing.

---

## Features

- Convert images between:
  - JPG
  - PNG
  - WEBP
  - BMP
  - TIFF
- Simple and modern PyQt6 interface
- Fast conversion engine
- Cancel conversion support
- Status feedback messages
- Windows executable build support

---

## Requirements

- Python 3.12.x (Recommended)
- Windows 10 / 11
- pip (latest version recommended)

> ⚠️ Avoid Python 3.13 if you face compatibility issues with PyQt6 or PyInstaller.

---

## Project Structure

```
Image-Converter/
│
├── image_converter_pro.py
├── requirements.txt
├── app_icon.ico
├── icons/
├── .gitignore
└── README.md
```

---

## Setup (Windows)

### 1. Clone Repository

```bash
git clone https://github.com/raja5667/Image-Converter.git
cd Image-Converter
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

### 3. Activate Virtual Environment

```bash
venv\Scripts\activate
```

### 4. Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## Run the Application

```bash
python image_converter_pro.py
```

---

## Build Windows Executable (.exe)

Make sure PyInstaller is installed:

```bash
pip install pyinstaller
```

Then build:

```bash
pyinstaller --onefile --windowed --icon=app_icon.ico --name "IMG Converter" image_converter_pro.py
```

The final executable will be inside:

```
dist/
```

---

## Troubleshooting

### App not starting?
- Make sure Python 3.12 is installed.
- Ensure virtual environment is activated.
- Reinstall dependencies.

### Icons not loading?
- Keep the `icons/` folder in the same directory while running in development mode.
- For PyInstaller builds, ensure assets are included properly.

---

## Development Notes

- Main GUI logic: `image_converter_pro.py`
- Uses PyQt6 for UI
- Designed for Windows desktop environment
- Virtual environment recommended

---

## License

This project is licensed under the MIT License.

---

## Author

Developed by Raja  
GitHub: https://github.com/raja5667
