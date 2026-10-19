import QtQuick
import QtQuick.Layouts
import Wavelane

/*! The three pages, as tabs along the bottom edge. */
Rectangle {
    id: root

    property string page: "wave"
    signal selected(string name)

    implicitHeight: 56
    color: Theme.bar

    Rectangle {
        width: parent.width
        height: 1
        color: Theme.border
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Repeater {
            model: [
                { name: "search",     glyph: Theme.iSearch,  label: qsTr("Поиск") },
                { name: "wave",       glyph: Theme.iWave,    label: qsTr("Моя волна") },
                { name: "collection", glyph: Theme.iLibrary, label: qsTr("Коллекция") }
            ]

            delegate: Item {
                id: tab

                required property var modelData
                readonly property bool on: root.page === modelData.name

                Layout.fillWidth: true
                Layout.fillHeight: true

                Rectangle {
                    width: parent.width
                    height: 2
                    color: Theme.accent
                    visible: tab.on
                }

                Column {
                    anchors.centerIn: parent
                    spacing: 4

                    Icon {
                        anchors.horizontalCenter: parent.horizontalCenter
                        glyph: tab.modelData.glyph
                        font.pixelSize: 20
                        color: tab.on ? Theme.accentText : Theme.faint
                    }
                    Mono {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: tab.modelData.label
                        font.pixelSize: 10
                        color: tab.on ? Theme.text : Theme.faint
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: root.selected(tab.modelData.name)
                }
            }
        }
    }
}
