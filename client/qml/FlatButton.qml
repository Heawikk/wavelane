import QtQuick
import Wavelane

/*! A rectangular text button; `primary` makes it the white call to action. */
Item {
    id: root

    property string text: ""
    property string glyph: ""
    property bool primary: false
    property bool danger: false
    property bool enabledWhen: true
    property int horizontalPadding: 14

    signal clicked()

    implicitHeight: 30
    implicitWidth: content.implicitWidth + 2 * horizontalPadding
    opacity: enabledWhen ? 1.0 : 0.4

    Rectangle {
        anchors.fill: parent
        color: root.primary ? (mouse.containsMouse && root.enabledWhen ? "#ffffff" : Theme.light)
                            : (mouse.containsMouse && root.enabledWhen ? Theme.rowSelected
                                                                       : "transparent")
        border.color: root.primary ? "transparent"
                                   : (root.danger ? Theme.negative : Theme.borderStrong)
        border.width: 1
    }

    Row {
        id: content
        anchors.centerIn: parent
        spacing: 8

        Icon {
            visible: root.glyph !== ""
            glyph: root.glyph
            font.pixelSize: 13
            color: root.primary ? Theme.darkOnLight : (root.danger ? Theme.negative : Theme.text)
            anchors.verticalCenter: parent.verticalCenter
        }

        Mono {
            visible: root.text !== ""
            text: root.text
            font.weight: Font.DemiBold
            color: root.primary ? Theme.darkOnLight : (root.danger ? Theme.negative : Theme.text)
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabledWhen
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
