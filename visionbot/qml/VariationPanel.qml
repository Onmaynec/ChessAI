import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Surface {
    id: panel
    readonly property var view: visionModel.boardView
    padding: 16
    contentItem: ColumnLayout {
        spacing: 10
        Label { text: panel.view.lineLabel || "Варианты"; font.pixelSize: Math.round(16 * workspaceModel.textScale / 100); font.weight: Font.DemiBold; color: theme.text; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: panel.view.line.join("  →  ") || "Нет данных"; textFormat: Text.PlainText; font.family: theme.mono; color: theme.text; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
        Rectangle { color: theme.border; Layout.fillWidth: true; height: 1 }
        Label { text: "Кандидаты · оценка стороны хода"; color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Repeater {
            model: panel.view.candidates
            delegate: UiButton {
                required property var modelData
                text: modelData.move + "     " + modelData.score
                Layout.fillWidth: true
                onClicked: visionModel.selectCandidate(modelData.move)
            }
        }
        Label { text: "Нет альтернатив в отчёте"; visible: panel.view.candidates.length === 0; color: theme.dim; Layout.fillWidth: true; wrapMode: Text.Wrap }
        UiButton { text: "Показать выбранный ход"; enabled: panel.view.move !== "—"; Layout.fillWidth: true; onClicked: visionModel.selectCandidate(panel.view.move) }
        Label { text: "Выбор кандидата меняет только стрелку. Основная линия остаётся исходной."; color: theme.dim; font.pixelSize: Math.round(11 * workspaceModel.textScale / 100); Layout.fillWidth: true; wrapMode: Text.Wrap }
    }
}
