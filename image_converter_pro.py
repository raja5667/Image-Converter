import sys
import traceback
import time
import math
from pathlib import Path
from PIL import Image, UnidentifiedImageError, ImageQt 
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QSize,
    QPropertyAnimation, pyqtProperty, QTimer, QEasingCurve
)
from PyQt6.QtGui import QPixmap, QIcon, QPainter, QPen, QColor, QLinearGradient, QBrush
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QComboBox, QMessageBox, QListWidget, QListWidgetItem,
    QProgressBar, QSizePolicy, QFrame, QStackedLayout, QGraphicsDropShadowEffect
)

# ----------------------------------------------------------------------
# SECURITY AND ROBUSTNESS ENHANCEMENTS (PILLOW)
# ----------------------------------------------------------------------

def get_resource_path(relative_path: str) -> str:
        """
        Returns absolute path to resource, works for:
        - Development
        - PyInstaller --onefile
        - PyInstaller --onedir
        """
        if getattr(sys, 'frozen', False):
            # Running as compiled EXE
            base_path = Path(sys._MEIPASS)
        else:
            # Running as normal Python script
            base_path = Path(__file__).parent
    
        return str(base_path / relative_path)

Image.MAX_IMAGE_PIXELS = 1024 * 1024 * 500

def detect_heif_support():
    """Dynamically register HEIF opener if pillow_heif is installed."""
    try:
        import pillow_heif  # type: ignore
        pillow_heif.register_heif_opener()
        return True
    except Exception:
        return False

HEIF_SUPPORTED = detect_heif_support()

SUPPORTED_FORMATS = [
    ("Select Format", None),
    ("PNG", "png"),
    ("JPEG", "jpg"),
    ("WEBP", "webp"),
    ("BMP", "bmp"),
    ("TIFF", "tiff"),
    ("GIF", "gif"),
    ("ICO", "ico"),
    ("PDF", "pdf")
]

# ----------------------------------------------------------------------
# QTHREAD WORKER FOR CONVERSION
# ----------------------------------------------------------------------

class ConvertWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    done = pyqtSignal(bool, str)

    def __init__(self, files, out_format, out_folder=None, quality=95):
        super().__init__()
        self.files = list(files)
        self.out_format = out_format.lower() if out_format else None
        self.out_folder = Path(out_folder) if out_folder else None
        self.quality = quality
        self.MIN_DURATION = 10.0  
        self._is_canceled = False

    def run(self):
        for i in range(8, 0, -1):
            self.status.emit("Wait for a moment...")
            self.progress.emit(int(((8 - i) / 8) * 80))
            time.sleep(1)
 
        self._cancel_locked = True

        if not self.out_format:
            self.done.emit(False, "Error: No output format selected.")
            return

        total = len(self.files)
        successful_conversions = 0
        final_conversion_pct = 0
        start_time = time.monotonic()

        try:
            for idx, fpath in enumerate(self.files, start=1):
                fname = Path(fpath).name
                try:
                    self.convert_one(Path(fpath))
                    successful_conversions += 1
            
                except UnidentifiedImageError:
                    error_msg = f"Skipped: {fname}. Unidentified or corrupted file format."
                    print(error_msg)
                    self.status.emit(error_msg)
                except OSError as e:
                    error_msg = f"Skipped: {fname}. File read/write error (OSError: {e})."
                    print(error_msg)
                    self.status.emit(error_msg)
                except Exception:
                    error_msg = f"Error converting {fname}. See console for details."
                    print(traceback.format_exc())
                    self.status.emit(error_msg)
                
                pct = 80 + int((idx / total) * 19)
                if pct > 99:
                    pct = 99
                self.progress.emit(pct)
                final_conversion_pct = pct
                time.sleep(0.01)

            conversion_duration = time.monotonic() - start_time
            required_delay = self.MIN_DURATION - conversion_duration

            if required_delay > 0:
                start_pct = final_conversion_pct if final_conversion_pct >= 1 else 1
            
                steps = 30
                step_delay = required_delay / steps
                pct_increment = (100 - start_pct) / steps
            
                dots = ["", ".", "..", "..."]
                dot_index = 0
            
                for i in range(1, steps + 1):
                    time.sleep(step_delay)
            
                    self.status.emit(f"<b style='color:orange;'>Your images are preparing{dots[dot_index]}</b>")
                    dot_index = (dot_index + 1) % len(dots)
            
                    new_pct = int(start_pct + pct_increment * i)
                    if new_pct > 99:
                        new_pct = 99
                    self.progress.emit(new_pct)

            self.progress.emit(100)
            
            if successful_conversions == total:
                result_msg = "All conversions completed successfully."
                self.done.emit(True, result_msg)
            elif successful_conversions > 0:
                result_msg = f"Conversion finished. Successfully converted {successful_conversions} of {total} files."
                self.done.emit(True, result_msg)
            else:
                result_msg = "Conversion failed for all files. Check file integrity or permissions."
                self.done.emit(False, result_msg)

        except Exception as e:
            print(f"FATAL WORKER ERROR: {traceback.format_exc()}")
            self.done.emit(False, "Critical error during batch process. See console.")

    def convert_one(self, p: Path):
        with Image.open(p) as img:
            fmt = self.out_format
            save_kwargs = {}

            if self.out_folder:
                out_path = self.out_folder / (p.stem + "." + fmt)
            else:
                out_path = p.with_suffix("." + fmt)
            
            img_to_save = img
            
            if fmt in ("jpg", "jpeg"):
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    if img.mode == "P" and "transparency" in img.info:
                        img_to_convert = img.convert("RGBA")
                    else:
                        img_to_convert = img.convert("RGBA") if img.mode != "RGBA" else img
                        
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    
                    background.paste(img_to_convert, mask=img_to_convert.split()[3]) 
                    img_to_save = background
                else:
                    img_to_save = img.convert("RGB")
            
            if fmt == "pdf":
                if img_to_save.mode in ("RGBA", "LA", "P"):
                    img_to_save = img_to_save.convert("RGB")
                img_to_save.save(out_path, "PDF", resolution=100.0)
                return

            if fmt in ("webp", "jpg", "jpeg"):
                save_kwargs["quality"] = self.quality

            img_to_save.save(out_path, **save_kwargs)

