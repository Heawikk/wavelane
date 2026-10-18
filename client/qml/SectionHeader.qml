import QtQuick
import Wavelane

/*! A numbered panel heading ("01 ИСТОЧНИКИ") with room for actions on the right. */
Rectangle {
    id: root

    property string number: "01"
    property string title: ""

    //! Anything declared inside lands in the right-hand action row.
    default property alias actions: actionRow.data

    implicitHeight: Theme.headerHeight
    color: "transparent"

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.border
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10

        Rectangle {
            width: 18
            height: 16
            color: Theme.accent
            anchors.verticalCenter: parent.verticalCenter

            Mono {
                anchors.centerIn: parent
                text: root.number
                color: "white"
                font.pixelSize: 10
                font.weight: Font.Bold
            }
        }

        Mono {
            text: root.title
            color: Theme.text
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Row {
        id: actionRow
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        spacing: 4
    }
}
