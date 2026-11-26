import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: panel
    property bool compact: false
    spacing: 8
    Label { text: "Журнал · " + visionModel.journal.length + " / " + visionModel.journalTotal; color: theme.text; font.weight: Font.DemiBold; Layout.fillWidth: true }
    TextField {
        id: search
        objectName: "journalSearch"
        Layout.fillWidth: true
        text: visionModel.journalQuery
        placeholderText: "Поиск по событиям"
        color: theme.text
        placeholderTextColor: theme.dim
        selectByMouse: true
        onTextEdited: visionModel.filterJournal(text, visionModel.journalCategory)
        background: Rectangle { color: theme.field; radius: theme.radius; border.color: search.activeFocus ? theme.accent : theme.border }
    }
    ComboBox {
        id: filter
        Layout.fillWidth: true
        model: ["Все", "Анализ", "Ходы", "Ошибки", "Информация"]
        property var keys: ["all","analysis","move","error","info"]
        currentIndex: Math.max(0, keys.indexOf(visionModel.journalCategory))
        onActivated: visionModel.filterJournal(visionModel.journalQuery, keys[currentIndex])
        palette.button: theme.field
        palette.buttonText: theme.text
        palette.base: theme.panel
        palette.text: theme.text
        palette.highlight: theme.active
        palette.highlightedText: theme.text
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 80
        radius: theme.radius
        color: theme.panel
        border.color: theme.border
        ListView {
            id: list
            objectName: "journalList"
            anchors.fill: parent
            anchors.margins: 6
            clip: true
            model: visionModel.journal
            spacing: 2
            ScrollBar.vertical: ScrollBar {}
            delegate: Rectangle {
                required property var modelData
                width: Math.max(1,list.width-12)
                height: eventRow.implicitHeight + 16
                color: theme.field
                RowLayout {
                    id: eventRow
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 8
                    Label { text: modelData.category.toUpperCase(); color: modelData.category === "error" ? theme.red : theme.muted; font.pixelSize: 10; Layout.preferredWidth: 60 }
                    Label { text: modelData.text; textFormat: Text.PlainText; color: theme.text; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                }
            }
            Label { anchors.centerIn: parent; visible: list.count === 0; text: "Нет событий"; color: theme.muted }
        }
    }
}
