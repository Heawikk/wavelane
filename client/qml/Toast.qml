import QtQuick
import Wavelane

/*! A transient message at the bottom of the window. */
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
        anchors.bottomMargin: Theme.playerBarHeight + Theme.spacingLarge
        width: Math.min(label.implicitWidth + 36, root.width - 80)
        height: label.implicitHeight + 24
        radius: Theme.radius
        color: Theme.surfaceActive
        border.color: Theme.border
        border.width: 1
        opacity: 0.0
        visible: opacity > 0.01

        Behavior on opacity {
            NumberAnimation { duration: Theme.durationNormal }
        }

        Text {
            id: label
            anchors.centerIn: parent
            width: parent.width - 36
            color: Theme.text
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
