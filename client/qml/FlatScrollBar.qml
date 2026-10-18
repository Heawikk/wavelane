import QtQuick
import QtQuick.Controls
import Wavelane

/*! A thin scroll bar that only shows itself when there is something to scroll. */
ScrollBar {
    id: bar

    implicitWidth: 8
    policy: ScrollBar.AsNeeded
    minimumSize: 0.08

    contentItem: Rectangle {
        implicitWidth: 4
        radius: 0
        color: bar.pressed ? Theme.faint : Theme.borderStrong
        opacity: bar.active || bar.pressed ? 1.0 : 0.0

        Behavior on opacity {
            NumberAnimation { duration: 150 }
        }
    }
    background: Item {}
}
