import QtQuick
import Wavelane

/*! A row of mutually exclusive options; the active one is filled white. */
Rectangle {
    id: root

    //! [{ value: "any", label: "Любой" }, ...]
    property var options: []
    property string current: ""
    //! Share the width equally instead of sizing each option to its label.
    property bool stretch: false

    signal picked(string value)

    implicitHeight: 28
    implicitWidth: row.implicitWidth + 2
    color: "transparent"
    border.color: Theme.borderStrong
    border.width: 1

    Row {
        id: row
        anchors.fill: parent
        anchors.margins: 1

        Repeater {
            model: root.options

            delegate: Rectangle {
                id: segment

                required property var modelData
                readonly property bool on: root.current === modelData.value

                height: row.height
                width: root.stretch ? Math.floor(row.width / Math.max(1, root.options.length))
                                    : label.implicitWidth + 26
                color: on ? Theme.light : (hover.containsMouse ? Theme.rowSelected : "transparent")

                Mono {
                    id: label
                    anchors.centerIn: parent
                    text: segment.modelData.label
                    color: segment.on ? Theme.darkOnLight : Theme.muted
                    font.weight: segment.on ? Font.DemiBold : Font.Normal
                }

                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.picked(segment.modelData.value)
                }
            }
        }
    }
}
