import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! The persistent transport bar along the bottom of the window. */
Rectangle {
    id: root

    color: Theme.surface

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.spacing
        anchors.rightMargin: Theme.spacing
        spacing: Theme.spacing

        // --- current track ---
        RowLayout {
            Layout.preferredWidth: 280
            Layout.maximumWidth: 320
            spacing: 10

            CoverArt {
                Layout.preferredWidth: 52
                Layout.preferredHeight: 52
                visible: player.hasTrack
                coverPath: player.currentTrack.coverPath || ""
                title: player.currentTrack.title || ""
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: player.hasTrack ? player.currentTrack.title
                                          : qsTr("Ничего не играет")
                    color: Theme.text
                    font.pixelSize: Theme.fontSmall
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    visible: player.hasTrack
                    text: player.currentTrack.artistName || ""
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontTiny
                    elide: Text.ElideRight
                }
            }
        }

        // --- transport ---
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: 6

                IconButton {
                    symbol: "♥"
                    tooltip: qsTr("Нравится")
                    enabledWhen: player.hasTrack
                    active: player.currentTrack.liked || false
                    activeColor: Theme.positive
                    onClicked: library.toggleLike(player.currentTrack.id)
                }

                IconButton {
                    symbol: player.playing ? "⏸" : "▶"
                    size: 42
                    glyphSize: 16
                    filled: true
                    tooltip: player.playing ? qsTr("Пауза") : qsTr("Играть")
                    enabledWhen: player.hasTrack
                    onClicked: player.togglePlayPause()
                }

                IconButton {
                    symbol: "⏭"
                    tooltip: qsTr("Следующий")
                    enabledWhen: player.hasTrack
                    onClicked: wave.playNext()
                }

                IconButton {
                    symbol: "✕"
                    tooltip: qsTr("Не нравится")
                    enabledWhen: player.hasTrack
                    activeColor: Theme.negative
                    onClicked: wave.dislike()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    text: player.positionText
                    color: Theme.textFaint
                    font.pixelSize: Theme.fontTiny
                    Layout.preferredWidth: 36
                    horizontalAlignment: Text.AlignRight
                }

                Slider {
                    id: seekBar
                    Layout.fillWidth: true
                    from: 0
                    to: 1
                    enabled: player.hasTrack && player.duration > 0
                    // While dragging, follow the handle rather than the player,
                    // otherwise position updates fight the user's finger.
                    value: pressed ? value
                                   : (player.duration > 0
                                      ? player.position / player.duration : 0)

                    onPressedChanged: {
                        if (!pressed)
                            player.seekFraction(value)
                    }

                    background: Rectangle {
                        x: seekBar.leftPadding
                        y: seekBar.topPadding + seekBar.availableHeight / 2 - 2
                        width: seekBar.availableWidth
                        height: 4
                        radius: 2
                        color: Theme.surfaceActive

                        Rectangle {
                            width: seekBar.visualPosition * parent.width
                            height: parent.height
                            radius: 2
                            color: seekHover.containsMouse || seekBar.pressed
                                   ? Theme.accent : Theme.textMuted

                            Behavior on color {
                                ColorAnimation { duration: Theme.durationFast }
                            }
                        }
                    }

                    handle: Rectangle {
                        x: seekBar.leftPadding
                           + seekBar.visualPosition * (seekBar.availableWidth - width)
                        y: seekBar.topPadding + seekBar.availableHeight / 2 - height / 2
                        width: 12
                        height: 12
                        radius: 6
                        color: Theme.text
                        visible: seekHover.containsMouse || seekBar.pressed
                    }

                    HoverHandler { id: seekHover }
                }

                Text {
                    text: player.durationText
                    color: Theme.textFaint
                    font.pixelSize: Theme.fontTiny
                    Layout.preferredWidth: 36
                }
            }
        }

        // --- volume ---
        RowLayout {
            Layout.preferredWidth: 150
            spacing: 4

            BusyIndicator {
                running: player.buffering
                visible: running
                implicitWidth: 18
                implicitHeight: 18
            }

            Item { Layout.fillWidth: true }

            IconButton {
                symbol: player.muted || player.volume === 0 ? "ὐ7" : "ὐ9"
                size: 28
                glyphSize: Theme.fontSmall
                tooltip: player.muted ? qsTr("Включить звук") : qsTr("Выключить звук")
                onClicked: player.muted = !player.muted
            }

            Slider {
                id: volumeSlider
                Layout.preferredWidth: 88
                from: 0
                to: 100
                value: player.volume
                onMoved: {
                    player.volume = value
                    if (player.muted && value > 0)
                        player.muted = false
                }

                background: Rectangle {
                    x: volumeSlider.leftPadding
                    y: volumeSlider.topPadding + volumeSlider.availableHeight / 2 - 2
                    width: volumeSlider.availableWidth
                    height: 4
                    radius: 2
                    color: Theme.surfaceActive

                    Rectangle {
                        width: volumeSlider.visualPosition * parent.width
                        height: parent.height
                        radius: 2
                        color: player.muted ? Theme.textFaint : Theme.textMuted
                    }
                }

                handle: Rectangle {
                    x: volumeSlider.leftPadding
                       + volumeSlider.visualPosition * (volumeSlider.availableWidth - width)
                    y: volumeSlider.topPadding + volumeSlider.availableHeight / 2 - height / 2
                    width: 11
                    height: 11
                    radius: 6
                    color: Theme.text
                }
            }
        }
    }

    // Space toggles playback, as it does everywhere else.
    Shortcut {
        sequences: ["Space"]
        onActivated: player.togglePlayPause()
    }
    Shortcut {
        sequences: ["Media Play"]
        onActivated: player.togglePlayPause()
    }
    Shortcut {
        sequences: ["Media Next"]
        onActivated: wave.playNext()
    }
}
