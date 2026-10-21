import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The administrators and what each of them has done to the library: tracks added and
    deleted, lyrics added and lyrics synced to the music. Above them, the same four numbers
    for everyone together.
*/
Flickable {
    id: root

    //! A phone: the numbers of an administrator in two columns instead of a row of four.
    property bool compact: false

    readonly property var team: library.adminTeam
    readonly property bool loaded: team.admins !== undefined
    readonly property int margin: compact ? 14 : 24

    readonly property var kinds: [
        { key: "tracks_added", label: qsTr("Треков добавлено"), color: Theme.positive },
        { key: "tracks_deleted", label: qsTr("Треков удалено"), color: Theme.negative },
        { key: "lyrics_added", label: qsTr("Текстов добавлено"), color: Theme.accentText },
        { key: "lyrics_synced", label: qsTr("Синхронизировано"), color: Theme.warning }
    ]

    function refresh() { library.loadAdminTeam() }

    function seen(iso) {
        if (!iso)
            return qsTr("ещё не заходил")
        // the server stores UTC and sends it without a zone, which would be read as local time
        const utc = /(Z|[+-]\d\d:?\d\d)$/.test(iso) ? iso : iso + "Z"
        return qsTr("был в сети ") + Qt.formatDateTime(new Date(utc), "dd.MM.yyyy HH:mm")
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

        // --- everyone together ---
        Column {
            width: parent.width
            spacing: 10
            visible: root.loaded

            Mono {
                text: qsTr("Всего")
                color: Theme.faint
            }

            Flow {
                width: parent.width
                spacing: 14

                Repeater {
                    model: root.loaded ? root.kinds : []

                    delegate: Rectangle {
                        id: total

                        required property var modelData

                        width: root.compact ? Math.floor((content.width - 14) / 2)
                                            : Math.floor((content.width - 3 * 14) / 4)
                        height: 96
                        color: Theme.panel
                        border.color: Theme.border
                        border.width: 1

                        Rectangle {
                            width: 3
                            height: parent.height
                            color: total.modelData.color
                        }
                        Text {
                            x: 18
                            y: 14
                            text: root.team.totals[total.modelData.key]
                            color: Theme.text
                            font.family: Theme.sans
                            font.pixelSize: 34
                            font.weight: Font.Bold
                        }
                        Mono {
                            x: 18
                            y: 64
                            width: parent.width - 30
                            text: total.modelData.label
                            color: Theme.faint
                            font.capitalization: Font.MixedCase
                            font.pixelSize: 11
                        }
                    }
                }
            }
        }

        // --- one card per administrator ---
        Column {
            width: parent.width
            spacing: 10
            visible: root.loaded

            Mono {
                text: qsTr("Администраторы") + "  ·  " + (root.loaded ? root.team.admins.length : 0)
                color: Theme.faint
            }

            Repeater {
                model: root.loaded ? root.team.admins : []

                delegate: Rectangle {
                    id: card

                    required property var modelData

                    width: content.width
                    height: head.height + figures.height + 36
                    color: Theme.panel
                    border.color: card.modelData.is_you ? Theme.accent : Theme.border
                    border.width: 1

                    Row {
                        id: head
                        x: 16
                        y: 16
                        width: parent.width - 32
                        height: 48
                        spacing: 14

                        ArtistAvatar {
                            width: 48
                            height: 48
                            name: card.modelData.display_name
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 62
                            spacing: 4

                            Row {
                                spacing: 10

                                Text {
                                    text: card.modelData.display_name
                                    color: Theme.text
                                    font.family: Theme.sans
                                    font.pixelSize: 16
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    width: Math.min(implicitWidth, head.width - 120)
                                }
                                Mono {
                                    visible: card.modelData.is_you
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: qsTr("Вы")
                                    color: Theme.accentText
                                }
                            }
                            Mono {
                                width: parent.width
                                text: "@" + card.modelData.username + "  ·  " + root.seen(card.modelData.last_seen_at)
                                color: Theme.faint
                                font.capitalization: Font.MixedCase
                            }
                        }
                    }

                    Flow {
                        id: figures
                        x: 16
                        y: head.y + head.height + 16
                        width: parent.width - 32
                        spacing: 10

                        Repeater {
                            model: root.kinds

                            delegate: Item {
                                id: figure

                                required property var modelData

                                width: root.compact ? Math.floor((figures.width - 10) / 2)
                                                    : Math.floor((figures.width - 3 * 10) / 4)
                                height: 48

                                Rectangle {
                                    width: 3
                                    height: parent.height
                                    color: figure.modelData.color
                                }
                                Text {
                                    x: 12
                                    text: card.modelData[figure.modelData.key]
                                    color: Theme.text
                                    font.family: Theme.sans
                                    font.pixelSize: 22
                                    font.weight: Font.DemiBold
                                }
                                Mono {
                                    x: 12
                                    y: 30
                                    width: parent.width - 14
                                    text: figure.modelData.label
                                    color: Theme.faint
                                    font.capitalization: Font.MixedCase
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }
        }

        Mono {
            width: parent.width
            visible: root.loaded
            text: qsTr("Добавленные треки учтены по тому, кто их загрузил. Удаления и тексты "
                       + "считаются с момента обновления сервера, раньше их никто не записывал.")
            color: Theme.faint
            font.capitalization: Font.MixedCase
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
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
