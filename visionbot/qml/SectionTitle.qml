import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    property string heading: ""
    property string description: ""
    spacing: 6
    Label { text: heading; font.pixelSize: 24; font.weight: Font.DemiBold; color: theme.text; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Label { text: description; font.pixelSize: 13; color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
}
