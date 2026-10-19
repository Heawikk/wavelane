import QtQuick
import QtQuick.Controls
import Wavelane

/*! A square, flat icon button. */
Item {
    id: root

    property string glyph: ""
    property string tooltip: ""
    property int size: 28
    property int glyphSize: 14
    property bool active: false
    property color activeColor: Theme.text
    property bool enabledWhen: true
    //! Solid white fill with a dark glyph, like the primary segment.
    property bool filled: false

    signal clicked()

    implicitWidth: size
    implicitHeight: size
    opacity: enabledWhen ? 1.0 : 0.35

    Rectangle {
        anchors.fill: parent
        color: root.filled ? (mouse.containsMouse ? "#ffffff" : Theme.light)
                           : (mouse.containsMouse && root.enabledWhen ? Theme.rowSelected
                                                                      : "transparent")
        border.color: root.filled ? "transparent" : (mouse.containsMouse ? Theme.borderStrong
                                                                         : "transparent")
        border.width: 1
    }

    Icon {
        anchors.centerIn: parent
        glyph: root.glyph
        font.pixelSize: root.glyphSize
        color: root.filled ? Theme.darkOnLight : (root.active ? root.activeColor : Theme.muted)
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
        visible: root.tooltip !== "" && mouse.containsMouse && !Theme.mobileIcons
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
