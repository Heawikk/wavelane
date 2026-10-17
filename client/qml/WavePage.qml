import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! "Моя волна": the endless personalised stream. */
Item {
    id: root

    property bool settingsOpen: false

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: root.width
            spacing: Theme.spacingLarge

            // --- header -------------------------------------------------
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: Theme.spacingLarge
                Layout.bottomMargin: 0
                spacing: Theme.spacing

                ColumnLayout {
                    spacing: 2
                    Text {
                        text: qsTr("Моя волна")
                        color: Theme.text
                        font.pixelSize: Theme.fontHeading
                        font.weight: Font.Bold
                    }
                    Text {
                        text: wave.started ? qsTr("Поток подстраивается под вас")
                                           : qsTr("Бесконечный поток под ваш вкус")
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                    }
                }

                Item { Layout.fillWidth: true }

                BusyIndicator {
                    running: wave.loading
                    visible: running
                    implicitWidth: 26
                    implicitHeight: 26
                }

                IconButton {
                    symbol: "⚙"
                    glyphSize: Theme.fontTitle
                    tooltip: qsTr("Настройки волны")
                    active: root.settingsOpen
                    onClicked: root.settingsOpen = !root.settingsOpen
                }

                IconButton {
                    symbol: "↻"
                    glyphSize: Theme.fontTitle
                    tooltip: qsTr("Начать волну заново")
                    onClicked: wave.reset()
                }
            }

            WaveSettingsPanel {
                Layout.fillWidth: true
                Layout.leftMargin: Theme.spacingLarge
                Layout.rightMargin: Theme.spacingLarge
                visible: root.settingsOpen
            }

            // --- now playing ---------------------------------------------
            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: Theme.spacingLarge
                Layout.rightMargin: Theme.spacingLarge
                Layout.preferredHeight: 300
                radius: Theme.radiusLarge
                color: Theme.surface
                border.color: Theme.border
                border.width: 1

                // Idle state: one big invitation to start.
                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: Theme.spacing
                    visible: !player.hasTrack

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: wave.statusMessage !== "" ? wave.statusMessage
                                                        : qsTr("Включите волну, и она подберёт музыку")
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontBody
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        Layout.maximumWidth: 420
                    }

                    Button {
                        id: startButton
                        Layout.alignment: Qt.AlignHCenter
                        enabled: !wave.loading
                        text: qsTr("Слушать волну")

                        contentItem: Text {
                            text: startButton.text
                            color: "white"
                            font.pixelSize: Theme.fontBody
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle {
                            implicitWidth: 190
                            implicitHeight: 46
                            radius: 23
                            opacity: startButton.enabled ? 1 : 0.5
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: Theme.accent }
                                GradientStop { position: 1.0; color: Theme.accentAlt }
                            }
                        }
                        onClicked: wave.start()
                    }
                }

                // Playing state.
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingLarge
                    spacing: Theme.spacingLarge
                    visible: player.hasTrack

                    CoverArt {
                        Layout.preferredWidth: 236
                        Layout.preferredHeight: 236
                        Layout.alignment: Qt.AlignVCenter
                        radius: Theme.radius
                        coverPath: player.currentTrack.coverPath || ""
                        title: player.currentTrack.title || ""
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 8

                        Item { Layout.fillHeight: true }

                        Row {
                            spacing: 8
                            visible: wave.currentReason !== ""

                            Rectangle {
                                height: 22
                                width: reasonText.implicitWidth + 20
                                radius: 11
                                color: Theme.accentSoft
                                Text {
                                    id: reasonText
                                    anchors.centerIn: parent
                                    text: wave.currentReason
                                    color: Theme.accent
                                    font.pixelSize: Theme.fontTiny
                                    font.weight: Font.DemiBold
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: player.currentTrack.title || ""
                            color: Theme.text
                            font.pixelSize: Theme.fontDisplay
                            font.weight: Font.Bold
                            elide: Text.ElideRight
                            maximumLineCount: 2
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            Layout.fillWidth: true
                            text: player.currentTrack.artistName || ""
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontTitle
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: text !== ""
                            text: {
                                const parts = []
                                if (player.currentTrack.albumTitle)
                                    parts.push(player.currentTrack.albumTitle)
                                if (player.currentTrack.quality)
                                    parts.push(player.currentTrack.quality)
                                const genres = player.currentTrack.genres || []
                                if (genres.length > 0)
                                    parts.push(genres.slice(0, 2).join(", "))
                                return parts.join("  ·  ")
                            }
                            color: Theme.textFaint
                            font.pixelSize: Theme.fontSmall
                            elide: Text.ElideRight
                        }

                        Item { Layout.fillHeight: true }

                        // --- wave controls ---
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.spacing

                            IconButton {
                                symbol: "♥"
                                size: 44
                                glyphSize: 20
                                tooltip: qsTr("Нравится")
                                active: player.currentTrack.liked || false
                                activeColor: Theme.positive
                                onClicked: wave.like()
                            }

                            IconButton {
                                symbol: "✕"
                                size: 44
                                glyphSize: 18
                                tooltip: qsTr("Не нравится — больше не покажем")
                                activeColor: Theme.negative
                                onClicked: wave.dislike()
                            }

                            IconButton {
                                symbol: "⏭"
                                size: 44
                                glyphSize: 18
                                tooltip: qsTr("Следующий трек")
                                onClicked: wave.playNext()
                            }

                            Item { Layout.fillWidth: true }

                            IconButton {
                                symbol: "⊘"
                                tooltip: qsTr("Не показывать этого исполнителя")
                                onClicked: wave.banCurrentArtist()
                            }
                        }
                    }
                }
            }

            // --- queue ---------------------------------------------------
            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: Theme.spacingLarge
                Layout.rightMargin: Theme.spacingLarge
                Layout.bottomMargin: Theme.spacingLarge
                spacing: 6
                visible: wave.queue.count > 0

                Text {
                    text: qsTr("Далее в волне")
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                    font.weight: Font.DemiBold
                }

                Repeater {
                    model: wave.queue
                    delegate: TrackRow {
                        Layout.fillWidth: true
                        showReason: true
                        // The queue is the wave's own plan; picking out of order
                        // would desynchronise it, so rows here are informational.
                        interactive: false
                    }
                }
            }

            // --- history -------------------------------------------------
            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: Theme.spacingLarge
                Layout.rightMargin: Theme.spacingLarge
                Layout.bottomMargin: Theme.spacingLarge
                spacing: 6
                visible: wave.history.count > 1

                Text {
                    text: qsTr("Уже прозвучало")
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                    font.weight: Font.DemiBold
                }

                Repeater {
                    model: wave.history
                    delegate: TrackRow {
                        Layout.fillWidth: true
                        interactive: false
                        dimmed: true
                    }
                }
            }
        }
    }
}
