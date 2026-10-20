import QtQuick
import Wavelane

/*!
    What sits above the tracks in the search results: the artists found, then the
    albums, then the heading of the tracks themselves. Nothing at all when the
    search found no artist and no album.
*/
Column {
    id: root

    property bool scrollable: false
    property int cardSize: 148
    property int margin: 16

    //! A shelf was folded or unfolded.
    signal shelfToggled()

    readonly property bool hasContent: library.searchArtists.length > 0
                                       || library.searchAlbums.length > 0

    ResultShelf {
        width: root.width
        heading: qsTr("Исполнители")
        kind: "artist"
        items: library.searchArtists
        cardSize: root.cardSize
        margin: root.margin
        scrollable: root.scrollable
        onPicked: function(id, title) { library.openArtist(id, title) }
        onToggled: root.shelfToggled()
    }

    ResultShelf {
        width: root.width
        heading: qsTr("Альбомы")
        kind: "album"
        items: library.searchAlbums
        cardSize: root.cardSize
        margin: root.margin
        scrollable: root.scrollable
        onPicked: function(id, title) { library.openAlbum(id, title) }
        onToggled: root.shelfToggled()
    }

    Item {
        width: root.width
        height: root.hasContent && library.searchResults.count > 0 ? 52 : 0
        visible: height > 0

        Text {
            x: root.margin
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 8
            text: qsTr("Треки")
            color: Theme.text
            font.family: Theme.sans
            font.pixelSize: Theme.mobileIcons ? 18 : 20
            font.weight: Font.Bold
        }
    }
}
