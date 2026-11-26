import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: root
    objectName: "rebornWorkspace"
    width: 1260
    height: 820
    minimumWidth: 620
    minimumHeight: 520
    visible: true
    color: theme.bg
    title: "Vision Bot Reborn · " + appVersion
    font.family: theme.font
    font.pixelSize: Math.round(14 * workspaceModel.textScale / 100)
    property int page: 0
    property bool authorized: false
    property bool resume: true
    property bool pinned: false
    readonly property bool wide: width >= 1040
    flags: Qt.Window | (pinned ? Qt.WindowStaysOnTopHint : 0)
    Component.onCompleted: {
        var g=workspaceModel.geometry("standard")
        if (g.length===4) { x=g[0]; y=g[1]; width=g[2]; height=g[3] }
        pinned=workspaceModel.pinned("main")
    }
    onClosing: function(event) {
        if (sessionModel.busy) { event.accepted=false; sessionModel.stop(); return }
        workspaceModel.record("standard",x,y,width,height)
        Qt.quit()
    }
    Shortcut { sequence: "Ctrl+1"; onActivated: root.page=0 }
    Shortcut { sequence: "Ctrl+2"; onActivated: root.page=1 }
    Shortcut { sequence: "Ctrl+3"; onActivated: root.page=2 }
    Shortcut { sequence: "Escape"; onActivated: sessionModel.stop() }
    FileDialog {
        id: replayDialog
        title: "Открыть локальную телеметрию"
        onAccepted: if (!sessionModel.busy) rebornModel.importReplay(selectedFile)
    }
    header: Rectangle {
        color: theme.panel
        implicitHeight: 72
        RowLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 14
            Rectangle {
                Layout.preferredWidth: 36; Layout.preferredHeight: 36
                radius: 9; color: theme.text
                Label { anchors.centerIn: parent; text: "♞"; color: theme.bg; font.pixelSize: 24 }
            }
            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true
                Label { text: "Vision Bot"; color: theme.text; font.pixelSize: 20; font.weight: Font.Bold }
                Label { text: "REBORN / " + appVersion; color: theme.muted; font.family: theme.mono; font.pixelSize: 11 }
            }
            StatusLabel { label: sessionModel.active ? "Активная сессия" : "Локальная среда"; tone: sessionModel.active ? "success" : "neutral" }
            UiButton { text: "Стоп · Esc"; enabled: sessionModel.active; onClicked: sessionModel.stop() }
        }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
    }
    footer: Rectangle {
        color: theme.panel
        implicitHeight: 34
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 14; anchors.rightMargin: 14
            Label { text: sessionModel.status; color: theme.muted; textFormat: Text.PlainText; elide: Text.ElideRight; Layout.fillWidth: true }
            Label { text: "Qt Quick"; color: theme.dim }
        }
    }
    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.preferredWidth: root.wide ? 178 : 108
            Layout.minimumWidth: 0
            Layout.fillHeight: true
            color: theme.panel
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 6
                Label { text: "WORKSPACE"; font.pixelSize: 10; color: theme.dim; Layout.fillWidth: true }
                Repeater {
                    model: ["Сессия","Журнал","Настройки"]
                    delegate: UiButton {
                        required property int index
                        required property string modelData
                        text: modelData
                        selected: root.page===index
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        onClicked: root.page=index
                    }
                }
                Item { Layout.fillHeight: true }
                Label { text: "Компьютерные тесты"; color: theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
                StatusLabel { label: rebornModel.engineAvailable ? "Движок найден" : "Нет движка"; tone: rebornModel.engineAvailable ? "success" : "warning"; Layout.fillWidth: true }
                StatusLabel { label: rebornModel.modelAvailable ? "Модель найдена" : "Нет модели"; tone: rebornModel.modelAvailable ? "success" : "warning"; Layout.fillWidth: true }
            }
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: theme.border }
        }
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.page
            ScrollView {
                id: sessionScroll
                clip: true
                contentWidth: availableWidth
                contentHeight: sessionContent.implicitHeight+36
                ColumnLayout {
                    id: sessionContent
                    x: 18; y: 18
                    width: Math.max(1,sessionScroll.availableWidth-36)
                    spacing: 14
                    SectionTitle { heading: "Рабочая область"; description: sessionModel.active ? "Разрешённая компьютерная сессия" : "Подготовьте модель и доску или откройте локальный анализ."; Layout.fillWidth: true }
                    GridLayout {
                        columns: root.wide ? 2 : 1
                        columnSpacing: 14
                        rowSpacing: 14
                        Layout.fillWidth: true
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredWidth: 560
                            Layout.row: root.wide ? 0 : 1
                            Layout.column: 0
                            Layout.alignment: Qt.AlignTop
                            spacing: 12
                            PositionPanel { Layout.fillWidth: true; Layout.minimumWidth: 0 }
                            VariationPanel { Layout.fillWidth: true; Layout.minimumWidth: 0 }
                        }
                        Surface {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredWidth: 360
                            Layout.row: 0
                            Layout.column: root.wide ? 1 : 0
                            Layout.alignment: Qt.AlignTop
                            padding: 16
                            contentItem: ColumnLayout {
                                spacing: 10
                                Label { text: "Настройка сессии"; color: theme.text; font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                Label { text: "01 / Эксперимент"; color: theme.muted; Layout.fillWidth: true }
                                RebornSelect {
                                    objectName: "runPicker"
                                    model: rebornModel.runs
                                    currentIndex: rebornModel.runs.indexOf(rebornModel.selectedRun)
                                    enabled: !sessionModel.busy && count>0
                                    Accessible.name: "Выбор запуска обучения"
                                    onActivated: rebornModel.selectRun(currentText)
                                    Layout.fillWidth: true
                                }
                                Label { text: "Checkpoint"; color: theme.muted; Layout.fillWidth: true }
                                RebornSelect {
                                    objectName: "modelPicker"
                                    model: rebornModel.models
                                    currentIndex: rebornModel.models.indexOf(rebornModel.selectedModel)
                                    enabled: !sessionModel.busy && count>0
                                    onActivated: rebornModel.selectModel(currentText)
                                    Accessible.name: "Выбор модели"
                                    Layout.fillWidth: true
                                }
                                UiButton { text: "Обновить модели"; enabled: !sessionModel.busy; onClicked: rebornModel.refreshRuns(); Layout.fillWidth: true }
                                Label { text: rebornModel.message; textFormat: Text.PlainText; color: theme.muted; visible: text.length>0; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                Rectangle { height: 1; color: theme.border; Layout.fillWidth: true }
                                Label { text: "02 / Калибровка"; color: theme.muted }
                                Label { text: sessionModel.region; color: theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                UiButton { text: "Выделить доску"; enabled: !sessionModel.busy; onClicked: sessionModel.calibrate(); Layout.fillWidth: true }
                                RebornSelect {
                                    model: ["Белые","Чёрные"]
                                    currentIndex: sessionModel.side==="white"?0:1
                                    enabled: !sessionModel.busy
                                    onActivated: sessionModel.setSide(currentIndex===0?"white":"black")
                                    Accessible.name: "Сторона"
                                    Layout.fillWidth: true
                                }
                                UiToggle { text: "Восстановить сохранённую сессию"; checked: root.resume; enabled: !sessionModel.busy; onToggled: root.resume=checked; Layout.fillWidth: true }
                                Rectangle { height: 1; color: theme.border; Layout.fillWidth: true }
                                Label { text: "03 / Разрешённый тест"; color: theme.muted }
                                UiToggle { text: "Есть разрешение на автоматизированный тест против компьютера"; checked: root.authorized; enabled: !sessionModel.busy; onToggled: root.authorized=checked; Layout.fillWidth: true }
                                UiButton { text: "Запустить сессию"; primary: true; enabled: !sessionModel.busy && root.authorized && rebornModel.modelAvailable && rebornModel.engineAvailable; onClicked: sessionModel.start(root.authorized,root.resume); Layout.fillWidth: true }
                                Label { text: sessionModel.status; textFormat: Text.PlainText; color: theme.muted; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                            }
                        }
                    }
                    Surface {
                        Layout.fillWidth: true
                        padding: 14
                        contentItem: ColumnLayout {
                            Label { text: "Локальная телеметрия"; color: theme.text; font.weight: Font.DemiBold; Layout.fillWidth: true }
                            Label { text: sessionModel.active ? "LIVE / разрешённый компьютерный тест" : rebornModel.source; textFormat: Text.PlainText; color: theme.muted; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                            RowLayout {
                                Layout.fillWidth: true
                                UiButton { text: "Открыть файл"; enabled: !sessionModel.busy; onClicked: replayDialog.open(); Layout.fillWidth: true }
                                UiButton { text: "Очистить"; enabled: !sessionModel.busy; onClicked: rebornModel.clearReplay(); Layout.fillWidth: true }
                            }
                        }
                    }
                }
            }
            Item { JournalPanel { anchors.fill: parent; anchors.margins: 16 } }
            ScrollView {
                id: settings
                clip: true
                contentWidth: availableWidth
                contentHeight: settingsContent.implicitHeight+36
                ColumnLayout {
                    id: settingsContent
                    x: 18; y: 18
                    width: Math.max(1,settings.availableWidth-36)
                    spacing: 12
                    SectionTitle { heading: "Настройки"; description: "Параметры новой оболочки Qt Quick."; Layout.fillWidth: true }
                    Surface {
                        Layout.fillWidth: true
                        contentItem: ColumnLayout {
                            spacing: 10
                            UiToggle { text: "Поверх окон"; checked: root.pinned; enabled: !sessionModel.busy; onToggled: { root.pinned=checked; workspaceModel.setPinned("main",checked) }; Layout.fillWidth: true }
                            UiToggle { text: "Уменьшить анимации"; checked: workspaceModel.reducedMotion; onToggled: workspaceModel.setReducedMotion(checked); Layout.fillWidth: true }
                            Label { text: "Размер текста"; color: theme.muted }
                            RebornSelect { model: ["100%","115%","130%"]; property var scales: [100,115,130]; currentIndex: scales.indexOf(workspaceModel.textScale); onActivated: workspaceModel.setTextScale(scales[currentIndex]); Layout.fillWidth: true }
                            Label { text: "Ctrl+1–3 — разделы · Esc — остановка"; color: theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        }
                    }
                }
            }
        }
    }
}
