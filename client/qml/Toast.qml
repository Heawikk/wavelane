import QtQuick
import Wavelane

/*! A transient message, bottom centre, in the same flat style as the rest. */
Item {
    id: root

    property int duration: 3200

    anchors.fill: parent
    z: 1000

    function show(message) {
        if (!message)
            return
        label.text = message
        popup.opacity = 1.0
        hideTimer.restart()
    }

    Rectangle {
        id: popup

        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.transportHeight + 90
        width: Math.min(label.implicitWidth + 36, root.width - 80)
        height: label.implicitHeight + 22
        color: Theme.bar
        border.color: Theme.borderStrong
        border.width: 1
        opacity: 0.0
        visible: opacity > 0.01

        Behavior on opacity {
            NumberAnimation { duration: 160 }
        }

        Rectangle {
            width: 2
            height: parent.height
            color: Theme.accent
        }

        Text {
            id: label
            anchors.centerIn: parent
            width: parent.width - 36
            color: Theme.text
            font.family: Theme.sans
            font.pixelSize: Theme.fontSmall
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }
    }

    Timer {
        id: hideTimer
        interval: root.duration
        onTriggered: popup.opacity = 0.0
    }
}
