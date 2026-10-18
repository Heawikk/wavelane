import QtQuick
import Wavelane

/*! A keycap, for the shortcut hints. */
Rectangle {
    property string keys: ""

    implicitWidth: Math.max(46, label.implicitWidth + 16)
    implicitHeight: 20
    color: "transparent"
    border.color: Theme.borderStrong
    border.width: 1

    Mono {
        id: label
        anchors.centerIn: parent
        text: parent.keys
        color: Theme.muted
        font.capitalization: Font.MixedCase
        font.letterSpacing: 0.2
        font.pixelSize: 10
    }
}
