import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    objectName: "visionWorkspace"
    width: 1200
    height: 800
    minimumWidth: mode === 'compact' ? 320 : 560
    minimumHeight: mode === 'compact' ? 260 : 480
    visible: true
    flags: Qt.Window | (pinned ? Qt.WindowStaysOnTopHint : 0)
    title: "Vision Bot · " + appVersion + " · Preview"
    color: theme.bg
    font.family: theme.font
    font.pixelSize: Math.round(13 * workspaceModel.textScale / 100)
    property int page: 0
    property string mode: "standard"
    property bool pinned: false
    property bool initialized: false
    readonly property bool wide: width >= 1000
    readonly property bool compactMode: mode === "compact"
    readonly property var pages: ["Обзор", "Анализ", "Журнал", "Настройки", "Компоненты"]


    function remember() {
        if (initialized && visibility === Window.Windowed)
            workspaceModel.record(mode, x, y, width, height)
    }
    function applyGeometry(key) {
        var g = workspaceModel.geometry(key)
        if (g.length === 4) {
            x = g[0]; y = g[1]; width = g[2]; height = g[3]
        }
    }
    function switchMode(next) {
        if (next === mode || ["compact","standard","expanded"].indexOf(next) < 0) return
        geometryTimer.stop()
        remember()
        initialized = false
        if (visibility !== Window.Windowed) showNormal()
        mode = next
        applyGeometry(mode)
        workspaceModel.setMode(mode)
        initialized = true
    }
    function openOverlay(key) {
        if (key === "metrics") metricsOverlay.openPanel()
        else if (key === "board") boardOverlay.openPanel()
        else if (key === "analysis") analysisOverlay.openPanel()
        else if (key === "journal") journalOverlay.openPanel()
    }
    Component.onCompleted: {
        mode = workspaceModel.initialMode()
        pinned = workspaceModel.pinned("main")
        applyGeometry(mode)
        initialized = true
    }
    onClosing: function(close) {
        geometryTimer.stop()
        remember()
        metricsOverlay.close()
        boardOverlay.close()
        analysisOverlay.close()
        journalOverlay.close()
    }
    Timer {
        id: geometryTimer
        interval: 400
        repeat: false
        onTriggered: root.remember()
    }
    onXChanged: if (initialized) geometryTimer.restart()
    onYChanged: if (initialized) geometryTimer.restart()
    onWidthChanged: if (initialized) geometryTimer.restart()
    onHeightChanged: if (initialized) geometryTimer.restart()
    OverlayWindow { id: metricsOverlay; panelKey: "metrics"; panelTitle: "Метрики" }
    OverlayWindow { id: boardOverlay; panelKey: "board"; panelTitle: "Доска" }
    OverlayWindow { id: analysisOverlay; panelKey: "analysis"; panelTitle: "Варианты" }
    OverlayWindow { id: journalOverlay; panelKey: "journal"; panelTitle: "Журнал" }
    Shortcut { sequence: "Ctrl+Shift+M"; onActivated: root.switchMode(root.compactMode ? "standard" : "compact") }
    Shortcut { sequence: "Ctrl+1"; enabled: !root.compactMode; onActivated: root.page = 0 }
    Shortcut { sequence: "Ctrl+2"; enabled: !root.compactMode; onActivated: root.page = 1 }
    Shortcut { sequence: "Ctrl+3"; enabled: !root.compactMode; onActivated: root.page = 2 }
    Shortcut { sequence: "Ctrl+4"; enabled: !root.compactMode; onActivated: root.page = 3 }
    Shortcut { sequence: "Ctrl+5"; enabled: !root.compactMode; onActivated: root.page = 4 }

    header: Rectangle {
        color: theme.bg
        implicitHeight: root.compactMode ? 48 : 64
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            spacing: 12
            Label { text: "VISION BOT"; font.weight: Font.Bold; font.pixelSize: Math.round(18 * workspaceModel.textScale / 100); color: theme.text }
            Label { text: appVersion; visible: !root.compactMode; color: theme.muted; font.pixelSize: Math.round(12 * workspaceModel.textScale / 100) }
            Item { Layout.fillWidth: true }
            ComboBox {
                id: modePicker
                model: ["Compact", "Standard", "Expanded"]
                property var keys: ["compact","standard","expanded"]
                currentIndex: Math.max(0,keys.indexOf(root.mode))
                onActivated: root.switchMode(keys[currentIndex])
                Layout.preferredWidth: 114
                palette.button: theme.field
                palette.buttonText: theme.text
                palette.base: theme.panel
                palette.text: theme.text
                palette.highlight: theme.active
                palette.highlightedText: theme.text
                Accessible.name: "Режим рабочего пространства"
            }
            Label {
                visible: !root.compactMode
                text: sourceLabel
                color: theme.warning
                font.pixelSize: Math.round(11 * workspaceModel.textScale / 100)
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                Layout.maximumWidth: 180
            }
        }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
    }
    footer: Rectangle {
        implicitHeight: root.compactMode ? 26 : 34
        color: theme.bg
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            Label { text: "Только просмотр · без управления партией"; color: theme.muted; font.pixelSize: Math.round(11 * workspaceModel.textScale / 100); Layout.fillWidth: true; elide: Text.ElideRight }
            Label { text: "Qt Quick"; color: theme.dim; font.pixelSize: Math.round(11 * workspaceModel.textScale / 100) }
        }
        Rectangle { width: parent.width; height: 1; color: theme.border }
    }

    RowLayout {
        anchors.fill: parent
        visible: !root.compactMode
        spacing: 0
        Rectangle {
            color: theme.panel
            Layout.fillHeight: true
            Layout.preferredWidth: root.wide ? 208 : Math.round(116 * workspaceModel.textScale / 100)
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 6
                Label { text: "РАБОЧАЯ СРЕДА"; color: theme.dim; font.pixelSize: Math.round(10 * workspaceModel.textScale / 100); Layout.fillWidth: true; elide: Text.ElideRight; Layout.topMargin: 8; Layout.bottomMargin: 8 }
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
                Label { text: "LOCAL / READ ONLY"; color: theme.dim; font.pixelSize: Math.round(10 * workspaceModel.textScale / 100); Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: theme.border }
        }

        StackLayout {
            id: workspace
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.page
            onCurrentIndexChanged: {
                pageFade.stop()
                opacity = 1
                if (root.initialized && !workspaceModel.reducedMotion && !root.compactMode) {
                    opacity = 0.72
                    pageFade.start()
                }
            }
            NumberAnimation { id: pageFade; target: workspace; property: "opacity"; to: 1; duration: theme.motion.page; easing.type: Easing.OutCubic }
            Connections {
                target: workspaceModel
                function onMotionChanged() { if (workspaceModel.reducedMotion) { pageFade.stop(); workspace.opacity = 1 } }
            }

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
                                StatusLabel { label: visionModel.active ? "Активна" : "Нет активной сессии"; tone: visionModel.active ? "success" : "neutral" }
                            }
                            Rectangle { height: 1; color: theme.border; Layout.fillWidth: true }
                            Label { text: "Источник: " + sourceLabel; color: theme.text; Layout.fillWidth: true; wrapMode: Text.Wrap }
                            Label { text: "Модель: " + (visionModel.model || "—"); textFormat: Text.PlainText; color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        }
                    }
                    GridLayout {
                        columns: root.wide ? 3 : 1
                        columnSpacing: 10
                        rowSpacing: 10
                        Layout.fillWidth: true
                        Metric { label: "Предложенный ход"; value: visionModel.boardView.move; detail: "Полученная телеметрия"; Layout.fillWidth: true }
                        Metric { label: "Оценка"; value: visionModel.boardView.score; detail: "Сообщено источником"; Layout.fillWidth: true }
                        Metric { label: "Глубина"; value: visionModel.boardView.depth; detail: "Полуходы"; Layout.fillWidth: true }
                    }
                    GridLayout {
                        columns: root.mode === "expanded" && root.wide ? 2 : 1
                        Layout.fillWidth: true
                        columnSpacing: 12
                        rowSpacing: 12
                        PositionPanel { Layout.fillWidth: true; Layout.preferredWidth: 500; Layout.alignment: Qt.AlignTop }
                        VariationPanel { visible: root.mode === "expanded"; Layout.fillWidth: true; Layout.preferredWidth: 260; Layout.alignment: Qt.AlignTop }
                    }
                    UiButton { text: "Подробный анализ"; onClicked: root.page = 1; Layout.alignment: Qt.AlignLeft }
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
                        PositionPanel { Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; Layout.preferredWidth: 490 }
                        VariationPanel { Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; Layout.preferredWidth: 260 }
                    }
                    GridLayout {
                        columns: root.wide ? 2 : 1
                        Layout.fillWidth: true
                        columnSpacing: 12
                        rowSpacing: 12
                        Metric { label: "Оценка стороны хода"; value: visionModel.boardView.score; Layout.fillWidth: true }
                        Metric { label: "Глубина"; value: visionModel.boardView.depth; Layout.fillWidth: true }
                        Metric { label: "Ожидаемый ответ"; value: visionModel.boardView.reply; Layout.fillWidth: true }
                        Metric { label: "Время расчёта"; value: visionModel.boardView.seconds; Layout.fillWidth: true }
                    }
                    Surface {
                        Layout.fillWidth: true
                        contentItem: ColumnLayout {
                            Label { text: "FEN выбранной записи"; color: theme.text; font.pixelSize: Math.round(16 * workspaceModel.textScale / 100) }
                            TextArea {
                                text: visionModel.boardView.fen || "Нет данных"
                                readOnly: true
                                textFormat: TextEdit.PlainText
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
                JournalPanel { anchors.fill: parent; anchors.margins: 20 }
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
                            Label { text: "Оформление"; color: theme.text; font.pixelSize: Math.round(17 * workspaceModel.textScale / 100); font.weight: Font.DemiBold }
                            Label { text: "Monochrome · #000000"; color: theme.muted }
                            UiToggle { id: top; text: "Поверх окон (только preview)"; checked: root.pinned; Layout.fillWidth: true; onToggled: { root.pinned = checked; workspaceModel.setPinned("main",checked) } }
                            Label { text: "Размер текста"; color: theme.muted; Layout.fillWidth: true }
                            ComboBox {
                                objectName: "textScalePicker"
                                model: ["100%", "115%", "130%"]
                                property var scales: [100,115,130]
                                currentIndex: scales.indexOf(workspaceModel.textScale)
                                onActivated: workspaceModel.setTextScale(scales[currentIndex])
                                Layout.fillWidth: true
                                Accessible.name: "Размер текста"
                                palette.button: theme.field
                                palette.buttonText: theme.text
                                palette.base: theme.panel
                                palette.text: theme.text
                            }
                            UiToggle { objectName: "settingsMotionToggle"; text: "Уменьшить анимации"; checked: workspaceModel.reducedMotion; Layout.fillWidth: true; onToggled: workspaceModel.setReducedMotion(checked) }
                            Label { text: "Ctrl+1–5 — разделы · Ctrl+Shift+M — компактный режим"; color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                            Label { text: workspaceModel.error; visible: text.length > 0; textFormat: Text.PlainText; color: theme.red; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        }
                    }
                    Surface {
                        Layout.fillWidth: true
                        contentItem: ColumnLayout {
                            spacing: 8
                            Label { text: "Независимые панели"; color: theme.text; font.pixelSize: Math.round(17 * workspaceModel.textScale / 100) }
                            Repeater {
                                model: [{key:"metrics",name:"Метрики"},{key:"board",name:"Доска"},{key:"analysis",name:"Варианты"},{key:"journal",name:"Журнал"}]
                                delegate: UiButton {
                                    required property var modelData
                                    text: "Открыть · " + modelData.name
                                    Layout.fillWidth: true
                                    onClicked: root.openOverlay(modelData.key)
                                }
                            }
                            Label { text: "Размер и положение сохраняются отдельно для каждой панели."; color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        }
                    }
                    Surface {
                        Layout.fillWidth: true
                        contentItem: ColumnLayout {
                            Label { text: "Режим работы"; color: theme.text; font.pixelSize: Math.round(17 * workspaceModel.textScale / 100) }
                            Label { text: "Запуск сессии, калибровка и управление доступны в прежнем интерфейсе. Здесь нет активных команд."; color: theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        }
                    }
                }
            }
            Loader {
                active: root.page === 4
                sourceComponent: Component { ComponentGallery {} }
            }
        }
    }
    ScrollView {
        id: compactScroll
        anchors.fill: parent
        visible: root.compactMode
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: compactScroll.availableWidth - 20
            x: 10; y: 8
            spacing: 8
            CompactPanel { Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                UiButton { text: "Доска"; Layout.fillWidth: true; implicitWidth: 70; onClicked: root.openOverlay("board") }
                UiButton { text: "Журнал"; Layout.fillWidth: true; implicitWidth: 70; onClicked: root.openOverlay("journal") }
                UiButton { text: root.pinned ? "Открепить" : "Закрепить"; Layout.fillWidth: true; implicitWidth: 90; onClicked: { root.pinned = !root.pinned; workspaceModel.setPinned("main",root.pinned) } }
            }
        }
    }

}
