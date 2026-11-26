import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    spacing: 8
    Label { text: sourceLabel; color: theme.warning; font.pixelSize: Math.round(11 * workspaceModel.textScale / 100); Layout.fillWidth: true; elide: Text.ElideRight }
    Label { text: "Локальная телеметрия"; color: theme.muted; Layout.fillWidth: true }
    RowLayout {
        Layout.fillWidth: true
        Metric { label: "Ход"; value: visionModel.boardView.move; Layout.fillWidth: true; Layout.minimumWidth: 0 }
        Metric { label: "Оценка"; value: visionModel.boardView.score; Layout.fillWidth: true; Layout.minimumWidth: 0 }
    }
    Label { text: "Глубина: " + visionModel.boardView.depth + "  ·  " + visionModel.boardView.seconds; color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Label { text: "Запись " + (visionModel.historyIndex+1) + " / " + visionModel.historyCount; color: theme.dim; Layout.fillWidth: true }
}
