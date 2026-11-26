import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: gallery
    objectName: "componentGallery"
    clip: true
    contentWidth: availableWidth
    contentHeight: galleryContent.implicitHeight + 40
    property int demoClicks: 0
    property bool demoSelected: false

    ColumnLayout {
        id: galleryContent
        width: Math.max(1,gallery.availableWidth - 40)
        x: 20; y: 20
        spacing: 16
        SectionTitle {
            heading: "Component Gallery"
            description: "Интерактивный каталог реальных компонентов интерфейса. Демонстрационные состояния не относятся к партии."
            Layout.fillWidth: true
        }
        Surface {
            Layout.fillWidth: true
            contentItem: ColumnLayout {
                spacing: 12
                Label { text: "01 / Controls"; color: theme.text; font.pixelSize: Math.round(theme.typeScale.section * workspaceModel.textScale / 100); font.weight: Font.DemiBold }
                Flow {
                    Layout.fillWidth: true
                    Layout.preferredHeight: implicitHeight
                    spacing: 8
                    UiButton { text: "Primary"; primary: true; onClicked: gallery.demoClicks++ }
                    UiButton { text: "Secondary"; onClicked: gallery.demoClicks++ }
                    UiButton { text: "Selected"; selected: gallery.demoSelected; onClicked: gallery.demoSelected = !gallery.demoSelected }
                    UiButton { text: "Disabled"; enabled: false }
                }
                Label { text: "Демо-нажатия: " + gallery.demoClicks; color: theme.muted; Layout.fillWidth: true }
                UiToggle { text: "Demo toggle"; Layout.fillWidth: true }
                UiToggle {
                    objectName: "galleryMotionToggle"
                    text: "Уменьшить анимации во всех окнах"
                    checked: workspaceModel.reducedMotion
                    onToggled: workspaceModel.setReducedMotion(checked)
                    Layout.fillWidth: true
                }
                Label { text: "Tab / Shift+Tab — фокус; Space / Enter — активация кнопки."; color: theme.dim; wrapMode: Text.Wrap; Layout.fillWidth: true }
            }
        }
        Surface {
            Layout.fillWidth: true
            contentItem: ColumnLayout {
                spacing: 10
                Label { text: "02 / Semantic status"; color: theme.text; font.pixelSize: Math.round(theme.typeScale.section * workspaceModel.textScale / 100); font.weight: Font.DemiBold }
                StatusLabel { label: "Ожидание"; tone: "neutral"; Layout.fillWidth: true }
                StatusLabel { label: "Готово"; tone: "success"; Layout.fillWidth: true }
                StatusLabel { label: "Требуется внимание"; tone: "warning"; Layout.fillWidth: true }
                StatusLabel { label: "Ошибка"; tone: "error"; Layout.fillWidth: true }
            }
        }
        Surface {
            Layout.fillWidth: true
            contentItem: ColumnLayout {
                spacing: 10
                Label { text: "03 / Typography"; color: theme.text; font.pixelSize: Math.round(theme.typeScale.section * workspaceModel.textScale / 100); font.weight: Font.DemiBold }
                Repeater {
                    model: [{name:"Heading",size:theme.typeScale.heading},{name:"Section",size:theme.typeScale.section},{name:"Body",size:theme.typeScale.body},{name:"Caption",size:theme.typeScale.caption}]
                    delegate: Label {
                        required property var modelData
                        text: modelData.name + " / " + modelData.size + " px"
                        font.pixelSize: modelData.size
                        color: theme.text
                        Layout.fillWidth: true
                    }
                }
                Label { text: "Monospace 0123456789"; color: theme.muted; font.family: theme.mono; Layout.fillWidth: true }
            }
        }
        Surface {
            Layout.fillWidth: true
            contentItem: ColumnLayout {
                spacing: 10
                Label { text: "04 / Palette"; color: theme.text; font.pixelSize: Math.round(theme.typeScale.section * workspaceModel.textScale / 100); font.weight: Font.DemiBold }
                Repeater {
                    model: [{name:"Background",value:theme.bg},{name:"Surface",value:theme.panel},{name:"Control",value:theme.field},{name:"Border",value:theme.border},{name:"Text",value:theme.text},{name:"Muted",value:theme.muted}]
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Rectangle { color: modelData.value; border.color: theme.track; radius: 4; Layout.preferredWidth: 30; Layout.preferredHeight: 24 }
                        Label { text: modelData.name; color: theme.text; Layout.fillWidth: true }
                        Label { text: modelData.value; color: theme.muted; font.family: theme.mono }
                    }
                }
            }
        }
        Metric { label: "05 / Metric empty"; value: "—"; detail: "Нет данных · без выдуманной телеметрии"; Layout.fillWidth: true }
        Item { Layout.preferredHeight: 20 }
    }
}
