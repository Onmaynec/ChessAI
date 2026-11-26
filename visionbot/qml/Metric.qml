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
        Label { text: card.label; color: theme.muted; font.pixelSize: theme.typeScale.body; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: card.value || "—"; textFormat: Text.PlainText; color: theme.text; font.pixelSize: theme.typeScale.metric; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
        Label { text: card.detail; color: theme.dim; font.pixelSize: theme.typeScale.caption; Layout.fillWidth: true; wrapMode: Text.Wrap; visible: text.length > 0 }
    }
}
