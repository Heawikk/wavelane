import QtQuick
import QtQuick.Controls
import Wavelane

/*!
    A round, flat icon button.

    The glyph comes from the font rather than an image asset, so the client has
    no icon files to ship or scale.
*/
Item {
    id: root

    property string symbol: ""
    property string tooltip: ""
    property int size: 34
    property int glyphSize: Theme.fontBody
    property color glyphColor: Theme.textMuted
    property color activeColor: Theme.text
    property bool active: false
    property bool enabledWhen: true
    property bool filled: false

    signal clicked()

    implicitWidth: size
    implicitHeight: size
    opacity: enabledWhen ? 1.0 : 0.35

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: {
            if (root.filled)
                return mouse.containsMouse ? Theme.accentAlt : Theme.accent
            if (mouse.containsMouse && root.enabledWhen)
                return Theme.surfaceHover
            return "transparent"
        }

        Behavior on color {
            ColorAnimation { duration: Theme.durationFast }
        }
    }

    Text {
        anchors.centerIn: parent
        text: root.symbol
        color: root.filled ? "white" : (root.active ? root.activeColor : root.glyphColor)
        font.pixelSize: root.glyphSize
        font.family: "Segoe UI Symbol"
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabledWhen
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }

    ToolTip.visible: root.tooltip !== "" && mouse.containsMouse
    ToolTip.text: root.tooltip
    ToolTip.delay: 400
}
