import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The metadata of a track, for an administrator to correct: title, artists, album, year,
    number, genres. Names with more than one value are separated by commas.

    Ask for it with openFor(trackId); it opens once the server has sent the full record.
*/
Popup {
    id: root

    property string trackId: ""
    //! The record was asked for and this dialog is the one waiting for it.
    property bool waiting: false
    property bool explicitValue: false

    readonly property bool canSave: titleField.inputText.trim() !== ""
                                    && artistsField.inputText.trim() !== "" && !library.saving

    function openFor(id) {
        if (!id)
            return
        trackId = id
        waiting = true
        library.beginTrackEdit(id)
    }

    function save() {
        library.saveTrack(root.trackId, {
            title: titleField.inputText,
            artists: artistsField.inputText,
            featured: featuredField.inputText,
            album: albumField.inputText,
            year: parseInt(yearField.inputText) || 0,
            trackNumber: numberField.inputText === "" ? -1 : parseInt(numberField.inputText),
            genres: genresField.inputText,
            explicit: root.explicitValue
        })
    }

    Connections {
        target: library

        function onTrackEditReady() {
            if (!root.waiting)
                return
            root.waiting = false
            const track = library.trackEdit
            titleField.inputText = track.title
            artistsField.inputText = track.artists
            featuredField.inputText = track.featured
            albumField.inputText = track.album
            yearField.inputText = track.year > 0 ? String(track.year) : ""
            numberField.inputText = track.trackNumber > 0 ? String(track.trackNumber) : ""
            genresField.inputText = track.genres
            root.explicitValue = track.explicit
            root.open()
        }
        function onTrackSaved(id) {
            if (root.opened && id === root.trackId)
                root.close()
        }
    }

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    dim: true
    focus: true
    padding: 0
    width: Math.min(560, (parent ? parent.width : 560) - 24)
    height: Math.min(layout.implicitHeight, (parent ? parent.height : 700) - 32)
    closePolicy: Popup.CloseOnEscape

    Overlay.modal: Rectangle { color: Theme.alpha("#000000", 0.6) }

    background: Rectangle {
        color: Theme.bar
        border.color: Theme.borderStrong
        border.width: 1
    }

    contentItem: ColumnLayout {
        id: layout
        spacing: 0

        SectionHeader {
            Layout.fillWidth: true
            title: qsTr("Изменить трек")
        }

        Flickable {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: form.implicitHeight + 32
            contentWidth: width
            contentHeight: form.implicitHeight + 32
            boundsBehavior: Flickable.StopAtBounds
            clip: true

            ColumnLayout {
                id: form
                x: 20
                y: 16
                width: parent.width - 40
                spacing: 12

                FlatField {
                    id: titleField
                    Layout.fillWidth: true
                    label: qsTr("Название")
                }
                FlatField {
                    id: artistsField
                    Layout.fillWidth: true
                    label: qsTr("Исполнитель (несколько через запятую)")
                }
                FlatField {
                    id: featuredField
                    Layout.fillWidth: true
                    label: qsTr("При участии (feat., через запятую)")
                }
                FlatField {
                    id: albumField
                    Layout.fillWidth: true
                    label: qsTr("Альбом (пусто — без альбома)")
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    FlatField {
                        id: yearField
                        Layout.fillWidth: true
                        label: qsTr("Год альбома")
                        validator: IntValidator { bottom: 0; top: 2200 }
                    }
                    FlatField {
                        id: numberField
                        Layout.fillWidth: true
                        label: qsTr("Номер трека")
                        validator: IntValidator { bottom: 0; top: 999 }
                    }
                }

                FlatField {
                    id: genresField
                    Layout.fillWidth: true
                    label: qsTr("Жанры (через запятую)")
                }

                // explicit lyrics
                Item {
                    Layout.fillWidth: true
                    implicitHeight: 28

                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10

                        Rectangle {
                            width: 18
                            height: 18
                            color: root.explicitValue ? Theme.accent : "transparent"
                            border.color: root.explicitValue ? Theme.accent : Theme.borderStrong
                            border.width: 1

                            Mono {
                                anchors.centerIn: parent
                                visible: root.explicitValue
                                text: "E"
                                color: "white"
                                font.pixelSize: 10
                                font.weight: Font.Bold
                            }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: qsTr("Откровенный текст (18+)")
                            color: Theme.muted
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontSmall
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.explicitValue = !root.explicitValue
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 20
            Layout.topMargin: 12
            spacing: 8

            Item { Layout.fillWidth: true }

            FlatButton {
                text: qsTr("Отмена")
                onClicked: root.close()
            }
            FlatButton {
                primary: true
                text: library.saving ? qsTr("Сохраняю…") : qsTr("Сохранить")
                enabledWhen: root.canSave
                onClicked: root.save()
            }
        }
    }
}
