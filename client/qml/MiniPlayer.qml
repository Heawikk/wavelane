import QtQuick
import QtQuick.Layouts
import Wavelane

/*! What is playing, as a strip above the navigation; tapping it opens the full player. */
Rectangle {
    id: root

    signal opened()

    implicitHeight: 60
    color: Theme.bar

    Rectangle {
        width: parent.width
        height: 1
        color: Theme.border
    }
    // how far into the track
    Rectangle {
        width: player.duration > 0 ? parent.width * Math.min(1, player.position / player.duration) : 0
        height: 2
        color: Theme.accent
    }

    TapHandler { onTapped: root.opened() }

    // Up opens the full player; a swipe sideways skips to the next track.
    DragHandler {
        id: swipe

        property real travelX: 0
        property real travelY: 0

        target: null

        onActiveChanged: {
            if (active) {
                travelX = 0
                travelY = 0
                return
            }
            if (Math.abs(travelX) > Math.abs(travelY) && travelX < -80) {
                if (player.context === "wave")
                    wave.playNext()
                else
                    library.playNext()
            } else if (Math.abs(travelY) > Math.abs(travelX) && travelY < -40) {
                root.opened()
            }
        }
        onActiveTranslationChanged: {
            if (active) {
                travelX = activeTranslation.x
                travelY = activeTranslation.y
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 4
        spacing: 12

        CoverArt {
            Layout.preferredWidth: 40
            Layout.preferredHeight: 40
            coverPath: player.currentTrack.coverPath || ""
            title: player.currentTrack.title || ""
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                Layout.fillWidth: true
                text: player.currentTrack.title || ""
                color: Theme.text
                font.family: Theme.sans
                font.pixelSize: 14
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                text: player.currentTrack.artistName || ""
                color: Theme.muted
                font.family: Theme.sans
                font.pixelSize: 12
                elide: Text.ElideRight
            }
        }

        IconButton {
            size: 48
            glyph: player.currentTrack.liked ? Theme.iHeartFill : Theme.iHeart
            glyphSize: 18
            active: player.currentTrack.liked || false
            activeColor: Theme.negative
            onClicked: library.toggleLike(player.currentTrack.id)
        }
        IconButton {
            size: 48
            glyph: player.playing ? Theme.iPause : Theme.iPlay
            glyphSize: 22
            onClicked: player.togglePlayPause()
        }
    }
}
