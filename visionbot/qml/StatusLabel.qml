import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: status
    property string label: ""
    property string tone: "neutral"
    readonly property color signalColor: tone === "success" ? theme.green : tone === "warning" ? theme.warning : tone === "error" ? theme.red : theme.muted
    spacing: 7
    Rectangle {
        Layout.preferredWidth: 7
        Layout.preferredHeight: 7
        radius: 4
        color: status.signalColor
    }
    Label {
        text: status.label
        textFormat: Text.PlainText
        color: status.signalColor
        font.pixelSize: theme.typeScale.caption
        font.weight: Font.DemiBold
        Layout.fillWidth: true
        wrapMode: Text.Wrap
    }
}
