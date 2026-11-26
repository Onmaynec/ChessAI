import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    required property string panelKey
    required property string panelTitle
    property bool pinned: false
    property bool initialized: false
    objectName: "overlay_" + panelKey
    title: panelTitle + " · " + sourceLabel
    color: theme.bg
    visible: false
    transientParent: null
    minimumWidth: panelKey === 'metrics' ? 300 : 320
    minimumHeight: panelKey === 'board' ? 340 : panelKey === 'metrics' ? 240 : 260
    font.family: theme.font
    font.pixelSize: theme.typeScale.body
    flags: Qt.Window | (pinned ? Qt.WindowStaysOnTopHint : 0)

    function remember() {
        if (initialized && visibility === Window.Windowed)
            workspaceModel.record(panelKey, x, y, width, height)
    }
    function openPanel() {
        if (visible) { raise(); requestActivate(); return }
        var g = workspaceModel.geometry(panelKey)
        if (g.length === 4) {
            x = g[0]; y = g[1]; width = g[2]; height = g[3]
        }
        pinned = workspaceModel.pinned(panelKey)
        initialized = true
        show()
        raise()
    }
    onClosing: function(close) { saveTimer.stop(); remember() }
    Timer {
        id: saveTimer
        interval: 400
        repeat: false
        onTriggered: if (win.visible) win.remember()
    }
    onXChanged: if (visible && initialized) saveTimer.restart()
    onYChanged: if (visible && initialized) saveTimer.restart()
    onWidthChanged: if (visible && initialized) saveTimer.restart()
    onHeightChanged: if (visible && initialized) saveTimer.restart()
    header: Rectangle {
        color: theme.panel
        implicitHeight: 48
        RowLayout {
            anchors.fill: parent
            anchors.margins: 8
            Label { text: win.panelTitle; color: theme.text; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
            UiButton {
                text: win.pinned ? "Открепить" : "Закрепить"
                implicitWidth: 100
                selected: win.pinned
                onClicked: { win.pinned = !win.pinned; workspaceModel.setPinned(win.panelKey, win.pinned) }
            }
        }
    }
    Loader {
        anchors.fill: parent
        anchors.margins: 10
        active: win.visible
        sourceComponent: win.panelKey === "metrics" ? metrics : win.panelKey === "board" ? board : win.panelKey === "analysis" ? analysis : journal
    }
    Component { id: metrics; Item { CompactPanel { anchors.fill: parent } } }
    Component {
        id: board
        ScrollView {
            id: boardScroll
            clip: true
            contentWidth: availableWidth
            PositionPanel { width: boardScroll.availableWidth }
        }
    }
    Component {
        id: analysis
        ScrollView {
            id: analysisScroll
            clip: true
            contentWidth: availableWidth
            VariationPanel { width: analysisScroll.availableWidth }
        }
    }
    Component { id: journal; Item { JournalPanel { anchors.fill: parent } } }
}
