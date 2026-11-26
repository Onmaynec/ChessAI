import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: section
    property string heading: ""
    property string description: ""
    spacing: 6
    Label { text: section.heading; font.pixelSize: theme.typeScale.heading; font.weight: Font.DemiBold; color: theme.text; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Label { text: section.description; font.pixelSize: theme.typeScale.body; color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
}
