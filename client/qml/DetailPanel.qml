import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    "03 ТРЕК": everything the server knows about the selected track.

    The bars are the audio features the wave actually ranks on, so this is also
    the answer to "why did it pick this".
*/
Rectangle {
    id: root

    //! A track as a variant map, or null.
    property var track: null
    //! False where playing from here makes no sense (the history).
    property bool canPlay: true

    signal playRequested()
    signal deleteRequested()
    signal editRequested()

    color: Theme.panel

    readonly property bool hasTrack: track !== null && track !== undefined && !!track.id
    readonly property bool isPlaying: hasTrack && player.hasTrack && player.currentTrack.id === track.id

    // List endpoints omit the audio features, so fall back to the full record
    // the library controller fetched for this track.
    readonly property var features: {
        if (!hasTrack)
            return ({})
        if (track.features && Object.keys(track.features).length > 0)
            return track.features
        if (library.detail.id === track.id && library.detail.features)
            return library.detail.features
        return ({})
    }
    readonly property bool hasFeatures: Object.keys(features).length > 0

    readonly property var barDefinitions: [
        { key: "energy",           label: qsTr("Энергия") },
        { key: "valence",          label: qsTr("Настроение") },
        { key: "danceability",     label: qsTr("Танцевальность") },
        { key: "acousticness",     label: qsTr("Акустичность") },
        { key: "instrumentalness", label: qsTr("Без слов") },
        { key: "brightness",       label: qsTr("Яркость") },
        { key: "loudness",         label: qsTr("Громкость") },
        { key: "dynamics",         label: qsTr("Динамика") }
    ]

    readonly property var shortcuts: [
        { keys: "Enter",  action: qsTr("Слушать") },
        { keys: "Space",  action: qsTr("Пауза / продолжить") },
        { keys: "N",      action: qsTr("Следующий трек") },
        { keys: "L",      action: qsTr("Нравится") },
        { keys: "D",      action: qsTr("Не нравится") },
        { keys: "Ctrl F", action: qsTr("Поиск") },
        { keys: "Ctrl U", action: qsTr("Загрузить музыку") },
        { keys: "Ctrl B", action: qsTr("Эта панель") }
    ]

    function keyName(index) {
        const names = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"]
        return index >= 0 && index < names.length ? names[index] : ""
    }

    function musicalKey() {
        if (features.musical_key === undefined || features.musical_key === null)
            return ""
        const name = keyName(features.musical_key)
        if (name === "")
            return ""
        return name + (features.musical_mode === 1 ? qsTr(" мажор")
                       : features.musical_mode === 0 ? qsTr(" минор") : "")
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SectionHeader {
            Layout.fillWidth: true
            title: qsTr("Трек")
        }

        // --- nothing selected ---
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.hasTrack

            ColumnLayout {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.margins: 20
                spacing: 14

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Выберите трек, чтобы увидеть детали.")
                    color: Theme.muted
                    font.family: Theme.sans
                    font.pixelSize: Theme.fontTitle
                    font.weight: Font.Bold
                    wrapMode: Text.WordWrap
                    lineHeight: 1.05
                }

                Column {
                    Layout.fillWidth: true
                    spacing: 6

                    Repeater {
                        model: root.shortcuts

                        delegate: Row {
                            id: hint
                            required property var modelData
                            spacing: 14

                            Kbd {
                                keys: hint.modelData.keys
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: hint.modelData.action
                                color: Theme.muted
                                font.family: Theme.sans
                                font.pixelSize: Theme.fontSmall
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }
                }
            }
        }

        // --- a track ---
        Flickable {
            id: flick
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.hasTrack
            clip: true
            contentWidth: width
            contentHeight: body.implicitHeight + 24
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: FlatScrollBar {}

            ColumnLayout {
                id: body
                x: 14
                y: 14
                width: flick.width - 28
                spacing: 12

                CoverArt {
                    Layout.preferredWidth: Math.min(body.width, 240)
                    Layout.preferredHeight: Layout.preferredWidth
                    coverPath: root.hasTrack ? (root.track.coverPath || "") : ""
                    title: root.hasTrack ? root.track.title : ""
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3

                    Text {
                        Layout.fillWidth: true
                        text: root.hasTrack ? root.track.title : ""
                        color: Theme.text
                        font.family: Theme.sans
                        font.pixelSize: Theme.fontTitle
                        font.weight: Font.Bold
                        wrapMode: Text.WordWrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                        lineHeight: 1.05
                    }
                    ArtistLinks {
                        Layout.fillWidth: true
                        artists: root.hasTrack ? (root.track.artists || []) : []
                        fallback: root.hasTrack ? root.track.artistName : ""
                        color: Theme.muted
                        font.pixelSize: Theme.fontBody
                    }
                    Mono {
                        Layout.fillWidth: true
                        visible: root.hasTrack && !!root.track.albumTitle
                        text: root.hasTrack ? root.track.albumTitle : ""
                        color: Theme.faint
                        font.capitalization: Font.MixedCase
                        font.letterSpacing: 0.2
                    }
                }

                // why the wave chose it
                Rectangle {
                    Layout.preferredHeight: 22
                    Layout.preferredWidth: reasonLabel.implicitWidth + 20
                    visible: root.isPlaying && wave.currentReason !== ""
                    color: Theme.alpha(Theme.accent, 0.16)
                    border.color: Theme.accent
                    border.width: 1

                    Mono {
                        id: reasonLabel
                        anchors.centerIn: parent
                        text: wave.currentReason
                        color: Theme.accentText
                        font.capitalization: Font.MixedCase
                        font.letterSpacing: 0.2
                    }
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: 6
                    visible: root.hasTrack

                    Repeater {
                        model: root.hasTrack ? (root.track.genres || []) : []

                        delegate: Rectangle {
                            id: chip
                            required property string modelData
                            width: chipText.implicitWidth + 14
                            height: 20
                            color: "transparent"
                            border.color: Theme.borderStrong
                            border.width: 1

                            Mono {
                                id: chipText
                                anchors.centerIn: parent
                                text: chip.modelData
                                font.pixelSize: 10
                            }
                        }
                    }

                    Rectangle {
                        visible: root.hasTrack && !!root.track.quality
                        width: qualityText.implicitWidth + 14
                        height: 20
                        color: "transparent"
                        border.color: Theme.borderStrong
                        border.width: 1

                        Mono {
                            id: qualityText
                            anchors.centerIn: parent
                            text: root.hasTrack ? root.track.quality : ""
                            font.pixelSize: 10
                            color: root.hasTrack && root.track.lossless ? Theme.positive : Theme.muted
                        }
                    }
                }

                // --- actions ---
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    FlatButton {
                        primary: true
                        glyph: Theme.iPlay
                        text: qsTr("Слушать")
                        visible: !root.isPlaying && root.canPlay
                        enabledWhen: root.hasTrack
                        onClicked: root.playRequested()
                    }
                    FlatButton {
                        glyph: root.hasTrack && root.track.liked ? Theme.iHeartFill : Theme.iHeart
                        text: qsTr("Нравится")
                        onClicked: library.toggleLike(root.track.id)
                    }
                    IconButton {
                        size: 30
                        glyph: Theme.iDislike
                        active: root.hasTrack && root.track.disliked
                        activeColor: Theme.negative
                        tooltip: qsTr("Не нравится — больше не покажем")
                        onClicked: root.isPlaying && player.context === "wave"
                                   ? wave.dislike() : library.toggleDislike(root.track.id)
                    }

                    Item { Layout.fillWidth: true }

                    // correcting and removing music are for administrators
                    IconButton {
                        visible: auth.isAdmin
                        size: 28
                        glyph: Theme.iEdit
                        tooltip: qsTr("Изменить метаданные")
                        onClicked: root.editRequested()
                    }
                    IconButton {
                        visible: auth.isAdmin
                        size: 28
                        glyph: Theme.iDelete
                        activeColor: Theme.negative
                        tooltip: qsTr("Удалить из библиотеки · Del")
                        onClicked: root.deleteRequested()
                    }
                }

                // --- what the server heard in it ---
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.border
                }

                Mono {
                    text: qsTr("Характеристики звука")
                    color: Theme.faint
                    font.pixelSize: 10
                }

                Mono {
                    visible: !root.hasFeatures
                    Layout.fillWidth: true
                    text: qsTr("Загружаем…")
                    color: Theme.faint
                }

                // tempo and key are numbers, not 0..1 bars
                RowLayout {
                    Layout.fillWidth: true
                    visible: root.hasFeatures
                    spacing: 16

                    ColumnLayout {
                        spacing: 0
                        Mono { text: qsTr("Темп"); font.pixelSize: 10; color: Theme.faint }
                        Text {
                            text: root.hasFeatures && root.features.tempo_bpm > 0
                                  ? Math.round(root.features.tempo_bpm) + " BPM" : "—"
                            color: Theme.text
                            font.family: Theme.monoFamily
                            font.pixelSize: Theme.fontBody
                        }
                    }
                    ColumnLayout {
                        spacing: 0
                        visible: root.musicalKey() !== ""
                        Mono { text: qsTr("Тональность"); font.pixelSize: 10; color: Theme.faint }
                        Text {
                            text: root.musicalKey()
                            color: Theme.text
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontBody
                        }
                    }
                    ColumnLayout {
                        spacing: 0
                        visible: root.hasFeatures && !!root.features.language
                                 && root.features.language !== "unknown"
                        Mono { text: qsTr("Язык"); font.pixelSize: 10; color: Theme.faint }
                        Text {
                            text: root.hasFeatures ? root.features.language : ""
                            color: Theme.text
                            font.family: Theme.sans
                            font.pixelSize: Theme.fontBody
                        }
                    }
                }

                Repeater {
                    model: root.hasFeatures ? root.barDefinitions : []

                    delegate: RowLayout {
                        id: bar

                        required property var modelData
                        readonly property real value: Math.max(0, Math.min(1,
                                                      root.features[modelData.key] || 0))

                        Layout.fillWidth: true
                        spacing: 10

                        Mono {
                            Layout.preferredWidth: 112
                            text: bar.modelData.label
                            font.pixelSize: 10
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 3
                            color: Theme.borderStrong

                            Rectangle {
                                width: parent.width * bar.value
                                height: parent.height
                                color: Theme.accent
                            }
                        }

                        Mono {
                            Layout.preferredWidth: 28
                            horizontalAlignment: Text.AlignRight
                            text: Math.round(bar.value * 100)
                            color: Theme.text
                            font.pixelSize: 10
                        }
                    }
                }
            }
        }
    }
}
