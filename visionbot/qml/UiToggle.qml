import QtQuick
import QtQuick.Controls

Switch {
    id: control
    font.family: theme.font
    font.pixelSize: Math.round(theme.typeScale.body * workspaceModel.textScale / 100)
    implicitHeight: Math.max(40, contentItem.implicitHeight + 12)
    hoverEnabled: true
    Accessible.name: text
    indicator: Rectangle {
        x: control.leftPadding
        y: (control.height-height)/2
        width: 40; height: 22; radius: 11
        color: control.checked ? theme.accent : theme.active
        border.color: control.activeFocus ? theme.accent : theme.track
        border.width: control.activeFocus ? 2 : 1
        Behavior on color { enabled: !workspaceModel.reducedMotion; ColorAnimation { duration: theme.motion.fast } }
        Rectangle {
            x: control.checked ? 20 : 3
            y: 3
            width: 16; height: 16; radius: 8
            color: control.checked ? theme.bg : theme.muted
            Behavior on x { enabled: !workspaceModel.reducedMotion; NumberAnimation { duration: theme.motion.normal; easing.type: Easing.OutCubic } }
        }
    }
    contentItem: Text {
        leftPadding: control.indicator.width + 10
        text: control.text
        font: control.font
        color: control.enabled ? theme.text : theme.dim
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
    }
}
