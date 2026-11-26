import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    property bool selected: false
    implicitHeight: Math.max(40, contentItem.implicitHeight + 20)
    implicitWidth: 112
    padding: 12
    hoverEnabled: true
    Accessible.name: text
    font.family: theme.font
    font.pixelSize: Math.round(theme.typeScale.body * workspaceModel.textScale / 100)
    font.weight: primary ? Font.DemiBold : Font.Normal
    contentItem: Text {
        text: control.text
        font: control.font
        color: !control.enabled ? theme.dim : control.primary ? theme.bg : theme.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: theme.radius
        color: !control.enabled ? theme.panel : control.primary ? (control.down || control.hovered ? theme.hover : theme.accent) : control.selected || control.down ? theme.active : control.hovered ? theme.surfaceHover : theme.field
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? theme.accent : control.selected ? theme.muted : theme.border
        Behavior on color { enabled: !workspaceModel.reducedMotion; ColorAnimation { duration: theme.motion.fast } }
    }
}
