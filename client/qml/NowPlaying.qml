import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The full-screen player: a big cover, the seek bar and the controls. It slides
    up over the pages from the mini player, and the words of the song slide over
    it in turn.
*/
Rectangle {
    id: root

    property bool lyricsOpen: false
    //! The sheet with the artists of the track is up.
    property bool artistsOpen: false

    signal closed()
    signal lyricsToggled()

    readonly property bool waveContext: player.context === "wave"

    color: Theme.bg

    function loadArtists() {
        library.loadPlayerArtists(player.currentTrack.artists || [])
    }

    onArtistsOpenChanged: if (artistsOpen) loadArtists()
    // put away with the player, so it is not still there the next time
    onVisibleChanged: if (!visible) artistsOpen = false

    Connections {
        target: player
        function onCurrentTrackChanged() { if (root.artistsOpen) root.loadArtists() }
    }

    function next() {
        if (waveContext)
            wave.playNext()
        else
            library.playNext()
    }

    function dislike() {
        if (!player.hasTrack)
            return
        if (waveContext) {
            wave.dislike()
        } else {
            library.toggleDislike(player.currentTrack.id)
            library.playNext()
        }
    }

    // swallow touches so nothing underneath reacts
    MouseArea { anchors.fill: parent }

    // --- swipes on the cover area ---
    //! How far the player has been pulled down; the window adds it to its own position.
    property real pull: 0
    //! True while a finger is moving the player or the cover, so the window follows without easing.
    property bool dragging: false
    //! Sideways travel of the cover while it is swiped.
    property real shift: 0

    Behavior on pull {
        enabled: !root.dragging
        NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
    }
    Behavior on shift {
        enabled: !root.dragging
        NumberAnimation { duration: 160; easing.type: Easing.OutCubic }
    }

    // Down closes the player, left skips to the next track, right likes the current one.
    // Only the part above the seek bar listens, so the seek bar keeps its own dragging.
    Item {
        id: swipeZone

        width: parent.width
        height: parent.height * 0.58

        DragHandler {
            id: swipe

            property string axis: ""
            property real travelX: 0
            property real travelY: 0

            target: null
            enabled: !root.lyricsOpen && !root.artistsOpen

            onActiveChanged: {
                if (active) {
                    axis = ""
                    travelX = 0
                    travelY = 0
                    root.dragging = true
                    return
                }
                root.dragging = false
                const dx = travelX
                const dy = travelY
                const how = axis
                axis = ""
                root.pull = 0
                root.shift = 0
                if (how === "v" && dy > 110) {
                    root.closed()
                } else if (how === "v" && dy < -90 && player.hasTrack) {
                    // pulled up: the artists
                    root.artistsOpen = true
                } else if (how === "h" && player.hasTrack) {
                    if (dx < -90)
                        root.next()
                    else if (dx > 90 && !player.currentTrack.liked)
                        library.toggleLike(player.currentTrack.id)
                }
            }
            onActiveTranslationChanged: {
                if (!active)
                    return
                travelX = activeTranslation.x
                travelY = activeTranslation.y
                if (axis === "" && Math.max(Math.abs(travelX), Math.abs(travelY)) > 14)
                    axis = Math.abs(travelY) > Math.abs(travelX) ? "v" : "h"
                if (axis === "v")
                    root.pull = Math.max(0, travelY)
                else if (axis === "h")
                    root.shift = travelX
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 20
        anchors.rightMargin: 20
        spacing: 0

        // --- top row ---
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            Layout.leftMargin: -12
            Layout.rightMargin: -12

            IconButton {
                size: 48
                glyph: Theme.iChevronDown
                glyphSize: 22
                onClicked: root.closed()
            }
            Item { Layout.fillWidth: true }
            Mono {
                text: root.waveContext ? qsTr("Моя волна") : qsTr("Сейчас играет")
                color: Theme.faint
            }
            Item { Layout.fillWidth: true }
            FlatButton {
                Layout.preferredHeight: 34
                Layout.rightMargin: 12
                horizontalPadding: 12
                text: qsTr("Текст")
                primary: root.lyricsOpen
                enabledWhen: player.hasTrack
                onClicked: root.lyricsToggled()
            }
        }

        Item { Layout.fillHeight: true; Layout.preferredHeight: 8 }

        // --- cover ---
        CoverArt {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: Math.min(root.width - 40, root.height * 0.40)
            Layout.preferredHeight: Layout.preferredWidth
            transform: Translate { x: root.shift * 0.6 }
            opacity: 1 - Math.min(0.5, Math.abs(root.shift) / 400)
            coverPath: player.currentTrack.coverPath || ""
            title: player.currentTrack.title || ""
        }

        Item { Layout.fillHeight: true; Layout.preferredHeight: 8 }

        // --- title ---
        Text {
            Layout.fillWidth: true
            text: player.hasTrack ? player.currentTrack.title : qsTr("Ничего не играет")
            color: Theme.text
            font.family: Theme.sans
            font.pixelSize: 22
            font.weight: Font.Bold
            elide: Text.ElideRight
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            spacing: 8

            ArtistLinks {
                Layout.fillWidth: true
                artists: player.currentTrack.artists || []
                fallback: player.currentTrack.artistName || ""
                color: Theme.muted
                font.pixelSize: 15
            }
            LyricsBadge { kind: player.currentTrack.lyricsKind || "none" }
        }
        Mono {
            Layout.fillWidth: true
            Layout.topMargin: 6
            visible: root.waveContext && wave.currentReason !== ""
            text: wave.currentReason
            color: Theme.faint
            font.capitalization: Font.MixedCase
            font.letterSpacing: 0.2
            font.pixelSize: 12
        }

        Item { Layout.preferredHeight: 18 }

        // --- seek ---
        Slider {
            id: seek
            Layout.fillWidth: true
            implicitHeight: 28
            from: 0
            to: 1
            enabled: player.hasTrack && player.duration > 0
            value: pressed ? value : (player.duration > 0 ? player.position / player.duration : 0)
            onPressedChanged: if (!pressed) player.seekFraction(value)

            background: Rectangle {
                x: seek.leftPadding
                y: seek.topPadding + seek.availableHeight / 2 - 1
                width: seek.availableWidth
                height: 3
                color: Theme.borderStrong

                Rectangle {
                    width: seek.visualPosition * parent.width
                    height: parent.height
                    color: Theme.accent
                }
            }
            handle: Rectangle {
                x: seek.leftPadding + seek.visualPosition * (seek.availableWidth - width)
                y: seek.topPadding + seek.availableHeight / 2 - height / 2
                width: 10
                height: 18
                color: Theme.light
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Mono { text: player.positionText; color: Theme.muted }
            Item { Layout.fillWidth: true }
            Mono { text: player.durationText; color: Theme.faint }
        }

        Item { Layout.fillHeight: true; Layout.preferredHeight: 12 }

        // --- controls ---
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 14

            IconButton {
                size: 52
                glyph: Theme.iDislike
                glyphSize: 20
                enabledWhen: player.hasTrack
                onClicked: root.dislike()
            }
            RoundButton {
                glyph: Theme.iPrev
                size: 52
                enabledWhen: false
            }
            RoundButton {
                glyph: player.playing ? Theme.iPause : Theme.iPlay
                size: 76
                filled: true
                enabledWhen: player.hasTrack
                onClicked: player.togglePlayPause()
            }
            RoundButton {
                glyph: Theme.iNext
                size: 52
                enabledWhen: player.hasTrack
                onClicked: root.next()
            }
            IconButton {
                size: 52
                glyph: player.currentTrack.liked ? Theme.iHeartFill : Theme.iHeart
                glyphSize: 20
                active: player.currentTrack.liked || false
                activeColor: Theme.negative
                enabledWhen: player.hasTrack
                onClicked: library.toggleLike(player.currentTrack.id)
            }
        }

        // the way up to the artists: tapped, or pulled up like the sheet itself
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            opacity: player.hasTrack ? 1 : 0.35

            TapHandler {
                enabled: player.hasTrack
                onTapped: root.artistsOpen = true
            }
            DragHandler {
                enabled: player.hasTrack && !root.artistsOpen
                target: null
                xAxis.enabled: false
                onActiveChanged: if (!active && activeTranslation.y < -40) root.artistsOpen = true
            }

            Row {
                anchors.centerIn: parent
                spacing: 8

                Icon {
                    anchors.verticalCenter: parent.verticalCenter
                    glyph: Theme.iChevronUp
                    font.pixelSize: 18
                    color: Theme.muted
                }
                Mono {
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("Об исполнителях")
                    color: Theme.muted
                }
            }
        }
    }

    // --- the words, over everything ---
    LyricsView {
        anchors.fill: parent
        visible: root.lyricsOpen
        onEditRequested: lyricsEditor.openForCurrent()
        onCloseRequested: root.lyricsToggled()
    }

    ArtistsSheet {
        width: parent.width
        height: parent.height
        opened: root.artistsOpen
        onCloseRequested: root.artistsOpen = false
    }

    LyricsEditor { id: lyricsEditor }
}
