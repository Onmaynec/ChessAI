import QtQuick
import QtQuick.Controls

Item {
    id: board
    property var position: ({cells: [], arrow: {}})
    property bool black: false
    readonly property real edge: Math.max(1, Math.min(width - 22, height - 22))
    readonly property real squareSize: edge / 8
    implicitWidth: 400
    implicitHeight: 400
    Accessible.name: "Шахматная позиция, только просмотр"
    Rectangle {
        id: grid
        x: 18
        y: 0
        width: board.edge
        height: board.edge
        color: theme.field
        Repeater {
            model: 64
            delegate: Rectangle {
                required property int index
                readonly property var cell: board.position.cells[index] || ({piece:"",square:""})
                x: (index % 8) * board.squareSize
                y: Math.floor(index / 8) * board.squareSize
                width: board.squareSize
                height: board.squareSize
                color: (index % 8 + Math.floor(index / 8)) % 2 === 0 ? "#c8c8c8" : "#727272"
                Rectangle {
                    anchors.fill: parent
                    color: "transparent"
                    border.width: 2
                    border.color: "#e9b963"
                    visible: {
                        var a = board.position.arrow
                        return a.x1 !== undefined && ((index % 8 === a.x1 && Math.floor(index/8) === a.y1) || (index%8 === a.x2 && Math.floor(index/8) === a.y2))
                    }
                }
                Image {
                    anchors.centerIn: parent
                    width: parent.width * 0.88
                    height: width
                    sourceSize.width: Math.ceil(width * 2)
                    sourceSize.height: sourceSize.width
                    source: cell.piece ? "pieces/" + (cell.piece === cell.piece.toUpperCase() ? "w" : "b") + cell.piece.toLowerCase() + ".svg" : ""
                    fillMode: Image.PreserveAspectFit
                }
            }
        }
        Canvas {
            id: arrowCanvas
            anchors.fill: parent
            property var arrow: board.position.arrow
            onArrowChanged: requestPaint()
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0,0,width,height)
                if (arrow.x1 === undefined) return
                var s = board.squareSize
                var x1 = (arrow.x1+.5)*s, y1 = (arrow.y1+.5)*s
                var x2 = (arrow.x2+.5)*s, y2 = (arrow.y2+.5)*s
                var angle = Math.atan2(y2-y1,x2-x1)
                var tip = s*.29
                ctx.strokeStyle = "#d59a32"
                ctx.fillStyle = "#d59a32"
                ctx.lineWidth = Math.max(2,s*.10)
                ctx.lineCap = "round"
                ctx.beginPath()
                ctx.moveTo(x1,y1)
                ctx.lineTo(x2-tip*.5*Math.cos(angle),y2-tip*.5*Math.sin(angle))
                ctx.stroke()
                ctx.beginPath()
                ctx.moveTo(x2,y2)
                ctx.lineTo(x2-tip*Math.cos(angle-.55),y2-tip*Math.sin(angle-.55))
                ctx.lineTo(x2-tip*Math.cos(angle+.55),y2-tip*Math.sin(angle+.55))
                ctx.closePath()
                ctx.fill()
            }
        }
        Rectangle {
            anchors.fill: parent
            visible: board.position.cells.length !== 64
            color: theme.panel
            opacity: .94
            Label { anchors.centerIn: parent; text: "Нет корректной позиции"; color: theme.muted }
        }
    }
    Repeater {
        model: 8
        delegate: Label {
            required property int index
            x: 0
            y: (index+.5)*board.squareSize-height/2
            text: board.black ? index+1 : 8-index
            color: theme.muted
            font.pixelSize: 10
        }
    }
    Repeater {
        model: 8
        delegate: Label {
            required property int index
            x: 18+(index+.5)*board.squareSize-width/2
            y: board.edge+3
            text: (board.black ? "hgfedcba" : "abcdefgh")[index]
            color: theme.muted
            font.pixelSize: 10
        }
    }
}
