import QtQuick
import QtQuick.Layouts
import Wavelane

/*!
    The left navigation, laid out like Yandex Music's: logo on top, a short
    list of places, the account at the bottom.
*/
Rectangle {
    id: root

    property string page: "wave"
    required property var window

    signal selected(string page)
    signal openSettings()

    color: Theme.panel

    readonly property var items: [
        { id: "search",     label: qsTr("Поиск"),      glyph: Theme.iSearch },
        { id: "wave",       label: qsTr("Моя волна"),  glyph: Theme.iWave },
        { id: "collection", label: qsTr("Коллекция"),  glyph: Theme.iLibrary }
    ]

    Rectangle {
        anchors.right: parent.right
        width: 1
        height: parent.height
        color: Theme.border
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.rightMargin: 1
        spacing: 0

        // --- logo (also drags the window, like the bar beside it) ---
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 72

            DragHandler {
                target: null
                onActiveChanged: if (active) root.window.startSystemMove()
            }

            Row {
                anchors.left: parent.left
                anchors.leftMargin: 18
                anchors.verticalCenter: parent.verticalCenter
                spacing: 10

                Logo {
                    size: 30
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    text: "Wavelane"
                    color: Theme.text
                    font.family: Theme.sans
                    font.pixelSize: 17
                    font.weight: Font.Bold
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }

        // --- places ---
        Repeater {
            model: root.items

            delegate: Rectangle {
                id: item

                required property var modelData
                readonly property bool on: root.page === modelData.id

                Layout.fillWidth: true
                Layout.preferredHeight: 44
                color: on ? Theme.rowSelected : (hover.containsMouse ? Theme.rowHover : "transparent")

                Rectangle {
                    width: 2
                    height: parent.height
                    color: Theme.accent
                    visible: item.on
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 12
                    spacing: 14

                    Icon {
                        glyph: item.modelData.glyph
                        font.pixelSize: 16
                        color: item.on ? Theme.text : Theme.faint
                    }
                    Text {
                        Layout.fillWidth: true
                        text: item.modelData.label
                        color: item.on ? Theme.text : Theme.muted
                        font.family: Theme.sans
                        font.pixelSize: Theme.fontBody
                        font.weight: item.on ? Font.DemiBold : Font.Normal
                        elide: Text.ElideRight
                    }
                }

                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.selected(item.modelData.id)
                }
            }
        }

        Item { Layout.fillHeight: true }

        // --- the account ---
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            color: "transparent"

            Rectangle {
                width: parent.width
                height: 1
                color: Theme.border
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 8
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 30
                    Layout.preferredHeight: 30
                    radius: 15
                    color: Theme.accent

                    Text {
                        anchors.centerIn: parent
                        text: (auth.displayName || auth.username || "?").charAt(0).toUpperCase()
                        color: "white"
                        font.family: Theme.sans
                        font.pixelSize: Theme.fontBody
                        font.weight: Font.Bold
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    Text {
                        Layout.fillWidth: true
                        text: auth.displayName || auth.username
                        color: Theme.text
                        font.family: Theme.sans
                        font.pixelSize: Theme.fontSmall
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    Mono {
                        Layout.fillWidth: true
                        visible: auth.isAdmin
                        text: qsTr("администратор")
                        font.pixelSize: 10
                        color: Theme.faint
                    }
                }

                IconButton {
                    glyph: Theme.iSettings
                    tooltip: qsTr("Интеграции")
                    onClicked: root.openSettings()
                }

                IconButton {
                    glyph: Theme.iLogout
                    tooltip: qsTr("Выйти")
                    onClicked: auth.signOut()
                }
            }
        }
    }
}