# ----------------------------------------------------------------------
# CUSTOM UI WIDGETS
# ----------------------------------------------------------------------

class GradientFrame(QFrame):
    """Frame with a styled gradient background."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setObjectName("gradientFrame")

class AnimatedGradientButton(QPushButton):
    """A button with an animated gradient border (lighting effect)."""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._shift = 0.0 
        self._is_animating = False

        self.anim = QPropertyAnimation(self, b"shift", self)
        self.anim.setDuration(2000)
        self.anim.setStartValue(0)
        self.anim.setEndValue(100)
        self.anim.setLoopCount(-1)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        self.setStyleSheet("""
            QPushButton {
                border-radius: 10px;
                padding: 8px 12px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255,255,255,0.06), stop:1 rgba(255,255,255,0.02));
                border: 2px solid rgba(0,0,0,0);
                color: #9ffcff;
                font-size: 16px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255,255,255,0.09), stop:1 rgba(255,255,255,0.03));
            }
        """)

    @pyqtProperty(float)
    def shift(self):
        return self._shift
    
    @shift.setter
    def shift(self, val):
        self._shift = float(val)
        self.update()

    def start_animation(self):
        if not self._is_animating:
            self._is_animating = True
            self.anim.start()
            self.update()

    def stop_animation(self):
        if self._is_animating:
            self._is_animating = False
            self.anim.stop()
            self._shift = 0.0
            self.update()
 
    def paintEvent(self, event):
        super().paintEvent(event)
    
        if not self._is_animating:
            return
    
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
        rect = self.rect().adjusted(2, 2, -2, -2)
    
        s = (self._shift % 100) / 100  
    
        full_gradient_width = rect.width() * 2 
        shift = full_gradient_width * s
    
        gradient = QLinearGradient(
            rect.left() - shift,
            rect.center().y(),
            rect.left() - shift + full_gradient_width,
            rect.center().y()
        )
    
        gradient.setColorAt(0.00, QColor("#ff007f"))  
        gradient.setColorAt(0.15, QColor("#ff9900"))  
        gradient.setColorAt(0.35, QColor("#00ffcc")) 
        gradient.setColorAt(0.50, QColor("#8a2be2"))  
        gradient.setColorAt(0.65, QColor("#ff007f"))  
        gradient.setColorAt(0.85, QColor("#ff9900"))  
        gradient.setColorAt(1.00, QColor("#00ffcc"))  
        
        pen = QPen()
        pen.setWidth(4)
        pen.setBrush(gradient)
        painter.setPen(pen)
    
        painter.drawRoundedRect(rect, 10, 10)

class ClickableDropLabel(QLabel):
    """Label for file dropping and clicking to open dialog."""
    clicked = pyqtSignal()

    def __init__(self, text, parent=None):
        super().__init__(text, parent)

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumSize(400, 400)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._angle = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_rotation)
        self.timer.start(100) 

        self.setStyleSheet("""
            QLabel {
                font-size: 15px;
                color: #bfeaff;
                padding: 16px;
                background: transparent;
            }
        """)

    def update_rotation(self):
        self._angle = (self._angle + 2) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()

        center = rect.center()
        radius = max(rect.width(), rect.height())

        rad = math.radians(self._angle)
        x = center.x() + radius * math.cos(rad)
        y = center.y() + radius * math.sin(rad)

        gradient = QLinearGradient(center.x(), center.y(), x, y)

        # Your gradient colors
        gradient.setColorAt(0.0, QColor("#000000"))
        gradient.setColorAt(0.12, QColor("#01030a"))
        gradient.setColorAt(0.30, QColor("#020a1d"))
        gradient.setColorAt(0.50, QColor("#041633"))
        gradient.setColorAt(0.70, QColor("#062552"))
        gradient.setColorAt(0.85, QColor("#0a3b72"))
        gradient.setColorAt(1.0, QColor("#0f56a5"))
        painter.setOpacity(0.88)
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)

        painter.setPen(QColor("#bfeaff"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.text())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

class ImagePreviewLabel(QLabel):
    """Label that scales its pixmap to fit the space."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(400, 400)
        self.pixmap_data = None

    def setPixmap(self, pixmap):
        self.pixmap_data = pixmap
        self.update_scaled_pixmap()

    def resizeEvent(self, event):
        if self.pixmap_data:
            self.update_scaled_pixmap()
        super().resizeEvent(event)

    def update_scaled_pixmap(self):
        if self.pixmap_data and not self.pixmap_data.isNull():
            target_size = self.size() - QSize(40, 40) 
            scaled = self.pixmap_data.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            super().setPixmap(scaled)
        else:
            super().setPixmap(QPixmap())

