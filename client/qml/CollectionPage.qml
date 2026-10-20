import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    Everything of yours: liked tracks, what the wave has played, and what it has
    learned about you. The whole catalogue and uploading are in the admin menu.
*/
Item {
    id: root

    property bool detailOpen: true
    property int tab: 0

    readonly property var tabs: [
        { value: "0", label: qsTr("Избранное") },
        { value: "1", label: qsTr("История") },
        { value: "2", label: qsTr("Профиль вкуса") }
    ]

    function refresh() {
        if (tab === 0)
            library.loadLiked()
        else if (tab === 2)
            wave.refreshProfile()
    }

    onTabChanged: refresh()

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 52

            Segmented {
                anchors.left: parent.left
                anchors.leftMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                options: root.tabs
                current: String(root.tab)
                onPicked: function(value) { root.tab = parseInt(value) }
            }

            Mono {
                anchors.right: parent.right
                anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                visible: root.tab === 0
                text: qsTr("Треков: ") + library.likedCount
                color: Theme.faint
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.border
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            TrackBrowser {
                anchors.fill: parent
                visible: root.tab < 2

                model: root.tab === 0 ? library.liked : wave.history
                context: "liked"
                // History rows carry stream links minted when the track was
                // served, which expire, so they are for reading, not replaying.
                playable: root.tab === 0
                detailOpen: root.detailOpen
                emptyText: root.tab === 0 ? qsTr("Пока ничего не нравится. Ставьте ♥ — и треки появятся здесь.")
                           : qsTr("Пока пусто. Включите волну — здесь появится всё, что в ней прозвучало.")
            }

            // what the wave has learned, as aligned text like a log
            Flickable {
                anchors.fill: parent
                visible: root.tab === 2
                contentWidth: width
                contentHeight: profileColumn.implicitHeight + 32
                boundsBehavior: Flickable.StopAtBounds
                clip: true

                ScrollBar.vertical: FlatScrollBar {}

                Column {
                    id: profileColumn
                    x: 16
                    y: 16
                    width: parent.width - 32
                    spacing: 8

                    Repeater {
                        model: wave.profileLines

                        delegate: Mono {
                            required property string modelData
                            width: profileColumn.width
                            text: modelData
                            color: Theme.muted
                            font.capitalization: Font.MixedCase
                            font.letterSpacing: 0.2
                            font.pixelSize: Theme.fontBody
                            wrapMode: Text.NoWrap
                        }
                    }

                    Mono {
                        visible: wave.profileLines.length === 0
                        text: qsTr("Пока пусто. Послушайте несколько треков, чтобы волна начала учиться.")
                        color: Theme.faint
                    }
                }
            }
        }
    }
}
