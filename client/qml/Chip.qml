import QtQuick
import Wavelane

/*! One option of a few, as a flat outlined tile; the chosen one is filled white. */
Rectangle {
    id: root

    property string label: ""
    property bool on: false

    signal clicked()

    implicitHeight: 40
    implicitWidth: text.implicitWidth + 28
    color: on ? Theme.light : (press.pressed ? Theme.rowSelected : "transparent")
    border.color: on ? Theme.light : Theme.borderStrong
    border.width: 1

    Mono {
        id: text
        anchors.centerIn: parent
        text: root.label
        color: root.on ? Theme.darkOnLight : Theme.muted
        font.weight: root.on ? Font.DemiBold : Font.Normal
        font.pixelSize: 12
    }

    MouseArea {
        id: press
        anchors.fill: parent
        onClicked: root.clicked()
    }
}
