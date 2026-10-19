import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! What is yours: liked tracks, the whole catalogue, what the wave played, the taste profile. */
Item {
    id: root

    property int tab: 0

    readonly property var tabs: [
        { value: "0", label: qsTr("Мои") },
        { value: "1", label: qsTr("Каталог") },
        { value: "2", label: qsTr("История") },
        { value: "3", label: qsTr("Вкус") }
    ]

    function refresh() {
        if (tab === 0)
            library.loadLiked()
        else if (tab === 1)
            library.loadCatalogue()
        else if (tab === 3)
            wave.refreshProfile()
    }

    onTabChanged: refresh()

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 56

            Segmented {
                anchors.fill: parent
                anchors.margins: 10
                anchors.topMargin: 12
                anchors.bottomMargin: 8
                stretch: true
                options: root.tabs
                current: String(root.tab)
                onPicked: function(value) { root.tab = parseInt(value) }
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

            MobileTrackList {
                anchors.fill: parent
                visible: root.tab < 3

                model: root.tab === 0 ? library.liked
                       : root.tab === 1 ? library.catalogue
                       : wave.history
                context: root.tab === 0 ? "liked" : "catalogue"
                // History rows carry stream links minted when the track was served,
                // which expire, so they are for reading, not replaying.
                playable: root.tab < 2
                emptyText: root.tab === 0 ? qsTr("Пока ничего не нравится. Ставьте сердечко, и треки появятся здесь.")
                           : root.tab === 1 ? qsTr("Каталог пуст.")
                           : qsTr("Пока пусто. Включите волну, и здесь появится всё, что в ней прозвучало.")
            }

            Flickable {
                anchors.fill: parent
                visible: root.tab === 3
                contentWidth: width
                contentHeight: profileColumn.implicitHeight + 32
                boundsBehavior: Flickable.StopAtBounds
                clip: true

                Column {
                    id: profileColumn
                    x: 16
                    y: 16
                    width: parent.width - 32
                    spacing: 10

                    Repeater {
                        model: wave.profileLines

                        delegate: Mono {
                            required property string modelData
                            width: profileColumn.width
                            text: modelData
                            color: Theme.muted
                            font.capitalization: Font.MixedCase
                            font.letterSpacing: 0.2
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                        }
                    }

                    Mono {
                        width: profileColumn.width
                        visible: wave.profileLines.length === 0
                        text: qsTr("Пока пусто. Послушайте несколько треков, чтобы волна начала учиться.")
                        color: Theme.faint
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                    }
                }
            }
        }
    }
}