class DotRingSpinner(QWidget):
    """Loading spinner with a semi-transparent background overlay."""
    def __init__(self, parent=None):
        super().__init__(parent)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.frame = 0

        self.setStyleSheet("background-color: rgba(0,0,0,128);")

        self.hide()

    def start(self):
        self.frame = 0
        self.timer.start(70)
        self.resize_to_parent()
        self.show()
        self.raise_()

    def stop(self):
        self.frame = 0 
        self.timer.stop()
        self.hide()

    def resize_to_parent(self):
        if self.parent():
            self.setGeometry(self.parent().rect())

    def resizeEvent(self, event):
        self.resize_to_parent()

    def update_animation(self):
        self.frame = (self.frame + 1) % 12
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        dot_count = 12
        radius = 40
        dot_size = 10
        center = self.rect().center()

        for i in range(dot_count):
            opacity = max(0.15, (i + self.frame) % dot_count / dot_count) 

            painter.setPen(Qt.PenStyle.NoPen)

            color = QColor(0, 255, 255) 
            color.setAlphaF(opacity)
            painter.setBrush(color)

            angle_deg = (360 / dot_count) * i
            rad = math.radians(angle_deg)

            x = center.x() + radius * math.cos(rad)
            y = center.y() + radius * math.sin(rad)

            painter.drawEllipse(
                int(x - dot_size / 2),
                int(y - dot_size / 2),
                dot_size,
                dot_size
            )

# ----------------------------------------------------------------------
# MAIN APPLICATION WINDOW (Updated)
# ----------------------------------------------------------------------

