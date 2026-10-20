import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The numbers of the library for an administrator: how many tracks there are, how many
    of them have words, and how many of those are synced to the music.
*/
Flickable {
    id: root

    //! A phone: one column of cards instead of a row.
    property bool compact: false

    readonly property var stats: library.adminStats
    readonly property bool loaded: stats.tracks !== undefined
    readonly property int margin: compact ? 14 : 24

    function refresh() { library.loadAdminStats() }

    function percent(part, whole) {
        return whole > 0 ? Math.round(100 * part / whole) : 0
    }

    function size(bytes) {
        const gb = bytes / 1073741824
        return gb >= 1 ? gb.toFixed(1) + " ГБ" : Math.round(bytes / 1048576) + " МБ"
    }

    contentWidth: width
    contentHeight: content.implicitHeight + 2 * margin
    boundsBehavior: Flickable.StopAtBounds
    clip: true

    ScrollBar.vertical: FlatScrollBar {}

    Column {
        id: content
        x: root.margin
        y: root.margin
        width: root.width - 2 * root.margin
        spacing: 22

        // --- the three numbers that matter ---
        Flow {
            width: parent.width
            spacing: 14

            Repeater {
                model: [
                    { label: qsTr("Треков"), value: root.loaded ? root.stats.tracks : -1,
                      note: root.loaded ? qsTr("в библиотеке") : "" },
                    { label: qsTr("Текстов"), value: root.loaded ? root.stats.with_lyrics : -1,
                      note: root.loaded ? root.percent(root.stats.with_lyrics, root.stats.tracks) + qsTr("% треков") : "" },
                    { label: qsTr("Синхронизировано"), value: root.loaded ? root.stats.synced_lyrics : -1,
                      note: root.loaded ? root.percent(root.stats.synced_lyrics, root.stats.tracks) + qsTr("% треков") : "" }
                ]

                delegate: Rectangle {
                    id: card

                    required property var modelData

                    width: root.compact ? content.width : Math.floor((content.width - 2 * 14) / 3)
                    height: 112
                    color: Theme.panel
                    border.color: Theme.border
                    border.width: 1

                    Mono {
                        x: 18
                        y: 16
                        text: card.modelData.label
                        color: Theme.faint
                    }
                    Text {
                        x: 18
                        y: 38
                        text: card.modelData.value >= 0 ? card.modelData.value : "—"
                        color: Theme.text
                        font.family: Theme.sans
                        font.pixelSize: 40
                        font.weight: Font.Bold
                    }
                    Mono {
                        x: 18
                        y: 88
                        text: card.modelData.note
                        color: Theme.muted
                        font.capitalization: Font.MixedCase
                    }
                }
            }
        }

        // --- coverage bars ---
        Rectangle {
            width: parent.width
            height: bars.implicitHeight + 36
            visible: root.loaded
            color: Theme.panel
            border.color: Theme.border
            border.width: 1

            Column {
                id: bars
                x: 18
                y: 18
                width: parent.width - 36
                spacing: 16

                Repeater {
                    model: [
                        { label: qsTr("С текстом"), part: root.loaded ? root.stats.with_lyrics : 0,
                          color: Theme.accent },
                        { label: qsTr("Синхронизирован с музыкой"),
                          part: root.loaded ? root.stats.synced_lyrics : 0, color: Theme.positive }
                    ]

                    delegate: Column {
                        id: bar

                        required property var modelData

                        width: bars.width
                        spacing: 8

                        RowLayout {
                            width: parent.width

                            Mono {
                                Layout.fillWidth: true
                                text: bar.modelData.label
                                color: Theme.muted
                            }
                            Mono {
                                text: bar.modelData.part + " / " + root.stats.tracks
                                      + "  ·  " + root.percent(bar.modelData.part, root.stats.tracks) + "%"
                                color: Theme.text
                                font.capitalization: Font.MixedCase
                            }
                        }
                        Rectangle {
                            width: parent.width
                            height: 6
                            color: Theme.border

                            Rectangle {
                                width: root.stats.tracks > 0
                                       ? parent.width * Math.min(1, bar.modelData.part / root.stats.tracks) : 0
                                height: parent.height
                                color: bar.modelData.color
                            }
                        }
                    }
                }
            }
        }

        // --- the rest ---
        Flow {
            width: parent.width
            spacing: 14
            visible: root.loaded

            Repeater {
                model: root.loaded ? [
                    { label: qsTr("Только текст, без синхронизации"), value: root.stats.plain_lyrics },
                    { label: qsTr("Без текста"), value: root.stats.without_lyrics },
                    { label: qsTr("Исполнителей"), value: root.stats.artists },
                    { label: qsTr("Альбомов"), value: root.stats.albums },
                    { label: qsTr("Размер библиотеки"), value: root.size(root.stats.storage_bytes) }
                ] : []

                delegate: Rectangle {
                    id: small

                    required property var modelData

                    width: root.compact ? Math.floor((content.width - 14) / 2)
                                        : Math.floor((content.width - 4 * 14) / 5)
                    height: 84
                    color: "transparent"
                    border.color: Theme.border
                    border.width: 1

                    Text {
                        x: 14
                        y: 12
                        width: parent.width - 28
                        text: small.modelData.value
                        color: Theme.text
                        font.family: Theme.sans
                        font.pixelSize: 24
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    Mono {
                        x: 14
                        y: 52
                        width: parent.width - 28
                        text: small.modelData.label
                        color: Theme.faint
                        font.capitalization: Font.MixedCase
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                    }
                }
            }
        }

        Mono {
            width: parent.width
            visible: !root.loaded
            text: qsTr("Нет данных. Если сервер старой версии, его нужно обновить: эта страница "
                       + "читает числа у самого сервера.")
            color: Theme.faint
            font.capitalization: Font.MixedCase
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }

        FlatButton {
            glyph: Theme.iRefresh
            text: qsTr("Обновить")
            onClicked: root.refresh()
        }
    }
}
