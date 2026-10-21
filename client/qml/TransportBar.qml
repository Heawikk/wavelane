import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! The strip along the bottom: transport, seek bar, like/dislike and volume. */
Rectangle {
    id: root

    color: Theme.bar

    readonly property bool waveContext: player.context === "wave"

    //! The lyrics view is open; the button lights up while it is.
    property bool lyricsOpen: false

    signal toggleLyrics()
    //! A dislike was given to the wave's track; the library path reports its own.
    signal waveDisliked()

    //! Where the reaction sparks start from.
    readonly property Item likeButton: likeBtn
    readonly property Item dislikeButton: dislikeBtn

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
            root.waveDisliked()
            wave.dislike()
        } else {
            library.toggleDislike(player.currentTrack.id)
            library.playNext()
        }
    }

    Rectangle {
        width: parent.width
        height: 1
        color: Theme.border
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        spacing: 10

        // --- current track ---
        RowLayout {
            Layout.preferredWidth: 270
            Layout.maximumWidth: 270
            spacing: 10

            CoverArt {
                Layout.preferredWidth: 38
                Layout.preferredHeight: 38
                visible: player.hasTrack
                coverPath: player.currentTrack.coverPath || ""
                title: player.currentTrack.title || ""
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    Layout.fillWidth: true
                    text: player.hasTrack ? player.currentTrack.title : qsTr("Ничего не играет")
                    color: player.hasTrack ? Theme.text : Theme.faint
                    font.family: Theme.sans
                    font.pixelSize: Theme.fontBody
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                ArtistLinks {
                    Layout.fillWidth: true
                    visible: player.hasTrack
                    artists: player.currentTrack.artists || []
                    fallback: player.currentTrack.artistName || ""
                    color: Theme.muted
                    font.pixelSize: Theme.fontSmall
                }
            }
        }

        // --- transport ---
        IconButton {
            size: 32
            glyph: player.playing ? Theme.iPause : Theme.iPlay
            glyphSize: 14
            filled: true
            enabledWhen: player.hasTrack
            tooltip: (player.playing ? qsTr("Пауза") : qsTr("Играть")) + " · Space"
            onClicked: player.togglePlayPause()
        }
        IconButton {
            size: 32
            glyph: Theme.iNext
            enabledWhen: player.hasTrack
            tooltip: qsTr("Следующий · N")
            onClicked: root.next()
        }

        // --- seek ---
        Mono {
            Layout.preferredWidth: 38
            horizontalAlignment: Text.AlignRight
            text: player.positionText
            color: Theme.muted
        }

        Slider {
            id: seek
            Layout.fillWidth: true
            implicitHeight: 20
            from: 0
            to: 1
            enabled: player.hasTrack && player.duration > 0
            // While dragging, follow the handle rather than the player, or the
            // position updates fight the cursor.
            value: pressed ? value : (player.duration > 0 ? player.position / player.duration : 0)
            onPressedChanged: if (!pressed) player.seekFraction(value)

            HoverHandler { id: seekHover }

            background: Rectangle {
                x: seek.leftPadding
                y: seek.topPadding + seek.availableHeight / 2 - 1
                width: seek.availableWidth
                height: 2
                color: Theme.borderStrong

                Rectangle {
                    width: seek.visualPosition * parent.width
                    height: parent.height
                    color: seekHover.hovered || seek.pressed ? Theme.accentText : Theme.accent
                }
            }
            handle: Rectangle {
                x: seek.leftPadding + seek.visualPosition * (seek.availableWidth - width)
                y: seek.topPadding + seek.availableHeight / 2 - height / 2
                width: 6
                height: 12
                color: Theme.light
                visible: seek.enabled && (seekHover.hovered || seek.pressed)
            }
        }

        Mono {
            Layout.preferredWidth: 38
            text: player.durationText
            color: Theme.faint
        }

        // --- reactions ---
        IconButton {
            id: likeBtn
            glyph: player.hasTrack && player.currentTrack.liked ? Theme.iHeartFill : Theme.iHeart
            enabledWhen: player.hasTrack
            active: player.hasTrack && player.currentTrack.liked
            activeColor: Theme.negative
            tooltip: qsTr("Нравится · L")
            onClicked: library.toggleLike(player.currentTrack.id)
        }
        IconButton {
            id: dislikeBtn
            glyph: Theme.iDislike
            enabledWhen: player.hasTrack
            tooltip: qsTr("Не нравится · D")
            onClicked: root.dislike()
        }

        FlatButton {
            Layout.alignment: Qt.AlignVCenter
            Layout.preferredHeight: 26
            horizontalPadding: 10
            text: qsTr("Текст")
            primary: root.lyricsOpen
            enabledWhen: player.hasTrack
            onClicked: root.toggleLyrics()
        }

        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 22
            color: Theme.border
        }

        // --- volume ---
        BusyIndicator {
            running: player.buffering
            visible: running
            implicitWidth: 18
            implicitHeight: 18
        }

        IconButton {
            glyph: player.muted || player.volume === 0 ? Theme.iMute : Theme.iVolume
            tooltip: player.muted ? qsTr("Включить звук") : qsTr("Выключить звук")
            onClicked: player.muted = !player.muted
        }

        Slider {
            id: volume
            Layout.preferredWidth: 90
            implicitHeight: 20
            from: 0
            to: 100
            value: player.volume
            onMoved: {
                player.volume = value
                if (player.muted && value > 0)
                    player.muted = false
            }

            background: Rectangle {
                x: volume.leftPadding
                y: volume.topPadding + volume.availableHeight / 2 - 1
                width: volume.availableWidth
                height: 2
                color: Theme.borderStrong

                Rectangle {
                    width: volume.visualPosition * parent.width
                    height: parent.height
                    color: player.muted ? Theme.faint : Theme.muted
                }
            }
            handle: Rectangle {
                x: volume.leftPadding + volume.visualPosition * (volume.availableWidth - width)
                y: volume.topPadding + volume.availableHeight / 2 - height / 2
                width: 6
                height: 12
                color: Theme.light
            }
        }
    }
}
