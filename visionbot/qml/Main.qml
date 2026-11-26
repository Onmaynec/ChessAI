import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    objectName: "visionWorkspace"
    width: 1200
    height: 800
    minimumWidth: 560
    minimumHeight: 480
    visible: true
    title: "Vision Bot · " + appVersion + " · Preview"
    color: theme.bg
    font.family: theme.font
    font.pixelSize: 13
    property int page: 0
    readonly property bool wide: width >= 1000
    readonly property var pages: ["Обзор", "Анализ", "Журнал", "Настройки"]
    property string query: ""
    property string category: "all"

    Shortcut { sequence: "Ctrl+1"; onActivated: root.page = 0 }
    Shortcut { sequence: "Ctrl+2"; onActivated: root.page = 1 }
    Shortcut { sequence: "Ctrl+3"; onActivated: root.page = 2 }
    Shortcut { sequence: "Ctrl+4"; onActivated: root.page = 3 }

    header: Rectangle {
        color: theme.bg
        implicitHeight: 64
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            spacing: 12
            Label { text: "VISION BOT"; font.weight: Font.Bold; font.pixelSize: 18; color: theme.text }
            Label { text: appVersion; color: theme.muted; font.pixelSize: 12 }
            Item { Layout.fillWidth: true }
            Label {
                text: sourceLabel
                color: theme.warning
                font.pixelSize: 11
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                Layout.maximumWidth: 180
            }
        }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
    }
    footer: Rectangle {
        implicitHeight: 34
        color: theme.bg
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            Label { text: "Только просмотр · без управления партией"; color: theme.muted; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
            Label { text: "Qt Quick"; color: theme.dim; font.pixelSize: 11 }
        }
        Rectangle { width: parent.width; height: 1; color: theme.border }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            color: theme.panel
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? 208 : 116
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 6
                Label { text: "РАБОЧАЯ СРЕДА"; color: theme.dim; font.pixelSize: 10; Layout.fillWidth: true; elide: Text.ElideRight; Layout.topMargin: 8; Layout.bottomMargin: 8 }
                Repeater {
                    model: root.pages
                    delegate: UiButton {
                        required property int index
                        required property string modelData
                        text: modelData
                        selected: root.page === index
                        Layout.fillWidth: true
                        onClicked: root.page = index
                    }
                }
                Item { Layout.fillHeight: true }
                Label { text: "LOCAL / READ ONLY"; color: theme.dim; font.pixelSize: 10; Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: theme.border }
        }

        StackLayout {
            id: workspace
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.page

            ScrollView {
                id: overview
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: overview.availableWidth - 40
                    x: 20
                    y: 20
                    spacing: 16
                    SectionTitle {
                        heading: "Рабочее пространство"
                        description: "Состояние локального источника и последняя полученная телеметрия."
                        Layout.fillWidth: true
                    }
                    Surface {
                        Layout.fillWidth: true
                        contentItem: ColumnLayout {
                            spacing: 10
                            RowLayout {
                                Layout.fillWidth: true
                                Label { text: "Состояние"; color: theme.muted; Layout.fillWidth: true }
                                Label { text: visionModel.active ? "Активна" : "Нет активной сессии"; color: visionModel.active ? theme.green : theme.muted }
                            }
                            Rectangle { height: 1; color: theme.border; Layout.fillWidth: true }
                            Label { text: "Источник: " + sourceLabel; color: theme.text; Layout.fillWidth: true; wrapMode: Text.Wrap }
                            Label { text: "Модель: " + (visionModel.model || "—"); color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        }
                    }
                    GridLayout {
                        columns: root.wide ? 3 : 1
                        columnSpacing: 10
                        rowSpacing: 10
                        Layout.fillWidth: true
                        Metric { label: "Последний ход"; value: visionModel.move; detail: "Полученная телеметрия"; Layout.fillWidth: true }
                        Metric { label: "Оценка"; value: visionModel.score; detail: "Сообщено источником"; Layout.fillWidth: true }
                        Metric { label: "Глубина"; value: visionModel.depth; detail: "Полуходы"; Layout.fillWidth: true }
                    }
                    Surface {
                        Layout.fillWidth: true
                        contentItem: ColumnLayout {
                            spacing: 10
                            Label { text: "Позиция · FEN"; font.pixelSize: 17; font.weight: Font.DemiBold; color: theme.text }
                            Label { text: visionModel.fen || "Позиция ещё не получена."; color: theme.muted; font.family: theme.mono; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                            UiButton { text: "Подробный анализ"; onClicked: root.page = 1; Layout.alignment: Qt.AlignLeft }
                        }
                    }
                    Item { Layout.preferredHeight: 20 }
                }
            }

            ScrollView {
                id: analysisPage
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: analysisPage.availableWidth - 40
                    x: 20
                    y: 20
                    spacing: 16
                    SectionTitle { heading: "Анализ позиции"; description: "Отображаются только значения из локальной телеметрии."; Layout.fillWidth: true }
                    GridLayout {
                        columns: root.wide ? 2 : 1
                        Layout.fillWidth: true
                        columnSpacing: 12
                        rowSpacing: 12
                        Metric { label: "Оценка"; value: visionModel.score; Layout.fillWidth: true }
                        Metric { label: "Глубина"; value: visionModel.depth; Layout.fillWidth: true }
                        Metric { label: "Ожидаемый ответ"; value: visionModel.reply; Layout.fillWidth: true }
                        Metric { label: "Время расчёта"; value: visionModel.searchTime; Layout.fillWidth: true }
                    }
                    Surface {
                        Layout.fillWidth: true
                        contentItem: ColumnLayout {
                            Label { text: "Последний известный FEN"; color: theme.text; font.pixelSize: 16 }
                            TextArea {
                                text: visionModel.fen || "Нет данных"
                                readOnly: true
                                selectByMouse: true
                                wrapMode: TextEdit.WrapAnywhere
                                color: theme.muted
                                font.family: theme.mono
                                Layout.fillWidth: true
                                background: Rectangle { color: theme.field; radius: theme.radius; border.color: theme.border }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 20 }
                }
            }

            Item {
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 12
                    SectionTitle { heading: "Журнал событий"; description: "История локального источника · до 600 записей."; Layout.fillWidth: true }
                    TextField {
                        id: search
                        objectName: "journalSearch"
                        Layout.fillWidth: true
                        placeholderText: "Поиск по событиям"
                        text: root.query
                        color: theme.text
                        placeholderTextColor: theme.dim
                        selectByMouse: true
                        onTextEdited: { root.query = text; visionModel.filterJournal(root.query, root.category) }
                        background: Rectangle { radius: theme.radius; color: theme.field; border.color: search.activeFocus ? theme.accent : theme.border }
                    }
                    Flow {
                        Layout.fillWidth: true
                        Layout.preferredHeight: implicitHeight
                        spacing: 6
                        Repeater {
                            model: [{key:"all", name:"Все"}, {key:"analysis", name:"Анализ"}, {key:"move", name:"Ходы"}, {key:"error", name:"Ошибки"}]
                            delegate: UiButton {
                                required property var modelData
                                text: modelData.name
                                implicitWidth: 84
                                selected: root.category === modelData.key
                                onClicked: { root.category = modelData.key; visionModel.filterJournal(root.query, root.category) }
                            }
                        }
                    }
                    Label { text: visionModel.journal.length + " / " + visionModel.journalTotal + " событий"; color: theme.muted; Layout.fillWidth: true }
                    Rectangle {
                        color: theme.panel
                        border.color: theme.border
                        radius: theme.radius
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ListView {
                            id: journalList
                            objectName: "journalList"
                            anchors.fill: parent
                            anchors.margins: 8
                            clip: true
                            model: visionModel.journal
                            spacing: 1
                            ScrollBar.vertical: ScrollBar {}
                            delegate: Rectangle {
                                required property var modelData
                                width: journalList.width - 12
                                height: eventRow.implicitHeight + 20
                                color: theme.field
                                RowLayout {
                                    id: eventRow
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 10
                                    Label { text: modelData.category.toUpperCase(); color: modelData.category === "error" ? theme.red : theme.muted; font.pixelSize: 10; Layout.preferredWidth: 65 }
                                    Label { text: modelData.text; textFormat: Text.PlainText; color: theme.text; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                }
                            }
                            Label { anchors.centerIn: parent; visible: journalList.count === 0; text: "Нет событий"; color: theme.muted }
                        }
                    }
                }
            }

            ScrollView {
                id: settingsPage
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: settingsPage.availableWidth - 40
                    x: 20
                    y: 20
                    spacing: 16
                    SectionTitle { heading: "Настройки интерфейса"; description: "Предварительная оболочка Qt Quick. Настройки рабочего Vision Bot не изменяются."; Layout.fillWidth: true }
                    Surface {
                        Layout.fillWidth: true
                        contentItem: ColumnLayout {
                            spacing: 12
                            Label { text: "Оформление"; color: theme.text; font.pixelSize: 17; font.weight: Font.DemiBold }
                            Label { text: "Monochrome · #000000"; color: theme.muted }
                            CheckBox { id: top; text: "Поверх окон (только preview)"; palette.windowText: theme.text; onToggled: root.flags = Qt.Window | (checked ? Qt.WindowStaysOnTopHint : 0) }
                            Label { text: "Ctrl+1–4 — переключение разделов"; color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        }
                    }
                    Surface {
                        Layout.fillWidth: true
                        contentItem: ColumnLayout {
                            Label { text: "Режим работы"; color: theme.text; font.pixelSize: 17 }
                            Label { text: "Запуск сессии, калибровка и управление доступны в прежнем интерфейсе. Здесь нет активных команд."; color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        }
                    }
                }
            }
        }
    }
}
