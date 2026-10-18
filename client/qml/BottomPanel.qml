import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    "04": a console-style panel with the listening history and the taste
    profile, so the way the wave is learning is visible rather than implied.
*/
Rectangle {
    id: root

    property bool open: true
    property int tab: 0

    signal toggle()

    readonly property int bodyHeight: 112

    color: Theme.panel
    implicitHeight: Theme.headerHeight + 1 + (open ? bodyHeight : 0)

    Behavior on implicitHeight {
        NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
    }

    Rectangle {
        width: parent.width
        height: 1
        color: Theme.border
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 1
        spacing: 0

        // --- header with tabs ---
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.headerHeight

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.border
                visible: root.open
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
                        text: "04"
                        color: "white"
                        font.pixelSize: 10
                        font.weight: Font.Bold
                    }
                }

                Repeater {
                    model: [qsTr("История"), qsTr("Профиль вкуса")]

                    delegate: Item {
                        id: tabItem

                        required property string modelData
                        required property int index
                        readonly property bool on: root.tab === index

                        width: tabLabel.implicitWidth + 14
                        height: Theme.headerHeight

                        Mono {
                            id: tabLabel
                            anchors.centerIn: parent
                            text: tabItem.modelData
                            color: tabItem.on ? Theme.text : Theme.faint
                            font.weight: tabItem.on ? Font.DemiBold : Font.Normal
                        }

                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: 2
                            color: Theme.accent
                            visible: tabItem.on
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                root.tab = tabItem.index
                                if (tabItem.index === 1)
                                    wave.refreshProfile()
                                if (!root.open)
                                    root.toggle()
                            }
                        }
                    }
                }
            }

            Row {
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4

                Mono {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: root.tab === 0
                    text: wave.history.count > 0 ? qsTr("Треков: ") + wave.history.count : ""
                    color: Theme.faint
                    rightPadding: 8
                }

                IconButton {
                    glyph: root.open ? Theme.iChevronDown : Theme.iChevronUp
                    tooltip: qsTr("Показать / скрыть · Ctrl+J")
                    onClicked: root.toggle()
                }
            }
        }

        // --- body ---
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.open
            clip: true

            // history: newest on top
            ListView {
                anchors.fill: parent
                visible: root.tab === 0
                model: wave.history
                // Like a log: oldest at the top, and it follows the newest line.
                onCountChanged: Qt.callLater(positionViewAtEnd)
                boundsBehavior: Flickable.StopAtBounds
                clip: true
                ScrollBar.vertical: FlatScrollBar {}

                delegate: Item {
                    id: line

                    required property int index
                    required property string title
                    required property string artistName
                    required property string reason

                    width: ListView.view.width
                    height: 22

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 12

                        Mono {
                            Layout.preferredWidth: 28
                            text: line.index + 1
                            color: Theme.faint
                        }
                        Text {
                            Layout.preferredWidth: parent.width * 0.34
                            text: line.title
                            color: Theme.text
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontSmall
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.preferredWidth: parent.width * 0.24
                            text: line.artistName
                            color: Theme.muted
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontSmall
                            elide: Text.ElideRight
                        }
                        Mono {
                            Layout.fillWidth: true
                            text: line.reason
                            color: Theme.faint
                            font.capitalization: Font.MixedCase
                            font.letterSpacing: 0.2
                        }
                    }
                }
            }

            // profile: aligned text, like a log
            Flickable {
                anchors.fill: parent
                visible: root.tab === 1
                contentWidth: width
                contentHeight: profileColumn.implicitHeight + 16
                boundsBehavior: Flickable.StopAtBounds
                clip: true

                ScrollBar.vertical: FlatScrollBar {}

                Column {
                    id: profileColumn
                    x: 10
                    y: 8
                    width: parent.width - 20
                    spacing: 5

                    Repeater {
                        model: wave.profileLines

                        delegate: Mono {
                            required property string modelData
                            width: profileColumn.width
                            text: modelData
                            color: Theme.muted
                            font.capitalization: Font.MixedCase
                            font.letterSpacing: 0.2
                            font.pixelSize: Theme.fontSmall
                            wrapMode: Text.NoWrap
                            // the label is the first 11 characters; the rest is the value
                            textFormat: Text.PlainText
                        }
                    }
                }
            }

            Mono {
                anchors.left: parent.left
                anchors.leftMargin: 10
                anchors.top: parent.top
                anchors.topMargin: 10
                visible: (root.tab === 0 && wave.history.count === 0)
                         || (root.tab === 1 && wave.profileLines.length === 0)
                text: root.tab === 0
                      ? qsTr("Пока пусто. Включите волну, чтобы увидеть историю.")
                      : qsTr("Пока пусто. Послушайте несколько треков, чтобы волна начала учиться.")
                color: Theme.faint
            }
        }
    }
}
