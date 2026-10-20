import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! Every artist of the library, with a search; a click opens one to edit (picture, name, ...). */
Item {
    id: root

    //! A phone: bigger rows.
    property bool compact: false

    function refresh() { library.loadAdminArtists(box.text) }

    ArtistEditDialog { id: editor }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            spacing: 0

            SearchBox {
                id: box
                Layout.fillWidth: true
                placeholder: qsTr("Найти исполнителя")
                onSearched: function(text) { library.loadAdminArtists(text) }
            }
            Mono {
                Layout.rightMargin: 16
                text: library.adminArtists.count + " / " + library.adminArtistsTotal
                color: Theme.faint
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.border
        }

        ListView {
            id: list

            Layout.fillWidth: true
            Layout.fillHeight: true
            model: library.adminArtists
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            cacheBuffer: 600

            ScrollBar.vertical: FlatScrollBar {}

            onAtYEndChanged: if (atYEnd && count > 0) library.loadMoreAdminArtists()

            delegate: Rectangle {
                id: row

                required property int index
                required property string artistId
                required property string name
                required property string imagePath
                required property string country
                required property string bio
                required property int trackCount

                width: ListView.view.width
                height: root.compact ? 64 : 52
                color: hover.hovered ? Theme.rowHover : "transparent"

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Theme.border
                }

                HoverHandler { id: hover }
                TapHandler {
                    onTapped: editor.openFor({
                        id: row.artistId, name: row.name, imagePath: row.imagePath,
                        country: row.country, bio: row.bio
                    })
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    spacing: 14

                    ArtistAvatar {
                        Layout.preferredWidth: root.compact ? 44 : 36
                        Layout.preferredHeight: root.compact ? 44 : 36
                        imagePath: row.imagePath
                        name: row.name
                    }
                    Text {
                        Layout.fillWidth: true
                        text: row.name
                        color: Theme.text
                        font.family: Theme.sans
                        font.pixelSize: root.compact ? 15 : Theme.fontBody
                        elide: Text.ElideRight
                    }
                    Mono {
                        visible: row.country !== ""
                        text: row.country
                        color: Theme.faint
                    }
                    Mono {
                        text: qsTr("%1 тр.").arg(row.trackCount)
                        color: Theme.muted
                    }
                    Icon {
                        visible: hover.hovered || root.compact
                        glyph: Theme.iEdit
                        font.pixelSize: 14
                        color: Theme.muted
                    }
                }
            }
        }
    }

    Mono {
        anchors.centerIn: parent
        visible: library.adminArtists.count === 0
        text: box.text === "" ? qsTr("Исполнителей пока нет") : qsTr("Ничего не найдено")
        color: Theme.faint
    }
}
