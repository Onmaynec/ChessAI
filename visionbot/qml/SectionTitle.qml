import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: section
    property string heading: ""
    property string description: ""
    spacing: 6
    Label { text: section.heading; font.pixelSize: Math.round(theme.typeScale.heading * workspaceModel.textScale / 100); font.weight: Font.DemiBold; color: theme.text; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Label { text: section.description; font.pixelSize: Math.round(theme.typeScale.body * workspaceModel.textScale / 100); color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
}
