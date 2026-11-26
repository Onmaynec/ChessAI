import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Surface {
    id: card
    property string label: ""
    property string value: "—"
    property string detail: ""
    padding: 16
    contentItem: ColumnLayout {
        spacing: 8
        Label { text: card.label; color: theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: card.value || "—"; color: theme.text; font.pixelSize: 26; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
        Label { text: card.detail; color: theme.dim; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap; visible: text.length > 0 }
    }
}
