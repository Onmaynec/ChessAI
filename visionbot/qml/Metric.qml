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
        Label { text: card.label; color: theme.muted; font.pixelSize: Math.round(theme.typeScale.body * workspaceModel.textScale / 100); Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: card.value || "—"; textFormat: Text.PlainText; color: theme.text; font.pixelSize: Math.round(theme.typeScale.metric * workspaceModel.textScale / 100); font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
        Label { text: card.detail; color: theme.dim; font.pixelSize: Math.round(theme.typeScale.caption * workspaceModel.textScale / 100); Layout.fillWidth: true; wrapMode: Text.Wrap; visible: text.length > 0 }
    }
}
