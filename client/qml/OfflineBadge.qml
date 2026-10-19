import QtQuick
import Wavelane

/*! A slim strip saying the server cannot be reached; it goes away by itself when it can. */
Rectangle {
    id: root

    //! Whether the strip is wanted at all (only while signed in).
    property bool wanted: true
    readonly property bool shown: wanted && api.offline

    implicitHeight: 26
    height: shown ? implicitHeight : 0
    visible: shown
    clip: true
    color: Theme.alpha(Theme.warning, 0.16)

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.alpha(Theme.warning, 0.5)
    }

    Row {
        anchors.centerIn: parent
        spacing: 8

        Rectangle {
            width: 6
            height: 6
            radius: 3
            color: Theme.warning
            anchors.verticalCenter: parent.verticalCenter

            SequentialAnimation on opacity {
                running: root.shown
                loops: Animation.Infinite
                NumberAnimation { to: 0.25; duration: 700 }
                NumberAnimation { to: 1.0; duration: 700 }
            }
        }
        Mono {
            text: qsTr("Нет соединения с сервером")
            color: Theme.warning
            font.pixelSize: 11
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
