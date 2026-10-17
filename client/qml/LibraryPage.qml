import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import Wavelane

/*! Liked tracks, the whole catalogue, and uploading new files. */
Item {
    id: root

    property int tab: 0

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
        anchors.margins: Theme.spacingLarge
        spacing: Theme.spacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacing

            Text {
                text: qsTr("Коллекция")
                color: Theme.text
                font.pixelSize: Theme.fontHeading
                font.weight: Font.Bold
            }

            Item { Layout.fillWidth: true }

            Text {
                visible: library.uploadStatus !== ""
                text: library.uploadStatus
                color: Theme.textMuted
                font.pixelSize: Theme.fontSmall
            }

            BusyIndicator {
                running: library.uploading
                visible: running
                implicitWidth: 22
                implicitHeight: 22
            }

            Button {
                id: uploadButton
                enabled: !library.uploading
                text: qsTr("Загрузить музыку")

                contentItem: Text {
                    text: uploadButton.text
                    color: "white"
                    font.pixelSize: Theme.fontSmall
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    implicitWidth: 160
                    implicitHeight: 36
                    radius: Theme.radiusSmall
                    opacity: uploadButton.enabled ? 1 : 0.5
                    color: uploadButton.hovered ? Qt.lighter(Theme.accent, 1.15) : Theme.accent
                }
                onClicked: fileDialog.open()
            }
        }

        // --- tabs ---
        RowLayout {
            Layout.fillWidth: true
            spacing: 4

            Repeater {
                model: [
                    { label: qsTr("Избранное"), index: 0 },
                    { label: qsTr("Весь каталог"), index: 1 }
                ]

                delegate: Rectangle {
                    required property var modelData
                    readonly property bool selected: root.tab === modelData.index

                    height: 32
                    width: tabLabel.implicitWidth + 28
                    radius: 16
                    color: selected ? Theme.surfaceActive
                                    : (tabMouse.containsMouse ? Theme.surfaceHover
                                                              : "transparent")

                    Text {
                        id: tabLabel
                        anchors.centerIn: parent
                        text: modelData.label
                        color: parent.selected ? Theme.text : Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        font.weight: parent.selected ? Font.DemiBold : Font.Normal
                    }

                    MouseArea {
                        id: tabMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.tab = modelData.index
                            if (modelData.index === 0)
                                library.loadLiked()
                            else
                                library.loadCatalogue()
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            Text {
                text: root.tab === 0
                      ? qsTr("%1 трек(ов) в избранном").arg(library.likedCount)
                      : qsTr("%1 трек(ов) в каталоге").arg(library.trackCount)
                color: Theme.textFaint
                font.pixelSize: Theme.fontTiny
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.tab

            ListView {
                model: library.liked
                clip: true
                spacing: 2
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}

                delegate: TrackRow {
                    required property int index
                    width: ListView.view.width
                    onActivated: library.playFrom(library.liked, index, "liked")
                }

                Text {
                    anchors.centerIn: parent
                    width: parent.width * 0.7
                    visible: library.liked.count === 0
                    text: qsTr("Пока ничего не нравится. Ставьте ♥ в волне — "
                               + "и треки появятся здесь.")
                    color: Theme.textFaint
                    font.pixelSize: Theme.fontBody
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }

            ListView {
                model: library.catalogue
                clip: true
                spacing: 2
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}

                delegate: TrackRow {
                    required property int index
                    width: ListView.view.width
                    onActivated: library.playFrom(library.catalogue, index, "search")
                }

                Text {
                    anchors.centerIn: parent
                    width: parent.width * 0.7
                    visible: library.catalogue.count === 0
                    text: qsTr("Каталог пуст. Загрузите аудиофайлы — сервер прочитает "
                               + "теги, обложки и проанализирует звук.")
                    color: Theme.textFaint
                    font.pixelSize: Theme.fontBody
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
