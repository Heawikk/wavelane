import QtQuick
import QtQuick.Layouts
import Wavelane

/*!
    One row of the track table.

    Takes plain properties rather than model roles, so the same row serves a
    list delegate and the "now playing" row above the queue. Column widths come
    from the table, which keeps the rows and the header lined up.
*/
Rectangle {
    id: root

    property int rowNumber: 0
    property string trackId: ""
    property string title: ""
    property string artistName: ""
    //! The credits (id, name, role), so each name can be a link; the plain text shows without them.
    property var artists: []
    property string albumTitle: ""
    property string coverPath: ""
    property string duration: ""
    property string quality: ""
    property string reason: ""
    property var genres: []
    property bool liked: false
    property bool isExplicit: false
    //! "none", "plain" or "synced".
    property string lyricsKind: "none"

    property bool selected: false
    property bool playingNow: false
    property bool showReason: false
    //! Rows of a list that cannot be replayed (the history) have no play button.
    property bool playable: true

    property int gap: 12
    property int colIndex: 40
    property int colArtist: 160
    property int colAlbum: 0
    property int colGenre: 0
    property int colQuality: 84
    property int colTime: 52

    signal clicked()
    signal activated()
    signal likeToggled()
    //! The play / pause button at the left of the row.
    signal playToggled()

    readonly property string genreText: genres && genres.length > 0
                                        ? genres.slice(0, 2).join(", ") : ""

    implicitHeight: Theme.rowHeight
    color: selected ? Theme.rowSelected : (hover.hovered ? Theme.rowHover : "transparent")

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.border
    }

    // the "this is playing" marker
    Rectangle {
        width: 2
        height: parent.height
        color: Theme.accent
        visible: root.playingNow
    }

    HoverHandler { id: hover }
    TapHandler {
        onTapped: root.clicked()
        onDoubleTapped: root.activated()
    }

    RowLayout {
        anchors.fill: parent
        spacing: root.gap

        // The number, which turns into a play button under the pointer; the track that is
        // playing keeps a button of its own (pause while it plays, play while it is paused).
        Item {
            id: lead

            readonly property bool showButton: root.playingNow || (root.playable && hover.hovered)

            Layout.preferredWidth: root.colIndex
            Layout.fillHeight: true

            Mono {
                anchors.centerIn: parent
                visible: !lead.showButton
                text: root.rowNumber > 0 ? root.rowNumber : ""
                color: Theme.faint
            }

            IconButton {
                anchors.centerIn: parent
                visible: lead.showButton
                size: 26
                glyphSize: 14
                glyph: root.playingNow && player.playing ? Theme.iPause : Theme.iPlay
                active: root.playingNow
                activeColor: Theme.accentText
                tooltip: root.playingNow && player.playing ? qsTr("Пауза") : qsTr("Воспроизвести")
                onClicked: root.playToggled()
            }
        }

        CoverArt {
            Layout.preferredWidth: 22
            Layout.preferredHeight: 22
            coverPath: root.coverPath
            title: root.title
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                // The title keeps its natural width, so the marks sit right after it;
                // it only shrinks (and elides) when the column is too narrow. What is
                // left over goes to the reason, or to the spacer below. Sizing it
                // from parent.width instead makes the layout recurse.
                Layout.fillWidth: false
                text: root.title
                color: root.playingNow ? Theme.accentText : Theme.text
                font.family: Theme.sans
                font.pixelSize: Theme.fontBody
                font.weight: root.playingNow ? Font.DemiBold : Font.Normal
                elide: Text.ElideRight
            }

            LyricsBadge {
                kind: root.lyricsKind
            }

            Rectangle {
                visible: root.isExplicit
                Layout.preferredWidth: 14
                Layout.preferredHeight: 14
                color: "transparent"
                border.color: Theme.borderStrong
                border.width: 1

                Mono {
                    anchors.centerIn: parent
                    text: "E"
                    font.pixelSize: 9
                    font.weight: Font.Bold
                }
            }

            Item {
                Layout.fillWidth: true
                visible: !(root.showReason && root.reason !== "")
            }

            Mono {
                Layout.fillWidth: true
                visible: root.showReason && root.reason !== ""
                text: root.reason
                color: Theme.faint
                font.capitalization: Font.MixedCase
                font.letterSpacing: 0.2
            }

        }

        ArtistLinks {
            Layout.preferredWidth: root.colArtist
            artists: root.artists
            fallback: root.artistName
            color: Theme.muted
            font.pixelSize: Theme.fontSmall
        }

        Text {
            visible: root.colAlbum > 0
            Layout.preferredWidth: root.colAlbum
            text: root.albumTitle
            color: Theme.faint
            font.family: Theme.sans
            font.pixelSize: Theme.fontSmall
            elide: Text.ElideRight
        }

        Mono {
            visible: root.colGenre > 0
            Layout.preferredWidth: root.colGenre
            text: root.genreText
            color: Theme.faint
        }

        Mono {
            Layout.preferredWidth: root.colQuality
            text: root.quality
            color: Theme.faint
        }

        Mono {
            Layout.preferredWidth: root.colTime
            text: root.duration
            horizontalAlignment: Text.AlignRight
            color: Theme.muted
        }

        Item {
            Layout.preferredWidth: 32
            Layout.fillHeight: true

            IconButton {
                anchors.centerIn: parent
                size: 24
                glyphSize: 13
                glyph: root.liked ? Theme.iHeartFill : Theme.iHeart
                visible: hover.hovered || root.liked || root.selected
                active: root.liked
                activeColor: Theme.negative
                tooltip: root.liked ? qsTr("Убрать из избранного") : qsTr("Нравится")
                onClicked: root.likeToggled()
            }
        }

        Item { Layout.preferredWidth: 4 }
    }
}
