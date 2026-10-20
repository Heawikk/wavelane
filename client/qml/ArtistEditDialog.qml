import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import Wavelane

/*!
    An artist, for an administrator to edit: the picture, the name, the country and the
    description. The picture is sent as soon as it is chosen; the rest on "Сохранить".

    Open it with openFor(artist), the artist being { id, name, imagePath, country, bio }.
*/
Popup {
    id: root

    property string artistId: ""
    property string imagePath: ""
    //! Set while "Сохранить" is on its way, so the dialog closes when it is done.
    property bool closeWhenSaved: false

    readonly property bool canSave: nameField.inputText.trim() !== "" && !library.saving

    function openFor(artist) {
        artistId = artist.id
        imagePath = artist.imagePath || ""
        nameField.inputText = artist.name || ""
        countryField.inputText = artist.country || ""
        bioField.text = artist.bio || ""
        closeWhenSaved = false
        open()
    }

    function save() {
        closeWhenSaved = true
        library.saveArtist(root.artistId, {
            name: nameField.inputText,
            country: countryField.inputText,
            bio: bioField.text
        })
    }

    Connections {
        target: library

        function onArtistSaved(id) {
            if (id !== root.artistId)
                return
            if (root.closeWhenSaved) {
                root.close()
                return
            }
            // the picture changed: take the new one from the list
            const row = library.adminArtists.indexOfId(id)
            if (row >= 0)
                root.imagePath = library.adminArtists.get(row).imagePath
        }
    }

    FileDialog {
        id: pictureDialog
        title: qsTr("Выберите картинку")
        nameFilters: [qsTr("Картинки (*.png *.jpg *.jpeg *.webp *.bmp)"), qsTr("Все файлы (*)")]
        onAccepted: {
            root.closeWhenSaved = false
            library.setArtistImage(root.artistId, selectedFile)
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
            title: qsTr("Исполнитель")
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
                spacing: 14

                // the picture
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 18

                    ArtistAvatar {
                        Layout.preferredWidth: 96
                        Layout.preferredHeight: 96
                        imagePath: root.imagePath
                        name: nameField.inputText
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        FlatButton {
                            glyph: Theme.iAdd
                            text: root.imagePath !== "" ? qsTr("Другая картинка…") : qsTr("Выбрать картинку…")
                            enabledWhen: !library.saving
                            onClicked: pictureDialog.open()
                        }
                        FlatButton {
                            visible: root.imagePath !== ""
                            text: qsTr("Убрать картинку")
                            danger: true
                            enabledWhen: !library.saving
                            onClicked: {
                                root.closeWhenSaved = false
                                library.removeArtistImage(root.artistId)
                            }
                        }
                    }
                }

                FlatField {
                    id: nameField
                    Layout.fillWidth: true
                    label: qsTr("Имя")
                }
                FlatField {
                    id: countryField
                    Layout.fillWidth: true
                    label: qsTr("Страна (две буквы, например RU)")
                    maxLength: 2
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5

                    Mono {
                        text: qsTr("Описание")
                        font.pixelSize: 10
                        color: Theme.faint
                    }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 110

                        TextArea {
                            id: bioField
                            color: Theme.text
                            selectByMouse: true
                            wrapMode: TextEdit.Wrap
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontSmall
                            padding: 10

                            background: Rectangle {
                                color: Theme.panel
                                border.color: bioField.activeFocus ? Theme.accent : Theme.borderStrong
                                border.width: 1
                            }
                        }
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
                text: qsTr("Закрыть")
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
