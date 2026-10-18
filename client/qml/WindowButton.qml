import QtQuick
import Wavelane

/*! Minimise / maximise / close, drawn to match the rest of the bar. */
Item {
    id: root

    property string glyph: ""
    property bool danger: false

    signal clicked()

    implicitWidth: 46
    implicitHeight: 32

    Rectangle {
        anchors.fill: parent
        color: mouse.containsMouse ? (root.danger ? "#e81123" : Theme.rowSelected) : "transparent"
    }

    Icon {
        anchors.centerIn: parent
        glyph: root.glyph
        font.pixelSize: 10
        color: mouse.containsMouse && root.danger ? "white"
               : (mouse.containsMouse ? Theme.text : Theme.muted)
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        onClicked: root.clicked()
    }
}
