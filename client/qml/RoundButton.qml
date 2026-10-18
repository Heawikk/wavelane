import QtQuick
import QtQuick.Controls
import Wavelane

/*!
    A round transport button: big filled play, dimmed prev/next beside it.

    Disabled buttons stay visible but faint instead of disappearing, so the
    row keeps its shape (the wave has no "previous", but the button belongs
    there).
*/
Item {
    id: root

    property string glyph: ""
    property string tooltip: ""
    property int size: 44
    property int glyphSize: Math.round(size * 0.38)
    property bool filled: false
    property bool enabledWhen: true

    signal clicked()

    implicitWidth: size
    implicitHeight: size

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        scale: mouse.pressed ? 0.94 : 1.0
        color: root.filled ? (mouse.containsMouse && root.enabledWhen ? "#ffffff" : Theme.light)
                           : (mouse.containsMouse && root.enabledWhen ? Theme.rowSelected
                                                                      : "transparent")
        border.color: root.filled ? "transparent" : (mouse.containsMouse && root.enabledWhen
                                                      ? Theme.borderStrong : "transparent")
        border.width: 1

        Behavior on scale { NumberAnimation { duration: 80 } }
    }

    Icon {
        anchors.centerIn: parent
        // the play glyph sits optically left of centre inside a circle
        anchors.horizontalCenterOffset: root.glyph === Theme.iPlay ? 2 : 0
        glyph: root.glyph
        font.pixelSize: root.glyphSize
        color: root.filled ? Theme.darkOnLight : (root.enabledWhen ? Theme.text : Theme.faint)
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabledWhen
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }

    ToolTip {
        id: tip
        visible: root.tooltip !== "" && mouse.containsMouse
        text: root.tooltip
        delay: 500
        padding: 6
        contentItem: Mono {
            text: tip.text
            color: Theme.text
        }
        background: Rectangle {
            color: Theme.bar
            border.color: Theme.borderStrong
            border.width: 1
        }
    }
}
