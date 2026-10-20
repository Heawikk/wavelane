import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    A list of tracks for a phone: cover, title with its marks, artist, a heart.
    Tapping a row plays it and makes the list the queue.
*/
ListView {
    id: root

    property string context: "search"
    property bool playable: true
    property string emptyText: ""
    //! Shown above the rows, scrolling with them (search puts artists and albums here).
    property Component topContent: null
    property bool topHasContent: false
    //! Administrators get a pencil on each row, which asks for the track to be edited.
    property bool editable: false

    signal editRequested(string trackId)

    //! The list has been scrolled to its last row.
    signal endReached()

    //! Back to the first row (and the content above it), for a list that was just replaced.
    function toTop() {
        stickToTop = true
        contentY = topY()
        stickTimer.restart()
    }

    //! Where the list is scrolled to when its first thing, the content above the rows
    //! included, is at the top edge.
    function topY() {
        return (headerItem ? headerItem.y : originY) - topMargin
    }

    // The content above the rows changes height while it is laid out, and the list shifts to
    // keep the rows where they were; for a moment after toTop() it is put back each time.
    property bool stickToTop: false
    Timer {
        id: stickTimer
        interval: 700
        onTriggered: root.stickToTop = false
    }
    onContentYChanged: if (stickToTop && !dragging && !flicking && Math.abs(contentY - topY()) > 0.5) contentY = topY()
    onMovementStarted: stickToTop = false

    header: topContent
    onAtYEndChanged: if (atYEnd && count > 0) endReached()

    clip: true
    boundsBehavior: Flickable.StopAtBounds
    cacheBuffer: 600

    ScrollBar.vertical: FlatScrollBar {}

    delegate: Rectangle {
        id: row

        required property int index
        required property string trackId
        required property string title
        required property string artistName
        required property string coverPath
        required property string duration
        required property bool liked
        required property bool isExplicit
        required property string lyricsKind

        readonly property bool playingNow: player.hasTrack && player.currentTrack.id === trackId

        width: ListView.view.width
        height: 64
        color: tap.pressed ? Theme.rowSelected : "transparent"

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 1
            color: Theme.border
        }
        Rectangle {
            width: 3
            height: parent.height
            color: Theme.accent
            visible: row.playingNow
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 4
            spacing: 12

            CoverArt {
                Layout.preferredWidth: 44
                Layout.preferredHeight: 44
                coverPath: row.coverPath
                title: row.title
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: row.title
                        color: row.playingNow ? Theme.accentText : Theme.text
                        font.family: Theme.sans
                        font.pixelSize: 15
                        font.weight: row.playingNow ? Font.DemiBold : Font.Normal
                        elide: Text.ElideRight
                    }
                    LyricsBadge { kind: row.lyricsKind }
                    Item { Layout.fillWidth: true }
                }
                Text {
                    Layout.fillWidth: true
                    text: row.artistName
                    color: Theme.muted
                    font.family: Theme.sans
                    font.pixelSize: 13
                    elide: Text.ElideRight
                }
            }

            Mono {
                text: row.duration
                color: Theme.faint
            }

            IconButton {
                visible: root.editable && auth.isAdmin
                size: 44
                glyph: Theme.iEdit
                glyphSize: 18
                onClicked: root.editRequested(row.trackId)
            }

            IconButton {
                size: 44
                glyph: row.liked ? Theme.iHeartFill : Theme.iHeart
                glyphSize: 18
                active: row.liked
                activeColor: Theme.negative
                onClicked: library.toggleLike(row.trackId)
            }
        }

        TapHandler {
            id: tap
            onTapped: if (root.playable) library.playFrom(root.model, row.index, root.context)
        }
    }

    Mono {
        anchors.centerIn: parent
        width: parent.width - 48
        visible: root.count === 0 && !root.topHasContent
        text: root.emptyText
        color: Theme.faint
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        font.capitalization: Font.MixedCase
        font.letterSpacing: 0.2
        font.pixelSize: 13
    }
}
