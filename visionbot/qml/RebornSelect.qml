import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ComboBox {
    id: control
    implicitHeight: 40
    font.family: theme.font
    font.pixelSize: Math.round(13 * workspaceModel.textScale / 100)
    leftPadding: 12
    rightPadding: 32
    contentItem: Text {
        text: control.displayText || "—"
        textFormat: Text.PlainText
        font: control.font
        color: control.enabled ? theme.text : theme.dim
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        x: control.width-width-12
        y: (control.height-height)/2
        text: control.popup.visible ? "⌃" : "⌄"
        color: theme.muted
        font.pixelSize: 17
    }
    background: Rectangle {
        color: control.enabled ? theme.field : theme.panel
        radius: 8
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? theme.accent : theme.border
    }
    delegate: ItemDelegate {
        required property int index
        required property var modelData
        width: control.width
        height: 36
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: String(modelData)
            textFormat: Text.PlainText
            color: theme.text
            font: control.font
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 5
            color: parent.highlighted || parent.hovered ? theme.active : theme.panel
        }
    }
    popup: Popup {
        y: control.height + 4
        width: control.width
        padding: 5
        implicitHeight: Math.min(contentItem.implicitHeight+10, 240)
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: Rectangle { color: theme.panel; border.color: theme.track; radius: 8 }
    }
}
