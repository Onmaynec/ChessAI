"""Qt-only calibration dialog; screenshot lives in memory, not on disk."""
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout, QDialogButtonBox, QRubberBand

def select_region(frame):
    h,w=frame.shape[:2]
    available=QApplication.primaryScreen().availableGeometry()
    factor=min(1.,(available.width()-100)/w,(available.height()-160)/h)
    if factor<=0:
        raise ValueError('Screen too small for calibration')
    rgb=frame[:,:,::-1].copy()
    image=QImage(rgb.data,w,h,rgb.strides[0],QImage.Format.Format_RGB888).copy()
    pixmap=QPixmap.fromImage(image).scaled(round(w*factor),round(h*factor),
                   Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
    dialog=QDialog()
    dialog.setWindowTitle('Vision Bot — калибровка')
    dialog.setStyleSheet('QDialog {background:#080808;color:white} QLabel {color:white} QPushButton {background:#242424;color:white;padding:8px;border:1px solid #505050}')
    layout=QVBoxLayout(dialog)
    info=QLabel('Выделите всю доску 8×8. Минимум 320×320 физических пикселей.')
    layout.addWidget(info)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
    ok=buttons.button(QDialogButtonBox.StandardButton.Ok)
    ok.setEnabled(False)
    class Selection(QLabel):
        def __init__(self):
            super().__init__()
            self.setPixmap(pixmap)
            self.setFixedSize(pixmap.size())
            self.band=QRubberBand(QRubberBand.Shape.Rectangle,self)
            self.origin=None
            self.region=None
        def point(self,event):
            p=event.position().toPoint()
            return QPoint(max(0,min(self.width(),p.x())),max(0,min(self.height(),p.y())))
        def mousePressEvent(self,event):
            if event.button()==Qt.MouseButton.LeftButton:
                self.origin=self.point(event)
                self.region=None
                ok.setEnabled(False)
                self.band.setGeometry(QRect(self.origin,self.origin))
                self.band.show()
        def mouseMoveEvent(self,event):
            if self.origin is not None:
                self.band.setGeometry(QRect(self.origin,self.point(event)).normalized())
        def mouseReleaseEvent(self,event):
            if self.origin is None:
                return
            end=self.point(event)
            x1,x2=sorted((self.origin.x(),end.x()))
            y1,y2=sorted((self.origin.y(),end.y()))
            self.origin=None
            sx,sy=round(x1*w/self.width()),round(y1*h/self.height())
            size=min(round((x2-x1)*w/self.width()),round((y2-y1)*h/self.height()))
            size=min(size,w-sx,h-sy)
            self.region=(sx,sy,size) if size>=320 else None
            ok.setEnabled(self.region is not None)
            info.setText(f'Область: {sx}, {sy} · {size} × {size} px' if self.region else 'Слишком маленькая область. Повторите выделение.')
            if self.region:
                self.band.setGeometry(QRect(x1,y1,round(size*self.width()/w),round(size*self.height()/h)))
    selection=Selection()
    layout.addWidget(selection)
    layout.addWidget(buttons)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    return selection.region if dialog.exec()==QDialog.DialogCode.Accepted else None
