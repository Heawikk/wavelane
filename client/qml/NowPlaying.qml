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

    signal closed()
    signal lyricsToggled()

    readonly property bool waveContext: player.context === "wave"

    color: Theme.bg

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

            Text {
                Layout.fillWidth: true
                text: player.currentTrack.artistName || ""
                color: Theme.muted
                font.family: Theme.sans
                font.pixelSize: 15
                elide: Text.ElideRight
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

        Item { Layout.preferredHeight: 28 }
    }

    // --- the words, over everything ---
    LyricsView {
        anchors.fill: parent
        visible: root.lyricsOpen
        onEditRequested: lyricsEditor.openForCurrent()
        onCloseRequested: root.lyricsToggled()
    }

    LyricsEditor { id: lyricsEditor }
}
