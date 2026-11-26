import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    property bool selected: false
    implicitHeight: 40
    implicitWidth: 112
    padding: 12
    hoverEnabled: true
    font.family: theme.font
    font.pixelSize: 13
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
        color: !control.enabled ? theme.panel : control.primary ? (control.down || control.hovered ? theme.hover : theme.accent) : control.selected || control.down || control.hovered ? theme.active : theme.field
        border.width: 1
        border.color: control.activeFocus ? theme.accent : control.selected ? theme.muted : theme.border
    }
}
