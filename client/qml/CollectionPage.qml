import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import Wavelane

/*!
    Everything of yours: liked tracks, the whole catalogue, what the wave has
    played, and what it has learned about you. Uploading lives here too.
*/
Item {
    id: root

    property bool detailOpen: true
    property int tab: 0

    signal toggleDetail()

    readonly property var tabs: [
        { value: "0", label: qsTr("Избранное") },
        { value: "1", label: qsTr("Каталог") },
        { value: "2", label: qsTr("История") },
        { value: "3", label: qsTr("Профиль вкуса") }
    ]

    function openUpload() { fileDialog.open() }

    function refresh() {
        if (tab === 0)
            library.loadLiked()
        else if (tab === 1)
            library.loadCatalogue()
        else if (tab === 3)
            wave.refreshProfile()
    }

    onTabChanged: refresh()

    FileDialog {
        id: fileDialog
        title: qsTr("Выберите аудиофайлы")
        fileMode: FileDialog.OpenFiles
        nameFilters: [
            qsTr("Аудио (*.mp3 *.flac *.m4a *.ogg *.opus *.wav *.aac *.wma *.aiff)"),
            qsTr("Все файлы (*)")
        ]
        onAccepted: library.uploadFiles(selectedFiles)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SectionHeader {
            Layout.fillWidth: true
            number: "03"
            title: qsTr("Коллекция")

            Mono {
                anchors.verticalCenter: parent.verticalCenter
                visible: library.uploadStatus !== ""
                text: library.uploadStatus
                font.capitalization: Font.MixedCase
                color: library.uploading ? Theme.accentText : Theme.muted
                rightPadding: 8
            }
            FlatButton {
                implicitHeight: 26
                glyph: Theme.iAdd
                text: library.uploading ? qsTr("Загрузка…") : qsTr("Загрузить музыку")
                enabledWhen: !library.uploading
                onClicked: root.openUpload()
            }
            IconButton {
                visible: root.tab < 3
                glyph: Theme.iPanel
                active: root.detailOpen
                activeColor: Theme.accentText
                tooltip: qsTr("Панель деталей · Ctrl+B")
                onClicked: root.toggleDetail()
            }
        }

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
                visible: root.tab < 2
                text: root.tab === 0 ? qsTr("Треков: ") + library.likedCount
                                     : qsTr("Треков: ") + library.trackCount
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
                visible: root.tab < 3

                model: root.tab === 0 ? library.liked
                       : root.tab === 1 ? library.catalogue
                       : wave.history
                context: root.tab === 0 ? "liked" : "catalogue"
                // History rows carry stream links minted when the track was
                // served, which expire, so they are for reading, not replaying.
                playable: root.tab < 2
                detailOpen: root.detailOpen
                emptyText: root.tab === 0 ? qsTr("Пока ничего не нравится. Ставьте ♥ — и треки появятся здесь.")
                           : root.tab === 1 ? qsTr("Каталог пуст. Загрузите аудиофайлы: сервер прочитает теги, обложки и проанализирует звук.")
                           : qsTr("Пока пусто. Включите волну — здесь появится всё, что в ней прозвучало.")
            }

            // what the wave has learned, as aligned text like a log
            Flickable {
                anchors.fill: parent
                visible: root.tab === 3
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