class NeonCyberGlowButton(QPushButton):
    def __init__(self, text="Cyber Glow", color="#00eaff", parent=None):
        super().__init__(text, parent)

        self._glow = 25
        self.neon_color = color

        self.setMinimumHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #0a0a0a;
                color: {color};
                border: 3px solid {color};
                border-radius: 14px;
                font-size: 14px;
                font-weight: bold;
            }}
        """)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setColor(QColor(color))
        self.shadow.setBlurRadius(self._glow)
        self.shadow.setOffset(0, 0)
        self.setGraphicsEffect(self.shadow)

        self.anim = QPropertyAnimation(self, b"glow")
        self.anim.setDuration(350)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def enterEvent(self, event):
        self.anim.stop()
        self.anim.setStartValue(self._glow)
        self.anim.setEndValue(60)
        self.anim.start()

    def leaveEvent(self, event):
        self.anim.stop()
        self.anim.setStartValue(self._glow)
        self.anim.setEndValue(25)
        self.anim.start()

    def getGlow(self):
        return self._glow

    def setGlow(self, value):
        self._glow = value
        self.shadow.setBlurRadius(value)

    glow = pyqtProperty(int, fget=getGlow, fset=setGlow)

class NeonButton(QPushButton):
    def __init__(self, text="", neon_color=QColor(0, 200, 255), parent=None):
        super().__init__(text, parent)
        self._glow = 0.0
        self.neon_color = QColor(neon_color)

        self.setStyleSheet(f"""
            QPushButton {{
                color: white;
                font-weight: 700;
                font-size: 15px;
                padding: 10px 20px;
                border-radius: 12px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(10,10,10,220),
                    stop:1 rgba(30,30,30,220)
                );
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(20,20,20,230),
                    stop:1 rgba(40,40,40,230)
                );
            }}
        """)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.glow_effect = QGraphicsDropShadowEffect(self)
        self.glow_effect.setOffset(0, 0)
        self.glow_effect.setBlurRadius(20)
        glow_color = QColor(self.neon_color)
        glow_color.setAlpha(120)
        self.glow_effect.setColor(glow_color)
        self.setGraphicsEffect(self.glow_effect)

        self.anim = QPropertyAnimation(self, b"glow", self)
        self.anim.setStartValue(0.0)
        self.anim.setKeyValueAt(0.5, 1.0)
        self.anim.setEndValue(0.0)
        self.anim.setDuration(2200)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.anim.setLoopCount(-1)
        self.anim.start()

    def getGlow(self):
        return self._glow

    def setGlow(self, value):
        self._glow = value

        min_blur, max_blur = 12, 48
        blur = min_blur + (max_blur - min_blur) * value

        min_alpha, max_alpha = 25, 200
        alpha = int(min_alpha + (max_alpha - min_alpha) * value)

        glow_color = QColor(self.neon_color)
        glow_color.setAlpha(alpha)
        self.glow_effect.setBlurRadius(blur)
        self.glow_effect.setColor(glow_color)

    glow = pyqtProperty(float, fget=getGlow, fset=setGlow)

class PerfectNeonButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)

        self._offset = 0 

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)

        self.text_color_normal = "#b9ffff"
        self.text_color_pressed = "#8BCCCC"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {self.text_color_normal};
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 1px;
            }}
        """)

        self.anim = QPropertyAnimation(self, b"offset", self)
        self.anim.setDuration(120)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)

    def getOffset(self):
        return self._offset

    def setOffset(self, val):
        self._offset = val
        self.update()

    offset = pyqtProperty(int, fget=getOffset, fset=setOffset)

    def mousePressEvent(self, e):
        self.anim.stop()
        self.anim.setStartValue(self._offset)
        self.anim.setEndValue(2)
        self.anim.start()
        return super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self.anim.stop()
        self.anim.setStartValue(self._offset)
        self.anim.setEndValue(0)
        self.anim.start()
        return super().mouseReleaseEvent(e)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.translate(0, self._offset)

        rect = self.rect().adjusted(4, 4, -4, -4)
        radius = 6

        dark_factor = 0.75 if self._offset > 0 else 1.0

        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0.0, QColor(0, int(245*dark_factor), int(255*dark_factor)))
        gradient.setColorAt(0.5, QColor(0, int(255*dark_factor), int(220*dark_factor)))
        gradient.setColorAt(1.0, QColor(0, int(255*dark_factor), int(150*dark_factor)))

        pen = QPen(QBrush(gradient), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.drawRoundedRect(rect, radius, radius)

        painter.setPen(QColor(self.text_color_pressed if self._offset > 0 else self.text_color_normal))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())

        painter.end()    

class ImageConverterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Format Converter")
        self.files = []  
        self.worker = None
        self.dest_folder = None
        self.block_status_updates = False
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setFixedSize(960, 560)
        self.setup_ui()

    def reset_all(self):
        """Fully reset UI after conversion timeout."""
        self.files.clear()
        self.list_widget.clear()
        self.preview_label.setPixmap(QPixmap())
        self.image_stack_layout.setCurrentIndex(0)
        self.progress.setValue(0)
        self.status_label.setText("Ready")
        self.dest_folder = None
        self.dest_label.setText("Save: Next to originals")
        self.format_box.setCurrentIndex(0)
        self.convert_btn.stop_animation()    

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        left_frame = GradientFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(18, 18, 18, 18)

        self.preview_label = ImagePreviewLabel()
        self.add_image_placeholder = ClickableDropLabel("Drop images here\nor click anywhere to 'Add Images'")
        self.add_image_placeholder.clicked.connect(self.on_add_images)
        
        self.image_stack_layout = QStackedLayout()
        self.image_stack_layout.addWidget(self.add_image_placeholder)
        self.image_stack_layout.addWidget(self.preview_label)
        self.image_stack_layout.setCurrentIndex(0)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addLayout(self.image_stack_layout)
        
        self.overlay = QWidget() 
        self.overlay_layout = QStackedLayout(self.overlay)

        self.loading_spinner = DotRingSpinner(self.overlay)
        self.loading_spinner.hide()
        
        # Stack 0: Main content (preview/placeholder)
        self.overlay_layout.addWidget(content_widget)
        # Stack 1: Loading Spinner (which has its own semi-transparent background)
        self.overlay_layout.addWidget(self.loading_spinner)
        
        self.overlay_layout.setCurrentIndex(0)
        
        left_layout.addWidget(self.overlay)

        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(140)
        self.list_widget.itemSelectionChanged.connect(self.on_list_selection_changed)
        left_layout.addWidget(self.list_widget)

        right_frame = QFrame()
        right_frame.setMaximumWidth(360)
        right_frame.setMinimumWidth(360)
        right_frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(22, 22, 22, 22)
        right_layout.setSpacing(12)

        # Buttons with object names for robust state management
        self.add_folder_btn = NeonCyberGlowButton("Add Folder", color="#00eaff")
        self.add_folder_btn.clicked.connect(self.on_add_folder)
        
        self.remove_btn = NeonCyberGlowButton("Remove Selected", color="#ff1f8f")
        self.remove_btn.clicked.connect(self.on_remove_selected)
        
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.add_folder_btn)
        btn_row.addWidget(self.remove_btn)
        right_layout.addLayout(btn_row)

        fmt_label = QLabel("Select Output Format:")
        fmt_label.setStyleSheet("font-weight:600;")
        right_layout.addWidget(fmt_label)

        self.format_box = QComboBox()
        self.format_box.setObjectName("FormatComboBox")
        for name, ext in SUPPORTED_FORMATS:
            if ext:
                self.format_box.addItem(f"{name} (.{ext})", ext)
            else:
                self.format_box.addItem(name, ext)
        self.format_box.setCurrentIndex(0)
        self.format_box.setCursor(Qt.CursorShape.PointingHandCursor)
        right_layout.addWidget(self.format_box)

        dest_row = QHBoxLayout()
        self.dest_label = QLabel("Save: Next to originals")
        self.dest_label.setWordWrap(True)
        self.dest_btn = PerfectNeonButton("CHOOSE FOLDER")
        self.dest_btn.clicked.connect(self.on_choose_folder)
        self.dest_btn.setObjectName("ChooseFolderBtn")
        dest_row.addWidget(self.dest_label, 1)
        dest_row.addWidget(self.dest_btn)
        right_layout.addLayout(dest_row)

        quality_row = QHBoxLayout()
        self.quality_label = QLabel("Quality: 95")
        quality_row.addWidget(self.quality_label)
        right_layout.addLayout(quality_row)
        fmt_label.setProperty("neonLabel", True)
        self.dest_label.setProperty("neonLabel", True)
        self.quality_label.setProperty("neonLabel", True)
        
        self.convert_btn = AnimatedGradientButton("Convert") # Changed to AnimatedGradientButton
        self.convert_btn.setObjectName("ConvertBtn")
        self.convert_btn.clicked.connect(self.on_convert)
        
        self.cancel_btn = NeonButton("Cancel", neon_color=QColor(255, 70, 70))  # Red neon
        self.cancel_btn.setFixedHeight(46)
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)
        self.cancel_btn.hide()
        
        self.cancel_btn.setObjectName("CancelBtn")
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)
        # Cancel button is hidden until conversion starts
        self.cancel_btn.hide()

        right_layout.addWidget(self.cancel_btn)
        right_layout.addWidget(self.convert_btn)

        self.progress = QProgressBar()
        self.progress.setObjectName("ProgressBar")
        self.progress.setValue(0)
        right_layout.addWidget(self.progress)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setStyleSheet("""
            QLabel {
                padding: 6px 8px;
                border-radius: 6px;
                background-color: rgba(255,255,255,0.05);
                color: #a8c7ff;
                font-size: 12px;
            }
        """)
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

        main_layout.addWidget(left_frame, 1)
        main_layout.addWidget(right_frame, 0)

        self.setAcceptDrops(True)
        self.setStyleSheet(self.app_stylesheet())
        
        # Ensure spinner position is updated on initial show/resize
        self.resizeEvent(None) 

    def app_stylesheet(self):
        """Returns the main application stylesheet."""

        icon_path = get_resource_path("icons/down_arrow.svg")
        icon_path = icon_path.replace("\\", "/")
        
        return f"""
        QWidget {{
            background: #0f0f12;
            color: #ffffff;
            font-family: "Segoe UI", Roboto, Arial;
            font-size: 13px;
        }}
    
        QLabel[neonLabel="true"] {{
            color: #9ffcff;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.4px;
            padding-left: 2px;
        }}
        
        QFrame#gradientFrame {{
            border-radius: 14px;
            background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(98, 60, 255, 220),
                stop:0.3 rgba(72, 153, 255, 200),
                stop:0.6 rgba(255, 87, 140, 180),
                stop:1 rgba(255, 195, 113, 160));
        }}
    
        QPushButton {{
            border-radius: 10px;
            padding: 8px 12px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.06), stop:1 rgba(255,255,255,0.02));
            border: 1px solid rgba(255,255,255,0.08);
            color: #fff;
        }}
    
        QPushButton:hover {{
            border: 1px solid rgba(255,255,255,0.18);
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.09), stop:1 rgba(255,255,255,0.03));
        }}
    
        QComboBox {{
            background: #0d0f14;
            border: 2px solid #00faff;
            border-radius: 10px;
            padding: 6px 36px 6px 10px;
            color: #bffcff;
            font-size: 14px;
        }}
        
        QComboBox:hover {{
            border: 2px solid #61ffff;
        }}
        
        QComboBox::drop-down {{
            border: none;
            width: 26px;
            background: transparent;
        }}
        
        QComboBox::down-arrow {{
            image: url("{icon_path}");
            width: 38px;
            height: 38px;
            margin-right: 10px;
            border: none;
            background: transparent;
        }}
    
        QComboBox QAbstractItemView {{
            background: #0c0e13;
            color: #cfffff;
            border: 1px solid #00faff;
            selection-background-color: #00faff;
            selection-color: black;
        }}
    
        QListWidget {{
            background: rgba(0,0,0,0.12);
            border-radius: 8px;
            outline: 0;
        }}
    
        QListWidget::item:selected {{
            background: rgba(255,255,255,0.15);
        }}
    
        QProgressBar {{
            border-radius: 8px;
            height: 14px;
            background: #0b0f1a;
            text-align: center;
            color: #7df9ff;
            font-weight: bold;
        }}
    
        QProgressBar::chunk {{
            border-radius: 8px;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #00ffd5,
                stop:0.4 #00bfff,
                stop:1 #0066ff
            );
        }}
        """
    
    def _get_allowed_extensions(self):
        """Returns allowed input extensions with dot prefix."""
        # Include HEIC and AVIF if HEIF support is detected
        extensions = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif", ".ico")
        if HEIF_SUPPORTED:
             extensions += (".heic", ".avif")
        return extensions

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            allowed_exts = self._get_allowed_extensions()
            
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    try:
                        path_suffix = Path(url.toLocalFile()).suffix.lower()
                        # Check if the path is a file and has an allowed extension
                        if path_suffix in allowed_exts:
                            event.acceptProposedAction()
                            return
                    except Exception:
                        continue
            
        event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        allowed_exts = self._get_allowed_extensions()
        files = []
        for u in urls:
            if u.isLocalFile():
                try:
                    p = Path(u.toLocalFile()).resolve() 
                    # Only add files that exist and have an allowed extension
                    if p.is_file() and p.suffix.lower() in allowed_exts:
                        files.append(str(p))
                except Exception:
                    continue

        if files:
            self.add_files(files)
        else:
            QMessageBox.warning(self, "Invalid File", "Only supported image files are allowed or files could not be resolved.")

    def on_add_images(self):
        # Dynamically build filter string based on supported extensions
        exts = self._get_allowed_extensions()
        exts_str = " *".join(exts)
        filter_str = f"Images (*{exts_str})"
        
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select image files", "", filter_str
        )
        if files:
            self.add_files(files)

    def on_add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder containing images")
        if not folder:
            return
            
        allowed_exts = self._get_allowed_extensions()
        folder_path = Path(folder)
        image_files = []
        
        # Use a list comprehension for efficiency and rglob for recursive search
        for p in folder_path.rglob("*"): 
            if p.is_file() and p.suffix.lower() in allowed_exts:
                image_files.append(str(p.resolve())) 
                
        if not image_files:
            QMessageBox.warning(self, "No Images Found", "No image files were found in this folder.")
            return
            
        self.add_files(image_files)

    def add_files(self, file_list):
        was_empty = len(self.files) == 0 
        allowed_exts = self._get_allowed_extensions()
        skipped = 0
        added = 0
        current_files_set = set(self.files)

        for f in file_list:
            try:
                p = Path(f).resolve()
            except Exception:
                skipped += 1
                continue

            if not p.is_file() or p.suffix.lower() not in allowed_exts:
                skipped += 1
                continue

            if str(p) in current_files_set:
                continue

            # Robust file check
            try:
                # Use Image.open for verification but close it immediately
                with Image.open(p) as im:
                    im.verify() 
            except Exception:
                skipped += 1
                continue

            self.files.append(str(p))
            current_files_set.add(str(p))
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.list_widget.addItem(item)
            added += 1

        if added > 0 and (was_empty or not self.convert_btn._is_animating):
            self.convert_btn.start_animation()

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(self.list_widget.count() - 1)
            self.preview_selected_image()
        
        if skipped:
            self.status_label.setText(f"Added {added} image(s), skipped {skipped} corrupted/invalid files.")
        else:
            self.status_label.setText(f"Added {added} image(s). Total: {len(self.files)}")

    def on_remove_selected(self):
        items_to_remove = self.list_widget.selectedItems()
        
        if not items_to_remove:
            return
            
        paths_to_remove = {it.data(Qt.ItemDataRole.UserRole) for it in items_to_remove}
        # Filter the main file list to keep only those not slated for removal
        self.files = [f for f in self.files if f not in paths_to_remove]
        
        for it in items_to_remove:
            self.list_widget.takeItem(self.list_widget.row(it))
        
        self.progress.setValue(0)
        removed_count = len(paths_to_remove)

        self.status_label.setText(f"Removed {removed_count} selected. Remaining: {len(self.files)}")

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
            self.preview_selected_image()
        else:
            self.image_stack_layout.setCurrentIndex(0)
            self.preview_label.setPixmap(QPixmap())
            # Stop animation when the list is empty
            self.convert_btn.stop_animation() 
    
    def on_cancel_clicked(self):
        if self.worker and getattr(self.worker, "_cancel_locked", False):
            self.block_status_updates = True
        
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.status_label.setText("Cancel not valid now")
        
            QTimer.singleShot(2000, self._restore_status_updates)
            return
        
        if self.worker and self.worker.isRunning():
            try:
                self.worker.terminate()
            except Exception:
                pass
    
        self.loading_spinner.stop()
        self.overlay_layout.setCurrentIndex(0)
        self.set_ui_enabled(True)
        
        # FIX 1: Explicitly show the convert button and hide the cancel button
        self.convert_btn.show() 
        self.cancel_btn.hide()
        
        self.status_label.setText("Conversion canceled.")
        self.progress.setValue(0)
        
        # FIX 2: START the animation because files are still loaded.
        if len(self.files) > 0:
            self.convert_btn.start_animation()
        else:
            self.convert_btn.stop_animation()

    def clear_status_message(self):
        self.status_label.setText("")
        self.status_label.setStyleSheet("")      

    def _restore_status_updates(self):
        self.block_status_updates = False
        self.clear_status_message()
      
    def on_choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder (optional)")
        if folder:
            self.dest_folder = Path(folder).resolve() 
            self.dest_label.setText(f"Save: {self.dest_folder.name}/")
        else:
            self.dest_folder = None
            self.dest_label.setText("Save: Next to originals")

    def on_list_selection_changed(self):
        self.preview_selected_image()

    def preview_selected_image(self):
        item = self.list_widget.currentItem()
        if not item:
            if self.list_widget.count() == 0:
                self.image_stack_layout.setCurrentIndex(0)
            return

        self.image_stack_layout.setCurrentIndex(1)
        path = item.data(Qt.ItemDataRole.UserRole)
        p = Path(path)
        
        if not p.exists():
            self.preview_label.setText("File not found or moved.")
            self.status_label.setText(f"Error: {p.name} not found.")
            return
            
        try:
            # 1. Try QPixmap native loading (fastest, supports most formats)
            pix = QPixmap(str(p))
            is_valid_pixmap = not pix.isNull()

            # 2. Fallback to Pillow/ImageQt for HEIC/AVIF and other formats QPixmap might miss
            if not is_valid_pixmap:
                with Image.open(p) as im:
                    qim = ImageQt.ImageQt(im.convert('RGBA')) # Convert to RGBA for safe ImageQt conversion
                    pix = QPixmap.fromImage(qim)
                    is_valid_pixmap = not pix.isNull()

            if is_valid_pixmap:
                self.preview_label.setPixmap(pix)
                self.status_label.setText(f"Preview: {p.name}")
            else:
                # If both fail, raise an error to hit the fallback block
                raise UnidentifiedImageError("Both native and Pillow/ImageQt fallback failed.")

        except UnidentifiedImageError:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Cannot preview this format (Unsupported or corrupted).")
            self.status_label.setText(f"Preview Error: Unsupported format for {p.name}.")
        except Exception as e:
            print(f"Preview exception: {traceback.format_exc()}")
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(f"Cannot preview image (Error: {type(e).__name__}).")
            self.status_label.setText(f"Preview Error: General failure for {p.name}.")

    def on_convert(self):
        if not self.files:
            QMessageBox.warning(self, "No files", "Please add at least one image to convert.")
            return

        out_ext = self.format_box.currentData()
        if not out_ext:
            QMessageBox.warning(self, "No Format Selected", "Please select an output format before converting.")
            return

        dest = getattr(self, "dest_folder", None)
        out_folder = str(dest) if dest else None
        quality = 95 # Hardcoded quality

        self.set_ui_enabled(False)
        self.convert_btn.hide()
        self.cancel_btn.show()
        
        self.overlay_layout.setCurrentIndex(1)
        self.loading_spinner.start()
        
        self.progress.setValue(0)
        self.status_label.setText("Starting conversion...")

        self.worker = ConvertWorker(self.files, out_ext, out_folder, quality=quality) 
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self._safe_set_status)
        self.worker.done.connect(self.on_conversion_done)
        self.worker.start()

    def _safe_set_status(self, text):
        if not self.block_status_updates:
            self.status_label.setText(text)

    def on_conversion_done(self, success: bool, msg: str):
        self.loading_spinner.stop()
        self.overlay_layout.setCurrentIndex(0)
        
        self.set_ui_enabled(True)
        self.cancel_btn.hide()
        self.convert_btn.show()

        self.worker = None

        default_status_style = """
            QLabel {
                padding: 6px 8px;
                border-radius: 6px;
                background-color: rgba(255,255,255,0.05);
                color: #a8c7ff;
                font-size: 12px;
            }
        """

        if success:
            self.progress.setValue(100)
            self.status_label.setStyleSheet(default_status_style)
            self.status_label.setText(msg)
            QMessageBox.information(self, "Done", msg)
        else:
            self.progress.setValue(0)
            self.status_label.setStyleSheet("""
                QLabel {
                    padding: 6px 8px;
                    border-radius: 6px;
                    background-color: rgba(255,0,0,0.12);
                    color: #ffb3b3;
                    font-size: 12px;
                }
            """)
            self.status_label.setText(f"Conversion failed: {msg}")
            QMessageBox.warning(self, "Conversion Error", msg)
        
        # Reset UI elements after a delay, which includes stopping the animation
        QTimer.singleShot(10000, self.reset_all)
        
    def set_ui_enabled(self, enabled: bool):
        """Enables or disables key UI elements."""
        self.add_folder_btn.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled)
        self.convert_btn.setEnabled(enabled)
        self.dest_btn.setEnabled(enabled)
        self.format_box.setEnabled(enabled)
        self.list_widget.setEnabled(enabled)
        self.add_image_placeholder.setEnabled(enabled)

def main():
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    win = ImageConverterApp()
    win.show()

    if not HEIF_SUPPORTED:
        win.status_label.setText("Warning: HEIC / AVIF support library not found. Install 'pillow-heif'.")
        win.status_label.setStyleSheet("""
            QLabel {
                padding: 6px 8px;
                border-radius: 6px;
                background-color: rgba(255,165,0,0.12);
                color: #ffd699;
                font-size: 12px;
            }
        """)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()