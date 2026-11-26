import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Surface {
    id: panel
    padding: 14
    readonly property var view: visionModel.boardView
    contentItem: ColumnLayout {
        spacing: 12
        Label { text: "Позиция перед предложенным ходом"; font.pixelSize: 16; font.weight: Font.DemiBold; color: theme.text; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: "Ход: " + panel.view.turn + " · " + panel.view.move; color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            UiButton { text: "←"; implicitWidth: 40; enabled: visionModel.historyIndex > 0; onClicked: visionModel.goHistory(visionModel.historyIndex-1); Accessible.name: "Предыдущая позиция" }
            Label { text: (visionModel.historyIndex+1) + " / " + visionModel.historyCount; color: theme.text; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
            UiButton { text: "→"; implicitWidth: 40; enabled: visionModel.historyIndex+1 < visionModel.historyCount; onClicked: visionModel.goHistory(visionModel.historyIndex+1); Accessible.name: "Следующая позиция" }
            UiButton { text: "↻"; implicitWidth: 40; onClicked: visionModel.flipBoard(); Accessible.name: "Перевернуть доску" }
        }
        Chessboard {
            objectName: "chessboard"
            position: panel.view
            black: visionModel.blackOrientation
            Layout.fillWidth: true
            Layout.maximumWidth: 510
            Layout.preferredHeight: width
            Layout.alignment: Qt.AlignHCenter
        }
        Label {
            text: panel.view.evaluation.kind === undefined ? "Оценка недоступна" : "Оценка в пользу белых: " + (panel.view.evaluation.kind === "mate" ? "M" : "") + (panel.view.evaluation.value > 0 ? "+" : "") + panel.view.evaluation.value + (panel.view.evaluation.kind === "cp" ? " cp" : "")
            color: theme.muted
            font.pixelSize: 12
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 10
            radius: 3
            color: theme.active
            border.color: theme.border
            visible: panel.view.evaluation.kind !== undefined
            clip: true
            Rectangle {
                width: parent.width * (panel.view.evaluation.fraction === undefined ? 0 : panel.view.evaluation.fraction)
                height: parent.height
                color: theme.text
            }
            Rectangle { x: parent.width/2; height: parent.height; width: 1; color: theme.dim }
        }
        Label { text: "Шкала ±800 cp, не вероятность победы."; color: theme.dim; font.pixelSize: 10; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: "Стрелка — предложенный ход, а не подтверждение выполнения."; color: theme.dim; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
    }
}
